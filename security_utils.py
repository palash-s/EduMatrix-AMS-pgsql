"""
Security Utilities for EduMatrix-AMS
=====================================
This module provides centralized security utilities including:
- Input validation and sanitization (OWASP compliant)
- Schema-based validation for API endpoints
- Rate limiting helpers
- Secure error handling

OWASP Top 10 Considerations:
- A01: Broken Access Control - Use role-based decorators
- A02: Cryptographic Failures - Use secure random, no hardcoded secrets
- A03: Injection - Schema validation, type checking, length limits
- A04: Insecure Design - Centralized security patterns
- A05: Security Misconfiguration - Environment-based config
- A09: Logging & Monitoring - Secure logging without sensitive data
"""

import re
import html
import logging
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple, Union
from flask import request, jsonify, current_app


# ==============================================================================
# CONFIGURATION CONSTANTS
# ==============================================================================

# Maximum field lengths (prevent DoS via large payloads)
MAX_STRING_LENGTH = 500          # General string fields
MAX_NAME_LENGTH = 100            # Names (user, school, department, etc.)
MAX_EMAIL_LENGTH = 254           # RFC 5321 compliant
MAX_TEXT_LENGTH = 5000           # Long text fields (remarks, descriptions)
MAX_CODE_LENGTH = 20             # Short codes (department codes, etc.)
MAX_PASSWORD_LENGTH = 128        # Password max length
MIN_PASSWORD_LENGTH = 8          # Password min length
MAX_LIST_ITEMS = 100             # Maximum items in array fields
MAX_REQUEST_SIZE_BYTES = 10 * 1024 * 1024  # 10MB max request size

# Regex patterns for validation
PATTERNS = {
    # Email: RFC 5322 simplified
    'email': re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
    # Username: alphanumeric, underscore, dot, hyphen (3-50 chars)
    'username': re.compile(r'^[a-zA-Z0-9._-]{3,50}$'),
    # Phone: digits, spaces, dashes, parens, plus (7-20 chars)
    'phone': re.compile(r'^[\d\s\-\(\)\+]{7,20}$'),
    # UUID: standard UUID format
    'uuid': re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'),
    # Alphanumeric code
    'code': re.compile(r'^[a-zA-Z0-9_-]{1,20}$'),
    # Date: YYYY-MM-DD
    'date': re.compile(r'^\d{4}-\d{2}-\d{2}$'),
    # Time: HH:MM or HH:MM:SS
    'time': re.compile(r'^\d{2}:\d{2}(:\d{2})?$'),
    # Safe filename: alphanumeric, underscore, hyphen, dot
    'filename': re.compile(r'^[a-zA-Z0-9._-]{1,255}$'),
    # Integer string
    'integer': re.compile(r'^-?\d+$'),
    # Positive integer string
    'positive_int': re.compile(r'^\d+$'),
    # Float string
    'float': re.compile(r'^-?\d+(\.\d+)?$'),
}

# Characters that should be stripped or escaped
DANGEROUS_CHARS = ['<', '>', '"', "'", '&', '\x00', '\n', '\r', '\t']


# ==============================================================================
# LOGGING UTILITIES (Secure - no sensitive data)
# ==============================================================================

def _mask_email(email: str) -> str:
    """Mask email for logging (show first 2 chars and domain)."""
    if not email or '@' not in email:
        return '***'
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        return f'{local[0]}***@{domain}'
    return f'{local[:2]}***@{domain}'


def _mask_id(user_id: str) -> str:
    """Mask user ID for logging (show first 8 chars)."""
    if not user_id:
        return '***'
    return f'{user_id[:8]}...' if len(user_id) > 8 else user_id


def log_security_event(event_type: str, details: Dict[str, Any], level: str = 'warning') -> None:
    """
    Log security-related events without exposing sensitive data.

    Args:
        event_type: Type of security event (e.g., 'rate_limit', 'auth_failure')
        details: Event details (will be sanitized)
        level: Log level ('info', 'warning', 'error', 'critical')
    """
    logger = logging.getLogger('security')

    # Sanitize details - mask sensitive fields
    safe_details = {}
    for key, value in details.items():
        if key in ('password', 'token', 'secret', 'api_key', 'refresh_token'):
            safe_details[key] = '***REDACTED***'
        elif key in ('email', 'username'):
            safe_details[key] = _mask_email(str(value)) if '@' in str(value) else value
        elif key in ('user_id', 'student_id', 'staff_id'):
            safe_details[key] = _mask_id(str(value))
        else:
            safe_details[key] = value

    # Get client IP safely
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip:
        client_ip = client_ip.split(',')[0].strip()  # First IP in chain

    log_msg = f"[SECURITY:{event_type}] IP={client_ip} {safe_details}"

    log_func = getattr(logger, level, logger.warning)
    log_func(log_msg)


# ==============================================================================
# INPUT VALIDATION & SANITIZATION
# ==============================================================================

class ValidationError(Exception):
    """Custom exception for validation failures."""
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(message)


def sanitize_string(value: Any, max_length: int = MAX_STRING_LENGTH,
                    allow_html: bool = False, strip: bool = True) -> str:
    """
    Sanitize a string value for safe use.

    Args:
        value: Input value to sanitize
        max_length: Maximum allowed length
        allow_html: If False, escape HTML entities
        strip: If True, strip leading/trailing whitespace

    Returns:
        Sanitized string
    """
    if value is None:
        return ''

    # Convert to string
    result = str(value)

    # Strip whitespace
    if strip:
        result = result.strip()

    # Remove null bytes (potential injection)
    result = result.replace('\x00', '')

    # Escape HTML if not allowed
    if not allow_html:
        result = html.escape(result, quote=True)

    # Enforce length limit
    if len(result) > max_length:
        result = result[:max_length]

    return result


def validate_email(value: Any, required: bool = True) -> Optional[str]:
    """Validate and normalize email address."""
    if value is None or str(value).strip() == '':
        if required:
            raise ValidationError("Email is required", "email")
        return None

    email = str(value).strip().lower()

    if len(email) > MAX_EMAIL_LENGTH:
        raise ValidationError(f"Email exceeds maximum length of {MAX_EMAIL_LENGTH}", "email")

    if not PATTERNS['email'].match(email):
        raise ValidationError("Invalid email format", "email")

    return email


def validate_string(value: Any, field_name: str, required: bool = True,
                   min_length: int = 0, max_length: int = MAX_STRING_LENGTH,
                   pattern: str = None, allowed_values: List[str] = None) -> Optional[str]:
    """
    Validate a string field with comprehensive checks.

    Args:
        value: Input value
        field_name: Name of the field (for error messages)
        required: If True, field must have a non-empty value
        min_length: Minimum string length
        max_length: Maximum string length
        pattern: Regex pattern key from PATTERNS dict or custom regex string
        allowed_values: List of allowed values (enum validation)

    Returns:
        Validated and sanitized string, or None if not required and empty
    """
    # Handle None/empty
    if value is None or str(value).strip() == '':
        if required:
            raise ValidationError(f"{field_name} is required", field_name)
        return None

    # Sanitize
    result = sanitize_string(value, max_length=max_length)

    # Length checks
    if len(result) < min_length:
        raise ValidationError(
            f"{field_name} must be at least {min_length} characters",
            field_name
        )

    if len(result) > max_length:
        raise ValidationError(
            f"{field_name} exceeds maximum length of {max_length}",
            field_name
        )

    # Pattern validation
    if pattern:
        regex = PATTERNS.get(pattern) if pattern in PATTERNS else re.compile(pattern)
        if not regex.match(result):
            raise ValidationError(f"Invalid {field_name} format", field_name)

    # Enum validation
    if allowed_values and result not in allowed_values:
        raise ValidationError(
            f"Invalid {field_name}. Allowed values: {', '.join(allowed_values)}",
            field_name
        )

    return result


def validate_integer(value: Any, field_name: str, required: bool = True,
                    min_value: int = None, max_value: int = None) -> Optional[int]:
    """Validate an integer field."""
    if value is None or str(value).strip() == '':
        if required:
            raise ValidationError(f"{field_name} is required", field_name)
        return None

    try:
        result = int(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{field_name} must be a valid integer", field_name)

    if min_value is not None and result < min_value:
        raise ValidationError(f"{field_name} must be at least {min_value}", field_name)

    if max_value is not None and result > max_value:
        raise ValidationError(f"{field_name} must not exceed {max_value}", field_name)

    return result


def validate_float(value: Any, field_name: str, required: bool = True,
                  min_value: float = None, max_value: float = None) -> Optional[float]:
    """Validate a float field."""
    if value is None or str(value).strip() == '':
        if required:
            raise ValidationError(f"{field_name} is required", field_name)
        return None

    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{field_name} must be a valid number", field_name)

    if min_value is not None and result < min_value:
        raise ValidationError(f"{field_name} must be at least {min_value}", field_name)

    if max_value is not None and result > max_value:
        raise ValidationError(f"{field_name} must not exceed {max_value}", field_name)

    return result


def validate_boolean(value: Any, field_name: str, required: bool = True) -> Optional[bool]:
    """Validate a boolean field."""
    if value is None:
        if required:
            raise ValidationError(f"{field_name} is required", field_name)
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        if value.lower() in ('true', '1', 'yes', 'on'):
            return True
        elif value.lower() in ('false', '0', 'no', 'off'):
            return False

    if isinstance(value, (int, float)):
        return bool(value)

    raise ValidationError(f"{field_name} must be a boolean value", field_name)


def validate_date(value: Any, field_name: str, required: bool = True) -> Optional[str]:
    """Validate a date string in YYYY-MM-DD format."""
    if value is None or str(value).strip() == '':
        if required:
            raise ValidationError(f"{field_name} is required", field_name)
        return None

    date_str = str(value).strip()

    if not PATTERNS['date'].match(date_str):
        raise ValidationError(f"{field_name} must be in YYYY-MM-DD format", field_name)

    # Additional validation: check if date is valid
    try:
        from datetime import datetime
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        raise ValidationError(f"{field_name} is not a valid date", field_name)

    return date_str


def validate_list(value: Any, field_name: str, required: bool = True,
                 min_items: int = 0, max_items: int = MAX_LIST_ITEMS,
                 item_validator: callable = None) -> Optional[List]:
    """
    Validate a list/array field.

    Args:
        value: Input value (should be a list)
        field_name: Name of the field
        required: If True, list must have at least one item
        min_items: Minimum number of items
        max_items: Maximum number of items
        item_validator: Optional function to validate each item

    Returns:
        Validated list
    """
    if value is None:
        if required:
            raise ValidationError(f"{field_name} is required", field_name)
        return None

    if not isinstance(value, list):
        raise ValidationError(f"{field_name} must be a list", field_name)

    if len(value) < min_items:
        raise ValidationError(
            f"{field_name} must have at least {min_items} items",
            field_name
        )

    if len(value) > max_items:
        raise ValidationError(
            f"{field_name} exceeds maximum of {max_items} items",
            field_name
        )

    if item_validator:
        validated_items = []
        for i, item in enumerate(value):
            try:
                validated_items.append(item_validator(item))
            except ValidationError as e:
                raise ValidationError(
                    f"{field_name}[{i}]: {e.message}",
                    f"{field_name}[{i}]"
                )
        return validated_items

    return value


def validate_uuid(value: Any, field_name: str, required: bool = True) -> Optional[str]:
    """Validate a UUID string."""
    if value is None or str(value).strip() == '':
        if required:
            raise ValidationError(f"{field_name} is required", field_name)
        return None

    uuid_str = str(value).strip().lower()

    if not PATTERNS['uuid'].match(uuid_str):
        raise ValidationError(f"{field_name} must be a valid UUID", field_name)

    return uuid_str


# ==============================================================================
# SCHEMA-BASED VALIDATION
# ==============================================================================

class Schema:
    """
    Schema-based validation for request payloads.

    Example:
        schema = Schema({
            'username': {'type': 'string', 'required': True, 'min_length': 3},
            'email': {'type': 'email', 'required': True},
            'age': {'type': 'integer', 'min_value': 18, 'max_value': 120},
            'role': {'type': 'string', 'allowed_values': ['student', 'staff', 'admin']},
            'tags': {'type': 'list', 'max_items': 10}
        })

        validated_data = schema.validate(request.json)
    """

    VALIDATORS = {
        'string': validate_string,
        'email': validate_email,
        'integer': validate_integer,
        'float': validate_float,
        'boolean': validate_boolean,
        'date': validate_date,
        'list': validate_list,
        'uuid': validate_uuid,
    }

    def __init__(self, fields: Dict[str, Dict], strict: bool = True):
        """
        Initialize schema.

        Args:
            fields: Dictionary of field definitions
            strict: If True, reject unexpected fields
        """
        self.fields = fields
        self.strict = strict

    def validate(self, data: Dict[str, Any], partial: bool = False) -> Dict[str, Any]:
        """
        Validate data against the schema.

        Args:
            data: Input data dictionary
            partial: If True, skip required checks (for PATCH operations)

        Returns:
            Validated and sanitized data dictionary

        Raises:
            ValidationError: If validation fails
        """
        if data is None:
            data = {}

        if not isinstance(data, dict):
            raise ValidationError("Request body must be a JSON object", "body")

        # Check for unexpected fields (strict mode)
        if self.strict:
            unexpected = set(data.keys()) - set(self.fields.keys())
            if unexpected:
                raise ValidationError(
                    f"Unexpected fields: {', '.join(sorted(unexpected))}",
                    "body"
                )

        result = {}
        errors = []

        for field_name, field_def in self.fields.items():
            value = data.get(field_name)
            field_type = field_def.get('type', 'string')
            required = field_def.get('required', False) and not partial

            try:
                validator = self.VALIDATORS.get(field_type, validate_string)

                # Build validator kwargs
                kwargs = {'required': required}
                if 'field_name' not in kwargs:
                    kwargs['field_name'] = field_name if field_type != 'email' else None

                # Add type-specific options
                for opt in ['min_length', 'max_length', 'min_value', 'max_value',
                           'pattern', 'allowed_values', 'min_items', 'max_items']:
                    if opt in field_def:
                        kwargs[opt] = field_def[opt]

                # Handle email specially (different signature)
                if field_type == 'email':
                    validated_value = validate_email(value, required=required)
                elif field_type == 'uuid':
                    validated_value = validate_uuid(value, field_name, required=required)
                else:
                    validated_value = validator(value, field_name, **{
                        k: v for k, v in kwargs.items()
                        if k != 'field_name'
                    })

                # Only include non-None values
                if validated_value is not None:
                    result[field_name] = validated_value

            except ValidationError as e:
                errors.append(f"{field_name}: {e.message}")

        if errors:
            raise ValidationError("; ".join(errors), "validation")

        return result


def validate_request(schema: Schema = None, fields: Dict = None):
    """
    Decorator to validate request JSON against a schema.

    Usage:
        @app.route('/api/user', methods=['POST'])
        @validate_request(fields={
            'username': {'type': 'string', 'required': True},
            'email': {'type': 'email', 'required': True}
        })
        def create_user():
            # request.validated_data contains validated input
            ...
    """
    if fields:
        schema = Schema(fields)

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if schema:
                try:
                    data = request.get_json(force=True, silent=True) or {}
                    request.validated_data = schema.validate(data)
                except ValidationError as e:
                    log_security_event('validation_failure', {
                        'endpoint': request.endpoint,
                        'error': e.message
                    })
                    return jsonify({
                        "error": "Validation failed",
                        "details": e.message
                    }), 400
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ==============================================================================
# RATE LIMITING HELPERS
# ==============================================================================

def get_rate_limit_key() -> str:
    """
    Get a composite key for rate limiting.
    Combines IP address with authenticated user ID if available.

    Returns:
        Rate limit key string
    """
    from flask_login import current_user

    # Get client IP (handle proxies)
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip:
        client_ip = client_ip.split(',')[0].strip()

    # Combine with user ID if authenticated
    user_part = ''
    try:
        if current_user and current_user.is_authenticated:
            user_part = f':{current_user.user_id}'
    except Exception:
        pass

    return f'{client_ip}{user_part}'


def create_rate_limit_exceeded_response():
    """
    Create a graceful 429 response for rate limiting.

    Returns:
        Flask response tuple (body, status_code, headers)
    """
    log_security_event('rate_limit_exceeded', {
        'endpoint': request.endpoint,
        'method': request.method
    })

    return jsonify({
        "error": "Too many requests",
        "message": "You have exceeded the rate limit. Please wait before retrying.",
        "retry_after": 60  # Suggest retry in 60 seconds
    }), 429, {'Retry-After': '60'}


# ==============================================================================
# PASSWORD VALIDATION
# ==============================================================================

def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validate password meets security requirements.

    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters"

    if len(password) > MAX_PASSWORD_LENGTH:
        return False, f"Password must not exceed {MAX_PASSWORD_LENGTH} characters"

    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"

    return True, ""


# ==============================================================================
# FILE UPLOAD VALIDATION
# ==============================================================================

ALLOWED_UPLOAD_EXTENSIONS = {'csv', 'xlsx', 'xls'}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

def validate_file_upload(file, allowed_extensions: set = None,
                         max_size: int = None) -> Tuple[bool, str]:
    """
    Validate an uploaded file.

    Args:
        file: FileStorage object from request.files
        allowed_extensions: Set of allowed file extensions
        max_size: Maximum file size in bytes

    Returns:
        Tuple of (is_valid, error_message)
    """
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_UPLOAD_EXTENSIONS

    if max_size is None:
        max_size = MAX_UPLOAD_SIZE

    if not file or not file.filename:
        return False, "No file provided"

    # Check extension
    filename = file.filename
    if '.' not in filename:
        return False, "File must have an extension"

    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in allowed_extensions:
        return False, f"File type not allowed. Allowed: {', '.join(allowed_extensions)}"

    # Check file size
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Seek back to start

    if size > max_size:
        return False, f"File too large. Maximum size: {max_size // (1024*1024)}MB"

    if size == 0:
        return False, "File is empty"

    return True, ""


# ==============================================================================
# COMMON SCHEMAS FOR REUSE
# ==============================================================================

# Login request schema
LOGIN_SCHEMA = Schema({
    'username': {
        'type': 'string',
        'required': True,
        'min_length': 1,
        'max_length': 100
    },
    'password': {
        'type': 'string',
        'required': True,
        'min_length': 1,
        'max_length': MAX_PASSWORD_LENGTH
    }
}, strict=False)  # Allow device_id, etc.

# Change password schema
CHANGE_PASSWORD_SCHEMA = Schema({
    'current_password': {
        'type': 'string',
        'required': True,
        'min_length': 1,
        'max_length': MAX_PASSWORD_LENGTH
    },
    'new_password': {
        'type': 'string',
        'required': True,
        'min_length': MIN_PASSWORD_LENGTH,
        'max_length': MAX_PASSWORD_LENGTH
    },
    'confirm_password': {
        'type': 'string',
        'required': True,
        'min_length': MIN_PASSWORD_LENGTH,
        'max_length': MAX_PASSWORD_LENGTH
    }
})

# Leave application schema
LEAVE_APPLICATION_SCHEMA = Schema({
    'leave_type': {
        'type': 'string',
        'required': True,
        'allowed_values': ['Medical', 'Personal', 'Family', 'Academic', 'Other']
    },
    'start_date': {
        'type': 'date',
        'required': True
    },
    'end_date': {
        'type': 'date',
        'required': True
    },
    'reason': {
        'type': 'string',
        'required': True,
        'min_length': 10,
        'max_length': MAX_TEXT_LENGTH
    }
}, strict=False)

# Attendance submission schema
ATTENDANCE_SUBMIT_SCHEMA = Schema({
    'schedule_id': {
        'type': 'integer',
        'required': True,
        'min_value': 1
    },
    'conducted_date': {
        'type': 'date',
        'required': True
    },
    'students': {
        'type': 'list',
        'required': True,
        'min_items': 1,
        'max_items': 500
    }
}, strict=False)  # Allow topic_id, topic_ids, etc.

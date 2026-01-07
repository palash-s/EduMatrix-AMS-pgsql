from __future__ import annotations

import os
import logging
import pandas as pd
import uuid
import secrets
import hashlib
import json
from functools import wraps
from datetime import timedelta, timezone
from datetime import datetime, date
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy import func
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

try:
    import firebase_admin
    from firebase_admin import credentials as firebase_credentials
    from firebase_admin import messaging as firebase_messaging
except Exception:
    firebase_admin = None
    firebase_credentials = None
    firebase_messaging = None

# 1. DATABASE IMPORTS
from sql_connection import (
    FeedbackQuestion, LessonLog, TeachingPlan, db, UserMaster, Department, Subject, ClassSection,
    School, Program, Specialization,
    StaffProfile, ParentProfile, StudentProfile, WeeklySchedule, TimetableVersion,
    EventMaster, EventParticipation, SubjectAllocation, StudentElective,
    ExtraSession,
    SessionLog, AttendanceTransaction, LeaveApplication, 
    LeaveWorkflowLog, DetentionRecord, SystemLog, MentorBatch, ElectiveOffering, 
    RoomMaster, MentorLog, MentorMeeting, MeetingAttendance, MeetingIssue, Notification, get_db_uri,CAMarks, TermGrantRecord,
    FeedbackCycle, FeedbackResponse, StudentFeedbackStatus, SystemConfig, ArchivedAllocation, ArchivedSchedule

    , SemesterCourseStructure, ElectiveWindow
    , RefreshToken, PushDevice, LoadAdjustment
)


def _infer_spec_code_from_section_name(section_name: str) -> str:
    """Infer a specialization code from a section/division string.

    Backward compatible:
    - If section_name is already a code like 'DA' -> returns 'DA'
    - If it's a division like 'DA1' -> returns 'DA'
    - If it doesn't match -> returns stripped input
    """
    raw = (section_name or '').strip()
    if not raw:
        return ''
    # Strip trailing digits (DA1 -> DA)
    i = len(raw)
    while i > 0 and raw[i - 1].isdigit():
        i -= 1
    base = raw[:i] if i > 0 else raw

    return base


def _resolve_class_section_for_csv(class_level: str, section_value: str) -> ClassSection | None:
    """Resolve a ClassSection for uploads.

    New convention (preferred):
      - CSV Section / Section Name == specialization code (e.g., DA, CORE, SMAD)
      - ClassSection.name stores that code, one row per class_level+code

    Backward-compatible fallback:
      - If older data uses division-like names (DA1/DA2), we only auto-resolve
        when there is exactly ONE matching section for the inferred spec.
        Otherwise we return None to avoid guessing.
    """
    cl = str(class_level or '').strip()
    sv = str(section_value or '').strip()
    if not cl or not sv:
        return None

    # 1) Direct match (new convention)
    direct = ClassSection.query.filter_by(class_level=cl, name=sv).first()
    if direct:
        return direct

    # 2) Legacy-safe fallback: infer spec code from division (DA1 -> DA)
    spec_code = _infer_spec_code_from_section_name(sv)
    if spec_code and spec_code != sv:
        by_code_name = ClassSection.query.filter_by(class_level=cl, name=spec_code).first()
        if by_code_name:
            return by_code_name

    # 3) If the section rows are linked to Specialization, resolve by spec code.
    if spec_code:
        spec = Specialization.query.filter_by(code=spec_code).first()
        if spec:
            matches = ClassSection.query.filter_by(class_level=cl, spec_id=spec.id).all()
            if len(matches) == 1:
                return matches[0]

    return None


def _normalize_header(s: str) -> str:
    return ''.join((s or '').strip().casefold().split())


def _dept_code_from_name(name: str) -> str:
    """Generate a short department code used for admin usernames.

    Examples:
      - Department of Information Technology -> IT
      - Computer Science & Engineering -> CSE
    """
    n = (name or '').strip().casefold()
    if not n:
        return 'DEPT'
    if 'information technology' in n:
        return 'IT'
    if 'computer science' in n:
        return 'CSE'

    import re
    words = [w for w in re.split(r"[^a-z0-9]+", n) if w]
    stop = {'department', 'of', 'and', 'the', 'engineering', 'technology'}
    letters = [w[0] for w in words if w not in stop and w[0].isalpha()]
    code = ''.join(letters[:4]).upper()
    return code or 'DEPT'


def _canonical_department_name(name: str) -> str:
    """Normalize department names to avoid duplicates from small variants.

    Examples:
      - "Department of Information Technology" -> "Information Technology"
      - extra spaces/case differences are normalized
    """
    import re
    raw = (name or '').strip()
    if not raw:
        return ''
    s = re.sub(r"\s+", " ", raw).strip()
    lower = s.casefold()
    prefixes = [
        'department of ',
        'dept of ',
        'dept. of ',
        'department ',
    ]
    for p in prefixes:
        if lower.startswith(p):
            s = s[len(p):].strip()
            break
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _spec_code_from_name(spec_name: str) -> str:
    """Generate a short specialization code from the name (fallback when CSV has no code)."""
    import re
    s = (spec_name or '').strip()
    if not s:
        return ''
    words = [w for w in re.split(r"[^A-Za-z0-9]+", s) if w]
    stop = {'and', 'of', 'the', 'in', 'for', 'with'}
    meaningful = [w for w in words if w.casefold() not in stop and w[0].isalnum()]
    # For single-word names (like "Core"), use the full word uppercased (up to 6 chars)
    if len(meaningful) == 1:
        return meaningful[0].upper()[:6]
    letters = [w[0].upper() for w in meaningful]
    code = ''.join(letters[:6])
    return code or (re.sub(r"[^A-Za-z0-9]", "", s).upper()[:6])


def _find_department_flexible(name_or_abbrev: str, scope_dept_ids=None):
    """
    Find a department by exact name, abbreviation, or partial match.
    Common abbreviations: IT -> Information Technology, CSE -> Computer Science & Engineering
    If scope_dept_ids is provided, only search within those departments.
    Returns the Department object or None.
    """
    s = (name_or_abbrev or '').strip()
    if not s:
        return None
    
    # Build base query
    base_q = Department.query
    if scope_dept_ids is not None:
        base_q = base_q.filter(Department.dept_id.in_(scope_dept_ids))
    
    # 1. Exact match
    dept = base_q.filter(Department.name == s).first()
    if dept:
        return dept
    
    # 2. Case-insensitive exact match
    dept = base_q.filter(func.lower(Department.name) == s.lower()).first()
    if dept:
        return dept
    
    # 3. Common abbreviation mapping
    abbrev_map = {
        'IT': ['Information Technology'],
        'CSE': ['Computer Science', 'Computer Science & Engineering', 'Computer Science and Engineering'],
        'ECE': ['Electronics', 'Electronics & Communication', 'Electronics and Communication'],
        'ME': ['Mechanical', 'Mechanical Engineering'],
        'CE': ['Civil', 'Civil Engineering'],
        'EE': ['Electrical', 'Electrical Engineering'],
    }
    if s.upper() in abbrev_map:
        for keyword in abbrev_map[s.upper()]:
            dept = base_q.filter(Department.name.ilike(f'%{keyword}%')).first()
            if dept:
                return dept
    
    # 4. Partial/substring match (case-insensitive)
    dept = base_q.filter(Department.name.ilike(f'%{s}%')).first()
    if dept:
        return dept
    
    return None


app = Flask(__name__)

# ==========================================
# SECURITY CONFIGURATION
# ==========================================
# CRITICAL: In production, set SECRET_KEY env var to a strong random value (min 32 chars)
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    logging.warning("⚠️  SECRET_KEY not set! Using insecure default. Set SECRET_KEY env var in production.")
    _secret_key = 'dev-secret-key-change-me'
app.config['SECRET_KEY'] = _secret_key

# Session security settings
# Set SESSION_COOKIE_SECURE via env var - only enable when HTTPS is configured
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JS access to session cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # Session timeout

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = get_db_uri(app) 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Mobile token lifetimes (seconds)
app.config['MOBILE_ACCESS_TOKEN_TTL_SECONDS'] = int(os.environ.get('MOBILE_ACCESS_TOKEN_TTL_SECONDS', '1800'))  # 30 min
app.config['MOBILE_REFRESH_TOKEN_TTL_DAYS'] = int(os.environ.get('MOBILE_REFRESH_TOKEN_TTL_DAYS', '30'))

# Session configuration for web authentication
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # Session expires after 8 hours

# WTF CSRF settings
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour token validity
app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # We'll selectively protect routes

db.init_app(app)
migrate = Migrate(app, db)


@app.teardown_appcontext
def shutdown_session(exception=None):
    """Clean up database session after each request to prevent stale transactions."""
    if exception:
        db.session.rollback()
    db.session.remove()


# ==========================================
# FLASK-LOGIN SETUP
# ==========================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'home'  # Redirect to login page (the '/' route)
login_manager.login_message = 'Please log in to access this page.'
login_manager.session_protection = 'strong'  # Regenerate session on IP/UA change


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login user loader callback."""
    return db.session.get(UserMaster, user_id)


@login_manager.unauthorized_handler
def unauthorized_api():
    """Return JSON 401 for API requests, redirect for page requests."""
    if request.path.startswith('/api/'):
        return jsonify({"error": "Authentication required"}), 401
    return redirect(url_for('home'))


# Make UserMaster compatible with Flask-Login
UserMaster.is_authenticated = property(lambda self: True)
UserMaster.is_anonymous = property(lambda self: False)
UserMaster.get_id = lambda self: str(self.user_id)


# ==========================================
# CSRF PROTECTION
# ==========================================
csrf = CSRFProtect(app)

# Exempt API endpoints that use token auth (mobile) or handle CSRF differently
CSRF_EXEMPT_ENDPOINTS = [
    'login',  # Web login endpoint
    'api_v1_auth_login',
    'api_v1_auth_refresh',
    'api_v1_me',
    'api_v1_student_dashboard',
    'api_v1_parent_dashboard',
    'api_v1_notifications',
    'api_v1_notification_read',
    'api_v1_test_push',
    'api_v1_devices_register',
]

@app.before_request
def try_bearer_auth_for_api():
    """For API requests with Bearer token, authenticate the user via Flask-Login.
    This allows mobile apps to use @login_required endpoints."""
    if request.path.startswith('/api/'):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.lower().startswith('bearer '):
            token = auth_header.split(' ', 1)[1].strip()
            if token:
                try:
                    payload = _mobile_access_serializer().loads(
                        token,
                        max_age=app.config['MOBILE_ACCESS_TOKEN_TTL_SECONDS'],
                    )
                    uid = payload.get('uid')
                    if uid:
                        user = UserMaster.query.get(uid)
                        if user and user.is_active:
                            login_user(user, remember=False)
                except Exception:
                    pass  # Token invalid, will fail at @login_required


@app.before_request
def csrf_protect_selectively():
    """Apply CSRF protection to non-exempt POST/PUT/DELETE requests."""
    if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
        if request.endpoint in CSRF_EXEMPT_ENDPOINTS:
            return  # Skip CSRF for mobile API
        # For API routes using Bearer token, skip CSRF
        auth_header = request.headers.get('Authorization', '')
        if auth_header.lower().startswith('bearer '):
            return
        # Skip CSRF for authenticated API requests (session-protected)
        # This is safe because session cookies have SameSite=Lax protection
        if request.path.startswith('/api/') and current_user.is_authenticated:
            return
        if auth_header.lower().startswith('bearer '):
            return


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF validation failures."""
    app.logger.warning(f"CSRF validation failed: {e.description}")
    return jsonify({"error": "Session expired. Please refresh and try again."}), 403


# ==========================================
# RATE LIMITING
# ==========================================
# Use Redis in production for distributed rate limiting across workers
_rate_limit_storage = os.environ.get('RATE_LIMIT_STORAGE_URI', 'memory://')
if os.environ.get('FLASK_ENV') == 'production' and _rate_limit_storage == 'memory://':
    logging.warning("⚠️  RATE_LIMIT_STORAGE_URI not set in production. Using in-memory storage (not shared across workers).")

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per minute"],  # Global default
    storage_uri=_rate_limit_storage,  # Set RATE_LIMIT_STORAGE_URI=redis://redis:6379 in prod
)


# ==========================================
# FIRST-LOGIN ONBOARDING GUARD (SUPERADMIN)
# ==========================================
@app.before_request
def _enforce_superadmin_onboarding():
    """Force SuperAdmin to complete hierarchy setup on first login.

    This is server-side (not just a login redirect) so the user can't be
    bounced to /admin/dashboard by frontend logic while onboarding is pending.

    - If user_master.onboarding_completed exists: require it to be True
    - Else (older DB): require at least one School row
    """
    try:
        if not current_user.is_authenticated:
            return None

        user_type_cf = (getattr(current_user, 'user_type', '') or '').strip().casefold()
        if user_type_cf != 'superadmin':
            return None

        path = (request.path or '')

        # Always allow these endpoints/resources
        if (
            path.startswith('/static/')
            or path.startswith('/api/login')
            or path.startswith('/api/logout')
            or path.startswith('/api/me')
            or path.startswith('/api/change-password')
            or path.startswith('/api/setup/')
            or path.startswith('/setup_hierarchy')
            or path.startswith('/superadmin/setup_hierarchy')
            or path.startswith('/superadmin/dashboard')
            or path.startswith('/change-password')
        ):
            return None

        # Only force redirects for page loads (not for API calls)
        if path.startswith('/api/'):
            return None

        onboarding_done = False
        try:
            from sqlalchemy import inspect as _sa_inspect
            cols = {c['name'] for c in _sa_inspect(db.engine).get_columns('user_master')}
            if 'onboarding_completed' in cols:
                # Avoid attribute access when column missing.
                onboarding_done = bool(getattr(current_user, 'onboarding_completed', False))
            else:
                onboarding_done = (School.query.count() > 0)
        except Exception:
            onboarding_done = False

        if not onboarding_done:
            return redirect('/superadmin/setup_hierarchy')
        return None
    except Exception:
        # Never block requests due to guard errors; fail open.
        return None


# ==========================================
# AUTH DECORATORS
# ==========================================
def require_roles(*allowed_roles):
    """Decorator to require specific user roles for an endpoint.
    
    Usage:
        @app.route('/admin/...')
        @require_roles('Admin')
        def admin_only_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Authentication required"}), 401

            # Normalize roles. We store user_type as a string; treat SuperAdmin as a superset of Admin.
            user_role_cf = (current_user.user_type or '').strip().casefold()
            allowed_cf = {(r or '').strip().casefold() for r in allowed_roles}

            is_allowed = user_role_cf in allowed_cf
            if not is_allowed and user_role_cf == 'superadmin' and 'admin' in allowed_cf:
                is_allowed = True

            if not is_allowed:
                app.logger.warning(
                    f"Access denied: {current_user.user_id} ({current_user.user_type}) tried to access {request.endpoint}"
                )
                return jsonify({"error": "Access denied"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_auth(f):
    """Decorator requiring any authenticated user (web session)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function


def _is_super_admin() -> bool:
    return (getattr(current_user, 'user_type', '') or '').strip().casefold() == 'superadmin'


def _require_superadmin_json():
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    if not _is_super_admin():
        return jsonify({"error": "SuperAdmin only"}), 403
    return None


def _get_admin_scope_dept_ids():
    """Return department IDs the current admin is allowed to manage.

    - SuperAdmin: returns None (means global access)
    - Department Admin: returns [dept_id]
    - Admin without scope: returns [] (deny department-scoped operations)
    """
    try:
        if not current_user.is_authenticated:
            return []
        role_cf = (current_user.user_type or '').strip().casefold()
        if role_cf == 'superadmin':
            return None
        if role_cf != 'admin':
            return []

        staff = StaffProfile.query.filter_by(staff_id=current_user.user_id).first()
        dept_id = getattr(staff, 'admin_access_dept_id', None) if staff else None
        if dept_id:
            return [dept_id]

        dept = Department.query.filter_by(dept_admin_id=current_user.user_id).first()
        if dept:
            return [dept.dept_id]
        return []
    except Exception:
        return []


def _get_user_scope_dept_ids():
    """Return department IDs the current user is allowed to access.

    Semantics:
      - SuperAdmin: None (global)
      - Admin: department scope (via StaffProfile.admin_access_dept_id or Department.dept_admin_id)
      - Staff: primary_department_id and/or HOD-mapped department
      - Others: [] (no department-based enumeration privileges)
    """
    try:
        if not current_user.is_authenticated:
            return []

        role_cf = (getattr(current_user, 'user_type', '') or '').strip().casefold()
        if role_cf == 'superadmin':
            return None

        if role_cf == 'admin':
            return _get_admin_scope_dept_ids()

        if role_cf == 'staff':
            staff = StaffProfile.query.filter_by(staff_id=current_user.user_id).first()
            dept_ids = set()
            if staff and getattr(staff, 'primary_department_id', None):
                dept_ids.add(int(staff.primary_department_id))

            hod_dept = Department.query.filter_by(hod_staff_id=current_user.user_id).first()
            if hod_dept:
                dept_ids.add(int(hod_dept.dept_id))

            return sorted(dept_ids)

        return []
    except Exception:
        return []


def _get_section_dept_id(section_id):
    if not section_id:
        return None
    row = (db.session.query(Specialization.dept_id)
           .join(ClassSection, ClassSection.spec_id == Specialization.id)
           .filter(ClassSection.section_id == section_id)
           .first())
    return row[0] if row else None


def _ensure_section_in_scope(section_id):
    """Return a JSON error response if section is out-of-scope; else None."""
    scope_dept_ids = _get_user_scope_dept_ids()
    if scope_dept_ids is None:
        return None
    if not scope_dept_ids:
        return jsonify({"error": "Department scope not configured"}), 403
    dept_id = _get_section_dept_id(int(section_id) if section_id is not None else None)
    if not dept_id or int(dept_id) not in scope_dept_ids:
        return jsonify({"error": "Out of scope"}), 403
    return None


def _ensure_student_in_scope(student_id):
    """Return a JSON error response if student is out-of-scope; else None."""
    if not student_id:
        return jsonify({"error": "student_id is required"}), 400

    scope_dept_ids = _get_user_scope_dept_ids()
    if scope_dept_ids is None:
        return None
    if not scope_dept_ids:
        return jsonify({"error": "Department scope not configured"}), 403

    student = db.session.get(StudentProfile, student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    if not getattr(student, 'current_section_id', None):
        return jsonify({"error": "Student section not assigned"}), 400

    dept_id = _get_section_dept_id(int(student.current_section_id))
    if not dept_id or int(dept_id) not in scope_dept_ids:
        return jsonify({"error": "Out of scope"}), 403
    return None

PRESENT_STATUSES = ['Present', 'OnDuty', 'OD', 'ML', 'CL']
# FIXED_DEPT_NAME removed - departments are now dynamic via hierarchy setup


# ==========================================
# SETUP: HIERARCHY (SUPER USER / ADMIN)
# ==========================================
@app.route('/setup_hierarchy')
def legacy_setup_hierarchy_redirect():
    # Backwards-compatible path
    return redirect('/superadmin/setup_hierarchy')


@app.route('/superadmin/setup_hierarchy')
@login_required
@require_roles('Admin')
def render_setup_hierarchy():
    if not _is_super_admin():
        return "Access denied", 403
    return render_template('setup_hierarchy.html')


@app.route('/superadmin/dashboard')
@login_required
@require_roles('Admin')
def render_superadmin_dashboard():
    if not _is_super_admin():
        return "Access denied", 403
    return render_template('super_admin_dashboard.html')


@app.route('/api/superadmin/kpis', methods=['GET'])
@login_required
@require_roles('Admin')
def api_superadmin_kpis():
    deny = _require_superadmin_json()
    if deny:
        return deny
    try:
        dept_admins = Department.query.filter(Department.dept_admin_id != None).count()
        return jsonify({
            "schools": School.query.count(),
            "departments": Department.query.count(),
            "programs": Program.query.count(),
            "specializations": Specialization.query.count(),
            "department_admins": dept_admins,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/superadmin/dept_admins', methods=['GET'])
@login_required
@require_roles('Admin')
def api_superadmin_list_dept_admins():
    """List all department admins with their assigned departments."""
    deny = _require_superadmin_json()
    if deny:
        return deny
    try:
        # Get all departments with assigned admins
        depts_with_admins = (
            db.session.query(Department, StaffProfile, UserMaster)
            .join(StaffProfile, Department.dept_admin_id == StaffProfile.staff_id)
            .join(UserMaster, StaffProfile.staff_id == UserMaster.user_id)
            .order_by(Department.name)
            .all()
        )
        
        result = []
        for dept, staff, user in depts_with_admins:
            result.append({
                "department": dept.name,
                "admin_name": staff.full_name,
                "email": staff.email_contact or user.username,
                "employee_code": staff.employee_code,
                "is_active": user.is_active,
            })
        
        # Also get departments without admins
        depts_without_admins = Department.query.filter(
            (Department.dept_admin_id == None) | (Department.dept_admin_id == '')
        ).order_by(Department.name).all()
        
        for dept in depts_without_admins:
            result.append({
                "department": dept.name,
                "admin_name": None,
                "email": None,
                "employee_code": None,
                "is_active": None,
            })
        
        return jsonify({"department_admins": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/superadmin/dept_admin/reset_password', methods=['POST'])
@login_required
@require_roles('Admin')
def api_superadmin_reset_dept_admin_password():
    """Reset password for a department admin and return the new password."""
    deny = _require_superadmin_json()
    if deny:
        return deny
    try:
        data = request.json or {}
        dept_name = (data.get('department') or '').strip()
        
        if not dept_name:
            return jsonify({"error": "Department name is required"}), 400
        
        dept = Department.query.filter_by(name=dept_name).first()
        if not dept:
            return jsonify({"error": f"Department '{dept_name}' not found"}), 404
        
        if not dept.dept_admin_id:
            return jsonify({"error": f"No admin assigned to department '{dept_name}'"}), 400
        
        user = UserMaster.query.get(dept.dept_admin_id)
        if not user:
            return jsonify({"error": "Admin user not found"}), 404
        
        # Generate new password - alphanumeric only for easy typing (no special chars)
        import string
        alphabet = string.ascii_letters + string.digits  # a-zA-Z0-9
        new_password = ''.join(secrets.choice(alphabet) for _ in range(10))
        user.password_hash = generate_password_hash(new_password)
        user.must_change_password = True
        
        db.session.commit()
        
        # Log for debugging (don't log the actual password!)
        app.logger.info(f"Password reset for {user.username} (dept: {dept_name})")
        
        return jsonify({
            "message": "Password reset successfully",
            "department": dept_name,
            "email": user.username,
            "new_password": new_password,
            "note": "User must change password on first login"
        })
    except Exception as e:
        db.session.rollback()
        app.logger.exception(f"Password reset failed for dept {dept_name}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/setup/hierarchy', methods=['POST'])
@login_required
@require_roles('Admin')
def setup_hierarchy():
    """Create the School -> Program -> Department -> Specialization chain.

    This is a one-time setup overlay; CSV structures remain unchanged.
    """
    try:
        if not _is_super_admin():
            return jsonify({"error": "Only SuperAdmin can run hierarchy setup"}), 403

        data = request.json or {}
        school_name = (data.get('school') or '').strip()
        program_name = (data.get('program') or '').strip()
        dept_name = (data.get('department') or '').strip()
        spec_name = (data.get('spec_name') or '').strip()
        spec_code = (data.get('spec_code') or '').strip()
        # Dept admin creation is handled by /api/superadmin/dept_admin

        if not school_name or not program_name or not dept_name or not spec_name or not spec_code:
            return jsonify({"error": "Missing required fields: school, program, department, spec_name, spec_code"}), 400

        school = School.query.filter_by(name=school_name).first()
        if not school:
            school = School(name=school_name)
            db.session.add(school)
            db.session.flush()

        dept = Department.query.filter_by(name=dept_name).first()
        if not dept:
            dept = Department(name=dept_name, school_id=school.id)
            db.session.add(dept)
            db.session.flush()
        else:
            if getattr(dept, 'school_id', None) in (None, 0):
                dept.school_id = school.id


        # Program (legacy schema requires dept_id + level)
        program = Program.query.filter_by(name=program_name, dept_id=dept.dept_id).first()
        if not program:
            program = Program(name=program_name, dept_id=dept.dept_id, level='Default', school_id=school.id)
            db.session.add(program)
            db.session.flush()
        else:
            if getattr(program, 'school_id', None) in (None, 0):
                program.school_id = school.id

        # Overlay link: Department -> Program
        if getattr(dept, 'program_id', None) in (None, 0):
            dept.program_id = program.id

        # Specialization codes can repeat across departments/programs (e.g., Core -> "C").
        # Always scope lookups by department + program.
        spec = Specialization.query.filter_by(code=spec_code, dept_id=dept.dept_id, program_id=program.id).first()
        if not spec:
            spec = Specialization(name=spec_name, code=spec_code, dept_id=dept.dept_id, program_id=program.id)
            db.session.add(spec)
        else:
            # Keep code stable; allow rename / re-link
            spec.name = spec_name
            spec.dept_id = dept.dept_id
            spec.program_id = program.id

        # Mark onboarding complete for the SuperAdmin once the first setup is saved.
        # Guarded so deployments where the migration wasn't applied yet won't crash.
        try:
            from sqlalchemy import inspect as _sa_inspect
            cols = {c['name'] for c in _sa_inspect(db.engine).get_columns('user_master')}
            if 'onboarding_completed' in cols:
                su = db.session.get(UserMaster, current_user.user_id)
                if su is not None:
                    su.onboarding_completed = True
        except Exception:
            pass

        db.session.commit()
        return jsonify({"message": "Hierarchy Created"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/setup/tree', methods=['GET'])
@login_required
@require_roles('Admin')
def get_hierarchy_tree():
    if not _is_super_admin():
        return jsonify({"error": "Only SuperAdmin can view hierarchy tree"}), 403
    schools = School.query.order_by(School.name).all()
    tree = []
    for s in schools:
        s_data = {"name": s.name, "programs": []}
        programs = Program.query.filter_by(school_id=s.id).order_by(Program.name).all()

        for p in programs:
            p_data = {"name": p.name, "departments": []}

            # Derive departments per program based on Specialization rows.
            dept_ids = [r[0] for r in (db.session.query(Specialization.dept_id)
                                      .filter(Specialization.program_id == p.id)
                                      .filter(Specialization.dept_id != None)
                                      .distinct()
                                      .all())]
            depts = []
            if dept_ids:
                depts = Department.query.filter(Department.dept_id.in_(dept_ids)).order_by(Department.name).all()

            for d in depts:
                d_data = {"name": d.name, "specializations": []}
                specs = (Specialization.query
                         .filter(Specialization.program_id == p.id, Specialization.dept_id == d.dept_id)
                         .order_by(Specialization.code)
                         .all())
                for sp in specs:
                    d_data["specializations"].append(f"{sp.name} ({sp.code})")
                p_data["departments"].append(d_data)

            s_data["programs"].append(p_data)

        tree.append(s_data)
    return jsonify(tree)


@app.route('/api/admin/import_templates/<key>', methods=['GET'])
def api_admin_download_import_template(key: str):
    """Download CSV templates for System Data Import cards.

    Uses a strict allow-list to avoid path traversal.
    """
    templates = {
        # Existing sample files
        'master_class': 'master_class_template.csv',
        'staff': 'staff_master_template.csv',
        'students': 'student_master_template.csv',
        'weekly_schedule': 'weekly_schedule.csv',
        'rooms': 'rooms_template.csv',
        'semester_course_structure': 'semester_course_structure_template.csv',
        'subject_allocation': 'subject_allocation_template.csv',
    }

    filename = templates.get((key or '').strip())
    if not filename:
        return jsonify({"error": "Template not found"}), 404

    data_dir = os.path.join(app.root_path, 'data')
    return send_from_directory(data_dir, filename, as_attachment=True)


# ==========================================
# HELPER: TIMEZONE CONVERSION
# ==========================================
# India Standard Time is UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

def _to_ist(dt):
    """Convert a naive UTC datetime to IST string for display."""
    if dt is None:
        return None
    # If naive datetime, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).isoformat()


# ==========================================
# HELPER: NOTIFICATION SYSTEM
# ==========================================
_FIREBASE_APP = None


def _firebase_get_app():
    """Initialize Firebase Admin app lazily.

    Supports either:
    - FIREBASE_CREDENTIALS_FILE (path to service account json)
    - FIREBASE_CREDENTIALS_JSON (service account json string)
    - GOOGLE_APPLICATION_CREDENTIALS (path)
    - Auto-discovery in secrets/ folder (for local development)

    Returns None when not configured; callers must treat push as best-effort.
    """
    global _FIREBASE_APP
    if _FIREBASE_APP is not None:
        return _FIREBASE_APP

    if firebase_admin is None:
        _FIREBASE_APP = None
        return None

    creds_file = os.environ.get('FIREBASE_CREDENTIALS_FILE') or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')

    # Auto-discover Firebase credentials in secrets/ folder for local development
    if not creds_file and not creds_json:
        secrets_dir = os.path.join(os.path.dirname(__file__), 'secrets')
        if os.path.isdir(secrets_dir):
            for fname in os.listdir(secrets_dir):
                if 'firebase' in fname.lower() and fname.endswith('.json'):
                    creds_file = os.path.join(secrets_dir, fname)
                    print(f"FCM: Auto-discovered credentials at {creds_file}")
                    break

    if not creds_file and not creds_json:
        _FIREBASE_APP = None
        return None

    try:
        if creds_json:
            info = json.loads(creds_json)
            cred = firebase_credentials.Certificate(info)
            print(f"FCM: Loaded credentials from JSON env var, project_id={info.get('project_id')}")
        else:
            print(f"FCM: Loading credentials from file: {creds_file}")
            cred = firebase_credentials.Certificate(creds_file)

        try:
            _FIREBASE_APP = firebase_admin.initialize_app(cred)
            print(f"FCM: Firebase app initialized, project_id={_FIREBASE_APP.project_id}")
        except ValueError:
            _FIREBASE_APP = firebase_admin.get_app()
            print(f"FCM: Firebase app already existed, project_id={_FIREBASE_APP.project_id}")
        return _FIREBASE_APP
    except Exception as e:
        import traceback
        print(f"FCM init failed: {e}")
        traceback.print_exc()
        _FIREBASE_APP = None
        return None


_fcm_last_error = None  # Store last FCM error for debugging

def _fcm_send_to_tokens(tokens, title: str, body: str, data: dict):
    """Send a push notification to a list of FCM tokens (best-effort)."""
    global _fcm_last_error
    _fcm_last_error = None

    if not tokens:
        _fcm_last_error = "no tokens provided"
        return 0

    fb_app = _firebase_get_app()
    if fb_app is None:
        _fcm_last_error = "Firebase not initialized - check credentials"
        return 0

    # Log project info for debugging
    try:
        project_id = fb_app.project_id
        print(f"FCM: Using project_id={project_id}, sending to {len(tokens)} token(s)")
    except Exception as e:
        print(f"FCM: Could not get project_id: {e}")

    try:
        # FCM requires all data values to be strings.
        safe_data = {}
        for k, v in (data or {}).items():
            if v is None:
                continue
            safe_data[str(k)] = str(v)

        # Include title/body in data so our app always handles display (even in background)
        safe_data['title'] = title or ''
        safe_data['body'] = (body or '')[:240]
        safe_data['message'] = (body or '')[:240]

        # Android config for high-priority delivery and our custom channel
        android_config = firebase_messaging.AndroidConfig(
            priority='high',
            notification=firebase_messaging.AndroidNotification(
                channel_id='ams_alerts',
                priority='high',
                default_sound=True,
                default_vibrate_timings=True,
            )
        )

        msg = firebase_messaging.MulticastMessage(
            notification=firebase_messaging.Notification(title=title or '', body=(body or '')[:240]),
            data=safe_data,
            android=android_config,
            tokens=tokens,
        )

        if hasattr(firebase_messaging, 'send_multicast'):
            resp = firebase_messaging.send_multicast(msg)
        elif hasattr(firebase_messaging, 'send_each_for_multicast'):
            # firebase-admin>=6 uses send_each_for_multicast
            resp = firebase_messaging.send_each_for_multicast(msg)
        else:
            # Very old firebase-admin fallback: send one-by-one.
            success_count = 0
            failure_count = 0
            errors = []
            for t in tokens:
                try:
                    m = firebase_messaging.Message(
                        notification=firebase_messaging.Notification(title=title or '', body=(body or '')[:240]),
                        data=safe_data,
                        android=android_config,
                        token=t,
                    )
                    firebase_messaging.send(m)
                    success_count += 1
                except Exception as e:
                    failure_count += 1
                    if len(errors) < 5:
                        errors.append(str(e))
            print(f"FCM send result (fallback): success={success_count} failure={failure_count} sample_errors={errors}")
            return success_count
        success_count = int(getattr(resp, 'success_count', 0) or 0)
        failure_count = int(getattr(resp, 'failure_count', 0) or 0)

        # Log failures because FCM often returns per-token errors without raising.
        try:
            if failure_count:
                errors = []
                for r in (getattr(resp, 'responses', None) or [])[:5]:
                    exc = getattr(r, 'exception', None)
                    if exc:
                        errors.append(str(exc))
                _fcm_last_error = "; ".join(errors) if errors else f"{failure_count} failures (no details)"
                print(f"FCM send result: success={success_count} failure={failure_count} sample_errors={errors}")
            else:
                print(f"FCM send result: success={success_count} failure={failure_count}")
        except Exception:
            pass

        return success_count
    except Exception as e:
        _fcm_last_error = str(e)
        print(f"FCM send failed: {e}")
        return 0


def _fcm_send_to_user(user_id: str, title: str, body: str, data: dict):
    """Send push to all active devices for a given user_id."""
    if not user_id:
        return 0

    try:
        devices = (PushDevice.query
                   .filter_by(user_id=user_id, is_active=True)
                   .all())
        tokens = [d.fcm_token for d in devices if d.fcm_token]
        if not tokens:
            return 0

        return _fcm_send_to_tokens(tokens, title, body, data)
    except Exception as e:
        print(f"FCM lookup failed for user {user_id}: {e}")
        return 0


def _fcm_send_to_user_debug(user_id: str, title: str, body: str, data: dict) -> dict:
    """Debug helper returning counts: {tokens, success, error}."""
    if not user_id:
        return {"tokens": 0, "success": 0, "error": "no user_id"}

    try:
        # Check if Firebase is initialized
        firebase_app = _firebase_get_app()
        if firebase_app is None:
            return {"tokens": 0, "success": 0, "error": "Firebase not initialized - check credentials"}

        devices = (PushDevice.query
                   .filter_by(user_id=user_id, is_active=True)
                   .all())
        tokens = [d.fcm_token for d in devices if d.fcm_token]
        if not tokens:
            return {"tokens": 0, "success": 0, "error": "no tokens registered"}

        success = _fcm_send_to_tokens(tokens, title, body, data)
        result = {"tokens": len(tokens), "success": int(success or 0)}
        if success == 0:
            result["error"] = _fcm_last_error or "FCM send returned 0 success - unknown error"
        return result
    except Exception as e:
        print(f"FCM debug lookup/send failed for user {user_id}: {e}")
        return {"tokens": 0, "success": 0, "error": str(e)}


def send_notification(user_id, title, message, type='info', link=None):
    try:
        if not user_id:
            return False

        # If the caller already has pending changes, we should NOT commit here
        # (so the notification participates in the caller's transaction).
        had_pending_work = bool(db.session.new) or bool(db.session.dirty) or bool(db.session.deleted)

        notif = Notification(user_id=user_id, title=title, message=message, type=type, link=link)
        db.session.add(notif)

        # If this helper is called after the caller already committed (common pattern
        # in this codebase), there may be no pending work; in that case commit just
        # the notification so it isn't silently lost.
        if had_pending_work:
            db.session.flush()  # ensure ID is generated if needed
        else:
            db.session.commit()

        # Best-effort push (never break web flows).
        try:
            notif_id = getattr(notif, 'id', None)
            _fcm_send_to_user(
                user_id,
                title,
                message,
                {
                    "notification_id": notif_id,
                    "type": type,
                    "link": link or '',
                    "user_id": user_id,
                },
            )

            # Parent app should also get pushes for child notifications.
            student = StudentProfile.query.get(user_id)
            if student and getattr(student, 'parent_user_id', None):
                _fcm_send_to_user(
                    student.parent_user_id,
                    title,
                    message,
                    {
                        "notification_id": notif_id,
                        "type": type,
                        "link": link or '',
                        "child_id": student.student_id,
                        "user_id": student.parent_user_id,
                    },
                )
        except Exception as e:
            print(f"FCM push skipped/failed: {e}")

        return True
    except Exception as e:
        print(f"Notification Error: {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return False


# ==========================================
# MOBILE: AUTH HELPERS (NEW)
# ==========================================
def _require_role(*allowed_roles):
    """Check if request comes from an authenticated user with one of allowed_roles.
    
    Uses Flask session for web authentication. Validates that the user is logged in
    via session and has one of the allowed roles.
    Returns (user, error_response). If error_response is not None, return it immediately.
    """
    user_id = session.get('user_id')
    if not user_id:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    
    user = db.session.get(UserMaster, user_id)
    if not user or not user.is_active:
        # Clear invalid session
        session.clear()
        return None, (jsonify({"error": "Unauthorized"}), 401)
    
    if allowed_roles and user.user_type not in allowed_roles:
        return None, (jsonify({"error": "Forbidden"}), 403)
    
    return user, None


def _mobile_access_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='ams-mobile-access-v1')


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _issue_access_token(user: UserMaster) -> str:
    payload = {
        "uid": user.user_id,
        "typ": "access",
        "v": 1,
    }
    return _mobile_access_serializer().dumps(payload)


def _verify_access_token(raw: str) -> UserMaster | None:
    if not raw:
        return None

    try:
        payload = _mobile_access_serializer().loads(
            raw,
            max_age=app.config['MOBILE_ACCESS_TOKEN_TTL_SECONDS'],
        )
    except SignatureExpired:
        return None
    except BadSignature:
        return None
    except Exception:
        return None

    if not isinstance(payload, dict) or payload.get('typ') != 'access':
        return None

    uid = payload.get('uid')
    if not uid:
        return None

    user = db.session.get(UserMaster, uid)
    if not user or not user.is_active:
        return None

    return user


def _get_bearer_token() -> str | None:
    auth = request.headers.get('Authorization') or ''
    if not auth.lower().startswith('bearer '):
        return None
    return auth.split(' ', 1)[1].strip() or None


def _require_mobile_auth() -> UserMaster:
    token = _get_bearer_token()
    user = _verify_access_token(token)
    if not user:
        # 401 is important so mobile can trigger refresh flow.
        raise PermissionError('Unauthorized')
    return user


def _try_bearer_login():
    """If Bearer token is present, verify it and log the user in via Flask-Login.
    This allows mobile apps to use session-protected endpoints."""
    token = _get_bearer_token()
    if token:
        user = _verify_access_token(token)
        if user:
            login_user(user, remember=False)


def _find_user_for_login(username: str) -> UserMaster | None:
    if not username:
        return None

    # 1) Username (email/phone) - case insensitive
    user = UserMaster.query.filter(UserMaster.username.ilike(username)).first()

    # 2) Staff employee_code
    if not user:
        staff = StaffProfile.query.filter(StaffProfile.employee_code.ilike(username)).first()
        if staff:
            user = db.session.get(UserMaster, staff.staff_id)

    # 3) Student admission_number
    if not user:
        student = StudentProfile.query.filter(StudentProfile.admission_number.ilike(username)).first()
        if student:
            user = db.session.get(UserMaster, student.student_id)

    return user


def _issue_refresh_token(user: UserMaster, device_id: str | None) -> str:
    raw = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw)
    expires_at = datetime.utcnow() + timedelta(days=app.config['MOBILE_REFRESH_TOKEN_TTL_DAYS'])
    rt = RefreshToken(
        user_id=user.user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        device_id=(device_id or None),
        user_agent=(request.headers.get('User-Agent') or None),
    )
    db.session.add(rt)
    db.session.commit()
    return raw


def _get_parent_children(parent_user_id: str):
    children = StudentProfile.query.filter_by(parent_user_id=parent_user_id).all()
    out = []
    for s in children:
        section = ClassSection.query.get(s.current_section_id) if s.current_section_id else None
        out.append({
            "student_id": s.student_id,
            "name": s.full_name,
            "admission_number": s.admission_number,
            "academic_status": s.academic_status,
            "section_id": s.current_section_id,
            "class": f"{section.class_level}-{section.name}" if section else None,
        })
    return out


def _require_role(user: UserMaster, allowed: set[str]):
    role = (user.user_type or '').lower()
    if role not in allowed:
        raise PermissionError('Forbidden')
    return role


def _get_student_or_404(student_id: str) -> StudentProfile | None:
    if not student_id:
        return None
    return StudentProfile.query.filter_by(student_id=student_id).first()


def _get_student_batch_name(student: StudentProfile) -> str | None:
    if student and student.mentor_batch_id:
        batch = db.session.get(MentorBatch, student.mentor_batch_id)
        if batch:
            return batch.batch_name
    return None


def _student_subject_attendance_payload(student: StudentProfile):
    if not student.current_section_id:
        return {
            "profile": {
                "student_id": student.student_id,
                "name": student.full_name,
                "admission_number": student.admission_number,
                "class": "Unassigned",
            },
            "stats": {
                "percentage": 0,
                "total_lectures": 0,
                "attended": 0,
                "is_defaulter": False,
            },
            "subjects": [],
        }

    section = ClassSection.query.get(student.current_section_id)
    if not section:
        return {
            "profile": {
                "student_id": student.student_id,
                "name": student.full_name,
                "admission_number": student.admission_number,
                "class": "Unknown",
            },
            "stats": {
                "percentage": 0,
                "total_lectures": 0,
                "attended": 0,
                "is_defaulter": False,
            },
            "subjects": [],
        }

    my_batch_name = _get_student_batch_name(student)

    allocations = SubjectAllocation.query.filter_by(section_id=section.section_id).all()
    subject_teacher_map = {a.subject_id: a.teacher_id for a in allocations}

    subjects = []
    grand_total_conducted = 0
    grand_total_attended = 0

    for sub_id, teacher_id in subject_teacher_map.items():
        subject = db.session.get(Subject, sub_id)
        if not subject:
            continue

        if is_elective_type(subject.subject_type):
            try:
                is_approved = StudentElective.query.filter_by(
                    student_id=student.student_id,
                    subject_id=sub_id,
                    status='Approved',
                ).first()
                if not is_approved:
                    continue
            except Exception:
                pass

        sessions = (
            db.session.query(SessionLog, WeeklySchedule.target_batch)
            .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
            .filter(WeeklySchedule.subject_id == sub_id)
            .filter(WeeklySchedule.section_id == section.section_id)
            .filter(SessionLog.status == 'Conducted')
            .all()
        )

        applicable_ids = []
        for sess, target_batch in sessions:
            if not target_batch or target_batch == my_batch_name:
                applicable_ids.append(sess.session_id)

        conducted = len(applicable_ids)
        attended_sub = 0
        if conducted > 0:
            attended_sub = AttendanceTransaction.query.filter(
                AttendanceTransaction.session_id.in_(applicable_ids),
                AttendanceTransaction.student_id == student.student_id,
                AttendanceTransaction.status.in_(['Present', 'OnDuty', 'OD', 'ML', 'CL']),
            ).count()

        grand_total_conducted += conducted
        grand_total_attended += attended_sub
        sub_perc = round((attended_sub / conducted) * 100, 1) if conducted > 0 else 0

        teacher_name = "Unassigned"
        if teacher_id:
            t = db.session.get(StaffProfile, teacher_id)
            if t:
                teacher_name = t.full_name

        subjects.append({
            "subject_id": subject.subject_id,
            "subject": subject.name,
            "code": subject.code,
            "teacher": teacher_name,
            "conducted": conducted,
            "attended": attended_sub,
            "percentage": sub_perc,
        })

    overall_percentage = round((grand_total_attended / grand_total_conducted) * 100, 1) if grand_total_conducted > 0 else 0

    return {
        "profile": {
            "student_id": student.student_id,
            "name": student.full_name,
            "admission_number": student.admission_number,
            "class": f"{section.class_level}-{section.name}",
            "section_id": section.section_id,
        },
        "stats": {
            "percentage": overall_percentage,
            "total_lectures": grand_total_conducted,
            "attended": grand_total_attended,
            "is_defaulter": overall_percentage < 75,
        },
        "subjects": sorted(subjects, key=lambda x: (x.get('subject') or '')),
    }


def _create_leave_for_student(student_id: str, total_days: float, start: date, end: date, reason: str | None, leave_type: str | None):
    initial_status = 'Pending_HOD' if total_days > 15 else 'Pending_CT'

    new_leave = LeaveApplication(
        student_id=student_id,
        total_days=total_days,
        start_date=start,
        end_date=end,
        reason=reason,
        status=initial_status,
        leave_type=leave_type,
    )
    db.session.add(new_leave)
    db.session.flush()

    student = StudentProfile.query.get(student_id)
    section = ClassSection.query.get(student.current_section_id) if student else None

    if total_days > 15:
        if section and section.class_teacher_id:
            ct_profile = StaffProfile.query.get(section.class_teacher_id)
            if ct_profile and ct_profile.primary_department_id:
                dept = Department.query.get(ct_profile.primary_department_id)
                if dept and dept.hod_staff_id:
                    send_notification(
                        dept.hod_staff_id,
                        "Long Leave Request",
                        f"{student.full_name if student else 'Student'} applied for {total_days} days (Requires HOD Approval).",
                        "warning",
                        "/staff/hod_dashboard",
                    )
    else:
        if section and section.class_teacher_id:
            send_notification(
                section.class_teacher_id,
                "New Leave Request",
                f"{student.full_name if student else 'Student'} applied for {total_days} days leave.",
                "info",
                "/staff/class_teacher_dashboard",
            )

    db.session.commit()
    return {"status": initial_status, "leave_id": new_leave.leave_id}


def _get_student_leave_payload(student_id: str):
    active_leaves = LeaveApplication.query.filter(
        LeaveApplication.student_id == student_id,
        LeaveApplication.status.in_(['Approved', 'Pending_CT', 'Pending_HOD']),
    ).all()

    used_days = 0
    blocked_dates = []
    for leave in active_leaves:
        used_days += leave.total_days
        curr = leave.start_date
        while curr <= leave.end_date:
            blocked_dates.append(curr.strftime('%Y-%m-%d'))
            curr += timedelta(days=1)

    history = LeaveApplication.query.filter_by(student_id=student_id).order_by(LeaveApplication.start_date.desc()).all()
    history_list = []
    for leave in history:
        clean_status = leave.status.replace('Pending_CT', 'Pending (CT)').replace('Pending_HOD', 'Pending (HOD)')
        s_str = leave.start_date.strftime('%d %b')
        e_str = leave.end_date.strftime('%d %b %Y')
        date_display = f"{s_str} - {e_str}" if leave.start_date != leave.end_date else e_str
        history_list.append({
            "leave_id": leave.leave_id,
            "type": leave.leave_type or "General",
            "days": leave.total_days,
            "status": clean_status,
            "raw_status": leave.status,
            "start_date": leave.start_date.isoformat() if leave.start_date else None,
            "end_date": leave.end_date.isoformat() if leave.end_date else None,
            "date_display": date_display,
            "reason": leave.reason,
        })

    return {
        "balance": {"total": 20, "used": used_days, "remaining": max(0, 20 - used_days)},
        "history": history_list,
        "blocked_dates": blocked_dates,
    }


def _get_student_results_payload(student_id: str):
    results_data = []
    ca_records = (
        db.session.query(CAMarks, Subject)
        .join(Subject, CAMarks.subject_id == Subject.subject_id)
        .filter(CAMarks.student_id == student_id)
        .all()
    )
    for marks, sub in ca_records:
        entry = {
            "subject": sub.name,
            "code": sub.code,
            "ta1": marks.ta1 if marks.is_published_ta1 else "-",
            "ta2": marks.ta2 if marks.is_published_ta2 else "-",
            "ta3": marks.ta3 if marks.is_published_ta3 else "-",
        }
        results_data.append(entry)

    term_grant = TermGrantRecord.query.filter_by(student_id=student_id).first()
    grant_data = None
    if term_grant:
        grant_data = {
            "status": term_grant.status,
            "remarks": term_grant.remarks,
            "att_perc": term_grant.attendance_perc,
            "ca_avg": term_grant.avg_ca_score,
            "is_published": bool(getattr(term_grant, 'is_published', False)),
        }

    return {
        "results": results_data,
        "term_grant": grant_data,
    }


def _get_student_timetable_payload(student: StudentProfile):
    if not student.current_section_id:
        return {"section_id": None, "entries": []}

    section = ClassSection.query.get(student.current_section_id)
    if not section:
        return {"section_id": None, "entries": []}

    my_batch_name = _get_student_batch_name(student)

    # Get active version for this section
    active_version_id = get_active_version_id(section.section_id)

    query = (
        db.session.query(WeeklySchedule, Subject, StaffProfile, RoomMaster)
        .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
        .outerjoin(StaffProfile, WeeklySchedule.teacher_id == StaffProfile.staff_id)
        .outerjoin(RoomMaster, WeeklySchedule.room_id == RoomMaster.room_id)
        .filter(WeeklySchedule.section_id == section.section_id)
    )

    # Filter by active version if one exists
    if active_version_id:
        query = query.filter(WeeklySchedule.version_id == active_version_id)

    slots = query.all()
    day_order = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}
    entries = []
    for sched, subj, teacher, room in slots:
        # Batch filter
        if sched.target_batch and sched.target_batch != my_batch_name:
            continue

        # Elective filter
        if is_elective_type(subj.subject_type):
            try:
                is_approved = StudentElective.query.filter_by(
                    student_id=student.student_id,
                    subject_id=subj.subject_id,
                    status='Approved',
                ).first()
                if not is_approved:
                    continue
            except Exception:
                pass

        entries.append({
            "schedule_id": sched.schedule_id,
            "day_of_week": sched.day_of_week,
            "day_index": day_order.get(sched.day_of_week, 99),
            "start_time": sched.start_time.strftime('%H:%M') if sched.start_time else None,
            "end_time": sched.end_time.strftime('%H:%M') if sched.end_time else None,
            "session_type": sched.session_type,
            "target_batch": sched.target_batch,
            "subject": {
                "subject_id": subj.subject_id,
                "name": subj.name,
                "code": subj.code,
                "type": subj.subject_type,
            },
            "teacher": {
                "staff_id": teacher.staff_id,
                "name": teacher.full_name,
            } if teacher else None,
            "room": {
                "room_id": room.room_id,
                "room_number": room.room_number,
                "room_type": room.room_type,
            } if room else None,
        })

    entries.sort(key=lambda e: (e.get('day_index', 99), e.get('start_time') or ''))
    return {
        "section_id": section.section_id,
        "class": f"{section.class_level}-{section.name}",
        "entries": entries,
    }


def get_current_term_name():
    """Returns the current academic term based on Config or Date."""
    try:
        # 1. Try DB Config (Set by Admin via Rollover)
        conf = SystemConfig.query.get('current_term')
        if conf: return conf.value
        
        # 2. Fallback: Date Logic
        # July - Dec = Sem 1
        # Jan - June = Sem 2
        def _ay(start_year: int) -> str:
            return f"{start_year}-{(start_year + 1) % 100:02d}"  # e.g. YYYY-YY

        today = date.today()
        if 7 <= today.month <= 12:
            return f"{_ay(today.year)} Sem 1"
        else:
            return f"{_ay(today.year - 1)} Sem 2"
    except Exception:
        # Final fallback that does not depend on DB.
        today = date.today()
        if 7 <= today.month <= 12:
            start_year = today.year
            sem = 1
        else:
            start_year = today.year - 1
            sem = 2
        return f"{start_year}-{(start_year + 1) % 100:02d} Sem {sem}"


def parse_term_parts(term: str):
    """Parse a term like 'YYYY-YY Sem 1' into (academic_year, semester_number, semester_label)."""
    try:
        import re

        if not term:
            return None, None, None

        m = re.search(r"(?P<year>\d{4}-\d{2}).*?Sem\s*(?P<sem>\d+)", str(term), flags=re.IGNORECASE)
        if not m:
            return None, None, None

        year = m.group('year')
        sem_num = int(m.group('sem'))
        return year, sem_num, f"Sem {sem_num}"
    except Exception:
        return None, None, None


@app.route('/api/current_term', methods=['GET'])
def api_current_term():
    """Public endpoint for current academic term (safe to expose)."""
    term = get_current_term_name()
    year, sem_num, sem_label = parse_term_parts(term)
    return jsonify({
        "current_term": term,
        "academic_year": year,
        "semester_number": sem_num,
        "semester": sem_label,
    })

def get_current_dept():
    """Returns the first available department or None if no departments exist.
    
    NOTE: Departments must be created via hierarchy setup (SuperAdmin).
    This function no longer auto-creates departments.
    """
    return Department.query.first()

def is_elective_type(type_str):
    if not type_str: return False
    t = type_str.lower()
    return "elective" in t or "open" in t


def parse_semester_no(raw: str):
    """Parse semester identifier from CSV.

    Accepts: Roman numerals (I..VIII) or digits ("3").
    Returns int or None.
    """
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s:
        return None

    roman = {
        'I': 1,
        'II': 2,
        'III': 3,
        'IV': 4,
        'V': 5,
        'VI': 6,
        'VII': 7,
        'VIII': 8,
    }
    if s in roman:
        return roman[s]
    # Sometimes CSV may include "Sem 3" or similar
    try:
        import re
        m = re.search(r"(\d+)", s)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def get_db_file_handle(request_obj):
    if 'file' not in request_obj.files: raise ValueError("No file part")
    file = request_obj.files['file']
    if file.filename == '': raise ValueError("No selected file")
    return file

def parse_flexible_time(time_str):
    if pd.isna(time_str): return None
    time_str = str(time_str).strip()
    formats = ['%H:%M:%S', '%H:%M', '%I:%M %p', '%I:%M:%S %p']
    for fmt in formats:
        try: return datetime.strptime(time_str, fmt).time()
        except ValueError: continue
    return None

def log_activity(action, desc, user=None, dept_id=None):
    """Log an activity with the current user's name, department, and UTC timestamp."""
    try:
        # Get current user and department if not specified
        if user is None:
            user = "System"
            if hasattr(session, 'get') and session.get('user_id'):
                from sql_connection import UserMaster, StaffProfile
                u = UserMaster.query.get(session['user_id'])
                if u:
                    staff = StaffProfile.query.filter_by(staff_id=u.user_id).first()
                    user = staff.full_name if staff else u.username
                    # Get department ID for scoped logging (if not explicitly passed)
                    if dept_id is None and staff:
                        if staff.admin_access_dept_id:
                            dept_id = staff.admin_access_dept_id
                        elif staff.primary_department_id:
                            dept_id = staff.primary_department_id
        
        log = SystemLog(action_type=action, description=desc, performed_by=user, dept_id=dept_id)
        db.session.add(log)
        db.session.commit()
    except Exception as e: print(f"Logging Failed: {e}")

# ==========================================
# FRONTEND ROUTES
# ==========================================
@app.route('/')
def home(): return render_template('login.html')

# Staff Routes
@app.route('/staff/dashboard')
def render_staff_dashboard(): return render_template('staff_dashboard.html')
@app.route('/staff/class_teacher_dashboard')
def render_ct_dashboard(): return render_template('class_teacher_dashboard.html')
@app.route('/staff/mark_attendance')
def render_mark_attendance(): return render_template('attendance_sheet.html')
@app.route('/staff/leave_approvals')
def render_leave_approvals(): return render_template('leave_approval.html')
@app.route('/staff/events')
def render_event_dashboard(): return render_template('event_dashboard.html')
@app.route('/staff/amc_dashboard')
def render_amc_dashboard(): return render_template('amc_dashboard.html')
@app.route('/staff/lesson_plan')
def render_lesson_plan(): return render_template('lesson_planning.html')

# Student Routes
@app.route('/student/dashboard')
def render_student_dashboard(): return render_template('student_dashboard.html')
@app.route('/student/apply_leave')
def render_apply_leave(): return render_template('apply_leave.html')

# Admin Routes
@app.route('/admin/dashboard')
def render_admin_dashboard(): return render_template('admin_dashboard.html')
@app.route('/admin/manage_classes')
def render_admin_classes(): return render_template('admin_classes.html')
@app.route('/admin/manage_coordinators')
def render_admin_coordinators(): return render_template('admin_coordinators.html')
@app.route('/admin/manage_events')
def render_admin_events(): return render_template('admin_events.html')
@app.route('/admin/manage_faculty')
def render_admin_faculty(): return render_template('admin_faculty.html')
@app.route('/admin/student_directory')
def render_student_directory(): return render_template('admin_students.html')
@app.route('/admin/promotions')
def render_admin_promotions(): return render_template('admin_promotions.html')
@app.route('/admin/bulk_uploads')
def render_admin_uploads(): return render_template('admin_uploads.html')
@app.route('/admin/manage_allocations')
def render_admin_allocations(): return render_template('admin_allocations.html')

@app.route('/admin/manage_electives') # <--- THIS WAS MISSING
def render_admin_electives(): return render_template('admin_electives.html')

@app.route('/admin/historical_reports')
def render_historical_reports():
    # Legacy page (department performance). Redirect to dashboard now that
    # Academic Archives has a dedicated entry point.
    return redirect(url_for('render_admin_dashboard'))


@app.route('/staff/marks_entry')
def render_marks_entry():
    return render_template('marks_entry.html')

@app.route('/student/feedback')
def render_student_feedback():
    return render_template('student_feedback.html')

# ==========================================
# API: CORE UTILITIES
# ==========================================
@app.route('/api/core/classes', methods=['GET'])
@login_required
def get_core_classes():
    try:
        role_cf = (getattr(current_user, 'user_type', '') or '').strip().casefold()

        # SuperAdmin can enumerate all.
        scope_dept_ids = _get_user_scope_dept_ids()
        if scope_dept_ids is None:
            classes = ClassSection.query.order_by(ClassSection.class_level, ClassSection.name).all()
            return jsonify({"classes": [{"id": c.section_id, "name": f"{c.class_level} - {c.name}"} for c in classes]})

        # Student/Parent: only their linked section(s)
        if role_cf == 'student':
            sp = StudentProfile.query.filter_by(student_id=current_user.user_id).first()
            if not sp or not sp.current_section_id:
                return jsonify({"classes": []})
            sec = db.session.get(ClassSection, int(sp.current_section_id))
            if not sec:
                return jsonify({"classes": []})
            return jsonify({"classes": [{"id": sec.section_id, "name": f"{sec.class_level} - {sec.name}"}]})

        if role_cf == 'parent':
            child = StudentProfile.query.filter_by(parent_user_id=current_user.user_id).first()
            if not child or not child.current_section_id:
                return jsonify({"classes": []})
            sec = db.session.get(ClassSection, int(child.current_section_id))
            if not sec:
                return jsonify({"classes": []})
            return jsonify({"classes": [{"id": sec.section_id, "name": f"{sec.class_level} - {sec.name}"}]})

        # Admin/Staff: only sections in scoped departments
        if not scope_dept_ids:
            return jsonify({"classes": []})

        classes = (db.session.query(ClassSection)
                   .join(Specialization, ClassSection.spec_id == Specialization.id)
                   .filter(Specialization.dept_id.in_(scope_dept_ids))
                   .order_by(ClassSection.class_level, ClassSection.name)
                   .all())

        return jsonify({"classes": [{"id": c.section_id, "name": f"{c.class_level} - {c.name}"} for c in classes]})
    except Exception as e: return jsonify({"error": str(e)}), 500

# In app.py

@app.route('/api/core/students', methods=['GET'])
@login_required
def get_students_by_section():
    try:
        section_id = request.args.get('section_id')
        if not section_id:
            return jsonify({"error": "section_id is required"}), 400

        role_cf = (getattr(current_user, 'user_type', '') or '').strip().casefold()

        # SuperAdmin can enumerate any section.
        scope_dept_ids = _get_user_scope_dept_ids()
        if scope_dept_ids is None:
            pass
        elif role_cf == 'student':
            sp = StudentProfile.query.filter_by(student_id=current_user.user_id).first()
            if not sp or str(getattr(sp, 'current_section_id', '')) != str(section_id):
                return jsonify({"error": "Out of scope"}), 403
        elif role_cf == 'parent':
            child = StudentProfile.query.filter_by(parent_user_id=current_user.user_id).first()
            if not child or str(getattr(child, 'current_section_id', '')) != str(section_id):
                return jsonify({"error": "Out of scope"}), 403
        else:
            deny = _ensure_section_in_scope(int(section_id))
            if deny:
                return deny

        students = StudentProfile.query.filter_by(current_section_id=section_id).order_by(StudentProfile.admission_number).all()
        
        student_list = []
        
        # ... (Existing Session Fetch Logic) ...
        section_sessions = (db.session.query(SessionLog.session_id, WeeklySchedule.subject_id) # Added Subject ID
                            .join(WeeklySchedule)
                            .filter(WeeklySchedule.section_id == section_id)
                            .filter(SessionLog.status == 'Conducted')
                            .all())
        
        sess_ids = [s[0] for s in section_sessions]
        total_sessions = len(sess_ids)

        for s in students:
            # 1. Attendance (Overall)
            attended = 0
            if sess_ids:
                attended = AttendanceTransaction.query.filter(
                    AttendanceTransaction.session_id.in_(sess_ids),
                    AttendanceTransaction.student_id == s.student_id,
                                AttendanceTransaction.status.in_(PRESENT_STATUSES)
                ).count()
            perc = round((attended / total_sessions) * 100, 1) if total_sessions > 0 else 0

            # 2. Mentor Name
            mentor_name = "Unassigned"
            if s.mentor_batch_id:
                batch = db.session.get(MentorBatch, s.mentor_batch_id)
                if batch and batch.mentor_id:
                    mentor = db.session.get(StaffProfile, batch.mentor_id)
                    if mentor: mentor_name = mentor.full_name.split(' ')[0] # First name only for space

            # 3. Lowest Subject (Risk Identification)
            # Simplified Logic: Group attendance by subject for this student
            # (In a real scalable app, this might be heavy, but for a class list it's okay)
            # For MVP speed, let's just return the mentor and status for now.
            
            # 4. Status & Leaves
            leaves_taken = db.session.query(db.func.sum(LeaveApplication.total_days)).filter_by(student_id=s.student_id, status='Approved').scalar() or 0
            has_detention = DetentionRecord.query.filter_by(student_id=s.student_id, status='Assigned').first() is not None

            # --- NEW: CHECK FOR LOGS ---
            has_logs = MentorLog.query.filter_by(student_id=s.student_id).first() is not None

            student_list.append({
                "id": s.student_id,
                "roll": s.admission_number,
                "name": s.full_name,
                "stats": {
                    "attendance": perc,
                    "leaves": int(leaves_taken),
                    "status": s.academic_status, # New
                    "mentor": mentor_name,       # New
                    "has_detention": has_detention
                    ,"has_logs": has_logs
                }
            })
            
        return jsonify({"students": student_list})
    except Exception as e: return jsonify({"error": str(e)}), 500

# ==========================================
# API: AUTHENTICATION
# ==========================================
@app.route('/api/login', methods=['POST'])
@limiter.limit("10 per minute")  # Prevent brute force
@csrf.exempt  # Login form handles this differently
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()  # This could be Email OR Employee Code
    password = data.get('password')
    
    app.logger.info(f"Login attempt for username: {username}")

    if not username or not password:
        app.logger.warning(f"Login failed: missing credentials for {username}")
        return jsonify({"error": "username and password are required"}), 400

    try:
        # 1. Try finding by Username (Email/Phone) - Case Insensitive
        user = UserMaster.query.filter(UserMaster.username.ilike(username)).first()
        app.logger.info(f"User lookup by username: {'found' if user else 'not found'}")
        
        # 2. If not found, try finding by Employee Code (Staff)
        if not user:
            staff = StaffProfile.query.filter(StaffProfile.employee_code.ilike(username)).first()
            if staff:
                app.logger.info(f"Staff found by employee_code: {staff.staff_id}")
                # If Staff found, get their User account (staff_id maps to user_id)
                user = db.session.get(UserMaster, staff.staff_id)
        
        # 3. If STILL not found, try Student Admission Number (Optional Bonus)
        if not user:
            student = StudentProfile.query.filter(StudentProfile.admission_number.ilike(username)).first()
            if student:
                app.logger.info(f"Student found by admission_number: {student.student_id}")
                user = db.session.get(UserMaster, student.student_id)

        # 4. Verify Password
        if not user:
            app.logger.warning(f"Login failed: user not found for {username}")
            return jsonify({"error": "Invalid credentials"}), 401
            
        if not check_password_hash(user.password_hash, password):
            app.logger.warning(f"Login failed: invalid password for {username}")
            return jsonify({"error": "Invalid credentials"}), 401
            
        if not user.is_active:
            return jsonify({"error": "Account Deactivated."}), 403

        user_type_raw = (user.user_type or '').strip()
        role = 'SuperAdmin' if user_type_raw.casefold() == 'superadmin' else user_type_raw.capitalize()
        
        # Zombie Check (Safety)
        if role == 'Staff' and not StaffProfile.query.filter_by(staff_id=user.user_id).first():
             db.session.delete(user); db.session.commit()
             return jsonify({"error": "Corrupted Account. Please contact Admin."}), 403
        
        # *** SECURITY: Check if password change is required ***
        must_change = getattr(user, 'must_change_password', False)
        
        # *** SECURITY FIX: Use Flask-Login session-based auth ***
        login_user(user, remember=False)
        session.permanent = True  # Use PERMANENT_SESSION_LIFETIME
             
        redirect_map = {
            'Student': '/student/dashboard',
            'Staff': '/staff/dashboard',
            'Parent': '/parent/dashboard',
            'Admin': '/admin/dashboard',
            'SuperAdmin': '/superadmin/dashboard',
        }
        
        # Store user info in session for secure authentication
        session['user_id'] = user.user_id
        session['user_type'] = role
        session.permanent = True
        
        # If user must change password, redirect to password change page
        redirect_url = '/change-password' if must_change else redirect_map.get(role, '/')

        # First login onboarding for SuperAdmin.
        # Use persistent flag; fall back to School-count heuristic for older DBs.
        if not must_change and role == 'SuperAdmin':
            try:
                # Prefer the persistent flag if the column exists; otherwise fall back.
                from sqlalchemy import inspect as _sa_inspect
                cols = {c['name'] for c in _sa_inspect(db.engine).get_columns('user_master')}
                if 'onboarding_completed' in cols:
                    # Accessing the deferred attribute triggers a SELECT; safe only when column exists.
                    if bool(getattr(user, 'onboarding_completed', False)) is False:
                        redirect_url = '/superadmin/setup_hierarchy'
                else:
                    if School.query.count() == 0:
                        redirect_url = '/superadmin/setup_hierarchy'
            except Exception:
                # Safe default: send SuperAdmin to setup.
                redirect_url = '/superadmin/setup_hierarchy'
        
        return jsonify({
            "message": "Success", 
            "user_id": user.user_id, 
            "role": role, 
            "redirect_url": redirect_url,
            "must_change_password": must_change
        }), 200
    except Exception:
        app.logger.exception("/api/login failed")
        return jsonify({"error": "Server error"}), 500


# ==========================================
# API: LOGOUT
# ==========================================
@app.route('/api/logout', methods=['POST'])
def api_logout():
    """Log out the current user and clear session."""
    logout_user()
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200


# ==========================================
# API: PASSWORD CHANGE
# ==========================================
@app.route('/change-password')
@login_required
def render_change_password():
    """Render password change page."""
    return render_template('change_password.html')


@app.route('/api/change-password', methods=['POST'])
@login_required
@limiter.limit("5 per minute")
def api_change_password():
    """Change current user's password."""
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    if not current_password or not new_password:
        return jsonify({"error": "Current and new password are required"}), 400
    
    if new_password != confirm_password:
        return jsonify({"error": "New passwords do not match"}), 400
    
    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    
    # Verify current password
    if not check_password_hash(current_user.password_hash, current_password):
        return jsonify({"error": "Current password is incorrect"}), 401
    
    # Update password
    current_user.password_hash = generate_password_hash(new_password)
    current_user.must_change_password = False
    db.session.commit()
    
    # Determine redirect based on role
    role = (current_user.user_type or '').capitalize()
    redirect_map = { 
        'Student': '/student/dashboard', 
        'Staff': '/staff/dashboard', 
        'Parent': '/parent/dashboard', 
        'Admin': '/admin/dashboard',
        'Superadmin': '/admin/dashboard',
        'SuperAdmin': '/admin/dashboard',
    }
    
    return jsonify({
        "message": "Password changed successfully",
        "redirect_url": redirect_map.get(role, '/')
    }), 200


@app.route('/api/me', methods=['GET'])
@login_required
def api_me():
    """Return the current user's basic info for frontend session validation."""
    raw_type = (current_user.user_type or '').strip()
    is_super_admin = raw_type.casefold() == 'superadmin'
    role = 'SuperAdmin' if is_super_admin else raw_type.capitalize()
    
    # Get display name
    name = ''
    if role == 'Student':
        student = StudentProfile.query.filter_by(student_id=current_user.user_id).first()
        name = student.full_name if student else current_user.user_id
    elif role == 'Staff':
        staff = StaffProfile.query.filter_by(staff_id=current_user.user_id).first()
        name = staff.full_name if staff else current_user.user_id
    elif role == 'Parent':
        name = current_user.user_id  # Parent doesn't have a separate name table
    else:
        name = current_user.user_id
    
    admin_dept_id = None
    admin_dept_name = None
    try:
        # For Admin users (department admin), expose the scoped department for UI locking.
        if not is_super_admin and raw_type.casefold() == 'admin':
            staff = StaffProfile.query.filter_by(staff_id=current_user.user_id).first()
            dept_id = getattr(staff, 'admin_access_dept_id', None) if staff else None
            if not dept_id:
                dept = Department.query.filter_by(dept_admin_id=current_user.user_id).first()
                dept_id = dept.dept_id if dept else None
            if dept_id:
                admin_dept_id = int(dept_id)
                dept = Department.query.get(admin_dept_id)
                admin_dept_name = dept.name if dept else None
    except Exception:
        admin_dept_id = None
        admin_dept_name = None

    return jsonify({
        "user_id": current_user.user_id,
        "role": role,
        "is_super_admin": is_super_admin,
        "name": name,
        "must_change_password": current_user.must_change_password or False,
        "admin_dept_id": admin_dept_id,
        "admin_dept_name": admin_dept_name,
    }), 200


@app.route('/api/superadmin/dept_admin', methods=['POST'])
@login_required
@require_roles('Admin')
def api_superadmin_create_or_assign_dept_admin():
    deny = _require_superadmin_json()
    if deny:
        return deny
    data = request.get_json(silent=True) or {}
    dept_name = (data.get('department') or '').strip()
    full_name = (data.get('full_name') or '').strip()
    employee_code = (data.get('employee_code') or '').strip()
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not dept_name:
        return jsonify({"error": "department is required"}), 400
    if not employee_code:
        return jsonify({"error": "employee_code is required"}), 400
    if not email:
        return jsonify({"error": "email is required"}), 400
    if not password:
        return jsonify({"error": "password is required"}), 400
    if not full_name:
        full_name = email

    dept = Department.query.filter_by(name=dept_name).first()
    if not dept:
        return jsonify({"error": f"Department '{dept_name}' not found. Create it in hierarchy first."}), 400

    # If staff exists by employee_code, bind that account; else create new staff+user.
    staff = StaffProfile.query.filter(StaffProfile.employee_code.ilike(employee_code)).first()
    user = None

    # Email uniqueness: username is the login.
    existing_by_email = UserMaster.query.filter(UserMaster.username.ilike(email)).first()
    if existing_by_email and (not staff or existing_by_email.user_id != staff.staff_id):
        return jsonify({"error": "A user with this email already exists"}), 400

    if staff:
        user = db.session.get(UserMaster, staff.staff_id)
        if not user:
            return jsonify({"error": "StaffProfile exists but user account is missing"}), 400
        user.username = email
        user.password_hash = generate_password_hash(password)
        user.user_type = 'Admin'
        user.is_active = True
    else:
        new_id = str(uuid.uuid4())
        user = UserMaster(
            user_id=new_id,
            username=email,
            password_hash=generate_password_hash(password),
            user_type='Admin',
            is_active=True,
        )
        db.session.add(user)
        db.session.flush()
        staff = StaffProfile(
            staff_id=new_id,
            full_name=full_name,
            employee_code=employee_code,
            email_contact=email,
            admin_access_dept_id=dept.dept_id,
        )
        db.session.add(staff)

        # Break circular FK dependency (Department.dept_admin_id -> StaffProfile.staff_id
        # and StaffProfile.admin_access_dept_id -> Department.dept_id) by inserting the
        # staff row first, then updating the department.
        db.session.flush()

    # Scope and assign
    staff.admin_access_dept_id = dept.dept_id
    dept.dept_admin_id = staff.staff_id

    db.session.commit()
    return jsonify({"message": f"Department admin set for {dept.name} ({email})"}), 200


@app.route('/api/superadmin/hierarchy/import', methods=['POST'])
@login_required
@require_roles('Admin')
def api_superadmin_import_hierarchy_csv():
    """Import hierarchy from CSV and auto-create one department-admin login per department.

    Expected headers (case/spacing tolerant):
      - School, Degree, Program, Department, Specialization

    Optional headers:
      - Specialization Code
    """
    deny = _require_superadmin_json()
    if deny:
        return deny
    try:
        file = get_db_file_handle(request)
        df = pd.read_csv(file, dtype=str).fillna('')

        # Map normalized headers to actual column names
        col_map = {_normalize_header(c): c for c in df.columns}
        def col(*candidates):
            for cand in candidates:
                k = _normalize_header(cand)
                if k in col_map:
                    return col_map[k]
            return None

        school_col = col('School')
        degree_col = col('Degree')
        program_col = col('Program')
        dept_col = col('Department')
        spec_col = col('Specialization', 'Specialisation')
        spec_code_col = col('Specialization Code', 'Spec Code', 'Specialisation Code')

        required = {'School': school_col, 'Degree': degree_col, 'Program': program_col, 'Department': dept_col, 'Specialization': spec_col}
        missing = [k for k, v in required.items() if not v]
        if missing:
            return jsonify({"error": f"Missing required columns: {', '.join(missing)}"}), 400

        email_domain = (os.environ.get('ADMIN_EMAIL_DOMAIN') or 'mituniversity.edu.in').strip()

        created = {
            'schools': 0,
            'departments': 0,
            'programs': 0,
            'specializations': 0,
            'dept_admins': 0,
            'dept_admins_existing': 0,
        }
        dept_admin_credentials = []

        # Cache lookups
        schools_by_name = {s.name: s for s in School.query.all()}
        depts_by_name = {_canonical_department_name(d.name): d for d in Department.query.all()}

        # We'll create programs/specs on demand
        for _, row in df.iterrows():
            school_name = str(row.get(school_col, '')).strip()
            degree = str(row.get(degree_col, '')).strip() or 'Default'
            program_name = str(row.get(program_col, '')).strip() or 'Default'
            dept_name_raw = str(row.get(dept_col, '')).strip()
            dept_name = _canonical_department_name(dept_name_raw)
            spec_name = str(row.get(spec_col, '')).strip()
            spec_code = str(row.get(spec_code_col, '')).strip() if spec_code_col else ''

            if not school_name or not dept_name or not spec_name:
                continue

            school = schools_by_name.get(school_name)
            if not school:
                school = School(name=school_name)
                db.session.add(school)
                db.session.flush()
                schools_by_name[school_name] = school
                created['schools'] += 1

            dept = depts_by_name.get(dept_name)
            if not dept:
                dept = Department(name=dept_name, school_id=school.id)
                db.session.add(dept)
                db.session.flush()
                depts_by_name[dept_name] = dept
                created['departments'] += 1
            else:
                if getattr(dept, 'school_id', None) in (None, 0):
                    dept.school_id = school.id

            program = Program.query.filter_by(name=program_name, dept_id=dept.dept_id).first()
            if not program:
                program = Program(name=program_name, dept_id=dept.dept_id, level=degree, school_id=school.id)
                db.session.add(program)
                db.session.flush()
                created['programs'] += 1
            else:
                if getattr(program, 'school_id', None) in (None, 0):
                    program.school_id = school.id

            if getattr(dept, 'program_id', None) in (None, 0):
                dept.program_id = program.id

            if not spec_code:
                spec_code = _spec_code_from_name(spec_name)

            # Ensure uniqueness of spec_code per (department, program)
            base_code = spec_code
            suffix = 1
            while Specialization.query.filter_by(code=spec_code, dept_id=dept.dept_id, program_id=program.id).first() is not None:
                suffix += 1
                spec_code = f"{base_code}{suffix}"

            # Scope specialization lookup by department + program to avoid collisions
            # (e.g., Core -> "C" can exist in both IT and CSE).
            spec = Specialization.query.filter_by(code=spec_code, dept_id=dept.dept_id, program_id=program.id).first()
            if not spec:
                spec = Specialization(name=spec_name, code=spec_code, dept_id=dept.dept_id, program_id=program.id)
                db.session.add(spec)
                created['specializations'] += 1
            else:
                spec.name = spec_name
                spec.dept_id = dept.dept_id
                spec.program_id = program.id

        # Create/assign one dept admin per department (if not already assigned)
        # IMPORTANT: there is a circular FK between staff_profile.admin_access_dept_id -> department
        # and department.dept_admin_id -> staff_profile. To avoid FK violations during autoflush,
        # we explicitly flush the staff row before setting dept_admin_id.
        with db.session.no_autoflush:
            for dept in depts_by_name.values():
                if getattr(dept, 'dept_admin_id', None):
                    continue
                dept_code = _dept_code_from_name(dept.name)
                username = f"admin.{dept_code.lower()}@{email_domain}"

                # Create unique employee code
                emp_base = f"ADMIN_{dept_code}"
                emp_code = emp_base
                n = 0
                while StaffProfile.query.filter(StaffProfile.employee_code.ilike(emp_code)).first() is not None:
                    n += 1
                    emp_code = f"{emp_base}{n}"

                existing_user = UserMaster.query.filter(UserMaster.username.ilike(username)).first()
                if existing_user:
                    # Bind existing account as this department's admin.
                    staff = StaffProfile.query.filter_by(staff_id=existing_user.user_id).first()
                    if not staff:
                        staff = StaffProfile(
                            staff_id=existing_user.user_id,
                            full_name=f"{dept_code} Department Admin",
                            employee_code=emp_code,
                            email_contact=username,
                            admin_access_dept_id=dept.dept_id,
                        )
                        db.session.add(staff)
                        db.session.flush()
                    else:
                        staff.admin_access_dept_id = dept.dept_id

                    existing_user.user_type = 'Admin'
                    existing_user.is_active = True
                    existing_user.must_change_password = existing_user.must_change_password or True

                    dept.dept_admin_id = staff.staff_id
                    created['dept_admins_existing'] += 1
                    dept_admin_credentials.append({
                        'department': dept.name,
                        'email': username,
                        'employee_code': staff.employee_code,
                        'password': None,
                        'note': 'already existed; password not reset',
                    })
                    continue

                # Create the user + staff
                password = secrets.token_urlsafe(10)
                new_id = str(uuid.uuid4())
                user = UserMaster(
                    user_id=new_id,
                    username=username,
                    password_hash=generate_password_hash(password),
                    user_type='Admin',
                    is_active=True,
                    must_change_password=True,
                )
                db.session.add(user)
                db.session.flush()

                staff = StaffProfile(
                    staff_id=new_id,
                    full_name=f"{dept_code} Department Admin",
                    employee_code=emp_code,
                    email_contact=username,
                    admin_access_dept_id=dept.dept_id,
                )
                db.session.add(staff)
                db.session.flush()  # ensure staff_profile row exists before setting dept FK

                dept.dept_admin_id = staff.staff_id

                created['dept_admins'] += 1
                dept_admin_credentials.append({
                    'department': dept.name,
                    'email': username,
                    'employee_code': emp_code,
                    'password': password,
                })

        # Mark onboarding complete for SuperAdmin if possible
        try:
            from sqlalchemy import inspect as _sa_inspect
            cols = {c['name'] for c in _sa_inspect(db.engine).get_columns('user_master')}
            if 'onboarding_completed' in cols:
                su = db.session.get(UserMaster, current_user.user_id)
                if su is not None:
                    su.onboarding_completed = True
        except Exception:
            pass

        db.session.commit()
        return jsonify({
            'message': 'Imported',
            'created': created,
            'department_admins': dept_admin_credentials,
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ==========================================
# MOBILE API v1: AUTH + PROFILE (NEW)
# ==========================================
@app.route('/api/v1/auth/login', methods=['POST'])
@limiter.limit("10 per minute")  # Prevent brute force on mobile too
@csrf.exempt
def api_v1_auth_login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password')
    device_id = (data.get('device_id') or '').strip() or None

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = _find_user_for_login(username)
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401
    if not user.is_active:
        return jsonify({"error": "Account Deactivated."}), 403
    
    # Check for forced password change (mobile can handle this differently)
    must_change = getattr(user, 'must_change_password', False)

    role = (user.user_type or '').lower()
    access_token = _issue_access_token(user)
    refresh_token = _issue_refresh_token(user, device_id=device_id)

    # Build staff roles for staff users
    staff_roles = None
    if role == 'staff':
        user_id = user.user_id
        dept_managed = Department.query.filter_by(hod_staff_id=user_id).first()
        class_managed = ClassSection.query.filter_by(class_teacher_id=user_id).first()
        staff_profile = StaffProfile.query.filter_by(staff_id=user_id).first()
        mentor_batch = MentorBatch.query.filter_by(mentor_id=user_id).first()

        staff_roles = {
            "is_hod": dept_managed is not None,
            "is_class_teacher": class_managed is not None,
            "is_event_coordinator": getattr(staff_profile, 'is_event_coordinator', False) if staff_profile else False,
            "is_amc_member": getattr(staff_profile, 'is_amc_member', False) if staff_profile else False,
            "is_amc_head": getattr(staff_profile, 'is_amc_head', False) if staff_profile else False,
            "is_mentor": mentor_batch is not None
        }

    return jsonify({
        "access_token": access_token,
        "expires_in": app.config['MOBILE_ACCESS_TOKEN_TTL_SECONDS'],
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "must_change_password": must_change,
        "user": {
            "user_id": user.user_id,
            "role": role,
            "username": user.username,
            "staff_roles": staff_roles
        }
    }), 200


@app.route('/api/v1/auth/refresh', methods=['POST'])
def api_v1_auth_refresh():
    data = request.json or {}
    refresh_token = (data.get('refresh_token') or '').strip()
    device_id = (data.get('device_id') or '').strip() or None
    if not refresh_token:
        return jsonify({"error": "refresh_token is required"}), 400

    token_hash = _hash_token(refresh_token)
    rt = RefreshToken.query.filter_by(token_hash=token_hash).first()
    if not rt or rt.revoked_at is not None:
        return jsonify({"error": "Invalid refresh token"}), 401

    if rt.expires_at and rt.expires_at < datetime.utcnow():
        return jsonify({"error": "Refresh token expired"}), 401

    if device_id and rt.device_id and rt.device_id != device_id:
        return jsonify({"error": "Device mismatch"}), 401

    user = db.session.get(UserMaster, rt.user_id)
    if not user or not user.is_active:
        return jsonify({"error": "Unauthorized"}), 401

    access_token = _issue_access_token(user)
    return jsonify({
        "access_token": access_token,
        "expires_in": app.config['MOBILE_ACCESS_TOKEN_TTL_SECONDS'],
        "token_type": "Bearer",
    }), 200


@app.route('/api/v1/me', methods=['GET'])
def api_v1_me():
    try:
        user = _require_mobile_auth()
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    role = (user.user_type or '').lower()
    payload = {
        "user_id": user.user_id,
        "role": role,
        "username": user.username,
    }

    if role == 'student':
        student = StudentProfile.query.filter_by(student_id=user.user_id).first()
        section = ClassSection.query.get(student.current_section_id) if student and student.current_section_id else None
        payload["student"] = {
            "student_id": student.student_id if student else user.user_id,
            "name": student.full_name if student else None,
            "admission_number": student.admission_number if student else None,
            "section_id": student.current_section_id if student else None,
            "class": f"{section.class_level}-{section.name}" if section else None,
        }
    elif role == 'parent':
        payload["children"] = _get_parent_children(user.user_id)

    return jsonify(payload), 200


# ==========================================
# MOBILE API v1: PARENT CHILDREN (NEW)
# ==========================================
@app.route('/api/v1/parent/children', methods=['GET'])
def api_v1_parent_children():
    try:
        user = _require_mobile_auth()
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    if (user.user_type or '').lower() != 'parent':
        return jsonify({"error": "Forbidden"}), 403

    return jsonify({"children": _get_parent_children(user.user_id)}), 200


# ==========================================
# MOBILE API v1: NOTIFICATIONS (NEW)
# ==========================================
@app.route('/api/v1/notifications', methods=['GET'])
def api_v1_notifications_list():
    try:
        user = _require_mobile_auth()
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    role = (user.user_type or '').lower()
    limit = int(request.args.get('limit', '50'))
    limit = max(1, min(limit, 200))
    child_id = (request.args.get('child_id') or '').strip() or None

    items = []
    if role == 'parent':
        children = StudentProfile.query.filter_by(parent_user_id=user.user_id).all()
        child_map = {c.student_id: {"student_id": c.student_id, "name": c.full_name, "admission_number": c.admission_number} for c in children}
        allowed_child_ids = set(child_map.keys())
        if child_id:
            if child_id not in allowed_child_ids:
                return jsonify({"error": "Invalid child_id"}), 400
            allowed_child_ids = {child_id}

        if not allowed_child_ids:
            return jsonify({"notifications": []}), 200

        q = Notification.query.filter(Notification.user_id.in_(list(allowed_child_ids))).order_by(Notification.timestamp.desc()).limit(limit)
        for n in q:
            c = child_map.get(n.user_id)
            items.append({
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "link": n.link,
                "is_read": bool(n.is_read),
                "timestamp": _to_ist(n.timestamp),
                "child": c,
            })
    else:
        q = Notification.query.filter_by(user_id=user.user_id).order_by(Notification.timestamp.desc()).limit(limit)
        for n in q:
            items.append({
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "link": n.link,
                "is_read": bool(n.is_read),
                "timestamp": _to_ist(n.timestamp),
            })

    return jsonify({"notifications": items}), 200


@app.route('/api/v1/notifications/<int:notif_id>/read', methods=['POST'])
def api_v1_notifications_mark_read(notif_id: int):
    try:
        user = _require_mobile_auth()
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    n = Notification.query.get(notif_id)
    if not n:
        return jsonify({"error": "Not found"}), 404

    role = (user.user_type or '').lower()
    if role == 'parent':
        allowed_child = StudentProfile.query.filter_by(parent_user_id=user.user_id, student_id=n.user_id).first()
        if not allowed_child:
            return jsonify({"error": "Forbidden"}), 403
    else:
        if n.user_id != user.user_id:
            return jsonify({"error": "Forbidden"}), 403

    n.is_read = True
    db.session.commit()
    return jsonify({"message": "OK"}), 200


@app.route('/api/v1/notifications/clear', methods=['DELETE'])
def api_v1_notifications_clear():
    """Delete all notifications for the current user."""
    try:
        user = _require_mobile_auth()
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    role = (user.user_type or '').lower()
    deleted_count = 0

    if role == 'parent':
        # For parents, delete notifications for all their children
        children = StudentProfile.query.filter_by(parent_user_id=user.user_id).all()
        child_ids = [c.student_id for c in children]
        if child_ids:
            deleted_count = Notification.query.filter(Notification.user_id.in_(child_ids)).delete(synchronize_session=False)
    else:
        # For other users, delete their own notifications
        deleted_count = Notification.query.filter_by(user_id=user.user_id).delete(synchronize_session=False)

    db.session.commit()
    return jsonify({"message": "OK", "deleted": deleted_count}), 200


# ==========================================
# MOBILE API v1: PUSH DEVICE REGISTRATION (NEW)
# ==========================================
@app.route('/api/v1/push/register', methods=['POST'])
def api_v1_push_register():
    try:
        user = _require_mobile_auth()
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    platform = (data.get('platform') or '').strip().lower()
    device_id = (data.get('device_id') or '').strip()
    fcm_token = (data.get('fcm_token') or '').strip()

    if platform not in {'android', 'ios'}:
        return jsonify({"error": "platform must be 'android' or 'ios'"}), 400
    if not device_id or not fcm_token:
        return jsonify({"error": "device_id and fcm_token are required"}), 400

    try:
        app.logger.info(
            "push_register user_id=%s platform=%s device_id=%s ip=%s",
            user.user_id,
            platform,
            device_id,
            request.remote_addr,
        )
    except Exception:
        pass

    # Upsert by (platform, device_id, user_id)
    pd = PushDevice.query.filter_by(platform=platform, device_id=device_id, user_id=user.user_id).first()
    if not pd:
        pd = PushDevice(platform=platform, device_id=device_id, user_id=user.user_id, fcm_token=fcm_token)
        db.session.add(pd)
    else:
        pd.fcm_token = fcm_token
        pd.is_active = True
        pd.last_seen_at = datetime.utcnow()

    # If token was previously registered elsewhere, deactivate those rows.
    try:
        PushDevice.query.filter(PushDevice.fcm_token == fcm_token, PushDevice.id != pd.id).update({
            PushDevice.is_active: False,
            PushDevice.last_seen_at: datetime.utcnow(),
        })
    except Exception:
        pass

    db.session.commit()
    return jsonify({"message": "registered"}), 200


@app.route('/api/v1/push/unregister', methods=['POST'])
def api_v1_push_unregister():
    try:
        user = _require_mobile_auth()
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    platform = (data.get('platform') or '').strip().lower()
    device_id = (data.get('device_id') or '').strip()

    if platform not in {'android', 'ios'}:
        return jsonify({"error": "platform must be 'android' or 'ios'"}), 400
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400

    pd = PushDevice.query.filter_by(platform=platform, device_id=device_id, user_id=user.user_id).first()
    if pd:
        pd.is_active = False
        pd.last_seen_at = datetime.utcnow()
        db.session.commit()

    return jsonify({"message": "unregistered"}), 200


@app.route('/api/v1/push/test', methods=['POST'])
def api_v1_push_test():
    """Send a test push + in-app notification to the authenticated user."""
    try:
        user = _require_mobile_auth()
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    title = (data.get('title') or '').strip() or 'Test Push'
    message = (data.get('message') or '').strip() or 'If you can read this, FCM delivery works.'

    # Create an in-app notification record.
    notif = Notification(user_id=user.user_id, title=title, message=message, type='info', link=None)
    db.session.add(notif)
    db.session.commit()

    notif_id = getattr(notif, 'id', None)
    push_stats = _fcm_send_to_user_debug(
        user.user_id,
        title,
        message,
        {
            "notification_id": notif_id,
            "type": "info",
            "link": "",
            "user_id": user.user_id,
        },
    )

    response = {
        "message": "sent",
        "push_tokens": push_stats.get("tokens", 0),
        "push_success": push_stats.get("success", 0),
    }
    if push_stats.get("error"):
        response["push_error"] = push_stats.get("error")
    return jsonify(response), 200


# ==========================================
# MOBILE API v1: STUDENT (NEW)
# ==========================================
@app.route('/api/v1/student/attendance/subjects', methods=['GET'])
def api_v1_student_attendance_subjects():
    try:
        user = _require_mobile_auth()
        _require_role(user, {'student'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    student = _get_student_or_404(user.user_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    return jsonify(_student_subject_attendance_payload(student)), 200


@app.route('/api/v1/student/timetable', methods=['GET'])
def api_v1_student_timetable():
    try:
        user = _require_mobile_auth()
        _require_role(user, {'student'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    student = _get_student_or_404(user.user_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    return jsonify(_get_student_timetable_payload(student)), 200


@app.route('/api/v1/student/leaves', methods=['GET'])
def api_v1_student_leaves_list():
    try:
        user = _require_mobile_auth()
        _require_role(user, {'student'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    return jsonify(_get_student_leave_payload(user.user_id)), 200


@app.route('/api/v1/student/leaves', methods=['POST'])
def api_v1_student_leaves_apply():
    try:
        user = _require_mobile_auth()
        _require_role(user, {'student'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    data = request.json or {}
    try:
        total_days = float(data.get('total_days'))
        start = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        end = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
    except Exception:
        return jsonify({"error": "Invalid total_days/start_date/end_date"}), 400

    if end < start:
        return jsonify({"error": "end_date must be >= start_date"}), 400
    if total_days <= 0:
        return jsonify({"error": "total_days must be > 0"}), 400

    created = _create_leave_for_student(
        student_id=user.user_id,
        total_days=total_days,
        start=start,
        end=end,
        reason=data.get('reason'),
        leave_type=data.get('leave_type'),
    )
    return jsonify({"message": "Leave applied successfully", **created}), 200


@app.route('/api/v1/student/results', methods=['GET'])
def api_v1_student_results():
    try:
        user = _require_mobile_auth()
        _require_role(user, {'student'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    return jsonify(_get_student_results_payload(user.user_id)), 200


@app.route('/api/v1/student/events', methods=['GET'])
def api_v1_student_events_list():
    try:
        user = _require_mobile_auth()
        _require_role(user, {'student'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    records = (
        db.session.query(EventParticipation, EventMaster)
        .join(EventMaster, EventParticipation.event_id == EventMaster.event_id)
        .filter(EventParticipation.student_id == user.user_id)
        .order_by(EventMaster.start_date.desc(), EventMaster.event_id.desc())
        .all()
    )

    events = []
    for part, event in records:
        time_str = "Full Day"
        if event.start_time and event.end_time:
            time_str = f"{event.start_time.strftime('%H:%M')} - {event.end_time.strftime('%H:%M')}"

        events.append({
            "event_id": event.event_id,
            "name": event.event_name,
            "start_date": event.start_date.isoformat() if event.start_date else None,
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "time": time_str,
            "description": event.description,
            "status": part.status,
            "role": part.student_role,
        })

    return jsonify({"events": events}), 200


# ==========================================
# MOBILE API v1: PARENT (CHILD-SCOPED) (NEW)
# ==========================================
def _require_parent_child(parent_user_id: str, child_id: str) -> StudentProfile | None:
    if not child_id:
        return None
    return StudentProfile.query.filter_by(parent_user_id=parent_user_id, student_id=child_id).first()


@app.route('/api/v1/parent/<string:child_id>/attendance/subjects', methods=['GET'])
def api_v1_parent_child_attendance_subjects(child_id: str):
    try:
        user = _require_mobile_auth()
        _require_role(user, {'parent'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    child = _require_parent_child(user.user_id, child_id)
    if not child:
        return jsonify({"error": "Invalid child_id"}), 404

    return jsonify(_student_subject_attendance_payload(child)), 200


@app.route('/api/v1/parent/<string:child_id>/timetable', methods=['GET'])
def api_v1_parent_child_timetable(child_id: str):
    try:
        user = _require_mobile_auth()
        _require_role(user, {'parent'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    child = _require_parent_child(user.user_id, child_id)
    if not child:
        return jsonify({"error": "Invalid child_id"}), 404

    return jsonify(_get_student_timetable_payload(child)), 200


@app.route('/api/v1/parent/<string:child_id>/leaves', methods=['GET'])
def api_v1_parent_child_leaves_list(child_id: str):
    try:
        user = _require_mobile_auth()
        _require_role(user, {'parent'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    child = _require_parent_child(user.user_id, child_id)
    if not child:
        return jsonify({"error": "Invalid child_id"}), 404

    return jsonify(_get_student_leave_payload(child.student_id)), 200


@app.route('/api/v1/parent/<string:child_id>/leaves', methods=['POST'])
def api_v1_parent_child_leaves_apply(child_id: str):
    try:
        user = _require_mobile_auth()
        _require_role(user, {'parent'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    child = _require_parent_child(user.user_id, child_id)
    if not child:
        return jsonify({"error": "Invalid child_id"}), 404

    data = request.json or {}
    try:
        total_days = float(data.get('total_days'))
        start = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        end = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
    except Exception:
        return jsonify({"error": "Invalid total_days/start_date/end_date"}), 400

    if end < start:
        return jsonify({"error": "end_date must be >= start_date"}), 400
    if total_days <= 0:
        return jsonify({"error": "total_days must be > 0"}), 400

    created = _create_leave_for_student(
        student_id=child.student_id,
        total_days=total_days,
        start=start,
        end=end,
        reason=data.get('reason'),
        leave_type=data.get('leave_type'),
    )
    return jsonify({"message": "Leave applied successfully", **created}), 200


@app.route('/api/v1/parent/<string:child_id>/results', methods=['GET'])
def api_v1_parent_child_results(child_id: str):
    try:
        user = _require_mobile_auth()
        _require_role(user, {'parent'})
    except PermissionError as e:
        return jsonify({"error": str(e) if str(e) else "Unauthorized"}), 401

    child = _require_parent_child(user.user_id, child_id)
    if not child:
        return jsonify({"error": "Invalid child_id"}), 404

    return jsonify(_get_student_results_payload(child.student_id)), 200


# ==========================================
# MOBILE API v1: EXTRA SESSIONS
# ==========================================
@app.route('/api/v1/extra_sessions', methods=['GET'])
def api_v1_extra_sessions_list():
    """Get extra sessions for the authenticated user (staff sees their own, students see their section's)."""
    try:
        user = _require_mobile_auth()
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    role = (user.user_type or '').lower()
    today = datetime.now().date()
    result = []

    if role == 'staff':
        # Staff sees their own extra sessions
        sessions = (db.session.query(ExtraSession, Subject, ClassSection)
                    .join(Subject, ExtraSession.subject_id == Subject.subject_id)
                    .join(ClassSection, ExtraSession.section_id == ClassSection.section_id)
                    .filter(ExtraSession.teacher_id == user.user_id)
                    .filter(ExtraSession.status != 'Cancelled')
                    .filter(ExtraSession.date >= today)
                    .order_by(ExtraSession.date.asc(), ExtraSession.start_time.asc())
                    .all())

        for es, subj, sec in sessions:
            session_log = SessionLog.query.filter_by(extra_session_id=es.id).first()
            result.append({
                "id": es.id,
                "subject_id": es.subject_id,
                "subject_name": subj.name,
                "section_id": es.section_id,
                "section_name": f"{sec.class_level}-{sec.name}",
                "date": es.date.isoformat(),
                "start_time": es.start_time.strftime('%H:%M'),
                "end_time": es.end_time.strftime('%H:%M'),
                "topic": es.topic,
                "meeting_link": es.meeting_link,
                "status": es.status,
                "attendance_marked": session_log is not None,
                "is_today": es.date == today
            })

    elif role == 'student':
        # Student sees extra sessions for their section (filtered by elective if applicable)
        student = StudentProfile.query.filter_by(student_id=user.user_id).first()
        if student and student.current_section_id:
            sessions = (db.session.query(ExtraSession, Subject, ClassSection, StaffProfile)
                        .join(Subject, ExtraSession.subject_id == Subject.subject_id)
                        .join(ClassSection, ExtraSession.section_id == ClassSection.section_id)
                        .join(StaffProfile, ExtraSession.teacher_id == StaffProfile.staff_id)
                        .filter(ExtraSession.section_id == student.current_section_id)
                        .filter(ExtraSession.status != 'Cancelled')
                        .filter(ExtraSession.date >= today)
                        .order_by(ExtraSession.date.asc(), ExtraSession.start_time.asc())
                        .all())

            for es, subj, sec, teacher in sessions:
                # Filter by elective: only show if student has approved selection
                if is_elective_type(subj.subject_type):
                    approved = StudentElective.query.filter_by(
                        student_id=student.student_id,
                        subject_id=subj.subject_id,
                        status='Approved'
                    ).first()
                    if not approved:
                        continue  # Skip - student hasn't opted for this elective

                result.append({
                    "id": es.id,
                    "subject_name": subj.name,
                    "section_name": f"{sec.class_level}-{sec.name}",
                    "teacher_name": teacher.full_name,
                    "date": es.date.isoformat(),
                    "start_time": es.start_time.strftime('%H:%M'),
                    "end_time": es.end_time.strftime('%H:%M'),
                    "topic": es.topic,
                    "meeting_link": es.meeting_link,
                    "status": es.status,
                    "is_today": es.date == today
                })

    elif role == 'parent':
        # Parent sees extra sessions for all their children (filtered by elective if applicable)
        children = StudentProfile.query.filter_by(parent_user_id=user.user_id).all()
        for child in children:
            if not child.current_section_id:
                continue  # Skip children without assigned section

            sessions = (db.session.query(ExtraSession, Subject, ClassSection, StaffProfile)
                        .join(Subject, ExtraSession.subject_id == Subject.subject_id)
                        .join(ClassSection, ExtraSession.section_id == ClassSection.section_id)
                        .join(StaffProfile, ExtraSession.teacher_id == StaffProfile.staff_id)
                        .filter(ExtraSession.section_id == child.current_section_id)
                        .filter(ExtraSession.status != 'Cancelled')
                        .filter(ExtraSession.date >= today)
                        .order_by(ExtraSession.date.asc(), ExtraSession.start_time.asc())
                        .all())

            for es, subj, sec, teacher in sessions:
                # Filter by elective: only show if child has approved selection
                if is_elective_type(subj.subject_type):
                    approved = StudentElective.query.filter_by(
                        student_id=child.student_id,
                        subject_id=subj.subject_id,
                        status='Approved'
                    ).first()
                    if not approved:
                        continue  # Skip - child hasn't opted for this elective

                result.append({
                    "id": es.id,
                    "child_name": child.full_name,
                    "child_id": child.student_id,
                    "subject_name": subj.name,
                    "section_name": f"{sec.class_level}-{sec.name}",
                    "teacher_name": teacher.full_name,
                    "date": es.date.isoformat(),
                    "start_time": es.start_time.strftime('%H:%M'),
                    "end_time": es.end_time.strftime('%H:%M'),
                    "topic": es.topic,
                    "meeting_link": es.meeting_link,
                    "status": es.status,
                    "is_today": es.date == today
                })

    return jsonify({"extra_sessions": result}), 200


@app.route('/api/v1/extra_sessions', methods=['POST'])
def api_v1_extra_sessions_create():
    """Create a new extra session (staff only)."""
    try:
        user = _require_mobile_auth()
        _require_role(user, {'staff'})
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    subject_id = data.get('subject_id')
    section_id = data.get('section_id')
    date_str = data.get('date')
    start_time_str = data.get('start_time')
    end_time_str = data.get('end_time')
    topic = data.get('topic', '').strip()
    meeting_link = data.get('meeting_link', '').strip()

    if not all([subject_id, section_id, date_str, start_time_str, end_time_str]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        from datetime import time as dt_time
        session_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()
    except ValueError:
        return jsonify({"error": "Invalid date/time format"}), 400

    # Validation: Date not in past
    if session_date < datetime.now().date():
        return jsonify({"error": "Cannot schedule sessions in the past"}), 400

    # Validation: Weekday must be after 17:00
    from datetime import time as dt_time
    day_of_week = session_date.weekday()
    is_weekend = day_of_week >= 5

    if not is_weekend and start_time < dt_time(17, 0):
        return jsonify({"error": "Weekday extra sessions must start after 5:00 PM"}), 400

    # Validation: Check section conflict
    conflicting = ExtraSession.query.filter(
        ExtraSession.section_id == section_id,
        ExtraSession.date == session_date,
        ExtraSession.status != 'Cancelled',
        db.or_(
            db.and_(ExtraSession.start_time <= start_time, ExtraSession.end_time > start_time),
            db.and_(ExtraSession.start_time < end_time, ExtraSession.end_time >= end_time),
            db.and_(ExtraSession.start_time >= start_time, ExtraSession.end_time <= end_time)
        )
    ).first()

    if conflicting:
        return jsonify({"error": "This class already has an extra session scheduled at this time"}), 400

    extra_session = ExtraSession(
        subject_id=subject_id,
        teacher_id=user.user_id,
        section_id=section_id,
        date=session_date,
        start_time=start_time,
        end_time=end_time,
        topic=topic if topic else None,
        meeting_link=meeting_link if meeting_link else None,
        status='Scheduled'
    )
    db.session.add(extra_session)
    db.session.commit()

    # Send notification to students (filter by elective if applicable)
    subject = Subject.query.get(subject_id)
    if is_elective_type(subject.subject_type):
        # Only notify students with approved elective selection
        students = (db.session.query(StudentProfile)
                    .join(StudentElective, StudentProfile.student_id == StudentElective.student_id)
                    .filter(StudentProfile.current_section_id == section_id)
                    .filter(StudentElective.subject_id == subject_id)
                    .filter(StudentElective.status == 'Approved')
                    .all())
    else:
        students = StudentProfile.query.filter_by(current_section_id=section_id).all()

    for student in students:
        send_notification(
            student.student_id,
            f"Extra Class: {subject.name}",
            f"Extra class scheduled on {session_date.strftime('%d %b')} at {start_time.strftime('%I:%M %p')}. Topic: {topic or 'TBA'}",
            type='info'
        )

    return jsonify({"message": "Extra session created", "id": extra_session.id}), 201


@app.route('/api/v1/extra_sessions/<int:session_id>', methods=['DELETE'])
def api_v1_extra_sessions_cancel(session_id):
    """Cancel an extra session (staff only)."""
    try:
        user = _require_mobile_auth()
        _require_role(user, {'staff'})
    except PermissionError:
        return jsonify({"error": "Unauthorized"}), 401

    extra_session = ExtraSession.query.get(session_id)
    if not extra_session:
        return jsonify({"error": "Extra session not found"}), 404

    if extra_session.teacher_id != user.user_id:
        return jsonify({"error": "Not authorized to cancel this session"}), 403

    session_log = SessionLog.query.filter_by(extra_session_id=session_id).first()
    if session_log:
        return jsonify({"error": "Cannot cancel session after attendance is marked"}), 400

    extra_session.status = 'Cancelled'
    db.session.commit()

    # Notify students (filter by elective if applicable)
    subject = Subject.query.get(extra_session.subject_id)
    if is_elective_type(subject.subject_type):
        # Only notify students with approved elective selection
        students = (db.session.query(StudentProfile)
                    .join(StudentElective, StudentProfile.student_id == StudentElective.student_id)
                    .filter(StudentProfile.current_section_id == extra_session.section_id)
                    .filter(StudentElective.subject_id == extra_session.subject_id)
                    .filter(StudentElective.status == 'Approved')
                    .all())
    else:
        students = StudentProfile.query.filter_by(current_section_id=extra_session.section_id).all()

    for student in students:
        send_notification(
            student.student_id,
            f"Extra Class Cancelled: {subject.name}",
            f"The extra class scheduled on {extra_session.date.strftime('%d %b')} at {extra_session.start_time.strftime('%I:%M %p')} has been cancelled.",
            type='warning'
        )

    return jsonify({"message": "Extra session cancelled"}), 200


# ==========================================
# API: STAFF DASHBOARD
# ==========================================
# In app.py

@app.route('/api/staff/dashboard', methods=['GET'])
@login_required
@require_roles('Staff')
def staff_dashboard():
    try:
        # Do not trust user_id from the client; always use the authenticated user.
        user_id = current_user.user_id

        staff = StaffProfile.query.filter_by(staff_id=user_id).first()
        if not staff: return jsonify({"error": "Staff profile not found"}), 404

        scope_dept_ids = _get_user_scope_dept_ids()

        # --- 1. ROLES & PERMISSIONS ---
        dept_managed = Department.query.filter_by(hod_staff_id=user_id).first()
        is_hod = True if dept_managed else False
        
        class_managed = ClassSection.query.filter_by(class_teacher_id=user_id).first()
        is_class_teacher = True if class_managed else False
        
        # Safe Access using getattr (prevents crash if column missing)
        is_coordinator = getattr(staff, 'is_event_coordinator', False)
        is_amc_member = getattr(staff, 'is_amc_member', False)
        is_amc_head = getattr(staff, 'is_amc_head', False)

        can_assign_detention = SubjectAllocation.query.filter_by(teacher_id=user_id).first() is not None
        can_assign_detention = True

        # --- 2. CLASS TEACHER DATA ---
        class_details = {}
        if is_class_teacher:
            student_count = StudentProfile.query.filter_by(current_section_id=class_managed.section_id).count()
            class_details = { "name": f"{class_managed.class_level} - {class_managed.name}", "count": student_count }

        # --- 3. MENTOR DATA ---
        # Check for batches assigned to this staff member
        mentor_batches = MentorBatch.query.filter_by(mentor_id=staff.staff_id).all()
        is_mentor = len(mentor_batches) > 0
        mentee_count = 0
        if is_mentor:
            for b in mentor_batches: 
                # Count students in each batch
                mentee_count += StudentProfile.query.filter_by(mentor_batch_id=b.batch_id).count()

        # --- 4. STATS (Load & Attendance) ---
        weekly_load = WeeklySchedule.query.filter_by(teacher_id=staff.staff_id).count()
        
        my_sessions = SessionLog.query.filter_by(actual_teacher_id=staff.staff_id).all()
        session_ids = [s.session_id for s in my_sessions]
        avg_attendance = 0
        if session_ids:
            total = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(session_ids)).count()
            present = AttendanceTransaction.query.filter(
                AttendanceTransaction.session_id.in_(session_ids),
                AttendanceTransaction.status.in_(PRESENT_STATUSES)
            ).count()
            if total > 0: avg_attendance = round((present / total) * 100, 1)

        # --- 5. ASSIGNED COURSES (Subject Allocation) ---
        alloc_q = (db.session.query(SubjectAllocation, Subject, ClassSection)
                   .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                   .join(ClassSection, SubjectAllocation.section_id == ClassSection.section_id)
                   .filter(SubjectAllocation.teacher_id == staff.staff_id))

        # Enforce department isolation for staff dashboards when we can resolve a scope.
        if scope_dept_ids is not None and scope_dept_ids:
            from sqlalchemy import or_
            alloc_q = (alloc_q.outerjoin(Specialization, ClassSection.spec_id == Specialization.id)
                             .filter(or_(
                                 Subject.dept_id.in_(scope_dept_ids),
                                 Specialization.dept_id.in_(scope_dept_ids),
                             )))

        allocations = alloc_q.all()
        
        my_subjects_list = []
        for alloc, subj, sec in allocations:
            # Calculate weekly load for this specific subject
            slots_count = WeeklySchedule.query.filter_by(
                subject_id=subj.subject_id, 
                section_id=sec.section_id, 
                teacher_id=staff.staff_id
            ).count()
            
            my_subjects_list.append({
                "subject_id": subj.subject_id, 
                "subject_name": subj.name, 
                "section_id": sec.section_id, 
                "class_name": f"{sec.class_level}-{sec.name}", 
                "sessions_per_week": slots_count,
                "status": "Scheduled" if slots_count > 0 else "Not Scheduled"
            })



        # SCHEDULE LOGIC
        today_name = datetime.now().strftime("%A")
        today_date = datetime.now().date()
        current_day_idx = {'Monday':0,'Tuesday':1,'Wednesday':2,'Thursday':3,'Friday':4,'Saturday':5,'Sunday':6}.get(today_name, 0)

        window_start = today_date
        window_end = today_date + timedelta(days=13)  # 2 weeks window for upcoming sessions
        
        # Filter by Active timetable versions only
        slots_q = (db.session.query(WeeklySchedule, ClassSection, Subject)
                   .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
                   .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                   .outerjoin(TimetableVersion, WeeklySchedule.version_id == TimetableVersion.version_id)
                   .filter(WeeklySchedule.teacher_id == staff.staff_id)
                   .filter(db.or_(
                       TimetableVersion.status == 'Active',
                       WeeklySchedule.version_id.is_(None)
                   )))

        if scope_dept_ids is not None and scope_dept_ids:
            from sqlalchemy import or_
            slots_q = (slots_q.outerjoin(Specialization, ClassSection.spec_id == Specialization.id)
                             .filter(or_(
                                 Subject.dept_id.in_(scope_dept_ids),
                                 Specialization.dept_id.in_(scope_dept_ids),
                             )))

        all_slots = slots_q.all()
        
        today_schedule = []; upcoming_schedule = []
        weekly_calendar = [] # <--- Ensure this list is initialized

        # --- LOAD ADJUSTMENT STATE (Pending + Approved for this staff within next 7 days) ---
        adjustments = []
        adj_by_req_key = {}
        adj_by_adj_key = {}
        other_staff_ids = set()
        schedule_meta = {}
        try:
            adjustments = (
                LoadAdjustment.query
                .filter(LoadAdjustment.status.in_(['Pending', 'Approved']))
                .filter((LoadAdjustment.requester_id == staff.staff_id) | (LoadAdjustment.adjuster_id == staff.staff_id))
                .filter(
                    (LoadAdjustment.req_date.between(window_start, window_end)) |
                    (LoadAdjustment.adj_date.between(window_start, window_end))
                )
                .order_by(LoadAdjustment.created_at.desc())
                .all()
            )

            for a in adjustments:
                other_staff_ids.add(a.requester_id)
                other_staff_ids.add(a.adjuster_id)

                rk = (a.req_schedule_id, a.req_date)
                ak = (a.adj_schedule_id, a.adj_date)

                # Keep latest by created_at (query is desc)
                if rk not in adj_by_req_key:
                    adj_by_req_key[rk] = a
                if ak not in adj_by_adj_key:
                    adj_by_adj_key[ak] = a

            # Preload schedule metadata for swapped-slot display (subject/class/time/day)
            adj_schedule_ids = list({a.req_schedule_id for a in adjustments if a.req_schedule_id} | {a.adj_schedule_id for a in adjustments if a.adj_schedule_id})
            if adj_schedule_ids:
                rows = (db.session.query(WeeklySchedule, ClassSection, Subject)
                        .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
                        .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                        .filter(WeeklySchedule.schedule_id.in_(adj_schedule_ids))
                        .all())
                for ws, sec, sub in rows:
                    schedule_meta[ws.schedule_id] = {
                        "schedule_id": ws.schedule_id,
                        "day": ws.day_of_week,
                        "time": f"{ws.start_time.strftime('%I:%M %p')} - {ws.end_time.strftime('%I:%M %p')}",
                        "subject": sub.name,
                        "class": f"{sec.class_level}-{sec.name}",
                    }
        except Exception:
            adjustments = []
            adj_by_req_key = {}
            adj_by_adj_key = {}
            schedule_meta = {}

        other_staff_ids.discard(staff.staff_id)
        staff_name_map = {}
        staff_code_map = {}
        if other_staff_ids:
            profs = StaffProfile.query.filter(StaffProfile.staff_id.in_(list(other_staff_ids))).all()
            staff_name_map = {p.staff_id: p.full_name for p in profs}
            staff_code_map = {p.staff_id: p.employee_code for p in profs}

        def _slot_adjustment_payload(slot_id: int, slot_date: date):
            """Return adjustment info for a slot that belongs to this staff (swap-out cases)."""
            a = adj_by_req_key.get((slot_id, slot_date))
            if a and a.requester_id == staff.staff_id:
                partner_id = a.adjuster_id
                swap_meta = schedule_meta.get(a.adj_schedule_id)
                swap_payload = None
                if swap_meta:
                    swap_payload = dict(swap_meta)
                    swap_payload["date_iso"] = a.adj_date.isoformat() if a.adj_date else None
                    swap_payload["date_display"] = a.adj_date.strftime('%d %b') if a.adj_date else None
                return {
                    "id": a.id,
                    "status": a.status,
                    "role": "requester",
                    "kind": "out",
                    "partner_id": partner_id,
                    "partner_name": staff_name_map.get(partner_id, partner_id),
                    "partner_code": staff_code_map.get(partner_id),
                    "swap": swap_payload,
                }

            a = adj_by_adj_key.get((slot_id, slot_date))
            if a and a.adjuster_id == staff.staff_id:
                partner_id = a.requester_id
                swap_meta = schedule_meta.get(a.req_schedule_id)
                swap_payload = None
                if swap_meta:
                    swap_payload = dict(swap_meta)
                    swap_payload["date_iso"] = a.req_date.isoformat() if a.req_date else None
                    swap_payload["date_display"] = a.req_date.strftime('%d %b') if a.req_date else None
                return {
                    "id": a.id,
                    "status": a.status,
                    "role": "adjuster",
                    "kind": "out",
                    "partner_id": partner_id,
                    "partner_name": staff_name_map.get(partner_id, partner_id),
                    "partner_code": staff_code_map.get(partner_id),
                    "swap": swap_payload,
                }

            return None

        # Helper to convert time to float (e.g. 09:30 -> 9.5) - define once
        def time_to_float(t): return t.hour + (t.minute / 60.0)

        for slot, section, subject in all_slots:
            slot_day_idx = {'Monday':0,'Tuesday':1,'Wednesday':2,'Thursday':3,'Friday':4,'Saturday':5,'Sunday':6}.get(slot.day_of_week, 7)

            s_type = getattr(slot, 'session_type', 'Lecture')
            s_batch = getattr(slot, 'target_batch', None)

            start_float = time_to_float(slot.start_time)
            end_float = time_to_float(slot.end_time)

            # Generate slots for both this week and next week (2 weeks total)
            for week_offset in range(2):
                # Compute the occurrence date for this weekday
                days_ahead = (slot_day_idx - current_day_idx) % 7 + (week_offset * 7)
                slot_date = today_date + timedelta(days=days_ahead)

                # Skip if beyond window
                if slot_date > window_end:
                    continue

                # Generate sort_key that accounts for actual date (not just day of week)
                # Use days_from_today * 10000 + time for proper ordering
                days_from_today = (slot_date - today_date).days
                sort_key = days_from_today * 10000 + int(slot.start_time.strftime('%H%M'))

                slot_data = {
                    "id": slot.schedule_id,
                    "time": f"{slot.start_time.strftime('%I:%M %p')} - {slot.end_time.strftime('%I:%M %p')}",
                    "class": f"{section.class_level}-{section.name}",
                    "subject": subject.name,
                    "day": slot.day_of_week,
                    "date_iso": slot_date.strftime('%Y-%m-%d'),
                    "date_display": slot_date.strftime('%d %b'),
                    "type": s_type,
                    "batch": s_batch,
                    "sort_key": sort_key,
                    # NEW FIELDS FOR CALENDAR
                    "start_float": start_float,
                    "duration_float": end_float - start_float,
                    "adjustment": _slot_adjustment_payload(slot.schedule_id, slot_date),
                }

                if slot_date == today_date:
                    session_exists = SessionLog.query.filter_by(schedule_id=slot.schedule_id, session_date=today_date).first()
                    slot_data["status"] = "Done" if session_exists else "Pending"
                    today_schedule.append(slot_data)
                elif slot_date > today_date:
                    upcoming_schedule.append(slot_data)

                # Add to Weekly Calendar (only first week for calendar view)
                if week_offset == 0:
                    weekly_calendar.append(slot_data)

        today_schedule.sort(key=lambda x: x['sort_key'])
        upcoming_schedule.sort(key=lambda x: x['sort_key'])

        # Inject swapped-in classes for Approved adjustments (today + upcoming within the 2-week window)
        try:
            approved_only = [a for a in adjustments if a.status == 'Approved']
            inject_pairs = []  # (schedule_id, date, role, partner_id)
            for a in approved_only:
                # Adjuster takes requester's slot on req_date
                if a.adjuster_id == staff.staff_id and window_start <= a.req_date <= window_end:
                    inject_pairs.append((a.req_schedule_id, a.req_date, 'adjuster', a.requester_id))
                # Requester takes adjuster's slot on adj_date
                if a.requester_id == staff.staff_id and window_start <= a.adj_date <= window_end:
                    inject_pairs.append((a.adj_schedule_id, a.adj_date, 'requester', a.adjuster_id))

            if inject_pairs:
                inject_ids = list({sid for sid, _, _, _ in inject_pairs})
                inject_schedule_map = {}
                injected_rows = (db.session.query(WeeklySchedule, ClassSection, Subject)
                                 .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
                                 .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                                 .filter(WeeklySchedule.schedule_id.in_(inject_ids))
                                 .all())
                for ws, sec, sub in injected_rows:
                    inject_schedule_map[ws.schedule_id] = (ws, sec, sub)

                # Avoid duplicates by key(schedule_id,date_iso)
                existing_keys = set()
                for x in today_schedule:
                    try:
                        existing_keys.add((int(x.get('id')), x.get('date_iso')))
                    except Exception:
                        pass
                for x in upcoming_schedule:
                    try:
                        existing_keys.add((int(x.get('id')), x.get('date_iso')))
                    except Exception:
                        pass

                for schedule_id, d, role, partner_id in inject_pairs:
                    tup = inject_schedule_map.get(schedule_id)
                    if not tup:
                        continue
                    ws, sec, sub = tup
                    slot_day_idx = {'Monday':0,'Tuesday':1,'Wednesday':2,'Thursday':3,'Friday':4,'Saturday':5,'Sunday':6}.get(ws.day_of_week, 7)

                    date_iso = d.strftime('%Y-%m-%d')
                    if (int(schedule_id), date_iso) in existing_keys:
                        continue

                    s_type = getattr(ws, 'session_type', 'Lecture')
                    s_batch = getattr(ws, 'target_batch', None)

                    def time_to_float(t):
                        return t.hour + (t.minute / 60.0)

                    start_float = time_to_float(ws.start_time)
                    end_float = time_to_float(ws.end_time)

                    slot_data = {
                        "id": ws.schedule_id,
                        "time": f"{ws.start_time.strftime('%I:%M %p')} - {ws.end_time.strftime('%I:%M %p')}",
                        "class": f"{sec.class_level}-{sec.name}",
                        "subject": sub.name,
                        "day": ws.day_of_week,
                        "date_iso": date_iso,
                        "date_display": d.strftime('%d %b'),
                        "type": s_type,
                        "batch": s_batch,
                        "sort_key": slot_day_idx * 10000 + int(ws.start_time.strftime('%H%M')),
                        "start_float": start_float,
                        "duration_float": end_float - start_float,
                        "adjustment": {
                            "status": "Approved",
                            "role": role,
                            "kind": "in",
                            "partner_id": partner_id,
                            "partner_name": staff_name_map.get(partner_id, partner_id),
                            "partner_code": staff_code_map.get(partner_id),
                        }
                    }

                    if d == today_date:
                        session_exists = SessionLog.query.filter_by(schedule_id=ws.schedule_id, session_date=today_date).first()
                        slot_data["status"] = "Done" if session_exists else "Pending"
                        today_schedule.append(slot_data)
                    else:
                        upcoming_schedule.append(slot_data)
                    existing_keys.add((int(schedule_id), date_iso))

                today_schedule.sort(key=lambda x: x['sort_key'])
                upcoming_schedule.sort(key=lambda x: x['sort_key'])
        except Exception:
            pass
        
        # ... (Rest of the function logic for History, Leaves, Response etc.) ...
        # Ensure you pass "weekly_calendar": weekly_calendar in the final JSON response

        # --- 7. HISTORY ---
        # history_records = (db.session.query(SessionLog, WeeklySchedule, Subject, ClassSection)
        #                 .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
        #                 .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
        #                 .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
        #                 .filter(SessionLog.actual_teacher_id == staff.staff_id)
        #                 .filter(SessionLog.status == 'Conducted')
        #                 .order_by(SessionLog.session_date.desc())
        #                 .limit(5)
        #                 .all())

        # history_list = []
        # for sess, sched, subj, sec in history_records:
        #     total = AttendanceTransaction.query.filter_by(session_id=sess.session_id).count()
        #     present = AttendanceTransaction.query.filter(
        #         AttendanceTransaction.session_id == sess.session_id, 
        #         AttendanceTransaction.status.in_(PRESENT_STATUSES)
        #     ).count()
        #     perc = round((present/total)*100) if total > 0 else 0
            
        #     history_list.append({ 
        #         "schedule_id": sched.schedule_id, 
        #         "date_iso": sess.session_date.strftime('%Y-%m-%d'), 
        #         "date_display": sess.session_date.strftime('%d %b'), 
        #         "subject": subj.name, 
        #         "class": f"{sec.class_level}-{sec.name}", 
        #         "percentage": perc 
        #     })
# --- UPDATED HISTORY LOGIC (LIMIT 2) ---
        history_records = (db.session.query(SessionLog, WeeklySchedule, Subject, ClassSection)
                        .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                        .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                        .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
                        .filter(SessionLog.actual_teacher_id == staff.staff_id)
                        .filter(SessionLog.status == 'Conducted')
                        .order_by(SessionLog.session_date.asc())
                        .limit(1) # <--- CHANGED FROM 5 TO 2
                        .all())

        history_list = []
        for sess, sched, subj, sec in history_records:
            total = AttendanceTransaction.query.filter_by(session_id=sess.session_id).count()
            present = AttendanceTransaction.query.filter(AttendanceTransaction.session_id == sess.session_id, AttendanceTransaction.status.in_(PRESENT_STATUSES)).count()
            perc = round((present/total)*100) if total > 0 else 0
            history_list.append({ "schedule_id": sched.schedule_id, "date_iso": sess.session_date.strftime('%Y-%m-%d'), "date_display": sess.session_date.strftime('%d %b'), "subject": subj.name, "class": f"{sec.class_level}-{sec.name}", "percentage": perc })

        # --- 8. PENDING LEAVES ---
        pending_leaves = []
        if is_class_teacher:
            pending_count = (db.session.query(LeaveApplication, StudentProfile)
                             .join(StudentProfile, LeaveApplication.student_id == StudentProfile.student_id)
                             .filter(StudentProfile.current_section_id == class_managed.section_id)
                             .filter(LeaveApplication.status == 'Pending_CT')
                             .count())
            pending_leaves = [1] * pending_count

        detention_review_count = DetentionRecord.query.filter_by(assigned_by_staff_id=staff.staff_id, status='In_Review').count()

        # Pending adjustment requests for this staff as adjuster
        adjustment_requests = []
        try:
            pending_adjustments = (LoadAdjustment.query
                                   .filter_by(adjuster_id=staff.staff_id, status='Pending')
                                   .order_by(LoadAdjustment.created_at.desc())
                                   .all())
            requester_ids = list({a.requester_id for a in pending_adjustments})
            requester_map = {s.staff_id: s for s in StaffProfile.query.filter(StaffProfile.staff_id.in_(requester_ids)).all()} if requester_ids else {}
            schedule_ids = list({a.req_schedule_id for a in pending_adjustments} | {a.adj_schedule_id for a in pending_adjustments})
            schedule_map = {s.schedule_id: s for s in WeeklySchedule.query.filter(WeeklySchedule.schedule_id.in_(schedule_ids)).all()} if schedule_ids else {}

            for a in pending_adjustments:
                req_slot = schedule_map.get(a.req_schedule_id)
                adj_slot = schedule_map.get(a.adj_schedule_id)

                req_time = req_slot.start_time.strftime('%I:%M %p') if req_slot and req_slot.start_time else ''
                adj_time = adj_slot.start_time.strftime('%I:%M %p') if adj_slot and adj_slot.start_time else ''
                date_line = f"{a.req_date.strftime('%a %d %b')} {req_time} \u2194 {a.adj_date.strftime('%a %d %b')} {adj_time}".strip()

                requester = requester_map.get(a.requester_id)
                adjustment_requests.append({
                    "id": a.id,
                    "requester": requester.full_name if requester else a.requester_id,
                    "date": date_line
                })
        except Exception:
            adjustment_requests = []

        # --- 9. EXTRA SESSIONS (One-time classes) ---
        extra_sessions_list = []
        try:
            extra_sessions = (db.session.query(ExtraSession, Subject, ClassSection)
                              .join(Subject, ExtraSession.subject_id == Subject.subject_id)
                              .join(ClassSection, ExtraSession.section_id == ClassSection.section_id)
                              .filter(ExtraSession.teacher_id == staff.staff_id)
                              .filter(ExtraSession.status != 'Cancelled')
                              .filter(ExtraSession.date >= today_date)
                              .order_by(ExtraSession.date.asc(), ExtraSession.start_time.asc())
                              .all())

            for es, subj, sec in extra_sessions:
                session_log = SessionLog.query.filter_by(extra_session_id=es.id).first()
                start_float = es.start_time.hour + (es.start_time.minute / 60.0)
                end_float = es.end_time.hour + (es.end_time.minute / 60.0)
                days_from_today = (es.date - today_date).days
                sort_key = days_from_today * 10000 + int(es.start_time.strftime('%H%M'))

                es_data = {
                    "id": f"extra_{es.id}",
                    "extra_session_id": es.id,
                    "time": f"{es.start_time.strftime('%I:%M %p')} - {es.end_time.strftime('%I:%M %p')}",
                    "class": f"{sec.class_level}-{sec.name}",
                    "subject": subj.name,
                    "day": es.date.strftime('%A'),
                    "date_iso": es.date.strftime('%Y-%m-%d'),
                    "date_display": es.date.strftime('%d %b'),
                    "type": "Extra",
                    "topic": es.topic,
                    "meeting_link": es.meeting_link,
                    "sort_key": sort_key,
                    "start_float": start_float,
                    "duration_float": end_float - start_float,
                    "status": "Done" if session_log else "Pending",
                    "is_extra_session": True,
                    "section_id": sec.section_id
                }

                if es.date == today_date:
                    today_schedule.append(es_data)
                else:
                    upcoming_schedule.append(es_data)
                extra_sessions_list.append(es_data)

            # Re-sort after adding extra sessions
            today_schedule.sort(key=lambda x: x['sort_key'])
            upcoming_schedule.sort(key=lambda x: x['sort_key'])
        except Exception as ex:
            print(f"Error loading extra sessions: {ex}")

        return jsonify({
            "profile": {
                "name": staff.full_name,
                "code": staff.employee_code,
                "dept": dept_managed.name if is_hod else "Faculty",
                "stats": { "weekly_classes": weekly_load, "avg_attendance": f"{avg_attendance}%" }
            },
            "roles": {
                "is_hod": is_hod,
                "is_class_teacher": is_class_teacher,
                "is_coordinator": is_coordinator,
                "is_amc_member": is_amc_member,
                "is_amc_head": is_amc_head,
                "is_mentor": is_mentor
            },
            "widgets": {
                "today_schedule": today_schedule,
                "upcoming_schedule": upcoming_schedule,
                "history_schedule": history_list,
                "my_subjects": my_subjects_list,
                "pending_leaves": pending_leaves,
                "class_teacher_data": class_details,
                "mentee_data": {"count": mentee_count},
                "my_events": [],
                "detention_review_count": detention_review_count,
                "adjustment_requests": adjustment_requests,
                "can_assign_detention": can_assign_detention,
                "extra_sessions": extra_sessions_list
            }
        })
    except Exception as e:
        print(f"CRITICAL ERROR in Staff Dashboard: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/staff/find_adjustment_faculty', methods=['GET'])
@login_required
@require_roles('Staff')
def api_staff_find_adjustment_faculty():
    """Discovery phase for mutual swap system.

    Given a req_schedule_id and req_date, returns candidate adjusters who:
    - are allocated to the same class/section
    - are free at the requested slot time
    And for each adjuster returns their candidate swap slots (same class/section)
    that occur after req_date and where requester is free.
    """
    try:
        schedule_id_raw = request.args.get('schedule_id')
        req_date_raw = request.args.get('date')
        # Do not trust requester_id from client
        requester_id = current_user.user_id

        if not schedule_id_raw or not req_date_raw:
            return jsonify([]), 200

        req_schedule_id = int(schedule_id_raw)
        req_date = datetime.strptime(req_date_raw, '%Y-%m-%d').date()

        req_slot = WeeklySchedule.query.filter_by(schedule_id=req_schedule_id).first()
        if not req_slot:
            return jsonify([]), 200

        deny = _ensure_section_in_scope(int(req_slot.section_id))
        if deny:
            return jsonify([]), 200

        section = ClassSection.query.filter_by(section_id=req_slot.section_id).first()
        class_division = f"{section.class_level}-{section.name}" if section else str(req_slot.section_id)

        if not requester_id:
            requester_id = req_slot.teacher_id

        # Validate date matches the req slot weekday (prevents mismatched swaps)
        if req_date.strftime('%A') != req_slot.day_of_week:
            return jsonify([]), 200

        section_id = req_slot.section_id
        req_start = req_slot.start_time
        req_end = req_slot.end_time
        req_day = req_slot.day_of_week

        day_to_idx = {'Monday':0,'Tuesday':1,'Wednesday':2,'Thursday':3,'Friday':4,'Saturday':5,'Sunday':6}
        req_day_idx = day_to_idx.get(req_day, 0)

        def overlaps(a_start, a_end, b_start, b_end) -> bool:
            return a_start < b_end and b_start < a_end

        # Peers allocated to same class/section
        peer_rows = (db.session.query(SubjectAllocation.teacher_id)
                     .filter(SubjectAllocation.section_id == section_id)
                     .filter(SubjectAllocation.teacher_id != requester_id)
                     .distinct()
                     .all())
        peer_ids = [r[0] for r in peer_rows if r and r[0]]
        if not peer_ids:
            return jsonify([]), 200

        peer_profiles = {s.staff_id: s for s in StaffProfile.query.filter(StaffProfile.staff_id.in_(peer_ids)).all()}
        dept_ids = list({p.primary_department_id for p in peer_profiles.values() if getattr(p, 'primary_department_id', None)})
        dept_map = {d.dept_id: d for d in Department.query.filter(Department.dept_id.in_(dept_ids)).all()} if dept_ids else {}

        # Preload requester's schedule for conflict checks
        requester_slots = WeeklySchedule.query.filter_by(teacher_id=requester_id).all()

        def requester_is_free(day_name: str, start_t, end_t) -> bool:
            for s in requester_slots:
                if s.day_of_week != day_name:
                    continue
                if overlaps(start_t, end_t, s.start_time, s.end_time):
                    return False
            return True

        results = []
        for peer_id in peer_ids:
            # Check peer is FREE at req slot time
            peer_day_slots = WeeklySchedule.query.filter_by(teacher_id=peer_id, day_of_week=req_day).all()
            has_conflict = any(overlaps(req_start, req_end, s.start_time, s.end_time) for s in peer_day_slots)
            if has_conflict:
                continue

            # Candidate swap slots: peer's slots with SAME class/section
            peer_section_slots = WeeklySchedule.query.filter_by(teacher_id=peer_id, section_id=section_id).all()
            if not peer_section_slots:
                continue

            slot_subject_ids = list({s.subject_id for s in peer_section_slots if s and s.subject_id is not None})
            subject_map = {subj.subject_id: subj for subj in Subject.query.filter(Subject.subject_id.in_(slot_subject_ids)).all()} if slot_subject_ids else {}

            slots_payload = []
            for s in peer_section_slots:
                if s.schedule_id == req_schedule_id:
                    continue
                slot_day_idx = day_to_idx.get(s.day_of_week, 0)
                delta = (slot_day_idx - req_day_idx) % 7
                if delta == 0:
                    delta = 7
                slot_date = req_date + timedelta(days=delta)

                # requester must be free at this swap slot time
                if not requester_is_free(s.day_of_week, s.start_time, s.end_time):
                    continue

                subj = subject_map.get(s.subject_id)
                slots_payload.append({
                    'id': s.schedule_id,
                    'day': s.day_of_week,
                    'date_iso': slot_date.strftime('%Y-%m-%d'),
                    'date_display': slot_date.strftime('%d %b'),
                    'time': f"{s.start_time.strftime('%I:%M %p')} - {s.end_time.strftime('%I:%M %p')}",
                    'subject': subj.name if subj else 'Subject',
                })

            if not slots_payload:
                continue

            profile = peer_profiles.get(peer_id)
            dept_name = ''
            if profile and getattr(profile, 'primary_department_id', None) in dept_map:
                dept_name = dept_map[profile.primary_department_id].name

            results.append({
                'id': peer_id,
                'name': profile.full_name if profile else peer_id,
                'dept': dept_name or 'Faculty',
                'class_division': class_division,
                'slots': sorted(slots_payload, key=lambda x: x.get('date_iso', '')),
            })

        return jsonify(results), 200
    except Exception as e:
        print('find_adjustment_faculty error:', e)
        return jsonify([]), 200


@app.route('/api/staff/submit_adjustment', methods=['POST'])
@login_required
@require_roles('Staff')
def api_staff_submit_adjustment():
    try:
        data = request.get_json(force=True) or {}
        requester_id = current_user.user_id
        adjuster_id = data.get('substitute_id')
        req_schedule_id = int(data.get('schedule_id'))
        adj_schedule_id = int(data.get('swap_slot_id'))
        req_date = datetime.strptime(data.get('original_date'), '%Y-%m-%d').date()
        adj_date = datetime.strptime(data.get('compensation_date'), '%Y-%m-%d').date()
        reason = (data.get('reason') or '').strip() or None

        if not requester_id or not adjuster_id:
            return jsonify({'error': 'Missing requester_id/substitute_id'}), 400

        req_slot = WeeklySchedule.query.filter_by(schedule_id=req_schedule_id).first()
        adj_slot = WeeklySchedule.query.filter_by(schedule_id=adj_schedule_id).first()
        if not req_slot or not adj_slot:
            return jsonify({'error': 'Invalid slot id'}), 400

        deny = _ensure_section_in_scope(int(req_slot.section_id))
        if deny:
            return jsonify({'error': 'Out of scope'}), 403

        # Validate ownership
        if req_slot.teacher_id != requester_id:
            return jsonify({'error': 'Requester does not own requested slot'}), 400
        if adj_slot.teacher_id != adjuster_id:
            return jsonify({'error': 'Adjuster does not own swap slot'}), 400

        # Validate both slots are for the same class/section
        if req_slot.section_id != adj_slot.section_id:
            return jsonify({'error': 'Swap must be within same class/section'}), 400

        # Validate selected dates match slot weekdays
        if req_date.strftime('%A') != req_slot.day_of_week:
            return jsonify({'error': 'original_date does not match requested slot day'}), 400
        if adj_date.strftime('%A') != adj_slot.day_of_week:
            return jsonify({'error': 'compensation_date does not match swap slot day'}), 400

        # Prevent duplicates
        existing = (LoadAdjustment.query
                    .filter(LoadAdjustment.status.in_(['Pending', 'Approved']))
                    .filter(LoadAdjustment.req_date == req_date)
                    .filter(LoadAdjustment.req_schedule_id == req_schedule_id)
                    .first())
        if existing:
            return jsonify({'error': 'A request already exists for this slot/date'}), 409

        # Validate availability constraints (defensive)
        def overlaps(a_start, a_end, b_start, b_end) -> bool:
            return a_start < b_end and b_start < a_end

        # Adjuster must be free at req slot time on that weekday
        adjuster_day_slots = WeeklySchedule.query.filter_by(teacher_id=adjuster_id, day_of_week=req_slot.day_of_week).all()
        for s in adjuster_day_slots:
            if overlaps(req_slot.start_time, req_slot.end_time, s.start_time, s.end_time):
                return jsonify({'error': 'Adjuster is not free at requested time'}), 400

        # Requester must be free at swap slot time on that weekday
        requester_day_slots = WeeklySchedule.query.filter_by(teacher_id=requester_id, day_of_week=adj_slot.day_of_week).all()
        for s in requester_day_slots:
            if overlaps(adj_slot.start_time, adj_slot.end_time, s.start_time, s.end_time):
                return jsonify({'error': 'Requester is not free at swap time'}), 400

        rec = LoadAdjustment(
            requester_id=requester_id,
            adjuster_id=adjuster_id,
            req_date=req_date,
            req_schedule_id=req_schedule_id,
            adj_date=adj_date,
            adj_schedule_id=adj_schedule_id,
            status='Pending',
            reason=reason,
        )
        db.session.add(rec)
        db.session.commit()
        return jsonify({'message': 'created', 'id': rec.id}), 200
    except Exception as e:
        print('submit_adjustment error:', e)
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/staff/respond_adjustment', methods=['POST'])
@login_required
@require_roles('Staff')
def api_staff_respond_adjustment():
    try:
        data = request.get_json(force=True) or {}
        req_id = int(data.get('request_id'))
        status = (data.get('status') or '').strip()
        if status not in {'Approved', 'Rejected'}:
            return jsonify({'error': 'Invalid status'}), 400

        rec = LoadAdjustment.query.filter_by(id=req_id).first()
        if not rec:
            return jsonify({'error': 'Not found'}), 404

        # Only the adjuster can respond.
        if rec.adjuster_id != current_user.user_id:
            return jsonify({'error': 'Forbidden'}), 403

        rec.status = status
        db.session.commit()
        return jsonify({'message': 'updated'}), 200
    except Exception as e:
        print('respond_adjustment error:', e)
        db.session.rollback()
        return jsonify({'error': str(e)}), 500




# In app.py

# ==========================================
# API: STUDENT LEAVE MANAGEMENT (RESTORED)
# ==========================================

@app.route('/api/student/leaves', methods=['GET'])
@login_required
def get_student_leaves():
    try:
        user_id = request.args.get('user_id')
        
        # 1. Fetch Active Leaves (Approved + Pending)
        active_leaves = LeaveApplication.query.filter(
            LeaveApplication.student_id == user_id,
            LeaveApplication.status.in_(['Approved', 'Pending_CT', 'Pending_HOD'])
        ).all()
        
        # Calculate Used Days & Generate Blocked Date List
        used_days = 0
        blocked_dates = []
        
        for leave in active_leaves:
            used_days += leave.total_days
            # Generate list of dates between start and end
            curr = leave.start_date
            while curr <= leave.end_date:
                blocked_dates.append(curr.strftime('%Y-%m-%d'))
                curr += timedelta(days=1)
        
        # 2. Get Full History
        history = LeaveApplication.query.filter_by(student_id=user_id).order_by(LeaveApplication.start_date.desc()).all()
        
        history_list = []
        for leave in history:
            status_color = 'text-yellow-600 bg-yellow-50 border-yellow-200'
            if leave.status == 'Approved': status_color = 'text-green-600 bg-green-50 border-green-200'
            elif leave.status == 'Rejected': status_color = 'text-red-600 bg-red-50 border-red-200'

            clean_status = leave.status.replace('Pending_CT', 'Pending (CT)').replace('Pending_HOD', 'Pending (HOD)')
            
            # Format Date Range
            s_str = leave.start_date.strftime('%d %b')
            e_str = leave.end_date.strftime('%d %b %Y')
            date_display = f"{s_str} - {e_str}" if leave.start_date != leave.end_date else e_str

            history_list.append({ 
                "type": leave.leave_type or "General", 
                "days": leave.total_days, 
                "status": clean_status,
                "status_color": status_color,
                "date_display": date_display 
            })

        return jsonify({ 
            "balance": { "total": 20, "used": used_days, "remaining": max(0, 20 - used_days) }, 
            "history": history_list,
            "blocked_dates": blocked_dates # List of 'YYYY-MM-DD'
        })
    except Exception as e: 
        print(f"Error fetching student leaves: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/leave/apply', methods=['POST'])
@login_required
def apply_leave():
    try:
        data = request.json
        student_id = data.get('student_id')
        total_days = float(data.get('total_days'))
        start = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        end = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
        
        # Determine Routing
        initial_status = 'Pending_HOD' if total_days > 15 else 'Pending_CT'
        
        new_leave = LeaveApplication(
            student_id=student_id, 
            total_days=total_days, 
            start_date=start, 
            end_date=end, 
            reason=data.get('reason'), 
            status=initial_status, 
            leave_type=data.get('leave_type')
        )
        db.session.add(new_leave)
        db.session.flush() 
        
        # --- NOTIFICATION LOGIC (FIXED) ---
        student = StudentProfile.query.get(student_id)
        section = ClassSection.query.get(student.current_section_id)
        
        if total_days > 15:
            # Notify HOD
            # Logic: Find the department of the class teacher to find the HOD
            # (Assuming student belongs to the dept of their class teacher)
            if section.class_teacher_id:
                ct_profile = StaffProfile.query.get(section.class_teacher_id)
                if ct_profile and ct_profile.primary_department_id:
                    dept = Department.query.get(ct_profile.primary_department_id)
                    if dept and dept.hod_staff_id:
                        send_notification(
                            dept.hod_staff_id, 
                            "Long Leave Request", 
                            f"{student.full_name} applied for {total_days} days (Requires HOD Approval).", 
                            "warning", 
                            "/staff/hod_dashboard"
                        )
        else:
            # Notify Class Teacher
            if section and section.class_teacher_id:
                send_notification(
                    section.class_teacher_id, 
                    "New Leave Request", 
                    f"{student.full_name} applied for {total_days} days leave.", 
                    "info", 
                    "/staff/class_teacher_dashboard"
                )
        # ----------------------------------
            
        db.session.commit()
        return jsonify({"message": "Leave applied successfully", "status": initial_status}), 200

    except Exception as e: return jsonify({"error": str(e)}), 500
# ==========================================
# API: CLASS ANALYTICS
# ==========================================

# ==========================================
# API: HOD DASHBOARD
# ==========================================
@app.route('/staff/hod_dashboard')
def render_hod_dashboard():
    return render_template('hod_dashboard.html')

@app.route('/api/hod/dashboard', methods=['GET'])
@login_required
def get_hod_stats():
    try:
        user_id = request.args.get('user_id')
        
        # 1. Validate HOD
        dept = Department.query.filter_by(hod_staff_id=user_id).first()
        if not dept: return jsonify({"error": "Unauthorized: You are not an HOD"}), 403
        
        dept_id = dept.dept_id

        # 2. Get All Faculty in Dept (Active Only)
        # --- UPDATE: Join with UserMaster to filter is_active=True ---
        dept_faculty = (db.session.query(StaffProfile)
                        .join(UserMaster, StaffProfile.staff_id == UserMaster.user_id)
                        .filter(StaffProfile.primary_department_id == dept_id)
                        .filter(StaffProfile.full_name != "System Administrator")
                        .filter(UserMaster.is_active == True)  # <--- FILTER
                        .all())
        
        faculty_ids = [f.staff_id for f in dept_faculty]
        
        # 3. Get ALL Students
        total_students = StudentProfile.query.count()
        
        # 4. Faculty Performance List
        faculty_performance = []
        dept_avg_attendance_sum = 0
        active_faculty_count = 0
        
        today_name = datetime.now().strftime("%A")
        today_date = datetime.now().date()
        current_time = datetime.now().time()

        for f in dept_faculty:
            scheduled_slots = WeeklySchedule.query.filter_by(teacher_id=f.staff_id).all()
            total_load = len(scheduled_slots)
            
            missed_today = 0
            conducted_total = 0
            
            for slot in scheduled_slots:
                session_exists = SessionLog.query.filter_by(schedule_id=slot.schedule_id, session_date=today_date).first()
                if session_exists:
                    conducted_total += 1
                elif slot.day_of_week == today_name and current_time > slot.end_time:
                    missed_today += 1
            
            sessions = SessionLog.query.filter_by(actual_teacher_id=f.staff_id).all()
            s_ids = [s.session_id for s in sessions]
            avg = 0
            if s_ids:
                tot = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(s_ids)).count()
                pres = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(s_ids), AttendanceTransaction.status.in_(PRESENT_STATUSES)).count()
                if tot > 0: 
                    avg = round((pres/tot)*100, 1)
                    dept_avg_attendance_sum += avg
                    active_faculty_count += 1
            
            detention_count = DetentionRecord.query.filter_by(assigned_by_staff_id=f.staff_id).count()

            roles = []
            if f.is_event_coordinator: roles.append("Event Coord")
            if f.is_amc_member: roles.append("AMC Member")
            role_str = ", ".join(roles) if roles else "Faculty"
            
            # Student Reach
            section_ids = {s.section_id for s in scheduled_slots}
            student_reach = 0
            if section_ids:
                student_reach = StudentProfile.query.filter(StudentProfile.current_section_id.in_(section_ids)).count()

            # Risk Subject
            allocations = SubjectAllocation.query.filter_by(teacher_id=f.staff_id).all()
            lowest_att = 100; risk_subject_name = "None"
            for alloc in allocations:
                sub_sessions = db.session.query(SessionLog).join(WeeklySchedule).filter(WeeklySchedule.subject_id==alloc.subject_id, WeeklySchedule.section_id==alloc.section_id, SessionLog.actual_teacher_id==f.staff_id).all()
                sub_s_ids = [s.session_id for s in sub_sessions]
                if sub_s_ids:
                    sub_tot = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(sub_s_ids)).count()
                    sub_pres = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(sub_s_ids), AttendanceTransaction.status.in_(PRESENT_STATUSES)).count()
                    sub_avg = round((sub_pres/sub_tot)*100) if sub_tot > 0 else 0
                    if sub_avg < lowest_att:
                        lowest_att = sub_avg; risk_subject_name = f"{db.session.get(Subject, alloc.subject_id).name} ({sub_avg}%)"

            faculty_performance.append({
                "name": f.full_name, "code": f.employee_code,
                "load": total_load, "avg_att": avg,
                "is_critical": avg < 70 and total_load > 0,
                "missed_today": missed_today, "detentions": detention_count, "roles": role_str,
                "student_reach": student_reach, "risk_subject": risk_subject_name, "total_conducted": conducted_total
            })

        dept_avg = round(dept_avg_attendance_sum / active_faculty_count, 1) if active_faculty_count > 0 else 0

        # 5. Approvals
        approvals = []
        pending_leaves = (db.session.query(LeaveApplication, StudentProfile, ClassSection)
                          .join(StudentProfile, LeaveApplication.student_id == StudentProfile.student_id)
                          .outerjoin(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
                          .filter(LeaveApplication.status == 'Pending_HOD') 
                          .all())
            
        for l, s, c in pending_leaves:
            class_name = f"{c.class_level}-{c.name}" if c else "Unassigned"
            approvals.append({
                "leave_id": l.leave_id, "student": s.full_name, "roll": s.admission_number,
                "class": class_name, "days": l.total_days, "reason": l.reason,
                "date": l.start_date.strftime('%d %b')
            })

        # 6. Load Adjustment Monitor (date-wise)
        from sqlalchemy.orm import aliased

        ReqWS = aliased(WeeklySchedule)
        AdjWS = aliased(WeeklySchedule)
        ReqSub = aliased(Subject)
        AdjSub = aliased(Subject)
        ReqSec = aliased(ClassSection)
        AdjSec = aliased(ClassSection)
        ReqFac = aliased(StaffProfile)
        AdjFac = aliased(StaffProfile)

        adjustments_rows = (
            db.session.query(
                LoadAdjustment,
                ReqWS, AdjWS,
                ReqSub, AdjSub,
                ReqSec, AdjSec,
                ReqFac, AdjFac,
            )
            .join(ReqWS, LoadAdjustment.req_schedule_id == ReqWS.schedule_id)
            .join(AdjWS, LoadAdjustment.adj_schedule_id == AdjWS.schedule_id)
            .join(ReqSub, ReqWS.subject_id == ReqSub.subject_id)
            .join(AdjSub, AdjWS.subject_id == AdjSub.subject_id)
            .join(ReqSec, ReqWS.section_id == ReqSec.section_id)
            .join(AdjSec, AdjWS.section_id == AdjSec.section_id)
            .join(ReqFac, LoadAdjustment.requester_id == ReqFac.staff_id)
            .join(AdjFac, LoadAdjustment.adjuster_id == AdjFac.staff_id)
            .filter(
                (ReqSub.dept_id == dept_id) |
                (AdjSub.dept_id == dept_id) |
                (ReqFac.primary_department_id == dept_id) |
                (AdjFac.primary_department_id == dept_id)
            )
            .order_by(LoadAdjustment.req_date.desc(), LoadAdjustment.created_at.desc())
            .limit(200)
            .all()
        )

        def _fmt_time_range(ws: WeeklySchedule) -> str:
            if not ws or not ws.start_time or not ws.end_time:
                return "-"
            return f"{ws.start_time.strftime('%H:%M')} - {ws.end_time.strftime('%H:%M')}"

        def _fmt_date_display(d):
            if not d:
                return "-"
            try:
                return d.strftime('%a %d %b')
            except Exception:
                return str(d)

        load_adjustments = []
        for la, req_ws, adj_ws, req_sub, adj_sub, req_sec, adj_sec, req_fac, adj_fac in adjustments_rows:
            req_class = f"{req_sec.class_level}-{req_sec.name}" if req_sec else "-"
            adj_class = f"{adj_sec.class_level}-{adj_sec.name}" if adj_sec else "-"

            load_adjustments.append({
                "id": la.id,
                "status": la.status,
                "reason": la.reason,
                "created_at_iso": la.created_at.isoformat() if getattr(la, 'created_at', None) else None,
                "created_at_display": la.created_at.strftime('%d %b %H:%M') if getattr(la, 'created_at', None) else None,
                "class_division": req_class,
                "requester": {
                    "id": req_fac.staff_id,
                    "name": req_fac.full_name,
                    "code": req_fac.employee_code,
                },
                "adjuster": {
                    "id": adj_fac.staff_id,
                    "name": adj_fac.full_name,
                    "code": adj_fac.employee_code,
                },
                "requested": {
                    "date_iso": la.req_date.isoformat() if la.req_date else None,
                    "date_display": _fmt_date_display(la.req_date),
                    "day": req_ws.day_of_week if req_ws else None,
                    "time": _fmt_time_range(req_ws),
                    "subject": req_sub.name if req_sub else "-",
                    "subject_code": req_sub.code if req_sub else "-",
                    "schedule_id": req_ws.schedule_id if req_ws else None,
                    "class_division": req_class,
                },
                "swap": {
                    "date_iso": la.adj_date.isoformat() if la.adj_date else None,
                    "date_display": _fmt_date_display(la.adj_date),
                    "day": adj_ws.day_of_week if adj_ws else None,
                    "time": _fmt_time_range(adj_ws),
                    "subject": adj_sub.name if adj_sub else "-",
                    "subject_code": adj_sub.code if adj_sub else "-",
                    "schedule_id": adj_ws.schedule_id if adj_ws else None,
                    "class_division": adj_class,
                },
            })

        return jsonify({
            "dept_name": dept.name,
            "stats": { "students": total_students, "faculty": len(dept_faculty), "attendance": dept_avg, "pending": len(approvals) },
            "faculty_list": faculty_performance,
            "approvals": approvals,
            "load_adjustments": load_adjustments,
        })

    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/hod/faculty_roles', methods=['GET'])
@login_required
def get_hod_faculty_roles():
    try:
        user_id = request.args.get('user_id')
        dept = Department.query.filter_by(hod_staff_id=user_id).first()
        if not dept: return jsonify({"error": "Unauthorized"}), 403
        
        # --- UPDATE: Filter Active Faculty ---
        faculty = (db.session.query(StaffProfile)
                   .join(UserMaster, StaffProfile.staff_id == UserMaster.user_id)
                   .filter(StaffProfile.primary_department_id == dept.dept_id)
                   .filter(StaffProfile.full_name != "System Administrator")
                   .filter(UserMaster.is_active == True) # <--- FILTER
                   .all())
        
        role_breakdown = { "Class Teachers": [], "Mentors": [], "AMC Team": [], "Event Coordinators": [], "Unassigned": [] }
        
        for f in faculty:
            has_role = False
            # Class Teacher
            ct_class = ClassSection.query.filter_by(class_teacher_id=f.staff_id).first()
            if ct_class:
                role_breakdown["Class Teachers"].append({ "name": f.full_name, "detail": f"{ct_class.class_level} - Division {ct_class.name}" })
                has_role = True
            # Mentor
            mentor_batches = MentorBatch.query.filter_by(mentor_id=f.staff_id).all()
            if mentor_batches:
                batch_details = []
                for b in mentor_batches:
                    section = db.session.get(ClassSection, b.section_id)
                    if section: batch_details.append(f"{section.class_level}-{section.name} ({b.batch_name})")
                role_breakdown["Mentors"].append({ "name": f.full_name, "detail": ", ".join(batch_details) })
                has_role = True
            # AMC
            if f.is_amc_member or f.is_amc_head:
                role = "Head" if f.is_amc_head else "Member"
                role_breakdown["AMC Team"].append({ "name": f.full_name, "detail": f"Role: {role}" }); has_role = True
            # Event
            if f.is_event_coordinator:
                role_breakdown["Event Coordinators"].append({ "name": f.full_name, "detail": "University Events" }); has_role = True
            
            if not has_role:
                role_breakdown["Unassigned"].append({ "name": f.full_name, "detail": "No administrative role" })
                
        return jsonify(role_breakdown)
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/hod/student_hierarchy', methods=['GET'])
@login_required
def get_hod_student_hierarchy():
    try:
        # Fetch all sections
        sections = ClassSection.query.order_by(ClassSection.class_level, ClassSection.name).all()
        
        hierarchy = {}
        
        for sec in sections:
            lvl = sec.class_level
            if lvl not in hierarchy: hierarchy[lvl] = []
            
            # Count Active Students in this section
            count = StudentProfile.query.filter_by(current_section_id=sec.section_id, academic_status='Active').count()
            
            hierarchy[lvl].append({
                "id": sec.section_id,
                "name": sec.name,
                "count": count
            })
            
        return jsonify(hierarchy)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/hod/approve_leave', methods=['POST'])
@login_required
def hod_approve_leave():
    try:
        data = request.json
        leave = LeaveApplication.query.get(data.get('leave_id'))
        if not leave: return jsonify({"error": "Not found"}), 404
        
        leave.status = data.get('action') # Approved / Rejected
        
        # Log
        log = LeaveWorkflowLog(leave_id=leave.leave_id, action_by_user_id=data.get('hod_id'), action=f"HOD {data.get('action')}")
        db.session.add(log)

        # NOTIFY STUDENT (and parent via push fan-out)
        msg_type = "success" if leave.status == "Approved" else "danger"
        send_notification(
            leave.student_id,
            f"Leave {leave.status}",
            f"Your leave request has been {leave.status}.",
            msg_type,
            "/student/dashboard",
        )

        db.session.commit()
        
        return jsonify({"message": "Updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/admin/assign_hod', methods=['POST'])
@login_required
@require_roles('Admin')
def assign_hod():
    try:
        data = request.json
        staff_id = data.get('staff_id')
        dept_name = data.get('dept_name') # Optional if we just use staff's dept
        
        staff = StaffProfile.query.get(staff_id)
        if not staff: return jsonify({"error": "Staff not found"}), 404
        
        # Find Dept
        dept = Department.query.get(staff.primary_department_id)
        if not dept: return jsonify({"error": "Staff has no department assigned"}), 400
        
        # Assign
        dept.hod_staff_id = staff_id
        db.session.commit()
        
        log_activity("Role Update", f"Assigned {staff.full_name} as HOD of {dept.name}")
        return jsonify({"message": f"Success! {staff.full_name} is now HOD."}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/class_teacher/analytics', methods=['GET'])
@login_required
def get_class_analytics():
    try:
        user_id = request.args.get('user_id')
        # Prevent data leakage via user_id spoofing
        if user_id and str(user_id) != str(getattr(current_user, 'user_id', '')):
            return jsonify({"error": "Forbidden"}), 403

        user_id = str(getattr(current_user, 'user_id', user_id))
        class_managed = ClassSection.query.filter_by(class_teacher_id=user_id).first()
        if not class_managed: return jsonify({"error": "No class assigned"}), 404

        students = StudentProfile.query.filter_by(current_section_id=class_managed.section_id).all()
        
        # Subject Analysis
        schedule_slots = WeeklySchedule.query.filter_by(section_id=class_managed.section_id).all()
        unique_subject_ids = set(slot.subject_id for slot in schedule_slots)
        
        subject_stats = []
        for sub_id in unique_subject_ids:
            subject = db.session.get(Subject, sub_id)
            if not subject: continue
            slot = WeeklySchedule.query.filter_by(section_id=class_managed.section_id, subject_id=sub_id).first()
            teacher_name = db.session.get(StaffProfile, slot.teacher_id).full_name if slot else "Unknown"

            conducted = (db.session.query(SessionLog)
                         .join(WeeklySchedule)
                         .filter(WeeklySchedule.subject_id == sub_id, WeeklySchedule.section_id == class_managed.section_id, SessionLog.status == 'Conducted').count())
            
            avg_sub_att = 0
            if conducted > 0 and len(students) > 0:
                sub_session_ids = [s.session_id for s in SessionLog.query.join(WeeklySchedule).filter(WeeklySchedule.subject_id == sub_id, WeeklySchedule.section_id == class_managed.section_id).all()]
                total_presents = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(sub_session_ids), AttendanceTransaction.status.in_(PRESENT_STATUSES)).count()
                avg_sub_att = round((total_presents / (len(students) * conducted)) * 100, 1)

            subject_stats.append({ "id": sub_id, "subject": subject.name, "teacher": teacher_name, "conducted": conducted, "avg_attendance": avg_sub_att })

        defaulters = []
        top_students = []
        total_class_sessions = (db.session.query(SessionLog).join(WeeklySchedule).filter(WeeklySchedule.section_id == class_managed.section_id, SessionLog.status == 'Conducted').count())

        if total_class_sessions > 0:
            for s in students:
                attended = AttendanceTransaction.query.filter(AttendanceTransaction.student_id == s.student_id, AttendanceTransaction.status.in_(PRESENT_STATUSES)).count()
                perc = round((attended / total_class_sessions) * 100, 1)
                s_data = { "name": s.full_name, "roll": s.admission_number, "perc": perc, "attended": attended, "total": total_class_sessions }
                if perc < 75: defaulters.append(s_data)
                if perc > 90: top_students.append(s_data)

        pending_leaves_count = LeaveApplication.query.join(StudentProfile).filter(StudentProfile.current_section_id == class_managed.section_id, LeaveApplication.status == 'Pending_CT').count()

        # Alerts: approved leave history + students in events (today + all)
        today = date.today()

        approved_leave_rows = (
            db.session.query(LeaveApplication, StudentProfile)
            .join(StudentProfile, LeaveApplication.student_id == StudentProfile.student_id)
            .filter(StudentProfile.current_section_id == class_managed.section_id)
            .filter(LeaveApplication.status == 'Approved')
            .order_by(LeaveApplication.start_date.desc(), LeaveApplication.leave_id.desc())
            .limit(30)
            .all()
        )
        approved_leave_history = []
        for leave, student in approved_leave_rows:
            approved_leave_history.append({
                "leave_id": leave.leave_id,
                "student_id": student.student_id,
                "student_name": student.full_name,
                "roll_no": student.admission_number,
                "leave_type": leave.leave_type or "General",
                "days": leave.total_days,
                "start_date": leave.start_date.isoformat() if leave.start_date else None,
                "end_date": leave.end_date.isoformat() if leave.end_date else None,
                "date_range": f"{leave.start_date.strftime('%d %b')} - {leave.end_date.strftime('%d %b')}" if (leave.start_date and leave.end_date) else "",
                "reason": leave.reason,
            })

        # NOTE: We return both:
        # - out_for_events_today: students currently out today due to an event
        # - out_for_events_all: students with any non-cancelled event participation (past/upcoming)
        # To keep payload size reasonable, we cap participation rows.
        MAX_EVENT_PARTICIPATION_ROWS = 500

        participation_rows = (
            db.session.query(EventParticipation, EventMaster, StudentProfile)
            .join(EventMaster, EventParticipation.event_id == EventMaster.event_id)
            .join(StudentProfile, EventParticipation.student_id == StudentProfile.student_id)
            .filter(StudentProfile.current_section_id == class_managed.section_id)
            .order_by(EventMaster.start_date.desc(), EventMaster.event_id.desc())
            .limit(MAX_EVENT_PARTICIPATION_ROWS)
            .all()
        )

        out_all_map = {}
        out_today_map = {}

        for part, event, student in participation_rows:
            raw_status = (getattr(part, 'status', '') or '').strip()
            status_norm = raw_status.lower()
            if status_norm in {'cancelled', 'canceled', 'rejected'}:
                continue

            sid = student.student_id
            event_payload = {
                "event_id": event.event_id,
                "event_name": event.event_name,
                "status": raw_status or 'Nominated',
                "start_date": event.start_date.isoformat() if event.start_date else None,
                "end_date": event.end_date.isoformat() if event.end_date else None,
                "date_range": f"{event.start_date.strftime('%d %b')} - {event.end_date.strftime('%d %b')}" if (event.start_date and event.end_date) else "",
            }

            if sid not in out_all_map:
                out_all_map[sid] = {
                    "student_id": sid,
                    "student_name": student.full_name,
                    "roll_no": student.admission_number,
                    "events": [],
                }
            out_all_map[sid]["events"].append(event_payload)

            if event.start_date and event.end_date and (event.start_date <= today <= event.end_date):
                if sid not in out_today_map:
                    out_today_map[sid] = {
                        "student_id": sid,
                        "student_name": student.full_name,
                        "roll_no": student.admission_number,
                        "events": [],
                    }
                out_today_map[sid]["events"].append(event_payload)

        out_for_events_today = list(out_today_map.values())
        out_for_events_today.sort(key=lambda x: (x.get('roll_no') or '', x.get('student_name') or ''))

        out_for_events_all = list(out_all_map.values())
        out_for_events_all.sort(key=lambda x: (x.get('roll_no') or '', x.get('student_name') or ''))

        return jsonify({
            "class_info": { "name": f"{class_managed.class_level} - {class_managed.name}", "total_students": len(students), "total_sessions": total_class_sessions },
            "summary": { "defaulter_count": len(defaulters), "pending_leaves": pending_leaves_count, "class_health": "Good" if len(defaulters) < (len(students)*0.2) else "At Risk" },
            "subjects": subject_stats,
            "defaulters": sorted(defaulters, key=lambda x: x['perc']),
            "top_students": sorted(top_students, key=lambda x: x['perc'], reverse=True)[:5],
            "alerts": {
                "approved_leave_history": approved_leave_history,
                "out_for_events_today": out_for_events_today,
                "out_for_events_all": out_for_events_all,
                "as_of": today.isoformat(),
            },
        })
    except Exception as e: return jsonify({"error": str(e)}), 500




# ==========================================
# HELPER: IS STUDENT IN BATCH?
# ==========================================
def is_student_in_batch(student, batch_name):
    """
    Returns True if the student belongs to the target batch 
    (e.g., 'Batch A') or if the session has no batch (Lecture).
    """
    if not batch_name: return True # Lecture (Everyone)
    
    # Get Student's Batch Name via MentorBatch
    if student.mentor_batch_id:
        my_batch = db.session.get(MentorBatch, student.mentor_batch_id)
        if my_batch and my_batch.batch_name == batch_name:
            return True
            
    return False



@app.route('/api/class_teacher/subject_report', methods=['GET'])
@login_required
def get_subject_report():
    try:
        user_id = request.args.get('user_id')
        subject_id = request.args.get('subject_id')
        section_id_param = request.args.get('section_id')
        
        # 1. Determine Context
        class_managed = ClassSection.query.filter_by(class_teacher_id=user_id).first()
        target_section_id = section_id_param if section_id_param else (class_managed.section_id if class_managed else None)
        if not target_section_id: return jsonify({"error": "Context Missing"}), 400

        # 2. Auth Check (CT or Subject Teacher)
        is_ct = (class_managed and str(class_managed.section_id) == str(target_section_id))
        is_st = SubjectAllocation.query.filter_by(section_id=target_section_id, subject_id=subject_id, teacher_id=user_id).first()
        if not (is_ct or is_st): return jsonify({"error": "Unauthorized"}), 403

        subject = db.session.get(Subject, subject_id)
        section = db.session.get(ClassSection, target_section_id)
        
        # 3. FETCH STUDENTS (Smart Filter)
        # --- FIX: ROBUST ELECTIVE CHECK ---
        # If Subject Type contains "Elective", treat as elective
        if is_elective_type(subject.subject_type):
            students = (db.session.query(StudentProfile)
                        .join(StudentElective, StudentProfile.student_id == StudentElective.student_id)
                        .filter(StudentProfile.current_section_id == target_section_id)
                        .filter(StudentElective.subject_id == subject_id)
                        .filter(StudentElective.status == 'Approved')
                        .order_by(StudentProfile.admission_number).all())
        else:
            # Core = Whole Class
            students = StudentProfile.query.filter_by(current_section_id=target_section_id).order_by(StudentProfile.admission_number).all()

        # 4. Get Sessions
        sessions = (db.session.query(SessionLog, WeeklySchedule.target_batch)
                    .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                    .filter(WeeklySchedule.subject_id == subject_id)
                    .filter(WeeklySchedule.section_id == target_section_id)
                    .filter(SessionLog.status == 'Conducted')
                    .order_by(SessionLog.session_date)
                    .all())
        
        headers = [s.session_date.strftime('%d/%m') for s, b in sessions]
        session_ids = [s.session_id for s, b in sessions]
        
        transactions = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(session_ids)).all()
        txn_map = {(t.student_id, t.session_id): t.status for t in transactions}

        rows = []
        for s in students:
            record = []
            present_count = 0
            valid_sessions = 0
            
            # Batch Check Logic
            my_batch = None
            if s.mentor_batch_id:
                mb = db.session.get(MentorBatch, s.mentor_batch_id)
                if mb: my_batch = mb.batch_name

            for sess, target_batch in sessions:
                # Apply Session if Lecture OR Batch Matches
                if not target_batch or target_batch == my_batch:
                    valid_sessions += 1
                    status = txn_map.get((s.student_id, sess.session_id), "Absent")
                    char = "A"
                    if status == "Present": char="P"; present_count+=1
                    elif status == "OnDuty": char="OD"; present_count+=1
                    record.append(char)
                else:
                    record.append("-") # Not applicable for this batch
            
            perc = round((present_count / valid_sessions) * 100) if valid_sessions > 0 else 0
            rows.append({ 
                "roll": s.admission_number, 
                "name": s.full_name, 
                "record": record, 
                "total": f"{present_count}/{valid_sessions}", 
                "perc": perc 
            })

        dept = db.session.get(Department, subject.dept_id) if subject.dept_id else None
        slot = SubjectAllocation.query.filter_by(section_id=target_section_id, subject_id=subject_id).first()
        teacher_name = "Unknown"
        if slot:
             t = db.session.get(StaffProfile, slot.teacher_id)
             if t: teacher_name = t.full_name
        
        current_term = get_current_term_name()
        if ' Sem' in current_term:
            year_str = current_term.split(' Sem')[0]
            sem_str = 'Sem ' + current_term.split('Sem')[-1].strip()
        else:
            today = date.today()
            year_str = f"{today.year}-{today.year+1}" if today.month > 6 else f"{today.year-1}-{today.year}"
            sem_str = "Sem"

        return jsonify({ 
            "meta": {
                "department": dept.name if dept else "General",
                "class_div": f"{section.class_level} - {section.name}",
                "strength": len(students),
                "teacher": teacher_name,
                "subject": subject.name,
                "code": subject.code,
                "year": year_str,
                "semester": sem_str
            },
            "dates": headers, "rows": rows
        })
    except Exception as e: 
        print(f"Report Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/class_teacher/overall_summary', methods=['GET'])
@login_required
def get_class_overall_summary():
    try:
        user_id = request.args.get('user_id')
        class_managed = ClassSection.query.filter_by(class_teacher_id=user_id).first()
        if not class_managed: return jsonify({"error": "Unauthorized"}), 401
        section_id = class_managed.section_id
        
        slots = (db.session.query(WeeklySchedule, Subject).join(Subject).filter(WeeklySchedule.section_id == section_id).all())
        unique_subjects = {subj.subject_id: {"id": subj.subject_id, "name": subj.name, "code": subj.code, "type": subj.subject_type} for slot, subj in slots}.values()
        sorted_subjects = sorted(list(unique_subjects), key=lambda x: x['name'])
        
        students = StudentProfile.query.filter_by(current_section_id=section_id).order_by(StudentProfile.admission_number).all()
        
        # Pre-fetch elective choices
        elective_map = {(c.student_id, c.subject_id): True for c in db.session.query(StudentElective).filter_by(status='Approved').all()}

        rows = []
        for s in students:
            my_batch = db.session.get(MentorBatch, s.mentor_batch_id).batch_name if s.mentor_batch_id else None
            cols = []; cond_all = 0; att_all = 0
            
            for sub in sorted_subjects:
                # --- FIX: ROBUST CHECK ---
                if is_elective_type(sub['type']):
                     if (s.student_id, sub['id']) not in elective_map:
                         cols.append("-"); continue
                # -------------------------

                sessions = db.session.query(SessionLog, WeeklySchedule.target_batch).join(WeeklySchedule).filter(WeeklySchedule.subject_id==sub['id'], WeeklySchedule.section_id==section_id, SessionLog.status=='Conducted').all()
                valid_sids = [sess.session_id for sess, batch in sessions if not batch or batch == my_batch]
                
                cond = len(valid_sids)
                att = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(valid_sids), AttendanceTransaction.student_id==s.student_id, AttendanceTransaction.status.in_(PRESENT_STATUSES)).count() if cond > 0 else 0
                
                cond_all += cond; att_all += att
                cols.append(f"{round((att/cond)*100) if cond > 0 else 0}%")
            
            cum_perc = round((att_all/cond_all)*100, 1) if cond_all > 0 else 0
            rows.append({ "roll": s.admission_number, "name": s.full_name, "subjects": cols, "total_conducted": cond_all, "total_attended": att_all, "cumulative_perc": cum_perc })
        current_term = get_current_term_name()
        return jsonify({ "headers": sorted_subjects, "rows": rows, "meta": { "class_name": f"{class_managed.class_level}-{class_managed.name}", "teacher": "CT", "year": current_term } })
    except Exception as e: return jsonify({"error": str(e)}), 500
# ==========================================
# API: ATTENDANCE SHEET & SUBMIT (SMART)
# ==========================================
@app.route('/api/attendance/sheet', methods=['GET'])
@login_required
def get_attendance_sheet():
    try:
        schedule_id = request.args.get('schedule_id')
        date_str = request.args.get('date')
        if date_str: target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else: target_date = date.today()

        # Check if this is an extra session (ID starts with "extra_")
        is_extra_session = schedule_id and schedule_id.startswith('extra_')

        if is_extra_session:
            # Handle Extra Session
            extra_session_id = int(schedule_id.replace('extra_', ''))
            extra_session = ExtraSession.query.get(extra_session_id)
            if not extra_session: return jsonify({"error": "Invalid Extra Session ID"}), 404

            subject = Subject.query.get(extra_session.subject_id)
            section = ClassSection.query.get(extra_session.section_id)

            # Fetch students - apply elective filter if subject is elective type
            if is_elective_type(subject.subject_type):
                # Only students with approved elective selection for this subject
                students = (db.session.query(StudentProfile)
                            .join(StudentElective, StudentProfile.student_id == StudentElective.student_id)
                            .filter(StudentProfile.current_section_id == section.section_id)
                            .filter(StudentElective.subject_id == subject.subject_id)
                            .filter(StudentElective.status == 'Approved')
                            .order_by(StudentProfile.admission_number).all())
            else:
                # Core subject = all students in section
                students = StudentProfile.query.filter_by(current_section_id=section.section_id).all()

            # Check existing session log for extra session
            existing_session = SessionLog.query.filter_by(extra_session_id=extra_session_id).first()
            is_locked = True if existing_session else False
            saved_status_map = {t.student_id: t.status for t in AttendanceTransaction.query.filter_by(session_id=existing_session.session_id).all()} if existing_session else {}

            # Store for later use in response
            slot = None
            time_str = f"{extra_session.start_time.strftime('%I:%M %p')} - {extra_session.end_time.strftime('%I:%M %p')}"
            display_class_name = f"{section.class_level}-{section.name}"
            target_date = extra_session.date  # Use the extra session's date
        else:
            # Handle Regular Weekly Schedule
            slot = WeeklySchedule.query.get(schedule_id)
            if not slot: return jsonify({"error": "Invalid Slot ID"}), 404
            subject = Subject.query.get(slot.subject_id)
            section = ClassSection.query.get(slot.section_id)

            # 1. Fetch Students (Batch, Elective, or Class)
            students = []
            if is_elective_type(subject.subject_type):
                # Elective subject = only students with approved selection
                base_query = (db.session.query(StudentProfile)
                              .join(StudentElective, StudentProfile.student_id == StudentElective.student_id)
                              .filter(StudentProfile.current_section_id == section.section_id)
                              .filter(StudentElective.subject_id == subject.subject_id)
                              .filter(StudentElective.status == 'Approved'))
                if slot.target_batch:
                    target_batch_obj = MentorBatch.query.filter_by(section_id=section.section_id, batch_name=slot.target_batch).first()
                    if target_batch_obj:
                        base_query = base_query.filter(StudentProfile.mentor_batch_id == target_batch_obj.batch_id)
                students = base_query.order_by(StudentProfile.admission_number).all()
            elif slot.target_batch:
                # Batch-specific (lab sessions)
                target_batch_obj = MentorBatch.query.filter_by(section_id=section.section_id, batch_name=slot.target_batch).first()
                if target_batch_obj: students = StudentProfile.query.filter_by(current_section_id=section.section_id, mentor_batch_id=target_batch_obj.batch_id).all()
            else:
                # Core subject = all students in section
                students = StudentProfile.query.filter_by(current_section_id=section.section_id).all()

            # 2. Check Existing Session (Locked State)
            existing_session = SessionLog.query.filter_by(schedule_id=schedule_id, session_date=target_date).first()
            is_locked = True if existing_session else False
            saved_status_map = {t.student_id: t.status for t in AttendanceTransaction.query.filter_by(session_id=existing_session.session_id).all()} if existing_session else {}

            time_str = f"{slot.start_time.strftime('%I:%M %p')} - {slot.end_time.strftime('%I:%M %p')}"
            display_class_name = f"{section.class_level}-{section.name}"
            if slot.target_batch: display_class_name += f" ({slot.target_batch})"

        # 3. Pre-fetch Approved Leaves & Events for this Date
        # Optimization: Fetch all approved leaves for this section on this date
        active_leaves = (db.session.query(LeaveApplication)
                         .join(StudentProfile)
                         .filter(StudentProfile.current_section_id == section.section_id)
                         .filter(LeaveApplication.status == 'Approved')
                         .filter(LeaveApplication.start_date <= target_date)
                         .filter(LeaveApplication.end_date >= target_date)
                         .all())
        
        # Map: student_id -> leave_type_code
        leave_map = {}
        for l in active_leaves:
            code = 'OD'
            if l.leave_type == 'Sick': code = 'ML'
            elif l.leave_type == 'Casual': code = 'CL'
            leave_map[l.student_id] = code

        # Pre-fetch Events (OD)
        active_events = (db.session.query(EventParticipation)
                         .join(EventMaster)
                         .join(StudentProfile)
                         .filter(StudentProfile.current_section_id == section.section_id)
                         .filter(EventParticipation.status == 'Attended')
                         .filter(EventMaster.start_date <= target_date)
                         .filter(EventMaster.end_date >= target_date)
                         .all())
        
        event_map = {}
        for ep in active_events:
            # Time conflict check could be added here, assuming full day OD for simplicity
            event_map[ep.student_id] = 'OD'

        # 4. Build Student List
        student_list = []
        for s in students:
            # Determine Status Priority:
            # 1. Saved Status (if locked)
            # 2. Event OD
            # 3. Approved Leave (ML/CL)
            # 4. Default "Present"
            
            status = "Present"
            is_od = False
            status_label = ""

            if is_locked:
                status = saved_status_map.get(s.student_id, "Present")
            else:
                if s.student_id in event_map:
                    status = 'OnDuty'
                    is_od = True
                    status_label = "Event OD"
                elif s.student_id in leave_map:
                    # Auto-mark as ML/CL/OD based on leave type
                    # In our DB we store 'OnDuty', 'Present', 'Absent'. 
                    # We can store 'ML' or 'CL' directly if the system supports it, 
                    # OR map them to 'OnDuty'/Absent with a label.
                    # Let's store the specific code for better reporting.
                    status = leave_map[s.student_id] 
                    status_label = f"Approved {status}"

            student_list.append({
                "student_id": s.student_id,
                "name": s.full_name,
                "roll_no": s.admission_number,
                "status": status,
                "is_on_duty": is_od,
                "status_label": status_label # Hint for UI
            })
        
        student_list.sort(key=lambda x: x['name'])

        return jsonify({
            "subject_name": subject.name, "class_name": display_class_name,
            "time": time_str, "date_display": target_date.strftime('%d %b %Y'),
            "is_locked": is_locked, "students": student_list, "subject_id": subject.subject_id,
            "is_extra_session": is_extra_session
        })

    except Exception as e:
        print(f"CRITICAL ERROR in get_attendance_sheet: {str(e)}")
        return jsonify({"error": str(e)}), 500



@app.route('/api/attendance/submit', methods=['POST'])
@login_required
def submit_attendance():
    try:
        data = request.json
        schedule_id = data.get('schedule_id')
        txn_date = datetime.strptime(data.get('date'), '%Y-%m-%d').date()

        submitted_by = data.get('submitted_by')

        # 1. Lesson Data - Support both single topic_id (legacy) and topic_ids array (new)
        topic_ids = data.get('topic_ids') or []  # New: array of topic IDs
        legacy_topic_id = data.get('topic_id')  # Legacy: single topic ID
        if legacy_topic_id and not topic_ids:
            topic_ids = [legacy_topic_id]  # Convert legacy to array format

        # Check if this is an extra session (ID starts with "extra_")
        is_extra_session = schedule_id and str(schedule_id).startswith('extra_')

        if is_extra_session:
            # Handle Extra Session
            extra_session_id = int(str(schedule_id).replace('extra_', ''))
            extra_session = ExtraSession.query.get(extra_session_id)
            if not extra_session:
                return jsonify({"error": "Invalid Extra Session"}), 404

            # Check if already marked
            existing_session = SessionLog.query.filter_by(extra_session_id=extra_session_id).first()
            if existing_session:
                return jsonify({"error": "Attendance locked."}), 403

            # For extra sessions, only the teacher who created it can mark attendance
            if extra_session.teacher_id != submitted_by:
                return jsonify({"error": "Not allowed to submit attendance for this session."}), 403

            # Create session log for extra session
            session = SessionLog(
                extra_session_id=extra_session_id,
                session_date=extra_session.date,
                status="Conducted",
                actual_teacher_id=submitted_by
            )
            db.session.add(session)
            db.session.flush()

        else:
            # Handle Regular Weekly Schedule
            existing_session = SessionLog.query.filter_by(schedule_id=schedule_id, session_date=txn_date).first()
            if existing_session: return jsonify({"error": "Attendance locked."}), 403
            slot = WeeklySchedule.query.get(schedule_id)

            # Determine who is allowed to submit attendance for this schedule/date.
            # - Default: scheduled teacher can submit.
            # - If there's an approved mutual swap for this schedule/date, only the swapped-in teacher can submit.
            allowed_teacher_id = slot.teacher_id if slot else None
            try:
                approved_swap = (
                    LoadAdjustment.query
                    .filter(LoadAdjustment.status == 'Approved')
                    .filter(
                        ((LoadAdjustment.req_schedule_id == schedule_id) & (LoadAdjustment.req_date == txn_date)) |
                        ((LoadAdjustment.adj_schedule_id == schedule_id) & (LoadAdjustment.adj_date == txn_date))
                    )
                    .order_by(LoadAdjustment.created_at.desc())
                    .first()
                )
                if approved_swap:
                    if approved_swap.req_schedule_id == schedule_id and approved_swap.req_date == txn_date:
                        allowed_teacher_id = approved_swap.adjuster_id
                    elif approved_swap.adj_schedule_id == schedule_id and approved_swap.adj_date == txn_date:
                        allowed_teacher_id = approved_swap.requester_id
            except Exception:
                pass

            actual_teacher_id = submitted_by or allowed_teacher_id
            if allowed_teacher_id and actual_teacher_id != allowed_teacher_id:
                return jsonify({"error": "Not allowed to submit attendance for this session."}), 403

            session = SessionLog(schedule_id=schedule_id, session_date=txn_date, status="Conducted", actual_teacher_id=actual_teacher_id)
            db.session.add(session)
            db.session.flush()

        for s in data.get('students'):
            final_status = "OnDuty" if s['is_on_duty'] else s['status']
            new_txn = AttendanceTransaction(session_id=session.session_id, student_id=s['student_id'], status=final_status)
            db.session.add(new_txn)

        # 5. Save Lesson Log(s) - only for regular sessions with topics
        if topic_ids and not is_extra_session:
            for tid in topic_ids:
                db.session.add(LessonLog(session_id=session.session_id, plan_id=tid, remarks="Conducted"))
                # Mark the TeachingPlan topic as Completed
                plan = TeachingPlan.query.get(tid)
                if plan:
                    plan.status = 'Completed'

        db.session.commit()
        return jsonify({"message": "Attendance Saved"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500



@app.route('/api/staff/session_history', methods=['GET'])
@login_required
def get_full_session_history():
    try:
        user_id = request.args.get('user_id')
        
        # Fetch ALL conducted sessions
        history_records = (db.session.query(SessionLog, WeeklySchedule, Subject, ClassSection)
                           .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                           .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                           .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
                           .filter(SessionLog.actual_teacher_id == user_id)
                           .filter(SessionLog.status == 'Conducted')
                           .order_by(SessionLog.session_date.desc(), WeeklySchedule.start_time.asc())
                           .all())

        history_list = []
        for sess, sched, subj, sec in history_records:
            # Attendance %
            total = AttendanceTransaction.query.filter_by(session_id=sess.session_id).count()
            present = AttendanceTransaction.query.filter(
                AttendanceTransaction.session_id == sess.session_id, 
                AttendanceTransaction.status.in_(PRESENT_STATUSES)
            ).count()
            perc = round((present/total)*100) if total > 0 else 0
            
            history_list.append({ 
                "schedule_id": sched.schedule_id, 
                "date_iso": sess.session_date.strftime('%Y-%m-%d'), # <--- CRITICAL FIELD
                "date_display": sess.session_date.strftime('%d %b %Y'), 
                "time": sched.start_time.strftime('%I:%M %p'),
                "subject": subj.name, 
                "class": f"{sec.class_level}-{sec.name}", 
                "percentage": perc 
            })

        return jsonify({"history": history_list})
    except Exception as e: return jsonify({"error": str(e)}), 500


# ==========================================
# API: EXTRA SESSIONS (One-time classes)
# ==========================================
@app.route('/api/staff/extra_sessions', methods=['GET'])
@login_required
def get_extra_sessions():
    """Get extra sessions for the logged-in teacher."""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id required"}), 400

        sessions = (db.session.query(ExtraSession, Subject, ClassSection)
                    .join(Subject, ExtraSession.subject_id == Subject.subject_id)
                    .join(ClassSection, ExtraSession.section_id == ClassSection.section_id)
                    .filter(ExtraSession.teacher_id == user_id)
                    .filter(ExtraSession.status != 'Cancelled')
                    .order_by(ExtraSession.date.desc(), ExtraSession.start_time.asc())
                    .all())

        result = []
        for es, subj, sec in sessions:
            # Check if attendance has been marked
            session_log = SessionLog.query.filter_by(extra_session_id=es.id).first()
            result.append({
                "id": es.id,
                "subject_id": es.subject_id,
                "subject_name": subj.name,
                "section_id": es.section_id,
                "section_name": f"{sec.class_level}-{sec.name}",
                "date": es.date.isoformat(),
                "start_time": es.start_time.strftime('%H:%M'),
                "end_time": es.end_time.strftime('%H:%M'),
                "topic": es.topic,
                "meeting_link": es.meeting_link,
                "status": es.status,
                "attendance_marked": session_log is not None
            })

        return jsonify({"extra_sessions": result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/staff/extra_sessions/allocations', methods=['GET'])
@login_required
def get_extra_session_allocations():
    """Get teacher's class/subject allocations for creating extra sessions."""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id required"}), 400

        # Use SubjectAllocation instead of WeeklySchedule to get class/subject combos
        # This ensures classes show even before timetable is published
        allocations = (db.session.query(SubjectAllocation, Subject, ClassSection)
                       .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                       .join(ClassSection, SubjectAllocation.section_id == ClassSection.section_id)
                       .filter(SubjectAllocation.teacher_id == user_id)
                       .all())

        sections = {}
        subjects = {}
        section_subjects = []

        for alloc, subj, sec in allocations:
            sec_key = sec.section_id
            subj_key = subj.subject_id

            if sec_key not in sections:
                sections[sec_key] = {
                    "section_id": sec.section_id,
                    "name": f"{sec.class_level}-{sec.name}"
                }
            if subj_key not in subjects:
                subjects[subj_key] = {
                    "subject_id": subj.subject_id,
                    "name": subj.name
                }

            section_subjects.append({
                "section_id": sec.section_id,
                "subject_id": subj.subject_id
            })

        return jsonify({
            "sections": list(sections.values()),
            "subjects": list(subjects.values()),
            "section_subjects": section_subjects
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/staff/extra_sessions', methods=['POST'])
@login_required
def create_extra_session():
    """Create a new extra session with validation."""
    try:
        data = request.json or {}
        user_id = data.get('user_id')
        subject_id = data.get('subject_id')
        section_id = data.get('section_id')
        date_str = data.get('date')
        start_time_str = data.get('start_time')
        end_time_str = data.get('end_time')
        topic = data.get('topic', '').strip()
        meeting_link = data.get('meeting_link', '').strip()

        # Validate required fields
        if not all([user_id, subject_id, section_id, date_str, start_time_str, end_time_str]):
            return jsonify({"error": "Missing required fields"}), 400

        # Parse date and time
        from datetime import datetime, time as dt_time
        session_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()

        # Validation 1: Check if date is in the past
        if session_date < datetime.now().date():
            return jsonify({"error": "Cannot schedule sessions in the past"}), 400

        # Validation 2: Weekday must be after 17:00
        day_of_week = session_date.weekday()  # 0=Monday, 6=Sunday
        is_weekend = day_of_week >= 5  # Saturday or Sunday

        if not is_weekend and start_time < dt_time(17, 0):
            return jsonify({"error": "Weekday extra sessions must start after 5:00 PM"}), 400

        # Validation 3: Check for section conflict (same section, overlapping time)
        conflicting = ExtraSession.query.filter(
            ExtraSession.section_id == section_id,
            ExtraSession.date == session_date,
            ExtraSession.status != 'Cancelled',
            db.or_(
                db.and_(ExtraSession.start_time <= start_time, ExtraSession.end_time > start_time),
                db.and_(ExtraSession.start_time < end_time, ExtraSession.end_time >= end_time),
                db.and_(ExtraSession.start_time >= start_time, ExtraSession.end_time <= end_time)
            )
        ).first()

        if conflicting:
            return jsonify({"error": "This class already has an extra session scheduled at this time"}), 400

        # Create the extra session
        extra_session = ExtraSession(
            subject_id=subject_id,
            teacher_id=user_id,
            section_id=section_id,
            date=session_date,
            start_time=start_time,
            end_time=end_time,
            topic=topic if topic else None,
            meeting_link=meeting_link if meeting_link else None,
            status='Scheduled'
        )
        db.session.add(extra_session)
        db.session.commit()

        # Send notification to students (filter by elective if applicable)
        section = ClassSection.query.get(section_id)
        subject = Subject.query.get(subject_id)
        teacher = StaffProfile.query.get(user_id)

        if is_elective_type(subject.subject_type):
            # Only notify students with approved elective selection
            students = (db.session.query(StudentProfile)
                        .join(StudentElective, StudentProfile.student_id == StudentElective.student_id)
                        .filter(StudentProfile.current_section_id == section_id)
                        .filter(StudentElective.subject_id == subject_id)
                        .filter(StudentElective.status == 'Approved')
                        .all())
        else:
            students = StudentProfile.query.filter_by(current_section_id=section_id).all()

        for student in students:
            send_notification(
                student.student_id,
                f"Extra Class: {subject.name}",
                f"Extra class scheduled on {session_date.strftime('%d %b')} at {start_time.strftime('%I:%M %p')}. Topic: {topic or 'TBA'}",
                type='info'
            )

        return jsonify({
            "message": "Extra session created successfully",
            "id": extra_session.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/staff/extra_sessions/<int:session_id>', methods=['PUT'])
@login_required
def update_extra_session(session_id):
    """Update an extra session."""
    try:
        data = request.json or {}
        user_id = data.get('user_id')

        extra_session = ExtraSession.query.get(session_id)
        if not extra_session:
            return jsonify({"error": "Extra session not found"}), 404

        if extra_session.teacher_id != user_id:
            return jsonify({"error": "Not authorized to modify this session"}), 403

        # Check if attendance already marked
        session_log = SessionLog.query.filter_by(extra_session_id=session_id).first()
        if session_log:
            return jsonify({"error": "Cannot modify session after attendance is marked"}), 400

        # Update fields
        if 'topic' in data:
            extra_session.topic = data['topic'].strip() or None
        if 'meeting_link' in data:
            extra_session.meeting_link = data['meeting_link'].strip() or None

        db.session.commit()
        return jsonify({"message": "Extra session updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/staff/extra_sessions/<int:session_id>', methods=['DELETE'])
@login_required
def cancel_extra_session(session_id):
    """Cancel an extra session."""
    try:
        user_id = request.args.get('user_id')

        extra_session = ExtraSession.query.get(session_id)
        if not extra_session:
            return jsonify({"error": "Extra session not found"}), 404

        if extra_session.teacher_id != user_id:
            return jsonify({"error": "Not authorized to cancel this session"}), 403

        # Check if attendance already marked
        session_log = SessionLog.query.filter_by(extra_session_id=session_id).first()
        if session_log:
            return jsonify({"error": "Cannot cancel session after attendance is marked"}), 400

        extra_session.status = 'Cancelled'
        db.session.commit()

        # Notify students (filter by elective if applicable)
        section = ClassSection.query.get(extra_session.section_id)
        subject = Subject.query.get(extra_session.subject_id)

        if is_elective_type(subject.subject_type):
            # Only notify students with approved elective selection
            students = (db.session.query(StudentProfile)
                        .join(StudentElective, StudentProfile.student_id == StudentElective.student_id)
                        .filter(StudentProfile.current_section_id == extra_session.section_id)
                        .filter(StudentElective.subject_id == extra_session.subject_id)
                        .filter(StudentElective.status == 'Approved')
                        .all())
        else:
            students = StudentProfile.query.filter_by(current_section_id=extra_session.section_id).all()

        for student in students:
            send_notification(
                student.student_id,
                f"Extra Class Cancelled: {subject.name}",
                f"The extra class scheduled on {extra_session.date.strftime('%d %b')} at {extra_session.start_time.strftime('%I:%M %p')} has been cancelled.",
                type='warning'
            )

        return jsonify({"message": "Extra session cancelled"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/staff/extra_sessions/<int:session_id>/mark_attendance', methods=['POST'])
@login_required
def mark_extra_session_attendance(session_id):
    """Mark attendance for an extra session - creates session log and attendance records."""
    try:
        data = request.json or {}
        user_id = data.get('user_id')
        attendance_data = data.get('attendance', [])

        extra_session = ExtraSession.query.get(session_id)
        if not extra_session:
            return jsonify({"error": "Extra session not found"}), 404

        if extra_session.teacher_id != user_id:
            return jsonify({"error": "Not authorized"}), 403

        # Check if already marked
        existing_log = SessionLog.query.filter_by(extra_session_id=session_id).first()
        if existing_log:
            return jsonify({"error": "Attendance already marked for this session"}), 400

        # Create session log
        session_log = SessionLog(
            extra_session_id=session_id,
            session_date=extra_session.date,
            status='Conducted',
            actual_teacher_id=user_id
        )
        db.session.add(session_log)
        db.session.flush()

        # Create attendance transactions
        for att in attendance_data:
            student_id = att.get('student_id')
            status = att.get('status', 'Absent')
            if student_id:
                txn = AttendanceTransaction(
                    session_id=session_log.session_id,
                    student_id=student_id,
                    status=status
                )
                db.session.add(txn)

        # Update extra session status
        extra_session.status = 'Conducted'
        db.session.commit()

        return jsonify({"message": "Attendance marked successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ==========================================
# API: LEAVE & STUDENT
# ==========================================
@app.route('/api/staff/leave_requests', methods=['GET'])
@login_required
def get_staff_leave_requests():
    user_id = request.args.get('user_id')
    include_all = request.args.get('include_all', 'false').lower() == 'true'
    class_managed = ClassSection.query.filter_by(class_teacher_id=user_id).first()
    dept_managed = Department.query.filter_by(hod_staff_id=user_id).first()
    leave_list = []

    def format_leave(leave, student, section, role_context):
        return {
            "leave_id": leave.leave_id,
            "student_name": student.full_name,
            "roll_no": student.admission_number,
            "class_name": f"{section.class_level}-{section.name}",
            "leave_type": leave.leave_type or "General",
            "days": leave.total_days,
            "start_date": leave.start_date.strftime('%Y-%m-%d') if leave.start_date else "",
            "end_date": leave.end_date.strftime('%Y-%m-%d') if leave.end_date else "",
            "date_range": f"{leave.start_date.strftime('%d %b')} - {leave.end_date.strftime('%d %b')}",
            "reason": leave.reason,
            "status": leave.status.replace('Pending_CT', 'Pending').replace('Pending_HOD', 'Pending'),
            "applied_on": leave.start_date.strftime('%d %b %Y') if leave.start_date else "",
            "role_context": role_context
        }

    if class_managed:
        # Pending requests for Class Teacher
        ct_pending = (db.session.query(LeaveApplication, StudentProfile, ClassSection)
            .join(StudentProfile, LeaveApplication.student_id == StudentProfile.student_id)
            .join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
            .filter(ClassSection.section_id == class_managed.section_id)
            .filter(LeaveApplication.status == 'Pending_CT').all())
        for leave, student, section in ct_pending:
            leave_list.append(format_leave(leave, student, section, "Class Teacher"))

        # Include approved/rejected if requested
        if include_all:
            ct_history = (db.session.query(LeaveApplication, StudentProfile, ClassSection)
                .join(StudentProfile, LeaveApplication.student_id == StudentProfile.student_id)
                .join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
                .filter(ClassSection.section_id == class_managed.section_id)
                .filter(LeaveApplication.status.in_(['Approved', 'Rejected']))
                .order_by(LeaveApplication.start_date.desc())
                .limit(50).all())
            for leave, student, section in ct_history:
                leave_list.append(format_leave(leave, student, section, "Class Teacher"))

    if dept_managed:
        # Pending requests for HOD
        hod_pending = (db.session.query(LeaveApplication, StudentProfile, ClassSection)
            .join(StudentProfile, LeaveApplication.student_id == StudentProfile.student_id)
            .join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
            .filter(LeaveApplication.status == 'Pending_HOD').all())
        for leave, student, section in hod_pending:
            leave_list.append(format_leave(leave, student, section, "HOD Approval"))

        # Include approved/rejected if requested (HOD scope - long leaves)
        if include_all:
            hod_history = (db.session.query(LeaveApplication, StudentProfile, ClassSection)
                .join(StudentProfile, LeaveApplication.student_id == StudentProfile.student_id)
                .join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
                .filter(LeaveApplication.total_days > 15)
                .filter(LeaveApplication.status.in_(['Approved', 'Rejected']))
                .order_by(LeaveApplication.start_date.desc())
                .limit(50).all())
            for leave, student, section in hod_history:
                leave_list.append(format_leave(leave, student, section, "HOD Approval"))

    # Fetch students on duty (events) for Class Teacher's section
    # Include ALL event participations (not just today) to match web app behavior
    on_duty_list = []
    if class_managed:
        today = date.today()
        MAX_EVENT_ROWS = 500
        event_participants = (
            db.session.query(EventParticipation, EventMaster, StudentProfile)
            .join(EventMaster, EventParticipation.event_id == EventMaster.event_id)
            .join(StudentProfile, EventParticipation.student_id == StudentProfile.student_id)
            .filter(StudentProfile.current_section_id == class_managed.section_id)
            .order_by(EventMaster.start_date.desc(), EventMaster.event_id.desc())
            .limit(MAX_EVENT_ROWS)
            .all()
        )

        # Group by student to avoid duplicates
        student_events = {}
        for part, event, student in event_participants:
            raw_status = (getattr(part, 'status', '') or '').strip()
            if raw_status.lower() in ('cancelled', 'canceled', 'rejected'):
                continue

            sid = student.student_id
            # Check if event is active today
            is_today = event.start_date and event.end_date and (event.start_date <= today <= event.end_date)

            if sid not in student_events:
                student_events[sid] = {
                    "student_id": sid,
                    "student_name": student.full_name,
                    "roll_no": student.admission_number,
                    "events": []
                }
            student_events[sid]["events"].append({
                "event_id": event.event_id,
                "event_name": event.event_name,
                "role": part.student_role or "Participant",
                "status": raw_status or "Nominated",
                "date_range": f"{event.start_date.strftime('%d %b')} - {event.end_date.strftime('%d %b')}" if event.start_date and event.end_date else "",
                "is_today": is_today
            })

        on_duty_list = sorted(student_events.values(), key=lambda x: x.get('roll_no', ''))

    return jsonify({"requests": leave_list, "on_duty_students": on_duty_list})

@app.route('/api/staff/leave_action', methods=['POST'])
@login_required
def staff_leave_action():
    try:
        data = request.json
        leave = LeaveApplication.query.get(data.get('leave_id'))
        if not leave: return jsonify({"error": "Leave not found"}), 404
        # Capitalize the action to match the status values in the database
        action = data.get('action', '').capitalize()
        leave.status = action
        
        # NOTIFY STUDENT
        msg_type = "success" if leave.status == "Approved" else "danger"
        send_notification(leave.student_id, f"Leave {leave.status}", f"Your leave request has been {leave.status}.", msg_type)
        
        db.session.commit()
        return jsonify({"message": f"Leave {data.get('action')}"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/student/dashboard', methods=['GET'])
@login_required
def student_dashboard():
    try:
        user_id = request.args.get('user_id')
        student = StudentProfile.query.get(user_id)
        if not student: return jsonify({"error": "Student not found"}), 404
        
        # --- SAFETY CHECK: Unassigned ---
        if not student.current_section_id:
            return jsonify({
                "profile": { "name": student.full_name, "roll": student.admission_number, "class": "Unassigned" },
                "stats": { "percentage": 0, "total_lectures": 0, "attended": 0, "is_defaulter": False },
                "subject_wise": [], "recent_activity": [], "events": [], "mentor": None, "results": []
            })

        section = ClassSection.query.get(student.current_section_id)
        if not section:
             return jsonify({ "profile": { "name": student.full_name, "roll": student.admission_number, "class": "Unknown" }, "stats": {}, "subject_wise": [] })

        # --- 1. MENTOR INFO ---
        mentor_info = None; my_batch_name = None; upcoming_meeting = None
        if student.mentor_batch_id:
            batch = db.session.get(MentorBatch, student.mentor_batch_id)
            if batch:
                my_batch_name = batch.batch_name
                if batch.mentor_id:
                    mentor = db.session.get(StaffProfile, batch.mentor_id)
                    if mentor: 
                        mentor_info = { "name": mentor.full_name, "email": mentor.email_contact, "batch_name": batch.batch_name }
                
                # Meeting Check
                try:
                    meeting = MentorMeeting.query.filter_by(batch_id=batch.batch_id, status='Scheduled').filter(MentorMeeting.date >= date.today()).order_by(MentorMeeting.date).first()
                    if meeting:
                        upcoming_meeting = {
                            "date": meeting.date.strftime('%d %b'),
                            "time": meeting.time.strftime('%I:%M %p'),
                            "agenda": meeting.agenda
                        }
                except: pass

        # --- 2. SUBJECT PERFORMANCE (Source: Allocation) ---
        # Fetch allocations (The Source of Truth for "What subjects do I have?")
        allocations = SubjectAllocation.query.filter_by(section_id=section.section_id).all()
        
        # Create Map: { subject_id : teacher_id } to preserve teacher info
        subject_teacher_map = {a.subject_id: a.teacher_id for a in allocations}
        
        sub_perf = []
        grand_total_conducted = 0
        grand_total_attended = 0

        for sub_id, teacher_id in subject_teacher_map.items():
            subject = db.session.get(Subject, sub_id)
            if not subject: continue
            
            # Elective Filter
            if is_elective_type(subject.subject_type):
                try:
                    # Only show if student has APPROVED selection
                    is_approved = StudentElective.query.filter_by(student_id=student.student_id, subject_id=sub_id, status='Approved').first()
                    if not is_approved: continue
                except: pass

            # Calculate Attendance
            # We join WeeklySchedule to find LOGS for this subject+section
            sessions = (db.session.query(SessionLog, WeeklySchedule.target_batch)
                        .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                        .filter(WeeklySchedule.subject_id == sub_id)
                        .filter(WeeklySchedule.section_id == section.section_id)
                        .filter(SessionLog.status == 'Conducted')
                        .all())
            
            applicable_ids = []
            for sess, target_batch in sessions:
                # Include if Lecture (No Batch) OR Batch matches Student
                if not target_batch or target_batch == my_batch_name:
                    applicable_ids.append(sess.session_id)
            
            conducted = len(applicable_ids)
            attended_sub = 0
            if conducted > 0:
                attended_sub = AttendanceTransaction.query.filter(
                    AttendanceTransaction.session_id.in_(applicable_ids),
                    AttendanceTransaction.student_id == student.student_id,
                    AttendanceTransaction.status.in_(PRESENT_STATUSES)
                ).count()
            
            grand_total_conducted += conducted
            grand_total_attended += attended_sub
            
            sub_perc = round((attended_sub / conducted) * 100, 1) if conducted > 0 else 0
            
            # Get Teacher Name
            t_name = "Unassigned"
            if teacher_id:
                t = db.session.get(StaffProfile, teacher_id)
                if t: t_name = t.full_name

            sub_perf.append({ 
                "subject": subject.name, 
                "code": subject.code, 
                "teacher": t_name,
                "conducted": conducted, 
                "attended": attended_sub, 
                "percentage": sub_perc 
            })

        # --- 3. OVERALL STATS ---
        overall_percentage = round((grand_total_attended / grand_total_conducted) * 100, 1) if grand_total_conducted > 0 else 0

        # --- 4. RECENT ACTIVITY ---
        activity = []
        try:
            recent_txns = (db.session.query(AttendanceTransaction, SessionLog, WeeklySchedule, Subject)
                           .join(SessionLog, AttendanceTransaction.session_id == SessionLog.session_id)
                           .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                           .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                           .filter(AttendanceTransaction.student_id == student.student_id)
                           .order_by(SessionLog.session_date.desc()).limit(5).all())
            
            for txn, sess, sched, subj in recent_txns:
                activity.append({ 
                    "date": sess.session_date.strftime('%d %b'), 
                    "subject": subj.name, 
                    "status": txn.status, 
                    "time": sched.start_time.strftime('%I:%M %p') 
                })
        except: pass

        # --- 5. EVENTS ---
        event_history = []
        try:
            events = (db.session.query(EventParticipation, EventMaster)
                      .join(EventMaster, EventParticipation.event_id == EventMaster.event_id)
                      .filter(EventParticipation.student_id == student.student_id)
                      .order_by(EventMaster.start_date.desc()).all())
            event_history = [{ "name": e.event_name, "date": e.start_date.strftime('%d %b'), "role": p.student_role, "status": p.status } for p, e in events]
        except: pass

        # --- 6. DETENTION ---
        detention_data = None
        try:
            active_detention = (DetentionRecord.query
                                .filter_by(student_id=user_id)
                                .filter(DetentionRecord.status.in_(['Assigned', 'In_Review']))
                                .order_by(DetentionRecord.detention_id.desc())
                                .first())
            if active_detention:
                detention_data = {
                    "id": active_detention.detention_id,
                    "reason": active_detention.reason,
                    "status": active_detention.status,
                    "task": active_detention.assignment_details,
                    "submission_url": active_detention.submission_doc_url
                }
        except: pass

        # --- 7. RESULTS ---
        results_data = []
        try:
            ca_records = (db.session.query(CAMarks, Subject)
                          .join(Subject, CAMarks.subject_id == Subject.subject_id)
                          .filter(CAMarks.student_id == user_id)
                          .all())
            
            for marks, sub in ca_records:
                entry = { "subject": sub.name, "code": sub.code }
                # Mask unpublished marks
                entry['ta1'] = marks.ta1 if marks.is_published_ta1 else "-"
                entry['ta2'] = marks.ta2 if marks.is_published_ta2 else "-"
                entry['ta3'] = marks.ta3 if marks.is_published_ta3 else "-"
                if marks.is_published_ta1: 
                    entry['a1'] = marks.a1; entry['a2'] = marks.a2
                results_data.append(entry)
        except: pass

        # --- 8. TERM GRANT STATUS (NEW) ---
        term_grant = TermGrantRecord.query.filter_by(student_id=user_id).first()
        grant_data = None

        # Only show if the record exists (AMC has generated it)
        if term_grant:
            grant_data = {
                "status": term_grant.status, # Granted, Provisional, Detained
                "remarks": term_grant.remarks,
                "att_perc": term_grant.attendance_perc,
                "ca_avg": term_grant.avg_ca_score
            }

        # --- 9. EXTRA SESSIONS (One-time classes) ---
        extra_sessions_list = []
        today_date = datetime.now().date()
        try:
            extra_sessions = (db.session.query(ExtraSession, Subject, StaffProfile)
                              .join(Subject, ExtraSession.subject_id == Subject.subject_id)
                              .join(StaffProfile, ExtraSession.teacher_id == StaffProfile.staff_id)
                              .filter(ExtraSession.section_id == section.section_id)
                              .filter(ExtraSession.status != 'Cancelled')
                              .filter(ExtraSession.date >= today_date)
                              .order_by(ExtraSession.date.asc(), ExtraSession.start_time.asc())
                              .all())

            for es, subj, teacher in extra_sessions:
                # Filter by elective: only show if student has approved selection for elective subjects
                if is_elective_type(subj.subject_type):
                    approved = StudentElective.query.filter_by(
                        student_id=student.student_id,
                        subject_id=subj.subject_id,
                        status='Approved'
                    ).first()
                    if not approved:
                        continue  # Skip this extra session - student hasn't opted for this elective

                extra_sessions_list.append({
                    "id": es.id,
                    "subject": subj.name,
                    "teacher": teacher.full_name,
                    "date": es.date.strftime('%d %b'),
                    "date_iso": es.date.isoformat(),
                    "day": es.date.strftime('%A'),
                    "time": f"{es.start_time.strftime('%I:%M %p')} - {es.end_time.strftime('%I:%M %p')}",
                    "topic": es.topic,
                    "meeting_link": es.meeting_link,
                    "is_today": es.date == today_date
                })
        except Exception as ex:
            print(f"Error loading extra sessions for student: {ex}")

        return jsonify({
            "profile": { "name": student.full_name, "roll": student.admission_number, "class": f"{section.class_level}-{section.name}" },
            "stats": {
                "percentage": overall_percentage,
                "total_lectures": grand_total_conducted,
                "attended": grand_total_attended,
                "is_defaulter": overall_percentage < 75
            },
            "subject_wise": sub_perf,
            "recent_activity": activity,
            "events": event_history,
            "mentor": mentor_info,
            "detention": detention_data,
            "meeting": upcoming_meeting,
            "results": results_data,
            "term_grant": grant_data,
            "extra_sessions": extra_sessions_list
        })

    except Exception as e:
        print(f"CRITICAL ERROR in Student Dashboard: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/student/timetable', methods=['GET'])
@login_required
def student_timetable_web():
    """Web-session based timetable for student dashboard (uses _get_student_timetable_payload)"""
    try:
        user_id = request.args.get('user_id')
        student = StudentProfile.query.get(user_id)
        if not student:
            return jsonify({"error": "Student not found"}), 404

        payload = _get_student_timetable_payload(student)

        # Add version info for display
        if student.current_section_id:
            active_version = TimetableVersion.query.filter_by(
                section_id=student.current_section_id,
                status='Active'
            ).first()
            if active_version:
                payload['version'] = {
                    'version_number': active_version.version_number,
                    'version_label': active_version.version_label,
                    'published_at': active_version.published_at.isoformat() if active_version.published_at else None
                }

        return jsonify(payload), 200

    except Exception as e:
        print(f"Error in student timetable: {e}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# ADMIN & STAFF UTILITIES (RESTORED/NEW)
# ==========================================

@app.route('/staff/detention')
def render_detention_assign():
    return render_template('detention_assign.html')

# # We need a quick way to look up student ID by roll number
# @app.route('/api/admin/directory', methods=['GET'])
# def get_student_directory():
#     # ... (Keep existing directory fetch logic) ...
#     # ADDED LOGIC: If roll_no is provided, return just that student's ID (for lookup)
#     roll_no = request.args.get('roll_no')
#     if roll_no:
#         student = StudentProfile.query.filter_by(admission_number=roll_no).first()
#         if student: return jsonify({"student_id": student.student_id})
#         return jsonify({"student_id": None})
    
#     # ... (Existing full directory dump logic) ...
#     # This part should handle the standard tabbed view if roll_no is not present
#     try:
#         results = (db.session.query(StudentProfile, ClassSection).outerjoin(ClassSection, StudentProfile.current_section_id == ClassSection.section_id).order_by(ClassSection.class_level, ClassSection.name, StudentProfile.full_name).all())
#         directory = {}
#         for student, section in results:
#             lvl = section.class_level if section else "Unassigned"
#             sec = section.name if section else "No Section"
#             if lvl not in directory: directory[lvl] = {}
#             if sec not in directory[lvl]: directory[lvl][sec] = []
#             directory[lvl][sec].append({ "id": student.student_id, "name": student.full_name, "roll": student.admission_number, "status": student.academic_status or "Active" })
#         return jsonify({"directory": directory})
#     except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/detention/assign', methods=['POST'])
@login_required
def assign_detention():
    try:
        data = request.json
        
        # 1. Check if an active detention already exists
        active_detention = DetentionRecord.query.filter_by(
            student_id=data.get('student_id'),
            status='Assigned'
        ).first()
        
        if active_detention:
            return jsonify({"error": "Student already has an active detention. Review pending tasks first."}), 400

        # 2. Create the record
        new_detention = DetentionRecord(
            student_id=data.get('student_id'),
            assigned_by_staff_id=data.get('assigned_by_staff_id'),
            reason=data.get('reason'),
            assignment_details=data.get('assignment_details'),
            status='Assigned'
        )
        db.session.add(new_detention)
        db.session.commit()
        
        # 3. Log
        student_name = StudentProfile.query.get(data.get('student_id')).full_name
        log_activity("Detention", f"Assigned task to {student_name} for {data.get('reason')}")

        new_detention = DetentionRecord(student_id=data.get('student_id'), assigned_by_staff_id=data.get('assigned_by_staff_id'), reason=data.get('reason'), assignment_details=data.get('assignment_details'), status='Assigned')
        db.session.add(new_detention); db.session.commit()
        
        # NOTIFY STUDENT
        send_notification(data.get('student_id'), "Detention Assigned", f"You have been assigned a remedial task for {data.get('reason')}.", "danger", "/student/dashboard")
        
        return jsonify({"message": "Detention assigned successfully"}), 200

    except Exception as e: return jsonify({"error": str(e)}), 500



# ==========================================
# API: DETENTION WATCHLIST
# ==========================================
# @app.route('/api/detention/watchlist', methods=['GET'])
# def get_defaulter_watchlist():
#     try:
#         user_id = request.args.get('user_id')
#         staff = StaffProfile.query.get(user_id)
#         if not staff: return jsonify({"error": "Staff not found"}), 404
        
#         # 1. Get all subjects taught by this faculty member
#         subject_allocations = SubjectAllocation.query.filter_by(teacher_id=user_id).all()
        
#         # Map: student_id -> (subject_code, attendance_percentage)
#         student_watch_list = {}
        
#         for alloc in subject_allocations:
#             section_id = alloc.section_id
#             subject = db.session.get(Subject, alloc.subject_id)
            
#             # Find all conducted sessions for this subject in this section
#             conducted_sessions = (db.session.query(SessionLog.session_id)
#                                   .join(WeeklySchedule)
#                                   .filter(WeeklySchedule.subject_id == subject.subject_id)
#                                   .filter(WeeklySchedule.section_id == section_id)
#                                   .filter(SessionLog.status == 'Conducted')
#                                   .all())
            
#             session_ids = [s[0] for s in conducted_sessions]
            
#             if not session_ids: continue # Skip if no sessions conducted yet

#             # Get students in this class section
#             students_in_class = StudentProfile.query.filter_by(current_section_id=section_id).all()

#             for student in students_in_class:
#                 student_id = student.student_id
                
#                 # Check if student has attendance for this subject
#                 attended_count = AttendanceTransaction.query.filter(
#                     AttendanceTransaction.session_id.in_(session_ids),
#                     AttendanceTransaction.student_id == student_id,
#                     AttendanceTransaction.status.in_(PRESENT_STATUSES)
#                 ).count()
                
#                 perc = round((attended_count / len(session_ids)) * 100, 1)

#                 if perc < 75:
#                     if student_id not in student_watch_list:
#                         student_watch_list[student_id] = {
#                             "id": student_id,
#                             "name": student.full_name,
#                             "roll": student.admission_number,
#                             "class": f"{ClassSection.class_level}-{ClassSection.name}",
#                             "defaulter_in": []
#                         }
                    
#                     student_watch_list[student_id]['defaulter_in'].append({
#                         "subject": subject.name,
#                         "percentage": perc
#                     })

#         # Convert dictionary to list
#         final_list = list(student_watch_list.values())
#         return jsonify({"watchlist": final_list})

#     except Exception as e: return jsonify({"error": str(e)}), 500



from datetime import timedelta # Ensure this is imported

@app.route('/api/detention/watchlist', methods=['GET'])
@login_required
def get_defaulter_watchlist():
    try:
        user_id = request.args.get('user_id')
        staff = StaffProfile.query.get(user_id)
        if not staff: return jsonify({"error": "Staff not found"}), 404
        
        # --- 1. SMART DATE LOGIC ---
        today = date.today()
        
        # If it's the start of the month (1st-5th), look at Previous Month
        if today.day <= 5:
            # Last day of prev month = 1st of this month - 1 day
            end_date = today.replace(day=1) - timedelta(days=1)
            start_date = end_date.replace(day=1)
            report_title = end_date.strftime('%B %Y') # e.g. "November 2023"
        else:
            # Current Month
            start_date = today.replace(day=1)
            end_date = today
            report_title = today.strftime('%B %Y') # e.g. "December 2023"

        # 2. Get Subjects (Allocations)
        subject_allocations = (db.session.query(SubjectAllocation, Subject, ClassSection)
                               .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                               .join(ClassSection, SubjectAllocation.section_id == ClassSection.section_id)
                               .filter(SubjectAllocation.teacher_id == user_id)
                               .all())
        
        student_watch_list = {}
        if not subject_allocations: return jsonify({"watchlist": [], "meta": "No subjects assigned."})

        # 3. Process Each Subject
        for alloc, subject, section in subject_allocations:
            section_id = section.section_id
            subject_id = subject.subject_id
            
            # FILTER SESSIONS BY DATE RANGE (Monthly View)
            conducted_sessions_data = (db.session.query(SessionLog.session_id, WeeklySchedule.target_batch)
                                  .join(WeeklySchedule)
                                  .filter(WeeklySchedule.subject_id == subject_id)
                                  .filter(WeeklySchedule.section_id == section_id)
                                  .filter(SessionLog.status == 'Conducted')
                                  .filter(SessionLog.session_date >= start_date) # <--- DATE FILTER
                                  .filter(SessionLog.session_date <= end_date)   # <--- DATE FILTER
                                  .all())
            
            # SAFETY VALVE: If less than 4 lectures done this month, don't calculate defaulters yet.
            if len(conducted_sessions_data) < 4: continue

            students_in_class = StudentProfile.query.filter_by(current_section_id=section_id).all()

            for student in students_in_class:
                student_id = student.student_id
                
                # Exclude if Active Detention Exists (Prevent Spam)
                has_active = DetentionRecord.query.filter_by(student_id=student_id).filter(DetentionRecord.status.in_(['Assigned', 'In_Review'])).first()
                if has_active: continue

                # Batch Logic (Student's Batch)
                student_batch_name = None
                if student.mentor_batch_id:
                    mb = db.session.get(MentorBatch, student.mentor_batch_id)
                    if mb: student_batch_name = mb.batch_name

                # Calculate Attendance for Valid Sessions
                valid_sessions = 0
                attended = 0
                
                for sess_id, target_batch in conducted_sessions_data:
                    # Check if session applies to student
                    if not target_batch or target_batch == student_batch_name:
                        valid_sessions += 1
                        # Check if attended
                        txn = AttendanceTransaction.query.filter_by(session_id=sess_id, student_id=student_id).filter(AttendanceTransaction.status.in_(PRESENT_STATUSES)).first()
                        if txn: attended += 1
                
                if valid_sessions == 0: continue

                perc = round((attended / valid_sessions) * 100, 1)

                if perc < 75:
                    if student_id not in student_watch_list:
                        student_watch_list[student_id] = {
                            "id": student_id,
                            "name": student.full_name,
                            "roll": student.admission_number,
                            "class": f"{section.class_level}-{section.name}",
                            "defaulter_in": []
                        }
                    
                    student_watch_list[student_id]['defaulter_in'].append({
                        "subject": subject.name,
                        "percentage": perc,
                        "total_held": valid_sessions # Useful context
                    })

        final_list = list(student_watch_list.values())
        return jsonify({
            "watchlist": final_list,
            "meta": {
                "period": report_title,
                "date_range": f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}"
            }
        })

    except Exception as e: 
        print(f"CRITICAL ERROR in Watchlist: {e}")
        return jsonify({"error": "Internal calculation error"}), 500



# ==========================================
# API: PARENT DASHBOARD
# ==========================================
@app.route('/parent/dashboard')
def render_parent_dashboard():
    return render_template('parent_dashboard.html')



@app.route('/api/parent/dashboard', methods=['GET'])
@login_required
def parent_dashboard():
    try:
        user_id = request.args.get('user_id')
        student = StudentProfile.query.filter_by(parent_user_id=user_id).first()
        if not student: return jsonify({"error": "No student linked."}), 404
        if not student.current_section_id: return jsonify({"error": "Unassigned."}), 404
        section = ClassSection.query.get(student.current_section_id)

        # 1. Mentor Info
        my_batch_name = None; mentor_info = None
        if student.mentor_batch_id:
            batch = db.session.get(MentorBatch, student.mentor_batch_id)
            if batch:
                my_batch_name = batch.batch_name
                if batch.mentor_id:
                     m = db.session.get(StaffProfile, batch.mentor_id)
                     if m: mentor_info = {"name": m.full_name, "email": m.email_contact, "batch_name": batch.batch_name}

        # 2. Attendance Stats
        allocations = SubjectAllocation.query.filter_by(section_id=section.section_id).all()
        unique_sub_ids = set(a.subject_id for a in allocations)
        sub_perf = []; gt_c = 0; gt_a = 0
        
        for sub_id in unique_sub_ids:
            sub = db.session.get(Subject, sub_id)
            if not sub: continue
            if is_elective_type(sub.subject_type):
                try:
                    if not StudentElective.query.filter_by(student_id=student.student_id, subject_id=sub_id, status='Approved').first(): continue
                except: pass

            sessions = db.session.query(SessionLog, WeeklySchedule.target_batch).join(WeeklySchedule).filter(WeeklySchedule.subject_id==sub_id, WeeklySchedule.section_id==section.section_id, SessionLog.status=='Conducted').all()
            valid_sids = [s.session_id for s, b in sessions if not b or b == my_batch_name]
            cond = len(valid_sids)
            att = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(valid_sids), AttendanceTransaction.student_id==student.student_id, AttendanceTransaction.status.in_(['Present', 'OnDuty', 'OD', 'ML', 'CL'])).count() if cond > 0 else 0
            gt_c += cond; gt_a += att
            sub_perf.append({
                "subject": sub.name,
                "code": sub.code,
                "subject_code": sub.code,
                "conducted": cond,
                "attended": att,
                "percentage": round((att/cond)*100, 1) if cond > 0 else 0
            })

        overall = round((gt_a/gt_c)*100, 1) if gt_c > 0 else 0
        
        # 3. Events & Leaves
        events = (db.session.query(EventParticipation, EventMaster).join(EventMaster).filter(EventParticipation.student_id == student.student_id).order_by(EventMaster.start_date.desc()).all())
        evts = [{ "name": e.event_name, "date": e.start_date.strftime('%d %b'), "role": p.student_role, "status": p.status } for p, e in events]

        leaves = LeaveApplication.query.filter_by(student_id=student.student_id).order_by(LeaveApplication.start_date.desc()).limit(5).all()
        lvs = [{ "type": l.leave_type or "General", "days": l.total_days, "status": l.status, "date": l.start_date.strftime('%d %b') } for l in leaves]
        
        # 4. Detention
        ad = DetentionRecord.query.filter_by(student_id=student.student_id).filter(DetentionRecord.status.in_(['Assigned', 'In_Review'])).first()
        det = { "reason": ad.reason, "status": ad.status } if ad else None
        
        # 5. Counseling Logs & Escalation Check
        # Sort so most recent is first
        logs_query = (db.session.query(MentorLog, StaffProfile)
                      .join(StaffProfile, MentorLog.mentor_id == StaffProfile.staff_id)
                      .filter(MentorLog.student_id == student.student_id)
                      .order_by(MentorLog.date.desc())
                      .all())
        
        clogs = []
        escalation_alert = None
        
        for log, m in logs_query:
            clogs.append({
                "date": log.date.strftime('%d %b %Y'), 
                "category": log.issue_category, 
                "remarks": log.remarks, 
                "status": log.status, 
                "mentor": m.full_name
            })
            # Check for ANY active escalation (even if old, if status is Escalated it needs attention)
            if log.status == 'Escalated' and not escalation_alert:
                escalation_alert = { "category": log.issue_category, "remarks": log.remarks }

        # 6. Results
        ca_records = (db.session.query(CAMarks, Subject).join(Subject, CAMarks.subject_id == Subject.subject_id).filter(CAMarks.student_id == student.student_id).all())
        results_data = []
        for marks, sub in ca_records:
            entry = { "subject": sub.name }
            entry['ta1'] = marks.ta1 if marks.is_published_ta1 else "-"
            entry['ta2'] = marks.ta2 if marks.is_published_ta2 else "-"
            entry['ta3'] = marks.ta3 if marks.is_published_ta3 else "-"
            if marks.is_published_ta1 or marks.is_published_ta2 or marks.is_published_ta3:
                results_data.append(entry)

        term_grant = TermGrantRecord.query.filter_by(student_id=student.student_id).first()
        grant_data = { "status": term_grant.status, "remarks": term_grant.remarks } if term_grant else None

        return jsonify({
            "student": { "name": student.full_name, "roll": student.admission_number, "class": f"{section.class_level}-{section.name}" },
            "stats": { "percentage": overall, "total": gt_c, "attended": gt_a },
            "subjects": sub_perf,
            "detention": det,
            "escalation": escalation_alert, # <--- Sending Escalation Info
            "mentor": mentor_info,
            "events": evts,
            "leaves": lvs,
            "logs": clogs,
            "results": results_data,
            "term_grant": grant_data
        })

    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/mentor/add_log', methods=['POST'])
def add_mentor_log():
    try:
        data = request.json
        student = StudentProfile.query.get(data.get('student_id'))
        
        # Create Log
        new_log = MentorLog(
            student_id=data.get('student_id'), 
            mentor_id=data.get('mentor_id'), 
            mentor_batch_id=student.mentor_batch_id if student else None, 
            issue_category=data.get('category'), 
            remarks=data.get('remarks'), 
            action_taken=data.get('action_taken')
        )
        db.session.add(new_log)
        db.session.commit()
        
        # NOTIFICATION
        send_notification(
            data.get('student_id'), 
            "New Mentor Log", 
            f"Your mentor recorded a session regarding: {data.get('category')}", 
            "info",
            "/student/dashboard" # Link to dashboard so they can check logs? (Student view of logs isn't fully built, but parent is)
        )
        
        return jsonify({"message": "Logged"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/mentor/update_log_status', methods=['POST'])
def update_mentor_log_status():
    try:
        data = request.json
        log = db.session.get(MentorLog, data.get('log_id'))
        if not log: return jsonify({"error": "Log not found"}), 404
        
        log.status = data.get('status')
        db.session.commit()
        
        # NOTIFICATION
        msg_type = "success"
        title = "Issue Resolved"
        msg = f"The {log.issue_category} issue has been marked resolved."
        
        if log.status == 'Escalated':
            msg_type = "danger"
            title = "Issue Escalated"
            msg = f"URGENT: The {log.issue_category} issue has been ESCALATED to HOD."
            
        send_notification(log.student_id, title, msg, msg_type)
        
        return jsonify({"message": "Updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500
# ==========================================
# API: DETENTION - STUDENT VIEW
# ==========================================

@app.route('/api/detention/my_detentions', methods=['GET'])
@login_required
def get_my_detentions():
    try:
        user_id = request.args.get('user_id')
        
        # Get all active/pending detentions for this student
        records = (db.session.query(DetentionRecord, StaffProfile)
                   .join(StaffProfile, DetentionRecord.assigned_by_staff_id == StaffProfile.staff_id)
                   .filter(DetentionRecord.student_id == user_id)
                   .filter(DetentionRecord.status.in_(['Assigned', 'In_Review']))
                   .order_by(DetentionRecord.detention_id.desc())
                   .all())
        
        detentions = []
        for det, staff in records:
            detentions.append({
                "id": det.detention_id,
                "reason": det.reason,
                "task": det.assignment_details,
                "status": det.status,
                "submission_url": det.submission_doc_url,
                "assigned_by": staff.full_name
            })
            
        return jsonify({"detentions": detentions})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/detention/submit_task', methods=['POST'])
@login_required
def submit_detention_task():
    try:
        data = request.json
        detention = DetentionRecord.query.get(data.get('detention_id'))
        detention.submission_doc_url = data.get('submission_url')
        detention.status = 'In_Review'
        
        # NOTIFY STAFF
        student = StudentProfile.query.get(detention.student_id)
        send_notification(detention.assigned_by_staff_id, "Task Submitted", f"{student.full_name} has submitted their detention task.", "info", "/staff/detention_review")
        
        db.session.commit()
        return jsonify({"message": "Submission received"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# ==========================================
# API: DETENTION - TEACHER REVIEW
# ==========================================

@app.route('/staff/detention_review')
def render_detention_review():
    return render_template('detention_review.html')

# In app.py

@app.route('/api/detention/review_list', methods=['GET'])
@login_required
def get_detention_review_list():
    try:
        staff_id = request.args.get('user_id')
        staff_profile = StaffProfile.query.get(staff_id)
        
        # Determine the user's role for filtering
        is_class_teacher = ClassSection.query.filter_by(class_teacher_id=staff_id).first() is not None
        
        # 1. Fetch Records Assigned by THIS Subject Teacher that are 'In_Review'
        reviews = (db.session.query(DetentionRecord, StudentProfile)
                   .join(StudentProfile, DetentionRecord.student_id == StudentProfile.student_id)
                   .filter(DetentionRecord.assigned_by_staff_id == staff_id)
                   .filter(DetentionRecord.status == 'In_Review')
                   .all())
        
        review_list = []
        for det, student in reviews:
            review_list.append({
                "id": det.detention_id,
                "student_name": student.full_name,
                "roll": student.admission_number,
                "reason": det.reason,
                "submission_url": det.submission_doc_url,
                "assigned_task": det.assignment_details,
                "assigned_by_me": True
            })
            
        # 2. If Class Teacher, fetch all Active Detentions for oversight (Optional feature)
        # We will keep the primary review inbox focused on *their* assigned tasks for now.
        
        return jsonify({"reviews": review_list})

    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/detention/release', methods=['POST'])
@login_required
def release_detention():
    try:
        data = request.json
        detention = DetentionRecord.query.get(data.get('detention_id'))
        detention.status = data.get('final_status')
        
        # NOTIFY STUDENT
        msg = "You have been released from detention." if detention.status == 'Released' else "Your detention task needs revision."
        type_ = "success" if detention.status == 'Released' else "warning"
        send_notification(detention.student_id, f"Detention Update: {detention.status}", msg, type_)
        
        db.session.commit()
        return jsonify({"message": "Status Updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# ==========================================
# API: ADMIN APIs (Protected)
# ==========================================
@app.route('/api/admin/dashboard', methods=['GET'])
@login_required
@require_roles('Admin')
def get_admin_stats():
    try:
        today = date.today()

        scope_dept_ids = _get_admin_scope_dept_ids()
        
        # 1. Students (Active Only)
        st_q = (db.session.query(StudentProfile)
                .join(UserMaster, StudentProfile.student_id == UserMaster.user_id)
                .filter(UserMaster.is_active == True))

        if scope_dept_ids is not None:
            if not scope_dept_ids:
                total_students = 0
            else:
                st_q = (st_q.join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
                          .join(Specialization, ClassSection.spec_id == Specialization.id)
                          .filter(Specialization.dept_id.in_(scope_dept_ids)))

        total_students = st_q.count()
        
        # 2. Staff (Active Only, Excluding System Admin)
        staff_q = (db.session.query(StaffProfile)
                   .join(UserMaster, StaffProfile.staff_id == UserMaster.user_id)
                   .filter(UserMaster.is_active == True)
                   .filter(StaffProfile.full_name != "System Administrator"))

        if scope_dept_ids is not None:
            if not scope_dept_ids:
                total_staff = 0
            else:
                staff_q = staff_q.filter(StaffProfile.primary_department_id.in_(scope_dept_ids))

        total_staff = staff_q.count()
                       
        # 3. Classes
        if scope_dept_ids is None:
            total_classes = ClassSection.query.count()
        elif not scope_dept_ids:
            total_classes = 0
        else:
            total_classes = (db.session.query(ClassSection)
                             .join(Specialization, ClassSection.spec_id == Specialization.id)
                             .filter(Specialization.dept_id.in_(scope_dept_ids))
                             .count())
        
        # 4. Attendance Rate (Today)
        attendance_rate = 0
        sess_q = (db.session.query(SessionLog)
                  .filter(SessionLog.session_date == today))

        if scope_dept_ids is not None:
            if not scope_dept_ids:
                total_sessions = 0
            else:
                # Prefer subject dept; fall back to section->spec dept.
                from sqlalchemy import or_
                sess_q = (sess_q.join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                              .outerjoin(Subject, Subject.subject_id == WeeklySchedule.subject_id)
                              .outerjoin(ClassSection, ClassSection.section_id == WeeklySchedule.section_id)
                              .outerjoin(Specialization, Specialization.id == ClassSection.spec_id)
                              .filter(or_(
                                  Subject.dept_id.in_(scope_dept_ids),
                                  Specialization.dept_id.in_(scope_dept_ids),
                              )))
                total_sessions = sess_q.count()
        else:
            total_sessions = sess_q.count()
        if total_sessions > 0:
            pres_q = (db.session.query(AttendanceTransaction)
                      .join(SessionLog)
                      .filter(SessionLog.session_date == today)
                      .filter(AttendanceTransaction.status.in_(PRESENT_STATUSES)))

            if scope_dept_ids is not None and scope_dept_ids:
                from sqlalchemy import or_
                pres_q = (pres_q.join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                              .outerjoin(Subject, Subject.subject_id == WeeklySchedule.subject_id)
                              .outerjoin(ClassSection, ClassSection.section_id == WeeklySchedule.section_id)
                              .outerjoin(Specialization, Specialization.id == ClassSection.spec_id)
                              .filter(or_(
                                  Subject.dept_id.in_(scope_dept_ids),
                                  Specialization.dept_id.in_(scope_dept_ids),
                              )))

            total_presents = pres_q.count()
            
            # Denominator: Total students in conducted sessions (approx)
            # For true accuracy, we'd need session-wise strength, but this is a dashboard estimate
            # Let's use (Total Active Students * Sessions Conducted) as a baseline estimate
            if total_students > 0:
                max_possible = total_students * total_sessions # Rough estimate
                attendance_rate = round((total_presents / max_possible) * 100, 1)

        return jsonify({ 
            "stats": { 
                "students": total_students, 
                "staff": total_staff, 
                "classes": total_classes, 
                "attendance_rate": attendance_rate 
            } 
        })
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/student_distribution', methods=['GET'])
@login_required
@require_roles('Admin')
def get_student_distribution():
    """Get student distribution by class level for dashboard chart."""
    try:
        distribution = {}
        
        # Query active students grouped by class_level (via their section)
        scope_dept_ids = _get_admin_scope_dept_ids()

        q = (db.session.query(
                ClassSection.class_level,
                db.func.count(StudentProfile.student_id)
            )
            .join(StudentProfile, StudentProfile.current_section_id == ClassSection.section_id)
            .join(UserMaster, StudentProfile.student_id == UserMaster.user_id)
            .filter(UserMaster.is_active == True))

        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"No Students": 0})
            q = (q.join(Specialization, ClassSection.spec_id == Specialization.id)
                   .filter(Specialization.dept_id.in_(scope_dept_ids)))

        results = (q.group_by(ClassSection.class_level).all())
        
        for class_level, count in results:
            if class_level:
                distribution[class_level] = count
        
        # If no data, return empty dict
        if not distribution:
            distribution = {"No Students": 0}
        
        return jsonify(distribution)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/classes', methods=['GET'])
@login_required
@require_roles('Admin')
def get_admin_classes():
    try:
        scope_dept_ids = _get_admin_scope_dept_ids()

        classes_q = (db.session.query(ClassSection, StaffProfile)
                     .outerjoin(StaffProfile, ClassSection.class_teacher_id == StaffProfile.staff_id))

        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"classes": [], "staff_directory": []})
            classes_q = (classes_q.join(Specialization, ClassSection.spec_id == Specialization.id)
                                   .filter(Specialization.dept_id.in_(scope_dept_ids)))

        classes = classes_q.all()
        class_list = [{ "section_id": c.section_id, "name": c.name, "display_name": f"{c.class_level} - {c.name}", "teacher_id": c.class_teacher_id, "teacher_name": t.full_name if t else "Not Assigned" } for c, t in classes]

        staff_q = StaffProfile.query.with_entities(StaffProfile.staff_id, StaffProfile.full_name).order_by(StaffProfile.full_name)
        if scope_dept_ids is not None:
            staff_q = staff_q.filter(StaffProfile.primary_department_id.in_(scope_dept_ids))
        all_staff = staff_q.all()
        return jsonify({ "classes": class_list, "staff_directory": [{"id": s.staff_id, "name": s.full_name} for s in all_staff] })
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/assign_teacher', methods=['POST'])
@login_required
@require_roles('Admin')
def assign_class_teacher():
    try:
        data = request.json
        section_id = data.get('section_id') if data else None
        if section_id is None:
            return jsonify({"error": "section_id is required"}), 400
        section = db.session.get(ClassSection, section_id)
        if not section: return jsonify({"error": "Class not found"}), 404

        scope_dept_ids = _get_admin_scope_dept_ids()
        if scope_dept_ids is not None:
            deny = _ensure_section_in_scope(int(section_id))
            if deny:
                return deny

            staff_id = data.get('staff_id')
            if staff_id:
                staff = db.session.get(StaffProfile, staff_id)
                if not staff or not staff.primary_department_id or int(staff.primary_department_id) not in scope_dept_ids:
                    return jsonify({"error": "Out of scope"}), 403

        section.class_teacher_id = data.get('staff_id')
        db.session.commit()
        log_activity("Role Update", f"Assigned Class Teacher for {section.class_level}-{section.name}")
        return jsonify({"message": "Updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/coordinators', methods=['GET'])
@login_required
@require_roles('Admin')
def get_all_staff_coordinators():
    try:
        scope_dept_ids = _get_admin_scope_dept_ids()

        q = (db.session.query(StaffProfile, Department)
             .outerjoin(Department, StaffProfile.primary_department_id == Department.dept_id))

        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"staff": []})
            q = q.filter(StaffProfile.primary_department_id.in_(scope_dept_ids))

        staff_list = q.all()
        result = []
        for staff, dept in staff_list:
            result.append({ "id": staff.staff_id, "name": staff.full_name, "emp_code": staff.employee_code, "dept": dept.name if dept else "N/A", "is_coordinator": staff.is_event_coordinator, "is_amc_member": staff.is_amc_member, "is_amc_head": staff.is_amc_head })
        return jsonify({"staff": result})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/toggle_role', methods=['POST'])
@login_required
@require_roles('Admin')
def toggle_staff_role():
    try:
        data = request.json
        staff_id = data.get('staff_id') if data else None
        if staff_id is None:
            return jsonify({"error": "staff_id is required"}), 400
        staff = db.session.get(StaffProfile, staff_id)
        role = data.get('role_type') if data else None
        if not staff: return jsonify({"error": "Staff not found"}), 404

        scope_dept_ids = _get_admin_scope_dept_ids()
        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"error": "Admin department scope not configured"}), 403
            if not staff.primary_department_id or int(staff.primary_department_id) not in scope_dept_ids:
                return jsonify({"error": "Out of scope"}), 403
        
        if role == 'event': staff.is_event_coordinator = not staff.is_event_coordinator
        elif role == 'amc_member': staff.is_amc_member = not staff.is_amc_member
        elif role == 'amc_head': 
             if not staff.is_amc_head: 
                 curr = StaffProfile.query.filter_by(is_amc_head=True).first()
                 if curr: curr.is_amc_head = False
             staff.is_amc_head = not staff.is_amc_head
        db.session.commit()
        log_activity("Role Update", f"Toggled {role} for {staff.full_name}")
        return jsonify({"message": "Updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/faculty_list', methods=['GET'])
@login_required
@require_roles('Admin')
def get_admin_faculty_list():
    try:
        scope_dept_ids = _get_admin_scope_dept_ids()
        q = (db.session.query(StaffProfile, UserMaster, Department)
             .join(UserMaster, StaffProfile.staff_id == UserMaster.user_id)
             .outerjoin(Department, StaffProfile.primary_department_id == Department.dept_id))

        # Department Admins only see their own department.
        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"faculty": []})
            q = q.filter(StaffProfile.primary_department_id.in_(scope_dept_ids))

        data = q.all()
        
        # HOD Logic (Keep existing)
        hods = Department.query.filter(Department.hod_staff_id != None).all()
        hod_map = {h.hod_staff_id: h.dept_id for h in hods}
        
        result = []
        for staff, user, dept in data:
            if staff.full_name == "System Administrator": continue
            
            is_hod = staff.staff_id in hod_map
            dept_hod_locked = False
            if dept:
                current_dept_hod_id = Department.query.get(dept.dept_id).hod_staff_id
                if current_dept_hod_id and current_dept_hod_id != staff.staff_id:
                    dept_hod_locked = True

            result.append({
                "id": staff.staff_id,
                "name": staff.full_name,
                "email": staff.email_contact,
                "code": staff.employee_code,
                "dept": dept.name if dept else "Unassigned",
                "designation": staff.designation, # <--- SENDING TO FRONTEND
                "is_active": user.is_active,
                "is_hod": is_hod,
                "dept_hod_locked": dept_hod_locked
            })
            
        return jsonify({"faculty": result})
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/admin/archive_stats', methods=['GET'])
@login_required
@require_roles('Admin')
def get_archive_stats():
    try:
        year_str = request.args.get('year') 
        if not year_str: return jsonify({"error": "Year required"}), 400
        
        try:
            start_year = int(year_str.split('-')[0])
            start_date = date(start_year, 7, 1)
            end_date = date(start_year + 1, 6, 30)
        except: return jsonify({"error": "Invalid year format"}), 400

        # 1. Fetch Sessions in Range
        sessions = (db.session.query(SessionLog, WeeklySchedule, ClassSection)
                    .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                    .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
                    .filter(SessionLog.session_date >= start_date)
                    .filter(SessionLog.session_date <= end_date)
                    .filter(SessionLog.status == 'Conducted')
                    .all())
        
        if not sessions:
            return jsonify({ "year": year_str, "no_data": True, "message": "No records found for this period." })

        session_ids = [s[0].session_id for s in sessions]
        
        # 2. GLOBAL ATTENDANCE STATS
        total_txns = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(session_ids)).count()
        present_txns = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(session_ids), AttendanceTransaction.status.in_(PRESENT_STATUSES)).count()
        avg_att = round((present_txns / total_txns) * 100, 1) if total_txns > 0 else 0

        # 3. BEST PERFORMING CLASS (Attendance Based)
        # Map SectionID -> {total, present}
        class_perf_map = {}
        for sess, slot, sec in sessions:
            if sec.name not in class_perf_map: class_perf_map[sec.name] = {'total': 0, 'present': 0, 'level': sec.class_level}
            
            # Get txns for this specific session
            s_txns = AttendanceTransaction.query.filter_by(session_id=sess.session_id).count()
            s_pres = AttendanceTransaction.query.filter_by(session_id=sess.session_id).filter(AttendanceTransaction.status.in_(PRESENT_STATUSES)).count()
            
            class_perf_map[sec.name]['total'] += s_txns
            class_perf_map[sec.name]['present'] += s_pres

        best_class = "N/A"
        best_score = -1
        for name, data in class_perf_map.items():
            score = (data['present'] / data['total']) * 100 if data['total'] > 0 else 0
            if score > best_score:
                best_score = score
                best_class = f"{data['level']}-{name} ({round(score)}%)"

        # 4. FACULTY PERFORMANCE (Most Active)
        # Map TeacherID -> Count
        faculty_map = {}
        for sess, slot, sec in sessions:
            tid = sess.actual_teacher_id
            faculty_map[tid] = faculty_map.get(tid, 0) + 1
            
        top_faculty = "N/A"
        if faculty_map:
            top_id = max(faculty_map, key=faculty_map.get)
            staff = db.session.get(StaffProfile, top_id)
            if staff: top_faculty = f"{staff.full_name} ({faculty_map[top_id]} Sessions)"

        return jsonify({
            "year": year_str,
            "date_range": f"{start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}",
            "no_data": False,
            "student_summary": {
                "avg_attendance": avg_att,
                "best_class": best_class,
                "total_records": total_txns
            },
            "faculty_summary": {
                "total_sessions": len(sessions),
                "top_performer": top_faculty,
                "avg_daily_sessions": round(len(sessions) / 365, 1) # Rough estimate
            }
        })

    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/hod/archive_stats', methods=['GET'])
def get_hod_archive_stats():
    try:
        from sqlalchemy import or_
        from sqlalchemy.orm import aliased

        year_str = request.args.get('year')
        semester_no_raw = request.args.get('semester_no')
        user_id = request.args.get('user_id')
        if not year_str:
            return jsonify({"error": "Year required"}), 400
        if not user_id:
            return jsonify({"error": "user_id required"}), 400

        hod_dept = Department.query.filter_by(hod_staff_id=user_id).first()
        if not hod_dept:
            return jsonify({"error": "Not mapped as HOD"}), 403

        semester_no = None
        if semester_no_raw not in (None, '', 'null', 'None', 'all', 'All', 'ALL'):
            try:
                semester_no = int(semester_no_raw)
            except Exception:
                return jsonify({"error": "Invalid semester"}), 400
            if semester_no not in (1, 2):
                return jsonify({"error": "Invalid semester"}), 400

        try:
            start_year = int(year_str.split('-')[0])

            # Academic year assumed as Jul -> Jun.
            # Sem 1: Jul-Dec (start_year)
            # Sem 2: Jan-Jun (start_year + 1)
            if semester_no == 1:
                start_date = date(start_year, 7, 1)
                end_date = date(start_year, 12, 31)
            elif semester_no == 2:
                start_date = date(start_year + 1, 1, 1)
                end_date = date(start_year + 1, 6, 30)
            else:
                start_date = date(start_year, 7, 1)
                end_date = date(start_year + 1, 6, 30)
        except:
            return jsonify({"error": "Invalid year format"}), 400

        ScheduledTeacher = aliased(StaffProfile)
        ActualTeacher = aliased(StaffProfile)

        sessions = (
            db.session.query(SessionLog, WeeklySchedule, ClassSection)
            .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
            .join(Subject, Subject.subject_id == WeeklySchedule.subject_id)
            .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
            .outerjoin(ScheduledTeacher, WeeklySchedule.teacher_id == ScheduledTeacher.staff_id)
            .outerjoin(ActualTeacher, SessionLog.actual_teacher_id == ActualTeacher.staff_id)
            # Dept matching strategy (robust):
            # - Prefer Subject.dept_id when it exists
            # - Fallback to scheduled/actual teacher primary_department_id
            .filter(or_(
                Subject.dept_id == hod_dept.dept_id,
                ScheduledTeacher.primary_department_id == hod_dept.dept_id,
                ActualTeacher.primary_department_id == hod_dept.dept_id,
            ))
            .filter(SessionLog.session_date >= start_date)
            .filter(SessionLog.session_date <= end_date)
            .filter(SessionLog.status == 'Conducted')
            .all()
        )

        if not sessions:
            return jsonify({
                "year": year_str,
                "semester_no": semester_no,
                "dept_name": hod_dept.name,
                "no_data": True,
                "message": "No records found for this period."
            })

        session_ids = [s[0].session_id for s in sessions]

        total_txns = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(session_ids)).count()
        present_txns = AttendanceTransaction.query.filter(
            AttendanceTransaction.session_id.in_(session_ids),
            AttendanceTransaction.status.in_(PRESENT_STATUSES)
        ).count()
        avg_att = round((present_txns / total_txns) * 100, 1) if total_txns > 0 else 0

        class_perf_map = {}
        for sess, slot, sec in sessions:
            key = f"{sec.class_level}-{sec.name}"
            if key not in class_perf_map:
                class_perf_map[key] = {'total': 0, 'present': 0}

            s_txns = AttendanceTransaction.query.filter_by(session_id=sess.session_id).count()
            s_pres = (
                AttendanceTransaction.query.filter_by(session_id=sess.session_id)
                .filter(AttendanceTransaction.status.in_(PRESENT_STATUSES))
                .count()
            )
            class_perf_map[key]['total'] += s_txns
            class_perf_map[key]['present'] += s_pres

        best_class = "N/A"
        best_score = -1
        for key, data in class_perf_map.items():
            score = (data['present'] / data['total']) * 100 if data['total'] > 0 else 0
            if score > best_score:
                best_score = score
                best_class = f"{key} ({round(score)}%)"

        faculty_map = {}
        for sess, slot, sec in sessions:
            tid = sess.actual_teacher_id or slot.teacher_id
            if not tid:
                continue
            faculty_map[tid] = faculty_map.get(tid, 0) + 1

        top_faculty = "N/A"
        if faculty_map:
            top_id = max(faculty_map, key=faculty_map.get)
            staff = db.session.get(StaffProfile, top_id)
            if staff:
                top_faculty = f"{staff.full_name} ({faculty_map[top_id]} Sessions)"

        return jsonify({
            "year": year_str,
            "semester_no": semester_no,
            "dept_name": hod_dept.name,
            "date_range": f"{start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}",
            "no_data": False,
            "student_summary": {
                "avg_attendance": avg_att,
                "best_class": best_class,
                "total_records": total_txns
            },
            "faculty_summary": {
                "total_sessions": len(sessions),
                "top_performer": top_faculty,
                "avg_daily_sessions": round(len(sessions) / 365, 1)
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/archived_terms', methods=['GET'])
@login_required
@require_roles('Admin')
def api_admin_archived_terms():
    """List available archived academic years and semesters.

    Source: archived_allocation.term_name and archived_schedule.term_name.
    Expected term format: "YYYY-YY Sem N".
    """
    try:
        import re

        def parse_term_name(term_name: str):
            if not term_name:
                return None
            m = re.search(r'(?P<ay>\d{4}-\d{2})\s*Sem\s*(?P<sem>\d+)', term_name, re.IGNORECASE)
            if not m:
                return None
            ay = m.group('ay')
            sem_no = int(m.group('sem'))
            return ay, sem_no

        alloc_terms = [r[0] for r in (db.session.query(ArchivedAllocation.term_name)
                                     .filter(ArchivedAllocation.term_name != None)
                                     .distinct()
                                     .all())]
        sched_terms = [r[0] for r in (db.session.query(ArchivedSchedule.term_name)
                                     .filter(ArchivedSchedule.term_name != None)
                                     .distinct()
                                     .all())]

        by_ay = {}
        for t in set(alloc_terms + sched_terms):
            parsed = parse_term_name(t)
            if not parsed:
                continue
            ay, sem_no = parsed
            by_ay.setdefault(ay, set()).add(sem_no)

        def ay_key(ay: str):
            try:
                return int((ay or '').split('-')[0])
            except Exception:
                return -1

        out = []
        for ay in sorted(by_ay.keys(), key=ay_key, reverse=True):
            out.append({
                "academic_year": ay,
                "semesters": sorted(list(by_ay[ay]))
            })

        return jsonify({"academic_years": out})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/archived_data', methods=['GET'])
@login_required
@require_roles('Admin')
def api_admin_archived_data():
    """Fetch archived allocations and schedule filtered by academic year and semester.

    Query params:
      - academic_year: YYYY-YY (required)
      - semester_no: int (optional)

    Returns both archived_allocation and archived_schedule rows for matching term_name(s).
    """
    try:
        import re

        academic_year = (request.args.get('academic_year') or '').strip()
        semester_no = request.args.get('semester_no', type=int)
        if not academic_year:
            return jsonify({"error": "academic_year required"}), 400

        term_re = re.compile(r'(?P<ay>\d{4}-\d{2})\s*Sem\s*(?P<sem>\d+)', re.IGNORECASE)

        def matches(term_name: str) -> bool:
            if not term_name:
                return False
            m = term_re.search(term_name)
            if not m:
                return False
            ay = m.group('ay')
            sem = int(m.group('sem'))
            if ay != academic_year:
                return False
            if semester_no is not None and sem != int(semester_no):
                return False
            return True

        # Pull candidate term names for the academic year (cheap filter), then exact-match in Python
        alloc_candidates = [r[0] for r in (db.session.query(ArchivedAllocation.term_name)
                                           .filter(ArchivedAllocation.term_name.ilike(f"{academic_year}%"))
                                           .distinct()
                                           .all())]
        sched_candidates = [r[0] for r in (db.session.query(ArchivedSchedule.term_name)
                                           .filter(ArchivedSchedule.term_name.ilike(f"{academic_year}%"))
                                           .distinct()
                                           .all())]

        term_names = sorted({t for t in (alloc_candidates + sched_candidates) if matches(t)})
        if not term_names:
            return jsonify({
                "academic_year": academic_year,
                "semester_no": semester_no,
                "term_names": [],
                "allocations": [],
                "schedule": []
            })

        alloc_rows = (ArchivedAllocation.query
                      .filter(ArchivedAllocation.term_name.in_(term_names))
                      .order_by(ArchivedAllocation.section_id, ArchivedAllocation.subject_code, ArchivedAllocation.teacher_name)
                      .all())

        sched_rows = (ArchivedSchedule.query
                      .filter(ArchivedSchedule.term_name.in_(term_names))
                      .order_by(ArchivedSchedule.section_name, ArchivedSchedule.day, ArchivedSchedule.time_slot)
                      .all())

        allocations = []
        for r in alloc_rows:
            allocations.append({
                "term_name": r.term_name,
                "section_id": r.section_id,
                "subject_code": r.subject_code,
                "subject_name": r.subject_name,
                "teacher_name": r.teacher_name,
                "archived_on": r.archived_on.isoformat() if getattr(r, 'archived_on', None) else None,
            })

        schedule = []
        for r in sched_rows:
            schedule.append({
                "term_name": r.term_name,
                "section_name": r.section_name,
                "day": r.day,
                "time_slot": r.time_slot,
                "subject": r.subject,
                "teacher": r.teacher,
            })

        return jsonify({
            "academic_year": academic_year,
            "semester_no": semester_no,
            "term_names": term_names,
            "allocations": allocations,
            "schedule": schedule,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/revoke_hod', methods=['POST'])
@login_required
@require_roles('Admin')
def revoke_hod():
    try:
        data = request.json
        staff_id = data.get('staff_id')
        
        staff = StaffProfile.query.get(staff_id)
        if not staff: return jsonify({"error": "Staff not found"}), 404
        
        dept = Department.query.get(staff.primary_department_id)
        if not dept: return jsonify({"error": "No dept linked"}), 400
        
        if dept.hod_staff_id == staff_id:
            dept.hod_staff_id = None # Revoke
            db.session.commit()
            log_activity("Role Update", f"Revoked HOD role from {staff.full_name}")
            return jsonify({"message": "HOD Unassigned"}), 200
        else:
            return jsonify({"error": "User is not HOD"}), 400
            
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/add_faculty', methods=['POST'])
@login_required
@require_roles('Admin')
def add_single_faculty():
    try:
        data = request.json
        email = data.get('email')
        if UserMaster.query.filter_by(username=email).first(): return jsonify({"error": "Email exists"}), 400

        scope_dept_ids = _get_admin_scope_dept_ids()
        
        new_uuid = str(uuid.uuid4())
        db.session.add(UserMaster(user_id=new_uuid, username=email, password_hash=generate_password_hash("Staff@123"), user_type='Staff', is_active=True))

        # Department Admins cannot create faculty outside their scope.
        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"error": "Admin department scope not configured"}), 403
            dept = Department.query.get(scope_dept_ids[0])
            if not dept:
                return jsonify({"error": "Scoped department not found"}), 400
        else:
            dept = Department.query.filter_by(name=data.get('dept')).first()
            if not dept:
                dept = Department(name=data.get('dept'))
                db.session.add(dept)
                db.session.flush()
        
        db.session.add(StaffProfile(
            staff_id=new_uuid, 
            full_name=data.get('name'), 
            employee_code=data.get('code'), 
            email_contact=email, 
            primary_department_id=dept.dept_id,
            designation=data.get('designation', 'Assistant Professor') # <--- SAVING HERE
        ))
        
        db.session.commit()
        log_activity("Faculty Added", f"Created profile for {data.get('name')}")
        return jsonify({"message": "Added"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/archive_faculty', methods=['POST'])
@login_required
@require_roles('Admin')
def archive_faculty():
    try:
        data = request.json
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400

        scope_dept_ids = _get_admin_scope_dept_ids()
        user = db.session.get(UserMaster, user_id)
        staff = db.session.get(StaffProfile, user_id)
        if not user: return jsonify({"error": "User not found"}), 404

        # Department Admins cannot modify faculty outside their scope.
        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"error": "Admin department scope not configured"}), 403
            if not staff or staff.primary_department_id not in scope_dept_ids:
                return jsonify({"error": "Out of scope"}), 403

        user.is_active = (data.get('action') == 'activate')
        if data.get('action') == 'archive':
            classes = ClassSection.query.filter_by(class_teacher_id=user.user_id).all()
            for cls in classes: cls.class_teacher_id = None
        db.session.commit()
        staff_name = staff.full_name if staff else data.get('user_id')
        log_activity("Faculty Status", f"{data.get('action').title()}d {staff_name}")
        return jsonify({"message": "Updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500


# In app.py

@app.route('/admin/manage_timetable')
def render_admin_timetable():
    return render_template('admin_timetable.html')

# --- SCHEDULER HELPER FUNCTIONS ---

def get_time_slots():
    """Returns standard time slots excluding breaks."""
    # Format: (Start, End, Duration_Hours, Is_Project_Slot)
    # Breaks: 10:35-10:50 (Short), 12:40-1:40 (Lunch)
    # 3:40-4:30 is Mentor/Library (We won't auto-schedule lectures there usually, or treat as slot 8)
    
    slots = [
        ("08:45", "09:40", 1, False), # Slot 1
        ("09:40", "10:35", 1, False), # Slot 2
        # Break 10:35-10:50
        ("10:50", "11:45", 1, False), # Slot 3
        ("11:45", "12:40", 1, False), # Slot 4
        # Lunch 12:40-13:40
        ("13:40", "14:40", 1, False), # Slot 5
        ("14:40", "15:40", 1, True),  # Slot 6 (Potential Project)
        ("15:40", "16:30", 1, True)   # Slot 7 (Mentor/Lib/Project)
    ]
    return slots

def is_resource_free(day, start_str, end_str, teacher_id, section_id, batch=None):
    """Checks if Teacher and Students are free."""
    start = datetime.strptime(start_str, "%H:%M").time()
    end = datetime.strptime(end_str, "%H:%M").time()

    # 1. Check Teacher Availability (Global)
    teacher_busy = WeeklySchedule.query.filter_by(day_of_week=day, teacher_id=teacher_id).filter(
        WeeklySchedule.start_time < end, WeeklySchedule.end_time > start
    ).first()
    if teacher_busy: return False

    # 2. Check Section Availability
    # If Batch is None (Lecture), whole class must be free.
    # If Batch is 'A', check if 'A' is busy (or if whole class is busy).
    
    section_query = WeeklySchedule.query.filter_by(day_of_week=day, section_id=section_id).filter(
        WeeklySchedule.start_time < end, WeeklySchedule.end_time > start
    )
    
    conflict = section_query.first()
    if conflict:
        # If existing slot is Whole Class, then conflict!
        if not conflict.target_batch: return False
        
        # If existing is Batch A, and we want Batch A, conflict!
        if batch and conflict.target_batch == batch: return False
        
        # If existing is Batch A, and we want Batch B, NO conflict (Parallel session!)
        if batch and conflict.target_batch != batch: return True
        
        # If existing is Batch A, and we want Whole Class, conflict!
        if not batch: return False

    return True

def get_free_room(day, start, end, required_type, min_capacity):
    # 1. Get all rooms of correct type and capacity
    candidates = RoomMaster.query.filter_by(room_type=required_type).filter(RoomMaster.capacity >= min_capacity).all()
    
    for room in candidates:
        # 2. Check if this room is busy
        busy = WeeklySchedule.query.filter_by(day_of_week=day, room_id=room.room_id).filter(
            WeeklySchedule.start_time < end, WeeklySchedule.end_time > start
        ).first()
        
        if not busy:
            return room
            
    return None

# In app.py

# In app.py

# --- 1. SCHEDULER CONFIGURATION ---
def get_time_slots():
    """
    Returns available teaching slots as Dictionaries.
    Breaks are represented by the gaps between end of one slot and start of next.
    """
    return [
        # Morning Session
        {"start": "08:45", "end": "09:40", "id": 1},
        {"start": "09:40", "end": "10:35", "id": 2},
        # Short Break (10:35 - 10:50) - Implied gap
        {"start": "10:50", "end": "11:45", "id": 3},
        {"start": "11:45", "end": "12:40", "id": 4},
        # Lunch Break (12:40 - 13:40) - CRITICAL GAP
        {"start": "13:40", "14:40": "14:40", "end": "14:40", "id": 5}, # Using standard key
        {"start": "14:40", "end": "15:40", "id": 6},
        {"start": "15:40", "end": "16:30", "id": 7}
    ]

# --- 2. CONFLICT CHECKER ---
def is_resource_free(day, start_str, end_str, teacher_id, section_id, batch=None):
    start = datetime.strptime(start_str, "%H:%M").time()
    end = datetime.strptime(end_str, "%H:%M").time()

    # A. Teacher Check
    if WeeklySchedule.query.filter_by(day_of_week=day, teacher_id=teacher_id).filter(
        WeeklySchedule.start_time < end, WeeklySchedule.end_time > start
    ).first(): return False

    # B. Class/Batch Check
    conflict = WeeklySchedule.query.filter_by(day_of_week=day, section_id=section_id).filter(
        WeeklySchedule.start_time < end, WeeklySchedule.end_time > start
    ).first()

    if conflict:
        # If the existing slot is for the Whole Class, it's a conflict
        if not conflict.target_batch: return False
        # If we want Whole Class but slot has a Batch, conflict
        if not batch: return False
        # If batches match (Batch A vs Batch A), conflict
        if conflict.target_batch == batch: return False
        # If batches differ (Batch A vs Batch B), ALLOW (Parallel Lab)
        if conflict.target_batch != batch: return True

    return True

# --- 3. MAIN GENERATOR ---
@app.route('/api/admin/generate_timetable', methods=['POST'])
@login_required
@require_roles('Admin')
def generate_timetable():
    try:
        data = request.json or {}
        target_section_id = data.get('section_id')  # Optional: generate for specific section only

        # Track versions created per section
        version_map = {}  # section_id -> version_id

        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        time_slots = get_time_slots()

        faculty_daily_load = {}
        schedule_log = []
        failed_items = []

        sections = ClassSection.query.all()
        if target_section_id:
            sections = [s for s in sections if s.section_id == int(target_section_id)]

        for section in sections:
            # Create draft version for this section
            existing_draft = TimetableVersion.query.filter_by(
                section_id=section.section_id,
                status='Draft'
            ).first()

            if existing_draft:
                # Clear existing draft slots (will be replaced)
                WeeklySchedule.query.filter_by(version_id=existing_draft.version_id).delete()
                draft_version = existing_draft
                # Update metadata
                draft_version.version_label = f"Auto-Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                draft_version.source_type = 'auto_generate'
                draft_version.created_by_id = current_user.user_id
            else:
                max_version = db.session.query(db.func.max(TimetableVersion.version_number)).filter_by(section_id=section.section_id).scalar() or 0
                draft_version = TimetableVersion(
                    section_id=section.section_id,
                    version_number=max_version + 1,
                    version_label=f"Auto-Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    status='Draft',
                    created_by_id=current_user.user_id,
                    source_type='auto_generate'
                )
                db.session.add(draft_version)
                db.session.flush()

            version_map[section.section_id] = draft_version.version_id

            # Get Student Count for Room Capacity Check
            class_strength = StudentProfile.query.filter_by(current_section_id=section.section_id).count()
            if class_strength == 0: class_strength = 60

            allocations = (db.session.query(SubjectAllocation, Subject)
                           .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                           .filter(SubjectAllocation.section_id == section.section_id)
                           .all())

            queue = []
            for alloc, subject in allocations:
                # --- NEW FILTER: EXCLUDE MDM-MINOR ---
                if "MDM-Minor" in subject.name:
                    continue # Skip this subject entirely
                # -------------------------------------

                # Lectures
                for _ in range(subject.l_count):
                    queue.append({ "sub": subject, "teacher": alloc.teacher_id, "type": "Lecture", "batch": None, "duration": 1 })

                # Tutorials
                for _ in range(subject.t_count):
                    queue.append({ "sub": subject, "teacher": alloc.teacher_id, "type": "Tutorial", "batch": None, "duration": 1 })

                # Practicals
                p_sessions = subject.p_count // 2
                for _ in range(p_sessions):
                    if section.name == "SMAD":
                        queue.append({ "sub": subject, "teacher": alloc.teacher_id, "type": "Practical", "batch": None, "duration": 2 })
                    else:
                        queue.append({ "sub": subject, "teacher": alloc.teacher_id, "type": "Practical", "batch": "Batch A", "duration": 2 })
                        queue.append({ "sub": subject, "teacher": alloc.teacher_id, "type": "Practical", "batch": "Batch B", "duration": 2 })

            # Prioritize Labs
            queue.sort(key=lambda x: 0 if x['type'] == 'Practical' else 1)

            # --- PLACEMENT ALGORITHM ---
            for item in queue:
                placed = False
                required_room_type = 'Laboratory' if item['type'] == 'Practical' else ('Tutorial Room' if item['type'] == 'Tutorial' else 'Classroom')
                required_capacity = class_strength if not item['batch'] else (class_strength // 2)

                # Try 3 Passes
                for _ in range(3):
                    if placed: break
                    for day in days:
                        if placed: break

                        # LY Project Rule
                        if section.class_level == 'LY' and "Project" in item['sub'].name and day != 'Friday': continue

                        for i, slot in enumerate(time_slots):
                            if placed: break

                            # Duration Check
                            if i + item['duration'] > len(time_slots): continue

                            # Lunch Guard (No 2hr lab starting at 11:45)
                            if item['duration'] == 2 and slot['id'] == 4: continue

                            start_str = slot['start']
                            end_slot_idx = i + item['duration'] - 1
                            end_str = time_slots[end_slot_idx]['end']

                            # Load Check
                            if faculty_daily_load.get((item['teacher'], day), 0) + item['duration'] > 4: continue

                            # Conflict Check (uses active versions + current draft being built)
                            if is_resource_free(day, start_str, end_str, item['teacher'], section.section_id, item['batch']):

                                # Room Check
                                start_obj = datetime.strptime(start_str, "%H:%M").time()
                                end_obj = datetime.strptime(end_str, "%H:%M").time()
                                assigned_room = get_free_room(day, start_obj, end_obj, required_room_type, required_capacity)

                                if assigned_room:
                                    new_slot = WeeklySchedule(
                                        section_id=section.section_id, subject_id=item['sub'].subject_id, teacher_id=item['teacher'],
                                        day_of_week=day, start_time=start_obj, end_time=end_obj,
                                        session_type=item['type'], target_batch=item['batch'],
                                        room_id=assigned_room.room_id,
                                        version_id=draft_version.version_id  # Link to draft version
                                    )
                                    db.session.add(new_slot)
                                    faculty_daily_load[(item['teacher'], day)] = faculty_daily_load.get((item['teacher'], day), 0) + item['duration']
                                    placed = True
                                    batch_txt = f"[{item['batch']}]" if item['batch'] else ""
                                    schedule_log.append(f"Scheduled: {section.name} | {day} {start_str} | {item['sub'].name} | Room: {assigned_room.room_number}")
                                    break

                if not placed:
                    failed_items.append(f"{section.name}: {item['sub'].name} ({item['type']})")

        db.session.commit()

        full_log = schedule_log + ["--- FAILED ITEMS ---"] + failed_items + [
            "",
            "=== IMPORTANT ===",
            "Schedule generated as DRAFT.",
            "Go to Version Manager to preview and publish."
        ]
        return jsonify({
            "message": "Generated as DRAFT",
            "logs": full_log,
            "versions_created": version_map,
            "note": "Use Version Manager to preview and publish the draft."
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"Scheduler Error: {e}")
        return jsonify({"error": str(e)}), 500
# ==========================================
# API: ELECTIVE MANAGEMENT (UPDATED)
# ==========================================
@app.route('/api/electives/init', methods=['POST'])
def init_electives():
    try:
        data = request.json
        section_id = data.get('section_id')
        subject_ids = data.get('subject_ids')
        
        # Reset offerings
        ElectiveOffering.query.filter_by(section_id=section_id).delete()
        for sub_id in subject_ids:
            db.session.add(ElectiveOffering(section_id=section_id, subject_id=sub_id, status='Open'))
            
        db.session.commit()
        return jsonify({"message": "Elective selection opened."}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/electives/live_stats', methods=['GET'])
def get_elective_stats():
    try:
        section_id = request.args.get('section_id')
        offerings = ElectiveOffering.query.filter_by(section_id=section_id).all()
        
        stats = []
        total_students = StudentProfile.query.filter_by(current_section_id=section_id).count()
        total_selected = 0
        
        for off in offerings:
            subject = Subject.query.get(off.subject_id)
            
            query_result = (db.session.query(StudentProfile, StudentElective.status)
                            .join(StudentElective, StudentProfile.student_id == StudentElective.student_id)
                            .filter(StudentElective.subject_id == off.subject_id)
                            .filter(StudentProfile.current_section_id == section_id)
                            .all())
            
            count = len(query_result)
            total_selected += count
            
            student_list = []
            for student, status in query_result:
                student_list.append({
                    "id": student.student_id,
                    "name": student.full_name,
                    "roll": student.admission_number,
                    "status": status
                })

            stats.append({
                "subject_id": subject.subject_id,
                "subject_name": subject.name,
                "code": subject.code,
                "type": subject.subject_type, # <--- NEW: Added Type
                "count": count,
                "status": off.status,
                "is_danger": count < 12,
                "students": student_list
            })
            
        return jsonify({
            "stats": stats, 
            "progress": f"{total_selected}/{total_students} Students Selected"
        })
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/electives/manage_enrollment', methods=['POST'])
def manage_elective_enrollment():
    try:
        data = request.json
        student_ids = data.get('student_ids') # List of IDs
        subject_id = data.get('subject_id')
        action = data.get('action') # 'Approve', 'Reject', 'Move'
        new_subject_id = data.get('new_subject_id') # Only for Move

        if not student_ids: return jsonify({"error": "No students selected"}), 400

        for s_id in student_ids:
            entry = StudentElective.query.filter_by(student_id=s_id, subject_id=subject_id).first()
            
            if action == 'Move' and new_subject_id:
                # Delete old, create new
                if entry: db.session.delete(entry)
                # Add new approved entry
                new_entry = StudentElective(student_id=s_id, subject_id=new_subject_id, status='Approved')
                db.session.add(new_entry)
                
            elif action == 'Reject':
                # Delete entry so they can choose again (or keep as Rejected record?)
                # Let's delete to allow re-selection logic or explicit "Rejected" status
                if entry: 
                    entry.status = 'Rejected'
                    # Alternatively: db.session.delete(entry) if you want them to disappear
            
            elif action == 'Approve':
                if entry: entry.status = 'Approved'

        db.session.commit()
        return jsonify({"message": "Updated successfully"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500


# ==========================================
# API: SEMESTER-BASED ELECTIVES (WINDOWS)
# ==========================================

@app.route('/api/admin/semester_structure/electives', methods=['GET'])
def api_admin_semester_structure_electives():
    """Return elective subjects from semester course structure for a given section + target semester.

    This is the pre-registration source of truth (independent of faculty allocation).
    """
    try:
        section_id = request.args.get('section_id', type=int)
        target_semester_no = request.args.get('target_semester_no', type=int)
        if not section_id or not target_semester_no:
            return jsonify({"error": "section_id and target_semester_no are required"}), 400

        section = ClassSection.query.get(section_id)
        if not section:
            return jsonify({"error": "Class section not found"}), 404

        rows = (db.session.query(Subject)
                .join(SemesterCourseStructure, SemesterCourseStructure.subject_id == Subject.subject_id)
                .filter(SemesterCourseStructure.section_id == section_id)
                .filter(SemesterCourseStructure.semester_no == target_semester_no)
                .order_by(Subject.subject_type, Subject.name)
                .all())

        grouped = {}
        for s in rows:
            if not is_elective_type(s.subject_type):
                continue
            grouped.setdefault(s.subject_type, []).append({
                "id": s.subject_id,
                "name": s.name,
                "code": s.code,
                "type": s.subject_type,
            })

        return jsonify({
            "section_id": section_id,
            "section": f"{section.class_level} - {section.name}",
            "target_semester_no": target_semester_no,
            "groups": grouped,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/elective_windows/open', methods=['POST'])
def api_admin_open_elective_windows():
    """Open elective windows for a section and target semester.

    Body:
      { section_id, target_semester_no, subject_ids: [], min_batch_size?: 12 }

    Creates 1 window per bucket (Subject.subject_type) found in subject_ids.
    Creates ElectiveOffering entries linked to the window.
    """
    try:
        data = request.json or {}
        section_id = int(data.get('section_id')) if data.get('section_id') else None
        target_semester_no = int(data.get('target_semester_no')) if data.get('target_semester_no') else None
        subject_ids = data.get('subject_ids') or []
        min_batch_size = int(data.get('min_batch_size') or 12)

        if not section_id or not target_semester_no:
            return jsonify({"error": "section_id and target_semester_no are required"}), 400
        if not isinstance(subject_ids, list) or len(subject_ids) == 0:
            return jsonify({"error": "subject_ids must be a non-empty list"}), 400
        if target_semester_no < 1 or target_semester_no > 8:
            return jsonify({"error": "target_semester_no must be between 1 and 8"}), 400

        section = ClassSection.query.get(section_id)
        if not section:
            return jsonify({"error": "Class section not found"}), 404

        subjects = Subject.query.filter(Subject.subject_id.in_(subject_ids)).all()
        if len(subjects) != len(set(subject_ids)):
            return jsonify({"error": "One or more subject_ids are invalid"}), 400

        # Group by bucket/type
        buckets = {}
        for s in subjects:
            if not is_elective_type(s.subject_type):
                return jsonify({"error": f"Subject '{s.code}' is not an elective type"}), 400
            buckets.setdefault(s.subject_type, []).append(s)

        created = []
        for bucket, subs in buckets.items():
            # Clear any existing OPEN/EXTENSION window for same (section, target_semester, bucket)
            existing_windows = (ElectiveWindow.query
                                .filter_by(section_id=section_id, target_semester_no=target_semester_no, bucket=bucket)
                                .filter(ElectiveWindow.status.in_(['Open', 'Extension']))
                                .all())
            for w in existing_windows:
                # Close them hard; keep history but prevent multiple actives for same bucket.
                w.status = 'Closed'
                w.closed_at = datetime.utcnow()
                ElectiveOffering.query.filter_by(window_id=w.id).update({"status": "Closed"})

            window = ElectiveWindow(
                section_id=section_id,
                target_semester_no=target_semester_no,
                bucket=bucket,
                status='Open',
                min_batch_size=min_batch_size,
            )
            db.session.add(window)
            db.session.flush()

            # Reset offerings for this new window
            for s in subs:
                db.session.add(ElectiveOffering(section_id=section_id, subject_id=s.subject_id, window_id=window.id, status='Open'))

            created.append({"window_id": window.id, "bucket": bucket, "subject_count": len(subs)})

        db.session.commit()
        return jsonify({
            "message": "Elective windows opened.",
            "section": f"{section.class_level} - {section.name}",
            "target_semester_no": target_semester_no,
            "windows": created,
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


def _window_offering_counts(window_id: int):
    window = ElectiveWindow.query.get(window_id)
    if not window:
        return None, []

    offerings = ElectiveOffering.query.filter_by(window_id=window_id).all()
    counts = []
    for off in offerings:
        subject = Subject.query.get(off.subject_id)
        c = (StudentElective.query
             .filter_by(window_id=window_id, subject_id=off.subject_id)
             .join(StudentProfile, StudentProfile.student_id == StudentElective.student_id)
             .filter(StudentProfile.current_section_id == window.section_id)
             .count())
        counts.append({
            "offering_id": off.offering_id,
            "subject_id": off.subject_id,
            "subject_name": subject.name if subject else str(off.subject_id),
            "code": subject.code if subject else "-",
            "bucket": window.bucket,
            "count": c,
            "status": off.status,
        })
    return window, counts


@app.route('/api/admin/elective_windows/close', methods=['POST'])
def api_admin_close_or_finalize_window():
    """Close or finalize an elective window.

    Body:
      { window_id, finalize?: false }

    - If finalize=false and any offering is < min_batch_size: set window to Extension.
    - If finalize=true: perform auto-balance, mark underfilled offerings Dropped if possible, then close.
    """
    try:
        data = request.json or {}
        window_id = int(data.get('window_id')) if data.get('window_id') else None
        finalize = bool(data.get('finalize'))
        if not window_id:
            return jsonify({"error": "window_id required"}), 400

        window, counts = _window_offering_counts(window_id)
        if not window:
            return jsonify({"error": "Window not found"}), 404

        min_batch = int(window.min_batch_size or 12)
        underfilled = [c for c in counts if c['status'] == 'Open' and c['count'] < min_batch]

        if (not finalize) and underfilled:
            window.status = 'Extension'
            db.session.commit()
            return jsonify({
                "message": "Window moved to Extension due to underfilled electives.",
                "window_id": window.id,
                "status": window.status,
                "min_batch_size": min_batch,
                "underfilled": underfilled,
            }), 200

        # Finalize: auto-balance and close.
        # 1) Determine current selections in this window
        section_students = StudentProfile.query.filter_by(current_section_id=window.section_id).order_by(StudentProfile.admission_number).all()
        student_ids = [s.student_id for s in section_students]

        selections = (StudentElective.query
                      .filter(StudentElective.window_id == window.id)
                      .filter(StudentElective.student_id.in_(student_ids))
                      .all())
        selected_by_student = {se.student_id: se for se in selections}

        # 2) Compute initial counts per offered subject
        offered = ElectiveOffering.query.filter_by(window_id=window.id).all()
        offered_subject_ids = [o.subject_id for o in offered]

        # Pre-count
        subject_counts = {sid: 0 for sid in offered_subject_ids}
        for se in selections:
            if se.subject_id in subject_counts:
                subject_counts[se.subject_id] += 1

        # 3) Decide which offerings to drop (if possible)
        to_drop = [sid for sid, c in subject_counts.items() if c < min_batch]
        active_subject_ids = [sid for sid in offered_subject_ids if sid not in to_drop]
        if not active_subject_ids:
            # Can't drop all; keep all active
            to_drop = []
            active_subject_ids = list(offered_subject_ids)

        # Mark offerings
        for off in offered:
            if off.subject_id in to_drop:
                off.status = 'Dropped'
            else:
                off.status = 'Closed'

        # 4) Build a list of students needing assignment or reassignment
        def _is_invalid_choice(se: StudentElective | None) -> bool:
            if se is None:
                return True
            if se.subject_id not in active_subject_ids:
                return True
            return False

        needing = []
        for s in section_students:
            se = selected_by_student.get(s.student_id)
            if _is_invalid_choice(se):
                needing.append(s.student_id)

        # 5) Recompute counts using only active subjects
        active_counts = {sid: 0 for sid in active_subject_ids}
        for s in section_students:
            se = selected_by_student.get(s.student_id)
            if se and se.subject_id in active_counts:
                active_counts[se.subject_id] += 1

        # 6) Assign students to smallest-count subject each time (equal distribution)
        def pick_least_loaded():
            return sorted(active_counts.items(), key=lambda kv: (kv[1], kv[0]))[0][0]

        assigned = 0
        for sid in needing:
            target_subject_id = pick_least_loaded()
            existing = selected_by_student.get(sid)
            if existing:
                existing.subject_id = target_subject_id
                existing.status = 'Approved'
            else:
                db.session.add(StudentElective(student_id=sid, subject_id=target_subject_id, window_id=window.id, status='Approved'))
            selected_by_student[sid] = selected_by_student.get(sid)  # no-op; keeps dict stable
            active_counts[target_subject_id] += 1
            assigned += 1

        # 7) Approve all remaining selections in this window
        StudentElective.query.filter_by(window_id=window.id).update({"status": "Approved"})

        # 8) Close window
        window.status = 'Closed'
        window.closed_at = datetime.utcnow()

        db.session.commit()
        return jsonify({
            "message": "Window finalized and closed.",
            "window_id": window.id,
            "status": window.status,
            "min_batch_size": min_batch,
            "dropped_subject_ids": to_drop,
            "auto_assigned": assigned,
            "final_counts": [{"subject_id": sid, "count": c} for sid, c in sorted(active_counts.items())],
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/elective_windows/update_subjects', methods=['POST'])
def api_admin_update_window_subjects():
    """Edit an existing elective window's offerings.

    Allowed only while window is Open/Extension.

    Body: { window_id, subject_ids: [] }
    - Replaces offerings for this window.
    - Clears student selections that point to removed subjects (so they must re-pick).
    """
    try:
        data = request.json or {}
        window_id = int(data.get('window_id')) if data.get('window_id') else None
        subject_ids = data.get('subject_ids') or []
        if not window_id:
            return jsonify({"error": "window_id required"}), 400
        if not isinstance(subject_ids, list) or len(subject_ids) == 0:
            return jsonify({"error": "subject_ids must be a non-empty list"}), 400

        window = ElectiveWindow.query.get(window_id)
        if not window:
            return jsonify({"error": "Window not found"}), 404
        if window.status not in ['Open', 'Extension']:
            return jsonify({"error": "Cannot edit a closed window"}), 403

        subjects = Subject.query.filter(Subject.subject_id.in_(subject_ids)).all()
        if len(subjects) != len(set(subject_ids)):
            return jsonify({"error": "One or more subject_ids are invalid"}), 400
        for s in subjects:
            if not is_elective_type(s.subject_type):
                return jsonify({"error": f"Subject '{s.code}' is not an elective type"}), 400
            if s.subject_type != window.bucket:
                return jsonify({"error": f"Subject '{s.code}' is not in bucket {window.bucket}"}), 400

        # Replace offerings
        ElectiveOffering.query.filter_by(window_id=window.id).delete()
        for s in subjects:
            db.session.add(ElectiveOffering(section_id=window.section_id, subject_id=s.subject_id, window_id=window.id, status='Open'))

        # Remove selections for subjects no longer offered
        offered_set = set(int(x) for x in subject_ids)
        stale = (StudentElective.query
                 .filter_by(window_id=window.id)
                 .filter(~StudentElective.subject_id.in_(offered_set))
                 .all())
        removed = 0
        for se in stale:
            db.session.delete(se)
            removed += 1

        db.session.commit()
        return jsonify({
            "message": "Window updated.",
            "window_id": window.id,
            "bucket": window.bucket,
            "offering_count": len(subject_ids),
            "selections_cleared": removed,
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@app.route('/api/student/elective_windows', methods=['GET'])
def api_student_elective_windows():
    """List open/extension elective windows and options for a student (scoped by section)."""
    try:
        user_id = request.args.get('user_id')
        student = StudentProfile.query.get(user_id)
        if not student or not student.current_section_id:
            return jsonify({"windows": []})

        windows = (ElectiveWindow.query
                   .filter_by(section_id=student.current_section_id)
                   .filter(ElectiveWindow.status.in_(['Open', 'Extension']))
                   .order_by(ElectiveWindow.target_semester_no, ElectiveWindow.bucket)
                   .all())

        out = []
        for w in windows:
            offerings = (db.session.query(ElectiveOffering, Subject)
                         .join(Subject, Subject.subject_id == ElectiveOffering.subject_id)
                         .filter(ElectiveOffering.window_id == w.id)
                         .filter(ElectiveOffering.status == 'Open')
                         .order_by(Subject.name)
                         .all())
            current = (StudentElective.query
                       .filter_by(student_id=student.student_id, window_id=w.id)
                       .first())
            out.append({
                "window_id": w.id,
                "target_semester_no": w.target_semester_no,
                "bucket": w.bucket,
                "status": w.status,
                "min_batch_size": int(w.min_batch_size or 12),
                "selection": current.subject_id if current else None,
                "options": [{"id": s.subject_id, "name": s.name, "code": s.code} for _, s in offerings],
            })

        return jsonify({"windows": out})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/elective_windows/live_dashboard', methods=['GET'])
def api_admin_elective_windows_live_dashboard():
    """Admin live dashboard for elective windows.

    Groups by section and returns each open/extension window and its offerings with counts.
    """
    try:
        windows = (ElectiveWindow.query
                   .filter(ElectiveWindow.status.in_(['Open', 'Extension']))
                   .order_by(ElectiveWindow.section_id, ElectiveWindow.target_semester_no, ElectiveWindow.bucket)
                   .all())

        by_section = {}
        for w in windows:
            by_section.setdefault(w.section_id, []).append(w)

        dashboard = []
        for section_id, sec_windows in by_section.items():
            section = ClassSection.query.get(section_id)
            if not section:
                continue

            sec_out = {
                "section_id": section_id,
                "class_name": f"{section.class_level} - {section.name}",
                "windows": []
            }

            for w in sec_windows:
                offerings = (db.session.query(ElectiveOffering, Subject)
                             .join(Subject, Subject.subject_id == ElectiveOffering.subject_id)
                             .filter(ElectiveOffering.window_id == w.id)
                             .filter(ElectiveOffering.status == 'Open')
                             .order_by(Subject.name)
                             .all())

                electives_data = []
                for off, subj in offerings:
                    # Promotion-safe: selections are tied to the window, not to the student's current section.
                    count = (StudentElective.query
                             .filter_by(window_id=w.id, subject_id=subj.subject_id)
                             .count())
                    electives_data.append({
                        "window_id": w.id,
                        "target_semester_no": w.target_semester_no,
                        "bucket": w.bucket,
                        "subject_id": subj.subject_id,
                        "name": subj.name,
                        "type": subj.subject_type,
                        "count": count,
                        "is_danger": count < int(w.min_batch_size or 12),
                    })

                sec_out["windows"].append({
                    "window_id": w.id,
                    "target_semester_no": w.target_semester_no,
                    "bucket": w.bucket,
                    "status": w.status,
                    "min_batch_size": int(w.min_batch_size or 12),
                    "electives": electives_data,
                })

            dashboard.append(sec_out)

        return jsonify({"dashboard": dashboard})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/elective_windows/live_stats', methods=['GET'])
def api_elective_window_live_stats():
    """Detailed stats for a specific elective window (students per subject)."""
    try:
        window_id = request.args.get('window_id', type=int)
        if not window_id:
            return jsonify({"error": "window_id required"}), 400

        window = ElectiveWindow.query.get(window_id)
        if not window:
            return jsonify({"error": "Window not found"}), 404

        offerings = (db.session.query(ElectiveOffering, Subject)
                     .join(Subject, Subject.subject_id == ElectiveOffering.subject_id)
                     .filter(ElectiveOffering.window_id == window.id)
                     .filter(ElectiveOffering.status == 'Open')
                     .order_by(Subject.name)
                     .all())

        stats = []
        # Promotion-safe: we can reliably count only submitted selections for the window.
        total_selected = (db.session.query(db.func.count(db.distinct(StudentElective.student_id)))
                  .filter(StudentElective.window_id == window.id)
                  .scalar()) or 0
        total_students = total_selected
        min_batch = int(window.min_batch_size or 12)

        for off, subject in offerings:
            query_result = (db.session.query(StudentProfile, StudentElective.status)
                            .join(StudentElective, StudentProfile.student_id == StudentElective.student_id)
                            .filter(StudentElective.window_id == window.id)
                            .filter(StudentElective.subject_id == subject.subject_id)
                            .all())

            count = len(query_result)

            student_list = []
            for student, status in query_result:
                student_list.append({
                    "id": student.student_id,
                    "name": student.full_name,
                    "roll": student.admission_number,
                    "status": status
                })

            stats.append({
                "window_id": window.id,
                "target_semester_no": window.target_semester_no,
                "bucket": window.bucket,
                "subject_id": subject.subject_id,
                "subject_name": subject.name,
                "code": subject.code,
                "type": subject.subject_type,
                "count": count,
                "status": off.status,
                "is_danger": count < min_batch,
                "students": student_list
            })

        return jsonify({
            "window": {
                "id": window.id,
                "section_id": window.section_id,
                "target_semester_no": window.target_semester_no,
                "bucket": window.bucket,
                "status": window.status,
                "min_batch_size": min_batch,
            },
            "stats": stats,
            "progress": f"{total_selected}/{total_students} Selected"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/elective_windows/manage_enrollment', methods=['POST'])
def api_manage_elective_window_enrollment():
    """Admin manage enrollment within a specific window.

    Body: { window_id, student_ids: [], subject_id, action, new_subject_id? }
    """
    try:
        data = request.json or {}
        window_id = int(data.get('window_id')) if data.get('window_id') else None
        student_ids = data.get('student_ids') or []
        subject_id = int(data.get('subject_id')) if data.get('subject_id') else None
        action = (data.get('action') or '').strip()
        new_subject_id = data.get('new_subject_id')

        if not window_id:
            return jsonify({"error": "window_id required"}), 400
        if not student_ids:
            return jsonify({"error": "No students selected"}), 400
        if not subject_id:
            return jsonify({"error": "subject_id required"}), 400

        window = ElectiveWindow.query.get(window_id)
        if not window:
            return jsonify({"error": "Window not found"}), 404

        # Validate action
        if action not in ['Approve', 'Reject', 'Move']:
            return jsonify({"error": "Invalid action"}), 400

        if action == 'Move':
            if not new_subject_id:
                return jsonify({"error": "new_subject_id required for Move"}), 400
            new_subject_id = int(new_subject_id)
            # Ensure new subject is offered in the same window
            ok = (ElectiveOffering.query
                  .filter_by(window_id=window.id, subject_id=new_subject_id, status='Open')
                  .first())
            if not ok:
                return jsonify({"error": "Target subject is not offered in this window"}), 400

        for s_id in student_ids:
            entry = (StudentElective.query
                     .filter_by(student_id=s_id, window_id=window.id)
                     .first())

            if action == 'Move':
                if entry:
                    entry.subject_id = new_subject_id
                    entry.status = 'Approved'
                else:
                    db.session.add(StudentElective(student_id=s_id, subject_id=new_subject_id, window_id=window.id, status='Approved'))
            elif action == 'Reject':
                if entry:
                    entry.status = 'Rejected'
            elif action == 'Approve':
                if entry:
                    entry.status = 'Approved'

        db.session.commit()
        return jsonify({"message": "Updated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ==========================================
# API: ELECTIVE MANAGEMENT (PRE-REG SUPPORT)
# ==========================================

@app.route('/api/admin/elective_subjects_by_source', methods=['GET'])
def api_admin_elective_subjects_by_source():
    """Return elective subjects from a target level (e.g. TY) to be offered to a current class (section).

    This enables pre-registration: map current Section -> future-year Subjects.
    """
    try:
        section_id = request.args.get('section_id', type=int)
        source_level = (request.args.get('source_level') or '').strip()

        if not section_id:
            return jsonify({"error": "Section ID required"}), 400

        section = ClassSection.query.get(section_id)
        if not section:
            return jsonify({"error": "Class section not found"}), 404

        def _suggest_next_level(level: str) -> str:
            key = (level or '').strip().upper()
            return {"FY": "SY", "SY": "TY", "TY": "LY"}.get(key, level)

        if not source_level:
            source_level = _suggest_next_level(section.class_level)

        # Strategy:
        # 1) Preferred: pull subjects that are allocated to ANY section with class_level == source_level.
        #    This works well in your current architecture where electives are offered each semester via allocations.
        # 2) Fallback: if allocations don't exist, fall back to Subject.target_class == source_level.

        candidates = (db.session.query(Subject)
                      .join(SubjectAllocation, Subject.subject_id == SubjectAllocation.subject_id)
                      .join(ClassSection, SubjectAllocation.section_id == ClassSection.section_id)
                      .filter(ClassSection.class_level == source_level)
                      .distinct()
                      .order_by(Subject.subject_type, Subject.name)
                      .all())

        if not candidates:
            candidates = (Subject.query
                          .filter(Subject.target_class == source_level)
                          .order_by(Subject.subject_type, Subject.name)
                          .all())

        # Final fallback: if the institution maintains a global elective catalog and
        # future-year allocations/target_class tagging isn't done yet, still show all electives.
        if not candidates:
            candidates = (Subject.query
                          .order_by(Subject.subject_type, Subject.name)
                          .all())

        electives = []
        for s in candidates:
            if is_elective_type(s.subject_type):
                electives.append({
                    "id": s.subject_id,
                    "name": s.name,
                    "code": s.code,
                    "type": s.subject_type,
                    "target_class": s.target_class
                })

        return jsonify({
            "section_id": section.section_id,
            "section": f"{section.class_level} - {section.name}",
            "source_level": source_level,
            "subjects": electives
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# In app.py

# ==========================================
# API: ELECTIVE MANAGEMENT (UPDATED)
# ==========================================

@app.route('/api/admin/class_possible_electives', methods=['GET'])
@login_required
@require_roles('Admin')
def get_class_possible_electives():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID required"}), 400

        deny = _ensure_section_in_scope(int(section_id))
        if deny:
            return deny

        # --- IMPROVED LOGIC ---
        # 1. Find subjects allocated to this section
        candidates = (db.session.query(Subject)
                      .join(SubjectAllocation, Subject.subject_id == SubjectAllocation.subject_id)
                      .filter(SubjectAllocation.section_id == section_id)
                      .all())
        
        # 2. Filter in Python (More flexible than SQL IN clause)
        electives = []
        for s in candidates:
            # Check if type contains "Elective" (case insensitive)
            if "elective" in s.subject_type.lower():
                electives.append({
                    "id": s.subject_id,
                    "name": s.name,
                    "code": s.code,
                    "type": s.subject_type
                })
        
        return jsonify({"subjects": electives})
    except Exception as e: return jsonify({"error": str(e)}), 500

    
@app.route('/api/admin/all_active_electives', methods=['GET'])
@login_required
@require_roles('Admin')
def get_all_active_electives():
    try:
        scope_dept_ids = _get_admin_scope_dept_ids()

        # 1. Find all sections that have ANY elective offering 'Open'
        active_section_ids = db.session.query(ElectiveOffering.section_id).filter_by(status='Open').distinct().all()
        active_section_ids = [i[0] for i in active_section_ids]

        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"dashboard": []})
            allowed_section_ids = [
                r[0] for r in (db.session.query(ClassSection.section_id)
                               .join(Specialization, ClassSection.spec_id == Specialization.id)
                               .filter(Specialization.dept_id.in_(scope_dept_ids))
                               .all())
            ]
            allowed_set = set(int(x) for x in allowed_section_ids)
            active_section_ids = [int(x) for x in active_section_ids if int(x) in allowed_set]
        
        dashboard_data = []
        
        for sec_id in active_section_ids:
            section = ClassSection.query.get(sec_id)
            offerings = ElectiveOffering.query.filter_by(section_id=sec_id).all()
            
            electives_data = []
            for off in offerings:
                subject = Subject.query.get(off.subject_id)
                count = StudentElective.query.filter_by(subject_id=off.subject_id).join(StudentProfile).filter(StudentProfile.current_section_id==sec_id).count()
                
                electives_data.append({
                    "subject_id": subject.subject_id,
                    "name": subject.name,
                    "type": subject.subject_type,
                    "count": count,
                    "is_danger": count < 12
                })
            
            dashboard_data.append({
                "section_id": section.section_id,
                "class_name": f"{section.class_level} - {section.name}",
                "electives": electives_data
            })
            
        return jsonify({"dashboard": dashboard_data})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/directory', methods=['GET'])
@login_required
@require_roles('Admin')
def get_student_directory():
    try:
        scope_dept_ids = _get_admin_scope_dept_ids()

        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"directory": {}})
            # For scoped admins, only students whose section maps to their dept via specialization.
            q = (db.session.query(StudentProfile, ClassSection)
                 .join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
                 .join(Specialization, ClassSection.spec_id == Specialization.id)
                 .filter(Specialization.dept_id.in_(scope_dept_ids)))
        else:
            # SuperAdmin sees all students
            q = (db.session.query(StudentProfile, ClassSection)
                 .outerjoin(ClassSection, StudentProfile.current_section_id == ClassSection.section_id))

        results = q.order_by(ClassSection.class_level, ClassSection.name, StudentProfile.full_name).all()
        directory = {}
        for student, section in results:
            lvl = section.class_level if section else "Unassigned"
            sec = section.name if section else "No Section"
            if lvl not in directory: directory[lvl] = {}
            if sec not in directory[lvl]: directory[lvl][sec] = []
            directory[lvl][sec].append({ "id": student.student_id, "name": student.full_name, "roll": student.admission_number, "status": student.academic_status or "Active" })
        return jsonify({"directory": directory})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/update_student_status', methods=['POST'])
@login_required
@require_roles('Admin')
def update_student_status():
    try:
        data = request.json
        deny = _ensure_student_in_scope((data or {}).get('student_id'))
        if deny:
            return deny

        student = StudentProfile.query.get(data.get('student_id'))
        status = data.get('status')
        if not student: return jsonify({"error": "Student not found"}), 404
        student.academic_status = status
        user = UserMaster.query.get(student.student_id)
        if user: user.is_active = status not in ['Semester Break', 'Dropped']
        db.session.commit()
        log_activity("Student Status", f"Marked {student.full_name} as {status}")
        return jsonify({"message": "Updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# ==========================================
# ADMIN: MENTOR & BATCH MANAGEMENT
# ==========================================
@app.route('/admin/manage_mentors')
def render_admin_mentors():
    return render_template('admin_mentors.html')

# ==========================================
# API: MENTOR MANAGEMENT (UPDATED)
# ==========================================
@app.route('/api/admin/get_batches', methods=['GET'])
@login_required
@require_roles('Admin')
def get_batches():
    try:
        section_id = request.args.get('section_id')
        if not section_id:
            return jsonify({"error": "section_id is required"}), 400
        deny = _ensure_section_in_scope(int(section_id))
        if deny:
            return deny
        batches = MentorBatch.query.filter_by(section_id=section_id).all()
        batch_data = []
        for b in batches:
            mentor = StaffProfile.query.get(b.mentor_id) if b.mentor_id else None
            count = StudentProfile.query.filter_by(mentor_batch_id=b.batch_id).count()
            batch_data.append({ "id": b.batch_id, "name": b.batch_name, "mentor_name": mentor.full_name if mentor else "Unassigned", "student_count": count })
        return jsonify({"batches": batch_data})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/delete_batch', methods=['POST'])
@login_required
@require_roles('Admin')
def delete_batch():
    try:
        batch_id = request.json.get('batch_id')
        batch = MentorBatch.query.get(batch_id)
        if not batch: return jsonify({"error": "Batch not found"}), 404

        deny = _ensure_section_in_scope(int(batch.section_id))
        if deny:
            return deny
        
        # Unlink students
        students = StudentProfile.query.filter_by(mentor_batch_id=batch_id).all()
        for s in students: s.mentor_batch_id = None
        
        db.session.delete(batch)
        db.session.commit()
        return jsonify({"message": "Batch removed, students unassigned"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/assign_mentors', methods=['POST'])
@login_required
@require_roles('Admin')
def assign_mentors():
    try:
        data = request.json
        section_id = data.get('section_id')
        if not section_id:
            return jsonify({"error": "section_id is required"}), 400
        deny = _ensure_section_in_scope(int(section_id))
        if deny:
            return deny

        # Mentors must be within department scope when scoped.
        scope_dept_ids = _get_admin_scope_dept_ids()
        if scope_dept_ids is not None:
            mentor_ids = [c.get('mentor_id') for c in (data.get('configs') or []) if c.get('mentor_id')]
            if mentor_ids:
                bad = (db.session.query(StaffProfile)
                       .filter(StaffProfile.staff_id.in_(mentor_ids))
                       .filter(~StaffProfile.primary_department_id.in_(scope_dept_ids))
                       .first())
                if bad:
                    return jsonify({"error": "Out of scope"}), 403
        mode = data.get('mode') # 'single', 'auto_split', 'manual_split'
        configs = data.get('configs') # List of objects: {mentor_id: x, count: y (optional)}

        # 1. Clear old batches for this section to avoid overlap/orphans
        old_batches = MentorBatch.query.filter_by(section_id=section_id).all()
        for b in old_batches:
            students = StudentProfile.query.filter_by(mentor_batch_id=b.batch_id).all()
            for s in students: s.mentor_batch_id = None
            db.session.delete(b)
        
        # 2. Get Students & Sort
        students = StudentProfile.query.filter_by(current_section_id=section_id).all()
        students.sort(key=lambda x: x.admission_number) # Deterministic Sort
        total_students = len(students)
        
        if total_students == 0: return jsonify({"error": "No students in class"}), 400

        current_idx = 0
        
        # 3. Process Allocation
        for i, config in enumerate(configs):
            mentor_id = config.get('mentor_id')
            
            # Determine Batch Size
            if mode == 'single':
                limit = total_students
                batch_name = "Whole Class"
            elif mode == 'manual_split':
                limit = int(config.get('count', 0))
                batch_name = f"Batch {chr(65+i)}"
            else: # auto_split
                # Even split logic
                remaining_students = total_students - current_idx
                remaining_batches = len(configs) - i
                limit = (remaining_students + remaining_batches - 1) // remaining_batches
                batch_name = f"Batch {chr(65+i)}"

            # Create Batch
            new_batch = MentorBatch(batch_name=batch_name, section_id=section_id, mentor_id=mentor_id)
            db.session.add(new_batch); db.session.flush()

            # Assign Students
            end_idx = min(current_idx + limit, total_students)
            for s in students[current_idx : end_idx]:
                s.mentor_batch_id = new_batch.batch_id
            
            current_idx = end_idx
            if current_idx >= total_students: break

        db.session.commit()
        return jsonify({"message": "Mentors assigned successfully"}), 200

    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/admin/mentor_hierarchy', methods=['GET'])
@login_required
@require_roles('Admin')
def get_mentor_hierarchy():
    try:
        # 1. Fetch all Classes
        scope_dept_ids = _get_admin_scope_dept_ids()
        classes_q = ClassSection.query
        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({}), 200
            classes_q = (classes_q
                        .join(Specialization, ClassSection.spec_id == Specialization.id)
                        .filter(Specialization.dept_id.in_(scope_dept_ids)))
        classes = classes_q.order_by(ClassSection.class_level, ClassSection.name).all()
        
        hierarchy = {}
        
        for cls in classes:
            lvl = cls.class_level
            if lvl not in hierarchy: hierarchy[lvl] = []
            
            # 2. Get Batches for this Class
            batches = MentorBatch.query.filter_by(section_id=cls.section_id).all()
            batch_list = []
            
            for b in batches:
                mentor = StaffProfile.query.get(b.mentor_id) if b.mentor_id else None
                # Get students in this batch
                students = StudentProfile.query.filter_by(mentor_batch_id=b.batch_id).all()
                student_data = [{"name": s.full_name, "roll": s.admission_number} for s in students]
                
                batch_list.append({
                    "id": b.batch_id,
                    "name": b.batch_name,
                    "mentor_name": mentor.full_name if mentor else "Unassigned",
                    "count": len(students),
                    "students": student_data # Sending data for the modal
                })
                
            # Get Unassigned Count
            total_students = StudentProfile.query.filter_by(current_section_id=cls.section_id).count()
            assigned_count = sum(b['count'] for b in batch_list)
            unassigned = total_students - assigned_count

            hierarchy[lvl].append({
                "section_id": cls.section_id,
                "section_name": cls.name,
                "total_students": total_students,
                "unassigned": unassigned,
                "batches": batch_list
            })
            
        return jsonify(hierarchy)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/auto_split_batches', methods=['POST'])
@login_required
@require_roles('Admin')
def auto_split_batches():
    try:
        data = request.json
        section_id = data.get('section_id')
        if not section_id:
            return jsonify({"error": "section_id is required"}), 400
        deny = _ensure_section_in_scope(int(section_id))
        if deny:
            return deny

        # Mentors must be within department scope when scoped.
        scope_dept_ids = _get_admin_scope_dept_ids()
        if scope_dept_ids is not None:
            mentor_ids = [mid for mid in (data.get('mentor_ids') or []) if mid]
            if mentor_ids:
                bad = (db.session.query(StaffProfile)
                       .filter(StaffProfile.staff_id.in_(mentor_ids))
                       .filter(~StaffProfile.primary_department_id.in_(scope_dept_ids))
                       .first())
                if bad:
                    return jsonify({"error": "Out of scope"}), 403
        mentor_ids = data.get('mentor_ids') # List
        mode = data.get('mode') # 'auto' or 'manual_single'

        # Clear old batches
        old_batches = MentorBatch.query.filter_by(section_id=section_id).all()
        for b in old_batches:
            students = StudentProfile.query.filter_by(mentor_batch_id=b.batch_id).all()
            for s in students: s.mentor_batch_id = None
            db.session.delete(b)
        
        students = StudentProfile.query.filter_by(current_section_id=section_id).all()
        # Sort Ascending by Admission/Roll
        students.sort(key=lambda x: x.admission_number)
        total = len(students)

        if total == 0: return jsonify({"error": "No students in class"}), 400

        # --- LOW STRENGTH LOGIC (< 20) ---
        if total < 20 or mode == 'manual_single':
            # Force Single Batch
            mentor_id = mentor_ids[0] if mentor_ids else None
            batch = MentorBatch(batch_name="Entire Class", section_id=section_id, mentor_id=mentor_id)
            db.session.add(batch); db.session.flush()
            for s in students: s.mentor_batch_id = batch.batch_id
            msg = f"Assigned entire class ({total} students) to one mentor."

        else:
            # Normal Split
            num_batches = len(mentor_ids)
            batch_size = (total + num_batches - 1) // num_batches
            curr = 0
            for i, mid in enumerate(mentor_ids):
                batch = MentorBatch(batch_name=f"Batch {chr(65+i)}", section_id=section_id, mentor_id=mid)
                db.session.add(batch); db.session.flush()
                end = min(curr + batch_size, total)
                for s in students[curr:end]: s.mentor_batch_id = batch.batch_id
                curr = end
                if curr >= total: break
            msg = f"Split {total} students into {num_batches} batches."

        db.session.commit()
        return jsonify({"message": msg}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# ==========================================
# API: STAFF MENTEE (NEW)
# ==========================================
# app.py

# ==========================================
# API: MENTOR MENTEES (Restore Missing API)
# ==========================================
@app.route('/api/staff/my_mentees', methods=['GET'])
@login_required
@require_roles('Staff')
def get_my_mentees():
    try:
        user_id = current_user.user_id
        my_batches = MentorBatch.query.filter_by(mentor_id=user_id).all()

        scope_dept_ids = _get_user_scope_dept_ids()
        if scope_dept_ids is not None and scope_dept_ids:
            allowed_section_ids = [
                r[0] for r in (db.session.query(ClassSection.section_id)
                               .join(Specialization, ClassSection.spec_id == Specialization.id)
                               .filter(Specialization.dept_id.in_(scope_dept_ids))
                               .all())
            ]
            allowed_set = set(int(x) for x in allowed_section_ids)
            my_batches = [b for b in my_batches if int(b.section_id) in allowed_set]
        
        mentees = []
        for b in my_batches:
            section = db.session.get(ClassSection, b.section_id)
            cls_name = f"{section.class_level}-{section.name}"
            
            # JOIN with ParentProfile to get details
            students_data = (db.session.query(StudentProfile, ParentProfile)
                             .outerjoin(ParentProfile, StudentProfile.parent_user_id == ParentProfile.parent_id)
                             .filter(StudentProfile.mentor_batch_id == b.batch_id)
                             .all())

            for s, p in students_data:
                # Attendance Calc
                total_sessions = db.session.query(SessionLog).join(WeeklySchedule).filter(WeeklySchedule.section_id == section.section_id, SessionLog.status=='Conducted').count()
                attended = AttendanceTransaction.query.filter(AttendanceTransaction.student_id == s.student_id, AttendanceTransaction.status.in_(PRESENT_STATUSES)).count()
                perc = round((attended/total_sessions)*100) if total_sessions > 0 else 0
                
                mentees.append({
                    "id": s.student_id,
                    "name": s.full_name,
                    "roll": s.admission_number,
                    "class": cls_name,
                    "batch": b.batch_name,
                    "batch_id": b.batch_id,
                    "attendance": perc,
                    # PARENT DETAILS
                    "father": p.father_name if p else "N/A",
                    "mother": p.mother_name if p else "N/A",
                    "phone": p.primary_phone if p else "N/A"
                })
        
        return jsonify({"mentees": mentees})
    except Exception as e: return jsonify({"error": str(e)}), 500
    
@app.route('/api/admin/activity_log', methods=['GET'])
@login_required
@require_roles('Admin')
def get_system_logs():
    try:
        from datetime import timezone, timedelta
        IST = timezone(timedelta(hours=5, minutes=30))
        
        # Filter logs by department scope
        scope_dept_ids = _get_admin_scope_dept_ids()
        logs_q = SystemLog.query
        
        if scope_dept_ids is not None:
            # Department admin: show only their department's logs
            if not scope_dept_ids:
                return jsonify({"logs": []})
            logs_q = logs_q.filter(SystemLog.dept_id.in_(scope_dept_ids))
        # else: SuperAdmin sees all logs (no filter)
        
        logs = logs_q.order_by(SystemLog.timestamp.desc()).limit(20).all()
        log_data = []
        
        now_utc = datetime.now(timezone.utc)
        
        for log in logs:
            # Convert timestamp to IST
            if log.timestamp.tzinfo is None:
                # Assume stored as UTC if no tzinfo
                log_utc = log.timestamp.replace(tzinfo=timezone.utc)
            else:
                log_utc = log.timestamp
            log_ist = log_utc.astimezone(IST)
            
            # Calculate time ago from UTC now
            diff = now_utc - log_utc
            time_ago = "Just now"
            if diff.days > 0: 
                time_ago = f"{diff.days}d ago"
            elif diff.seconds > 3600: 
                time_ago = f"{diff.seconds//3600}h ago"
            elif diff.seconds > 60: 
                time_ago = f"{diff.seconds//60}m ago"
            
            # Format: "06 Jan 2026, 3:45 PM"
            formatted_time = log_ist.strftime("%d %b %Y, %I:%M %p")
            
            icon = "activity"; color = "bg-gray-100 text-gray-600"
            if "Import" in log.action_type: icon="upload"; color="bg-blue-50 text-blue-600"
            elif "Role" in log.action_type: icon="shield"; color="bg-green-50 text-green-600"
            elif "Faculty" in log.action_type: icon="user-x"; color="bg-red-50 text-red-600"
            elif "Promotion" in log.action_type: icon="trending-up"; color="bg-yellow-50 text-yellow-600"
            elif "Student" in log.action_type: icon="users"; color="bg-purple-50 text-purple-600"
            elif "Timetable" in log.action_type: icon="calendar"; color="bg-indigo-50 text-indigo-600"
            
            log_data.append({ 
                "action": log.action_type, 
                "desc": log.description, 
                "time": time_ago,
                "timestamp": formatted_time,
                "icon": icon, 
                "color": color 
            })
        return jsonify({"logs": log_data})
    except Exception as e: return jsonify({"error": str(e)}), 500

# In app.py

# In app.py

@app.route('/api/amc/dashboard', methods=['GET'])
def get_amc_stats():
    try:
        user_id = request.args.get('user_id')
        date_str = request.args.get('date')
        section_id = request.args.get('section_id') # NEW FILTER
        
        staff = StaffProfile.query.filter_by(staff_id=user_id).first()
        if not staff or not (staff.is_amc_member or staff.is_amc_head):
            return jsonify({"error": "Unauthorized"}), 403

        if date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            target_day_name = target_date.strftime("%A")
        else:
            target_date = datetime.now().date()
            target_day_name = datetime.now().strftime("%A")
            
        current_time = datetime.now().time()
        is_past_date = target_date < datetime.now().date()

        # Base Query
        query = (db.session.query(WeeklySchedule, StaffProfile, Subject, ClassSection)
                 .join(StaffProfile, WeeklySchedule.teacher_id == StaffProfile.staff_id)
                 .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                 .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
                 .filter(WeeklySchedule.day_of_week == target_day_name))
        
        # Apply Filter if provided
        if section_id:
            query = query.filter(WeeklySchedule.section_id == section_id)
            
        todays_slots = query.order_by(WeeklySchedule.start_time).all()
        
        compliance_report = []
        conducted_count = 0
        missing_count = 0
        
        for slot, teacher, subj, section in todays_slots:
            session = SessionLog.query.filter_by(schedule_id=slot.schedule_id, session_date=target_date).first()
            
            status = "Pending"
            if session:
                status = "Conducted"
                conducted_count += 1
            elif is_past_date or current_time > slot.end_time:
                status = "Missing"
                missing_count += 1
            
            # Strength Calc
            if slot.target_batch:
                batch_obj = MentorBatch.query.filter_by(section_id=section.section_id, batch_name=slot.target_batch).first()
                strength = StudentProfile.query.filter_by(mentor_batch_id=batch_obj.batch_id).count() if batch_obj else 0
            else:
                strength = StudentProfile.query.filter_by(current_section_id=section.section_id).count()

            present = 0
            absent = 0
            if session:
                present = AttendanceTransaction.query.filter_by(session_id=session.session_id).filter(AttendanceTransaction.status.in_(PRESENT_STATUSES)).count()
                absent = strength - present
            elif status == "Missing":
                absent = strength

            compliance_report.append({
                "time": f"{slot.start_time.strftime('%I:%M %p')} - {slot.end_time.strftime('%I:%M %p')}",
                "teacher": teacher.full_name,
                "subject": f"{subj.name} ({slot.session_type})",
                "class": f"{section.class_level}-{section.name}",
                "batch": slot.target_batch if slot.target_batch else "-",
                "status": status,
                "strength": strength,
                "present": present if status == 'Conducted' else '-',
                "absent": absent if status == 'Conducted' or status == 'Missing' else '-'
            })

        total = len(todays_slots)
        rate = round((conducted_count/total)*100) if total > 0 else 0

        return jsonify({
            "date": target_date.strftime('%Y-%m-%d'),
            "date_display": target_date.strftime('%d %b %Y'),
            "stats": {
                "total_scheduled": total,
                "conducted": conducted_count,
                "missing": missing_count,
                "compliance_rate": rate
            },
            "compliance_list": compliance_report
        })

    except Exception as e: return jsonify({"error": str(e)}), 500

# In app.py - Add to the MARKS/AMC section

@app.route('/api/amc/class_ca_summary', methods=['GET'])
def get_class_ca_summary():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID required"}), 400

        # 1. Fetch Class Context
        section = db.session.get(ClassSection, section_id)
        
        # 2. Get All Subjects allocated to this class
        allocations = SubjectAllocation.query.filter_by(section_id=section_id).all()
        subject_ids = [a.subject_id for a in allocations]
        subjects = Subject.query.filter(Subject.subject_id.in_(subject_ids)).order_by(Subject.name).all()
        
        # Map Subject ID -> Name for easy lookup
        sub_headers = [{"id": s.subject_id, "name": s.name, "code": s.code, "type": s.subject_type} for s in subjects]
        
        # 3. Get All Students
        students = StudentProfile.query.filter_by(current_section_id=section_id).order_by(StudentProfile.admission_number).all()
        
        # 4. Fetch ALL Marks for this section
        all_marks = CAMarks.query.filter_by(section_id=section_id).all()
        
        # Create a fast lookup map: (student_id, subject_id) -> total_ca
        marks_map = {}
        for m in all_marks:
            marks_map[(m.student_id, m.subject_id)] = m.total_ca

        # 5. Build Distribution Stats Containers
        # Format: { subject_id: { '0-9': 0, '10-19': 0 ... } }
        distribution = {s.subject_id: {"0-9": 0, "10-19": 0, "20-30": 0, "31-40": 0, "41-50": 0} for s in subjects}

        # 6. Build Rows
        rows = []
        for student in students:
            row_data = {
                "roll": student.admission_number,
                "name": student.full_name,
                "scores": []
            }
            
            for sub in subjects:
                # Elective Logic: Check if student has opted
                is_valid = True
                if is_elective_type(sub.subject_type):
                    opted = StudentElective.query.filter_by(student_id=student.student_id, subject_id=sub.subject_id, status='Approved').first()
                    if not opted: is_valid = False
                
                if not is_valid:
                    row_data["scores"].append("-")
                    continue

                # Get Mark
                score = marks_map.get((student.student_id, sub.subject_id), None)
                
                if score is not None:
                    row_data["scores"].append(round(score))
                    
                    # Update Distribution
                    s = distribution[sub.subject_id]
                    if score <= 9: s["0-9"] += 1
                    elif score <= 19: s["10-19"] += 1
                    elif score <= 30: s["20-30"] += 1
                    elif score <= 40: s["31-40"] += 1
                    else: s["41-50"] += 1
                else:
                    row_data["scores"].append("NA") # Not Assigned/Entered

            rows.append(row_data)

        # Format Distribution for Frontend
        dist_report = []
        for sub in subjects:
            d = distribution[sub.subject_id]
            dist_report.append({
                "subject": sub.name,
                "ranges": [d["0-9"], d["10-19"], d["20-30"], d["31-40"], d["41-50"]],
                "total_students": sum(d.values())
            })

        return jsonify({
            "meta": { "class_name": f"{section.class_level}-{section.name}" },
            "headers": sub_headers,
            "distribution": dist_report,
            "rows": rows
        })

    except Exception as e: return jsonify({"error": str(e)}), 500

# In app.py

@app.route('/api/amc/compliance_hierarchy', methods=['GET'])
def get_amc_compliance_hierarchy():
    try:
        date_str = request.args.get('date')
        if date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            target_date = date.today()
            
        day_name = target_date.strftime("%A")
        current_time = datetime.now().time()
        is_today = target_date == date.today()

        # Fetch all sections sorted
        sections = ClassSection.query.order_by(ClassSection.class_level, ClassSection.name).all()
        
        hierarchy = {}
        
        for section in sections:
            lvl = section.class_level
            if lvl not in hierarchy: 
                hierarchy[lvl] = {
                    "total_scheduled": 0, "conducted": 0, "missing": 0, 
                    "sections": []
                }
            
            # Get slots for this section on this day
            slots = WeeklySchedule.query.filter_by(section_id=section.section_id, day_of_week=day_name).all()
            
            sec_total = len(slots)
            sec_conducted = 0
            sec_missing = 0
            
            for slot in slots:
                session = SessionLog.query.filter_by(schedule_id=slot.schedule_id, session_date=target_date).first()
                if session:
                    sec_conducted += 1
                elif not is_today or current_time > slot.end_time:
                    # If date is past OR time has passed today, and no log exists -> Missing
                    sec_missing += 1
            
            # Append Section Data
            hierarchy[lvl]["sections"].append({
                "id": section.section_id,
                "name": section.name,
                "stats": {
                    "total": sec_total,
                    "conducted": sec_conducted,
                    "missing": sec_missing,
                    "compliance": round((sec_conducted/sec_total)*100) if sec_total > 0 else (100 if sec_total == 0 else 0)
                }
            })
            
            # Aggregate Level Data
            hierarchy[lvl]["total_scheduled"] += sec_total
            hierarchy[lvl]["conducted"] += sec_conducted
            hierarchy[lvl]["missing"] += sec_missing

        # Final Compliance Calc for Levels
        for lvl in hierarchy:
            t = hierarchy[lvl]["total_scheduled"]
            c = hierarchy[lvl]["conducted"]
            hierarchy[lvl]["compliance"] = round((c/t)*100) if t > 0 else (100 if t == 0 else 0)
            
        return jsonify(hierarchy)

    except Exception as e: return jsonify({"error": str(e)}), 500




@app.route('/api/admin/batch_stats', methods=['GET'])
@login_required
@require_roles('Admin')
def get_batch_stats():
    try:
        scope_dept_ids = _get_admin_scope_dept_ids()
        levels = ['FY', 'SY', 'TY', 'LY']
        stats = []
        for lvl in levels:
            q = (db.session.query(StudentProfile)
                 .join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
                 .filter(ClassSection.class_level == lvl)
                 .filter(StudentProfile.academic_status == 'Active'))

            bq = (db.session.query(StudentProfile.batch)
                  .join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
                  .filter(ClassSection.class_level == lvl))

            if scope_dept_ids is not None:
                if not scope_dept_ids:
                    stats.append({"level": lvl, "count": 0, "batches": ""})
                    continue
                q = (q.join(Specialization, ClassSection.spec_id == Specialization.id)
                       .filter(Specialization.dept_id.in_(scope_dept_ids)))
                bq = (bq.join(Specialization, ClassSection.spec_id == Specialization.id)
                        .filter(Specialization.dept_id.in_(scope_dept_ids)))

            count = q.count()
            batches = bq.distinct().all()
            batch_names = [b[0] for b in batches if b[0]]
            stats.append({ "level": lvl, "count": count, "batches": ", ".join(batch_names) })
        return jsonify({"stats": stats})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/promote_batch', methods=['POST'])
@login_required
@require_roles('Admin')
def promote_batch():
    try:
        data = request.json
        from_lvl = data.get('from_level')
        to_lvl = data.get('to_level')

        scope_dept_ids = _get_admin_scope_dept_ids()
        
        # 1. Find Students to Promote
        q = (db.session.query(StudentProfile, ClassSection)
             .join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
             .filter(ClassSection.class_level == from_lvl)
             .filter(StudentProfile.academic_status == 'Active'))

        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"error": "Admin department scope not configured"}), 403
            q = (q.join(Specialization, ClassSection.spec_id == Specialization.id)
                   .filter(Specialization.dept_id.in_(scope_dept_ids)))

        students_to_promote = q.all()
        
        if not students_to_promote: return jsonify({"error": "No students found"}), 404
        promoted_count = 0
        
        # 2. Handle Graduation (Alumni)
        if to_lvl == 'Alumni':
            for student, _ in students_to_promote:
                student.current_section_id = None
                student.academic_status = 'Completed'
                student.mentor_batch_id = None # Remove mentor link for alumni
                promoted_count += 1
        
        # 3. Handle Progression (FY -> SY -> TY)
        else:
            # Pre-fetch target sections to minimize DB hits
            target_sections_q = ClassSection.query.filter_by(class_level=to_lvl)
            if scope_dept_ids is not None:
                target_sections_q = (target_sections_q.join(Specialization, ClassSection.spec_id == Specialization.id)
                                     .filter(Specialization.dept_id.in_(scope_dept_ids)))
            target_sections = target_sections_q.all()
            target_map = {sec.name: sec.section_id for sec in target_sections}
            
            # Cache for Target Batches to prevent duplicates during loop
            # Format: { section_id: { 'BatchName': batch_object } }
            target_batch_cache = {}

            for student, current_sec in students_to_promote:
                target_id = target_map.get(current_sec.name)
                
                if target_id:
                    # A. Move Student to New Class
                    student.current_section_id = target_id
                    promoted_count += 1
                    
                    # B. Carry Forward Mentor Logic
                    if student.mentor_batch_id:
                        old_batch = db.session.get(MentorBatch, student.mentor_batch_id)
                        
                        if old_batch:
                            # Initialize cache for this section if needed
                            if target_id not in target_batch_cache:
                                existing_batches = MentorBatch.query.filter_by(section_id=target_id).all()
                                target_batch_cache[target_id] = {b.batch_name: b for b in existing_batches}
                            
                            # Check if corresponding batch exists in new class
                            new_batch = target_batch_cache[target_id].get(old_batch.batch_name)
                            
                            if not new_batch:
                                # [Inference] Batch doesn't exist in new class, so create it & assign SAME MENTOR
                                new_batch = MentorBatch(
                                    batch_name=old_batch.batch_name,
                                    section_id=target_id,
                                    mentor_id=old_batch.mentor_id # <--- Copy Mentor ID
                                )
                                db.session.add(new_batch)
                                db.session.flush() # Get ID immediately
                                target_batch_cache[target_id][old_batch.batch_name] = new_batch
                            
                            # Link Student to the New Batch
                            student.mentor_batch_id = new_batch.batch_id

        db.session.commit()
        log_activity("Promotion", f"Promoted {promoted_count} students from {from_lvl} to {to_lvl}")
        return jsonify({"message": f"Promoted {promoted_count} students"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# In app.py - Add these missing functions

@app.route('/api/admin/allocation_data', methods=['GET'])
@login_required
@require_roles('Admin')
def get_allocation_data():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID required"}), 400

        deny = _ensure_section_in_scope(int(section_id))
        if deny:
            return deny
        
        allocations = (db.session.query(SubjectAllocation, Subject, StaffProfile)
                       .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                       .join(StaffProfile, SubjectAllocation.teacher_id == StaffProfile.staff_id)
                       .filter(SubjectAllocation.section_id == section_id)
                       .all())
        
        allocated_data = []
        for alloc, sub, staff in allocations:
            allocated_data.append({
                "allocation_id": alloc.allocation_id,
                "subject_name": sub.name,
                "subject_code": sub.code,
                "teacher_name": staff.full_name,
                "teacher_id": staff.staff_id,
                "type": sub.subject_type
            })
            
        return jsonify({"allocations": allocated_data})
    except Exception as e: return jsonify({"error": str(e)}), 500

# @app.route('/api/admin/faculty_load_list', methods=['GET'])
# def get_faculty_load_list():
#     try:
#         # 1. Calculate Load
#         load_counts = db.session.query(SubjectAllocation.teacher_id, db.func.count(SubjectAllocation.allocation_id)).group_by(SubjectAllocation.teacher_id).all()
#         load_map = {teacher_id: count for teacher_id, count in load_counts}

#         # 2. Get Staff
#         all_staff = StaffProfile.query.order_by(StaffProfile.full_name).all()
#         staff_list = []
#         for s in all_staff:
#             staff_list.append({
#                 "id": s.staff_id,
#                 "name": s.full_name,
#                 "load": load_map.get(s.staff_id, 0),
#                 "dept": str(s.primary_department_id)
#             })
            
#         # 3. Get Subjects
#         all_subjects = Subject.query.order_by(Subject.name).all()
#         subject_list = [{"id": s.subject_id, "name": s.name, "code": s.code} for s in all_subjects]
        
#         return jsonify({"faculty": staff_list, "subjects": subject_list})
#     except Exception as e: return jsonify({"error": str(e)}), 500

# @app.route('/api/admin/save_allocation', methods=['POST'])
# def save_allocation():
#     try:
#         data = request.json
#         section_id = data.get('section_id')
#         subject_id = data.get('subject_id')
#         staff_id = data.get('staff_id')
        
#         existing = SubjectAllocation.query.filter_by(section_id=section_id, subject_id=subject_id).first()
        
#         if existing:
#             existing.teacher_id = staff_id
#             msg = "Faculty Updated"
#         else:
#             new_alloc = SubjectAllocation(section_id=section_id, subject_id=subject_id, teacher_id=staff_id)
#             db.session.add(new_alloc)
#             msg = "New Subject Assigned"
            
#         db.session.commit()
#         return jsonify({"message": msg}), 200
#     except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/admin/faculty_load_list', methods=['GET'])
@login_required
@require_roles('Admin')
def get_faculty_load_list():
    try:
        section_id = request.args.get('section_id')
        if section_id:
            deny = _ensure_section_in_scope(int(section_id))
            if deny:
                return deny

        scope_dept_ids = _get_admin_scope_dept_ids()
        load_counts = db.session.query(SubjectAllocation.teacher_id, db.func.count(SubjectAllocation.allocation_id)).group_by(SubjectAllocation.teacher_id).all()
        load_map = {tid: count for tid, count in load_counts}
        active_mentors = db.session.query(MentorBatch.mentor_id).filter(MentorBatch.mentor_id != None).distinct().all()
        mentor_ids = {m[0] for m in active_mentors}

        # --- UPDATE: Filter Active Faculty ---
        all_staff = (db.session.query(StaffProfile)
                     .join(UserMaster, StaffProfile.staff_id == UserMaster.user_id)
                     .filter(UserMaster.is_active == True)
                     .order_by(StaffProfile.full_name)
                     .all())

        if scope_dept_ids is not None:
            if not scope_dept_ids:
                return jsonify({"faculty": [], "subjects": []})
            all_staff = [s for s in all_staff if s.primary_department_id in scope_dept_ids]
        
        staff_list = []
        for s in all_staff:
            if "System Administrator" in s.full_name: continue
            staff_list.append({
                "id": s.staff_id, "name": s.full_name, "load": load_map.get(s.staff_id, 0),
                "dept": str(s.primary_department_id), "is_locked": s.staff_id in mentor_ids
            })
            
        if section_id:
            assigned_ids = [a[0] for a in db.session.query(SubjectAllocation.subject_id).filter_by(section_id=section_id).all()]
            target_section = ClassSection.query.get(section_id)
            target_level = target_section.class_level if target_section else None
            
            query = Subject.query.filter(Subject.subject_id.notin_(assigned_ids))
            if target_level: query = query.filter_by(target_class=target_level)
            query = query.filter(Subject.subject_type == 'Core')
            if scope_dept_ids is not None:
                query = query.filter(Subject.dept_id.in_(scope_dept_ids))
            available_subjects = query.order_by(Subject.name).all()
        else:
            query = Subject.query
            if scope_dept_ids is not None:
                query = query.filter(Subject.dept_id.in_(scope_dept_ids))
            available_subjects = query.order_by(Subject.name).all()
            
        subject_list = [{"id": s.subject_id, "name": s.name, "code": s.code} for s in available_subjects]
        return jsonify({"faculty": staff_list, "subjects": subject_list})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/save_allocation', methods=['POST'])
@login_required
@require_roles('Admin')
def save_allocation():
    try:
        data = request.json
        section_id = (data or {}).get('section_id')
        subject_id = (data or {}).get('subject_id')
        staff_id = (data or {}).get('staff_id')

        if not section_id or not subject_id:
            return jsonify({"error": "section_id and subject_id are required"}), 400

        deny = _ensure_section_in_scope(int(section_id))
        if deny:
            return deny

        scope_dept_ids = _get_admin_scope_dept_ids()
        if scope_dept_ids is not None:
            if staff_id:
                staff = db.session.get(StaffProfile, staff_id)
                if not staff or not staff.primary_department_id or int(staff.primary_department_id) not in scope_dept_ids:
                    return jsonify({"error": "Out of scope"}), 403

            subj = db.session.get(Subject, int(subject_id))
            if subj and getattr(subj, 'dept_id', None) and int(subj.dept_id) not in scope_dept_ids:
                return jsonify({"error": "Out of scope"}), 403

        existing = SubjectAllocation.query.filter_by(section_id=data.get('section_id'), subject_id=data.get('subject_id')).first()
        if existing: existing.teacher_id = data.get('staff_id'); msg = "Updated"
        else: db.session.add(SubjectAllocation(section_id=data.get('section_id'), subject_id=data.get('subject_id'), teacher_id=data.get('staff_id'))); msg = "Assigned"
        db.session.commit()
        return jsonify({"message": msg}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/get_class_schedule', methods=['GET'])
@login_required
@require_roles('Admin')
def get_class_schedule():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID missing"}), 400

        deny = _ensure_section_in_scope(int(section_id))
        if deny:
            return deny

        # Get active version for this section
        active_version_id = get_active_version_id(int(section_id))

        # 1. Get Time Slots (filtered by active version)
        query = (db.session.query(WeeklySchedule, Subject, StaffProfile, RoomMaster)
                 .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                 .join(StaffProfile, WeeklySchedule.teacher_id == StaffProfile.staff_id)
                 .outerjoin(RoomMaster, WeeklySchedule.room_id == RoomMaster.room_id)
                 .filter(WeeklySchedule.section_id == section_id))

        # Filter by active version if one exists
        if active_version_id:
            query = query.filter(WeeklySchedule.version_id == active_version_id)

        slots = query.all()
                 
        schedule_data = []
        for slot, subj, teacher, room in slots:
            schedule_data.append({
                "day": slot.day_of_week,
                "start_time": slot.start_time.strftime("%I:%M %p"),
                "end_time": slot.end_time.strftime("%I:%M %p"),
                "subject": subj.name,
                "code": subj.code,
                "type": slot.session_type,
                "batch": slot.target_batch,
                "teacher": teacher.full_name,
                "room": room.room_number if room else "TBD"
            })
            
        # 2. Get Subject List (ROBUST FETCH)
        # We query SubjectAllocation to see everything assigned to this class
        allocations = (db.session.query(SubjectAllocation, Subject, StaffProfile)
                       .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                       .join(StaffProfile, SubjectAllocation.teacher_id == StaffProfile.staff_id)
                       .filter(SubjectAllocation.section_id == section_id)
                       .order_by(Subject.name)
                       .all())
        
        subject_list = []
        for alloc, sub, staff in allocations:
            # Format Load String
            load_str = f"L:{sub.l_count} T:{sub.t_count} P:{sub.p_count} C:{sub.credits}"
            
            subject_list.append({
                "code": sub.code,
                "name": sub.name,
                "teacher": staff.full_name,
                "load": load_str,
                "type": sub.subject_type
            })
            
        return jsonify({"schedule": schedule_data, "subjects": subject_list})

    except Exception as e: return jsonify({"error": str(e)}), 500


# ==========================================
# TIMETABLE VERSION MANAGEMENT APIs
# ==========================================

def get_active_version_id(section_id):
    """Get the active version_id for a section, or None if no active version"""
    active = TimetableVersion.query.filter_by(section_id=section_id, status='Active').first()
    return active.version_id if active else None


@app.route('/api/admin/timetable_versions', methods=['GET'])
@login_required
@require_roles('Admin')
def list_timetable_versions():
    """List all versions for a section"""
    section_id = request.args.get('section_id', type=int)
    if not section_id:
        return jsonify({"error": "section_id required"}), 400

    deny = _ensure_section_in_scope(int(section_id))
    if deny:
        return deny

    versions = (TimetableVersion.query
                .filter_by(section_id=section_id)
                .order_by(TimetableVersion.version_number.desc())
                .all())

    section = ClassSection.query.get(section_id)

    result = []
    for v in versions:
        creator = StaffProfile.query.get(v.created_by_id) if v.created_by_id else None
        slot_count = WeeklySchedule.query.filter_by(version_id=v.version_id).count()

        result.append({
            "version_id": v.version_id,
            "version_number": v.version_number,
            "version_label": v.version_label,
            "status": v.status,
            "created_by": creator.full_name if creator else "System",
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "published_at": v.published_at.isoformat() if v.published_at else None,
            "source_type": v.source_type,
            "slot_count": slot_count,
            "notes": v.notes
        })

    return jsonify({
        "section_id": section_id,
        "section_name": f"{section.class_level} - {section.name}" if section else "Unknown",
        "versions": result,
        "has_active": any(v["status"] == "Active" for v in result),
        "has_draft": any(v["status"] == "Draft" for v in result)
    })


@app.route('/api/admin/timetable_versions/<int:version_id>', methods=['GET'])
@login_required
@require_roles('Admin')
def get_version_schedule(version_id):
    """Get schedule slots for a specific version (preview)"""
    version = TimetableVersion.query.get_or_404(version_id)

    deny = _ensure_section_in_scope(int(version.section_id))
    if deny:
        return deny

    slots = (db.session.query(WeeklySchedule, Subject, StaffProfile, RoomMaster)
             .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
             .join(StaffProfile, WeeklySchedule.teacher_id == StaffProfile.staff_id)
             .outerjoin(RoomMaster, WeeklySchedule.room_id == RoomMaster.room_id)
             .filter(WeeklySchedule.version_id == version_id)
             .all())

    schedule_data = []
    for slot, subj, teacher, room in slots:
        schedule_data.append({
            "schedule_id": slot.schedule_id,
            "day": slot.day_of_week,
            "start_time": slot.start_time.strftime("%I:%M %p"),
            "end_time": slot.end_time.strftime("%I:%M %p"),
            "subject": subj.name,
            "code": subj.code,
            "type": slot.session_type,
            "batch": slot.target_batch,
            "teacher": teacher.full_name,
            "teacher_id": teacher.staff_id,
            "room": room.room_number if room else "TBD"
        })

    return jsonify({
        "version": {
            "version_id": version.version_id,
            "version_number": version.version_number,
            "version_label": version.version_label,
            "status": version.status
        },
        "schedule": schedule_data
    })


@app.route('/api/admin/timetable_versions/publish', methods=['POST'])
@login_required
@require_roles('Admin')
def publish_timetable_version():
    """Publish a draft version, archiving the current active"""
    data = request.json
    version_id = data.get('version_id')

    version = TimetableVersion.query.get_or_404(version_id)

    deny = _ensure_section_in_scope(int(version.section_id))
    if deny:
        return deny

    if version.status != 'Draft':
        return jsonify({"error": "Only draft versions can be published"}), 400

    # Find and archive current active version for this section
    current_active = TimetableVersion.query.filter_by(
        section_id=version.section_id,
        status='Active'
    ).first()

    if current_active:
        current_active.status = 'Archived'
        current_active.archived_at = datetime.now()

    # Publish the draft
    version.status = 'Active'
    version.published_at = datetime.now()

    db.session.commit()

    # Send notifications to affected students and staff
    _notify_timetable_change(version.section_id, version.version_id)

    log_activity("Timetable Published", f"Version {version.version_number} published for section {version.section_id}")

    return jsonify({"message": "Version published successfully", "version_id": version.version_id}), 200


@app.route('/api/admin/timetable_versions/clone', methods=['POST'])
@login_required
@require_roles('Admin')
def clone_timetable_version():
    """Clone active version to create a new draft for editing"""
    data = request.json
    section_id = data.get('section_id')
    if not section_id:
        return jsonify({"error": "section_id required"}), 400

    deny = _ensure_section_in_scope(int(section_id))
    if deny:
        return deny

    # Check if draft already exists
    existing_draft = TimetableVersion.query.filter_by(section_id=section_id, status='Draft').first()
    if existing_draft:
        return jsonify({"error": "A draft already exists for this section. Delete it first."}), 400

    # Find active version
    active_version = TimetableVersion.query.filter_by(section_id=section_id, status='Active').first()
    if not active_version:
        return jsonify({"error": "No active version to clone"}), 404

    # Calculate next version number
    max_version = db.session.query(db.func.max(TimetableVersion.version_number)).filter_by(section_id=section_id).scalar() or 0

    # Create new draft version
    new_version = TimetableVersion(
        section_id=section_id,
        version_number=max_version + 1,
        version_label=data.get('label', f"Draft v{max_version + 1}"),
        status='Draft',
        created_by_id=current_user.user_id,
        source_type='clone',
        cloned_from_version_id=active_version.version_id,
        notes=data.get('notes')
    )
    db.session.add(new_version)
    db.session.flush()  # Get the version_id

    # Clone all schedule slots
    active_slots = WeeklySchedule.query.filter_by(version_id=active_version.version_id).all()
    for slot in active_slots:
        new_slot = WeeklySchedule(
            section_id=slot.section_id,
            subject_id=slot.subject_id,
            teacher_id=slot.teacher_id,
            day_of_week=slot.day_of_week,
            start_time=slot.start_time,
            end_time=slot.end_time,
            session_type=slot.session_type,
            target_batch=slot.target_batch,
            room_id=slot.room_id,
            version_id=new_version.version_id
        )
        db.session.add(new_slot)

    db.session.commit()

    return jsonify({
        "message": "Draft created from active version",
        "version_id": new_version.version_id,
        "slot_count": len(active_slots)
    }), 201


@app.route('/api/admin/timetable_versions/<int:version_id>', methods=['DELETE'])
@login_required
@require_roles('Admin')
def delete_timetable_version(version_id):
    """Delete a draft or archived version"""
    version = TimetableVersion.query.get_or_404(version_id)

    deny = _ensure_section_in_scope(int(version.section_id))
    if deny:
        return deny

    if version.status == 'Active':
        return jsonify({"error": "Cannot delete active version. Publish another version first."}), 400

    # Delete associated schedules
    WeeklySchedule.query.filter_by(version_id=version_id).delete()

    # Delete version
    db.session.delete(version)
    db.session.commit()

    return jsonify({"message": "Version deleted successfully"}), 200


def _notify_timetable_change(section_id, version_id):
    """Send notifications to students and teachers when timetable changes"""
    section = ClassSection.query.get(section_id)
    if not section:
        return

    section_name = f"{section.class_level} - {section.name}"

    # Notify all students in the section
    students = StudentProfile.query.filter_by(current_section_id=section_id).all()
    for student in students:
        send_notification(
            student.student_id,
            "Timetable Updated",
            f"A new timetable has been published for {section_name}. Please check your schedule.",
            "info",
            "/student/dashboard"
        )

    # Notify teachers who have classes in this section's new version
    teacher_ids = db.session.query(WeeklySchedule.teacher_id).filter_by(
        version_id=version_id
    ).distinct().all()

    for (teacher_id,) in teacher_ids:
        if teacher_id:
            send_notification(
                teacher_id,
                "Timetable Updated",
                f"A new timetable has been published for {section_name} that includes your classes.",
                "info",
                "/staff/dashboard"
            )


# In app.py

@app.route('/api/admin/course_structure', methods=['GET'])
@login_required
@require_roles('Admin')
def get_course_structure():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID missing"}), 400

        deny = _ensure_section_in_scope(int(section_id))
        if deny:
            return deny

        # Fetch allocations for this section (Source of Truth)
        allocations = (db.session.query(SubjectAllocation, Subject, StaffProfile)
                       .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                       .join(StaffProfile, SubjectAllocation.teacher_id == StaffProfile.staff_id)
                       .filter(SubjectAllocation.section_id == section_id)
                       .order_by(Subject.name)
                       .all())
        
        course_list = []
        for alloc, sub, staff in allocations:
            course_list.append({
                "code": sub.code,
                "name": sub.name,
                "teacher": staff.full_name,
                "type": sub.subject_type,
                "load": f"L:{sub.l_count} T:{sub.t_count} P:{sub.p_count} C:{sub.credits}",
                "total_hours": sub.l_count + sub.t_count + sub.p_count
            })
            
        return jsonify({"courses": course_list})

    except Exception as e: return jsonify({"error": str(e)}), 500


# ==========================================
# API: ADMIN EVENTS MANAGEMENT
# ==========================================

@app.route('/api/admin/events', methods=['GET'])
@login_required
@require_roles('Admin')
def get_admin_events():
    """Get all events with coordinator info for admin management."""
    try:
        scope_dept_ids = _get_admin_scope_dept_ids()
        
        # Get all events with coordinator info
        events_query = (db.session.query(EventMaster, StaffProfile)
                       .join(StaffProfile, EventMaster.coordinator_id == StaffProfile.staff_id)
                       .order_by(EventMaster.start_date.desc()))
        
        # If department-scoped admin, filter by department
        if scope_dept_ids:
            events_query = events_query.filter(StaffProfile.primary_department_id.in_(scope_dept_ids))
        
        events = events_query.all()
        
        events_list = []
        for evt, coord in events:
            date_str = evt.start_date.strftime('%d %b %Y')
            if evt.end_date and evt.end_date != evt.start_date:
                date_str += f" - {evt.end_date.strftime('%d %b %Y')}"
            
            events_list.append({
                "id": evt.event_id,
                "name": evt.event_name,
                "date": date_str,
                "start_date": evt.start_date.strftime('%Y-%m-%d'),
                "end_date": evt.end_date.strftime('%Y-%m-%d') if evt.end_date else evt.start_date.strftime('%Y-%m-%d'),
                "coordinator_id": evt.coordinator_id,
                "coordinator_name": coord.full_name,
                "description": evt.description or ""
            })
        
        # Get staff list for dropdown (event coordinators)
        staff_query = StaffProfile.query.filter_by(is_archived=False)
        if scope_dept_ids:
            staff_query = staff_query.filter(StaffProfile.primary_department_id.in_(scope_dept_ids))
        
        staff = staff_query.order_by(StaffProfile.full_name).all()
        staff_list = [{"id": s.staff_id, "name": s.full_name} for s in staff]
        
        return jsonify({
            "events": events_list,
            "staff_directory": staff_list
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/save_event', methods=['POST'])
@login_required
@require_roles('Admin')
def save_admin_event():
    """Create or update an event (admin only)."""
    try:
        data = request.json or {}
        event_id = data.get('id')
        name = (data.get('name') or '').strip()
        date_str = data.get('date')
        coordinator_id = data.get('coordinator_id')
        description = (data.get('description') or '').strip()
        
        if not name or not date_str or not coordinator_id:
            return jsonify({"error": "name, date, and coordinator_id are required"}), 400
        
        try:
            event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400
        
        if event_id:
            # Update existing event
            event = EventMaster.query.get(event_id)
            if not event:
                return jsonify({"error": "Event not found"}), 404
            
            event.event_name = name
            event.start_date = event_date
            event.end_date = event_date
            event.coordinator_id = coordinator_id
            event.description = description
            
            log_activity("Events", f"Updated event: {name}")
            db.session.commit()
            return jsonify({"message": "Event updated successfully"}), 200
        else:
            # Create new event
            new_event = EventMaster(
                event_name=name,
                start_date=event_date,
                end_date=event_date,
                coordinator_id=coordinator_id,
                description=description
            )
            db.session.add(new_event)
            db.session.commit()
            
            log_activity("Events", f"Created event: {name}")
            return jsonify({"message": "Event created successfully", "id": new_event.event_id}), 201
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/delete_event', methods=['POST'])
@login_required
@require_roles('Admin')
def delete_admin_event():
    """Delete an event and its participation records (admin only)."""
    try:
        data = request.json or {}
        event_id = data.get('id')
        
        if not event_id:
            return jsonify({"error": "Event ID is required"}), 400
        
        event = EventMaster.query.get(event_id)
        if not event:
            return jsonify({"error": "Event not found"}), 404
        
        event_name = event.event_name
        
        # Delete participation records first (foreign key constraint)
        EventParticipation.query.filter_by(event_id=event_id).delete()
        
        # Delete the event
        db.session.delete(event)
        db.session.commit()
        
        log_activity("Events", f"Deleted event: {event_name}")
        return jsonify({"message": "Event deleted successfully"}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/events/create', methods=['POST'])
def create_event():
    try:
        data = request.json
        s_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        e_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
        s_time = datetime.strptime(data.get('start_time'), '%H:%M').time() if data.get('start_time') else None
        e_time = datetime.strptime(data.get('end_time'), '%H:%M').time() if data.get('end_time') else None
        
        new_event = EventMaster(
            event_name=data.get('name'),
            start_date=s_date,
            end_date=e_date,
            start_time=s_time,
            end_time=e_time,
            description=data.get('description'),
            coordinator_id=data.get('user_id'),
        )
        db.session.add(new_event)
        db.session.commit()

        notified = 0
        if data.get('notify_all_students'):
            students = StudentProfile.query.filter_by(academic_status='Active').all()
            for s in students:
                send_notification(
                    s.student_id,
                    "New Event",
                    f"{new_event.event_name} was created.",
                    "info",
                    "/student/dashboard",
                )
                notified += 1

        return jsonify({"message": "Event Created", "id": new_event.event_id, "notified": notified}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/events/update', methods=['POST'])
def update_event():
    try:
        data = request.json or {}
        event_id = data.get('event_id')
        user_id = data.get('user_id')
        if not event_id or not user_id:
            return jsonify({"error": "event_id and user_id are required"}), 400

        event = EventMaster.query.get(event_id)
        if not event:
            return jsonify({"error": "Event not found"}), 404
        if event.coordinator_id != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if data.get('name'):
            event.event_name = data.get('name')
        if data.get('start_date'):
            event.start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        if data.get('end_date'):
            event.end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
        if 'start_time' in data:
            event.start_time = datetime.strptime(data.get('start_time'), '%H:%M').time() if data.get('start_time') else None
        if 'end_time' in data:
            event.end_time = datetime.strptime(data.get('end_time'), '%H:%M').time() if data.get('end_time') else None
        if 'description' in data:
            event.description = data.get('description')

        participants = EventParticipation.query.filter_by(event_id=event.event_id).all()
        for part in participants:
            send_notification(
                part.student_id,
                "Event Updated",
                f"{event.event_name} details were updated.",
                "info",
                "/student/dashboard",
            )

        db.session.commit()
        return jsonify({"message": "Event Updated", "notified": len(participants)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/my_events', methods=['GET'])
def get_my_events():
    try:
        user_id = request.args.get('user_id')
        events = EventMaster.query.filter_by(coordinator_id=user_id).order_by(EventMaster.start_date.desc()).all()
        event_list = []
        for e in events:
            count = EventParticipation.query.filter_by(event_id=e.event_id).count()
            time_str = "Full Day"
            if e.start_time: time_str = f"{e.start_time.strftime('%I:%M %p')} - {e.end_time.strftime('%I:%M %p')}"
            event_list.append({ "id": e.event_id, "name": e.event_name, "date": e.start_date.strftime('%d %b'), "time": time_str, "student_count": count })
        return jsonify({"events": event_list})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/events/add_student', methods=['POST'])
def add_event_participant():
    try:
        data = request.json
        student = StudentProfile.query.filter_by(admission_number=data.get('roll_no')).first()
        if not student: return jsonify({"error": "Student not found"}), 404
        if EventParticipation.query.filter_by(event_id=data.get('event_id'), student_id=student.student_id).first(): return jsonify({"error": "Already added"}), 400

        event = EventMaster.query.get(data.get('event_id'))
        event_name = event.event_name if event else "Event"

        db.session.add(EventParticipation(
            event_id=data.get('event_id'),
            student_id=student.student_id,
            status='Nominated',
            student_role=data.get('role', 'Participant'),
        ))

        send_notification(
            student.student_id,
            "Event Nomination",
            f"You have been nominated for: {event_name}.",
            "info",
            "/student/dashboard",
        )

        db.session.commit()
        return jsonify({"message": "Added"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/events/participants', methods=['GET'])
def get_event_participants():
    try:
        event_id = request.args.get('event_id')
        
        # Use OUTER JOIN for ClassSection so we don't crash if a student has no class
        participants = (db.session.query(EventParticipation, StudentProfile, ClassSection)
                        .join(StudentProfile, EventParticipation.student_id == StudentProfile.student_id)
                        .outerjoin(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
                        .filter(EventParticipation.event_id == event_id)
                        .all())
        
        list_data = []
        for part, student, sec in participants:
            # Handle missing class gracefully
            class_name = "Unassigned"
            if sec:
                class_name = f"{sec.class_level}-{sec.name}"

            list_data.append({
                "participation_id": part.participation_id,
                "student_id": student.student_id,
                "name": student.full_name,
                "roll": student.admission_number,
                "class": class_name,
                "status": part.status,
                "role": part.student_role
            })
            
        return jsonify({"participants": list_data})

    except Exception as e:
        print(f"CRITICAL ERROR in Event Participants: {e}") # Check terminal for details
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/mark_attendance', methods=['POST'])
def mark_event_attendance():
    try:
        data = request.json
        part = DetentionRecord.query.get(data.get('participation_id')) # Wait, wrong table query in previous code? 
        # Correction: It should be EventParticipation. 
        # Let's write the clean query.
        
        part = EventParticipation.query.get(data.get('participation_id'))
        if not part: return jsonify({"error": "Record not found"}), 404
        
        new_status = 'Attended' if data.get('status') else 'Nominated'
        part.status = new_status
        
        # --- NEW: RETROACTIVE OD UPDATE ---
        if new_status == 'Attended':
            event = db.session.get(EventMaster, part.event_id)
            student_id = part.student_id
            
            # Iterate through every day of the event
            curr_date = event.start_date
            while curr_date <= event.end_date:
                # Find all attendance records for this student on this day
                # We join SessionLog to filter by date, and WeeklySchedule to filter by time
                query = (db.session.query(AttendanceTransaction)
                         .join(SessionLog, AttendanceTransaction.session_id == SessionLog.session_id)
                         .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                         .filter(AttendanceTransaction.student_id == student_id)
                         .filter(SessionLog.session_date == curr_date))
                
                # If event has specific times, filter for overlap
                # Overlap Logic: (StartA < EndB) and (EndA > StartB)
                if event.start_time and event.end_time:
                    query = query.filter(
                        WeeklySchedule.start_time < event.end_time,
                        WeeklySchedule.end_time > event.start_time
                    )
                
                # Execute Update
                transactions = query.all()
                updated_count = 0
                for txn in transactions:
                    # Overwrite Absent/Present with OnDuty
                    if txn.status != 'OnDuty':
                        txn.status = 'OnDuty'
                        updated_count += 1
                
                print(f"DEBUG: Updated {updated_count} records to OD for Student {student_id} on {curr_date}")
                
                curr_date += timedelta(days=1)
        # ----------------------------------

        # NOTIFY STUDENT when status changes
        try:
            event = db.session.get(EventMaster, part.event_id)
            event_name = event.event_name if event else "Event"
            if new_status == 'Attended':
                send_notification(
                    part.student_id,
                    "Event Attendance",
                    f"Attendance marked for: {event_name}.",
                    "success",
                    "/student/dashboard",
                )
            else:
                send_notification(
                    part.student_id,
                    "Event Update",
                    f"Your event participation status was updated for: {event_name}.",
                    "info",
                    "/student/dashboard",
                )
        except Exception as e:
            print(f"Event notify failed: {e}")

        db.session.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception as e: 
        print(f"Event Update Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/delete', methods=['POST'])
def delete_faculty_event():
    try:
        data = request.json
        event = EventMaster.query.get(data.get('event_id'))
        if not event: return jsonify({"error": "Event not found"}), 404
        if event.coordinator_id != data.get('user_id'): return jsonify({"error": "Unauthorized"}), 403
        if EventParticipation.query.filter_by(event_id=event.event_id).count() > 0: return jsonify({"error": "Cannot delete: Remove students first"}), 400
        db.session.delete(event); db.session.commit()
        return jsonify({"message": "Deleted"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500



# In app.py

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"notifications": [], "unread": 0}), 200
        
        # 1. Identify Target IDs (User + Linked Students if Parent)
        target_ids = [user_id]

        children = StudentProfile.query.filter_by(parent_user_id=user_id).all()
        child_prefix_map = {}
        for c in children:
            try:
                first_name = (c.full_name or '').split()[0]
            except Exception:
                first_name = ''
            child_prefix_map[c.student_id] = first_name or (c.admission_number or 'Child')

        if children:
            target_ids.extend([c.student_id for c in children])
            
        # 2. Fetch Notifications for ALL target IDs
        # We fetch unread + recent read (limit 20)
        notifs = (Notification.query
                  .filter(Notification.user_id.in_(target_ids))
                  .order_by(Notification.timestamp.desc())
                  .limit(20)
                  .all())
        
        data = []
        unread_count = 0
        for n in notifs:
            if not n.is_read: unread_count += 1
            
            time_diff = datetime.now() - n.timestamp
            if time_diff.days > 0: time_ago = f"{time_diff.days}d ago"
            elif time_diff.seconds > 3600: time_ago = f"{time_diff.seconds//3600}h ago"
            else: time_ago = f"{time_diff.seconds//60}m ago"
            
            # Add a visual indicator if it's for a child
            prefix = ""
            child_label = child_prefix_map.get(n.user_id)
            if child_label:
                prefix = f"[{child_label}] "
            
            data.append({
                "id": n.id, 
                "title": prefix + n.title, 
                "message": n.message, 
                "type": n.type, 
                "link": n.link, 
                "is_read": n.is_read, 
                "time": time_ago 
            })
            
        return jsonify({"notifications": data, "unread": unread_count})

    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/notifications/mark_read', methods=['POST'])
def mark_notification_read():
    try:
        notif_id = request.json.get('id')
        if notif_id == 'all':
            user_id = request.json.get('user_id')
            if not user_id:
                return jsonify({"error": "user_id required"}), 400

            # Parent users can see their linked students' notifications too; clear all.
            target_ids = [user_id]
            children = StudentProfile.query.filter_by(parent_user_id=user_id).all()
            if children:
                target_ids.extend([c.student_id for c in children])

            Notification.query.filter(Notification.user_id.in_(target_ids), Notification.is_read == False).update({'is_read': True})
        else:
            n = Notification.query.get(notif_id)
            if n: n.is_read = True
        db.session.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# ==========================================
# UPLOAD APIs (Admin Only - Protected)
# ==========================================
@app.route('/api/upload/master_dept_subject', methods=['POST'])
@login_required
@require_roles('Admin')
def upload_dept_subject():
    try:
        dept_ids = _get_admin_scope_dept_ids()
        file = get_db_file_handle(request); df = pd.read_csv(file, dtype=str)

        # Department Admins can only upload for their own department.
        if dept_ids is not None:
            if not dept_ids:
                return jsonify({"error": "Admin department scope not set. Assign Department Admin to a department first."}), 403
            allowed_depts = Department.query.filter(Department.dept_id.in_(dept_ids)).all()
            allowed_names = {d.name for d in allowed_depts}
            csv_names = {str(x).strip() for x in df['Department Name'].dropna().unique()}
            disallowed = sorted([n for n in csv_names if n not in allowed_names])
            if disallowed:
                return jsonify({
                    "error": "Department Admin can only upload data for their own department",
                    "disallowed_departments": disallowed,
                }), 403

        unique_depts = df['Department Name'].dropna().unique()
        for dept_name in unique_depts:
            # Only SuperAdmin can create new departments.
            if dept_ids is None:
                if not Department.query.filter_by(name=str(dept_name).strip()).first():
                    db.session.add(Department(name=str(dept_name).strip()))
        db.session.commit()
        for _, row in df.iterrows():
            dept = Department.query.filter_by(name=str(row['Department Name']).strip()).first()
            if dept and not Subject.query.filter_by(code=str(row['Subject Code']).strip()).first():
                db.session.add(Subject(name=str(row['Subject Name']).strip(), code=str(row['Subject Code']).strip(), dept_id=dept.dept_id))
        db.session.commit()
        log_activity("Bulk Import", "Uploaded Departments & Subjects")
        return jsonify({"message": "Uploaded"}), 201
    except Exception:
        app.logger.exception("upload_dept_subject failed")
        return jsonify({"error": "Upload failed. Check file format."}), 400

@app.route('/api/upload/master_class', methods=['POST'])
@login_required
@require_roles('Admin')
def upload_classes():
    try:
        dept_ids = _get_admin_scope_dept_ids()
        file = get_db_file_handle(request)
        df = pd.read_csv(file, dtype=str).fillna('')

        created = 0
        updated = 0

        # Optional columns to help map each class section to a specialization.
        # If missing, we can infer from Section Name (e.g., DA1 -> DA) or auto-assign
        # when the department has exactly one specialization.
        def _pick_col(*candidates):
            for c in candidates:
                if c in df.columns:
                    return c
            return None

        spec_code_col = _pick_col('Specialization Code', 'Spec Code', 'Specialisation Code')
        spec_name_col = _pick_col('Specialization', 'Specialisation')

        scoped_specs = None
        scoped_specs_by_code = {}
        scoped_specs_by_name = {}
        if dept_ids is not None:
            if not dept_ids:
                return jsonify({"error": "Admin department scope not set. Assign Department Admin to a department first."}), 403
            scoped_specs = Specialization.query.filter(Specialization.dept_id.in_(dept_ids)).all()
            scoped_specs_by_code = {str(s.code).strip(): s for s in scoped_specs if getattr(s, 'code', None)}
            scoped_specs_by_name = {str(s.name).strip().casefold(): s for s in scoped_specs if getattr(s, 'name', None)}

        mapping_errors = []
        for idx, row in df.iterrows():
            class_level = str(row.get('Class Level', '')).strip()
            section_name = str(row.get('Section Name', '')).strip()
            if not class_level or not section_name:
                continue

            # Determine specialization for this row.
            spec = None
            spec_code = ''
            spec_name = ''

            if spec_code_col:
                spec_code = str(row.get(spec_code_col, '')).strip()
            if not spec_code:
                spec_code = _infer_spec_code_from_section_name(section_name)

            if spec_name_col:
                spec_name = str(row.get(spec_name_col, '')).strip()

            if dept_ids is None:
                # SuperAdmin/global: try to resolve by code, else proceed without spec.
                if spec_code:
                    spec = Specialization.query.filter_by(code=spec_code).first()
                if not spec and spec_name:
                    spec = Specialization.query.filter(Specialization.name.ilike(spec_name)).first()
            else:
                # Department Admin: scoped mapping required, but allow auto-assign if only one spec exists.
                if scoped_specs and len(scoped_specs) == 1:
                    spec = scoped_specs[0]
                else:
                    if spec_code and spec_code in scoped_specs_by_code:
                        spec = scoped_specs_by_code.get(spec_code)
                    elif spec_name and spec_name.casefold() in scoped_specs_by_name:
                        spec = scoped_specs_by_name.get(spec_name.casefold())

                if not spec:
                    mapping_errors.append({
                        "row": int(idx) + 2,
                        "class_level": class_level,
                        "section_name": section_name,
                        "inferred_spec_code": spec_code,
                        "hint": "Preferred: set 'Section Name' equal to the Specialization Code (e.g., DA, CORE). Or add 'Specialization Code' column explicitly.",
                    })
                    continue

            existing = ClassSection.query.filter_by(class_level=class_level, name=section_name).first()
            if not existing:
                db.session.add(ClassSection(class_level=class_level, name=section_name, spec_id=(spec.id if spec else None)))
                created += 1
            else:
                if spec and getattr(existing, 'spec_id', None) in (None, 0):
                    existing.spec_id = spec.id
                    updated += 1
        db.session.commit()
        if mapping_errors:
            return jsonify({
                "error": "Some rows could not be mapped to a specialization in this department.",
                "details": mapping_errors[:25],
                "details_truncated": len(mapping_errors) > 25,
            }), 400
        log_activity("Bulk Import", f"Created {created} Class Sections")
        msg = f"{created} created"
        if updated:
            msg += f", {updated} linked to specialization"
        return jsonify({"message": msg}), 201
    except Exception:
        app.logger.exception("upload_classes failed")
        return jsonify({"error": "Upload failed. Check file format."}), 400


@app.route('/api/upload/semester_course_structure', methods=['POST'])
@login_required
@require_roles('Admin')
def upload_semester_course_structure():
    """Upload semester course structure independent of faculty allocation.

    Expected CSV columns (as in subject list-ltp.csv):
      - Course Code, Course, Course Type, Section, SEM, Class Level, L, T, P, Credits

    Optional query param:
      - parity: 'odd' or 'even' (validates SEM parity during upload)

    Behavior:
      - Upserts Subjects by Course Code
      - Replaces SemesterCourseStructure rows per (section_id, semester_no)
    """
    try:
        parity = (request.args.get('parity') or '').strip().lower()  # odd|even|''
        if parity and parity not in ['odd', 'even']:
            return jsonify({"error": "Invalid parity; must be 'odd' or 'even'"}), 400

        file = get_db_file_handle(request)
        df = pd.read_csv(file, dtype=str).fillna('')

        required_cols = ['Course Code', 'Course', 'Course Type', 'Section', 'SEM', 'Class Level']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return jsonify({"error": f"Missing columns: {', '.join(missing)}"}), 400

        def clean_int(val):
            v = str(val).strip()
            return int(v) if v.isdigit() else 0

        # Track which (section_id, semester_no) combos appear so we can replace structures.
        seen_keys = set()
        errors = []
        upserted_subjects = 0
        inserted_rows = 0
        skipped_rows = 0

        # Pre-resolve ClassSections and prep a replacement plan.
        for idx, row in df.iterrows():
            course_code = str(row.get('Course Code', '')).strip()
            section_name = str(row.get('Section', '')).strip()
            class_level = str(row.get('Class Level', '')).strip()
            sem_raw = str(row.get('SEM', '')).strip()

            if not course_code or not section_name or not class_level or not sem_raw:
                skipped_rows += 1
                errors.append(f"Row {idx+2}: Missing Course Code / Section / Class Level / SEM")
                continue

            semester_no = parse_semester_no(sem_raw)
            if not semester_no or semester_no < 1 or semester_no > 8:
                skipped_rows += 1
                errors.append(f"Row {idx+2}: Invalid SEM '{sem_raw}'")
                continue

            if parity:
                is_odd = (semester_no % 2) == 1
                if (parity == 'odd' and not is_odd) or (parity == 'even' and is_odd):
                    skipped_rows += 1
                    errors.append(f"Row {idx+2}: SEM '{sem_raw}' does not match parity '{parity}'")
                    continue

            section = _resolve_class_section_for_csv(class_level, section_name)
            if not section:
                skipped_rows += 1
                errors.append(f"Row {idx+2}: Class section '{class_level}-{section_name}' not found. Ensure Class Level + Section match your Class Sections upload (Section should be specialization code).")
                continue

            seen_keys.add((section.section_id, semester_no))

        # Replace existing structures for the seen keys.
        for section_id, semester_no in sorted(seen_keys):
            SemesterCourseStructure.query.filter_by(section_id=section_id, semester_no=semester_no).delete()
        db.session.flush()

        # Insert new structures.
        for idx, row in df.iterrows():
            course_code = str(row.get('Course Code', '')).strip()
            course_name = str(row.get('Course', '')).strip()
            course_type_raw = str(row.get('Course Type', 'Core')).strip()
            section_name = str(row.get('Section', '')).strip()
            class_level = str(row.get('Class Level', '')).strip()
            sem_raw = str(row.get('SEM', '')).strip()

            if not course_code or not section_name or not class_level or not sem_raw:
                continue

            semester_no = parse_semester_no(sem_raw)
            if not semester_no or semester_no < 1 or semester_no > 8:
                continue

            if parity:
                is_odd = (semester_no % 2) == 1
                if (parity == 'odd' and not is_odd) or (parity == 'even' and is_odd):
                    continue

            section = _resolve_class_section_for_csv(class_level, section_name)
            if not section:
                continue

            # Subject type normalization (reuse existing approach)
            is_core_keyword = any(x in course_type_raw for x in ["Core", "PCC", "BSC", "ESC", "HSMC", "HSSM", "MDHC", "VSEC", "PEC", "CEP", "MDM"])
            subj_type = "Core" if is_core_keyword else course_type_raw

            l_val = clean_int(row.get('L', '0'))
            t_val = clean_int(row.get('T', '0'))
            p_val = clean_int(row.get('P', '0'))
            c_val = clean_int(row.get('Credits', '0'))

            subject = Subject.query.filter_by(code=course_code).first()
            if not subject:
                subject = Subject(
                    name=course_name or course_code,
                    code=course_code,
                    subject_type=subj_type,
                    l_count=l_val,
                    t_count=t_val,
                    p_count=p_val,
                    credits=c_val,
                )
                db.session.add(subject)
                db.session.flush()
                upserted_subjects += 1
            else:
                # Keep latest name/LTP/type from upload
                if course_name:
                    subject.name = course_name
                subject.subject_type = subj_type
                subject.l_count = l_val
                subject.t_count = t_val
                subject.p_count = p_val
                subject.credits = c_val

            db.session.add(SemesterCourseStructure(section_id=section.section_id, semester_no=semester_no, subject_id=subject.subject_id))
            inserted_rows += 1

        db.session.commit()
        log_activity("Bulk Import", f"Uploaded semester course structure ({inserted_rows} rows)")
        return jsonify({
            "message": f"Uploaded structure: {inserted_rows} rows.",
            "subjects_upserted": upserted_subjects,
            "structures_replaced": len(seen_keys),
            "skipped": skipped_rows,
            "errors": errors,
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/upload/rooms', methods=['POST'])
@login_required
@require_roles('Admin')
def upload_rooms():
    try:
        file = get_db_file_handle(request)
        # CSV Headers: Room Number, Type, Capacity, Location, Department Name
        df = pd.read_csv(file, dtype=str).fillna('')
        
        success = 0
        for _, row in df.iterrows():
            r_num = row['Room Number'].strip()
            r_type = row['Type'].strip() # e.g. "Laboratory"
            
            # 1. Find Dept
            dept_name = str(row['Department Name']).strip()
            dept = Department.query.filter_by(name=dept_name).first()
            
            # 2. Check Duplicate
            if RoomMaster.query.filter_by(room_number=r_num).first():
                continue
                
            # 3. Create Room
            new_room = RoomMaster(
                room_number=r_num,
                room_type=r_type,
                capacity=int(row['Capacity']),
                location=row['Location'],
                dept_id=dept.dept_id if dept else None
            )
            db.session.add(new_room)
            success += 1
            
        db.session.commit()
        log_activity("Bulk Import", f"Added {success} rooms to Infrastructure")
        return jsonify({"message": f"Infrastructure updated: {success} rooms added."}), 201

    except Exception:
        app.logger.exception("upload_rooms failed")
        return jsonify({"error": "Upload failed. Check file format."}), 500


@app.route('/api/upload/staff', methods=['POST'])
@login_required
@require_roles('Admin')
def upload_staff():
    try:
        file = get_db_file_handle(request); df = pd.read_csv(file)
        count = 0
        skipped = 0
        errors = []
        created_accounts = []  # Track for admin to see temp passwords
        
        # Department scope check for non-SuperAdmin
        scope_dept_ids = _get_admin_scope_dept_ids()
        
        for _, row in df.iterrows():
            if UserMaster.query.filter_by(username=row['Email']).first(): continue
            
            # Handle Dept - use flexible lookup with abbreviation support
            d_name = str(row['Department Name']).strip()
            dept = _find_department_flexible(d_name, scope_dept_ids)
            
            # Department Admin scope validation
            if scope_dept_ids is not None:
                if not dept:
                    errors.append({
                        "email": row['Email'],
                        "error": f"Department '{d_name}' does not exist or is not in your scope. Create it in hierarchy first."
                    })
                    skipped += 1
                    continue
                # Already filtered by scope in _find_department_flexible
            else:
                # SuperAdmin: auto-create department if needed
                if not dept: 
                    dept = Department(name=d_name)
                    db.session.add(dept); db.session.flush()
            
            new_uuid = str(uuid.uuid4())
            # Default password - users must change on first login
            default_password = 'Staff@123'
            
            # Create Login - must flush before creating profile due to FK constraint
            db.session.add(UserMaster(
                user_id=new_uuid, 
                username=row['Email'], 
                password_hash=generate_password_hash(default_password), 
                user_type=row.get('Role', 'Staff'), 
                is_active=True,
                must_change_password=True  # Force password change on first login
            ))
            db.session.flush()  # Ensure UserMaster exists before StaffProfile
            
            # Create Profile with Designation
            # Default to 'Assistant Professor' if column missing in CSV
            desig = row.get('Designation').strip() if row.get('Designation') else 'Assistant Professor'
            
            db.session.add(StaffProfile(
                staff_id=new_uuid, 
                full_name=row['Full Name'], 
                employee_code=str(row['Employee Code']).strip(), 
                email_contact=row['Email'], 
                primary_department_id=dept.dept_id,
                designation=desig
            ))
            created_accounts.append({"email": row['Email'], "temp_password": default_password})
            count += 1
            
        db.session.commit()
        log_activity("Bulk Import", f"Onboarded {count} Staff Members")
        # Return info about default password
        response = {
            "message": f"Staff uploaded: {count} accounts created",
            "default_password": "Staff@123",
            "note": "All staff accounts use default password 'Staff@123'. Users must change password on first login."
        }
        if skipped > 0:
            response["skipped"] = skipped
            response["errors"] = errors
        return jsonify(response), 201
    except Exception:
        app.logger.exception("upload_staff failed")
        return jsonify({"error": "Upload failed. Check file format."}), 400

@app.route('/api/upload/students', methods=['POST'])
@login_required
@require_roles('Admin')
def upload_students():
    try:
        file = get_db_file_handle(request)
        df = pd.read_csv(file, dtype=str).fillna('')
        
        count = 0
        updated = 0
        errors = []
        created_accounts = []  # Track for admin
        # Local cache to handle siblings in the same CSV efficiently
        # Format: { 'phone_number': 'user_id_uuid' }
        processed_parents = {} 

        for _, row in df.iterrows():
            parent_phone = str(row['Parent Phone']).strip()
            
            # 1. Resolve Parent ID (Handle Siblings & New Parents)
            parent_uuid = None
            
            # Check Local Cache first
            if parent_phone in processed_parents:
                parent_uuid = processed_parents[parent_phone]
            else:
                # Check Database
                existing_parent = UserMaster.query.filter_by(username=parent_phone).first()
                if existing_parent:
                    parent_uuid = existing_parent.user_id
                    processed_parents[parent_phone] = parent_uuid
                else:
                    # Create New Parent User with default password
                    parent_uuid = str(uuid.uuid4())
                    parent_default_pwd = 'Parent@123'
                    db.session.add(UserMaster(
                        user_id=parent_uuid, 
                        username=parent_phone, 
                        password_hash=generate_password_hash(parent_default_pwd), 
                        user_type='Parent', 
                        is_active=True,
                        must_change_password=True  # Force password change on first login
                    ))
                    db.session.flush() # CRITICAL: Create Parent User immediately

                    # Create Parent Profile
                    db.session.add(ParentProfile(
                        parent_id=parent_uuid, 
                        father_name=row['Father Name'], 
                        mother_name=row['Mother Name'], 
                        primary_phone=parent_phone
                    ))
                    db.session.flush() # Ensure Profile is ready
                    
                    processed_parents[parent_phone] = parent_uuid
                    created_accounts.append({"type": "parent", "username": parent_phone, "password": "Parent@123"})

            # 2. Resolve class section (needed even for existing students so we can repair assignment)
            admission_no = str(row.get('Admission Number', '')).strip()
            c_level = str(row.get('Class Level', '')).strip()
            c_sec = str(row.get('Section Name', '')).strip()
            if not admission_no:
                errors.append({"error": "Missing Admission Number"})
                continue

            section = _resolve_class_section_for_csv(c_level, c_sec)
            if not section:
                errors.append({
                    "admission_number": admission_no,
                    "class_level": c_level,
                    "section": c_sec,
                    "error": "Class section not found. Upload Class Sections first (Class Level + Section Name must match; Section Name should be specialization code like DA/CORE)."
                })
                continue

            # Department-scoped admins can only upload students into their own department.
            scope_dept_ids = _get_admin_scope_dept_ids()
            if scope_dept_ids is not None:
                deny = _ensure_section_in_scope(int(section.section_id))
                if deny:
                    errors.append({
                        "admission_number": admission_no,
                        "class_level": c_level,
                        "section": c_sec,
                        "error": "Out of scope. This class section is not mapped to your department (check specialization mapping)."
                    })
                    continue

            # 3. Create or update student
            existing_student = StudentProfile.query.filter_by(admission_number=admission_no).first()
            if existing_student:
                # Repair missing/wrong section assignments on re-upload.
                if getattr(existing_student, 'current_section_id', None) != section.section_id:
                    existing_student.current_section_id = section.section_id
                    updated += 1
                continue

            # New student create path
            student_uuid = str(uuid.uuid4())

            # Default password - students must change on first login
            student_default_pwd = 'Student@123'
            student_email = row.get('Student Email') or f"{admission_no}@school.mituniversity.edu.in"

            # A. Create Student Login
            db.session.add(UserMaster(
                user_id=student_uuid,
                username=student_email,
                password_hash=generate_password_hash(student_default_pwd),
                user_type='Student',
                is_active=True,
                must_change_password=True  # Force password change on first login
            ))

            # --- FIX: Force DB to recognize UserMaster BEFORE creating Profile ---
            db.session.flush()
            # -------------------------------------------------------------------

            # B. Create Student Profile
            db.session.add(StudentProfile(
                student_id=student_uuid,
                full_name=row['Student Full Name'],
                admission_number=admission_no,
                parent_user_id=parent_uuid,
                current_section_id=section.section_id,
            ))
            created_accounts.append({"type": "student", "username": student_email, "password": "Student@123"})
            count += 1
        
        db.session.commit()
        log_activity("Bulk Import", f"Enrolled {count} Students")
        msg = f"Successfully enrolled {count} students."
        if updated:
            msg += f" Updated {updated} existing students."
        return jsonify({
            "message": msg,
            "updated": updated,
            "errors": errors,
            "default_passwords": {"student": "Student@123", "parent": "Parent@123"},
            "note": "All accounts use default passwords. Users must change password on first login.",
            "security_note": "Distribute these temporary passwords securely. Users should change passwords on first login."
        }), 201

    except Exception:
        db.session.rollback() # Important: Rollback if anything fails
        app.logger.exception("upload_students failed")
        return jsonify({"error": "Upload failed. Check file format."}), 500

@app.route('/api/upload/schedule', methods=['POST'])
@login_required
@require_roles('Admin')
def upload_schedule():
    try:
        scope_dept_ids = _get_admin_scope_dept_ids()
        file = get_db_file_handle(request)
        df = pd.read_csv(file, dtype=str).fillna('')

        # Track versions created per section (creates DRAFT versions)
        sections_processed = {}  # section_id -> version_id
        success = 0
        errors = []

        for index, row in df.iterrows():
            # 1. Basic Lookups
            subject = Subject.query.filter_by(code=str(row['Subject Code']).strip()).first()
            teacher = StaffProfile.query.filter_by(employee_code=str(row['Employee Code']).strip()).first()
            section = _resolve_class_section_for_csv(str(row['Class Level']).strip(), str(row['Section Name']).strip())

            if not subject or not teacher or not section:
                errors.append(f"Row {index}: Data missing (Subject/Teacher/Class not found)")
                continue

            # Department scope validation for non-SuperAdmin
            if scope_dept_ids is not None:
                deny = _ensure_section_in_scope(int(section.section_id))
                if deny:
                    errors.append(f"Row {index}: Section '{section.name}' is out of scope for your department")
                    continue

            # 2. Create or get draft version for this section
            if section.section_id not in sections_processed:
                # Check for existing draft
                existing_draft = TimetableVersion.query.filter_by(
                    section_id=section.section_id,
                    status='Draft'
                ).first()

                if existing_draft:
                    # Delete existing draft slots (will be replaced)
                    WeeklySchedule.query.filter_by(version_id=existing_draft.version_id).delete()
                    draft_version = existing_draft
                else:
                    # Create new draft
                    max_version = db.session.query(db.func.max(TimetableVersion.version_number)).filter_by(section_id=section.section_id).scalar() or 0
                    draft_version = TimetableVersion(
                        section_id=section.section_id,
                        version_number=max_version + 1,
                        version_label=f"CSV Upload {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        status='Draft',
                        created_by_id=current_user.user_id,
                        source_type='csv_upload'
                    )
                    db.session.add(draft_version)
                    db.session.flush()

                sections_processed[section.section_id] = draft_version.version_id

            version_id = sections_processed[section.section_id]

            # 3. Parse Times
            start = parse_flexible_time(row['Start Time'])
            end = parse_flexible_time(row['End Time'])
            if not start or not end:
                errors.append(f"Row {index}: Invalid Time Format")
                continue

            # 4. Parse Metadata (Type, Batch, Room)
            sess_type = str(row.get('Session Type', 'Lecture')).strip()

            raw_batch = str(row.get('Batch', '')).strip()
            target_batch = raw_batch if raw_batch else None

            # Room Lookup
            room_num = str(row.get('Room Number', '')).strip()
            room = RoomMaster.query.filter_by(room_number=room_num).first()
            room_id = room.room_id if room else None

            # 5. Save Slot with version_id
            new_slot = WeeklySchedule(
                section_id=section.section_id,
                subject_id=subject.subject_id,
                teacher_id=teacher.staff_id,
                day_of_week=str(row['Day']).strip(),
                start_time=start,
                end_time=end,
                session_type=sess_type,
                target_batch=target_batch,
                room_id=room_id,
                version_id=version_id  # Link to draft version
            )
            db.session.add(new_slot)
            success += 1

        db.session.commit()
        log_activity("Bulk Import", f"Uploaded Weekly Schedule ({success} slots) as DRAFT.")
        return jsonify({
            "message": f"{success} slots created as DRAFT",
            "sections_affected": list(sections_processed.keys()),
            "note": "Schedule saved as draft. Use Version Manager to preview and publish.",
            "errors": errors
        }), 201
    except Exception:
        db.session.rollback()
        app.logger.exception("upload_schedule failed")
        return jsonify({"error": "Upload failed. Check file format."}), 500
    

@app.route('/api/upload/assign_class_teachers', methods=['POST'])
@login_required
@require_roles('Admin')
def upload_class_teachers():
    try:
        scope_dept_ids = _get_admin_scope_dept_ids()
        file = get_db_file_handle(request); df = pd.read_csv(file, dtype=str)
        success = 0; errors = []
        for index, row in df.iterrows():
            cls = _resolve_class_section_for_csv(row['Class Level'].strip(), row['Section Name'].strip())
            user = UserMaster.query.filter_by(username=row['Teacher Email'].strip()).first()
            if not cls or not user: errors.append(f"Row {index}: Data mismatch"); continue
            
            # Department scope validation for non-SuperAdmin
            if scope_dept_ids is not None:
                deny = _ensure_section_in_scope(int(cls.section_id))
                if deny:
                    errors.append(f"Row {index}: Section '{cls.name}' is out of scope for your department")
                    continue
            
            staff = StaffProfile.query.get(user.user_id)
            if staff: cls.class_teacher_id = staff.staff_id; success += 1
        db.session.commit()
        log_activity("Role Update", f"Bulk Assigned {success} Class Teachers")
        response = {"message": f"{success} assigned"}
        if errors:
            response["errors"] = errors
        return jsonify(response), 201
    except Exception:
        app.logger.exception("upload_class_teachers failed")
        return jsonify({"error": "Upload failed. Check file format."}), 500



# In app.py

# ==========================================
# API: MENTOR LOGGING
# ==========================================

# In app.py

# ==========================================
# API: MENTOR MEETING SCHEDULER
# ==========================================

@app.route('/api/mentor/schedule_meeting', methods=['POST'])
@login_required
@require_roles('Staff', 'Admin')
def schedule_mentor_meeting():
    try:
        data = request.json
        mentor_id = data.get('mentor_id')
        batch_id = data.get('batch_id')

        # 1. Count existing meetings
        count = MentorMeeting.query.filter_by(batch_id=batch_id).count()
        if count >= 4:
            return jsonify({"error": "Maximum 4 mandatory meetings already scheduled."}), 400

        # 2. Create Meeting with new fields
        date_obj = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
        time_obj = datetime.strptime(data.get('time'), '%H:%M').time()

        meeting = MentorMeeting(
            mentor_id=mentor_id,
            batch_id=batch_id,
            date=date_obj,
            time=time_obj,
            agenda=data.get('agenda'),
            venue=data.get('venue'),  # New field
            discussion_points=data.get('discussion_points'),  # New field
            status='Scheduled'
        )

        # 3. Notify students with enhanced message
        venue_text = f" at {data.get('venue')}" if data.get('venue') else ""
        students = StudentProfile.query.filter_by(mentor_batch_id=batch_id).all()
        for s in students:
            send_notification(
                s.student_id,
                "Mentor Meeting Scheduled",
                f"Meeting on {data.get('date')} at {data.get('time')}{venue_text}. Agenda: {data.get('agenda')}",
                "info"
            )
        db.session.add(meeting)
        db.session.commit()

        return jsonify({"message": "Meeting scheduled successfully.", "meeting_id": meeting.meeting_id}), 200
    except Exception:
        app.logger.exception("schedule_mentor_meeting failed")
        return jsonify({"error": "Failed to schedule meeting."}), 500

@app.route('/api/mentor/get_meetings', methods=['GET'])
@login_required
@require_roles('Staff', 'Admin')
def get_mentor_meetings():
    try:
        batch_id = request.args.get('batch_id')

        meetings = MentorMeeting.query.filter_by(batch_id=batch_id).order_by(MentorMeeting.date).all()

        # Get batch info for batch_name
        batch = MentorBatch.query.get(batch_id)
        section = ClassSection.query.get(batch.section_id) if batch else None
        batch_name = f"{section.class_level}-{section.name} ({batch.batch_name})" if section and batch else "Unknown"

        meeting_list = []
        for m in meetings:
            # Count attendance and issues
            attendee_count = MeetingAttendance.query.filter_by(meeting_id=m.meeting_id, attended=True).count()
            issues_count = MeetingIssue.query.filter_by(meeting_id=m.meeting_id).count()

            meeting_list.append({
                "id": m.meeting_id,
                "batch_id": m.batch_id,
                "batch_name": batch_name,
                "date": m.date.strftime('%d %b %Y'),
                "date_raw": m.date.strftime('%Y-%m-%d'),
                "time": m.time.strftime('%I:%M %p'),
                "time_raw": m.time.strftime('%H:%M'),
                "agenda": m.agenda,
                "venue": m.venue,
                "discussion_points": m.discussion_points,
                "summary": m.summary,
                "status": m.status,
                "attendance_count": attendee_count,
                "issues_count": issues_count
            })

        return jsonify({"meetings": meeting_list, "count": len(meetings)})
    except Exception:
        app.logger.exception("get_mentor_meetings failed")
        return jsonify({"error": "Failed to fetch meetings."}), 500


@app.route('/api/mentor/get_meeting_details', methods=['GET'])
@login_required
@require_roles('Staff', 'Admin')
def get_meeting_details():
    """Get full meeting details including attendance and issues."""
    try:
        meeting_id_raw = request.args.get('meeting_id')
        try:
            meeting_id = int(meeting_id_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid meeting_id"}), 400
        meeting = db.session.get(MentorMeeting, meeting_id)
        if not meeting:
            return jsonify({"error": "Meeting not found"}), 404

        # Get mentor info
        mentor = StaffProfile.query.get(meeting.mentor_id)

        # Get batch info
        batch = MentorBatch.query.get(meeting.batch_id)
        section = ClassSection.query.get(batch.section_id) if batch else None

        # Get all students in batch with attendance status
        students = StudentProfile.query.filter_by(mentor_batch_id=meeting.batch_id).all()
        attendance_map = {
            a.student_id: a for a in
            MeetingAttendance.query.filter_by(meeting_id=meeting_id).all()
        }

        # Students list (for populating dropdowns and attendance)
        students_list = []
        for s in students:
            students_list.append({
                "student_id": s.student_id,
                "name": s.full_name,
                "roll_no": s.admission_number
            })

        # Attendance list with status
        attendance_list = []
        for s in students:
            att = attendance_map.get(s.student_id)
            attendance_list.append({
                "student_id": s.student_id,
                "name": s.full_name,
                "roll_no": s.admission_number,
                "attended": att.attended if att else False,
                "remarks": att.remarks if att else None
            })

        # Get issues raised
        issues = MeetingIssue.query.filter_by(meeting_id=meeting_id).order_by(MeetingIssue.created_at).all()
        issues_list = []
        for i in issues:
            raised_by = StudentProfile.query.get(i.raised_by_student_id) if i.raised_by_student_id else None
            issues_list.append({
                "issue_id": i.issue_id,
                "issue_description": i.issue_description,
                "category": i.category,
                "raised_by_name": raised_by.full_name if raised_by else None,
                "raised_by_student_id": i.raised_by_student_id,
                "action_taken": i.action_taken,
                "action_status": i.action_status,
                "created_at": i.created_at.strftime('%Y-%m-%d %H:%M') if i.created_at else None
            })

        batch_name = f"{section.class_level}-{section.name} ({batch.batch_name})" if section and batch else "Unknown"

        return jsonify({
            "meeting": {
                "id": meeting.meeting_id,
                "date": meeting.date.strftime('%Y-%m-%d'),
                "date_display": meeting.date.strftime('%d %b %Y'),
                "time": meeting.time.strftime('%H:%M'),
                "time_display": meeting.time.strftime('%I:%M %p'),
                "agenda": meeting.agenda,
                "venue": meeting.venue,
                "discussion_points": meeting.discussion_points,
                "summary": meeting.summary,
                "status": meeting.status,
                "batch_name": batch_name,
                "completed_at": meeting.completed_at.strftime('%Y-%m-%d %H:%M') if meeting.completed_at else None
            },
            "mentor": {
                "id": mentor.staff_id if mentor else None,
                "name": mentor.full_name if mentor else "Unknown"
            },
            "batch": {
                "id": batch.batch_id if batch else None,
                "name": batch.batch_name if batch else "Unknown",
                "class": f"{section.class_level}-{section.name}" if section else "Unknown"
            },
            "students": students_list,
            "attendance": attendance_list,
            "issues": issues_list
        })
    except Exception:
        app.logger.exception("get_meeting_details failed")
        return jsonify({"error": "Failed to fetch meeting details."}), 500


@app.route('/api/mentor/conduct_meeting', methods=['POST'])
@login_required
@require_roles('Staff', 'Admin')
def conduct_meeting():
    """Mark meeting as conducted and record attendance."""
    try:
        data = request.json
        meeting_id = data.get('meeting_id')
        attendance_list = data.get('attendance', [])
        summary = data.get('summary')

        meeting = db.session.get(MentorMeeting, meeting_id)
        if not meeting:
            return jsonify({"error": "Meeting not found"}), 404

        # Update meeting status
        meeting.status = 'Completed'
        meeting.completed_at = datetime.now()
        if summary:
            meeting.summary = summary

        # Clear existing attendance and insert new
        MeetingAttendance.query.filter_by(meeting_id=meeting_id).delete()
        for att in attendance_list:
            attendance = MeetingAttendance(
                meeting_id=meeting_id,
                student_id=att.get('student_id'),
                attended=att.get('attended', False),
                remarks=att.get('remarks')
            )
            db.session.add(attendance)

        db.session.commit()
        return jsonify({"message": "Meeting marked as completed."}), 200
    except Exception:
        app.logger.exception("conduct_meeting failed")
        return jsonify({"error": "Failed to complete meeting."}), 500


@app.route('/api/mentor/add_meeting_issue', methods=['POST'])
@login_required
@require_roles('Staff', 'Admin')
def add_meeting_issue():
    """Record an issue raised during meeting."""
    try:
        data = request.json
        meeting_id = data.get('meeting_id')
        description = data.get('issue_description') or data.get('description')
        category = data.get('category', 'General')
        raised_by_id = data.get('raised_by_student_id')
        action_taken = data.get('action_taken')

        if not meeting_id or not description:
            return jsonify({"error": "Meeting ID and description are required"}), 400

        # Get student name if provided
        raised_by_name = None
        if raised_by_id:
            student = StudentProfile.query.get(raised_by_id)
            raised_by_name = student.full_name if student else None

        issue = MeetingIssue(
            meeting_id=meeting_id,
            issue_description=description,
            category=category,
            raised_by_student_id=raised_by_id if raised_by_id else None,
            action_taken=action_taken,
            action_status='Pending' if not action_taken else 'In Progress'
        )
        db.session.add(issue)
        db.session.commit()

        return jsonify({
            "message": "Issue recorded.",
            "issue": {
                "issue_id": issue.issue_id,
                "issue_description": issue.issue_description,
                "category": issue.category,
                "raised_by_student_id": issue.raised_by_student_id,
                "raised_by_name": raised_by_name,
                "action_taken": issue.action_taken,
                "action_status": issue.action_status
            }
        }), 200
    except Exception:
        app.logger.exception("add_meeting_issue failed")
        return jsonify({"error": "Failed to add issue."}), 500


@app.route('/api/mentor/update_meeting_issue', methods=['POST'])
@login_required
@require_roles('Staff', 'Admin')
def update_meeting_issue():
    """Update action taken on an issue."""
    try:
        data = request.json
        issue_id = data.get('issue_id')
        action_taken = data.get('action_taken')
        action_status = data.get('action_status', 'Pending')

        issue = db.session.get(MeetingIssue, issue_id)
        if not issue:
            return jsonify({"error": "Issue not found"}), 404

        issue.action_taken = action_taken
        issue.action_status = action_status
        if action_status == 'Resolved':
            issue.resolved_at = datetime.now()

        db.session.commit()
        return jsonify({"message": "Issue updated."}), 200
    except Exception:
        app.logger.exception("update_meeting_issue failed")
        return jsonify({"error": "Failed to update issue."}), 500


@app.route('/api/mentor/get_meeting_report', methods=['GET'])
@login_required
@require_roles('Staff', 'Admin')
def get_meeting_report():
    """Get comprehensive meeting data for PDF generation."""
    try:
        meeting_id_raw = request.args.get('meeting_id')
        try:
            meeting_id = int(meeting_id_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid meeting_id"}), 400
        meeting = db.session.get(MentorMeeting, meeting_id)
        if not meeting:
            return jsonify({"error": "Meeting not found"}), 404

        # Get mentor info
        mentor = StaffProfile.query.get(meeting.mentor_id)

        # Get batch info
        batch = MentorBatch.query.get(meeting.batch_id)
        section = ClassSection.query.get(batch.section_id) if batch else None

        # Get attendance with student details
        students = StudentProfile.query.filter_by(mentor_batch_id=meeting.batch_id).order_by(StudentProfile.admission_number).all()
        attendance_map = {
            a.student_id: a for a in
            MeetingAttendance.query.filter_by(meeting_id=meeting_id).all()
        }

        attendance_list = []
        present_count = 0
        for s in students:
            att = attendance_map.get(s.student_id)
            attended = att.attended if att else False
            if attended:
                present_count += 1
            attendance_list.append({
                "roll_no": s.admission_number,
                "name": s.full_name,
                "attended": attended,
                "remarks": att.remarks if att else ""
            })

        # Get issues
        issues = MeetingIssue.query.filter_by(meeting_id=meeting_id).order_by(MeetingIssue.created_at).all()
        issues_list = []
        for i in issues:
            raised_by = StudentProfile.query.get(i.raised_by_student_id) if i.raised_by_student_id else None
            issues_list.append({
                "issue_description": i.issue_description,
                "category": i.category,
                "raised_by": raised_by.full_name if raised_by else "General",
                "action_taken": i.action_taken or "-",
                "action_status": i.action_status
            })

        batch_name = f"{section.class_level}-{section.name} ({batch.batch_name})" if section and batch else "Unknown"

        # Return structure expected by frontend (data.meeting, data.attendance, data.issues)
        return jsonify({
            "meeting": {
                "meeting_number": MentorMeeting.query.filter(
                    MentorMeeting.batch_id == meeting.batch_id,
                    MentorMeeting.date <= meeting.date
                ).count(),
                "date": meeting.date.strftime('%d %b %Y'),
                "time": meeting.time.strftime('%I:%M %p'),
                "venue": meeting.venue or "Not specified",
                "agenda": meeting.agenda,
                "discussion_points": meeting.discussion_points,
                "summary": meeting.summary or "",
                "mentor_name": mentor.full_name if mentor else "Unknown",
                "batch_name": batch_name,
                "total_students": len(students),
                "present_count": present_count,
                "term": "",
                "academic_year": "",
                "school": "",
                "department": ""
            },
            "attendance": attendance_list,
            "issues": issues_list
        })
    except ProgrammingError:
        app.logger.exception("get_meeting_report failed (db schema)")
        return jsonify({
            "error": "Meeting report tables are not ready. Run database migrations (flask db upgrade) and retry."
        }), 503
    except SQLAlchemyError:
        app.logger.exception("get_meeting_report failed (db)")
        return jsonify({"error": "Database error while generating meeting report."}), 500
    except Exception:
        app.logger.exception("get_meeting_report failed")
        return jsonify({"error": "Failed to generate report data."}), 500


@app.route('/api/mentor/my_pending_issues', methods=['GET'])
@login_required
@require_roles('Staff', 'Admin')
def get_mentor_pending_issues():
    """Get all pending (Open) logs for a mentor across all their batches."""
    try:
        mentor_id = request.args.get('mentor_id')

        # Get all batches for this mentor
        my_batches = MentorBatch.query.filter_by(mentor_id=mentor_id).all()
        batch_ids = [b.batch_id for b in my_batches]

        if not batch_ids:
            return jsonify({"issues": [], "count": 0})

        # Get all Open and Escalated logs for students in mentor's batches
        logs = (db.session.query(MentorLog, StudentProfile)
                .join(StudentProfile, MentorLog.student_id == StudentProfile.student_id)
                .filter(MentorLog.mentor_batch_id.in_(batch_ids))
                .filter(MentorLog.status.in_(['Open', 'Escalated']))
                .order_by(MentorLog.date.desc())
                .all())

        issue_list = []
        for log, student in logs:
            issue_list.append({
                "log_id": log.log_id,
                "student_id": log.student_id,
                "student_name": student.full_name,
                "date": log.date.strftime('%Y-%m-%d'),
                "category": log.issue_category,
                "remarks": log.remarks,
                "action_taken": log.action_taken,
                "status": log.status
            })

        return jsonify({"issues": issue_list, "count": len(issue_list)})
    except Exception:
        app.logger.exception("get_mentor_pending_issues failed")
        return jsonify({"error": "Failed to fetch pending issues."}), 500


@app.route('/api/mentor/get_logs', methods=['GET'])
def get_mentor_logs():
    try:
        student_id = request.args.get('student_id')
        
        logs = (db.session.query(MentorLog, StaffProfile)
                .join(StaffProfile, MentorLog.mentor_id == StaffProfile.staff_id)
                .filter(MentorLog.student_id == student_id)
                .order_by(MentorLog.date.desc())
                .all())
        
        log_data = []
        for log, mentor in logs:
            log_data.append({
                "id": log.log_id,
                "date": log.date.strftime('%Y-%m-%d'),
                "mentor_name": mentor.full_name,
                "category": log.issue_category,
                "remarks": log.remarks,
                "action": log.action_taken,
                "status": log.status
            })
            
        return jsonify({"logs": log_data})
    except Exception as e: return jsonify({"error": str(e)}), 500

# @app.route('/api/mentor/add_log', methods=['POST'])
# def add_mentor_log():
#     try:
#         data = request.json
        
#         # Determine the student's batch ID for the log record
#         student = StudentProfile.query.get(data.get('student_id'))
#         batch_id = student.mentor_batch_id if student else None

#         new_log = MentorLog(
#             student_id=data.get('student_id'),
#             mentor_id=data.get('mentor_id'),
#             mentor_batch_id=batch_id,
#             issue_category=data.get('category'),
#             remarks=data.get('remarks'),
#             action_taken=data.get('action_taken')
#         )
#         db.session.add(new_log)
#         db.session.commit()
        
#         log_activity("Mentoring", f"Logged session for student ID {new_log.student_id}")
#         return jsonify({"message": "Log recorded successfully"}), 200
#     except Exception as e: return jsonify({"error": str(e)}), 500


# In app.py

# @app.route('/api/mentor/update_log_status', methods=['POST'])
# def update_mentor_log_status():
#     try:
#         data = request.json
#         log_id = data.get('log_id')
#         new_status = data.get('status') # 'Resolved' or 'Escalated'
        
#         log = db.session.get(MentorLog, log_id)
#         if not log: return jsonify({"error": "Log entry not found"}), 404
        
#         log.status = new_status
#         db.session.commit()
        
#         # Optional: Log this system activity
#         log_activity("Mentoring", f"Updated log {log_id} status to {new_status}")
        
#         return jsonify({"message": f"Status updated to {new_status}"}), 200
#     except Exception as e: return jsonify({"error": str(e)}), 500


# 1. UPDATE UPLOAD LOGIC (Save specific type)
@app.route('/api/upload/subject_allocation', methods=['POST'])
@login_required
@require_roles('Admin')
def upload_subject_allocation():
    try:
        dept_ids = _get_admin_scope_dept_ids()
        try:
            file = get_db_file_handle(request)
        except Exception as e:
            msg = str(e)
            if 'No file part' in msg or 'No selected file' in msg:
                return jsonify({"error": msg}), 400
            raise
        df = pd.read_csv(file, dtype=str).fillna('')

        # Enforce structure-first workflow: allocation upload must reference an existing
        # SemesterCourseStructure row per (section, semester, subject).
        # Accept either 'SEM' or 'Sem' as the column name.
        if 'SEM' not in df.columns and 'Sem' in df.columns:
            df = df.rename(columns={'Sem': 'SEM'})

        required_cols = ['Course Code', 'Section', 'Class Level', 'SEM']
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return jsonify({
                "error": f"Missing columns: {', '.join(missing)}. Upload refused: run Semester Course Structure upload first and use the Subject Allocation template.",
                "errors": ["Download the CSV template from Bulk Uploads → Faculty Subject Allocation."]
            }), 400
        
        success_count = 0
        unassigned_count = 0
        skipped_list = []

        def resolve_section_for_row(row):
            """Resolve the target ClassSection.

            Convention:
              - CSV 'Section' is the specialization code / class section name (e.g., DA, CORE)
              - Mentor batches (DA1/DA2) are NOT uploaded here.
            """
            class_level = str(row.get('Class Level', '')).strip()
            section_code = str(row.get('Section', '')).strip()

            section = _resolve_class_section_for_csv(class_level, section_code)
            if not section:
                return None

            # Backfill spec_id using specialization code if missing.
            if getattr(section, 'spec_id', None) in (None, 0):
                spec_q = Specialization.query.filter_by(code=str(section.name).strip())
                if dept_ids is not None and dept_ids:
                    spec_q = spec_q.filter(Specialization.dept_id.in_(dept_ids))
                spec = spec_q.first()
                if spec:
                    section.spec_id = spec.id

            # Enforce department scoping for Dept Admins
            if dept_ids is not None:
                if not dept_ids:
                    return None
                if getattr(section, 'spec_id', None):
                    sp = db.session.get(Specialization, section.spec_id)
                    if not sp or getattr(sp, 'dept_id', None) not in dept_ids:
                        return None

            return section

        # --- PRE-VALIDATION (fail fast; no partial updates) ---
        # Validate that every row references an existing structure entry.
        pre_errors = []
        for index, row in df.iterrows():
            course_code = str(row.get('Course Code', '')).strip()
            section_name = str(row.get('Section', '')).strip()
            class_level = str(row.get('Class Level', '')).strip()
            sem_raw = str(row.get('SEM', '')).strip()

            if not course_code or not section_name or not class_level or not sem_raw:
                pre_errors.append(f"Row {index+2}: Missing Course Code / Section / Class Level / SEM")
                continue

            semester_no = parse_semester_no(sem_raw)
            if not semester_no or semester_no < 1 or semester_no > 8:
                pre_errors.append(f"Row {index+2}: Invalid SEM '{sem_raw}'")
                continue

            section = resolve_section_for_row(row)
            if not section:
                pre_errors.append(f"Row {index+2}: Class section '{class_level}-{section_name}' not found")
                continue

            subject = Subject.query.filter_by(code=course_code).first()
            if not subject:
                pre_errors.append(f"Row {index+2}: Subject '{course_code}' not found. Upload Semester Course Structure first.")
                continue

            struct = (SemesterCourseStructure.query
                      .filter_by(section_id=section.section_id, semester_no=semester_no, subject_id=subject.subject_id)
                      .first())
            if not struct:
                pre_errors.append(
                    f"Row {index+2}: No SemesterCourseStructure for '{class_level}-{section_name}', Sem {semester_no}, Course '{course_code}'. Upload structure first."
                )

        if pre_errors:
            db.session.rollback()
            return jsonify({
                "error": "Upload refused: Semester Course Structure not found for one or more rows.",
                "errors": pre_errors
            }), 400
        
        # --- 1. ENSURE SYSTEM PLACEHOLDER EXISTS (ROBUST) ---
        # Goal: Get a valid staff_id for "Unassigned Faculty"
        
        # A. Check if the Login User exists first
        system_email = "unassigned@system"
        system_user = UserMaster.query.filter_by(username=system_email).first()
        
        if not system_user:
            # Create User if missing
            system_user = UserMaster(
                user_id=str(uuid.uuid4()), 
                username=system_email, 
                password_hash="x", 
                user_type='Staff', 
                is_active=False
            )
            db.session.add(system_user)
            db.session.flush() # CRITICAL: Commit ID to DB immediately
        
        # B. Check if the Profile exists
        unassigned_staff = StaffProfile.query.filter_by(staff_id=system_user.user_id).first()
        
        if not unassigned_staff:
            # Create Profile linked to the User we just confirmed exists
            unassigned_staff = StaffProfile(
                staff_id=system_user.user_id, 
                full_name="Unassigned Faculty", 
                employee_code="NA", 
                email_contact=system_email, 
                designation="System"
            )
            db.session.add(unassigned_staff)
            db.session.flush() # CRITICAL: Commit Profile immediately
        # ----------------------------------------------------

        for index, row in df.iterrows():
            # Parse Basic Info
            course_code = row.get('Course Code', '').strip()
            class_level = row.get('Class Level', '').strip()
            sem_raw = str(row.get('SEM', '')).strip()

            semester_no = parse_semester_no(sem_raw)
            
            # 2. Resolve Subject (allocation must not create/overwrite structure)
            subject = Subject.query.filter_by(code=course_code).first()
            if not subject:
                skipped_list.append(f"Row {index+2}: Subject '{course_code}' not found. Upload Semester Course Structure first.")
                continue

            # 3. Resolve Class Section
            section = resolve_section_for_row(row)
            if not section:
                skipped_list.append(f"Row {index+2}: Class '{class_level}-{row.get('Section','').strip()}' not found.")
                continue

            # 3b. Enforce structure existence per (section, sem, subject)
            struct = (SemesterCourseStructure.query
                      .filter_by(section_id=section.section_id, semester_no=semester_no, subject_id=subject.subject_id)
                      .first())
            if not struct:
                skipped_list.append(
                    f"Row {index+2}: No SemesterCourseStructure for '{class_level}-{row.get('Section','').strip()}', Sem {semester_no}, Course '{course_code}'."
                )
                continue

            # 4. Resolve Faculty (with Fallback)
            teacher = None
            emp_code = row.get('Employee Code', '').strip()
            faculty_name = row.get('Faculty Name', '').strip()
            
            # Try finding real teacher
            if emp_code: 
                teacher = StaffProfile.query.filter_by(employee_code=emp_code).first()
            if not teacher and faculty_name:
                teacher = StaffProfile.query.filter(StaffProfile.full_name.ilike(f"%{faculty_name}%")).first()

            # Fallback to Unassigned
            if not teacher:
                teacher = unassigned_staff
                unassigned_count += 1

            # 5. Create Allocation
            existing_alloc = SubjectAllocation.query.filter_by(section_id=section.section_id, subject_id=subject.subject_id).first()
            if existing_alloc:
                existing_alloc.teacher_id = teacher.staff_id
            else:
                db.session.add(SubjectAllocation(section_id=section.section_id, subject_id=subject.subject_id, teacher_id=teacher.staff_id))
            
            success_count += 1

        db.session.commit()
        
        msg = f"Processed {success_count} subjects."
        if unassigned_count > 0:
            msg += f" ({unassigned_count} marked as Unassigned)."
            
        return jsonify({
            "message": msg, 
            "errors": skipped_list 
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# 2. UPDATE OPTIONS API (Group by Type)
@app.route('/api/student/get_elective_options', methods=['GET'])
def get_student_elective_options():
    try:
        user_id = request.args.get('user_id')
        student = StudentProfile.query.get(user_id)
        if not student.current_section_id: return jsonify({"groups": {}})
        
        # Filter Approved Types
        approved = [r[0] for r in db.session.query(Subject.subject_type).join(StudentElective).filter(StudentElective.student_id==user_id, StudentElective.status=='Approved').all()]

        offerings = (db.session.query(ElectiveOffering, Subject)
                     .join(Subject, ElectiveOffering.subject_id == Subject.subject_id)
                     .filter(ElectiveOffering.section_id == student.current_section_id, ElectiveOffering.status == 'Open')
                     .all())
        grouped_options = {}
        for off, s in offerings:
            if s.subject_type in approved: continue # Hide if already approved
            if s.subject_type not in grouped_options: grouped_options[s.subject_type] = []
            grouped_options[s.subject_type].append({ "id": s.subject_id, "name": s.name, "code": s.code, "window_id": off.window_id })
            
        current_choices = (db.session.query(StudentElective, Subject)
                           .join(Subject)
                           .filter(StudentElective.student_id == user_id)
                           .all())

        # Legacy selection map (by bucket/type)
        selections = {s.subject_type: s.subject_id for se, s in current_choices if not se.window_id}

        # Window-aware view (recommended)
        windows = (ElectiveWindow.query
                   .filter_by(section_id=student.current_section_id)
                   .filter(ElectiveWindow.status.in_(['Open', 'Extension']))
                   .order_by(ElectiveWindow.target_semester_no, ElectiveWindow.bucket)
                   .all())

        windows_out = []
        for w in windows:
            opts = (db.session.query(ElectiveOffering, Subject)
                    .join(Subject, Subject.subject_id == ElectiveOffering.subject_id)
                    .filter(ElectiveOffering.window_id == w.id)
                    .filter(ElectiveOffering.status == 'Open')
                    .order_by(Subject.name)
                    .all())
            sel = StudentElective.query.filter_by(student_id=user_id, window_id=w.id).first()
            windows_out.append({
                "window_id": w.id,
                "target_semester_no": w.target_semester_no,
                "bucket": w.bucket,
                "status": w.status,
                "selection": sel.subject_id if sel else None,
                "options": [{"id": s.subject_id, "name": s.name, "code": s.code} for _, s in opts]
            })

        return jsonify({"groups": grouped_options, "selections": selections, "windows": windows_out})
    except Exception as e: return jsonify({"error": str(e)}), 500

# 3. UPDATE SUBMIT API (Smart Replace)
# In app.py

@app.route('/api/student/submit_elective', methods=['POST'])
def submit_elective():
    try:
        data = request.json
        student_id = data.get('user_id')
        subject_id = data.get('subject_id')
        window_id = data.get('window_id')

        student = StudentProfile.query.get(student_id)
        if not student or not student.current_section_id:
            return jsonify({"error": "Student profile not found or class not assigned"}), 400

        # --- NEW: Window-based submission (semester + bucket scoped) ---
        if window_id:
            window = ElectiveWindow.query.get(int(window_id))
            if not window:
                return jsonify({"error": "Elective window not found"}), 404
            if window.section_id != student.current_section_id:
                return jsonify({"error": "This elective window is not for your class"}), 403

            if window.status not in ['Open', 'Extension']:
                return jsonify({"error": "Selection window is closed"}), 403
        
        # 1. Validate Subject
        new_subject = Subject.query.get(subject_id)
        if not new_subject: return jsonify({"error": "Subject not found"}), 404
        if not is_elective_type(new_subject.subject_type):
            return jsonify({"error": "Invalid subject type (not an elective)"}), 400

        if window_id:
            # Must match bucket
            if new_subject.subject_type != window.bucket:
                return jsonify({"error": f"Invalid bucket. Expected {window.bucket}"}), 400

            # Must be offered in this window
            offering = (ElectiveOffering.query
                        .filter_by(window_id=window.id, section_id=student.current_section_id, subject_id=subject_id)
                        .filter(ElectiveOffering.status == 'Open')
                        .first())
            if not offering:
                return jsonify({"error": "This elective is not offered in this window"}), 403

            existing = StudentElective.query.filter_by(student_id=student.student_id, window_id=window.id).first()

            if window.status == 'Extension':
                # Allow edit only if student is affected (no choice OR current choice is underfilled)
                min_batch = int(window.min_batch_size or 12)
                if existing:
                    current_count = (StudentElective.query
                                     .filter_by(window_id=window.id, subject_id=existing.subject_id)
                                     .join(StudentProfile, StudentProfile.student_id == StudentElective.student_id)
                                     .filter(StudentProfile.current_section_id == student.current_section_id)
                                     .count())
                    if current_count >= min_batch:
                        return jsonify({"error": "You are not eligible for extension changes"}), 403

            # Save/replace (editable while open/extension)
            if existing:
                existing.subject_id = subject_id
                existing.status = 'Pending'
            else:
                db.session.add(StudentElective(student_id=student_id, subject_id=subject_id, window_id=window.id, status='Pending'))
            db.session.commit()
            return jsonify({"message": "Saved", "window_id": window.id}), 200

        # 1b. Validate: Subject must be actively offered to the student's CURRENT class
        offering = (ElectiveOffering.query
                    .filter_by(section_id=student.current_section_id, subject_id=subject_id)
                    .filter(ElectiveOffering.status == 'Open')
                    .first())
        if not offering:
            return jsonify({"error": "This elective is not offered to your class"}), 403

        target_type = new_subject.subject_type
        
        # 2. Check for Existing Selection (LOCKING MECHANISM)
        existing = (db.session.query(StudentElective)
                    .join(Subject)
                    .filter(StudentElective.student_id == student_id)
                    .filter(Subject.subject_type == target_type)
                    .first())
        
        if existing:
            # Strict Lock: Do not allow changes once submitted
            return jsonify({"error": f"Selection for {target_type} is locked. Contact Class Teacher to change."}), 403
        
        # 3. Save New Choice
        db.session.add(StudentElective(student_id=student_id, subject_id=subject_id))
        db.session.commit()
        
        return jsonify({"message": "Saved"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500



@app.route('/api/marks/get_ca_sheet', methods=['GET'])
def get_ca_sheet():
    try:
        section_id = request.args.get('section_id')
        subject_id = request.args.get('subject_id')
        
        # 1. Fetch Basic Objects
        subject = db.session.get(Subject, subject_id)
        section = db.session.get(ClassSection, section_id)
        
        # 2. Fetch Allocation for Teacher Name
        allocation = SubjectAllocation.query.filter_by(section_id=section_id, subject_id=subject_id).first()
        teacher_name = "Unassigned"
        if allocation and allocation.teacher_id:
            t = db.session.get(StaffProfile, allocation.teacher_id)
            if t: teacher_name = t.full_name
            
        # 3. Fetch Dept
        dept_name = "Unknown Department"
        if subject.dept_id:
            d = db.session.get(Department, subject.dept_id)
            if d: dept_name = d.name

        # 4. Students Query (Elective Aware)
        students_query = StudentProfile.query.filter_by(current_section_id=section_id)
        if is_elective_type(subject.subject_type):
            students_query = (students_query.join(StudentElective)
                              .filter(StudentElective.subject_id == subject_id)
                              .filter(StudentElective.status == 'Approved'))
        students = students_query.order_by(StudentProfile.admission_number).all()

        # 5. Fetch Marks
        # Fetch Existing Marks
        existing = CAMarks.query.filter_by(section_id=section_id, subject_id=subject_id).all()
        marks_map = {m.student_id: m for m in existing}
        
        pub_status = {
            'ta1': any(m.is_published_ta1 for m in existing),
            'ta2': any(m.is_published_ta2 for m in existing),
            'ta3': any(m.is_published_ta3 for m in existing)
        }

        sheet = []
        for s in students:
            m = marks_map.get(s.student_id)
            sheet.append({
                "student_id": s.student_id,
                "roll": s.admission_number,
                "name": s.full_name,
                "ta1": m.ta1 if m else "", "ta2": m.ta2 if m else "", "ta3": m.ta3 if m else "",
                "a1": m.a1 if m else "", "a2": m.a2 if m else "", "a3": m.a3 if m else "", "a4": m.a4 if m else "", "a5": m.a5 if m else "",
                "status": m.learner_status if m else "-",
                # --- NEW: SEND SAVED ATTENDANCE SCORE ---
                "att_score": m.attendance_score if m else 0
            })
        
        # 6. Metadata Payload
        today = date.today()
        year_str = f"{today.year}-{today.year+1}" if today.month > 6 else f"{today.year-1}-{today.year}"
        current_term = get_current_term_name() # <--- NEW
        meta = {
            "department": dept_name,
            "school": "MIT Art, Design and Technology University",
            "class_name": f"{section.class_level} - {section.name}",
            "subject_name": subject.name,
            "subject_code": subject.code,
            "teacher": teacher_name,
            "academic_year": current_term.split(' Sem')[0],
            "semester": current_term.split(' ')[-2] + " " + current_term.split(' ')[-1] # Extracts "Sem 1"
        }

        return jsonify({"subject": subject.name, "meta": meta, "publish_status": pub_status, "students": sheet})
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/marks/submit_ca', methods=['POST'])
def submit_ca_marks():
    try:
        data = request.json
        subject_id = data.get('subject_id')
        section_id = data.get('section_id')
        marks_list = data.get('marks')
        term = data.get('term') 
        publish = data.get('publish', False)
        
        # Fetch Subject for Notification
        subject = db.session.get(Subject, subject_id)
        if not subject: return jsonify({"error": "Subject not found"}), 404

        # --- 1. PRE-FETCH ATTENDANCE DATA (Optimization) ---
        # Get all conducted sessions for this Subject + Class
        sessions = (db.session.query(SessionLog.session_id, WeeklySchedule.target_batch)
                    .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                    .filter(WeeklySchedule.subject_id == subject_id)
                    .filter(WeeklySchedule.section_id == section_id)
                    .filter(SessionLog.status == 'Conducted')
                    .all())
        
        # Get all attendance records for these sessions
        sess_ids = [s.session_id for s in sessions]
        att_map = {}
        if sess_ids:
            transactions = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(sess_ids)).all()
            # Map: (student_id, session_id) -> status
            att_map = {(t.student_id, t.session_id): t.status for t in transactions}
        # ---------------------------------------------------

        for row in marks_list:
            student_id = row['student_id']
            record = CAMarks.query.filter_by(student_id=student_id, subject_id=subject_id).first()
            
            # Create if new
            if not record: 
                record = CAMarks(
                    student_id=student_id, subject_id=subject_id, section_id=section_id,
                    ta1=0, ta2=0, ta3=0, a1=0, a2=0, a3=0, a4=0, a5=0
                )
                db.session.add(record)
            
            # Helper to parse input
            def get_val(key): return float(row.get(key) or 0)

            # Update specific term data
            if term == 'ta1':
                record.ta1 = get_val('ta1'); record.a1 = get_val('a1'); record.a2 = get_val('a2')
                if publish: record.is_published_ta1 = True
            elif term == 'ta2':
                record.ta2 = get_val('ta2'); record.a3 = get_val('a3'); record.a4 = get_val('a4')
                if publish: record.is_published_ta2 = True
            elif term == 'ta3':
                record.ta3 = get_val('ta3'); record.a5 = get_val('a5')
                if publish: record.is_published_ta3 = True

            # --- 2. CALCULATE REAL ATTENDANCE SCORE ---
            # Get Student Object to find Batch
            student = db.session.get(StudentProfile, student_id)
            student_batch = None
            if student and student.mentor_batch_id:
                mb = db.session.get(MentorBatch, student.mentor_batch_id)
                if mb: student_batch = mb.batch_name

            valid_sessions = 0
            attended_count = 0
            
            for sess_id, target_batch in sessions:
                # Logic: If lecture (no batch) OR batch matches student
                if not target_batch or target_batch == student_batch:
                    valid_sessions += 1
                    status = att_map.get((student_id, sess_id))
                    if status in PRESENT_STATUSES:
                        attended_count += 1
            
            # Scale to 5 Marks
            # Example: 80% Attendance = (80/100)*5 = 4 Marks
            att_perc = (attended_count / valid_sessions) if valid_sessions > 0 else 0
            real_att_score = round(att_perc * 5, 1)
            
            record.attendance_score = real_att_score
            # ------------------------------------------

            # --- 3. RECALCULATE TOTALS ---
            def safe_get(val): return float(val) if val is not None else 0.0

            val_ta1 = safe_get(record.ta1)
            val_ta2 = safe_get(record.ta2)
            val_ta3 = safe_get(record.ta3)
            
            # Learner Status
            avg_ta = (val_ta1 + val_ta2) / 2
            if avg_ta < 8: record.learner_status = 'Slow Learner'
            elif avg_ta >= 16: record.learner_status = 'Advanced Learner'
            else: record.learner_status = 'Average'
            
            # Final Score
            sum_assign = (safe_get(record.a1) + safe_get(record.a2) + 
                          safe_get(record.a3) + safe_get(record.a4) + 
                          safe_get(record.a5))
            avg_assign = sum_assign / 5
            
            s_ta1 = val_ta1 * 0.5
            s_ta2 = val_ta2 * 0.5
            s_assign = avg_assign * 1.5
            
            # Total = TA1(10) + TA2(10) + TA3(10) + Assign(15) + Att(5) = 50
            record.total_ca = min(50, s_ta1 + s_ta2 + val_ta3 + s_assign + real_att_score)

            # Notification
            if publish:
                send_notification(
                    student_id, 
                    f"Results: {subject.name}", 
                    f"{term.upper()} marks published. Current Attendance Score: {real_att_score}/5", 
                    "success", 
                    "/student/dashboard"
                )

        db.session.commit()
        
        msg = f"{term.upper()} Marks Published!" if publish else f"{term.upper()} Marks Saved."
        return jsonify({"message": msg}), 200
        
    except Exception as e: 
        print(f"Marks Error: {e}")
        return jsonify({"error": str(e)}), 500
    
    
@app.route('/api/marks/upload_csv', methods=['POST'])
def upload_marks_csv():
    try:
        file = get_db_file_handle(request)
        section_id = request.form.get('section_id')
        term = request.form.get('term') # 'ta1', 'ta2', 'ta3'
        
        df = pd.read_csv(file, dtype=str).fillna('')
        
        # Validation Config per Term
        TERM_CONFIG = {
            'ta1': {'TA1': 20, 'A1': 10, 'A2': 10},
            'ta2': {'TA2': 20, 'A3': 10, 'A4': 10},
            'ta3': {'TA3': 10, 'A5': 10}
        }
        
        config = TERM_CONFIG.get(term)
        if not config: return jsonify({"error": "Invalid Term Context"}), 400

        parsed_marks = []
        errors = []
        
        for index, row in df.iterrows():
            roll = str(row.get('Roll No', '')).strip()
            student = StudentProfile.query.filter_by(admission_number=roll, current_section_id=section_id).first()
            
            if not student:
                errors.append(f"Row {index+2}: Student '{roll}' not found in this class.")
                continue

            entry = {"student_id": student.student_id}
            
            # Map columns and Validate
            for col, max_val in config.items():
                val_str = row.get(col, '0').strip()
                try:
                    val = float(val_str) if val_str else 0
                    if val > max_val:
                        errors.append(f"Row {index+2}: {col} ({val}) exceeds Max ({max_val}).")
                        val = 0
                    entry[col.lower()] = val
                except ValueError:
                    entry[col.lower()] = 0
            
            parsed_marks.append(entry)
        
        if errors:
            return jsonify({"error": "Validation Failed", "details": errors}), 400
            
        return jsonify({"message": "CSV Parsed Successfully", "data": parsed_marks}), 200

    except Exception as e: return jsonify({"error": str(e)}), 500


# In app.py - Add inside the MARKS & EXAM section

@app.route('/api/marks/download_template', methods=['GET'])
def download_marks_template():
    try:
        section_id = request.args.get('section_id')
        subject_id = request.args.get('subject_id')
        term = request.args.get('term')
        
        # 1. Validation
        if not (section_id and subject_id and term):
            return "Missing parameters", 400
            
        TERM_CONFIG = {
            'ta1': ['TA1', 'A1', 'A2'],
            'ta2': ['TA2', 'A3', 'A4'],
            'ta3': ['TA3', 'A5']
        }
        headers = ['Roll No', 'Name'] + TERM_CONFIG.get(term, [])
        
        # 2. Fetch Students (Elective Aware)
        subject = db.session.get(Subject, subject_id)
        section = db.session.get(ClassSection, section_id)
        
        students_query = StudentProfile.query.filter_by(current_section_id=section_id)
        
        if is_elective_type(subject.subject_type):
            students_query = (students_query.join(StudentElective)
                              .filter(StudentElective.subject_id == subject_id)
                              .filter(StudentElective.status == 'Approved'))
                              
        students = students_query.order_by(StudentProfile.admission_number).all()
        
        # 3. Generate CSV String
        import io
        import csv
        from flask import Response
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write Header
        writer.writerow(headers)
        
        # Write Student Rows (Pre-filled)
        for s in students:
            # Create a row with student info + empty slots for marks
            row_data = [s.admission_number, s.full_name] + [''] * len(TERM_CONFIG.get(term, []))
            writer.writerow(row_data)
            
        # 4. Return File
        output.seek(0)
        filename = f"{subject.code}_{term.upper()}_Template.csv"
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )

    except Exception as e: return str(e), 500


@app.route('/api/amc/ca_report', methods=['GET'])
def get_amc_ca_report():
    try:
        section_id = request.args.get('section_id')
        subject_id = request.args.get('subject_id')
        
        marks_data = (db.session.query(CAMarks, StudentProfile)
                      .join(StudentProfile)
                      .filter(CAMarks.section_id == section_id, CAMarks.subject_id == subject_id)
                      .order_by(StudentProfile.admission_number)
                      .all())
        
        report_rows = []
        # Distribution Buckets
        dist = {"0-9": 0, "10-19": 0, "20-30": 0, "31-40": 0, "41-50": 0}
        
        for m, s in marks_data:
            # --- SCALING LOGIC (The "Not Straight Forward" Part) ---
            # Example Config:
            # TA1 (20) -> Scaled to 10
            # TA2 (20) -> Scaled to 10
            # TA3 (10) -> Scaled to 10
            # Assignments (Avg of 5) -> Scaled to 15
            # Attendance -> 5
            # Total = 10 + 10 + 10 + 15 + 5 = 50
            
            s_ta1 = (m.ta1 / 20) * 10
            s_ta2 = (m.ta2 / 20) * 10
            s_ta3 = m.ta3 # Already 10? Or scaled? Let's assume TA3 is 10.
            
            avg_assign = (m.a1 + m.a2 + m.a3 + m.a4 + m.a5) / 5
            s_assign = (avg_assign / 10) * 15 # Assuming assignment out of 10, scaled to 15
            
            s_att = m.attendance_score
            
            final_total = s_ta1 + s_ta2 + s_ta3 + s_assign + s_att
            final_total = min(50, round(final_total)) # Cap at 50

            # Bucketing
            if final_total <= 9: dist["0-9"] += 1
            elif final_total <= 19: dist["10-19"] += 1
            elif final_total <= 30: dist["20-30"] += 1
            elif final_total <= 40: dist["31-40"] += 1
            else: dist["41-50"] += 1
            
            report_rows.append({
                "roll": s.admission_number,
                "name": s.full_name,
                "ta1": m.ta1, "ta2": m.ta2, "ta3": m.ta3,
                "assign_avg": round(avg_assign, 1),
                "att": m.attendance_score,
                # Scaled
                "s_ta1": round(s_ta1, 1), "s_ta2": round(s_ta2, 1), 
                "s_assign": round(s_assign, 1), "s_att": s_att,
                "total": final_total,
                "status": m.learner_status
            })
            
        return jsonify({
            "rows": report_rows,
            "distribution": dist,
            "total_students": len(report_rows)
        })
    except Exception as e: return jsonify({"error": str(e)}), 500


# ==========================================
# API: SYLLABUS REPORT (AMC)
# ==========================================
@app.route('/api/amc/syllabus_report', methods=['GET'])
def get_amc_syllabus_report():
    try:
        section_id = request.args.get('section_id')
        term = request.args.get('term') # 'ta1', 'ta2', 'ta3'
        
        if not section_id or not term:
            return jsonify({"error": "Missing parameters"}), 400

        # 1. Define Target Units
        target_units = []
        if term == 'ta1': target_units = [1, 2]
        elif term == 'ta2': target_units = [3, 4]
        elif term == 'ta3': target_units = [5, 6] # Assuming max 6 units

        # 2. Get Subjects & Teachers
        allocations = (db.session.query(SubjectAllocation, Subject, StaffProfile)
                       .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                       .join(StaffProfile, SubjectAllocation.teacher_id == StaffProfile.staff_id)
                       .filter(SubjectAllocation.section_id == section_id)
                       .all())
        
        report_data = []

        for alloc, subject, teacher in allocations:
            # A. Get Planned Data for Target Units
            plans = TeachingPlan.query.filter_by(subject_id=subject.subject_id).filter(TeachingPlan.unit_number.in_(target_units)).all()
            
            planned_hours = sum(p.planned_hours for p in plans)
            target_units_count = len(set(p.unit_number for p in plans)) # How many units actually exist in plan
            
            # B. Get Conducted Data
            # Find lesson logs where the plan belongs to target units
            conducted_logs = (db.session.query(LessonLog)
                              .join(TeachingPlan)
                              .join(SessionLog)
                              .join(WeeklySchedule)
                              .filter(WeeklySchedule.section_id == section_id)
                              .filter(TeachingPlan.subject_id == subject.subject_id)
                              .filter(TeachingPlan.unit_number.in_(target_units))
                              .all())
            
            conducted_hours = len(conducted_logs) # Assuming 1 log = 1 hour (approx)
            
            # C. Calculate Units Fully Covered
            # A unit is "Covered" if conducted >= planned for that unit
            units_covered_count = 0
            for u in target_units:
                u_planned = sum(p.planned_hours for p in plans if p.unit_number == u)
                u_conducted = (db.session.query(LessonLog)
                               .join(TeachingPlan)
                               .join(SessionLog)
                               .join(WeeklySchedule)
                               .filter(WeeklySchedule.section_id == section_id)
                               .filter(TeachingPlan.subject_id == subject.subject_id)
                               .filter(TeachingPlan.unit_number == u)
                               .count())
                if u_planned > 0 and u_conducted >= u_planned:
                    units_covered_count += 1

            # D. Stats
            percent = round((conducted_hours / planned_hours) * 100) if planned_hours > 0 else 0
            gap = max(0, planned_hours - conducted_hours)
            
            # Remark Logic
            remark = "On Track"
            if percent < 80: remark = "Lagging Behind"
            if percent < 50: remark = "Critical Lag"
            if percent >= 100: remark = "Completed"

            report_data.append({
                "teacher": teacher.full_name,
                "subject": subject.name,
                "code": subject.code,
                "planned": planned_hours,
                "conducted": conducted_hours,
                "units_covered": f"{units_covered_count}/{target_units_count}",
                "percentage": f"{percent}%",
                "required_hours": gap,
                "remark": remark
            })

        return jsonify({
            "term": term.upper(),
            "data": report_data
        })

    except Exception as e: return jsonify({"error": str(e)}), 500


# In app.py

# ==========================================
# API: TERM GRANT (AMC)
# ==========================================

@app.route('/api/amc/generate_term_grant', methods=['POST'])
def generate_term_grant():
    try:
        data = request.json
        section_id = data.get('section_id')
        threshold_att = float(data.get('att_threshold', 75))
        threshold_marks = float(data.get('marks_threshold', 20)) # Out of 50
        
        # 1. Clear old records for this class (Re-calculation)
        TermGrantRecord.query.filter_by(section_id=section_id).delete()
        
        # 2. Fetch all students
        students = StudentProfile.query.filter_by(current_section_id=section_id).all()
        
        # 3. Fetch all subjects for this class (for Marks check)
        allocations = SubjectAllocation.query.filter_by(section_id=section_id).all()
        subject_ids = [a.subject_id for a in allocations]
        
        # 4. Fetch Global Attendance (Simplified for performance)
        total_sessions = db.session.query(SessionLog).join(WeeklySchedule).filter(WeeklySchedule.section_id == section_id, SessionLog.status=='Conducted').count()
        
        count = 0
        for s in students:
            # A. Attendance %
            attended = AttendanceTransaction.query.join(SessionLog).join(WeeklySchedule).filter(
                WeeklySchedule.section_id == section_id,
                AttendanceTransaction.student_id == s.student_id,
                AttendanceTransaction.status.in_(['Present', 'OnDuty'])
            ).count()
            
            att_perc = round((attended / total_sessions) * 100, 1) if total_sessions > 0 else 0
            
            # B. CA Marks
            ca_records = CAMarks.query.filter(CAMarks.student_id == s.student_id, CAMarks.subject_id.in_(subject_ids)).all()
            total_score = sum(m.total_ca for m in ca_records)
            subject_count = len(ca_records)
            avg_ca = round(total_score / subject_count, 1) if subject_count > 0 else 0
            
            # Count Failed Subjects (Below Threshold)
            failed_count = sum(1 for m in ca_records if m.total_ca < threshold_marks)
            
            # C. Detention
            det_count = DetentionRecord.query.filter_by(student_id=s.student_id).filter(DetentionRecord.status.in_(['Assigned', 'In_Review'])).count()
            
            # D. DECISION LOGIC
            status = 'Granted'
            reasons = []
            
            if att_perc < threshold_att:
                status = 'Provisional' if att_perc > (threshold_att - 15) else 'Detained'
                reasons.append(f"Low Attendance ({att_perc}%)")
                
            if failed_count > 0:
                if status == 'Granted': status = 'Provisional'
                reasons.append(f"Failed {failed_count} Subjects")
                
            if det_count > 0:
                status = 'Detained' # Strict Rule
                reasons.append(f"Active Detention ({det_count})")
            
            # Create Record
            rec = TermGrantRecord(
                student_id=s.student_id,
                section_id=section_id,
                attendance_perc=att_perc,
                avg_ca_score=avg_ca,
                failed_subjects_count=failed_count,
                active_detentions=det_count,
                status=status,
                remarks=", ".join(reasons) if reasons else "All Clear",
                is_published=False
            )
            db.session.add(rec)
            count += 1
            
        db.session.commit()
        return jsonify({"message": f"Generated Term Grant for {count} students."}), 200

    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/amc/term_grant_list', methods=['GET'])
def get_term_grant_list():
    try:
        section_id = request.args.get('section_id')
        records = (db.session.query(TermGrantRecord, StudentProfile)
                   .join(StudentProfile)
                   .filter(TermGrantRecord.section_id == section_id)
                   .order_by(StudentProfile.admission_number)
                   .all())
        
        data = []
        stats = {"Granted": 0, "Provisional": 0, "Detained": 0}
        
        for r, s in records:
            stats[r.status] = stats.get(r.status, 0) + 1
            data.append({
                "id": r.record_id,
                "roll": s.admission_number,
                "name": s.full_name,
                "att": r.attendance_perc,
                "ca_avg": r.avg_ca_score,
                "fails": r.failed_subjects_count,
                "det": r.active_detentions,
                "status": r.status,
                "remarks": r.remarks,
                "published": r.is_published
            })
            
        return jsonify({"students": data, "stats": stats})
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/amc/update_grant_status', methods=['POST'])
def update_grant_status():
    try:
        data = request.json
        rec = TermGrantRecord.query.get(data.get('record_id'))
        if not rec: return jsonify({"error": "Record not found"}), 404
        
        rec.status = data.get('status')
        rec.remarks = data.get('remarks', rec.remarks)
        db.session.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500


# ==========================================
# API: FEEDBACK SYSTEM
# ==========================================

@app.route('/api/feedback/active_cycle', methods=['GET'])
def get_active_feedback_cycle():
    try:
        today = date.today()
        cycle = FeedbackCycle.query.filter(
            FeedbackCycle.is_active == True,
            FeedbackCycle.start_date <= today,
            FeedbackCycle.end_date >= today
        ).order_by(FeedbackCycle.cycle_id.desc()).first()
        if not cycle:
            return jsonify({"active": False})
        
        return jsonify({
            "active": True,
            "id": cycle.cycle_id,
            "name": cycle.name,
            "end_date": cycle.end_date.strftime('%d %b %Y')
        })
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/feedback/questions', methods=['GET'])
def get_feedback_questions():
    try:
        qs = FeedbackQuestion.query.filter_by(is_active=True).all()
        return jsonify({"questions": [{"id": q.question_id, "text": q.text, "category": q.category} for q in qs]})
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/feedback/pending_list', methods=['GET'])
def get_student_pending_feedback():
    try:
        user_id = request.args.get('user_id')
        
        # 1. Check Active Cycle
        today = date.today()
        cycle = FeedbackCycle.query.filter(
            FeedbackCycle.is_active == True,
            FeedbackCycle.start_date <= today,
            FeedbackCycle.end_date >= today
        ).order_by(FeedbackCycle.cycle_id.desc()).first()
        if not cycle:
            return jsonify({"active": False, "subjects": []})

        # 2. Get Enrolled Subjects
        student = StudentProfile.query.get(user_id)
        if not student or not student.current_section_id: return jsonify({"active": False, "subjects": []})
        
        allocations = SubjectAllocation.query.filter_by(section_id=student.current_section_id).all()
        
        pending_list = []
        for alloc in allocations:
            subject = db.session.get(Subject, alloc.subject_id)
            
            # Elective Check
            if is_elective_type(subject.subject_type):
                approved = StudentElective.query.filter_by(student_id=user_id, subject_id=subject.subject_id, status='Approved').first()
                if not approved: continue

            # Check if already submitted
            done = StudentFeedbackStatus.query.filter_by(student_id=user_id, cycle_id=cycle.cycle_id, subject_id=subject.subject_id).first()
            if not done:
                teacher = db.session.get(StaffProfile, alloc.teacher_id)
                pending_list.append({
                    "subject_id": subject.subject_id,
                    "subject_name": subject.name,
                    "code": subject.code,
                    "teacher_name": teacher.full_name if teacher else "Unassigned",
                    "teacher_id": alloc.teacher_id
                })
        
        return jsonify({"active": True, "cycle_name": cycle.name, "subjects": pending_list})

    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/feedback/submit', methods=['POST'])
def submit_feedback():
    try:
        data = request.json
        student_id = data.get('student_id')
        cycle_id = data.get('cycle_id')
        subject_id = data.get('subject_id')
        section_id = data.get('section_id')
        teacher_id = data.get('teacher_id')
        responses = data.get('responses') # {question_id: rating}

        student = StudentProfile.query.get(student_id)
        if not student or not student.current_section_id:
             return jsonify({"error": "Student class not found"}), 400
        section_id = student.current_section_id
        
        # 1. Save Anonymous Responses
        for q_id, rating in responses.items():
            db.session.add(FeedbackResponse(
                cycle_id=cycle_id,
                subject_id=subject_id,
                teacher_id=teacher_id,
                section_id=section_id,
                question_id=int(q_id),
                rating=int(rating)
            ))
        
        # 2. Mark as Done for Student
        db.session.add(StudentFeedbackStatus(student_id=student_id, cycle_id=cycle_id, subject_id=subject_id))
        
        db.session.commit()
        return jsonify({"message": "Feedback Submitted"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/admin/create_feedback_cycle', methods=['POST'])
def create_feedback_cycle():
    try:
        data = request.json
        name = (data.get('name') or '').strip()
        start_raw = data.get('start_date')
        end_raw = data.get('end_date')
        is_active = bool(data.get('is_active', True))

        if not name or not start_raw or not end_raw:
            return jsonify({"error": "name, start_date, end_date are required"}), 400

        try:
            start_date = datetime.strptime(start_raw, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_raw, '%Y-%m-%d').date()
        except Exception:
            return jsonify({"error": "Invalid date format (expected YYYY-MM-DD)"}), 400

        if start_date > end_date:
            return jsonify({"error": "Start date must be before or equal to end date"}), 400

        if is_active:
            today = date.today()
            if not (start_date <= today <= end_date):
                return jsonify({"error": "To activate a cycle, today's date must fall between start and end dates."}), 400

        if is_active:
            FeedbackCycle.query.update({FeedbackCycle.is_active: False})
            
        new_cycle = FeedbackCycle(
            name=name,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active
        )
        db.session.add(new_cycle)
        
        # Seed default questions if none exist
        if FeedbackQuestion.query.count() == 0:
            defaults = [
                "The faculty covers the syllabus on time.",
                "The faculty explains concepts clearly.",
                "The faculty is punctual to class.",
                "The faculty encourages questions and interaction.",
                "Course materials/notes provided were helpful."
            ]
            for txt in defaults:
                db.session.add(FeedbackQuestion(text=txt, category="Teaching"))
        
        db.session.commit()
        return jsonify({"message": "Cycle Created"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/admin/feedback_status', methods=['GET'])
def get_admin_feedback_status():
    """Class/division-wise feedback submission counts for the currently active feedback cycle."""
    try:
        from sqlalchemy import and_, func

        today = date.today()
        cycle = FeedbackCycle.query.filter(
            FeedbackCycle.is_active == True,
            FeedbackCycle.start_date <= today,
            FeedbackCycle.end_date >= today
        ).order_by(FeedbackCycle.cycle_id.desc()).first()

        if not cycle:
            return jsonify({"active": False, "sections": []})

        q = (
            db.session.query(
                ClassSection.section_id,
                ClassSection.class_level,
                ClassSection.name,
                func.count(StudentProfile.student_id).label('total_students'),
                func.count(func.distinct(StudentFeedbackStatus.student_id)).label('submitted_students'),
            )
            .join(StudentProfile, StudentProfile.current_section_id == ClassSection.section_id)
            .outerjoin(
                StudentFeedbackStatus,
                and_(
                    StudentFeedbackStatus.student_id == StudentProfile.student_id,
                    StudentFeedbackStatus.cycle_id == cycle.cycle_id,
                ),
            )
            .filter(StudentProfile.academic_status == 'Active')
            .group_by(ClassSection.section_id)
            .order_by(ClassSection.class_level.asc(), ClassSection.name.asc())
        )

        rows = []
        for section_id, class_level, division_name, total_students, submitted_students in q.all():
            total_students = int(total_students or 0)
            submitted_students = int(submitted_students or 0)
            pct = round((submitted_students / total_students) * 100, 1) if total_students else 0
            rows.append({
                "section_id": section_id,
                "class": f"{class_level}-{division_name}",
                "submitted_students": submitted_students,
                "total_students": total_students,
                "percentage": pct,
            })

        return jsonify({
            "active": True,
            "cycle_id": cycle.cycle_id,
            "cycle_name": cycle.name,
            "start_date": cycle.start_date.strftime('%Y-%m-%d'),
            "end_date": cycle.end_date.strftime('%Y-%m-%d'),
            "sections": rows,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# API: SYSTEM CONFIG & ROLLOVER
# ==========================================

@app.route('/api/admin/system_config', methods=['GET', 'POST'])
def manage_system_config():
    def _impl():
        if request.method == 'POST':
            data = request.json or {}
            term = (data.get('current_term') or '').strip()
            if not term:
                return jsonify({"error": "current_term is required"}), 400

            conf = SystemConfig.query.get('current_term')
            if not conf:
                conf = SystemConfig(key='current_term', value=term)
                db.session.add(conf)
            else:
                conf.value = term

            db.session.commit()
            return jsonify({"message": "Term Updated"}), 200
        else:
            conf = SystemConfig.query.get('current_term')
            return jsonify({"current_term": conf.value if conf else get_current_term_name()})

    try:
        return _impl()
    except OperationalError as e:
        if 'no such table' in str(e).lower():
            db.create_all()
            return _impl()
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/admin/rollover_semester', methods=['POST'])
def rollover_semester():
    def _impl():
        conf = SystemConfig.query.get('current_term')
        old_term = conf.value if conf else get_current_term_name()

        # Archive Allocations
        allocs = (
            db.session.query(SubjectAllocation, Subject, StaffProfile)
            .join(Subject, Subject.subject_id == SubjectAllocation.subject_id)
            .join(StaffProfile, StaffProfile.staff_id == SubjectAllocation.teacher_id)
            .all()
        )

        for a, sub, staff in allocs:
            db.session.add(
                ArchivedAllocation(
                    term_name=old_term,
                    section_id=a.section_id,
                    subject_code=sub.code,
                    subject_name=sub.name,
                    teacher_name=staff.full_name,
                )
            )

        # Archive Schedule
        slots = (
            db.session.query(WeeklySchedule, ClassSection, Subject, StaffProfile)
            .join(ClassSection, ClassSection.section_id == WeeklySchedule.section_id)
            .join(Subject, Subject.subject_id == WeeklySchedule.subject_id)
            .join(StaffProfile, StaffProfile.staff_id == WeeklySchedule.teacher_id)
            .all()
        )

        for slot, sec, sub, staff in slots:
            time_str = f"{slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}"
            db.session.add(
                ArchivedSchedule(
                    term_name=old_term,
                    section_name=f"{sec.class_level}-{sec.name}",
                    day=slot.day_of_week,
                    time_slot=time_str,
                    subject=sub.name,
                    teacher=staff.full_name,
                )
            )

        # FLUSH Active Tables
        db.session.query(WeeklySchedule).delete()
        db.session.query(SubjectAllocation).delete()
        db.session.query(StudentElective).delete()
        db.session.query(ElectiveOffering).delete()

        db.session.commit()
        log_activity("System Rollover", f"Archived {old_term} and reset for new term.")

        return (
            jsonify(
                {
                    "message": f"Rollover Complete. System reset for new term. Old data archived under '{old_term}'."
                }
            ),
            200,
        )

    try:
        return _impl()
    except OperationalError as e:
        if 'no such table' in str(e).lower():
            db.create_all()
            return _impl()
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ==========================================
# API: HOD ANALYTICS
# ==========================================

@app.route('/api/hod/feedback_analysis', methods=['GET'])
def get_hod_feedback_analysis():
    try:
        user_id = request.args.get('user_id')
        
        # 1. Identify HOD's Department
        dept = Department.query.filter_by(hod_staff_id=user_id).first()
        # No fallback to hardcoded department - HOD must be assigned
            
        if not dept: return jsonify({"error": "Unauthorized / No Dept Found"}), 403

        # 2. Faculty Overall Scores (Group by Teacher)
        fac_results = (db.session.query(
                            StaffProfile.full_name, 
                            db.func.avg(FeedbackResponse.rating).label('avg_rating'),
                            db.func.count(FeedbackResponse.response_id).label('count')
                       )
                       .join(StaffProfile, FeedbackResponse.teacher_id == StaffProfile.staff_id)
                       .filter(StaffProfile.primary_department_id == dept.dept_id)
                       .group_by(StaffProfile.full_name)
                       .all())

        faculty_scores = []
        dept_sum = 0
        total_responses = 0

        for name, avg, count in fac_results:
            score = round(float(avg), 2)
            faculty_scores.append({
                "name": name,
                "score": score,
                "responses": count,
                "status": "Excellent" if score >= 4.5 else ("Good" if score >= 3.5 else "Needs Improvement")
            })
            dept_sum += (float(avg) * count)
            total_responses += count

        dept_avg = round(dept_sum / total_responses, 2) if total_responses > 0 else 0

        # 3. Subject-wise Analysis
        sub_results = (db.session.query(
                            ClassSection.class_level,
                            ClassSection.name,
                            Subject.name,
                            Subject.code,
                            StaffProfile.full_name, 
                            db.func.avg(FeedbackResponse.rating).label('avg_rating')
                       )
                       .join(StaffProfile, FeedbackResponse.teacher_id == StaffProfile.staff_id)
                       .join(Subject, FeedbackResponse.subject_id == Subject.subject_id)
                       .join(ClassSection, FeedbackResponse.section_id == ClassSection.section_id)
                       .filter(StaffProfile.primary_department_id == dept.dept_id)
                       .group_by(ClassSection.class_level, ClassSection.name, Subject.name, Subject.code, StaffProfile.full_name)
                       .order_by(ClassSection.class_level, ClassSection.name, Subject.name)
                       .all())

        subject_analysis = []
        for lvl, sec_name, s_name, s_code, t_name, avg in sub_results:
            subject_analysis.append({
                "class": f"{lvl}-{sec_name}",
                "subject": s_name,
                "code": s_code,
                "faculty": t_name,
                "score": round(float(avg), 2)
            })

        faculty_scores.sort(key=lambda x: x['score'], reverse=True)

        return jsonify({
            "dept_avg": dept_avg,
            "total_responses": total_responses,
            "faculty_scores": faculty_scores,
            "subject_analysis": subject_analysis
        })

    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/hod/syllabus_status', methods=['GET'])
def get_hod_syllabus_status():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID required"}), 400
        
        allocations = (db.session.query(SubjectAllocation, Subject, StaffProfile)
                       .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                       .join(StaffProfile, SubjectAllocation.teacher_id == StaffProfile.staff_id)
                       .filter(SubjectAllocation.section_id == section_id)
                       .all())
        
        data = []
        for alloc, sub, teacher in allocations:
            total_topics = TeachingPlan.query.filter_by(
                subject_id=sub.subject_id, 
                created_by_id=teacher.staff_id
            ).count()
            
            if total_topics == 0:
                perc = 0
                status_text = "Plan Not Uploaded"
                color = "gray"
            else:
                completed_count = (db.session.query(LessonLog.plan_id)
                                   .join(SessionLog, LessonLog.session_id == SessionLog.session_id)
                                   .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                                   .filter(WeeklySchedule.section_id == section_id)
                                   .filter(WeeklySchedule.subject_id == sub.subject_id)
                                   .filter(SessionLog.status == 'Conducted')
                                   .distinct()
                                   .count())
                                   
                perc = round((completed_count / total_topics) * 100)
                status_text = f"{completed_count}/{total_topics} Topics"
                
                if perc < 40: color = "red"
                elif perc < 70: color = "yellow"
                else: color = "green"

            data.append({
                "subject": sub.name,
                "code": sub.code,
                "teacher": teacher.full_name,
                "percentage": perc,
                "status": status_text,
                "color": color
            })
            
        return jsonify({"subjects": data})
        
    except Exception as e: return jsonify({"error": str(e)}), 500


# ==========================================
# API: ACADEMIC / LESSON PLANNING
# ==========================================

@app.route('/api/academic/create_plan', methods=['POST'])
def create_teaching_plan():
    try:
        data = request.json
        subject_id = data.get('subject_id')
        teacher_id = data.get('teacher_id')
        topics = data.get('topics') # List of {unit, topic, hours}
        
        count = 0
        for item in topics:
            plan = TeachingPlan(
                subject_id=subject_id,
                created_by_id=teacher_id,
                unit_number=int(item['unit']),
                topic_name=item['topic'],
                planned_hours=int(item['hours'])
            )
            db.session.add(plan)
            count += 1
            
        db.session.commit()
        return jsonify({"message": f"Added {count} topics to syllabus."}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/upload/syllabus', methods=['POST'])
def upload_syllabus_csv():
    try:
        file = get_db_file_handle(request)
        subject_id = request.form.get('subject_id')
        teacher_id = request.form.get('teacher_id')
        
        if not subject_id or not teacher_id:
            return jsonify({"error": "Context missing (Subject/Teacher)"}), 400

        try:
            df = pd.read_csv(file, dtype=str)
        except UnicodeDecodeError:
            file.seek(0)
            df = pd.read_csv(file, dtype=str, encoding='cp1252')
        except Exception:
            file.seek(0)
            df = pd.read_csv(file, dtype=str, encoding='latin1')
            
        df = df.fillna('')
        
        count = 0
        for index, row in df.iterrows():
            unit = row.get('Unit', '').strip()
            topic = row.get('Topic', '').strip()
            hours = row.get('Hours', '1').strip()
            sub_unit = row.get('Sub Unit', '').strip()
            
            if not unit or not topic: continue
            
            plan = TeachingPlan(
                subject_id=subject_id,
                created_by_id=teacher_id,
                unit_number=int(unit),
                sub_unit=sub_unit,
                topic_name=topic,
                planned_hours=int(hours) if hours.isdigit() else 1
            )
            db.session.add(plan)
            count += 1
            
        db.session.commit()
        return jsonify({"message": f"Successfully added {count} topics."}), 201

    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/academic/get_syllabus', methods=['GET'])
def get_syllabus():
    try:
        subject_id = request.args.get('subject_id')
        
        plans = TeachingPlan.query.filter_by(subject_id=subject_id).order_by(TeachingPlan.unit_number, TeachingPlan.sub_unit).all()
        
        syllabus = []
        total_topics = len(plans)
        completed_topics = 0
        
        unit_hours = {}
        for p in plans:
            u = p.unit_number
            unit_hours[u] = unit_hours.get(u, 0) + p.planned_hours

        for p in plans:
            log_entry = (db.session.query(LessonLog, SessionLog)
                         .join(SessionLog, LessonLog.session_id == SessionLog.session_id)
                         .filter(LessonLog.plan_id == p.plan_id)
                         .first())
            
            conducted_date = None
            status = "Pending"

            if log_entry: 
                lesson, session = log_entry
                status = 'Completed'
                conducted_date = session.session_date.strftime('%d %b %Y')
                completed_topics += 1
                
            syllabus.append({
                "id": p.plan_id,
                "unit": p.unit_number,
                "sub_unit": p.sub_unit,
                "topic": p.topic_name,
                "hours": p.planned_hours,
                "unit_total_hours": unit_hours.get(p.unit_number, 0),
                "status": status,
                "conducted_date": conducted_date
            })
            
        progress = round((completed_topics / total_topics) * 100) if total_topics > 0 else 0
        
        return jsonify({
            "syllabus": syllabus,
            "progress": progress
        })
    except Exception as e: return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # --- SEED DATA: CREATE SUPER ADMIN (No departments - must set up hierarchy first) ---
        admin_email = "admin@mituniversity.edu.in"
        if not UserMaster.query.filter_by(username=admin_email).first():
            print("Creating System Environment...")
            new_uuid = str(uuid.uuid4())
            
            # NOTE: No department created here - SuperAdmin must set up hierarchy via CSV upload
            
            admin_user = UserMaster(user_id=new_uuid, username=admin_email, password_hash=generate_password_hash("Admin@123"), user_type='SuperAdmin', is_active=True)
            db.session.add(admin_user)
            
            admin_profile = StaffProfile(staff_id=new_uuid, full_name="System Administrator", employee_code="ADMIN001", email_contact=admin_email)
            db.session.add(admin_profile)
            
            db.session.commit()
            print(f"Super Admin Created! Login: {admin_email} / Admin@123")
        else:
            print("Database initialized.")

    app.run(debug=True, port=5000)



import os
import uuid
from flask_sqlalchemy import SQLAlchemy

from sqlalchemy import MetaData
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import deferred

convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": 'uq_%(table_name)s_%(column_0_name)s',
    "ck": 'ck_%(table_name)s_%(constraint_name)s',
    "fk": 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    "pk": 'pk_%(table_name)s'
}

metadata = MetaData(naming_convention=convention)
db = SQLAlchemy(metadata=metadata)

def get_db_uri(app):
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        return db_url

    pg_user = os.environ.get('POSTGRES_USER', 'admin')
    pg_password = os.environ.get('POSTGRES_PASSWORD')
    pg_db = os.environ.get('POSTGRES_DB', 'school_system')
    pg_host = os.environ.get('POSTGRES_HOST', 'db')
    pg_port_raw = os.environ.get('POSTGRES_PORT', '5432')

    if pg_password is not None:
        try:
            pg_port = int(pg_port_raw)
        except Exception:
            pg_port = 5432

        url = URL.create(
            drivername='postgresql+psycopg2',
            username=pg_user,
            password=pg_password,
            host=pg_host,
            port=pg_port,
            database=pg_db,
        )
        return url.render_as_string(hide_password=False)

    # PostgreSQL is required - raise error if not configured
    raise RuntimeError(
        "PostgreSQL environment variables not configured. "
        "Please set POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB."
    )


# ==========================================
# 1. CORE IDENTITY & AUTH
# ==========================================
class UserMaster(db.Model):
    __tablename__ = 'user_master'
    user_id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    user_type = db.Column(db.String(20), nullable=False) # 'Staff', 'Student', 'Parent', 'Admin'
    two_factor_secret = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    # Security: Force password change on first login for bulk-uploaded accounts
    must_change_password = db.Column(db.Boolean, default=False)

    # First-login onboarding (SuperAdmin): redirect to hierarchy setup until completed.
    # Deferred so older DBs (without the column yet) won't crash on SELECT.
    onboarding_completed = deferred(db.Column(db.Boolean, default=False))

# ==========================================
# 2. PROFILES
# ==========================================


class StaffProfile(db.Model):
    __tablename__ = 'staff_profile'
    staff_id = db.Column(db.String(36), db.ForeignKey('user_master.user_id'), primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    employee_code = db.Column(db.String(50), unique=True, nullable=False)
    email_contact = db.Column(db.String(100))
    primary_department_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'))
    
    # Faculty abbreviation for timetable lookup (e.g., PB, SH, JN, RK)
    abbreviation = db.Column(db.String(20), nullable=True, index=True)

    # Legacy/Admin scope (exists in initial migration)
    admin_access_dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'), nullable=True)

    # Designation
    designation = db.Column(db.String(50))
    
    # Roles
    is_event_coordinator = db.Column(db.Boolean, default=False)
    is_amc_member = db.Column(db.Boolean, default=False)
    is_amc_head = db.Column(db.Boolean, default=False)
    is_mdm_oe_coordinator = db.Column(db.Boolean, default=False)
    
    # Placeholder flag for adjunct/external faculty created during bulk upload
    is_placeholder = db.Column(db.Boolean, default=False)


class Department(db.Model):
    __tablename__ = 'department'
    dept_id = db.Column(db.Integer, primary_key=True)
    # Legacy: Department belongs to a School (initial schema)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # NEW (Hierarchy Overlay): optional link to Program
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=True)

    # NEW (Hierarchy Overlay): admin for this department
    dept_admin_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)
    
    # --- FIX: usage of use_alter=True handles the circular dependency ---
    hod_staff_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id', use_alter=True), nullable=True)


# ==========================================
# 3A. ACADEMIC HIERARCHY (NEW - OVERLAY)
# ==========================================
class School(db.Model):
    __tablename__ = 'school'
    id = db.Column(db.Integer, primary_key=True)
    # Keep consistent with initial migration (length 255, no enforced unique here)
    name = db.Column(db.String(255), nullable=False)


class Program(db.Model):
    __tablename__ = 'program'
    id = db.Column(db.Integer, primary_key=True)
    # Legacy (initial schema)
    dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    level = db.Column(db.String(50), nullable=False)
    # NEW (Hierarchy Overlay): Program belongs to a School
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=True)


class Specialization(db.Model):
    __tablename__ = 'specialization'
    # Legacy (initial schema)
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50), nullable=False)
    # NEW (Hierarchy Overlay): Specialization belongs to a Department
    dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'), nullable=True)
    hod_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)

# class Department(db.Model):
#     __tablename__ = 'department'
#     dept_id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), unique=True, nullable=False)
#     hod_staff_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)


class ParentProfile(db.Model):
    __tablename__ = 'parent_profile'
    parent_id = db.Column(db.String(36), db.ForeignKey('user_master.user_id'), primary_key=True)
    father_name = db.Column(db.String(100))
    mother_name = db.Column(db.String(100))
    primary_phone = db.Column(db.String(20), unique=True)

class StudentProfile(db.Model):
    __tablename__ = 'student_profile'
    student_id = db.Column(db.String(36), db.ForeignKey('user_master.user_id'), primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    admission_number = db.Column(db.String(50), unique=True, nullable=False)
    parent_user_id = db.Column(db.String(36), db.ForeignKey('parent_profile.parent_id'))
    current_section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'))
    academic_status = db.Column(db.String(50), default='Active')
    batch = db.Column(db.String(20))
    
    # NEW: MENTOR LINK
    mentor_batch_id = db.Column(db.Integer, db.ForeignKey('mentor_batch.batch_id'), nullable=True)

# ==========================================
# 3. ACADEMIC STRUCTURE
# ==========================================
class Subject(db.Model):
    __tablename__ = 'subject'
    subject_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'))
    subject_type = db.Column(db.String(50), default='Core')
    
    # Abbreviation used in timetable (e.g., OS, SE, CN, DEVOPS)
    abbreviation = db.Column(db.String(20), nullable=True, index=True)
    
    # Category from allocation (e.g., PCC, ELECTIVE-I, HSSM-ENT, ELC, VSEC)
    category = db.Column(db.String(50), nullable=True)
    
    # Pattern year (e.g., 2021, 2023)
    pattern = db.Column(db.String(10), nullable=True)

    # NEW: Academic Load Structure (Hours per Week)
    l_count = db.Column(db.Integer, default=0) # Lecture Hours
    t_count = db.Column(db.Integer, default=0) # Tutorial Hours
    p_count = db.Column(db.Integer, default=0) # Practical/Lab Hours
    credits = db.Column(db.Integer, default=0) # Total Credits

    target_class = db.Column(db.String(10))
    
    # MDM/OE Integration - Treat MDM courses as "special subjects"
    is_mdm_oe = db.Column(db.Boolean, default=False)  # True if this subject is from MDM/OE pool
    mdm_pool_id = db.Column(db.Integer, db.ForeignKey('mdm_offering_pool.id'), nullable=True)  # Link back to pool
    mdm_direction = db.Column(db.String(10), nullable=True)  # 'Inbound' or 'Outbound' (for quick filtering)

class ClassSection(db.Model):
    __tablename__ = 'class_section'
    section_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False)
    class_level = db.Column(db.String(50), nullable=False)
    # NEW (Hierarchy Overlay): optional link to Specialization
    spec_id = db.Column(db.Integer, db.ForeignKey('specialization.id'), nullable=True)
    class_teacher_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)
    
    # MDM/OE: Virtual sections for external students
    is_virtual = db.Column(db.Boolean, default=False)  # True = virtual section for MDM inbound
    mdm_pool_id = db.Column(db.Integer, db.ForeignKey('mdm_offering_pool.id'), nullable=True)  # Links to pool for virtual sections

class SubjectAllocation(db.Model):
    __tablename__ = 'subject_allocation'
    allocation_id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)
    teacher_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)  # Nullable for "Respective Faculties"
    
    # Session type: L (Lecture), T (Tutorial), P (Practical)
    session_type = db.Column(db.String(10), nullable=True)
    
    # Batch for practical sessions (A, B, C, etc.) - NULL means full class
    target_batch = db.Column(db.String(20), nullable=True)
    
    # Teaching type: Regular, Block
    teaching_type = db.Column(db.String(20), default='Regular')
    
    # Faculty abbreviation for quick lookup (e.g., PB, SH, JN)
    faculty_abbreviation = db.Column(db.String(20), nullable=True)
    
    # Unique constraint: one teacher per subject per section per session_type per batch
    __table_args__ = (
        db.Index('ix_allocation_lookup', 'section_id', 'subject_id', 'session_type', 'target_batch'),
    )


class SemesterCourseStructure(db.Model):
    __tablename__ = 'semester_course_structure'
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)
    semester_no = db.Column(db.Integer, nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)

class StudentElective(db.Model):
    __tablename__ = 'student_elective'
    map_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)
    # NEW: tie selections to a specific elective window (target semester + bucket)
    window_id = db.Column(db.Integer, db.ForeignKey('elective_window.id'), nullable=True)
    status = db.Column(db.String(20), default='Pending') # 'Pending', 'Approved', 'Rejected'

class TimetableVersion(db.Model):
    """Versioning for timetable/schedule - allows Draft vs Active vs Archived per section"""
    __tablename__ = 'timetable_version'
    version_id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)

    # Version identification
    version_number = db.Column(db.Integer, nullable=False, default=1)
    version_label = db.Column(db.String(50))  # e.g., "2025-26 Sem1 Initial", "Mid-Term Adjustment"

    # Status: 'Draft', 'Active', 'Archived'
    status = db.Column(db.String(20), nullable=False, default='Draft')

    # Timetable type: 'Block' or 'Regular' (for dual-timetable system)
    timetable_type = db.Column(db.String(20), default='Regular')
    # Link to period configuration
    period_id = db.Column(db.Integer, db.ForeignKey('timetable_period.id'), nullable=True)

    # Metadata
    created_by_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    published_at = db.Column(db.DateTime, nullable=True)  # When Draft -> Active
    archived_at = db.Column(db.DateTime, nullable=True)   # When Active -> Archived

    # Source tracking (for audit)
    source_type = db.Column(db.String(20))  # 'csv_upload', 'auto_generate', 'clone', 'manual', 'migration'
    cloned_from_version_id = db.Column(db.Integer, db.ForeignKey('timetable_version.version_id'), nullable=True)

    # Notes
    notes = db.Column(db.Text, nullable=True)

    # Index for efficient lookups
    __table_args__ = (
        db.Index('ix_timetable_version_section_status', 'section_id', 'status'),
    )


class WeeklySchedule(db.Model):
    __tablename__ = 'weekly_schedule'
    schedule_id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'))
    teacher_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'))
    day_of_week = db.Column(db.String(15), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    session_type = db.Column(db.String(20), default='Lecture') # Lecture, Practical, Tutorial
    target_batch = db.Column(db.String(20), nullable=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room_master.room_id'), nullable=True)

    # Link to timetable version (nullable for migration compatibility)
    version_id = db.Column(db.Integer, db.ForeignKey('timetable_version.version_id'), nullable=True, index=True)

    # For "Respective Faculties" entries - slot created but faculty TBD
    is_unassigned = db.Column(db.Boolean, default=False)
    
    # Custom label for special slots (Library, Mentor Meeting, SCIL, etc.) when no subject assigned
    slot_label = db.Column(db.String(100), nullable=True)

# ==========================================
# 4. MENTOR MANAGEMENT (NEW)
# ==========================================
class MentorBatch(db.Model):
    __tablename__ = 'mentor_batch'
    batch_id = db.Column(db.Integer, primary_key=True)
    batch_name = db.Column(db.String(50), nullable=False) # e.g., "Batch A", "Batch B"
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)
    mentor_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)

# ==========================================
# 5. EVENT MANAGEMENT
# ==========================================
class EventMaster(db.Model):
    __tablename__ = 'event_master'
    event_id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    coordinator_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=False)
    description = db.Column(db.String(255))

class EventParticipation(db.Model):
    __tablename__ = 'event_participation'
    participation_id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event_master.event_id'), nullable=False)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    status = db.Column(db.String(20), default='Nominated')
    student_role = db.Column(db.String(50), default='Participant')

# ==========================================
# 6. OPERATIONS
# ==========================================
class SessionLog(db.Model):
    __tablename__ = 'session_log'
    session_id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('weekly_schedule.schedule_id'), nullable=True)  # Made nullable for MDM/Extra
    extra_session_id = db.Column(db.Integer, db.ForeignKey('extra_session.id'), nullable=True)  # For extra sessions
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=True)  # For MDM sessions (no schedule_id)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=True)  # For MDM sessions
    session_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Conducted')
    actual_teacher_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)

class AttendanceTransaction(db.Model):
    __tablename__ = 'attendance_transaction'
    transaction_id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_log.session_id'), nullable=False)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=True)  # Made nullable for external students
    external_student_id = db.Column(db.Integer, db.ForeignKey('external_student_profile.external_id'), nullable=True)  # NEW: For MDM/OE inbound students
    status = db.Column(db.String(20), nullable=False)

class LeaveApplication(db.Model):
    __tablename__ = 'leave_application'
    leave_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    total_days = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(255))
    status = db.Column(db.String(20), default='Pending_CT')
    leave_type = db.Column(db.String(50))
    document_url = db.Column(db.String(255))

class LeaveWorkflowLog(db.Model):
    __tablename__ = 'leave_workflow_log'
    log_id = db.Column(db.Integer, primary_key=True)
    leave_id = db.Column(db.Integer, db.ForeignKey('leave_application.leave_id'), nullable=False)
    action_by_user_id = db.Column(db.String(36), db.ForeignKey('user_master.user_id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

class DetentionRecord(db.Model):
    __tablename__ = 'detention_record'
    detention_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    assigned_by_staff_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=False)
    reason = db.Column(db.String(255))
    assignment_details = db.Column(db.Text)
    status = db.Column(db.String(20), default='Assigned')
    submission_doc_url = db.Column(db.String(255))

class SystemLog(db.Model):
    __tablename__ = 'system_log'
    log_id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    action_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    performed_by = db.Column(db.String(100))
    # Department scope for filtering (NULL = global/SuperAdmin action)
    dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'), nullable=True)


# ==========================================
# 7. ELECTIVE MANAGEMENT (NEW)
# ==========================================
class ElectiveOffering(db.Model):
    __tablename__ = 'elective_offering'
    offering_id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)

    # NEW: link offerings to a specific elective window (target semester + bucket)
    window_id = db.Column(db.Integer, db.ForeignKey('elective_window.id'), nullable=True)
    
    # Status: 'Open' (Students can pick), 'Closed' (Selection over), 'Dropped' (Less than 12 students)
    status = db.Column(db.String(20), default='Open')


class ElectiveWindow(db.Model):
    __tablename__ = 'elective_window'
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)
    target_semester_no = db.Column(db.Integer, nullable=False)
    bucket = db.Column(db.String(50), nullable=False)  # e.g. 'Elective-II', 'Open Elective'
    # Window status: Open (all can edit), Extension (only affected students can edit), Closed (locked)
    status = db.Column(db.String(20), default='Open')
    min_batch_size = db.Column(db.Integer, default=12)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    closed_at = db.Column(db.DateTime, nullable=True)
    # NEW: Deadline & automation fields
    deadline_at = db.Column(db.DateTime, nullable=True)  # Auto-close after this
    reminder_sent_at = db.Column(db.DateTime, nullable=True)  # Track reminders
    rollout_batch_id = db.Column(db.String(36), nullable=True)  # Group windows from same bulk operation


class ElectiveSubjectPool(db.Model):
    """Elective subjects available for rollout - independent of SemesterCourseStructure.
    This allows rolling out electives BEFORE the full course structure is uploaded."""
    __tablename__ = 'elective_subject_pool'
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)
    target_class_level = db.Column(db.String(2), nullable=False)  # FY, SY, TY, LY
    target_semester_no = db.Column(db.Integer, nullable=False)
    bucket = db.Column(db.String(50), nullable=False)  # 'Elective-I', 'Open Elective', etc.
    academic_year = db.Column(db.String(20), nullable=False)  # '2025-26'
    
    # Academic Load Structure (Hours per Week) - for load calculation
    l_count = db.Column(db.Integer, default=0)  # Lecture Hours
    t_count = db.Column(db.Integer, default=0)  # Tutorial Hours
    p_count = db.Column(db.Integer, default=0)  # Practical/Lab Hours
    credits = db.Column(db.Integer, default=3)  # Total Credits
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    created_by_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)

    # Unique constraint: same subject can't be in same bucket twice for same level/sem/year
    __table_args__ = (
        db.UniqueConstraint('subject_id', 'target_class_level', 'target_semester_no', 'bucket', 'academic_year',
                            name='uq_elective_pool_subject'),
    )


class ElectiveAuditLog(db.Model):
    """Audit trail for all elective-related actions - enables recovery and debugging"""
    __tablename__ = 'elective_audit_log'
    id = db.Column(db.Integer, primary_key=True)
    action_type = db.Column(db.String(50), nullable=False)  # 'POOL_UPLOAD', 'ROLLOUT_START', 'STUDENT_SELECT', 'ADMIN_MOVE', 'WINDOW_CLOSE', 'ROLLOVER'
    window_id = db.Column(db.Integer, db.ForeignKey('elective_window.id'), nullable=True)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=True)
    old_value = db.Column(db.JSON, nullable=True)  # Previous state for recovery
    new_value = db.Column(db.JSON, nullable=True)  # New state
    details = db.Column(db.Text, nullable=True)  # Human-readable description
    performed_by_id = db.Column(db.String(36), db.ForeignKey('user_master.user_id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())


class ElectiveRolloutTemplate(db.Model):
    """Templates for quickly creating elective windows across sections"""
    __tablename__ = 'elective_rollout_template'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g., "SY Sem 4 Standard"
    dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'), nullable=True)
    class_level = db.Column(db.String(10), nullable=False)  # FY, SY, TY, LY
    target_semester_no = db.Column(db.Integer, nullable=False)
    buckets_config = db.Column(db.JSON, nullable=False)  # [{bucket, subject_ids}]
    min_batch_size = db.Column(db.Integer, default=12)
    default_duration_days = db.Column(db.Integer, default=7)  # Default window duration
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    created_by_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)



# ==========================================
# 8. INFRASTRUCTURE (NEW)
# ==========================================
class RoomMaster(db.Model):
    __tablename__ = 'room_master'
    room_id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(50), unique=True, nullable=False) # e.g., "C-101", "LAB-2"
    room_type = db.Column(db.String(50), nullable=False) # 'Classroom', 'Laboratory', 'Tutorial Room'
    capacity = db.Column(db.Integer, nullable=False)
    location = db.Column(db.String(100)) # e.g., "Building A, 2nd Floor"
    dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id')) # Which dept owns this room

from datetime import date
class MentorLog(db.Model):
    __tablename__ = 'mentor_log'
    log_id = db.Column(db.Integer, primary_key=True)
    
    # Links
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    mentor_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=False)
    mentor_batch_id = db.Column(db.Integer, db.ForeignKey('mentor_batch.batch_id'), nullable=True)
    
    date = db.Column(db.Date, nullable=False, default=date.today)
    
    # Content
    issue_category = db.Column(db.String(50), nullable=False) # Academic, Personal, Disciplinary, Financial
    remarks = db.Column(db.Text, nullable=False)
    action_taken = db.Column(db.Text, nullable=True)
    
    # Status: Open, Resolved, Escalated
    status = db.Column(db.String(20), default='Open')

class MentorMeeting(db.Model):
    __tablename__ = 'mentor_meeting'
    meeting_id = db.Column(db.Integer, primary_key=True)
    mentor_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('mentor_batch.batch_id'), nullable=False)

    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    agenda = db.Column(db.String(255), nullable=False) # e.g. "Term Start Review"

    # New fields for NAAC compliance
    venue = db.Column(db.String(100), nullable=True)  # e.g., "Room C-101" or "HOD Chamber"
    discussion_points = db.Column(db.Text, nullable=True)  # Newline-separated topics
    summary = db.Column(db.Text, nullable=True)  # Notes after meeting is conducted
    completed_at = db.Column(db.DateTime, nullable=True)  # When meeting was marked complete

    # Status: 'Scheduled', 'Completed'
    status = db.Column(db.String(20), default='Scheduled')


class MeetingAttendance(db.Model):
    """Tracks which students attended each mentor meeting."""
    __tablename__ = 'meeting_attendance'
    attendance_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('mentor_meeting.meeting_id'), nullable=False)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    attended = db.Column(db.Boolean, default=False)
    remarks = db.Column(db.String(255), nullable=True)  # Reason for absence or special notes


class MeetingIssue(db.Model):
    """Records issues raised during mentor meetings and actions taken."""
    __tablename__ = 'meeting_issue'
    issue_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('mentor_meeting.meeting_id'), nullable=False)

    # Who raised the issue (optional - for anonymous issues)
    raised_by_student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=True)

    # Issue details
    issue_description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default='General')  # Academic, Personal, Infrastructure, Other

    # Action taken
    action_taken = db.Column(db.Text, nullable=True)
    action_status = db.Column(db.String(20), default='Pending')  # Pending, In Progress, Resolved

    # Timestamps
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    resolved_at = db.Column(db.DateTime, nullable=True)


class Notification(db.Model):
    __tablename__ = 'notification'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user_master.user_id'), nullable=False) # Recipient
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(20), default='info') # info, warning, success, danger
    link = db.Column(db.String(255)) # Optional URL to redirect (e.g. to detention page)
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())


# ==========================================
# MOBILE: TOKENS & PUSH DEVICES (NEW)
# ==========================================
class RefreshToken(db.Model):
    __tablename__ = 'refresh_token'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user_master.user_id'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    device_id = db.Column(db.String(128), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)


class PushDevice(db.Model):
    __tablename__ = 'push_device'
    __table_args__ = (
        db.UniqueConstraint('platform', 'device_id', 'user_id', name='uq_push_device_platform_device_user'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user_master.user_id'), nullable=False, index=True)
    platform = db.Column(db.String(20), nullable=False)  # 'android' / 'ios'
    device_id = db.Column(db.String(128), nullable=False)
    fcm_token = db.Column(db.String(255), nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    last_seen_at = db.Column(db.DateTime, default=db.func.current_timestamp())


class CAMarks(db.Model):
    __tablename__ = 'ca_marks'
    mark_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=True)  # Made nullable for external students
    external_student_id = db.Column(db.Integer, db.ForeignKey('external_student_profile.external_id'), nullable=True)  # NEW: For MDM/OE inbound students
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=True)  # Nullable for cross-school offerings
    cross_school_offering_id = db.Column(db.Integer, db.ForeignKey('cross_school_offering.offering_id'), nullable=True)  # NEW: For MDM/OE courses
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=True)  # Nullable for external students
    
    # Raw Marks
    ta1 = db.Column(db.Float, default=0)
    ta2 = db.Column(db.Float, default=0)
    ta3 = db.Column(db.Float, default=0)
    a1 = db.Column(db.Float, default=0)
    a2 = db.Column(db.Float, default=0)
    a3 = db.Column(db.Float, default=0)
    a4 = db.Column(db.Float, default=0)
    a5 = db.Column(db.Float, default=0)
    
    # Derived Data
    learner_status = db.Column(db.String(20), default='Average') 
    attendance_score = db.Column(db.Float, default=0) 
    total_ca = db.Column(db.Float, default=0) 
    
    # --- UPDATED: Granular Publish Flags ---
    is_published_ta1 = db.Column(db.Boolean, default=False)
    is_published_ta2 = db.Column(db.Boolean, default=False)
    is_published_ta3 = db.Column(db.Boolean, default=False)

class TermGrantRecord(db.Model):
    __tablename__ = 'term_grant_record'
    record_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)
    
    # Snapshot of metrics at time of calculation
    attendance_perc = db.Column(db.Float, default=0.0)
    avg_ca_score = db.Column(db.Float, default=0.0)
    failed_subjects_count = db.Column(db.Integer, default=0) # Subjects with < 20 marks
    active_detentions = db.Column(db.Integer, default=0)
    
    # Decision
    status = db.Column(db.String(20), default='Pending') # Granted, Provisional, Detained
    remarks = db.Column(db.String(255))
    is_published = db.Column(db.Boolean, default=False)


    # In sql_connection.py

# ==========================================
# 11. STUDENT FEEDBACK SYSTEM
# ==========================================
class FeedbackCycle(db.Model):
    __tablename__ = 'feedback_cycle'
    cycle_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # e.g. "End Semester Feedback 2025"
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=False)

class FeedbackQuestion(db.Model):
    __tablename__ = 'feedback_question'
    question_id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50)) # e.g. "Teaching", "Resources", "Lab"
    is_active = db.Column(db.Boolean, default=True)

class FeedbackResponse(db.Model):
    __tablename__ = 'feedback_response'
    response_id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey('feedback_cycle.cycle_id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)
    teacher_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True) # Optional for general feedback
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)
    
    # Store ratings as JSON string to be flexible (e.g. {"q1": 5, "q2": 4})
    # Or simple columns if questions are fixed. Let's use a simple mapping for standard 5-point scale.
    # We will store individual question ratings in a separate table or just aggregate here?
    # To keep it relational and simple for SQL averaging:
    question_id = db.Column(db.Integer, db.ForeignKey('feedback_question.question_id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False) # 1-5

class StudentFeedbackStatus(db.Model):
    """Tracks IF a student has submitted feedback for a subject, without linking to the score."""
    __tablename__ = 'student_feedback_status'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    cycle_id = db.Column(db.Integer, db.ForeignKey('feedback_cycle.cycle_id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)
    submitted_on = db.Column(db.DateTime, default=db.func.current_timestamp())



# ==========================================
# 12. LESSON PLANNING & SYLLABUS
# ==========================================
class TeachingPlan(db.Model):
    __tablename__ = 'teaching_plan'
    plan_id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)
    created_by_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'))
    
    unit_number = db.Column(db.Integer, nullable=False)
    sub_unit = db.Column(db.String(50)) # <--- NEW COLUMN (e.g., "1.1", "1.2")
    topic_name = db.Column(db.String(255), nullable=False)
    planned_hours = db.Column(db.Integer, default=1)
    
    # Status can be 'Pending', 'Completed'
    status = db.Column(db.String(20), default='Pending')

class LessonLog(db.Model):
    __tablename__ = 'lesson_log'
    log_id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_log.session_id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('teaching_plan.plan_id'), nullable=False)
    
    completion_percentage = db.Column(db.Integer, default=100) # Did they finish the whole topic?
    remarks = db.Column(db.String(255))


# ==========================================
# 13. LOAD ADJUSTMENT (MUTUAL SWAP)
# ==========================================
class LoadAdjustment(db.Model):
    __tablename__ = 'load_adjustment'
    id = db.Column(db.Integer, primary_key=True)
    
    requester_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=False)
    adjuster_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=False)
    
    # Slot A: The one Requester cannot take (Given to Adjuster)
    req_date = db.Column(db.Date, nullable=False)
    req_schedule_id = db.Column(db.Integer, db.ForeignKey('weekly_schedule.schedule_id'), nullable=False)
    
    # Slot B: The one Adjuster gives back (Taken by Requester)
    adj_date = db.Column(db.Date, nullable=False)
    adj_schedule_id = db.Column(db.Integer, db.ForeignKey('weekly_schedule.schedule_id'), nullable=False)
    
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Rejected
    reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


# ==========================================
# 14. SYSTEM CONFIGURATION & ARCHIVES
# ==========================================
class SystemConfig(db.Model):
    __tablename__ = 'system_config'
    key = db.Column(db.String(50), primary_key=True) # e.g., 'current_term'
    value = db.Column(db.String(100)) # e.g., 'YYYY-YY Sem 1'

class ArchivedAllocation(db.Model):
    __tablename__ = 'archived_allocation'
    id = db.Column(db.Integer, primary_key=True)
    term_name = db.Column(db.String(50)) # Snapshot tag
    section_id = db.Column(db.Integer)
    subject_code = db.Column(db.String(20))
    subject_name = db.Column(db.String(100))
    teacher_name = db.Column(db.String(100))
    archived_on = db.Column(db.DateTime, default=db.func.current_timestamp())

class ArchivedSchedule(db.Model):
    __tablename__ = 'archived_schedule'
    id = db.Column(db.Integer, primary_key=True)
    term_name = db.Column(db.String(50))
    section_name = db.Column(db.String(50))
    day = db.Column(db.String(20))
    time_slot = db.Column(db.String(50))
    subject = db.Column(db.String(100))
    teacher = db.Column(db.String(100))


# ==========================================
# 15. EXTRA SESSIONS (ONE-TIME CLASSES)
# ==========================================
class ExtraSession(db.Model):
    """Extra session - one-time class scheduled outside regular timetable"""
    __tablename__ = 'extra_session'
    id = db.Column(db.Integer, primary_key=True)

    # Link to subject and section
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)
    teacher_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=False)

    # Schedule
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    # Optional details
    topic = db.Column(db.String(255), nullable=True)
    meeting_link = db.Column(db.String(255), nullable=True)

    # Status: Scheduled, Completed, Cancelled
    status = db.Column(db.String(20), default='Scheduled')


# ==========================================
# 16. CROSS-SCHOOL COURSES (MDM/OE)
# ==========================================
class CrossSchoolOffering(db.Model):
    """MDM (Multidisciplinary Minor) and OE (Open Elective) course catalog.
    
    Supports both:
    - Inbound: External students come to us (we host the course)
    - Outbound: Our students go to other schools (they host the course)
    """
    __tablename__ = 'cross_school_offering'
    offering_id = db.Column(db.Integer, primary_key=True)
    
    # Course Details
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), nullable=True)
    type = db.Column(db.String(20), nullable=False)  # 'MDM' or 'OE'
    direction = db.Column(db.String(20), nullable=False)  # 'Inbound' or 'Outbound'
    credits = db.Column(db.Integer, default=0)
    
    # Host Information
    host_school_id = db.Column(db.Integer, nullable=True)
    host_school_name = db.Column(db.String(100), nullable=True)  # For Outbound display
    
    # Inbound-specific (when we host)
    assigned_faculty_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)
    capacity = db.Column(db.Integer, nullable=True)
    
    # Timeline
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    schedule_pattern = db.Column(db.String(255), nullable=True)  # "Mon-Fri, 4 PM - 6 PM"
    
    # Status: Draft, Open, Closed, Archived
    status = db.Column(db.String(20), default='Draft')
    
    # Description
    description = db.Column(db.Text, nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Exclude from regular faculty load calculation
    exclude_from_load = db.Column(db.Boolean, default=True)


class ExternalStudentProfile(db.Model):
    """Lightweight profile for guest students attending our Inbound MDM/OE courses.
    
    These students belong to other schools and are NOT in our main StudentProfile table.
    No login credentials - used only for attendance and marks tracking.
    """
    __tablename__ = 'external_student_profile'
    external_id = db.Column(db.Integer, primary_key=True)
    
    # Basic Info
    full_name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), nullable=True)
    
    # Home School
    home_school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=True)
    home_school_name = db.Column(db.String(100), nullable=False)
    department_name = db.Column(db.String(100), nullable=True)
    
    # Enrollment
    enrolled_offering_id = db.Column(db.Integer, db.ForeignKey('cross_school_offering.offering_id'), nullable=False)
    
    # Status: Active, Completed, Dropped
    status = db.Column(db.String(20), default='Active')
    
    # Metadata
    enrolled_on = db.Column(db.DateTime, default=db.func.current_timestamp())


class CrossSchoolEnrollment(db.Model):
    """Tracks our students enrolled in Outbound MDM/OE courses (hosted by other schools)."""
    __tablename__ = 'cross_school_enrollment'
    enrollment_id = db.Column(db.Integer, primary_key=True)
    
    # Our Student
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    
    # Outbound Course
    offering_id = db.Column(db.Integer, db.ForeignKey('cross_school_offering.offering_id'), nullable=False)
    
    # Status: Pending, Confirmed, Completed, Dropped
    status = db.Column(db.String(20), default='Pending')
    
    # Marks from external school (imported via CSV)
    external_marks = db.Column(db.Float, nullable=True)
    external_grade = db.Column(db.String(5), nullable=True)
    
    # Metadata
    enrolled_on = db.Column(db.DateTime, default=db.func.current_timestamp())
    completed_on = db.Column(db.DateTime, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


# ==========================================
# 17. MDM/OE REVAMPED - Pool & Selection System
# ==========================================

class MDMOfferingPool(db.Model):
    """Pool of MDM/OE courses available for rollout - handles BOTH Inbound and Outbound.
    
    Inbound (we host): Our faculty teaches external students
    Outbound (they host): Partner school teaches our students
    """
    __tablename__ = 'mdm_offering_pool'
    id = db.Column(db.Integer, primary_key=True)
    
    # Core identity
    code = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(10), nullable=False)       # 'MDM' or 'OE'
    direction = db.Column(db.String(10), nullable=False)  # 'Inbound' or 'Outbound'
    
    # Academic Load Structure (Hours per Week) - for load calculation
    l_count = db.Column(db.Integer, default=0)   # Lecture Hours
    t_count = db.Column(db.Integer, default=0)   # Tutorial Hours
    p_count = db.Column(db.Integer, default=0)   # Practical/Lab Hours
    credits = db.Column(db.Integer, default=3)   # Total Credits
    
    # Inbound-specific (we host)
    assigned_faculty_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)
    
    # Outbound-specific (partner hosts)
    host_school_name = db.Column(db.String(200), nullable=True)
    host_contact_email = db.Column(db.String(100), nullable=True)
    
    # Common fields
    capacity = db.Column(db.Integer, nullable=True)  # NULL = unlimited
    schedule_pattern = db.Column(db.String(100), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.Text, nullable=True)
    
    # Scoping
    academic_year = db.Column(db.String(20), nullable=False)  # '2025-26'
    target_class_levels = db.Column(db.String(50), nullable=True)  # 'SY,TY' or NULL for all
    dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'), nullable=True)  # Department scope

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    created_by_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('code', 'academic_year', name='uq_mdm_pool_code_year'),
    )


class MDMOutboundWindow(db.Model):
    """Selection window for OUR students to choose Outbound MDM/OE courses.
    
    Similar to ElectiveWindow but specifically for outbound cross-school courses.
    Inbound courses don't need windows - external students are assigned via CSV upload.
    """
    __tablename__ = 'mdm_outbound_window'
    id = db.Column(db.Integer, primary_key=True)
    
    # Target audience (our students)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=True)
    class_level = db.Column(db.String(10), nullable=True)  # FY, SY, TY, LY - if NULL, uses section
    dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'), nullable=True)
    
    course_type = db.Column(db.String(10), nullable=False)  # 'MDM', 'OE', or 'BOTH'
    academic_year = db.Column(db.String(20), nullable=False)
    
    # Window lifecycle
    status = db.Column(db.String(20), default='Open')  # Open, Extension, Closed
    min_batch_size = db.Column(db.Integer, default=15)
    
    # Timeline
    deadline_at = db.Column(db.DateTime, nullable=True)
    extension_deadline_at = db.Column(db.DateTime, nullable=True)
    reminder_sent_at = db.Column(db.DateTime, nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    closed_at = db.Column(db.DateTime, nullable=True)
    rollout_batch_id = db.Column(db.String(36), nullable=True)  # Group windows from same operation
    created_by_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)


class MDMWindowOffering(db.Model):
    """Links pool courses to outbound selection windows.
    
    Defines which courses from the pool are available in a specific window.
    """
    __tablename__ = 'mdm_window_offering'
    id = db.Column(db.Integer, primary_key=True)
    window_id = db.Column(db.Integer, db.ForeignKey('mdm_outbound_window.id'), nullable=False)
    pool_id = db.Column(db.Integer, db.ForeignKey('mdm_offering_pool.id'), nullable=False)
    
    # Override capacity for this specific window (NULL = use pool capacity)
    window_capacity = db.Column(db.Integer, nullable=True)
    
    # Status after window closes: Pending, Confirmed, Cancelled (if < min_batch)
    final_status = db.Column(db.String(20), default='Pending')
    
    __table_args__ = (
        db.UniqueConstraint('window_id', 'pool_id', name='uq_mdm_window_offering'),
    )


class MDMOutboundSelection(db.Model):
    """Our student's selection for an Outbound MDM/OE course.
    
    Similar to StudentElective but for cross-school outbound courses.
    """
    __tablename__ = 'mdm_outbound_selection'
    id = db.Column(db.Integer, primary_key=True)
    
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    window_id = db.Column(db.Integer, db.ForeignKey('mdm_outbound_window.id'), nullable=False)
    pool_id = db.Column(db.Integer, db.ForeignKey('mdm_offering_pool.id'), nullable=False)
    
    # Status: Selected, Confirmed, Dropped, Reassigned
    status = db.Column(db.String(20), default='Selected')
    selected_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    confirmed_at = db.Column(db.DateTime, nullable=True)
    
    # Marks imported from partner school (after course completion)
    external_marks = db.Column(db.Float, nullable=True)
    external_grade = db.Column(db.String(5), nullable=True)
    marks_imported_at = db.Column(db.DateTime, nullable=True)
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'window_id', 'pool_id', name='uq_mdm_student_selection'),
    )


class MDMAuditLog(db.Model):
    """Audit trail for all MDM/OE actions - enables recovery and debugging."""
    __tablename__ = 'mdm_audit_log'
    id = db.Column(db.Integer, primary_key=True)
    
    action_type = db.Column(db.String(50), nullable=False)  
    # Actions: POOL_UPLOAD, POOL_DELETE, WINDOW_OPEN, WINDOW_CLOSE, STUDENT_SELECT, 
    #          STUDENT_DROP, COURSE_CANCEL, MARKS_IMPORT, EXTERNAL_UPLOAD, MARKS_EXPORT
    
    window_id = db.Column(db.Integer, db.ForeignKey('mdm_outbound_window.id'), nullable=True)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=True)
    pool_id = db.Column(db.Integer, db.ForeignKey('mdm_offering_pool.id'), nullable=True)
    
    old_value = db.Column(db.JSON, nullable=True)  # Previous state
    new_value = db.Column(db.JSON, nullable=True)  # New state
    details = db.Column(db.Text, nullable=True)    # Human-readable description

    performed_by_id = db.Column(db.String(36), db.ForeignKey('user_master.user_id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())


# ==========================================
# DUAL TIMETABLE SYSTEM (Block + Regular)
# ==========================================

class TimetablePeriod(db.Model):
    """Date range configuration for Block Teaching vs Regular Teaching periods"""
    __tablename__ = 'timetable_period'
    id = db.Column(db.Integer, primary_key=True)

    # Period identification
    name = db.Column(db.String(100), nullable=False)  # e.g., "Block Teaching Jan 2026"
    timetable_type = db.Column(db.String(20), nullable=False)  # 'Block' or 'Regular'
    academic_year = db.Column(db.String(20), nullable=False)   # '2025-26'
    semester = db.Column(db.Integer, nullable=False)           # 1 (odd) or 2 (even)

    # Date range (global dates, applies to all sections)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    # Status: Draft, Active, Archived
    status = db.Column(db.String(20), default='Draft')

    # Metadata
    created_by_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


class ScheduleChange(db.Model):
    """Runtime changes to timetable (substitutions, room changes, cancellations)"""
    __tablename__ = 'schedule_change'
    id = db.Column(db.Integer, primary_key=True)

    # Change type: FACULTY_SUB, ROOM_CHANGE, TIME_SWAP, BATCH_MERGE, BATCH_SPLIT, SESSION_CANCEL, MAKEUP_CLASS
    change_type = db.Column(db.String(30), nullable=False)

    # What's being changed
    original_schedule_id = db.Column(db.Integer, db.ForeignKey('weekly_schedule.schedule_id'), nullable=True)

    # Effective date range (when this change applies)
    effective_from = db.Column(db.Date, nullable=False)
    effective_to = db.Column(db.Date, nullable=True)  # NULL = permanent

    # For specific date overrides (e.g., single day substitution)
    specific_dates = db.Column(db.JSON, nullable=True)  # List of specific dates if not continuous

    # Change details (stored as JSON for flexibility)
    original_values = db.Column(db.JSON, nullable=True)  # Snapshot before change
    new_values = db.Column(db.JSON, nullable=False)      # New values

    # Status: Active, Reverted, Expired
    status = db.Column(db.String(20), default='Active')

    # Audit
    reason = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    approved_by_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)


class HolidayCalendar(db.Model):
    """Institution-wide and department-specific holidays"""
    __tablename__ = 'holiday_calendar'
    id = db.Column(db.Integer, primary_key=True)

    date = db.Column(db.Date, nullable=False)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Republic Day"
    type = db.Column(db.String(30), default='Full')   # 'Full', 'Half', 'Optional'

    # Scope (NULL = institution-wide)
    dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'), nullable=True)

    academic_year = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())


class LoadAllocationDetail(db.Model):
    """Detailed load allocation from CSV - one row per session type + batch combination"""
    __tablename__ = 'load_allocation_detail'
    id = db.Column(db.Integer, primary_key=True)

    # Teaching type: 'Block' or 'Regular'
    teaching_type = db.Column(db.String(20), nullable=False)

    # Subject reference
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)

    # Teacher (NULL if "Respective Faculties" placeholder)
    teacher_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)
    is_unassigned = db.Column(db.Boolean, default=False)  # True for "Respective Faculties"

    # Session type: L (Lecture), T (Tutorial), P (Practical)
    session_type = db.Column(db.String(10), nullable=False)  # 'L', 'T', 'P'

    # Target section (NULL if applies to all classes - cross-class Block session)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=True)
    class_level = db.Column(db.String(10), nullable=True)  # FY, SY, TY, LY (NULL = all)

    # Batch for practicals (NULL = whole class)
    batch = db.Column(db.String(20), nullable=True)  # 'A', 'B', 'C', or NULL

    # Hours per week for this session
    hours_per_week = db.Column(db.Integer, default=1)

    # Category from CSV (PCC, Elective-I, MDM, etc.)
    category = db.Column(db.String(50), nullable=True)

    # Pattern/curriculum year
    pattern = db.Column(db.String(10), nullable=True)  # '2023', '2021'

    # Academic context
    academic_year = db.Column(db.String(20), nullable=True)  # '2025-26'
    semester = db.Column(db.Integer, nullable=True)  # 1 or 2

    # Metadata
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    upload_batch_id = db.Column(db.String(36), nullable=True)  # Group rows from same upload

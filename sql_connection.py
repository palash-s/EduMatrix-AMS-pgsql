import os
import uuid
from flask_sqlalchemy import SQLAlchemy

from sqlalchemy import MetaData
from sqlalchemy.engine.url import URL

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

    # Designation
    designation = db.Column(db.String(50))
    
    # Roles
    is_event_coordinator = db.Column(db.Boolean, default=False)
    is_amc_member = db.Column(db.Boolean, default=False)
    is_amc_head = db.Column(db.Boolean, default=False)


class Department(db.Model):
    __tablename__ = 'department'
    dept_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    
    # --- FIX: usage of use_alter=True handles the circular dependency ---
    hod_staff_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id', use_alter=True), nullable=True)

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

    # NEW: Academic Load Structure (Hours per Week)
    l_count = db.Column(db.Integer, default=0) # Lecture Hours
    t_count = db.Column(db.Integer, default=0) # Tutorial Hours
    p_count = db.Column(db.Integer, default=0) # Practical/Lab Hours
    credits = db.Column(db.Integer, default=0) # Total Credits

    target_class = db.Column(db.String(10))

class ClassSection(db.Model):
    __tablename__ = 'class_section'
    section_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False)
    class_level = db.Column(db.String(50), nullable=False)
    class_teacher_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)

class SubjectAllocation(db.Model):
    __tablename__ = 'subject_allocation'
    allocation_id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)
    teacher_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=False)


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
    schedule_id = db.Column(db.Integer, db.ForeignKey('weekly_schedule.schedule_id'), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Conducted')
    actual_teacher_id = db.Column(db.String(36), db.ForeignKey('staff_profile.staff_id'), nullable=True)

class AttendanceTransaction(db.Model):
    __tablename__ = 'attendance_transaction'
    transaction_id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session_log.session_id'), nullable=False)
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
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
    student_id = db.Column(db.String(36), db.ForeignKey('student_profile.student_id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.subject_id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('class_section.section_id'), nullable=False)
    
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
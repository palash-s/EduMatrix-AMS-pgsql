from __future__ import annotations

import os
import pandas as pd
import uuid
import secrets
import hashlib
import json
from datetime import timedelta
from datetime import datetime, date
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from sqlalchemy.exc import OperationalError
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
    StaffProfile, ParentProfile, StudentProfile, WeeklySchedule,
    EventMaster, EventParticipation, SubjectAllocation, StudentElective,
    SessionLog, AttendanceTransaction, LeaveApplication, 
    LeaveWorkflowLog, DetentionRecord, SystemLog, MentorBatch, ElectiveOffering, 
    RoomMaster, MentorLog, MentorMeeting, Notification, get_db_uri,CAMarks, TermGrantRecord,
    FeedbackCycle, FeedbackResponse, StudentFeedbackStatus, SystemConfig, ArchivedAllocation, ArchivedSchedule

    , SemesterCourseStructure, ElectiveWindow
    , RefreshToken, PushDevice, LoadAdjustment
)

app = Flask(__name__)
# NOTE: Mobile token auth needs a stable secret key.
# In production set env var SECRET_KEY to a strong random value.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school_system.db'
app.config['SQLALCHEMY_DATABASE_URI'] = get_db_uri(app) 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Mobile token lifetimes (seconds)
app.config['MOBILE_ACCESS_TOKEN_TTL_SECONDS'] = int(os.environ.get('MOBILE_ACCESS_TOKEN_TTL_SECONDS', '1800'))  # 30 min
app.config['MOBILE_REFRESH_TOKEN_TTL_DAYS'] = int(os.environ.get('MOBILE_REFRESH_TOKEN_TTL_DAYS', '30'))


db.init_app(app)
migrate = Migrate(app, db)

PRESENT_STATUSES = ['Present', 'OnDuty', 'OD', 'ML', 'CL']
FIXED_DEPT_NAME = os.environ.get('APP_DEPARTMENT_NAME', 'Department of Information Technology')


@app.route('/api/admin/import_templates/<key>', methods=['GET'])
def api_admin_download_import_template(key: str):
    """Download CSV templates for System Data Import cards.

    Uses a strict allow-list to avoid path traversal.
    """
    templates = {
        # Existing sample files
        'master_class': 'master_class.csv',
        'staff': 'staff_master.csv',
        'students': 'student_master.csv',
        'weekly_schedule': 'weekly_schedule.csv',
        'rooms': 'IT_infra.csv',
        'semester_course_structure': 'semester_course_structure_template.csv',
        'subject_allocation': 'subject_allocation_template.csv',
    }

    filename = templates.get((key or '').strip())
    if not filename:
        return jsonify({"error": "Template not found"}), 404

    data_dir = os.path.join(app.root_path, 'data')
    return send_from_directory(data_dir, filename, as_attachment=True)


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

    if not creds_file and not creds_json:
        _FIREBASE_APP = None
        return None

    try:
        if creds_json:
            info = json.loads(creds_json)
            cred = firebase_credentials.Certificate(info)
        else:
            cred = firebase_credentials.Certificate(creds_file)

        try:
            _FIREBASE_APP = firebase_admin.initialize_app(cred)
        except ValueError:
            _FIREBASE_APP = firebase_admin.get_app()
        return _FIREBASE_APP
    except Exception as e:
        print(f"FCM init failed: {e}")
        _FIREBASE_APP = None
        return None


def _fcm_send_to_tokens(tokens, title: str, body: str, data: dict):
    """Send a push notification to a list of FCM tokens (best-effort)."""
    if not tokens:
        return 0

    if _firebase_get_app() is None:
        return 0

    try:
        # FCM requires all data values to be strings.
        safe_data = {}
        for k, v in (data or {}).items():
            if v is None:
                continue
            safe_data[str(k)] = str(v)

        msg = firebase_messaging.MulticastMessage(
            notification=firebase_messaging.Notification(title=title or '', body=(body or '')[:240]),
            data=safe_data,
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
                print(f"FCM send result: success={success_count} failure={failure_count} sample_errors={errors}")
            else:
                print(f"FCM send result: success={success_count} failure={failure_count}")
        except Exception:
            pass

        return success_count
    except Exception as e:
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
    """Debug helper returning counts: {tokens, success}."""
    if not user_id:
        return {"tokens": 0, "success": 0}

    try:
        devices = (PushDevice.query
                   .filter_by(user_id=user_id, is_active=True)
                   .all())
        tokens = [d.fcm_token for d in devices if d.fcm_token]
        if not tokens:
            return {"tokens": 0, "success": 0}

        success = _fcm_send_to_tokens(tokens, title, body, data)
        return {"tokens": len(tokens), "success": int(success or 0)}
    except Exception as e:
        print(f"FCM debug lookup/send failed for user {user_id}: {e}")
        return {"tokens": 0, "success": 0}


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
# AUTH HELPERS (Session + Mobile)
# ==========================================
def _require_role(*allowed_roles):
    """Check if request comes from a user with one of the allowed_roles.
    
    Expects a 'user_id' in query params or JSON body, then validates the user's type.
    This helper does NOT validate any session or token; callers must ensure that
    providing 'user_id' is safe in their context or combine this with stronger auth.
    Returns (user, error_response). If error_response is not None, return it immediately.
    """
    user_id = request.args.get('user_id') or (request.json or {}).get('user_id')
    if not user_id:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    user = db.session.get(UserMaster, user_id)
    if not user or not user.is_active:
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

    slots = (
        db.session.query(WeeklySchedule, Subject, StaffProfile, RoomMaster)
        .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
        .outerjoin(StaffProfile, WeeklySchedule.teacher_id == StaffProfile.staff_id)
        .outerjoin(RoomMaster, WeeklySchedule.room_id == RoomMaster.room_id)
        .filter(WeeklySchedule.section_id == section.section_id)
        .all()
    )

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
    """Ensures the Single Department exists and returns it."""
    dept = Department.query.filter_by(name=FIXED_DEPT_NAME).first()
    if not dept:
        dept = Department(name=FIXED_DEPT_NAME)
        db.session.add(dept)
        db.session.flush() # Get ID
        print(f"Initialized Department: {FIXED_DEPT_NAME}")
    return dept

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

def log_activity(action, desc, user="Admin"):
    try:
        log = SystemLog(action_type=action, description=desc, performed_by=user)
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
def get_core_classes():
    try:
        classes = ClassSection.query.order_by(ClassSection.class_level, ClassSection.name).all()
        return jsonify({"classes": [{"id": c.section_id, "name": f"{c.class_level} - {c.name}"} for c in classes]})
    except Exception as e: return jsonify({"error": str(e)}), 500

# In app.py

@app.route('/api/core/students', methods=['GET'])
def get_students_by_section():
    try:
        section_id = request.args.get('section_id')
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
                    AttendanceTransaction.status.in_(['Present', 'OnDuty'])
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
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()  # This could be Email OR Employee Code
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    try:
        # 1. Try finding by Username (Email/Phone) - Case Insensitive
        user = UserMaster.query.filter(UserMaster.username.ilike(username)).first()
        
        # 2. If not found, try finding by Employee Code (Staff)
        if not user:
            staff = StaffProfile.query.filter(StaffProfile.employee_code.ilike(username)).first()
            if staff:
                # If Staff found, get their User account (staff_id maps to user_id)
                user = db.session.get(UserMaster, staff.staff_id)
        
        # 3. If STILL not found, try Student Admission Number (Optional Bonus)
        if not user:
            student = StudentProfile.query.filter(StudentProfile.admission_number.ilike(username)).first()
            if student:
                user = db.session.get(UserMaster, student.student_id)

        # 4. Verify Password
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Invalid credentials"}), 401
            
        if not user.is_active:
            return jsonify({"error": "Account Deactivated."}), 403

        role = user.user_type.capitalize()
        
        # Zombie Check (Safety)
        if role == 'Staff' and not StaffProfile.query.filter_by(staff_id=user.user_id).first():
             db.session.delete(user); db.session.commit()
             return jsonify({"error": "Corrupted Account. Please contact Admin."}), 403
             
        redirect_map = { 
            'Student': '/student/dashboard', 
            'Staff': '/staff/dashboard', 
            'Parent': '/parent/dashboard', 
            'Admin': '/admin/dashboard' 
        }
        
        return jsonify({
            "message": "Success", 
            "user_id": user.user_id, 
            "role": role, 
            "redirect_url": redirect_map.get(role, '/')
        }), 200
    except Exception:
        app.logger.exception("/api/login failed")
        return jsonify({"error": "Server error"}), 500


# ==========================================
# MOBILE API v1: AUTH + PROFILE (NEW)
# ==========================================
@app.route('/api/v1/auth/login', methods=['POST'])
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

    role = (user.user_type or '').lower()
    access_token = _issue_access_token(user)
    refresh_token = _issue_refresh_token(user, device_id=device_id)

    return jsonify({
        "access_token": access_token,
        "expires_in": app.config['MOBILE_ACCESS_TOKEN_TTL_SECONDS'],
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "user": {
            "user_id": user.user_id,
            "role": role,
            "username": user.username,
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
                "timestamp": n.timestamp.isoformat() if n.timestamp else None,
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
                "timestamp": n.timestamp.isoformat() if n.timestamp else None,
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

    return jsonify({
        "message": "sent",
        "push_tokens": push_stats.get("tokens", 0),
        "push_success": push_stats.get("success", 0),
    }), 200


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
# API: STAFF DASHBOARD
# ==========================================
# In app.py

@app.route('/api/staff/dashboard', methods=['GET'])
def staff_dashboard():
    try:
        user_id = request.args.get('user_id')
        if not user_id: return jsonify({"error": "Unauthorized"}), 401

        staff = StaffProfile.query.filter_by(staff_id=user_id).first()
        if not staff: return jsonify({"error": "Staff profile not found"}), 404

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
                AttendanceTransaction.status.in_(['Present', 'OnDuty'])
            ).count()
            if total > 0: avg_attendance = round((present / total) * 100, 1)

        # --- 5. ASSIGNED COURSES (Subject Allocation) ---
        allocations = (db.session.query(SubjectAllocation, Subject, ClassSection)
                       .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                       .join(ClassSection, SubjectAllocation.section_id == ClassSection.section_id)
                       .filter(SubjectAllocation.teacher_id == staff.staff_id)
                       .all())
        
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
        window_end = today_date + timedelta(days=6)
        
        all_slots = (db.session.query(WeeklySchedule, ClassSection, Subject)
                    .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
                    .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                    .filter(WeeklySchedule.teacher_id == staff.staff_id)
                    .all())
        
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

        for slot, section, subject in all_slots:
            slot_day_idx = {'Monday':0,'Tuesday':1,'Wednesday':2,'Thursday':3,'Friday':4,'Saturday':5,'Sunday':6}.get(slot.day_of_week, 7)
            
            s_type = getattr(slot, 'session_type', 'Lecture')
            s_batch = getattr(slot, 'target_batch', None)
            
            # Helper to convert time to float (e.g. 09:30 -> 9.5)
            def time_to_float(t): return t.hour + (t.minute / 60.0)
            
            start_float = time_to_float(slot.start_time)
            end_float = time_to_float(slot.end_time)

            # Compute the next occurrence date for this weekday relative to today.
            # For today it will be today_date; for future days in the week it will be within the next 6 days.
            days_ahead = (slot_day_idx - current_day_idx) % 7
            slot_date = today_date + timedelta(days=days_ahead)

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
                "sort_key": slot_day_idx * 10000 + int(slot.start_time.strftime('%H%M')),
                # NEW FIELDS FOR CALENDAR
                "start_float": start_float,
                "duration_float": end_float - start_float,
                "adjustment": _slot_adjustment_payload(slot.schedule_id, slot_date),
            }

            if slot_day_idx == current_day_idx:
                session_exists = SessionLog.query.filter_by(schedule_id=slot.schedule_id, session_date=today_date).first()
                slot_data["status"] = "Done" if session_exists else "Pending"
                today_schedule.append(slot_data)
            elif slot_day_idx > current_day_idx:
                upcoming_schedule.append(slot_data)
            
            # Add to Weekly Calendar
            weekly_calendar.append(slot_data)

        today_schedule.sort(key=lambda x: x['sort_key'])

        # Inject swapped-in classes for Approved adjustments (today + upcoming within the next 7 days)
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
        #         AttendanceTransaction.status.in_(['Present', 'OnDuty'])
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
            present = AttendanceTransaction.query.filter(AttendanceTransaction.session_id == sess.session_id, AttendanceTransaction.status.in_(['Present', 'OnDuty'])).count()
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
                "can_assign_detention": can_assign_detention
            }
        })
    except Exception as e:
        print(f"CRITICAL ERROR in Staff Dashboard: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/staff/find_adjustment_faculty', methods=['GET'])
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
        requester_id = request.args.get('user_id') or request.args.get('requester_id')

        if not schedule_id_raw or not req_date_raw:
            return jsonify([]), 200

        req_schedule_id = int(schedule_id_raw)
        req_date = datetime.strptime(req_date_raw, '%Y-%m-%d').date()

        req_slot = WeeklySchedule.query.filter_by(schedule_id=req_schedule_id).first()
        if not req_slot:
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
def api_staff_submit_adjustment():
    try:
        data = request.get_json(force=True) or {}
        requester_id = data.get('requester_id')
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
                pres = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(s_ids), AttendanceTransaction.status.in_(['Present', 'OnDuty'])).count()
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
                    sub_pres = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(sub_s_ids), AttendanceTransaction.status.in_(['Present', 'OnDuty'])).count()
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
def get_class_analytics():
    try:
        user_id = request.args.get('user_id')
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
                total_presents = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(sub_session_ids), AttendanceTransaction.status.in_(['Present', 'OnDuty'])).count()
                avg_sub_att = round((total_presents / (len(students) * conducted)) * 100, 1)

            subject_stats.append({ "id": sub_id, "subject": subject.name, "teacher": teacher_name, "conducted": conducted, "avg_attendance": avg_sub_att })

        defaulters = []
        top_students = []
        total_class_sessions = (db.session.query(SessionLog).join(WeeklySchedule).filter(WeeklySchedule.section_id == class_managed.section_id, SessionLog.status == 'Conducted').count())

        if total_class_sessions > 0:
            for s in students:
                attended = AttendanceTransaction.query.filter(AttendanceTransaction.student_id == s.student_id, AttendanceTransaction.status.in_(['Present', 'OnDuty'])).count()
                perc = round((attended / total_class_sessions) * 100, 1)
                s_data = { "name": s.full_name, "roll": s.admission_number, "perc": perc, "attended": attended, "total": total_class_sessions }
                if perc < 75: defaulters.append(s_data)
                if perc > 90: top_students.append(s_data)

        pending_leaves_count = LeaveApplication.query.join(StudentProfile).filter(StudentProfile.current_section_id == class_managed.section_id, LeaveApplication.status == 'Pending_CT').count()

        return jsonify({
            "class_info": { "name": f"{class_managed.class_level} - {class_managed.name}", "total_students": len(students), "total_sessions": total_class_sessions },
            "summary": { "defaulter_count": len(defaulters), "pending_leaves": pending_leaves_count, "class_health": "Good" if len(defaulters) < (len(students)*0.2) else "At Risk" },
            "subjects": subject_stats,
            "defaulters": sorted(defaulters, key=lambda x: x['perc']),
            "top_students": sorted(top_students, key=lambda x: x['perc'], reverse=True)[:5]
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
                att = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(valid_sids), AttendanceTransaction.student_id==s.student_id, AttendanceTransaction.status.in_(['Present', 'OnDuty'])).count() if cond > 0 else 0
                
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
def get_attendance_sheet():
    try:
        schedule_id = request.args.get('schedule_id')
        date_str = request.args.get('date')
        if date_str: target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else: target_date = date.today()
        
        slot = WeeklySchedule.query.get(schedule_id)
        if not slot: return jsonify({"error": "Invalid Slot ID"}), 404
        subject = Subject.query.get(slot.subject_id)
        section = ClassSection.query.get(slot.section_id)
        
        # 1. Fetch Students (Batch or Class)
        students = []
        if slot.target_batch:
            target_batch_obj = MentorBatch.query.filter_by(section_id=section.section_id, batch_name=slot.target_batch).first()
            if target_batch_obj: students = StudentProfile.query.filter_by(current_section_id=section.section_id, mentor_batch_id=target_batch_obj.batch_id).all()
        else: 
            students = StudentProfile.query.filter_by(current_section_id=section.section_id).all()
        
        # 2. Check Existing Session (Locked State)
        existing_session = SessionLog.query.filter_by(schedule_id=schedule_id, session_date=target_date).first()
        is_locked = True if existing_session else False
        saved_status_map = {t.student_id: t.status for t in AttendanceTransaction.query.filter_by(session_id=existing_session.session_id).all()} if existing_session else {}

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
        
        display_class_name = f"{section.class_level}-{section.name}"
        if slot.target_batch: display_class_name += f" ({slot.target_batch})"
        time_str = f"{slot.start_time.strftime('%I:%M %p')} - {slot.end_time.strftime('%I:%M %p')}"
        
        return jsonify({ 
            "subject_name": subject.name, "class_name": display_class_name, 
            "time": time_str, "date_display": target_date.strftime('%d %b %Y'), 
            "is_locked": is_locked, "students": student_list, "subject_id": subject.subject_id 
        })

    except Exception as e:
        print(f"CRITICAL ERROR in get_attendance_sheet: {str(e)}")
        return jsonify({"error": str(e)}), 500



@app.route('/api/attendance/submit', methods=['POST'])
def submit_attendance():
    try:
        data = request.json
        schedule_id = data.get('schedule_id')
        txn_date = datetime.strptime(data.get('date'), '%Y-%m-%d').date()

        submitted_by = data.get('submitted_by')

        # 1. Lesson Data (NEW)
        topic_id = data.get('topic_id') # Optional

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
        db.session.add(session); db.session.flush()

        for s in data.get('students'):
            final_status = "OnDuty" if s['is_on_duty'] else s['status']
            new_txn = AttendanceTransaction(session_id=session.session_id, student_id=s['student_id'], status=final_status)
            db.session.add(new_txn)

        # 5. Save Lesson Log (NEW)
        if topic_id:
            db.session.add(LessonLog(session_id=session.session_id, plan_id=topic_id, remarks="Conducted"))

        db.session.commit()
        return jsonify({"message": "Attendance Saved"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500



@app.route('/api/staff/session_history', methods=['GET'])
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
                AttendanceTransaction.status.in_(['Present', 'OnDuty'])
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
# API: LEAVE & STUDENT
# ==========================================
@app.route('/api/staff/leave_requests', methods=['GET'])
def get_staff_leave_requests():
    user_id = request.args.get('user_id')
    class_managed = ClassSection.query.filter_by(class_teacher_id=user_id).first()
    dept_managed = Department.query.filter_by(hod_staff_id=user_id).first()
    pending_leaves = []
    if class_managed:
        ct_requests = (db.session.query(LeaveApplication, StudentProfile, ClassSection).join(StudentProfile, LeaveApplication.student_id == StudentProfile.student_id).join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id).filter(ClassSection.section_id == class_managed.section_id).filter(LeaveApplication.status == 'Pending_CT').all())
        for leave, student, section in ct_requests: pending_leaves.append({ "leave_id": leave.leave_id, "student_name": student.full_name, "roll_no": student.admission_number, "class_name": f"{section.class_level}-{section.name}", "leave_type": leave.leave_type or "General", "days": leave.total_days, "date_range": f"{leave.start_date.strftime('%d %b')} - {leave.end_date.strftime('%d %b')}", "reason": leave.reason, "role_context": "Class Teacher" })
    if dept_managed:
        hod_requests = (db.session.query(LeaveApplication, StudentProfile, ClassSection).join(StudentProfile, LeaveApplication.student_id == StudentProfile.student_id).join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id).filter(LeaveApplication.status == 'Pending_HOD').all())
        for leave, student, section in hod_requests: pending_leaves.append({ "leave_id": leave.leave_id, "student_name": student.full_name, "roll_no": student.admission_number, "class_name": f"{section.class_level}-{section.name}", "leave_type": leave.leave_type or "Long Leave", "days": leave.total_days, "date_range": f"{leave.start_date.strftime('%d %b')} - {leave.end_date.strftime('%d %b')}", "reason": leave.reason, "role_context": "HOD Approval" })
    return jsonify({"requests": pending_leaves})

@app.route('/api/staff/leave_action', methods=['POST'])
def staff_leave_action():
    try:
        data = request.json
        leave = LeaveApplication.query.get(data.get('leave_id'))
        if not leave: return jsonify({"error": "Leave not found"}), 404
        leave.status = data.get('action')
        
        # NOTIFY STUDENT
        msg_type = "success" if leave.status == "Approved" else "danger"
        send_notification(leave.student_id, f"Leave {leave.status}", f"Your leave request has been {leave.status}.", msg_type)
        
        db.session.commit()
        return jsonify({"message": f"Leave {data.get('action')}"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/student/dashboard', methods=['GET'])
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
                    AttendanceTransaction.status.in_(['Present', 'OnDuty'])
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
            "term_grant": grant_data # <--- NEW FIELD
        })

    except Exception as e:
        print(f"CRITICAL ERROR in Student Dashboard: {e}")
        import traceback
        traceback.print_exc()
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


# In app.py

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
#                     AttendanceTransaction.status.in_(['Present', 'OnDuty'])
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
                        txn = AttendanceTransaction.query.filter_by(session_id=sess_id, student_id=student_id).filter(AttendanceTransaction.status.in_(['Present', 'OnDuty'])).first()
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

# In app.py

# In app.py

@app.route('/api/parent/dashboard', methods=['GET'])
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
# API: ADMIN APIs
# ==========================================
@app.route('/api/admin/dashboard', methods=['GET'])
def get_admin_stats():
    try:
        today = date.today()
        
        # 1. Students (Active Only)
        total_students = (db.session.query(StudentProfile)
                          .join(UserMaster, StudentProfile.student_id == UserMaster.user_id)
                          .filter(UserMaster.is_active == True)
                          .count())
        
        # 2. Staff (Active Only, Excluding System Admin)
        total_staff = (db.session.query(StaffProfile)
                       .join(UserMaster, StaffProfile.staff_id == UserMaster.user_id)
                       .filter(UserMaster.is_active == True)
                       .filter(StaffProfile.full_name != "System Administrator")
                       .count())
                       
        # 3. Classes
        total_classes = ClassSection.query.count()
        
        # 4. Attendance Rate (Today)
        attendance_rate = 0
        total_sessions = SessionLog.query.filter_by(session_date=today).count()
        if total_sessions > 0:
            total_presents = (db.session.query(AttendanceTransaction)
                              .join(SessionLog)
                              .filter(SessionLog.session_date == today)
                              .filter(AttendanceTransaction.status.in_(['Present', 'OnDuty']))
                              .count())
            
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
@app.route('/api/admin/classes', methods=['GET'])
def get_admin_classes():
    try:
        classes = db.session.query(ClassSection, StaffProfile).outerjoin(StaffProfile, ClassSection.class_teacher_id == StaffProfile.staff_id).all()
        class_list = [{ "section_id": c.section_id, "name": c.name, "display_name": f"{c.class_level} - {c.name}", "teacher_id": c.class_teacher_id, "teacher_name": t.full_name if t else "Not Assigned" } for c, t in classes]
        all_staff = StaffProfile.query.with_entities(StaffProfile.staff_id, StaffProfile.full_name).order_by(StaffProfile.full_name).all()
        return jsonify({ "classes": class_list, "staff_directory": [{"id": s.staff_id, "name": s.full_name} for s in all_staff] })
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/assign_teacher', methods=['POST'])
def assign_class_teacher():
    try:
        user, err = _require_role('Admin')
        if err: return err
        data = request.json
        section = db.session.get(ClassSection, data.get('section_id'))
        if not section: return jsonify({"error": "Class not found"}), 404
        section.class_teacher_id = data.get('staff_id')
        db.session.commit()
        log_activity("Role Update", f"Assigned Class Teacher for {section.class_level}-{section.name}")
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        app.logger.exception("assign_class_teacher failed")
        return jsonify({"error": "Server error"}), 500

@app.route('/api/admin/coordinators', methods=['GET'])
def get_all_staff_coordinators():
    try:
        staff_list = (db.session.query(StaffProfile, Department).outerjoin(Department, StaffProfile.primary_department_id == Department.dept_id).all())
        result = []
        for staff, dept in staff_list:
            result.append({ "id": staff.staff_id, "name": staff.full_name, "emp_code": staff.employee_code, "dept": dept.name if dept else "N/A", "is_coordinator": staff.is_event_coordinator, "is_amc_member": staff.is_amc_member, "is_amc_head": staff.is_amc_head })
        return jsonify({"staff": result})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/toggle_role', methods=['POST'])
def toggle_staff_role():
    try:
        user, err = _require_role('Admin')
        if err: return err
        data = request.json
        staff_id = data.get('staff_id') if data else None
        if staff_id is None:
            return jsonify({"error": "staff_id is required"}), 400
        staff = db.session.get(StaffProfile, staff_id)
        role = data.get('role_type') if data else None
        if not staff: return jsonify({"error": "Staff not found"}), 404
        
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
    except Exception as e:
        app.logger.exception("toggle_staff_role failed")
        return jsonify({"error": "Server error"}), 500

@app.route('/api/admin/faculty_list', methods=['GET'])
def get_admin_faculty_list():
    try:
        data = (db.session.query(StaffProfile, UserMaster, Department)
                .join(UserMaster, StaffProfile.staff_id == UserMaster.user_id)
                .outerjoin(Department, StaffProfile.primary_department_id == Department.dept_id)
                .all())
        
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
        present_txns = AttendanceTransaction.query.filter(AttendanceTransaction.session_id.in_(session_ids), AttendanceTransaction.status.in_(['Present', 'OnDuty'])).count()
        avg_att = round((present_txns / total_txns) * 100, 1) if total_txns > 0 else 0

        # 3. BEST PERFORMING CLASS (Attendance Based)
        # Map SectionID -> {total, present}
        class_perf_map = {}
        for sess, slot, sec in sessions:
            if sec.name not in class_perf_map: class_perf_map[sec.name] = {'total': 0, 'present': 0, 'level': sec.class_level}
            
            # Get txns for this specific session
            s_txns = AttendanceTransaction.query.filter_by(session_id=sess.session_id).count()
            s_pres = AttendanceTransaction.query.filter_by(session_id=sess.session_id).filter(AttendanceTransaction.status.in_(['Present', 'OnDuty'])).count()
            
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
            AttendanceTransaction.status.in_(['Present', 'OnDuty'])
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
                .filter(AttendanceTransaction.status.in_(['Present', 'OnDuty']))
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
def add_single_faculty():
    try:
        data = request.json
        email = data.get('email')
        if UserMaster.query.filter_by(username=email).first(): return jsonify({"error": "Email exists"}), 400
        
        new_uuid = str(uuid.uuid4())
        db.session.add(UserMaster(user_id=new_uuid, username=email, password_hash=generate_password_hash("Staff@123"), user_type='Staff', is_active=True))
        
        dept = Department.query.filter_by(name=data.get('dept')).first()
        if not dept: dept = Department(name=data.get('dept')); db.session.add(dept); db.session.flush()
        
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
    except Exception as e:
        app.logger.exception("add_faculty failed")
        return jsonify({"error": "Server error"}), 500

@app.route('/api/admin/archive_faculty', methods=['POST'])
def archive_faculty():
    try:
        admin, err = _require_role('Admin')
        if err: return err
        data = request.json
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        user = db.session.get(UserMaster, user_id)
        staff = db.session.get(StaffProfile, user_id)
        if not user: return jsonify({"error": "User not found"}), 404
        user.is_active = (data.get('action') == 'activate')
        if data.get('action') == 'archive':
            classes = ClassSection.query.filter_by(class_teacher_id=user.user_id).all()
            for cls in classes: cls.class_teacher_id = None
        db.session.commit()
        staff_name = staff.full_name if staff else data.get('user_id')
        log_activity("Faculty Status", f"{data.get('action').title()}d {staff_name}")
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        app.logger.exception("archive_faculty failed")
        return jsonify({"error": "Server error"}), 500


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
def generate_timetable():
    try:
        # 1. Clear Old Schedule
        db.session.query(WeeklySchedule).delete()
        db.session.commit()

        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        time_slots = get_time_slots()
        
        faculty_daily_load = {} 
        schedule_log = []
        failed_items = []

        sections = ClassSection.query.all()

        for section in sections:
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

                            # Conflict Check
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
                                        room_id=assigned_room.room_id
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
        
        full_log = schedule_log + ["--- FAILED ITEMS ---"] + failed_items
        return jsonify({"message": "Generated", "logs": full_log}), 200

    except Exception as e:
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
def get_class_possible_electives():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID required"}), 400

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
def get_all_active_electives():
    try:
        # 1. Find all sections that have ANY elective offering 'Open'
        active_section_ids = db.session.query(ElectiveOffering.section_id).filter_by(status='Open').distinct().all()
        active_section_ids = [i[0] for i in active_section_ids]
        
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
def get_student_directory():
    try:
        results = (db.session.query(StudentProfile, ClassSection).outerjoin(ClassSection, StudentProfile.current_section_id == ClassSection.section_id).order_by(ClassSection.class_level, ClassSection.name, StudentProfile.full_name).all())
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
def update_student_status():
    try:
        data = request.json
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
def get_batches():
    try:
        section_id = request.args.get('section_id')
        batches = MentorBatch.query.filter_by(section_id=section_id).all()
        batch_data = []
        for b in batches:
            mentor = StaffProfile.query.get(b.mentor_id) if b.mentor_id else None
            count = StudentProfile.query.filter_by(mentor_batch_id=b.batch_id).count()
            batch_data.append({ "id": b.batch_id, "name": b.batch_name, "mentor_name": mentor.full_name if mentor else "Unassigned", "student_count": count })
        return jsonify({"batches": batch_data})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/delete_batch', methods=['POST'])
def delete_batch():
    try:
        batch_id = request.json.get('batch_id')
        batch = MentorBatch.query.get(batch_id)
        if not batch: return jsonify({"error": "Batch not found"}), 404
        
        # Unlink students
        students = StudentProfile.query.filter_by(mentor_batch_id=batch_id).all()
        for s in students: s.mentor_batch_id = None
        
        db.session.delete(batch)
        db.session.commit()
        return jsonify({"message": "Batch removed, students unassigned"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/assign_mentors', methods=['POST'])
def assign_mentors():
    try:
        data = request.json
        section_id = data.get('section_id')
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
def get_mentor_hierarchy():
    try:
        # 1. Fetch all Classes
        classes = ClassSection.query.order_by(ClassSection.class_level, ClassSection.name).all()
        
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
def auto_split_batches():
    try:
        data = request.json
        section_id = data.get('section_id')
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
def get_my_mentees():
    try:
        user_id = request.args.get('user_id')
        my_batches = MentorBatch.query.filter_by(mentor_id=user_id).all()
        
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
                attended = AttendanceTransaction.query.filter(AttendanceTransaction.student_id == s.student_id, AttendanceTransaction.status.in_(['Present', 'OnDuty'])).count()
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
def get_system_logs():
    try:
        logs = SystemLog.query.order_by(SystemLog.timestamp.desc()).limit(10).all()
        log_data = []
        for log in logs:
            diff = datetime.now() - log.timestamp
            time_ago = "Just now"
            if diff.days > 0: time_ago = f"{diff.days} days ago"
            elif diff.seconds > 3600: time_ago = f"{diff.seconds//3600}h ago"
            elif diff.seconds > 60: time_ago = f"{diff.seconds//60}m ago"
            
            icon = "activity"; color = "bg-gray-100 text-gray-600"
            if "Import" in log.action_type: icon="upload"; color="bg-blue-50 text-blue-600"
            elif "Role" in log.action_type: icon="shield"; color="bg-green-50 text-green-600"
            elif "Faculty" in log.action_type: icon="user-x"; color="bg-red-50 text-red-600"
            elif "Promotion" in log.action_type: icon="trending-up"; color="bg-yellow-50 text-yellow-600"
            
            log_data.append({ "action": log.action_type, "desc": log.description, "time": time_ago, "icon": icon, "color": color })
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
                present = AttendanceTransaction.query.filter_by(session_id=session.session_id).filter(AttendanceTransaction.status.in_(['Present', 'OnDuty'])).count()
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
def get_batch_stats():
    try:
        levels = ['FY', 'SY', 'TY', 'LY']
        stats = []
        for lvl in levels:
            count = (db.session.query(StudentProfile).join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id).filter(ClassSection.class_level == lvl).filter(StudentProfile.academic_status == 'Active').count())
            batches = (db.session.query(StudentProfile.batch).join(ClassSection).filter(ClassSection.class_level == lvl).distinct().all())
            batch_names = [b[0] for b in batches if b[0]]
            stats.append({ "level": lvl, "count": count, "batches": ", ".join(batch_names) })
        return jsonify({"stats": stats})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/promote_batch', methods=['POST'])
def promote_batch():
    try:
        data = request.json
        from_lvl = data.get('from_level')
        to_lvl = data.get('to_level')
        
        # 1. Find Students to Promote
        students_to_promote = (db.session.query(StudentProfile, ClassSection)
                               .join(ClassSection, StudentProfile.current_section_id == ClassSection.section_id)
                               .filter(ClassSection.class_level == from_lvl)
                               .filter(StudentProfile.academic_status == 'Active')
                               .all())
        
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
            target_sections = ClassSection.query.filter_by(class_level=to_lvl).all()
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
def get_allocation_data():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID required"}), 400
        
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
def get_faculty_load_list():
    try:
        section_id = request.args.get('section_id')
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
            available_subjects = query.order_by(Subject.name).all()
        else:
            available_subjects = Subject.query.order_by(Subject.name).all()
            
        subject_list = [{"id": s.subject_id, "name": s.name, "code": s.code} for s in available_subjects]
        return jsonify({"faculty": staff_list, "subjects": subject_list})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/save_allocation', methods=['POST'])
def save_allocation():
    try:
        data = request.json
        existing = SubjectAllocation.query.filter_by(section_id=data.get('section_id'), subject_id=data.get('subject_id')).first()
        if existing: existing.teacher_id = data.get('staff_id'); msg = "Updated"
        else: db.session.add(SubjectAllocation(section_id=data.get('section_id'), subject_id=data.get('subject_id'), teacher_id=data.get('staff_id'))); msg = "Assigned"
        db.session.commit()
        return jsonify({"message": msg}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/admin/get_class_schedule', methods=['GET'])
def get_class_schedule():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID missing"}), 400
        
        # 1. Get Time Slots (Existing)
        slots = (db.session.query(WeeklySchedule, Subject, StaffProfile, RoomMaster)
                 .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                 .join(StaffProfile, WeeklySchedule.teacher_id == StaffProfile.staff_id)
                 .outerjoin(RoomMaster, WeeklySchedule.room_id == RoomMaster.room_id)
                 .filter(WeeklySchedule.section_id == section_id)
                 .all())
                 
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


# In app.py

@app.route('/api/admin/course_structure', methods=['GET'])
def get_course_structure():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID missing"}), 400

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
        
        # 1. Identify Target IDs (User + Linked Student if Parent)
        target_ids = [user_id]
        
        # Check if this user is a Parent
        student = StudentProfile.query.filter_by(parent_user_id=user_id).first()
        if student:
            target_ids.append(student.student_id)
            
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
            
            # Add a visual indicator if it's for the student
            prefix = ""
            if student and n.user_id == student.student_id:
                prefix = f"[{student.full_name.split()[0]}] "
            
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

            # Parent users can see their linked student's notifications too; clear both.
            target_ids = [user_id]
            student = StudentProfile.query.filter_by(parent_user_id=user_id).first()
            if student:
                target_ids.append(student.student_id)

            Notification.query.filter(Notification.user_id.in_(target_ids), Notification.is_read == False).update({'is_read': True})
        else:
            n = Notification.query.get(notif_id)
            if n: n.is_read = True
        db.session.commit()
        return jsonify({"message": "Updated"}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# ==========================================
# UPLOAD APIs
# ==========================================
@app.route('/api/upload/master_dept_subject', methods=['POST'])
def upload_dept_subject():
    try:
        file = get_db_file_handle(request); df = pd.read_csv(file, dtype=str)
        unique_depts = df['Department Name'].dropna().unique()
        for dept_name in unique_depts:
            if not Department.query.filter_by(name=str(dept_name).strip()).first(): db.session.add(Department(name=str(dept_name).strip()))
        db.session.commit()
        for _, row in df.iterrows():
            dept = Department.query.filter_by(name=str(row['Department Name']).strip()).first()
            if dept and not Subject.query.filter_by(code=str(row['Subject Code']).strip()).first():
                db.session.add(Subject(name=str(row['Subject Name']).strip(), code=str(row['Subject Code']).strip(), dept_id=dept.dept_id))
        db.session.commit()
        log_activity("Bulk Import", "Uploaded Departments & Subjects")
        return jsonify({"message": "Uploaded"}), 201
    except Exception as e: return jsonify({"error": str(e)}), 400

@app.route('/api/upload/master_class', methods=['POST'])
def upload_classes():
    try:
        file = get_db_file_handle(request); df = pd.read_csv(file, dtype=str)
        count = 0
        for _, row in df.iterrows():
            if not ClassSection.query.filter_by(class_level=str(row['Class Level']).strip(), name=str(row['Section Name']).strip()).first():
                db.session.add(ClassSection(class_level=str(row['Class Level']).strip(), name=str(row['Section Name']).strip())); count += 1
        db.session.commit()
        log_activity("Bulk Import", f"Created {count} Class Sections")
        return jsonify({"message": f"{count} created"}), 201
    except Exception as e: return jsonify({"error": str(e)}), 400


@app.route('/api/upload/semester_course_structure', methods=['POST'])
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

            section = ClassSection.query.filter_by(class_level=class_level, name=section_name).first()
            if not section:
                skipped_rows += 1
                errors.append(f"Row {idx+2}: Class section '{class_level}-{section_name}' not found")
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

            section = ClassSection.query.filter_by(class_level=class_level, name=section_name).first()
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

    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/api/upload/staff', methods=['POST'])
def upload_staff():
    try:
        file = get_db_file_handle(request); df = pd.read_csv(file)
        count = 0
        for _, row in df.iterrows():
            if UserMaster.query.filter_by(username=row['Email']).first(): continue
            
            new_uuid = str(uuid.uuid4())
            # Create Login
            db.session.add(UserMaster(
                user_id=new_uuid, 
                username=row['Email'], 
                password_hash=generate_password_hash("Staff@123"), 
                user_type=row.get('Role', 'Staff'), 
                is_active=True
            ))
            
            # Handle Dept
            d_name = str(row['Department Name']).strip()
            dept = Department.query.filter_by(name=d_name).first()
            if not dept: 
                dept = Department(name=d_name)
                db.session.add(dept); db.session.flush()
            
            # Create Profile with Designation
            # Default to 'Assistant Professor' if column missing in CSV
            desig = row.get('Designation').strip()
            
            db.session.add(StaffProfile(
                staff_id=new_uuid, 
                full_name=row['Full Name'], 
                employee_code=str(row['Employee Code']).strip(), 
                email_contact=row['Email'], 
                primary_department_id=dept.dept_id,
                designation=desig # <--- SAVING HERE
            ))
            count += 1
            
        db.session.commit()
        log_activity("Bulk Import", f"Onboarded {count} Staff Members")
        return jsonify({"message": "Staff uploaded"}), 201
    except Exception as e: return jsonify({"error": str(e)}), 400

@app.route('/api/upload/students', methods=['POST'])
def upload_students():
    try:
        file = get_db_file_handle(request)
        df = pd.read_csv(file, dtype=str).fillna('')
        
        count = 0
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
                    # Create New Parent User
                    parent_uuid = str(uuid.uuid4())
                    db.session.add(UserMaster(
                        user_id=parent_uuid, 
                        username=parent_phone, 
                        password_hash=generate_password_hash("Parent@123"), 
                        user_type='Parent', 
                        is_active=True
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

            # 2. Create Student
            if not StudentProfile.query.filter_by(admission_number=str(row['Admission Number'])).first():
                student_uuid = str(uuid.uuid4())
                c_level = str(row['Class Level']).strip()
                c_sec = str(row['Section Name']).strip()
                
                section = ClassSection.query.filter_by(class_level=c_level, name=c_sec).first()
                
                # A. Create Student Login
                db.session.add(UserMaster(
                    user_id=student_uuid, 
                    username=row['Student Email'] or f"{row['Admission Number']}@school.mituniversity.edu.in", 
                    password_hash=generate_password_hash("Student@123"), 
                    user_type='Student', 
                    is_active=True
                ))
                
                # --- FIX: Force DB to recognize UserMaster BEFORE creating Profile ---
                db.session.flush() 
                # -------------------------------------------------------------------

                # B. Create Student Profile
                db.session.add(StudentProfile(
                    student_id=student_uuid, 
                    full_name=row['Student Full Name'], 
                    admission_number=str(row['Admission Number']), 
                    parent_user_id=parent_uuid, 
                    current_section_id=section.section_id if section else None,
                    batch=str(row['Batch']).strip() if 'Batch' in row else None
                ))
                count += 1
        
        db.session.commit()
        log_activity("Bulk Import", f"Enrolled {count} Students")
        return jsonify({"message": f"Successfully enrolled {count} students."}), 201

    except Exception as e:
        db.session.rollback() # Important: Rollback if anything fails
        return jsonify({"error": str(e)}), 500

@app.route('/api/upload/schedule', methods=['POST'])
def upload_schedule():
    try:
        file = get_db_file_handle(request)
        df = pd.read_csv(file, dtype=str).fillna('')
        
        # Optional: Clear existing schedule before upload to prevent duplicates
        # db.session.query(WeeklySchedule).delete()
        # db.session.commit()
        
        success = 0
        errors = []
        
        for index, row in df.iterrows():
            # 1. Basic Lookups
            subject = Subject.query.filter_by(code=str(row['Subject Code']).strip()).first()
            teacher = StaffProfile.query.filter_by(employee_code=str(row['Employee Code']).strip()).first()
            section = ClassSection.query.filter_by(
                class_level=str(row['Class Level']).strip(), 
                name=str(row['Section Name']).strip()
            ).first()
            
            if not subject or not teacher or not section: 
                errors.append(f"Row {index}: Data missing (Subject/Teacher/Class not found)")
                continue

            # 2. Parse Times
            start = parse_flexible_time(row['Start Time'])
            end = parse_flexible_time(row['End Time'])
            if not start or not end: 
                errors.append(f"Row {index}: Invalid Time Format")
                continue

            # 3. Parse Metadata (Type, Batch, Room)
            sess_type = str(row.get('Session Type', 'Lecture')).strip()
            
            raw_batch = str(row.get('Batch', '')).strip()
            target_batch = raw_batch if raw_batch else None
            
            # Room Lookup
            room_num = str(row.get('Room Number', '')).strip()
            room = RoomMaster.query.filter_by(room_number=room_num).first()
            room_id = room.room_id if room else None

            # 4. Save Slot
            new_slot = WeeklySchedule(
                section_id=section.section_id, 
                subject_id=subject.subject_id, 
                teacher_id=teacher.staff_id, 
                day_of_week=str(row['Day']).strip(), 
                start_time=start, 
                end_time=end,
                session_type=sess_type,
                target_batch=target_batch,
                room_id=room_id # <--- Saved from CSV
            )
            db.session.add(new_slot)
            success += 1
            
        db.session.commit()
        log_activity("Bulk Import", f"Uploaded Weekly Schedule ({success} slots).")
        return jsonify({"message": f"{success} slots created", "errors": errors}), 201
    except Exception as e: 
        return jsonify({"error": str(e)}), 500
    

@app.route('/api/upload/assign_class_teachers', methods=['POST'])
def upload_class_teachers():
    try:
        file = get_db_file_handle(request); df = pd.read_csv(file, dtype=str)
        success = 0; errors = []
        for index, row in df.iterrows():
            cls = ClassSection.query.filter_by(class_level=row['Class Level'].strip(), name=row['Section Name'].strip()).first()
            user = UserMaster.query.filter_by(username=row['Teacher Email'].strip()).first()
            if not cls or not user: errors.append(f"Row {index}: Data mismatch"); continue
            staff = StaffProfile.query.get(user.user_id)
            if staff: cls.class_teacher_id = staff.staff_id; success += 1
        db.session.commit()
        log_activity("Role Update", f"Bulk Assigned {success} Class Teachers")
        return jsonify({"message": f"{success} assigned"}), 201
    except Exception as e: return jsonify({"error": str(e)}), 500



# In app.py

# ==========================================
# API: MENTOR LOGGING
# ==========================================

# In app.py

# ==========================================
# API: MENTOR MEETING SCHEDULER
# ==========================================

@app.route('/api/mentor/schedule_meeting', methods=['POST'])
def schedule_mentor_meeting():
    try:
        data = request.json
        mentor_id = data.get('mentor_id')
        batch_id = data.get('batch_id')
        
        # 1. Count existing meetings
        count = MentorMeeting.query.filter_by(batch_id=batch_id).count()
        if count >= 4:
            return jsonify({"error": "Maximum 4 mandatory meetings already scheduled."}), 400

        # 2. Create Meeting
        date_obj = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
        time_obj = datetime.strptime(data.get('time'), '%H:%M').time()
        
        meeting = MentorMeeting(
            mentor_id=mentor_id,
            batch_id=batch_id,
            date=date_obj,
            time=time_obj,
            agenda=data.get('agenda'),
            status='Scheduled'
        )

        students = StudentProfile.query.filter_by(mentor_batch_id=data.get('batch_id')).all()
        for s in students:
            send_notification(s.student_id, "New Mentor Meeting", f"Meeting scheduled on {data.get('date')} for {data.get('agenda')}.", "info")
        db.session.add(meeting)
        db.session.commit()
        
        return jsonify({"message": "Meeting scheduled successfully."}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/mentor/get_meetings', methods=['GET'])
def get_mentor_meetings():
    try:
        batch_id = request.args.get('batch_id')
        
        meetings = MentorMeeting.query.filter_by(batch_id=batch_id).order_by(MentorMeeting.date).all()
        
        meeting_list = []
        for m in meetings:
            meeting_list.append({
                "id": m.meeting_id,
                "date": m.date.strftime('%d %b %Y'),
                "time": m.time.strftime('%I:%M %p'),
                "agenda": m.agenda,
                "status": m.status
            })
            
        return jsonify({"meetings": meeting_list, "count": len(meetings)})
    except Exception as e: return jsonify({"error": str(e)}), 500


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
def upload_subject_allocation():
    try:
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

            section = ClassSection.query.filter_by(class_level=class_level, name=section_name).first()
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
            section_name = row.get('Section', '').strip()
            class_level = row.get('Class Level', '').strip()
            sem_raw = str(row.get('SEM', '')).strip()

            semester_no = parse_semester_no(sem_raw)
            
            # 2. Resolve Subject (allocation must not create/overwrite structure)
            subject = Subject.query.filter_by(code=course_code).first()
            if not subject:
                skipped_list.append(f"Row {index+2}: Subject '{course_code}' not found. Upload Semester Course Structure first.")
                continue

            # 3. Resolve Class Section
            section = ClassSection.query.filter_by(class_level=class_level, name=section_name).first()
            if not section:
                skipped_list.append(f"Row {index+2}: Class '{class_level}-{section_name}' not found.")
                continue

            # 3b. Enforce structure existence per (section, sem, subject)
            struct = (SemesterCourseStructure.query
                      .filter_by(section_id=section.section_id, semester_no=semester_no, subject_id=subject.subject_id)
                      .first())
            if not struct:
                skipped_list.append(
                    f"Row {index+2}: No SemesterCourseStructure for '{class_level}-{section_name}', Sem {semester_no}, Course '{course_code}'."
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
        dept_name = "Department of Information Technology"
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
                    if status in ['Present', 'OnDuty']:
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
        # We assume get_students_by_section logic logic or recalculate here
        # For batch calculation, we'll do a quick loop
        
        total_sessions = db.session.query(SessionLog).join(WeeklySchedule).filter(WeeklySchedule.section_id == section_id, SessionLog.status=='Conducted').count()
        
        count = 0
        for s in students:
            # A. Attendance %
            # Note: This is global class attendance. For batch-specific accuracy, we'd need the detailed logic.
            # Using simple global approximation for speed in this demo block:
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


# In app.py

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

# ADMIN SETUP
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

        # Strict behavior: only an active cycle within its configured window is visible to students.
        # Enforce that when Admin activates a cycle.
        if is_active:
            today = date.today()
            if not (start_date <= today <= end_date):
                return jsonify({"error": "To activate a cycle, today's date must fall between start and end dates."}), 400

        # Deactivate others? Maybe not necessary if dates don't overlap, but safe practice.
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

        # Total students per section (Active only)
        # Submitted students per section = distinct students who submitted at least one subject in this cycle.
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



# In app.py

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
        # Helpful for fresh databases where migrations haven't been applied yet.
        if 'no such table' in str(e).lower():
            db.create_all()
            return _impl()
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/rollover_semester', methods=['POST'])
def rollover_semester():
    def _impl():
        # 1. Get Current Term Name to tag the archive
        conf = SystemConfig.query.get('current_term')
        old_term = conf.value if conf else get_current_term_name()

        # 2. Archive Allocations
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

        # 3. Archive Schedule
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

        # 4. FLUSH Active Tables
        # We delete all rows to reset the system for the new term
        db.session.query(WeeklySchedule).delete()
        db.session.query(SubjectAllocation).delete()
        db.session.query(StudentElective).delete()  # Reset elective choices
        db.session.query(ElectiveOffering).delete()  # Reset offerings

        # Note: We DO NOT delete Students, Classes, or Staff. They stay.

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


@app.route('/api/hod/feedback_analysis', methods=['GET'])
def get_hod_feedback_analysis():
    try:
        user_id = request.args.get('user_id')
        
        # 1. Identify HOD's Department
        dept = Department.query.filter_by(hod_staff_id=user_id).first()
        if not dept:
            # Fallback for Single Dept Mode
            dept = Department.query.filter_by(name=FIXED_DEPT_NAME).first()
            
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

        # 3. Subject-wise Analysis (Class-Division Wise)
        # FIX: Join ClassSection and Group By it
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
                       .join(ClassSection, FeedbackResponse.section_id == ClassSection.section_id) # <--- Added Join
                       .filter(StaffProfile.primary_department_id == dept.dept_id)
                       .group_by(ClassSection.class_level, ClassSection.name, Subject.name, Subject.code, StaffProfile.full_name)
                       .order_by(ClassSection.class_level, ClassSection.name, Subject.name) # Sorted for display
                       .all())

        subject_analysis = []
        for lvl, sec_name, s_name, s_code, t_name, avg in sub_results:
            subject_analysis.append({
                "class": f"{lvl}-{sec_name}", # <--- New Field
                "subject": s_name,
                "code": s_code,
                "faculty": t_name,
                "score": round(float(avg), 2)
            })

        # Sort faculty by score descending for the chart
        faculty_scores.sort(key=lambda x: x['score'], reverse=True)

        return jsonify({
            "dept_avg": dept_avg,
            "total_responses": total_responses,
            "faculty_scores": faculty_scores,
            "subject_analysis": subject_analysis
        })

    except Exception as e: return jsonify({"error": str(e)}), 500

# In app.py

@app.route('/api/hod/syllabus_status', methods=['GET'])
def get_hod_syllabus_status():
    try:
        section_id = request.args.get('section_id')
        if not section_id: return jsonify({"error": "Section ID required"}), 400
        
        # Get Allocations for this class
        allocations = (db.session.query(SubjectAllocation, Subject, StaffProfile)
                       .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                       .join(StaffProfile, SubjectAllocation.teacher_id == StaffProfile.staff_id)
                       .filter(SubjectAllocation.section_id == section_id)
                       .all())
        
        data = []
        for alloc, sub, teacher in allocations:
            # 1. Total Topics in Plan (Created by this teacher for this subject)
            # Note: Assuming plan is per subject/teacher. 
            total_topics = TeachingPlan.query.filter_by(
                subject_id=sub.subject_id, 
                created_by_id=teacher.staff_id
            ).count()
            
            if total_topics == 0:
                perc = 0
                status_text = "Plan Not Uploaded"
                color = "gray"
            else:
                # 2. Completed Topics for THIS Section
                # Link: LessonLog -> SessionLog -> WeeklySchedule (to check section)
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
                
                # Color Coding
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
    

@app.route('/api/academic/create_plan', methods=['POST'])
def create_teaching_plan():
    try:
        data = request.json
        subject_id = data.get('subject_id')
        teacher_id = data.get('teacher_id')
        topics = data.get('topics') # List of {unit, topic, hours}
        
        # Optional: Clear old plan for this subject? Or append? 
        # Let's append/update based on logic, but for MVP just add new ones.
        
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

        # --- FIX: ROBUST ENCODING HANDLING ---
        try:
            # Try standard UTF-8 first
            df = pd.read_csv(file, dtype=str)
        except UnicodeDecodeError:
            # If failed (e.g., Excel file with special dashes), try Windows-1252
            file.seek(0) # Reset file pointer to start
            df = pd.read_csv(file, dtype=str, encoding='cp1252')
        except Exception:
            # Last resort: Latin-1 (handles almost anything)
            file.seek(0)
            df = pd.read_csv(file, dtype=str, encoding='latin1')
            
        df = df.fillna('')
        # -------------------------------------
        
        # Expected Headers: "Unit", "Sub Unit", "Topic", "Hours"
        count = 0
        
        for index, row in df.iterrows():
            unit = row.get('Unit', '').strip()
            topic = row.get('Topic', '').strip()
            hours = row.get('Hours', '1').strip()
            sub_unit = row.get('Sub Unit', '').strip()
            
            if not unit or not topic: continue
            
            # Create Plan Entry
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
        
        # Fetch Plan
        plans = TeachingPlan.query.filter_by(subject_id=subject_id).order_by(TeachingPlan.unit_number, TeachingPlan.sub_unit).all()
        
        syllabus = []
        total_topics = len(plans)
        completed_topics = 0
        
        # Helper to group hours by unit
        unit_hours = {}

        # First Pass: Calculate Unit Totals
        for p in plans:
            u = p.unit_number
            unit_hours[u] = unit_hours.get(u, 0) + p.planned_hours

        # Second Pass: Build Response
        for p in plans:
            # Check if this topic is logged
            # We join SessionLog to get the date
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
                "conducted_date": conducted_date # <--- NEW FIELD
            })
            
        progress = round((completed_topics / total_topics) * 100) if total_topics > 0 else 0
        
        return jsonify({
            "syllabus": syllabus,
            "progress": progress
        })
    except Exception as e: return jsonify({"error": str(e)}), 500

# In app.py - Add to the AMC section

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


@app.route('/api/amc/syllabus_progress', methods=['GET'])
def get_syllabus_progress():
    try:
        section_id = request.args.get('section_id')
        term = request.args.get('term')  # '1' or '2'
        
        if not section_id or not term:
            return jsonify({"error": "Missing parameters"}), 400

        # Define target units based on term
        target_units = []
        if term == '1': target_units = [1, 2, 3]
        elif term == '2': target_units = [4, 5, 6]

        # Get subjects allocated to this section
        allocations = (db.session.query(SubjectAllocation, Subject, StaffProfile)
                       .join(Subject, SubjectAllocation.subject_id == Subject.subject_id)
                       .join(StaffProfile, SubjectAllocation.teacher_id == StaffProfile.staff_id)
                       .filter(SubjectAllocation.section_id == section_id)
                       .all())

        subjects_data = []
        for alloc, subject, teacher in allocations:
            # Get total topics in target units
            total_topics = (db.session.query(TeachingPlan)
                            .filter(TeachingPlan.subject_id == subject.subject_id)
                            .filter(TeachingPlan.unit_number.in_(target_units))
                            .count())

            # Get completed topics (those with lesson logs)
            completed_topics = (db.session.query(LessonLog)
                                .join(SessionLog, LessonLog.session_id == SessionLog.session_id)
                                .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                                .filter(WeeklySchedule.subject_id == subject.subject_id)
                                .filter(WeeklySchedule.section_id == section_id)
                                .filter(LessonLog.plan_id.isnot(None))
                                .join(TeachingPlan, LessonLog.plan_id == TeachingPlan.plan_id)
                                .filter(TeachingPlan.unit_number.in_(target_units))
                                .count())

            pending_topics = total_topics - completed_topics

            # Last updated: most recent lesson log
            last_log = (db.session.query(LessonLog.created_at)
                        .join(SessionLog, LessonLog.session_id == SessionLog.session_id)
                        .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
                        .filter(WeeklySchedule.subject_id == subject.subject_id)
                        .filter(WeeklySchedule.section_id == section_id)
                        .order_by(LessonLog.created_at.desc())
                        .first())

            last_updated = last_log.created_at if last_log else None

            subjects_data.append({
                "subject_name": subject.name,
                "total_topics": total_topics,
                "completed": completed_topics,
                "pending": pending_topics,
                "last_updated": last_updated.isoformat() if last_updated else None
            })

        return jsonify({"subjects": subjects_data})

    except Exception as e: return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # --- SEED DATA: CREATE SUPER ADMIN & IT DEPARTMENT ---
        admin_email = "admin@mituniversity.edu.in"
        if not UserMaster.query.filter_by(username=admin_email).first():
            print("Creating System Environment...")
            new_uuid = str(uuid.uuid4())
            
            # Create IT Department (Required for many features)
            if not Department.query.filter_by(name="Department of Information Technology").first():
                db.session.add(Department(name="Department of Information Technology"))
            
            seed_password = os.environ.get('ADMIN_SEED_PASSWORD', 'Admin@123')  # Use env var in prod!
            admin_user = UserMaster(user_id=new_uuid, username=admin_email, password_hash=generate_password_hash(seed_password), user_type='Admin', is_active=True)
            db.session.add(admin_user)
            
            admin_profile = StaffProfile(staff_id=new_uuid, full_name="System Administrator", employee_code="ADMIN001", email_contact=admin_email)
            db.session.add(admin_profile)
            
            db.session.commit()
            print(f"Super Admin Created! Login: {admin_email} (password from ADMIN_SEED_PASSWORD or default)")
        else:
            print("Database initialized.")

    # NOTE: In production, use gunicorn. Only use app.run() for local dev.
    # Set FLASK_DEBUG=1 to enable debug mode locally.
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1', port=5000)



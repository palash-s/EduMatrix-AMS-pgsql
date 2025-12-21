import os
import sys
from pathlib import Path
from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import aliased

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import (
    app,
    db,
    Department,
    StaffProfile,
    UserMaster,
    SystemConfig,
    get_current_term_name,
    SessionLog,
    WeeklySchedule,
    Subject,
)


def parse_ay_sem(term: str):
    if not term:
        return None, None
    import re

    m = re.search(r"(\d{4}-\d{2})\s*Sem\s*(\d+)", term, re.I)
    if not m:
        return None, None
    return m.group(1), int(m.group(2))


def date_window(ay: str, sem: int | None):
    start_year = int(ay.split("-")[0])

    # Academic year assumed as Jul -> Jun.
    # Sem 1: Jul-Dec (start_year)
    # Sem 2: Jan-Jun (start_year + 1)
    if sem == 1:
        return date(start_year, 7, 1), date(start_year, 12, 31)
    if sem == 2:
        return date(start_year + 1, 1, 1), date(start_year + 1, 6, 30)
    return date(start_year, 7, 1), date(start_year + 1, 6, 30)


def main():
    user_id = os.environ.get("USER_ID")
    if not user_id:
        raise SystemExit("Set USER_ID env var")

    override_ay = os.environ.get("AY")
    override_sem_raw = os.environ.get("SEM")
    override_sem = None
    if override_sem_raw not in (None, "", "null", "None"):
        try:
            override_sem = int(override_sem_raw)
        except Exception:
            raise SystemExit("SEM must be 1 or 2 (or unset)")
        if override_sem not in (1, 2):
            raise SystemExit("SEM must be 1 or 2 (or unset)")

    with app.app_context():
        user = db.session.get(UserMaster, user_id)
        staff = db.session.get(StaffProfile, user_id)
        dept = Department.query.filter_by(hod_staff_id=user_id).first()

        print("DATABASE_URL:", os.environ.get("DATABASE_URL"))
        print("effective_SQLALCHEMY_DATABASE_URI:", app.config.get("SQLALCHEMY_DATABASE_URI"))
        try:
            print("engine_url:", str(db.engine.url))
        except Exception as e:
            print("engine_url: <unavailable>", str(e))
        print("user_master_exists:", bool(user))
        print("user_type:", getattr(user, "user_type", None))
        print("staff_exists:", bool(staff))
        print("staff_name:", getattr(staff, "full_name", None))
        print("staff_primary_department_id:", getattr(staff, "primary_department_id", None))
        print("hod_department:", (dept.dept_id, dept.name) if dept else None)

        cfg = SystemConfig.query.get('current_term')
        cfg_term = cfg.value if cfg and cfg.value else None
        computed_term = get_current_term_name()
        computed_ay, computed_sem = parse_ay_sem(computed_term)
        print("system_config_current_term:", cfg_term)
        print("computed_current_term:", computed_term)
        print("parsed_academic_year:", computed_ay)
        print("parsed_semester:", computed_sem)

        ay = override_ay or computed_ay
        sem = override_sem if override_sem is not None else computed_sem
        print("effective_academic_year:", ay)
        print("effective_semester:", sem)
        if override_ay or override_sem is not None:
            print("NOTE: Using overrides from env (AY/SEM).")

        if not ay:
            print("No AY parsed; skipping window counts")
            return

        start_date, end_date = date_window(ay, sem)
        print("window:", start_date, "->", end_date)

        global_cnt = (
            db.session.query(SessionLog)
            .filter(SessionLog.session_date >= start_date)
            .filter(SessionLog.session_date <= end_date)
            .filter(SessionLog.status == "Conducted")
            .count()
        )
        print("global_conducted_sessions_in_window:", global_cnt)

        if not dept:
            print("No HOD dept mapping; /api/hod/archive_stats will 403")
            return

        ScheduledTeacher = aliased(StaffProfile)
        ActualTeacher = aliased(StaffProfile)
        dept_cnt = (
            db.session.query(SessionLog)
            .join(WeeklySchedule, SessionLog.schedule_id == WeeklySchedule.schedule_id)
            .join(Subject, Subject.subject_id == WeeklySchedule.subject_id)
            .outerjoin(ScheduledTeacher, WeeklySchedule.teacher_id == ScheduledTeacher.staff_id)
            .outerjoin(ActualTeacher, SessionLog.actual_teacher_id == ActualTeacher.staff_id)
            .filter(
                or_(
                    Subject.dept_id == dept.dept_id,
                    ScheduledTeacher.primary_department_id == dept.dept_id,
                    ActualTeacher.primary_department_id == dept.dept_id,
                )
            )
            .filter(SessionLog.session_date >= start_date)
            .filter(SessionLog.session_date <= end_date)
            .filter(SessionLog.status == "Conducted")
            .count()
        )
        print("dept_matched_sessions_in_window:", dept_cnt)

        sch_rows = (
            db.session.query(WeeklySchedule)
            .outerjoin(ScheduledTeacher, WeeklySchedule.teacher_id == ScheduledTeacher.staff_id)
            .filter(ScheduledTeacher.primary_department_id == dept.dept_id)
            .count()
        )
        print("weekly_schedule_rows_by_dept_faculty:", sch_rows)

        subj_cnt = Subject.query.filter(Subject.dept_id == dept.dept_id).count()
        null_dept_subjects = Subject.query.filter(Subject.dept_id == None).count()
        print("subjects_in_dept:", subj_cnt)
        print("subjects_with_null_dept_id:", null_dept_subjects)


if __name__ == "__main__":
    main()

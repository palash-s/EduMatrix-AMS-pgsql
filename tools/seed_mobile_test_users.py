import uuid
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from werkzeug.security import generate_password_hash

from app import app, db
from sql_connection import ParentProfile, StudentProfile, UserMaster


def main() -> None:
    pwd = "Pass@123"

    with app.app_context():
        # Student
        username_s = "mobile_student@test.com"
        u = UserMaster.query.filter_by(username=username_s).first()
        if not u:
            uid = str(uuid.uuid4())
            u = UserMaster(
                user_id=uid,
                username=username_s,
                password_hash=generate_password_hash(pwd),
                user_type="Student",
                is_active=True,
            )
            db.session.add(u)
            db.session.flush()
            db.session.add(
                StudentProfile(
                    student_id=uid,
                    full_name="Mobile Student",
                    admission_number="MOB001",
                    parent_user_id=None,
                    current_section_id=None,
                )
            )

        # Parent with 2 children
        username_p = "mobile_parent@test.com"
        up = UserMaster.query.filter_by(username=username_p).first()
        if not up:
            pid = str(uuid.uuid4())
            up = UserMaster(
                user_id=pid,
                username=username_p,
                password_hash=generate_password_hash(pwd),
                user_type="Parent",
                is_active=True,
            )
            db.session.add(up)
            db.session.flush()
            db.session.add(
                ParentProfile(
                    parent_id=pid,
                    father_name="Parent",
                    mother_name="Parent",
                    primary_phone="9999999999",
                )
            )

            for i in range(2):
                cid = str(uuid.uuid4())
                su = UserMaster(
                    user_id=cid,
                    username=f"mobile_child{i + 1}@test.com",
                    password_hash=generate_password_hash(pwd),
                    user_type="Student",
                    is_active=True,
                )
                db.session.add(su)
                db.session.flush()
                db.session.add(
                    StudentProfile(
                        student_id=cid,
                        full_name=f"Mobile Child {i + 1}",
                        admission_number=f"MOB00{i + 2}",
                        parent_user_id=pid,
                        current_section_id=None,
                    )
                )

        db.session.commit()

    print("Seeded test users:")
    print(f"  student: {username_s} / {pwd}")
    print(f"  parent : {username_p} / {pwd}")


if __name__ == "__main__":
    main()

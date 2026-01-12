#!/usr/bin/env python3
"""
Test Data Seeder for EduMatrix AMS
Creates test users and data for comprehensive system testing.

Usage:
    python seed_test_data.py
"""

import os
import sys
import uuid
import json
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import app and database
from app import app
from sql_connection import db
from sql_connection import (
    UserMaster, StaffProfile, StudentProfile, ParentProfile,
    Department, ClassSection, Subject, MentorBatch, MDMOfferingPool
)


def load_test_users():
    """Load test users from fixture file."""
    fixture_path = os.path.join(os.path.dirname(__file__), 'tests', 'fixtures', 'test_users.json')
    with open(fixture_path, 'r') as f:
        return json.load(f)


def seed_users(test_users: dict):
    """Create test users in the database."""
    created_users = {}

    print("\n=== Creating Test Users ===")

    for role_key, user_data in test_users.items():
        username = user_data['username']
        password = user_data['password']
        user_type = user_data['user_type']

        # Check if user already exists
        existing = UserMaster.query.filter_by(username=username).first()
        if existing:
            print(f"  [EXISTS] {role_key}: {username}")
            created_users[role_key] = existing.user_id
            continue

        # Create new user
        user_id = str(uuid.uuid4())
        user = UserMaster(
            user_id=user_id,
            username=username,
            password_hash=generate_password_hash(password),
            user_type=user_type,
            is_active=True,
            must_change_password=False
        )
        db.session.add(user)
        created_users[role_key] = user_id
        print(f"  [CREATED] {role_key}: {username} ({user_type})")

    db.session.commit()
    return created_users


def seed_department():
    """Create test department."""
    print("\n=== Creating Test Department ===")

    # Department model uses 'name' column
    dept = Department.query.filter_by(name='Information Technology').first()
    if not dept:
        dept = Department(name='Information Technology')
        db.session.add(dept)
        db.session.commit()
        print(f"  [CREATED] Department: Information Technology")
    else:
        print(f"  [EXISTS] Department: Information Technology")

    return dept.dept_id


def seed_class_section(dept_id: int):
    """Create test class section."""
    print("\n=== Creating Test Class Section ===")

    # ClassSection uses 'name' and 'class_level' columns
    section = ClassSection.query.filter_by(name='DA', class_level='SY').first()
    if not section:
        section = ClassSection(
            class_level='SY',
            name='DA'
        )
        db.session.add(section)
        db.session.commit()
        print(f"  [CREATED] Class Section: SY-DA")
    else:
        print(f"  [EXISTS] Class Section: SY-DA")

    return section.section_id


def seed_staff_profiles(user_ids: dict, dept_id: int, section_id: int):
    """Create staff profiles and assign roles."""
    print("\n=== Creating Staff Profiles ===")

    staff_roles = {
        'hod': {'full_name': 'Dr. HOD Test', 'employee_code': 'EMP1001'},
        'class_teacher': {'full_name': 'Prof. ClassTeacher Test', 'employee_code': 'EMP1002'},
        'mentor': {'full_name': 'Prof. Mentor Test', 'employee_code': 'EMP1003'},
        'event_coordinator': {'full_name': 'Prof. EventCoord Test', 'employee_code': 'EMP1004'},
        'amc_member': {'full_name': 'Prof. AMC Test', 'employee_code': 'EMP1005'},
        'mdm_coordinator': {'full_name': 'Prof. MDM Test', 'employee_code': 'EMP1006'},
    }

    for role_key, profile_data in staff_roles.items():
        if role_key not in user_ids:
            continue

        user_id = user_ids[role_key]
        existing = StaffProfile.query.filter_by(staff_id=user_id).first()

        if existing:
            print(f"  [EXISTS] {role_key}: {profile_data['full_name']}")
            continue

        # Create staff profile
        profile = StaffProfile(
            staff_id=user_id,
            full_name=profile_data['full_name'],
            employee_code=profile_data['employee_code'],
            primary_department_id=dept_id,
            is_event_coordinator=(role_key == 'event_coordinator'),
            is_amc_member=(role_key == 'amc_member'),
            is_amc_head=False,
            is_mdm_oe_coordinator=(role_key == 'mdm_coordinator')
        )
        db.session.add(profile)
        print(f"  [CREATED] {role_key}: {profile_data['full_name']}")

    db.session.commit()

    # Assign HOD
    if 'hod' in user_ids:
        dept = db.session.get(Department, dept_id)
        if dept:
            dept.hod_staff_id = user_ids['hod']
            db.session.commit()
            print(f"  [ASSIGNED] HOD to IT Department")

    # Assign Class Teacher
    if 'class_teacher' in user_ids:
        section = db.session.get(ClassSection, section_id)
        if section:
            section.class_teacher_id = user_ids['class_teacher']
            db.session.commit()
            print(f"  [ASSIGNED] Class Teacher to SY-DA")


def seed_student_profile(user_ids: dict, section_id: int):
    """Create student profile."""
    print("\n=== Creating Student Profile ===")

    if 'student' not in user_ids:
        return None

    user_id = user_ids['student']
    existing = StudentProfile.query.filter_by(student_id=user_id).first()

    if existing:
        print(f"  [EXISTS] Student: STU2024001")
        return user_id

    # StudentProfile uses admission_number, current_section_id, academic_status
    profile = StudentProfile(
        student_id=user_id,
        admission_number='2024001',
        full_name='Test Student',
        current_section_id=section_id,
        academic_status='Active'
    )
    db.session.add(profile)
    db.session.commit()
    print(f"  [CREATED] Student: Test Student (2024001)")

    return user_id


def seed_parent_profile(user_ids: dict, student_id: str):
    """Create parent profile linked to student."""
    print("\n=== Creating Parent Profile ===")

    if 'parent' not in user_ids or not student_id:
        return

    user_id = user_ids['parent']
    existing = ParentProfile.query.filter_by(parent_id=user_id).first()

    if existing:
        print(f"  [EXISTS] Parent: PAR2024001")
        # Link student to parent if not already linked
        student = StudentProfile.query.filter_by(student_id=student_id).first()
        if student and not student.parent_user_id:
            student.parent_user_id = user_id
            db.session.commit()
        return

    # ParentProfile uses father_name, mother_name, primary_phone
    profile = ParentProfile(
        parent_id=user_id,
        father_name='Test Father',
        mother_name='Test Mother',
        primary_phone='9876543210'
    )
    db.session.add(profile)
    db.session.commit()

    # Link student to parent
    student = StudentProfile.query.filter_by(student_id=student_id).first()
    if student:
        student.parent_user_id = user_id
        db.session.commit()

    print(f"  [CREATED] Parent: Test Parent (linked to STU2024001)")


def seed_mentor_batch(user_ids: dict, section_id: int, student_id: str):
    """Create mentor batch assignment."""
    print("\n=== Creating Mentor Batch ===")

    if 'mentor' not in user_ids:
        return None

    # Check if batch already exists
    existing = MentorBatch.query.filter_by(mentor_id=user_ids['mentor']).first()
    if existing:
        print(f"  [EXISTS] Mentor Batch: SY-DA-Batch1")
        batch_id = existing.batch_id
    else:
        # MentorBatch uses batch_name, section_id, mentor_id
        batch = MentorBatch(
            mentor_id=user_ids['mentor'],
            batch_name='SY-DA-Batch1',
            section_id=section_id
        )
        db.session.add(batch)
        db.session.commit()
        batch_id = batch.batch_id
        print(f"  [CREATED] Mentor Batch: SY-DA-Batch1")

    # Assign student to mentor batch
    if student_id:
        student = StudentProfile.query.filter_by(student_id=student_id).first()
        if student and not student.mentor_batch_id:
            student.mentor_batch_id = batch_id
            db.session.commit()
            print(f"  [ASSIGNED] Student to Mentor Batch")

    return batch_id


def seed_test_subjects(dept_id: int):
    """Create test subjects."""
    print("\n=== Creating Test Subjects ===")

    # Subject uses 'name' and 'code' columns
    subjects_data = [
        {'name': 'Data Structures', 'code': 'DS301', 'type': 'Core'},
        {'name': 'Database Management', 'code': 'DBMS302', 'type': 'Core'},
        {'name': 'Operating Systems', 'code': 'OS303', 'type': 'Core'},
        {'name': 'Machine Learning', 'code': 'ML304', 'type': 'Elective'},
        {'name': 'Cloud Computing', 'code': 'CC305', 'type': 'Elective'},
    ]

    for subj_data in subjects_data:
        existing = Subject.query.filter_by(code=subj_data['code']).first()
        if existing:
            print(f"  [EXISTS] Subject: {subj_data['name']} ({subj_data['code']})")
            continue

        subject = Subject(
            name=subj_data['name'],
            code=subj_data['code'],
            dept_id=dept_id,
            subject_type=subj_data['type'],
            credits=3
        )
        db.session.add(subject)
        print(f"  [CREATED] Subject: {subj_data['name']} ({subj_data['code']})")

    db.session.commit()


def seed_mdm_pool(dept_id: int):
    """Create MDM/OE course pool with department scoping."""
    print("\n=== Creating MDM/OE Course Pool ===")

    # MDMOfferingPool uses code, name, type, direction, host_school_name, academic_year, dept_id
    courses = [
        {'code': 'MDM101', 'name': 'Data Science Fundamentals', 'type': 'MDM', 'direction': 'Outbound', 'host': 'Partner University A'},
        {'code': 'MDM102', 'name': 'AI Ethics', 'type': 'MDM', 'direction': 'Outbound', 'host': 'Partner University B'},
        {'code': 'OE201', 'name': 'Entrepreneurship', 'type': 'OE', 'direction': 'Outbound', 'host': 'Business School'},
        {'code': 'OE202', 'name': 'Technical Communication', 'type': 'OE', 'direction': 'Outbound', 'host': 'Humanities Dept'},
    ]

    for course in courses:
        existing = MDMOfferingPool.query.filter_by(code=course['code']).first()
        if existing:
            print(f"  [EXISTS] {course['type']}: {course['name']} ({course['code']})")
            continue

        pool = MDMOfferingPool(
            code=course['code'],
            name=course['name'],
            type=course['type'],
            direction=course['direction'],
            host_school_name=course['host'],
            credits=3,
            capacity=30,
            academic_year='2024-25',
            dept_id=dept_id,  # Department scope
            is_active=True
        )
        db.session.add(pool)
        print(f"  [CREATED] {course['type']}: {course['name']} ({course['code']}) [Dept: {dept_id}]")

    db.session.commit()


def print_summary(test_users: dict):
    """Print test user credentials summary."""
    print("\n" + "=" * 60)
    print("TEST USER CREDENTIALS SUMMARY")
    print("=" * 60)
    print(f"{'Role':<20} {'Username':<15} {'Password':<20}")
    print("-" * 60)

    for role_key, user_data in test_users.items():
        print(f"{role_key:<20} {user_data['username']:<15} {user_data['password']:<20}")

    print("=" * 60)
    print("\nTest data seeding complete!")
    print("You can now start running tests.")


def main():
    """Main function to seed all test data."""
    print("=" * 60)
    print("EduMatrix AMS - Test Data Seeder")
    print("=" * 60)

    with app.app_context():
        # Load test users from fixture
        test_users = load_test_users()

        # Seed users
        user_ids = seed_users(test_users)

        # Seed department
        dept_id = seed_department()

        # Seed class section
        section_id = seed_class_section(dept_id)

        # Seed staff profiles
        seed_staff_profiles(user_ids, dept_id, section_id)

        # Seed student
        student_id = seed_student_profile(user_ids, section_id)

        # Seed parent
        seed_parent_profile(user_ids, student_id)

        # Seed mentor batch
        seed_mentor_batch(user_ids, section_id, student_id)

        # Seed subjects
        seed_test_subjects(dept_id)

        # Seed MDM pool (with department scoping)
        seed_mdm_pool(dept_id)

        # Print summary
        print_summary(test_users)


if __name__ == '__main__':
    main()

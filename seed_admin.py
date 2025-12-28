#!/usr/bin/env python
"""Seed the admin user for fresh database."""
from app import app, db, UserMaster, StaffProfile, Department
from werkzeug.security import generate_password_hash
import uuid

with app.app_context():
    admin_email = "admin@mituniversity.edu.in"
    if not UserMaster.query.filter_by(username=admin_email).first():
        new_uuid = str(uuid.uuid4())
        if not Department.query.filter_by(name="Department of Information Technology").first():
            db.session.add(Department(name="Department of Information Technology"))
            db.session.flush()
        
        admin_user = UserMaster(
            user_id=new_uuid, 
            username=admin_email, 
            password_hash=generate_password_hash("Admin@123"), 
            user_type="Admin", 
            is_active=True
        )
        db.session.add(admin_user)
        db.session.flush()  # Flush to satisfy FK constraint
        
        admin_profile = StaffProfile(
            staff_id=new_uuid, 
            full_name="System Administrator", 
            employee_code="ADMIN001", 
            email_contact=admin_email
        )
        db.session.add(admin_profile)
        db.session.commit()
        print(f"Super Admin Created! Login: {admin_email} / Admin@123")
    else:
        print("Admin already exists")

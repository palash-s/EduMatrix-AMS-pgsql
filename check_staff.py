from app import app, db, UserMaster, StaffProfile

with app.app_context():
    print("\n--- CHECKING DATABASE ---")
    
    # 1. Check Login Accounts
    users = UserMaster.query.all()
    print(f"Total Users: {len(users)}")
    
    # 2. Check Staff Profiles
    staff = StaffProfile.query.all()
    print(f"Total Staff Profiles: {len(staff)}")
    
    if len(staff) == 0:
        print("❌ CRITICAL: No Staff Profiles found!")
        print("   -> You MUST go to Admin > Bulk Uploads > Upload Staff.")
    else:
        print("\n✅ Valid Staff Found:")
        for s in staff:
            print(f" - {s.full_name} ({s.email_contact}) | ID: {s.staff_id}")

    print("-" * 30)
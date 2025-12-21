from app import app, db, UserMaster, StaffProfile, StudentProfile

with app.app_context():
    print("\n--- DIAGNOSTIC REPORT ---")
    
    users = UserMaster.query.all()
    print(f"Total Login Accounts: {len(users)}")
    
    zombies = 0
    for u in users:
        if u.user_type == 'Admin': continue # Admins don't always need profiles
        
        profile = None
        if u.user_type == 'Staff':
            profile = StaffProfile.query.filter_by(staff_id=u.user_id).first()
        elif u.user_type == 'Student':
            profile = StudentProfile.query.filter_by(student_id=u.user_id).first()
            
        if not profile:
            print(f"❌ ZOMBIE FOUND: {u.username} (Role: {u.user_type}) has ID but NO PROFILE.")
            zombies += 1
            
    if zombies == 0:
        print("✅ System is healthy. All users have profiles.")
    else:
        print(f"\n⚠️ Found {zombies} broken accounts. Please reset the database.")
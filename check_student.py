from app import app, db, StudentProfile, ClassSection

with app.app_context():
    count = StudentProfile.query.count()
    print(f"\n--- Total Students: {count} ---")
    
    if count == 0:
        print("❌ No students found. Please upload 'student_master.csv'.")
    else:
        # Check links
        orphans = StudentProfile.query.filter(StudentProfile.current_section_id == None).count()
        print(f"✅ Linked Students: {count - orphans}")
        print(f"⚠️ Unassigned Students: {orphans}")
        
        if orphans > 0:
            print("\nFirst 5 Unassigned Students:")
            bad_students = StudentProfile.query.filter(StudentProfile.current_section_id == None).limit(5).all()
            for s in bad_students:
                print(f" - {s.full_name} ({s.admission_number})")
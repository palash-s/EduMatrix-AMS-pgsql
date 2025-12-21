from sql_connection import db

# Initialize SQLAlchemy (Not attached to app yet)
 


from app import app, WeeklySchedule, Subject, StaffProfile, ClassSection

with app.app_context():
    # Join all tables to get the full picture
    schedule = (db.session.query(WeeklySchedule, Subject, StaffProfile, ClassSection)
                .join(Subject, WeeklySchedule.subject_id == Subject.subject_id)
                .join(StaffProfile, WeeklySchedule.teacher_id == StaffProfile.staff_id)
                .join(ClassSection, WeeklySchedule.section_id == ClassSection.section_id)
                .all())

    print(f"\n--- FULL SCHEDULE VERIFICATION ({len(schedule)} Slots) ---")
    print(f"{'DAY':<10} | {'TIME':<15} | {'CLASS':<10} | {'SUBJECT':<10} | {'TEACHER'}")
    print("-" * 70)
    
    for slot, subj, teacher, section in schedule:
        time_str = f"{slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')}"
        class_str = f"{section.class_level}-{section.name}"
        
        print(f"{slot.day_of_week:<10} | {time_str:<15} | {class_str:<10} | {subj.code:<10} | {teacher.full_name}")
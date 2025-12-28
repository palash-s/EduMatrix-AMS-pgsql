from werkzeug.security import generate_password_hash
from app import app, db
from sql_connection import UserMaster

with app.app_context():
    # Reset ALL passwords based on user type
    all_users = UserMaster.query.all()
    staff_count = 0
    student_count = 0
    parent_count = 0
    
    for user in all_users:
        user_type = (user.user_type or '').lower()
        
        if user_type == 'staff':
            user.password_hash = generate_password_hash('Staff@123')
            user.must_change_password = True
            staff_count += 1
        elif user_type == 'student':
            user.password_hash = generate_password_hash('Student@123')
            user.must_change_password = True
            student_count += 1
        elif user_type == 'parent':
            user.password_hash = generate_password_hash('Parent@123')
            user.must_change_password = True
            parent_count += 1
        # Skip Admin users
    
    db.session.commit()
    print(f'Password reset complete!')
    print(f'  Staff:   {staff_count} users -> Staff@123')
    print(f'  Student: {student_count} users -> Student@123')
    print(f'  Parent:  {parent_count} users -> Parent@123')
    print(f'All users must change password on first login.')

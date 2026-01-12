# MDM/OE Module - Next Steps

## What Was Implemented

✅ **Database Schema** (3 new tables + extended 2 existing tables)
- `cross_school_offering` - Catalog of MDM/OE courses
- `external_student_profile` - Guest students from other schools
- `cross_school_enrollment` - Our students in outbound courses
- Extended `ca_marks` with external student support
- Extended `attendance_transaction` with external student support
- Added `is_mdm_oe_coordinator` flag to `staff_profile`

✅ **Backend API** (11 new endpoints)
- Coordinator CRUD for offerings
- External student CSV upload/export
- MDM session auto-generation
- Student enrollment in outbound courses
- Attendance marking for external students
- Marks entry for external students

✅ **Frontend Dashboard**
- New coordinator dashboard at `/admin/mdm_oe_coordinator`
- Statistics cards (Inbound/Outbound counts)
- Tab interface for Inbound/Outbound/Create
- CSV upload modal
- Marks export functionality

✅ **Migration File**
- Alembic migration: `a1b2c3d4e5f6_add_mdm_oe_cross_school_module.py`

---

## How to Deploy

### 1. Run Database Migration

```bash
# Navigate to project root
cd e:\feature-AMS\EduMatrix-AMS-pgsql

# Run migration
flask db upgrade
```

### 2. Assign Coordinator Role

**Via Admin Dashboard (Recommended):**
1. Login as Admin
2. Navigate to **Admin Dashboard → Roles & Permissions** (or `/admin/manage_coordinators`)
3. Find the faculty member in the list
4. Click the toggle button under **MDM/OE Coord** column
5. The button will turn green with a checkmark when enabled

**Via Database (Quick Test - Alternative):**
```sql
UPDATE staff_profile 
SET is_mdm_oe_coordinator = TRUE 
WHERE employee_code = 'ADMIN001';  -- Replace with actual employee code
```

### 3. Access Coordinator Dashboard

**Method 1 - Via Sidebar Link:**
- Login as Admin (with MDM/OE Coordinator role)
- In the left sidebar, under **System** section, click **"MDM/OE Cross-School"**

**Method 2 - Direct URL:**
- Navigate to: `http://localhost:5000/admin/mdm_oe_coordinator`

You should see the MDM/OE dashboard with 4 stat cards (Inbound/Outbound offerings, External students, Our students)

---

## Testing Workflow

### Scenario 1: Create Inbound MDM Course

1. **Create Offering**
   - Dashboard → "Create Offering" tab
   - Fill form:
     - Name: "Introduction to Blockchain"
     - Code: "MDM101"
     - Type: MDM
     - Direction: Inbound
     - Credits: 3
     - Capacity: 60
     - Start Date: 2026-02-01
     - End Date: 2026-03-31
     - Schedule: "Mon-Fri 4:00-6:00 PM"
   - Submit

2. **Upload External Students**
   - Create CSV file:
     ```csv
     Student Name,Roll Number,Email,Home School,Department
     Alice Johnson,ENG2023001,alice@eng.edu,School of Engineering,Computer Science
     Bob Smith,ENG2023002,bob@eng.edu,School of Engineering,Computer Science
     ```
   - Dashboard → "Upload External Students" button
   - Select offering, upload CSV

3. **Generate Sessions**
   - Test via API:
     ```bash
     curl -X POST http://localhost:5000/api/coordinator/generate_mdm_sessions \
       -H "Content-Type: application/json" \
       -d '{"offering_id": 1}'
     ```
   - Should create ~40 sessions (Mon-Fri for 2 months)

4. **Mark Attendance**
   - Test via API:
     ```bash
     curl -X POST http://localhost:5000/api/staff/mark_mdm_attendance \
       -H "Content-Type: application/json" \
       -d '{
         "session_id": 1,
         "attendance": [
           {"external_student_id": 1, "status": "Present"},
           {"external_student_id": 2, "status": "Absent"}
         ]
       }'
     ```

5. **Submit Marks**
   - Test via API:
     ```bash
     curl -X POST http://localhost:5000/api/marks/submit_mdm_ca \
       -H "Content-Type: application/json" \
       -d '{
         "offering_id": 1,
         "marks": [
           {"external_student_id": 1, "ta1": 18, "ta2": 20, "ta3": 19},
           {"external_student_id": 2, "ta1": 15, "ta2": 17, "ta3": 18}
         ]
       }'
     ```

6. **Export Marks**
   - Dashboard → Inbound tab → "Export Marks" button
   - Should download CSV with calculated grades

---

### Scenario 2: Create Outbound OE Course

1. **Create Offering**
   - Dashboard → "Create Offering" tab
   - Fill form:
     - Name: "Data Visualization"
     - Code: "OE201"
     - Type: OE
     - Direction: Outbound
     - Credits: 2
     - Capacity: 40
     - Host School Name: "School of Design"
     - Schedule: "Tue-Thu 3:00-5:00 PM"
   - Submit

2. **Change Status to Open**
   - Update via API:
     ```bash
     curl -X PUT http://localhost:5000/api/coordinator/offerings/update \
       -H "Content-Type: application/json" \
       -d '{"offering_id": 2, "status": "Open"}'
     ```

3. **Student Enrollment**
   - Login as student
   - Test via API:
     ```bash
     curl -X GET http://localhost:5000/api/student/mdm_oe_offerings
     ```
   - Should see "Data Visualization" in list
   - Enroll:
     ```bash
     curl -X POST http://localhost:5000/api/student/mdm_oe_enroll \
       -H "Content-Type: application/json" \
       -d '{"offering_id": 2}'
     ```

---

## Known Limitations (TODO)

1. **✅ UI Integration (COMPLETED)**
   - ✅ Added "MDM/OE Coordinator" toggle to `admin_coordinators.html`
   - ✅ Added sidebar link to MDM/OE dashboard in `admin_dashboard.html`
   - TODO: Student dashboard link to browse MDM/OE courses

2. **Session Auto-Generator Edge Cases**
   - Currently uses fixed 4-6 PM time slot
   - Need to parse `schedule_pattern` dynamically
   - Add validation for start_date < end_date

3. **Attendance UI**
   - No frontend for faculty to mark external student attendance
   - Need dedicated page similar to `attendance_sheet.html`

4. **Marks Entry UI**
   - No frontend for faculty to enter TA marks for external students
   - Need dedicated page similar to `marks_entry.html`

5. **Student Selection UI**
   - No frontend for students to browse/enroll in outbound courses
   - Need new page or integrate into `student_dashboard.html`

6. **Validation Gaps**
   - No constraint to ensure either (student_id, subject_id) OR (external_student_id, cross_school_offering_id) in ca_marks
   - Need database CHECK constraint or application-level validation

---

## Files Modified

- `sql_connection.py` - Added 3 models, extended 2 models
- `app.py` - Added 11 API endpoints, 1 route, 3 imports
- `templates/coordinator_mdm_oe.html` - New coordinator dashboard (created)
- `templates/admin_coordinators.html` - Added MDM/OE Coordinator toggle column
- `templates/admin_dashboard.html` - Added sidebar link to MDM/OE dashboard
- `migrations/versions/a1b2c3d4e5f6_*.py` - Migration file (created)
- `docs/MDM_OE_IMPLEMENTATION.md` - Full documentation (created)

---

## Quick Verification Commands

```bash
# Check tables were created
psql -U postgres -d ams_db -c "\dt cross_school*"
psql -U postgres -d ams_db -c "\dt external_student_profile"

# Check column was added
psql -U postgres -d ams_db -c "\d staff_profile" | grep mdm_oe_coordinator

# Check ca_marks columns
psql -U postgres -d ams_db -c "\d ca_marks" | grep external_student_id

# Verify coordinator flag
psql -U postgres -d ams_db -c "SELECT staff_id, full_name, is_mdm_oe_coordinator FROM staff_profile WHERE is_mdm_oe_coordinator = TRUE;"
```

---

## Support

For issues or questions:
1. Check `docs/MDM_OE_IMPLEMENTATION.md` for detailed API documentation
2. Review migration file for schema details
3. Test endpoints with curl/Postman before UI integration

---

**Status**: ✅ Core infrastructure complete, ready for UI integration and testing.

# MDM/OE Cross-School Module Implementation Summary

## Overview
This implementation adds a comprehensive MDM (Multidisciplinary Minor) and OE (Open Elective) module to the EduMatrix AMS system, enabling federated cross-school course management without direct database connections between schools.

## Architecture

### Data Flow Model
**Federated Import/Export Pattern:**
- Schools exchange data via CSV handshakes (not direct DB queries)
- **Inbound Flow:** External students from other schools attend our courses
- **Outbound Flow:** Our students attend courses at other schools
- Isolated data structures prevent login/ID collisions

### Key Features
1. **Coordinator Role**: New `is_mdm_oe_coordinator` flag on StaffProfile
2. **Direction-Aware Catalog**: Offerings marked as Inbound/Outbound
3. **External Student Isolation**: Separate table for guest students (no login)
4. **Compressed Timeline Support**: 2-month MDM course session generation
5. **CSV Handshakes**: Import/export for enrollments and marks
6. **Attendance & Assessment**: Extended to support external students

---

## Database Schema Changes

### New Tables

#### 1. `cross_school_offering`
Catalog of MDM/OE courses (both hosted by us and hosted externally).

| Column | Type | Description |
|--------|------|-------------|
| `offering_id` | Integer (PK) | Unique offering ID |
| `name` | String(200) | Course name |
| `code` | String(50) | Unique course code |
| `type` | String(10) | 'MDM' or 'OE' |
| `direction` | String(10) | 'Inbound' (we host) or 'Outbound' (they host) |
| `credits` | Integer | Credit hours |
| `capacity` | Integer | Maximum enrollment |
| `host_school_id` | Integer (FK) | School.school_id (for Inbound) |
| `host_school_name` | String(200) | Host school name (for Outbound) |
| `assigned_faculty_id` | String(36) (FK) | StaffProfile.staff_id |
| `start_date` | Date | Course start date |
| `end_date` | Date | Course end date |
| `schedule_pattern` | String(100) | E.g., "Mon-Fri 4:00-6:00 PM" |
| `status` | String(20) | 'Draft', 'Open', 'Closed', 'Archived' |
| `exclude_from_load` | Boolean | Don't count toward regular teaching load |
| `description` | Text | Course description |
| `created_at` | DateTime | Timestamp |

**Indexes:** Unique on `code`

---

#### 2. `external_student_profile`
Guest students from other schools (Inbound flow only). Lightweight, no login.

| Column | Type | Description |
|--------|------|-------------|
| `external_id` | Integer (PK) | Unique external student ID |
| `full_name` | String(100) | Student name |
| `roll_number` | String(50) | Roll number from home school |
| `email` | String(100) | Contact email (optional) |
| `home_school_id` | Integer | Home school ID (optional) |
| `home_school_name` | String(200) | Home school name |
| `department_name` | String(100) | Home department |
| `enrolled_offering_id` | Integer (FK) | CrossSchoolOffering.offering_id |
| `status` | String(20) | 'Enrolled', 'Completed', 'Withdrawn' |
| `enrolled_on` | DateTime | Enrollment timestamp |

**FK:** `enrolled_offering_id` → `cross_school_offering.offering_id`

---

#### 3. `cross_school_enrollment`
Tracks our students enrolled in Outbound courses.

| Column | Type | Description |
|--------|------|-------------|
| `enrollment_id` | Integer (PK) | Unique enrollment ID |
| `student_id` | String(36) (FK) | StudentProfile.student_id |
| `offering_id` | Integer (FK) | CrossSchoolOffering.offering_id |
| `status` | String(20) | 'Enrolled', 'Completed', 'Withdrawn' |
| `external_marks` | Float | Marks received from host school (CSV import) |
| `external_grade` | String(5) | Grade from host school |
| `enrolled_on` | DateTime | Enrollment timestamp |
| `completed_on` | DateTime | Completion timestamp |

**FK:** `student_id` → `student_profile.student_id`, `offering_id` → `cross_school_offering.offering_id`

---

### Modified Tables

#### `staff_profile`
**Added Column:**
- `is_mdm_oe_coordinator` (Boolean, default=False) - Flag for MDM/OE coordinator privilege

---

#### `ca_marks`
**Modified Columns (nullable for external students):**
- `student_id` → nullable (was NOT NULL)
- `subject_id` → nullable (was NOT NULL)
- `section_id` → nullable (was NOT NULL)

**Added Columns:**
- `external_student_id` (Integer, FK → external_student_profile.external_id)
- `cross_school_offering_id` (Integer, FK → cross_school_offering.offering_id)

**Constraint:** Either (`student_id` AND `subject_id`) OR (`external_student_id` AND `cross_school_offering_id`) must be populated.

---

#### `attendance_transaction`
**Modified Column:**
- `student_id` → nullable (was NOT NULL)

**Added Column:**
- `external_student_id` (Integer, FK → external_student_profile.external_id)

**Constraint:** Either `student_id` OR `external_student_id` must be populated.

---

## API Endpoints

### Coordinator Endpoints (Admin + Coordinator flag required)

#### `POST /api/coordinator/offerings/create`
Create a new MDM/OE offering.

**Request Body:**
```json
{
  "name": "Introduction to Blockchain",
  "code": "MDM101",
  "type": "MDM",
  "direction": "Inbound",
  "credits": 3,
  "capacity": 60,
  "assigned_faculty_id": "uuid-string",
  "start_date": "2026-02-01",
  "end_date": "2026-03-31",
  "schedule_pattern": "Mon-Fri 4:00-6:00 PM",
  "description": "Fundamentals of blockchain...",
  "host_school_name": "School of Engineering"  // Required for Outbound only
}
```

**Response:**
```json
{
  "message": "Offering created successfully",
  "offering_id": 123
}
```

---

#### `GET /api/coordinator/offerings/list`
List all MDM/OE offerings with optional filters.

**Query Params:**
- `direction`: "Inbound" | "Outbound"
- `type`: "MDM" | "OE"
- `status`: "Draft" | "Open" | "Closed" | "Archived"

**Response:**
```json
{
  "offerings": [
    {
      "id": 123,
      "name": "Blockchain Fundamentals",
      "code": "MDM101",
      "type": "MDM",
      "direction": "Inbound",
      "credits": 3,
      "capacity": 60,
      "enrolled": 45,
      "faculty": "Dr. John Doe",
      "faculty_id": "uuid",
      "host_school": "School of Computing",
      "start_date": "2026-02-01",
      "end_date": "2026-03-31",
      "schedule": "Mon-Fri 4-6 PM",
      "status": "Open",
      "description": "..."
    }
  ]
}
```

---

#### `PUT /api/coordinator/offerings/update`
Update an existing offering.

**Request Body:**
```json
{
  "offering_id": 123,
  "capacity": 80,
  "status": "Open",
  "assigned_faculty_id": "new-uuid"
}
```

---

#### `POST /api/coordinator/upload_external_students`
Bulk import external students via CSV (Inbound offerings only).

**Form Data:**
- `offering_id`: Integer
- `file`: CSV file

**CSV Format:**
| Student Name | Roll Number | Email | Home School | Department |
|--------------|-------------|-------|-------------|------------|
| Alice Smith | CS2023001 | alice@school.edu | School of Engineering | Computer Science |

**Response:**
```json
{
  "message": "Processed 45 students",
  "errors": [
    "Row 10: Student CS2023010 already enrolled",
    "Row 15: Offering at full capacity (60)"
  ]
}
```

---

#### `GET /api/coordinator/export_external_marks`
Export marks for external students (CSV handshake back to home school).

**Query Params:**
- `offering_id`: Integer

**Response:** CSV file download

**CSV Format:**
| Roll Number | Student Name | Home School | TA1 | TA2 | TA3 | Total Marks | Grade | Host School |
|-------------|--------------|-------------|-----|-----|-----|-------------|-------|-------------|
| CS2023001 | Alice Smith | School of Engineering | 18 | 20 | 19 | 57 | B+ | School of Computing |

---

#### `POST /api/coordinator/generate_mdm_sessions`
Auto-generate SessionLog entries for 2-month compressed MDM timeline.

**Request Body:**
```json
{
  "offering_id": 123
}
```

**Behavior:**
- Creates sessions Mon-Fri from `start_date` to `end_date`
- Default: 4:00-6:00 PM (overridable via `schedule_pattern`)
- Links sessions to `assigned_faculty_id`

**Response:**
```json
{
  "message": "Generated 40 sessions",
  "sessions_created": 40
}
```

---

### Student Endpoints

#### `GET /api/student/mdm_oe_offerings`
List available Outbound MDM/OE courses for student enrollment.

**Response:**
```json
{
  "offerings": [
    {
      "id": 456,
      "name": "Data Visualization",
      "code": "OE201",
      "type": "OE",
      "credits": 2,
      "host_school": "School of Design",
      "capacity": 40,
      "enrolled": 25,
      "available": 15,
      "schedule": "Tue-Thu 3-5 PM",
      "description": "...",
      "is_enrolled": false,
      "enrollment_status": null
    }
  ]
}
```

---

#### `POST /api/student/mdm_oe_enroll`
Student enrolls in an Outbound course.

**Request Body:**
```json
{
  "offering_id": 456
}
```

**Response:**
```json
{
  "message": "Enrollment successful"
}
```

**Validations:**
- Offering must be Outbound and status='Open'
- Capacity not exceeded
- No duplicate enrollment

---

### Staff Endpoints

#### `GET /api/staff/mdm_classes`
Faculty view of assigned MDM/OE classes.

**Response:**
```json
{
  "mdm_oe_classes": [
    {
      "offering_id": 123,
      "name": "Blockchain Fundamentals",
      "code": "MDM101",
      "type": "MDM",
      "direction": "Inbound",
      "student_count": 45,
      "schedule": "Mon-Fri 4-6 PM",
      "upcoming_sessions": [
        {
          "session_id": 789,
          "date": "2026-02-05",
          "time": "16:00-18:00"
        }
      ]
    }
  ]
}
```

---

#### `POST /api/staff/mark_mdm_attendance`
Mark attendance for external students.

**Request Body:**
```json
{
  "session_id": 789,
  "attendance": [
    {"external_student_id": 1, "status": "Present"},
    {"external_student_id": 2, "status": "Absent"}
  ]
}
```

---

#### `POST /api/marks/submit_mdm_ca`
Submit TA1/TA2/TA3 marks for external students.

**Request Body:**
```json
{
  "offering_id": 123,
  "marks": [
    {"external_student_id": 1, "ta1": 18, "ta2": 20},
    {"external_student_id": 2, "ta1": 15, "ta2": 17, "ta3": 19}
  ]
}
```

---

## Frontend Changes

### New Dashboard: `coordinator_mdm_oe.html`
**Route:** `/admin/mdm_oe_coordinator`

**Access Control:**
- User must have Admin role
- User must have `is_mdm_oe_coordinator=True`

**Features:**
1. **Statistics Dashboard**
   - Inbound Offerings count
   - Outbound Offerings count
   - Total External Students enrolled
   - Total Our Students in Outbound courses

2. **Inbound Tab**
   - List all Inbound offerings
   - Upload External Students (CSV)
   - Export Marks (CSV)

3. **Outbound Tab**
   - List all Outbound offerings
   - View enrollment counts

4. **Create Offering Tab**
   - Form to create new MDM/OE offerings
   - Direction toggle (shows/hides Host School field)
   - Date range picker
   - Schedule pattern input

**Technologies:**
- TailwindCSS for styling
- Lucide icons
- Vanilla JavaScript (no framework dependencies)

---

### Modified Dashboard: `admin_faculty.html`
**New Toggle Button:**
- Add "MDM/OE Coordinator" role toggle alongside Event Coordinator, AMC Member, AMC Head
- Calls `/api/admin/toggle_role` with `role_type='mdm_oe_coordinator'`

---

## Migration

### File: `a1b2c3d4e5f6_add_mdm_oe_cross_school_module.py`

**Upgrade Operations:**
1. Add `is_mdm_oe_coordinator` column to `staff_profile`
2. Create `cross_school_offering` table
3. Create `external_student_profile` table
4. Create `cross_school_enrollment` table
5. Alter `ca_marks`: make columns nullable, add FKs
6. Alter `attendance_transaction`: make `student_id` nullable, add `external_student_id` FK

**Downgrade Operations:**
- Reverses all changes (drops tables, removes columns, restores NOT NULL constraints)

**Run Migration:**
```bash
flask db upgrade
```

---

## CSV Templates

### External Students Upload
**Filename:** `external_students_template.csv`

| Student Name | Roll Number | Email | Home School | Department |
|--------------|-------------|-------|-------------|------------|
| John Doe | 2023001 | john@school.edu | School of Engineering | Computer Science |

---

### External Marks Export
**Auto-generated** via `/api/coordinator/export_external_marks?offering_id=123`

| Roll Number | Student Name | Home School | TA1 | TA2 | TA3 | Total Marks | Grade | Host School |
|-------------|--------------|-------------|-----|-----|-----|-------------|-------|-------------|
| 2023001 | John Doe | School of Engineering | 18 | 20 | 19 | 57 | B+ | School of Computing |

---

## Testing Checklist

### Phase 1: Coordinator Setup
- [ ] Assign `is_mdm_oe_coordinator=True` to a faculty member
- [ ] Access `/admin/mdm_oe_coordinator` dashboard
- [ ] Create Inbound MDM offering
- [ ] Create Outbound OE offering

### Phase 2: Inbound Flow
- [ ] Upload external students CSV
- [ ] Generate MDM sessions (2-month timeline)
- [ ] Mark attendance for external students
- [ ] Submit TA marks for external students
- [ ] Export marks CSV (verify grades calculated)

### Phase 3: Outbound Flow
- [ ] Student views available Outbound offerings
- [ ] Student enrolls in Outbound course
- [ ] Verify capacity checks
- [ ] Verify duplicate enrollment prevention

### Phase 4: Integration
- [ ] Verify MDM courses excluded from regular faculty load
- [ ] Test session generation for date ranges
- [ ] Test CSV error handling (duplicate students, over-capacity)
- [ ] Verify attendance transaction links correctly
- [ ] Verify CA marks links correctly

---

## Security Considerations

1. **Role Enforcement**: All coordinator endpoints check `is_mdm_oe_coordinator` flag
2. **Input Validation**: CSV uploads validate required fields and data types
3. **Capacity Checks**: Prevent over-enrollment in offerings
4. **Duplicate Prevention**: Check for existing enrollments before insert
5. **Faculty Authorization**: Staff can only mark attendance/grades for their assigned offerings

---

## Performance Notes

1. **Indexing**: `cross_school_offering.code` has unique index for fast lookups
2. **Batch Operations**: CSV uploads use bulk inserts with error collection
3. **Query Optimization**: Use JOINs to fetch offering + enrollment counts in single query
4. **Session Generation**: Bulk insert SessionLog entries (avoid N+1 queries)

---

## Future Enhancements

1. **Student Selection Workflow**: Add approval workflow for outbound enrollments
2. **Conflict Detection**: Check for schedule conflicts with regular courses
3. **Automated Reminders**: Email notifications for upcoming MDM sessions
4. **Analytics Dashboard**: Cross-school enrollment trends, completion rates
5. **Bi-directional CSV Sync**: Automated marks import from partner schools
6. **Gradebook Integration**: Link external grades to transcript generation

---

## Support Documentation

### Coordinator Quick Start Guide

1. **Access Dashboard**: Navigate to Admin → MDM/OE Coordinator
2. **Create Offering**: Click "Create Offering" tab, fill form, submit
3. **Upload Students** (Inbound): Select offering, upload CSV with student list
4. **Generate Sessions** (Inbound): Click offering, generate 2-month session schedule
5. **Mark Attendance**: Staff dashboard → MDM Classes → Select session → Mark attendance
6. **Export Marks**: Coordinator dashboard → Inbound tab → Click "Export Marks"

### Student Quick Start Guide

1. **Browse Courses**: Login → Student Dashboard → MDM/OE Courses
2. **Enroll**: Click offering → Enroll button
3. **View Schedule**: Check upcoming sessions in dashboard
4. **Attend Classes**: Follow schedule pattern (e.g., Mon-Fri 4-6 PM)

---

## Technical Dependencies

- **Backend**: Flask 3.0, SQLAlchemy ORM, PostgreSQL 13
- **Migration**: Alembic
- **Frontend**: TailwindCSS 3.x, Lucide Icons, Vanilla JS
- **CSV Processing**: Python `csv` module, `io.StringIO`

---

## Contact

For technical support or feature requests, contact the development team or raise an issue in the project repository.

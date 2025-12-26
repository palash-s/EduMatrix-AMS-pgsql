# EduMatrix AMS (Academic Management System)

<p align="center">
  <img src="static/images/mit_logo.png" alt="EduMatrix AMS Logo" width="120"/>
</p>

<p align="center">
  <strong>A Production-Grade, Containerized Academic ERP for Universities</strong>
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-mobile-apps">Mobile Apps</a> •
  <a href="#-deployment">Deployment</a>
</p>

---

## 📋 Overview

EduMatrix AMS is a comprehensive Academic Management System that digitizes the entire academic lifecycle—from student onboarding and timetabling to attendance, disciplinary workflows, assessment, and reporting. Built with Flask + PostgreSQL and fully containerized with Docker.

### Target Scale
- **6,500+ Students**
- **2,000+ Parents**
- **250+ Faculty Members**
- **Multi-department Support**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                              │
├─────────────┬─────────────┬─────────────┬──────────────────────┤
│  Web Portal │ Android App │   iOS App   │  React Native App    │
│  (Browser)  │  (Kotlin)   │  (Planned)  │    (Hybrid)          │
└──────┬──────┴──────┬──────┴──────┬──────┴──────────┬───────────┘
       │             │             │                  │
       └─────────────┴─────────────┴──────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Nginx Reverse   │
                    │      Proxy        │
                    │   (Port 80/443)   │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Flask App       │
                    │   (Gunicorn)      │
                    │   Port 5000       │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   PostgreSQL 13   │
                    │   (Database)      │
                    └───────────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.9+, Flask 3.0, SQLAlchemy ORM |
| **Database** | PostgreSQL 13 with Flask-Migrate (Alembic) |
| **Frontend** | HTML5, Tailwind CSS, Vanilla JS (ES6+) |
| **Charts** | Chart.js |
| **PDF Export** | jsPDF (client-side) |
| **Mobile** | Android (Kotlin), React Native |
| **Infrastructure** | Docker, Docker Compose, Nginx, Gunicorn |
| **Push Notifications** | Firebase Cloud Messaging (FCM) |
| **CI/CD** | GitHub Actions, GHCR |

---

## ✨ Features

### 1. 🔐 Authentication & Security

| Feature | Description |
|---------|-------------|
| **Multi-Role Authentication** | Admin, Staff, Student, Parent with role-based access |
| **Server-Side Sessions** | Flask-Login with secure session management |
| **Password Security** | PBKDF2-SHA256 hashing via Werkzeug |
| **Force Password Change** | Bulk-uploaded users must change password on first login |
| **Rate Limiting** | Flask-Limiter prevents brute force attacks |
| **CSRF Protection** | Flask-WTF CSRF tokens on all forms |
| **Security Headers** | X-Frame-Options, CSP, X-XSS-Protection via Nginx |

**Default Passwords (for bulk uploads):**
- Staff: `Staff@123`
- Students: `Student@123`  
- Parents: `Parent@123`

---

### 2. 🏛️ Admin Console

#### Dashboard Analytics
- Real-time student/staff counts
- Attendance rate monitoring
- Student distribution charts (by year/department)
- System activity log

#### User Management
| Feature | Endpoint | Description |
|---------|----------|-------------|
| Faculty Directory | `/admin/manage_faculty` | Add, archive, view faculty with department assignments |
| Student Directory | `/admin/student_directory` | View, filter, update student status |
| Class Management | `/admin/manage_classes` | Create sections, assign class teachers |
| Role Assignment | `/api/admin/toggle_role` | HOD, AMC Member, Event Coordinator toggles |
| HOD Assignment | `/api/admin/assign_hod` | Assign department heads |

#### Bulk Data Uploads
| Upload Type | Template Available | Description |
|-------------|-------------------|-------------|
| Departments & Subjects | ✅ | Master data with L-T-P credits |
| Class Sections | ✅ | Year-wise sections (FY-A, SY-B, etc.) |
| Staff Master | ✅ | Faculty with departments |
| Student Master | ✅ | Students with admission numbers, sections |
| Semester Course Structure | ✅ | Subject mapping per semester (Odd/Even) |
| Subject Allocation | ✅ | Teacher-subject-section mapping |
| Weekly Schedule | ✅ | Timetable slots |
| Room Master | ✅ | Classrooms, labs with capacity |
| Syllabus/Teaching Plan | ✅ | Unit-wise topic breakdown |

#### Intelligent Auto-Scheduler
Generates conflict-free weekly timetables using a **Greedy First-Fit Algorithm**:

- **Queue Priority**: Labs (2-hour) → Tutorials → Lectures
- **Constraints Checked**:
  - Teacher availability
  - Room type matching (Lab vs Classroom)
  - Batch divisions (A/B for practicals)
  - Lunch break avoidance
  - Maximum 4 hours/day per faculty

---

### 3. 📚 Academic Operations (Staff Portal)

#### Attendance Management
| Feature | Description |
|---------|-------------|
| **Batch-Aware Marking** | Theory vs Practical sessions |
| **Quick Mark All** | One-click present/absent for entire class |
| **Session History** | Full audit trail with date/time |
| **On-Duty Auto-Update** | Event participation → Absent becomes OnDuty |

#### Class Teacher Dashboard
- Section-wise analytics
- Subject performance reports
- Overall attendance summary
- Student issue tracking

#### Leave Management
| Flow | Description |
|------|-------------|
| **Student Applies** | Through portal or mobile app |
| **Class Teacher Review** | First-level approval |
| **HOD Escalation** | Leaves >15 days auto-escalate |
| **Balance Tracking** | Real-time leave balance |

#### Lesson Planning
- Unit/Sub-unit wise syllabus upload
- Topic completion tracking
- Session-to-topic linking
- Syllabus progress reports

---

### 4. 📝 Internal Assessment (CA Marks)

| Component | Max Marks | Description |
|-----------|-----------|-------------|
| TA1 | 20 | Term Assessment 1 |
| TA2 | 20 | Term Assessment 2 |
| TA3 | 20 | Term Assessment 3 |
| A1-A5 | 10 each | Assignments (5 total) |
| Attendance | 10 | Auto-calculated from percentage |

**Auto-Scaling Formula:**
```
Total CA = (TA1 × 0.5) + (TA2 × 0.5) + TA3 + (Avg_Assignments × 1.5) + Attendance_Score
```

**Learner Classification:**
- 🔴 **Slow Learner**: <40%
- 🟡 **Average**: 40-80%
- 🟢 **Advanced Learner**: >80%

**Analysis Reports:**
- Bell curve distribution
- Score brackets (0-9, 10-19, 20-29...)
- NAAC compliance matrices

---

### 5. 🧩 Elective Pre-Registration System

Semester-based window system for B.Tech 8-semester workflows:

```
┌─────────────────────────────────────────────────────────────┐
│  1. Upload Semester Course Structure (Odd/Even)             │
│     - Maps: Section + Semester → Elective Buckets          │
├─────────────────────────────────────────────────────────────┤
│  2. Admin Opens Window per Bucket                           │
│     - Status: Open → Extension → Closed                     │
│     - Min batch size: 12 (configurable)                     │
├─────────────────────────────────────────────────────────────┤
│  3. Students Select (One per Bucket)                        │
│     - Editable while Open/Extension                         │
├─────────────────────────────────────────────────────────────┤
│  4. Close Window                                            │
│     - Under-filled → Extension for affected students        │
│     - Final close → Auto-balance enrollment                 │
└─────────────────────────────────────────────────────────────┘
```

**Key APIs:**
- `GET /api/admin/semester_structure/electives`
- `POST /api/admin/elective_windows/open`
- `POST /api/admin/elective_windows/close`
- `GET /api/admin/elective_windows/live_dashboard`
- `GET /api/student/elective_windows`

---

### 6. 🛡️ Detention & Remedial System

| Stage | Actor | Action |
|-------|-------|--------|
| **Detection** | System | Auto-flags students with <75% attendance |
| **Assignment** | Faculty | Assigns remedial task with details |
| **Submission** | Student | Uploads completed work |
| **Review** | Faculty | Approves/rejects submission |
| **Release** | Faculty | Clears detention status |

**Endpoints:**
- `GET /api/detention/watchlist` - Low attendance list
- `POST /api/detention/assign` - Assign detention
- `GET /api/detention/my_detentions` - Student view
- `POST /api/detention/submit_task` - Submit work
- `POST /api/detention/release` - Clear detention

---

### 7. 👥 Mentor-Mentee System

| Feature | Description |
|---------|-------------|
| **Batch Assignment** | Auto-split students into mentor batches |
| **Counseling Log** | Digital records of meetings |
| **Issue Categories** | Academic, Personal, Disciplinary, Financial |
| **Issue Lifecycle** | Open → Resolved / Escalated |
| **Meeting Scheduler** | Min 2, Max 4 meetings per semester |
| **Progress Tracking** | Visual progress bars |

**Mentor APIs:**
- `POST /api/mentor/schedule_meeting`
- `GET /api/mentor/get_meetings`
- `GET /api/mentor/get_logs`
- `POST /api/mentor/add_log`
- `POST /api/mentor/update_log_status`

---

### 8. 🎪 Event Management

| Feature | Description |
|---------|-------------|
| **Event Creation** | Name, dates, times, coordinator |
| **Student Nomination** | Add participants with roles |
| **Attendance Marking** | Track actual participation |
| **Auto OD Update** | Conflict resolution with class attendance |

**Coordinator Dashboard** (`/staff/events`):
- My events view
- Participant management
- Attendance tracking

---

### 9. 📊 Governance Dashboards

#### HOD Dashboard (`/staff/hod_dashboard`)
- Faculty performance metrics (sessions conducted vs missed)
- Average student attendance per teacher
- Long leave approval inbox
- Escalated counseling cases
- Feedback analysis reports
- Syllabus progress by subject

#### AMC Dashboard (`/staff/amc_dashboard`)
- Daily compliance report (scheduled vs actual)
- Department-wide CA summary
- Term grant generation
- Result analysis matrices

---

### 10. 📱 Student Feedback System

| Stage | Description |
|-------|-------------|
| **Cycle Creation** | Admin defines feedback period |
| **Questions** | Configurable question bank with categories |
| **Anonymous Submission** | Students rate teachers 1-5 |
| **Analysis** | HOD views aggregated feedback scores |

**Tables:**
- `FeedbackCycle` - Active feedback periods
- `FeedbackQuestion` - Question bank
- `FeedbackResponse` - Individual ratings
- `StudentFeedbackStatus` - Tracks completion (anonymized)

---

### 11. 📅 Term Grant & Promotions

**Criteria Evaluated:**
- Attendance percentage
- Average CA score
- Failed subjects count (<20 marks)
- Active detentions

**Status Outcomes:**
- ✅ **Granted** - Meets all criteria
- ⚠️ **Provisional** - Conditional promotion
- ❌ **Detained** - Must repeat

---

### 12. 🔔 Notification System

| Type | Description |
|------|-------------|
| **In-App Bell** | Real-time notification center |
| **Push (FCM)** | Mobile push notifications |
| **Categories** | Info, Warning, Success, Danger |
| **Deep Links** | Navigate to relevant pages |

**Tables:**
- `Notification` - In-app notifications
- `PushDevice` - FCM token registry
- `RefreshToken` - Mobile auth tokens

---

### 13. 👨‍👩‍👧 Parent Portal

| Feature | Description |
|---------|-------------|
| **Multi-Child Support** | View all linked children |
| **Attendance View** | Subject-wise attendance percentage |
| **Results** | Published CA marks |
| **Leave Application** | Apply on behalf of child |
| **Mentor Contact** | View assigned mentor details |
| **Notifications** | Combined feed with child filter |

---

### 14. 🔄 Load Adjustment (Faculty Swap)

Mutual exchange system for faculty schedule conflicts:

1. **Requester** selects slot they cannot take
2. **Requester** picks colleague and their slot to swap
3. **Adjuster** approves/rejects
4. **System** updates effective timetable for the date

---

### 15. 📦 Archive & Historical Data

| Feature | Description |
|---------|-------------|
| **Term Rollover** | Snapshot current allocations/schedules |
| **Archived Terms** | View historical data |
| **Report Generation** | Historical attendance/marks reports |

---

## 📱 Mobile Apps

### Native Android (Kotlin)
Location: `AMS-android/`

**Features:**
- Student/Parent login with JWT
- Subject-wise attendance view
- Weekly timetable
- Leave application
- Result viewing
- Push notifications

### React Native (Cross-platform)
Location: `AMS-mobile-rn/`

**Screens:**
- `LoginScreen` - Authentication
- `DashboardScreen` - Home with summary
- `AttendanceScreen` - Subject-wise attendance
- `TimetableScreen` - Weekly schedule
- `LeavesScreen` - Apply/view leaves
- `ResultsScreen` - CA marks
- `NotificationsScreen` - Alerts feed

### Mobile API v1 Endpoints

**Authentication:**
```
POST /api/v1/auth/login     → {access_token, refresh_token}
POST /api/v1/auth/refresh   → {access_token}
GET  /api/v1/me             → User profile
```

**Student:**
```
GET  /api/v1/student/attendance/subjects
GET  /api/v1/student/timetable
GET  /api/v1/student/leaves
POST /api/v1/student/leaves
GET  /api/v1/student/results
GET  /api/v1/student/events
```

**Parent:**
```
GET  /api/v1/parent/children
GET  /api/v1/parent/<child_id>/attendance/subjects
GET  /api/v1/parent/<child_id>/timetable
GET  /api/v1/parent/<child_id>/leaves
POST /api/v1/parent/<child_id>/leaves
GET  /api/v1/parent/<child_id>/results
```

**Push Notifications:**
```
POST /api/v1/push/register
POST /api/v1/push/unregister
GET  /api/v1/notifications
POST /api/v1/notifications/<id>/read
```

---

## 🚀 Quick Start

### Prerequisites
- Docker Desktop installed and running
- Git

### 1. Clone Repository
```bash
git clone https://github.com/palash-s/EduMatrix-AMS-pgsql.git
cd EduMatrix-AMS-pgsql
```

### 2. Launch Development Environment
```bash
docker compose -f docker-compose.yml up --build
```
Access at: http://localhost

### 3. Apply Database Migrations
```bash
docker compose exec web flask db upgrade
```

### 4. Create Admin User
```bash
docker compose exec web python seed_admin.py
```

**Default Admin Login:**
- Email: `admin@mituniversity.edu.in`
- Password: `Admin@123`

---

## 🚢 Production Deployment

### GitHub Actions CI/CD

The repository includes automated workflows:

| Workflow | File | Description |
|----------|------|-------------|
| **CI** | `.github/workflows/ci.yml` | Syntax check, Docker build, Compose validation |
| **Deploy** | `.github/workflows/deploy.yml` | Manual deploy to server via SSH |

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `SSH_HOST` | Server IP (Tailscale IP if private) |
| `SSH_PORT` | SSH port (default: 22) |
| `SSH_USER` | Deploy user |
| `SSH_PRIVATE_KEY` | SSH private key |
| `DEPLOY_PATH` | e.g., `/opt/edumatrix-ams` |
| `TAILSCALE_AUTHKEY` | Optional: For private servers |
| `GHCR_USERNAME` | GitHub username |
| `GHCR_TOKEN` | GitHub PAT with `read:packages` |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `POSTGRES_DB` | Database name |
| `SECRET_KEY` | Flask secret key |

### Production Commands

**Apply migrations:**
```bash
docker compose -f docker-compose.prod.yml exec web flask db upgrade
```

**Create admin:**
```bash
docker compose -f docker-compose.prod.yml exec web python seed_admin.py
```

**View logs:**
```bash
docker compose -f docker-compose.prod.yml logs -f web
```

---

## 📂 Project Structure

```
EduMatrix-AMS-pgsql/
├── app.py                      # Main Flask application (9600+ lines)
├── sql_connection.py           # SQLAlchemy models (40+ tables)
├── seed_admin.py               # Admin user seeding script
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container definition
├── docker-compose.yml          # Development orchestration
├── docker-compose.prod.yml     # Production orchestration
│
├── migrations/                 # Alembic database migrations
│   └── versions/              # Migration scripts
│
├── templates/                  # Jinja2 HTML templates
│   ├── login.html
│   ├── admin_dashboard.html
│   ├── staff_dashboard.html
│   ├── student_dashboard.html
│   ├── parent_dashboard.html
│   ├── hod_dashboard.html
│   ├── amc_dashboard.html
│   └── ... (30+ templates)
│
├── static/                     # Static assets
│   ├── style.css
│   ├── script.js
│   └── images/
│
├── nginx/                      # Nginx configuration
│   ├── default.conf           # Development config
│   └── default-ssl.conf       # SSL config template
│
├── data/                       # Sample CSV templates
│
├── tests/                      # Pytest test suite
│   ├── conftest.py
│   └── test_security.py
│
├── tools/                      # Utility scripts
│   └── seed_mobile_test_users.py
│
├── docs/                       # Documentation
│   └── AZURE_INFRASTRUCTURE_REQUIREMENTS.md
│
├── AMS-android/               # Native Android app (Kotlin)
│   └── app/src/main/
│
├── AMS-mobile-rn/             # React Native app
│   └── src/screens/
│
├── secrets/                    # Firebase credentials (gitignored)
│
└── .github/
    ├── workflows/
    │   ├── ci.yml             # CI pipeline
    │   └── deploy.yml         # Deployment pipeline
    └── pull_request_template.md
```

---

## 📊 Database Schema

### Core Tables (40+)

| Category | Tables |
|----------|--------|
| **Identity** | `user_master` |
| **Profiles** | `staff_profile`, `student_profile`, `parent_profile`, `department` |
| **Academic** | `subject`, `class_section`, `subject_allocation`, `semester_course_structure` |
| **Schedule** | `weekly_schedule`, `room_master`, `session_log` |
| **Operations** | `attendance_transaction`, `leave_application`, `leave_workflow_log` |
| **Assessment** | `ca_marks`, `term_grant_record` |
| **Mentoring** | `mentor_batch`, `mentor_log`, `mentor_meeting` |
| **Detention** | `detention_record` |
| **Electives** | `elective_window`, `elective_offering`, `student_elective` |
| **Events** | `event_master`, `event_participation` |
| **Feedback** | `feedback_cycle`, `feedback_question`, `feedback_response`, `student_feedback_status` |
| **Syllabus** | `teaching_plan`, `lesson_log` |
| **Mobile** | `refresh_token`, `push_device` |
| **System** | `notification`, `system_log`, `system_config`, `load_adjustment` |
| **Archive** | `archived_allocation`, `archived_schedule` |

---

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session encryption | Required in prod |
| `POSTGRES_HOST` | Database host | `db` |
| `POSTGRES_PORT` | Database port | `5432` |
| `POSTGRES_USER` | Database user | `admin` |
| `POSTGRES_PASSWORD` | Database password | Required |
| `POSTGRES_DB` | Database name | `school_system` |
| `FLASK_ENV` | Environment mode | `production` |
| `SESSION_COOKIE_SECURE` | HTTPS-only cookies | `false` |
| `MOBILE_ACCESS_TOKEN_TTL_SECONDS` | JWT access token TTL | `1800` |
| `MOBILE_REFRESH_TOKEN_TTL_DAYS` | JWT refresh token TTL | `30` |

---

## 🧪 Testing

```bash
# Run tests
docker compose exec web pytest

# With coverage
docker compose exec web pytest --cov=app --cov-report=html
```

---

## 📜 License

This project is licensed under the MIT License.

---

## 👥 Contributors

- Development Team
- MIT ADT University

---

<p align="center">
  <strong>Built with ❤️ for Academic Excellence</strong>
</p>

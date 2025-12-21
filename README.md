# EduMatrix AMS (Academic Management System)

A production-grade, containerized Academic ERP for universities.

EduMatrix AMS digitizes the academic lifecycle—from student onboarding and timetabling to attendance, disciplinary workflows, assessment, and reporting. It runs on Flask + PostgreSQL with Docker Compose.

- added collaborator for PR

## 🚀 Key Features

### 1. 🏛️ Administrative Command Center
- **Bulk Data Ingestion**: Rapid onboarding via CSV uploads for Departments, Staff, Students, and Curriculum.
- **Academic Term Control (Rollover)**:
  - Admin-set **Current Term** (Academic Year + Sem) used across dashboards and exports.
  - Public API: `GET /api/current_term` returns `current_term`, `academic_year`, `semester_number`, `semester`.
- **Intelligent Auto-Scheduler**: A constraint-based algorithm that generates conflict-free weekly timetables considering:
  - Faculty Workload (Max 4 hrs/day)
  - Room Capacity & Type (Lab vs. Classroom)
  - Batch Divisions (Batch A/B for Practicals)
  - Lunch Breaks & Continuous Slot Constraints.
- **Infrastructure Management**: Room allocation and capacity tracking.
- **Role Management**: Granular permission toggles (HOD, AMC Head, Event Coordinator).

### 2. 🧩 Semester-Based Elective Pre-Registration (Window System)
Designed for 8-sem B.Tech workflows where students select electives for an upcoming semester before faculty allocation.

- **Semester Course Structure upload (Odd/Even)**:
  - Upload structure from `SEM + Section + Course Type` (e.g., Elective-III, Open Elective).
  - Endpoint: `POST /api/upload/semester_course_structure?parity=odd|even`.
  - This is the source-of-truth for which buckets exist per section and semester.
- **Open elective windows from structure** (Admin → Electives):
  - Choose class + target semester; select subjects grouped by bucket; open one window per bucket.
  - Students choose **one subject per bucket** (editable while window is Open).
- **Min batch size + extension + auto-balance**:
  - Default min batch size is 12.
  - If under-filled buckets exist at close: window moves to Extension for affected students.
  - Final close auto-assigns remaining students to balance counts.
- **Faculty allocation is decoupled**:
  - Faculty subject allocation upload is enforced as **allocation-only** (requires structure first).

### 2. 📚 Academic Operations (Staff Portal)
- **Smart Attendance**:
  - Batch-aware attendance marking (Theory vs. Practical).
  - Retroactive OD Update: Event participation automatically overwrites "Absent" status to "On Duty" for conflicting lectures.
  - Session History: Full audit trail of every class conducted with date/time stamps.
- **Leave Management**:
  - Two-Tier Approval Workflow: Leaves > 15 Days auto-escalate to HOD.
  - Real-time balance tracking and history.

### 3. 🛡️ Corrective & Support Systems
- **Detention Module**:
  - Auto-Detection: Identifies students with <75% attendance.
  - Assignment Workflow: Faculty assigns remedial tasks -> Student submits -> Faculty Reviews -> Release.
- **Mentor-Mentee System**:
  - Digital Counseling Log: Records academic, personal, or disciplinary interventions.
  - Issue Lifecycle: Track issues from "Open" to "Resolved" or "Escalated".
  - Meeting Scheduler: Tracks mandatory mentor meetings (min 2, max 4 per semester) with progress bars.

### 4. 📊 Internal Assessment (Outcomes)
- **Continuous Assessment (CA)**:
  - Granular entry for TA1, TA2, TA3, and Assignments.
  - Auto-Scaling: Automatically calculates final score out of 50 based on weighted averages.
  - Learner Classification: Auto-tags students as "Slow Learners" (<40%) or "Advanced Learners" (>80%).
  - Analysis Reports: Generates Bell Curve graphs and distribution matrices (0-9, 10-19, etc.) for NAAC compliance.

### 5. 👁️ Governance (HOD & AMC Console)
- **HOD Dashboard**:
  - Faculty Performance: Real-time view of sessions missed vs. conducted and average student attendance per teacher.
  - Approval Inbox: Central hub for long leaves and escalated counseling cases.
- **AMC (Academic Monitoring Committee)**:
  - Daily Compliance Report: Live tracking of scheduled vs. actual classes.
  - Result Analysis: Department-wide performance matrix.

### 6. 👨‍👩‍👧 Student & Parent Portals
- **Transparency**: Real-time view of Attendance, Marks, and Detention status.
- **Communication**: Centralized Notification Center (Bell Icon) for alerts on Leaves, Results, and Disciplinary actions.
- **Parent View**: Dedicated access for parents to view their ward's academic health and mentor contact details.

## 🛠️ Tech Stack
- **Backend**: Python (Flask)
- **Database**: PostgreSQL 13
- **ORM**: SQLAlchemy with Flask-Migrate
- **Frontend**: HTML5, Tailwind CSS, Vanilla JS (ES6+)
- **Visualization**: Chart.js
- **Reporting**: jsPDF (client-side PDF generation)
- **Infrastructure**: Docker, Docker Compose, Nginx (Reverse Proxy), Gunicorn (WSGI)

## 📱 Native Mobile Apps (Android v1, iOS later)

This backend supports **native** mobile apps via a JSON API layer.

### v1 scope (Student + Parent)

- Subject-wise attendance
- Timetable
- Leave management
- Result view (published by faculty)
- Notifications (event participation/involvement, detention notice, general notices)

Parent supports **multiple children** and a combined notifications feed with a child filter.

### Mobile API foundation (new)

- `POST /api/v1/auth/login` → Bearer `access_token` + `refresh_token`
- `POST /api/v1/auth/refresh` → new `access_token`
- `GET /api/v1/me` → authenticated profile (+ children for parent)
- `GET /api/v1/parent/children` → list linked children
- `GET /api/v1/notifications?limit=50&child_id=<optional>` → in-app feed
- `POST /api/v1/notifications/<id>/read` → mark read
- `POST /api/v1/push/register` → register FCM token
- `POST /api/v1/push/unregister` → unregister token

### Mobile v1 feature endpoints

Student:

- `GET /api/v1/student/attendance/subjects`
- `GET /api/v1/student/timetable`
- `GET /api/v1/student/leaves`
- `POST /api/v1/student/leaves`
- `GET /api/v1/student/results`

Parent (child-scoped):

- `GET /api/v1/parent/<child_id>/attendance/subjects`
- `GET /api/v1/parent/<child_id>/timetable`
- `GET /api/v1/parent/<child_id>/leaves`
- `POST /api/v1/parent/<child_id>/leaves`
- `GET /api/v1/parent/<child_id>/results`

All `/api/v1/*` endpoints use `Authorization: Bearer <access_token>`.

### Configuration

- `SECRET_KEY` (required in production)
- Optional:
  - `MOBILE_ACCESS_TOKEN_TTL_SECONDS` (default 1800)
  - `MOBILE_REFRESH_TOKEN_TTL_DAYS` (default 30)

## ⚙️ Installation & Setup

### Prerequisites
- Docker Desktop installed and running.

### 1. Clone & Configure
```bash
git clone https://github.com/yourusername/edumatrix-ams.git
cd edumatrix-ams
```

### 2. Launch with Docker (Production Mode)
This spins up the Web App, PostgreSQL Database, and Nginx Proxy.
```bash
docker compose up --build
```
Access the app at http://localhost

## 🚢 Click-to-Deploy (GitHub Actions + GHCR + Ubuntu)

This repo includes a manual (“click to deploy”) pipeline that:
- builds the Docker image on GitHub Actions
- pushes it to GitHub Container Registry (GHCR)
- SSHes into your Ubuntu server and runs Docker Compose

### 1) Server prerequisites (one-time)
On your Ubuntu server:

```bash
# Docker
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow your deploy user to run docker without sudo (optional)
sudo usermod -aG docker $USER
```

Pick a deploy folder, for example:
```bash
sudo mkdir -p /opt/ams
sudo chown -R $USER:$USER /opt/ams
mkdir -p /opt/ams/secrets
```

### 2) GitHub Container Registry (GHCR)
The workflow builds and pushes these tags:
- `ghcr.io/<owner>/<repo>:<sha>`
- `ghcr.io/<owner>/<repo>:latest`

### 3) GitHub Secrets you must add
In your GitHub repo: Settings → Secrets and variables → Actions → New repository secret:

- `SSH_HOST` → server IP / hostname
- `SSH_PORT` → usually `22`
- `SSH_USER` → ubuntu user (e.g. `ubuntu`)
- `SSH_PRIVATE_KEY` → private key for SSH (multi-line)
- `DEPLOY_PATH` → e.g. `/opt/ams`

If your server is not publicly reachable (example: you access it only via Tailscale), add:
- `TAILSCALE_AUTHKEY` → Tailscale auth key for GitHub Actions runner
  - Create it in Tailscale Admin Console → Settings/Keys → Generate auth key
  - Prefer an **ephemeral** key, and rotate it if leaked
  - Set `SSH_HOST` to your server’s **Tailscale IP** (example: `100.100.x.x`)

- `GHCR_USERNAME` → usually your GitHub username or org name
- `GHCR_TOKEN` → a GitHub PAT used by the server to pull images from GHCR
  - For private images: needs at least `read:packages` and access to the repo/package (commonly `repo` for classic PATs)

- `POSTGRES_USER` → e.g. `admin`
- `POSTGRES_PASSWORD` → strong password
- `POSTGRES_DB` → e.g. `school_system`
- `SECRET_KEY` → strong random string

Firebase (push notifications) is optional. If you don't configure Firebase, the app will run normally but push notifications will be skipped.

### 4) How to deploy (manual)
Go to GitHub → Actions → **Deploy (Manual)** → Run workflow.

- Leave `image_tag` empty to deploy the current commit SHA.
- Or set `image_tag=latest` to force deploy latest.

The server runs using [docker-compose.prod.yml](docker-compose.prod.yml).

### Notes
- The dev compose file `docker-compose.yml` uses bind mounts + `--reload` for development.
- Production uses `docker-compose.prod.yml` (no source bind-mounts, no `--reload`).

### 3. Initialize Database (First Run Only)
Use migrations to create/update schema in Postgres.

Open a new terminal:
```bash
docker compose exec web python -m flask db upgrade
```

If you run `flask` locally (outside Docker), make sure `DATABASE_URL` points to Postgres.

### 4. Create Admin User (One-Time)
Since a fresh DB has no users, create an Admin account once.

Open a new terminal:
```bash
docker compose exec web python -c "import uuid; from app import app, db, UserMaster, generate_password_hash, StaffProfile; app.app_context().push(); admin_id=str(uuid.uuid4()); email='admin@mituniversity.edu.in'; db.session.add(UserMaster(user_id=admin_id, username=email, password_hash=generate_password_hash('Admin@123'), user_type='Admin', is_active=True)); db.session.add(StaffProfile(staff_id=admin_id, full_name='System Administrator', employee_code='ADMIN001', email_contact=email, designation='Admin')); db.session.commit(); print('Admin Created:', email)"
```

## 📥 CSV Imports (Bulk Uploads)
Admin → Bulk Uploads provides upload cards and matching downloadable CSV templates.

- **Download templates**:
  - `GET /api/admin/import_templates/master_class`
  - `GET /api/admin/import_templates/staff`
  - `GET /api/admin/import_templates/students`
  - `GET /api/admin/import_templates/weekly_schedule`
  - `GET /api/admin/import_templates/semester_course_structure`
  - `GET /api/admin/import_templates/subject_allocation`
  - `GET /api/admin/import_templates/rooms`

### Elective pre-registration flow (recommended)
1) Upload **Semester Course Structure** (Odd/Even)
2) Open elective windows in Admin → Electives for a target semester
3) Students submit one choice per bucket while Open/Extension
4) Close window(s): enforce min batch, extension, and final auto-balance

## 📂 Project Structure
```
AMS-flask/
├── app.py                  # Main Application Logic (API Routes)
├── sql_connection.py       # Database Models & Schema
├── requirements.txt        # Python Dependencies
├── Dockerfile              # Container Definition
├── docker-compose.yml      # Service Orchestration
├── migrations/             # Database Migration Scripts (Alembic)
├── nginx/
│   └── default.conf        # Nginx Proxy Config
├── static/
│   ├── images/             # Logos and Assets
│   └── uploads/            # (Optional) Storage for docs
└── templates/              # HTML Frontend Views
    ├── login.html
    ├── staff_dashboard.html
    ├── student_dashboard.html
    ├── admin_dashboard.html
    ├── hod_dashboard.html
    ├── marks_entry.html
    └── ... (other modules)
```

## 🧠 Logic & Algorithms

### The Intelligent Scheduler
The scheduler uses a Greedy First-Fit Algorithm with backtracking retry logic.

- **Queue Prioritization**: Labs (2-hour blocks) are scheduled first, followed by Tutorials, then Lectures.
- **Constraint Checking**:
  - Is the Teacher free?
  - Is the Student Batch free?
  - Is a Room of the correct type (Lab/Classroom) available?
  - Does the slot cross a lunch break? (Prevent 2-hour labs starting at 11:45).
- **Conflict Resolution**: If a slot fails, it logs the specific reason (Room Unavailable vs Teacher Busy) for admin review.

### Auto-Scaling Assessment
Marks are normalized to a standard 50-Mark Scale regardless of input type:
```
Total = (TA1 * 0.5) + (TA2 * 0.5) + TA3 + (Avg_Assignments * 1.5) + Attendance_Score
```

## 🔒 Security
- **Password Hashing**: Uses werkzeug.security (PBKDF2-SHA256).
- **Role-Based Access Control (RBAC)**: Middleware checks user_id and Role before serving sensitive JSON data.
- **Container Isolation**: Database is not exposed to the public internet (internal Docker network only).

## 📜 License
This project is licensed under __.

# EduMatrix AMS - Android App Feature Gap Analysis

## Executive Summary

This document analyzes modules present in the **Web App** but **missing from the Android App**, with ratings for inclusion priority in the mobile platform.

---

## Rating Scale

| Rating | Priority | Description |
|--------|----------|-------------|
| **5** | Critical | Must-have for core functionality; users expect this on mobile |
| **4** | High | Significantly improves user experience; common mobile use case |
| **3** | Medium | Nice-to-have; moderate value for mobile users |
| **2** | Low | Better suited for web; occasional mobile use |
| **1** | Skip | Not suitable for mobile; keep web-only |

---

## Current Android App Status

### Implemented Modules by Role

| Role | Implemented Features |
|------|---------------------|
| **Student** | Dashboard, Attendance, Timetable, Leaves, Results, Feedback, Notifications |
| **Staff** | Dashboard, Schedule, Attendance Marking, Session History, Leave Approvals (CT) |
| **Staff (Mentor)** | Dashboard, Mentees, Issue Logs, Meetings |
| **Staff (Event Coord)** | Events Dashboard, Create Events, Participants, Attendance |
| **Staff (Class Teacher)** | Analytics Dashboard |
| **Parent** | Dashboard, Child Attendance, Notifications |
| **Admin** | Placeholder only (not implemented) |
| **HOD** | Routes defined (not implemented) |

---

## MISSING MODULES - DETAILED ANALYSIS

---

### 1. ADMIN MODULE (Complete)

**Status**: Not implemented in Android (placeholder only)

#### 1.1 Admin Dashboard & Analytics
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Admin Overview Dashboard | `/admin/dashboard` | **3** | Quick stats useful on mobile, but full admin work better on web |
| Student Distribution Charts | `/api/admin/student_distribution` | **2** | Visualization better on larger screens |
| Archive Statistics | `/api/admin/archive_stats` | **2** | Rarely needed on-the-go |

#### 1.2 Class & Section Management
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| View Classes | `/api/admin/classes` | **3** | Reference info useful on mobile |
| Assign Class Teacher | `/api/admin/assign_teacher` | **2** | Setup task, web preferred |
| Manage Batches | `/api/admin/get_batches` | **2** | Complex UI, web preferred |

#### 1.3 Faculty Management
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Faculty List | `/api/admin/faculty_list` | **3** | Contact lookup useful on mobile |
| Add Faculty | `/api/admin/add_faculty` | **1** | Onboarding task, web only |
| Archive Faculty | `/api/admin/archive_faculty` | **1** | Administrative action, web only |

#### 1.4 Coordinator Management
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| View Coordinators | `/api/admin/coordinators` | **3** | Reference info |
| Toggle Roles | `/api/admin/toggle_role` | **2** | Role assignment better on web |

#### 1.5 Student Management
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Student Directory | `/api/admin/directory` | **4** | Frequently needed for lookups |
| Update Student Status | `/api/admin/update_student_status` | **2** | Administrative action |
| Student Promotion | `/api/admin/promote_batch` | **1** | Batch operation, web only |

#### 1.6 Mentor Assignment
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| View Mentor Hierarchy | `/api/admin/mentor_hierarchy` | **3** | Reference lookup |
| Assign Mentors | `/api/admin/assign_mentors` | **2** | Setup task |
| Auto-Split Batches | `/api/admin/auto_split_batches` | **1** | Complex operation, web only |

#### 1.7 Activity Logging
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Activity Log | `/api/admin/activity_log` | **3** | Audit trail useful for quick checks |

**Admin Module Summary**: Rating **2.3** (Low-Medium) - Most admin features are setup/management tasks better suited for web. Consider implementing a **read-only Admin Dashboard** for mobile with key stats and student/faculty directory lookup.

---

### 2. HOD MODULE

**Status**: Routes defined but not implemented

#### 2.1 HOD Dashboard & Statistics
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| HOD Dashboard | `/api/hod/dashboard` | **4** | Department stats useful on-the-go |
| Faculty Roles View | `/api/hod/faculty_roles` | **3** | Quick reference |
| Student Hierarchy | `/api/hod/student_hierarchy` | **3** | Department overview |

#### 2.2 Leave Management
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| HOD Leave Approval | `/api/hod/approve_leave` | **5** | Time-sensitive; needs mobile approval |

#### 2.3 Reports & Analysis
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Feedback Analysis | `/api/hod/feedback_analysis` | **3** | Review data, moderate mobile need |
| Syllabus Status | `/api/hod/syllabus_status` | **3** | Tracking progress |
| Archive Stats | `/api/hod/archive_stats` | **2** | Historical data, web preferred |

**HOD Module Summary**: Rating **3.4** (Medium-High) - HOD leave approvals are **critical** for mobile. Department dashboard and reports are valuable additions.

---

### 3. AMC (Academic Monitoring Committee) MODULE

**Status**: Not implemented in Android

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| AMC Dashboard | `/api/amc/dashboard` | **3** | Overview useful on mobile |
| Class CA Summary | `/api/amc/class_ca_summary` | **3** | Performance monitoring |
| Compliance Hierarchy | `/api/amc/compliance_hierarchy` | **3** | Tracking compliance |
| CA Report | `/api/amc/ca_report` | **2** | Detailed reports better on web |
| Syllabus Report | `/api/amc/syllabus_report` | **2** | Documentation review |
| Generate Term Grant | `/api/amc/generate_term_grant` | **2** | Batch operation |
| Term Grant List | `/api/amc/term_grant_list` | **3** | Status review |
| Update Grant Status | `/api/amc/update_grant_status` | **2** | Administrative action |

**AMC Module Summary**: Rating **2.5** (Low-Medium) - AMC members may benefit from a **read-only dashboard** for monitoring, but most actions are batch operations better on web.

---

### 4. MARKS ENTRY MODULE

**Status**: Web-only (noted in Android code comments)

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| View CA Sheet | `/api/marks/get_ca_sheet` | **3** | Read-only view useful |
| Submit CA Marks | `/api/marks/submit_ca` | **2** | Data entry better with keyboard |
| Bulk Upload Marks | `/api/marks/upload_csv` | **1** | File upload, web only |
| Download Template | `/api/marks/download_template` | **1** | File download, web only |

**Marks Entry Summary**: Rating **1.75** (Low) - Marks entry is data-intensive and better suited for web. Consider **read-only CA marks view** for faculty reference.

---

### 5. ELECTIVE MANAGEMENT MODULE

**Status**: Model defined but screens not implemented

#### 5.1 Student Elective Selection
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| View Elective Windows | `/api/student/elective_windows` | **5** | Time-sensitive selection |
| View Elective Options | `/api/student/get_elective_options` | **5** | Choosing electives |
| Submit Elective | `/api/student/submit_elective` | **5** | Critical action for students |

#### 5.2 Admin Elective Management
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Elective Pool Management | `/api/admin/elective_rollout/pool` | **1** | Setup, web only |
| Open/Close Windows | `/api/admin/elective_windows/*` | **2** | Administrative |
| Live Dashboard | `/api/admin/elective_windows/live_dashboard` | **3** | Monitoring progress |
| Bulk Rollout | `/api/admin/elective_rollout/bulk_*` | **1** | Batch operations |

**Student Elective Summary**: Rating **5.0** (Critical) - Students MUST be able to select electives on mobile. Time-sensitive and highly mobile use case.

**Admin Elective Summary**: Rating **1.6** (Low) - Administrative tasks better on web.

---

### 6. MDM/OE (Cross-School) MODULE

**Status**: Not implemented in Android

#### 6.1 Student MDM Outbound
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| View MDM Windows | `/api/student/mdm_outbound/windows` | **5** | Time-sensitive selection |
| Select Outbound Course | `/api/student/mdm_outbound/select` | **5** | Critical enrollment |
| View My Courses | `/api/student/mdm_outbound/my_courses` | **4** | Reference enrolled courses |

#### 6.2 Admin MDM Management
| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| MDM Pool Management | `/api/admin/mdm_rollout/pool/*` | **1** | Setup, web only |
| Inbound Course Management | `/api/admin/mdm_rollout/inbound/*` | **1** | Administrative |
| Outbound Windows | `/api/admin/mdm_rollout/outbound/*` | **2** | Administrative |
| Import Marks | `/api/admin/mdm_rollout/outbound/import_marks` | **1** | File operations |

**Student MDM Summary**: Rating **4.7** (High-Critical) - Students selecting cross-school courses is a key mobile use case.

**Admin MDM Summary**: Rating **1.25** (Low) - Complex administrative features, web only.

---

### 7. TIMETABLE MANAGEMENT (Admin)

**Status**: Not implemented in Android

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Course Structure | `/api/admin/course_structure` | **2** | Reference data |
| Generate Timetable | `/api/admin/generate_timetable` | **1** | Complex ML-based, web only |
| Timetable Versions | `/api/admin/timetable_versions` | **2** | Version management |
| Publish Timetable | `/api/admin/timetable_versions/publish` | **2** | Administrative action |

**Timetable Management Summary**: Rating **1.75** (Low) - Timetable creation is complex and web-only. Students already have timetable view.

---

### 8. BULK UPLOAD MODULE

**Status**: Not implemented in Android

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| All Bulk Uploads | `/api/upload/*` | **1** | File operations, web only |

**Bulk Upload Summary**: Rating **1.0** (Skip) - File uploads not suitable for mobile.

---

### 9. DETENTION MANAGEMENT (Extended)

**Status**: Partially implemented (view only for students)

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Assign Detention | `/api/detention/assign` | **3** | Staff quick action |
| View Watchlist | `/api/detention/watchlist` | **4** | Staff needs quick access |
| Review List | `/api/detention/review_list` | **4** | Staff needs to review submissions |
| Release Student | `/api/detention/release` | **3** | Administrative action |

**Detention Summary**: Rating **3.5** (Medium-High) - Staff detention management is useful for quick mobile actions.

---

### 10. LESSON PLANNING & SYLLABUS

**Status**: Not implemented in Android

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Get Syllabus | `/api/academic/get_syllabus` | **3** | Reference material |
| Create Lesson Plan | `/api/academic/create_plan` | **2** | Planning better on web |
| Upload Syllabus | `/api/upload/syllabus` | **1** | File upload, web only |

**Lesson Planning Summary**: Rating **2.0** (Low) - Content creation better on web. Read-only syllabus view could be useful.

---

### 11. LOAD ADJUSTMENT (Extended)

**Status**: Partially implemented (request only)

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Find Adjustment Faculty | Implemented | ✅ | Already in app |
| Submit Adjustment | Implemented | ✅ | Already in app |
| Respond to Adjustment | Implemented | ✅ | Already in app |

**Load Adjustment Summary**: Already fully implemented in Android.

---

### 12. EXTRA SESSIONS (Extended)

**Status**: Partially implemented

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Create Extra Session | Implemented | ✅ | Already in app |
| View Extra Sessions | Implemented | ✅ | Already in app |
| Cancel Extra Session | Implemented | ✅ | Already in app |
| Mark Attendance | `/api/staff/extra_sessions/{id}/mark_attendance` | **4** | Missing - should add |

**Extra Sessions Summary**: Rating **4.0** - Add attendance marking for extra sessions.

---

### 13. SUPERADMIN MODULE

**Status**: Not implemented in Android

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| SuperAdmin Dashboard | `/superadmin/dashboard` | **2** | Rarely used on mobile |
| Hierarchy Setup | `/api/setup/hierarchy` | **1** | Initial setup, web only |
| Create Dept Admin | `/api/superadmin/dept_admin` | **1** | Administrative |
| System KPIs | `/api/superadmin/kpis` | **2** | Monitoring |

**SuperAdmin Summary**: Rating **1.5** (Low) - SuperAdmin tasks are setup-oriented, web only.

---

### 14. FEEDBACK MANAGEMENT (Admin/HOD)

**Status**: Student submission implemented; Admin features missing

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Create Feedback Cycle | `/api/admin/create_feedback_cycle` | **1** | Administrative setup |
| Feedback Status | `/api/admin/feedback_status` | **2** | Monitoring |
| Feedback Analysis (HOD) | `/api/hod/feedback_analysis` | **3** | Analysis review |

**Feedback Admin Summary**: Rating **2.0** (Low) - Admin feedback setup is web-only. HOD analysis could be mobile.

---

### 15. SYSTEM CONFIGURATION

**Status**: Not implemented in Android

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Get/Set Config | `/api/admin/system_config` | **1** | Administrative |
| Semester Rollover | `/api/admin/rollover_semester` | **1** | Major operation |
| Current Term | Implemented | ✅ | Already in app |

**System Config Summary**: Rating **1.0** (Skip) - System configuration is web-only.

---

### 16. HISTORICAL/ARCHIVE DATA

**Status**: Not implemented in Android

| Feature | Web Endpoint | Rating | Justification |
|---------|-------------|--------|---------------|
| Archived Terms | `/api/admin/archived_terms` | **2** | Historical reference |
| Archived Data | `/api/admin/archived_data` | **2** | Historical lookup |

**Archive Summary**: Rating **2.0** (Low) - Historical data access is occasional.

---

## PRIORITY IMPLEMENTATION ROADMAP

### Phase 1: Critical (Rating 5) - Must Have
| Module | Features | User Role | Effort |
|--------|----------|-----------|--------|
| **Student Elective Selection** | View windows, options, submit selection | Student | Medium |
| **Student MDM/OE Selection** | View windows, select course, my courses | Student | Medium |
| **HOD Leave Approval** | Approve/reject escalated leaves | HOD | Low |

### Phase 2: High Priority (Rating 4)
| Module | Features | User Role | Effort |
|--------|----------|-----------|--------|
| **HOD Dashboard** | Department stats, faculty overview | HOD | Medium |
| **Admin Student Directory** | Search and view students | Admin | Low |
| **Staff Detention Management** | Watchlist, review submissions | Staff | Medium |
| **Extra Session Attendance** | Mark attendance for extra sessions | Staff | Low |
| **Student MDM Course View** | View enrolled outbound courses | Student | Low |

### Phase 3: Medium Priority (Rating 3)
| Module | Features | User Role | Effort |
|--------|----------|-----------|--------|
| **AMC Dashboard** | Read-only monitoring dashboard | AMC | Medium |
| **Admin Dashboard** | Key stats, quick overview | Admin | Medium |
| **Faculty Directory** | Contact lookup | Admin | Low |
| **Syllabus View** | Read-only syllabus reference | Staff | Low |
| **Activity Log** | Audit trail viewer | Admin | Low |

### Phase 4: Low Priority (Rating 2) - Consider Later
| Module | Features | User Role | Effort |
|--------|----------|-----------|--------|
| Read-only CA Marks View | View marks sheet | Staff | Low |
| Feedback Analysis | View feedback results | HOD | Medium |
| Archived Data Viewer | Historical lookup | Admin | Low |

### Phase 5: Skip for Mobile (Rating 1)
- All bulk upload features
- Timetable generation
- System configuration
- SuperAdmin setup
- Marks entry (data input)
- Complex batch operations

---

## SUMMARY TABLE

| Module | Current Status | Avg Rating | Recommendation |
|--------|---------------|------------|----------------|
| Student Elective Selection | Not implemented | **5.0** | **CRITICAL - Implement immediately** |
| Student MDM/OE Selection | Not implemented | **4.7** | **HIGH - Implement soon** |
| HOD Leave Approval | Not implemented | **5.0** | **CRITICAL - Single feature, easy win** |
| HOD Dashboard | Not implemented | **3.4** | Implement with leave approval |
| Staff Detention Mgmt | Partial | **3.5** | Add staff features |
| Extra Session Attendance | Missing | **4.0** | Quick addition |
| AMC Dashboard | Not implemented | **2.5** | Read-only dashboard |
| Admin Dashboard | Placeholder | **2.3** | Basic stats + directory |
| Marks Entry | Web-only | **1.75** | Keep web-only |
| Admin Elective Mgmt | Not implemented | **1.6** | Web-only |
| Admin MDM Mgmt | Not implemented | **1.25** | Web-only |
| Timetable Mgmt | Not implemented | **1.75** | Web-only |
| Bulk Uploads | Not implemented | **1.0** | Web-only |
| SuperAdmin | Not implemented | **1.5** | Web-only |
| System Config | Not implemented | **1.0** | Web-only |

---

## RECOMMENDED IMMEDIATE ACTIONS

1. **Student Elective Selection** (Rating 5.0)
   - Implement `StudentElectiveScreen` with window view and selection
   - Add to student navigation
   - Time-sensitive feature during enrollment periods

2. **Student MDM/OE Selection** (Rating 4.7)
   - Implement `StudentMDMScreen` for cross-school courses
   - Similar flow to elective selection
   - Show enrolled courses

3. **HOD Leave Approval** (Rating 5.0)
   - Add `HodLeaveApprovalScreen`
   - Integrate with existing leave models
   - Push notifications for pending approvals

4. **Extra Session Attendance** (Rating 4.0)
   - Add attendance marking to existing extra session flow
   - Reuse `StaffMarkAttendanceScreen` pattern

---

## TECHNICAL NOTES

### API Endpoints Already Available
All required endpoints exist in the web backend. Android implementation only needs:
- UI screens (Jetpack Compose)
- API calls in `ApiService.kt`
- Navigation routes in `NavRoutes.kt`
- Data models (most already defined)

### Estimated Development Effort
| Priority | Features | Estimated Days |
|----------|----------|----------------|
| Phase 1 (Critical) | 3 features | 5-7 days |
| Phase 2 (High) | 5 features | 7-10 days |
| Phase 3 (Medium) | 6 features | 8-12 days |
| **Total for valuable mobile features** | 14 features | **20-29 days** |

---

*Document generated: January 2026*
*Analysis based on: EduMatrix AMS Web App (Flask) vs Android App (Kotlin/Compose)*

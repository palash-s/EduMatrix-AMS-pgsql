# EduMatrix AMS Android App - Complete Implementation Plan

## Executive Summary

This document outlines the complete implementation plan for the EduMatrix AMS Android application to support **all stakeholders** (Admin, Staff, Student, Parent) with the **exact same design principles and UI** as the web application.

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Architecture Overview](#architecture-overview)
3. [Technology Stack](#technology-stack)
4. [Design System](#design-system)
5. [Implementation Phases](#implementation-phases)
6. [Staff Portal Implementation](#staff-portal-implementation)
7. [Parent Portal Implementation](#parent-portal-implementation)
8. [Student Portal Enhancements](#student-portal-enhancements)
9. [Admin Portal Implementation](#admin-portal-implementation)
10. [Testing Strategy](#testing-strategy)
11. [How to Preview in Android Studio](#how-to-preview-in-android-studio)

---

## 1. Current State Analysis

### What Exists

| Component | Status | Notes |
|-----------|--------|-------|
| Login Screen | ✅ Complete | Student-only, needs multi-role support |
| Student Dashboard | ✅ Basic | Missing many features |
| Attendance View | ✅ Basic | Text-only, needs visual ring |
| Timetable View | ✅ Basic | Text-only list |
| Leaves Screen | ✅ Basic | Form + history |
| Results Screen | ✅ Basic | Text-only |
| Notifications | ✅ Basic | Text-only list |
| Push Notifications | ✅ Complete | Firebase integrated |

### What's Missing

- **Staff Portal**: Entire module (0%)
- **Parent Portal**: Entire module (0%)
- **Admin Portal**: Entire module (0%)
- **Multi-role Login**: Not implemented
- **Role-based Navigation**: Not implemented
- **Enhanced UI Components**: Progress rings, cards, modals
- **Offline Support**: Not implemented
- **Proper Architecture**: No MVVM, no ViewModels

---

## 2. Architecture Overview

### Current Architecture (Monolithic)
```
MainActivity.kt (800+ lines)
├── All screens as @Composable functions
├── Direct API calls in UI
├── No separation of concerns
└── Hard to maintain/test
```

### Target Architecture (MVVM + Clean Architecture)
```
com.eduMatrix.ams/
├── data/
│   ├── api/
│   │   ├── ApiClient.kt (HTTP client)
│   │   ├── AuthApi.kt
│   │   ├── StaffApi.kt
│   │   ├── StudentApi.kt
│   │   └── ParentApi.kt
│   ├── models/
│   │   ├── User.kt
│   │   ├── Attendance.kt
│   │   ├── Session.kt
│   │   └── ... (all data classes)
│   └── repository/
│       ├── AuthRepository.kt
│       ├── StaffRepository.kt
│       └── ...
├── domain/
│   └── usecase/ (optional for complex logic)
├── ui/
│   ├── theme/
│   │   ├── Color.kt
│   │   ├── Type.kt
│   │   ├── Theme.kt
│   │   └── Shapes.kt
│   ├── components/
│   │   ├── AttendanceRing.kt
│   │   ├── StatCard.kt
│   │   ├── SubjectCard.kt
│   │   ├── LoadingOverlay.kt
│   │   └── ... (reusable components)
│   ├── navigation/
│   │   ├── NavRoutes.kt
│   │   ├── MainNavigation.kt
│   │   └── RoleBasedNavigation.kt
│   ├── auth/
│   │   ├── LoginScreen.kt
│   │   ├── LoginViewModel.kt
│   │   └── ChangePasswordScreen.kt
│   ├── student/
│   │   ├── StudentDashboard.kt
│   │   ├── StudentViewModel.kt
│   │   └── screens/
│   ├── staff/
│   │   ├── StaffDashboard.kt
│   │   ├── StaffViewModel.kt
│   │   ├── attendance/
│   │   ├── marks/
│   │   ├── leaves/
│   │   └── screens/
│   ├── parent/
│   │   ├── ParentDashboard.kt
│   │   ├── ParentViewModel.kt
│   │   └── screens/
│   └── admin/
│       ├── AdminDashboard.kt
│       └── screens/
├── utils/
│   ├── DateUtils.kt
│   ├── Extensions.kt
│   └── Constants.kt
└── MainActivity.kt (minimal, just sets up navigation)
```

---

## 3. Technology Stack

### Core Dependencies (Already Present)
- **Jetpack Compose** - Declarative UI framework
- **Material 3** - Design system
- **Navigation Compose** - In-app navigation
- **OkHttp** - HTTP client
- **Firebase Messaging** - Push notifications

### To Add
```kotlin
// ViewModel support
implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")

// Coroutines for async operations
implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

// JSON parsing (replace manual org.json)
implementation("com.google.code.gson:gson:2.11.0")

// Image loading (for avatars, logos)
implementation("io.coil-kt:coil-compose:2.7.0")

// Date/Time picker
implementation("com.maxkeppeler.sheets-compose-dialogs:core:1.3.0")
implementation("com.maxkeppeler.sheets-compose-dialogs:calendar:1.3.0")

// Pull-to-refresh
implementation("androidx.compose.material3:material3:1.3.0")

// Icons (Material Icons Extended)
implementation("androidx.compose.material:material-icons-extended:1.7.0")
```

---

## 4. Design System

### Brand Colors (Matching Web)
```kotlin
// Primary
val MitPurple = Color(0xFF48166D)      // Primary brand
val MitPurpleDark = Color(0xFF2D0D45)  // Dark variant
val MitPurpleHover = Color(0xFF350F50) // Hover state

// Secondary
val MitTeal = Color(0xFF00A887)        // Success, progress
val MitOrange = Color(0xFFF17736)      // Warning, alerts
val MitGold = Color(0xFFBF9D55)        // Accent

// Backgrounds
val AppBackgroundLight = Color(0xFFF8FAFC) // Slate-50
val SurfaceLight = Color(0xFFFFFFFF)       // White
val AppBackgroundDark = Color(0xFF0B1220)  // Dark navy

// Status Colors
val StatusGreen = Color(0xFF22C55E)    // Present, Success
val StatusRed = Color(0xFFEF4444)      // Absent, Error
val StatusYellow = Color(0xFFF59E0B)   // Warning
val StatusBlue = Color(0xFF3B82F6)     // Info
```

### Typography (Matching Web)
```kotlin
val Typography = Typography(
    // Headlines - Merriweather-like feel
    headlineLarge = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize = 32.sp,
        lineHeight = 40.sp
    ),
    headlineMedium = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize = 28.sp,
        lineHeight = 36.sp
    ),
    // Titles
    titleLarge = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 22.sp,
        lineHeight = 28.sp
    ),
    titleMedium = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        lineHeight = 24.sp
    ),
    // Body
    bodyLarge = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 24.sp
    ),
    bodyMedium = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp
    ),
    bodySmall = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 12.sp,
        lineHeight = 16.sp
    ),
    // Labels
    labelLarge = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 14.sp,
        lineHeight = 20.sp
    )
)
```

### Spacing System (4dp base)
```kotlin
object Spacing {
    val xs = 4.dp
    val sm = 8.dp
    val md = 12.dp
    val lg = 16.dp
    val xl = 24.dp
    val xxl = 32.dp
}
```

### Common UI Components

#### 1. StatCard (Dashboard Stats)
```
┌─────────────────────┐
│ 🎓  245             │
│ Total Students      │
└─────────────────────┘
```

#### 2. AttendanceRing (SVG Circle)
```
     ╭───────╮
    ╱  78.5%  ╲
   │           │
    ╲  /100   ╱
     ╰───────╯
```

#### 3. SubjectCard (Performance)
```
┌─────────────────────────────────┐
│ Data Structures                 │
│ CS301 • Dr. Sharma              │
│ ████████████░░░░░░░░  85%       │
│ 34/40 lectures                  │
└─────────────────────────────────┘
```

#### 4. SessionCard (Today's Classes)
```
┌─────────────────────────────────┐
│ 09:00 - 10:00                   │
│ ┌─────────────────────────────┐ │
│ │ 🟣 Data Structures          │ │
│ │    Room 301 • FY-A          │ │
│ │    [Mark Attendance]        │ │
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

---

## 5. Implementation Phases

### Phase 1: Architecture & Multi-Role Login (Week 1)
- [ ] Restructure project to MVVM architecture
- [ ] Add new dependencies (ViewModel, Gson, Coil)
- [ ] Create reusable UI components
- [ ] Implement multi-role login (Staff, Student, Parent, Admin)
- [ ] Store user role in preferences
- [ ] Role-based navigation routing

### Phase 2: Staff Dashboard & Navigation (Week 1-2)
- [ ] Staff main dashboard with role-aware cards
- [ ] Today's schedule display
- [ ] Quick action buttons
- [ ] Stats overview (sessions, students)
- [ ] Notifications integration

### Phase 3: Staff - Attendance Marking (Week 2)
- [ ] Class/Subject selection
- [ ] Student list with checkboxes
- [ ] Mark All Present/Absent
- [ ] Topic selection (lesson linking)
- [ ] Session history view
- [ ] Submit attendance API

### Phase 4: Staff - Marks Entry (Week 2-3)
- [ ] Subject/Section selection
- [ ] Tabbed interface (TA1, TA2, TA3, Summary)
- [ ] Score input grid
- [ ] CSV upload capability
- [ ] Save draft / Publish actions
- [ ] Student learner classification display

### Phase 5: Staff - Leave Management (Week 3)
- [ ] Pending leave requests list
- [ ] Leave details modal
- [ ] Approve/Reject/Escalate actions
- [ ] Leave history view

### Phase 6: Class Teacher Features (Week 3)
- [ ] Class teacher dashboard
- [ ] Section analytics
- [ ] Subject-wise reports
- [ ] Overall attendance summary
- [ ] Student issue tracking

### Phase 7: HOD Features (Week 4)
- [ ] HOD dashboard
- [ ] Department faculty list
- [ ] Faculty performance metrics
- [ ] Long leave approvals
- [ ] Feedback analysis view
- [ ] Syllabus progress tracking

### Phase 8: Mentor Features (Week 4)
- [ ] My mentees list
- [ ] Counseling log entry
- [ ] Issue categorization
- [ ] Meeting scheduler
- [ ] Progress tracking

### Phase 9: Event Coordinator Features (Week 5)
- [ ] Event creation form
- [ ] Student nomination
- [ ] Event attendance marking
- [ ] Event history

### Phase 10: Parent Portal (Week 5-6)
- [ ] Multi-child selector
- [ ] Per-child dashboard
- [ ] Attendance tracking
- [ ] Results viewing
- [ ] Leave application for child
- [ ] Mentor contact info

### Phase 11: Student Portal Enhancements (Week 6)
- [ ] Visual attendance ring
- [ ] Subject performance cards
- [ ] Detention alerts & submission
- [ ] Feedback submission
- [ ] Elective selection
- [ ] Mentor info & meetings
- [ ] Event participation

### Phase 12: Admin Portal (Week 7-8)
- [ ] Admin dashboard with system stats
- [ ] Faculty management
- [ ] Student directory
- [ ] Class management
- [ ] Basic timetable view
- [ ] (Note: Complex admin features like bulk uploads better suited for web)

### Phase 13: Polish & Testing (Week 8)
- [ ] Loading states & skeletons
- [ ] Error handling & retry
- [ ] Offline indicators
- [ ] Pull-to-refresh everywhere
- [ ] Unit tests
- [ ] UI tests
- [ ] Performance optimization

---

## 6. Staff Portal Implementation (Detailed)

### 6.1 API Endpoints Required

```
Authentication:
POST /api/v1/auth/login          → Login (role detection)

Staff Dashboard:
GET  /api/staff/dashboard        → Dashboard data with role flags

Attendance:
GET  /api/attendance/sheet       → Get attendance sheet for session
POST /api/attendance/submit      → Submit attendance

Marks:
GET  /api/marks/get_ca_sheet     → Get CA marks for subject/section
POST /api/marks/submit_ca        → Submit CA marks

Leaves:
GET  /api/staff/leave_requests   → Pending leave requests
POST /api/staff/leave_action     → Approve/reject leave

Class Teacher:
GET  /api/class_teacher/analytics       → Section analytics
GET  /api/class_teacher/subject_report  → Subject breakdown
GET  /api/class_teacher/overall_summary → Overall summary

HOD:
GET  /api/hod/dashboard          → HOD dashboard data
GET  /api/hod/faculty_roles      → Faculty role assignments
POST /api/hod/approve_leave      → Approve long leaves

Mentor:
GET  /api/staff/my_mentees       → My mentee batch
POST /api/mentor/add_log         → Add counseling log
POST /api/mentor/schedule_meeting→ Schedule meeting
GET  /api/mentor/get_meetings    → Get meetings
```

### 6.2 Screen Flow

```
Login → Role Detection
         │
         ├─► Student → Student Dashboard
         │
         ├─► Parent → Parent Dashboard (child selector)
         │
         ├─► Admin → Admin Dashboard
         │
         └─► Staff → Staff Dashboard
                     │
                     ├── Today's Classes
                     ├── Mark Attendance → Student List → Submit
                     ├── Marks Entry → Subject Select → Score Grid
                     ├── Leave Approvals → List → Detail → Action
                     │
                     ├── [If Class Teacher]
                     │   └── Class Dashboard → Analytics
                     │
                     ├── [If HOD]
                     │   └── HOD Dashboard → Faculty → Approvals
                     │
                     └── [If Mentor]
                         └── My Mentees → Logs → Meetings
```

### 6.3 Staff Dashboard Layout

```
┌────────────────────────────────────────┐
│ ≡  Staff Dashboard            🔔  👤  │
├────────────────────────────────────────┤
│                                        │
│  Good Morning, Dr. Sharma              │
│  Department of Computer Science        │
│                                        │
│  ┌──────────┐ ┌──────────┐            │
│  │ 📚 12    │ │ 👥 180   │            │
│  │ Subjects │ │ Students │            │
│  └──────────┘ └──────────┘            │
│  ┌──────────┐ ┌──────────┐            │
│  │ ✅ 45    │ │ 📋 3     │            │
│  │ Sessions │ │ Pending  │            │
│  └──────────┘ └──────────┘            │
│                                        │
│  Today's Schedule                      │
│  ┌────────────────────────────────┐   │
│  │ 09:00  Data Structures  FY-A  │   │
│  │        [Mark Attendance]       │   │
│  ├────────────────────────────────┤   │
│  │ 11:00  Algorithms       SY-B  │   │
│  │        [Mark Attendance]       │   │
│  └────────────────────────────────┘   │
│                                        │
│  Quick Actions                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ │
│  │ Marks   │ │ Leaves  │ │ Mentor  │ │
│  │ Entry   │ │ Approve │ │ Logs    │ │
│  └─────────┘ └─────────┘ └─────────┘ │
│                                        │
├────────────────────────────────────────┤
│  🏠    📊    📅    📋    ⚙️          │
│ Home  Analytics Time  Tasks  Settings  │
└────────────────────────────────────────┘
```

---

## 7. Parent Portal Implementation

### 7.1 Key Features
- Multi-child support (parent can have multiple children)
- Per-child attendance view
- Per-child results view
- Apply leave on behalf of child
- Mentor contact information
- Notifications combined with child filter

### 7.2 Screen Flow
```
Login → Parent Dashboard
              │
              ├── Child Selector (dropdown/tabs)
              │
              ├── Selected Child Dashboard
              │   ├── Attendance Ring
              │   ├── Subject Performance
              │   ├── Recent Activity
              │   └── Term Grant Status
              │
              ├── Apply Leave (for child)
              │
              ├── View Results
              │
              └── Mentor Info
```

---

## 8. Student Portal Enhancements

### Missing Features to Add
1. **Visual Attendance Ring** - SVG circular progress
2. **Subject Performance Cards** - With progress bars
3. **Detention Alerts** - With task submission modal
4. **Feedback Submission** - Rating teachers
5. **Elective Selection** - When windows are open
6. **Mentor Info** - Contact and meeting schedule
7. **Event Participation** - History with roles
8. **Activity Timeline** - Recent attendance history

---

## 9. Admin Portal Implementation

### Features (Mobile-Appropriate)
- Dashboard with system statistics
- Faculty directory (view)
- Student directory (view/search)
- Class sections (view)
- Timetable (view)
- Notifications management

### Features NOT for Mobile
- Bulk CSV uploads (use web)
- Timetable generation (complex, use web)
- System configuration (use web)

---

## 10. Testing Strategy

### Unit Tests
- ViewModel logic tests
- Repository tests with mock API
- Utility function tests

### UI Tests
- Screen navigation tests
- Form validation tests
- Component rendering tests

### Integration Tests
- End-to-end login flow
- Attendance submission flow
- Leave approval flow

---

## 11. How to Preview in Android Studio

### Step 1: Open the Project
1. Open Android Studio
2. Click **File → Open**
3. Navigate to `E:\feature-AMS\EduMatrix-AMS-pgsql\AMS-android`
4. Click **OK** and wait for Gradle sync

### Step 2: Wait for Gradle Sync
- Bottom bar shows "Gradle sync" progress
- Wait until it shows "BUILD SUCCESSFUL"
- If errors, click **Try Again** or **Sync Now**

### Step 3: Run on Emulator
1. Click **Tools → Device Manager** (or AVD Manager icon)
2. If no device, click **Create Device**:
   - Choose **Pixel 6** or similar
   - Select **API 34** (Android 14) system image
   - Click **Finish**
3. Click the **Play** button (▶️) on the device to start it
4. Wait for emulator to fully boot

### Step 4: Run the App
1. Select your emulator from the device dropdown (top toolbar)
2. Click the green **Run** button (▶️) or press **Shift+F10**
3. Wait for the app to build and install
4. App will automatically open on the emulator

### Step 5: Use Compose Preview
1. Open any Composable file (e.g., `MainActivity.kt`)
2. Add a preview function:
```kotlin
@Preview(showBackground = true)
@Composable
fun PreviewLoginScreen() {
    AMSandroidTheme {
        LoginScreen(onLoginSuccess = {})
    }
}
```
3. Click **Split** or **Design** tab on the right
4. Click **Build & Refresh** to see the preview

### Step 6: Hot Reload (Apply Changes)
1. Make a code change
2. Click **Apply Changes** (⚡ icon) or press **Ctrl+F10**
3. Changes apply without full rebuild

### Troubleshooting

**"Gradle sync failed"**
- Check internet connection
- Click **File → Invalidate Caches / Restart**
- Delete `.gradle` folder and re-sync

**"No devices available"**
- Open Device Manager and start an emulator
- Or connect a physical Android device with USB debugging enabled

**"App crashes on launch"**
- Check Logcat (View → Tool Windows → Logcat)
- Look for red error messages
- Common issue: API_BASE_URL needs to be correct for emulator

**"Cannot connect to API"**
- Emulator uses `10.0.2.2` to reach host machine
- Ensure backend is running on `localhost:5000`
- Check if firewall is blocking

---

## Appendix: File Naming Conventions

### Kotlin Files
- **Screens**: `{Feature}Screen.kt` (e.g., `StaffDashboardScreen.kt`)
- **ViewModels**: `{Feature}ViewModel.kt` (e.g., `StaffViewModel.kt`)
- **Components**: `{ComponentName}.kt` (e.g., `AttendanceRing.kt`)
- **API**: `{Feature}Api.kt` (e.g., `StaffApi.kt`)
- **Repository**: `{Feature}Repository.kt`
- **Models**: `{ModelName}.kt` (e.g., `Session.kt`)

### Packages
- `ui.{feature}` - Feature screens and ViewModels
- `ui.components` - Reusable composables
- `data.api` - API client and endpoints
- `data.models` - Data classes
- `data.repository` - Data layer
- `utils` - Helper functions

---

## Next Steps

1. ✅ Read and understand this plan
2. ⏳ Start Phase 1: Architecture restructure
3. ⏳ Implement multi-role login
4. ⏳ Build Staff Dashboard
5. ⏳ Continue with remaining phases

**Questions?** The implementation will include detailed comments and step-by-step guidance for each feature.

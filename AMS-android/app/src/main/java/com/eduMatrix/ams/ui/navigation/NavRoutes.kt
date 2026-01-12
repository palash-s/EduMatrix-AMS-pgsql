package com.eduMatrix.ams.ui.navigation

/**
 * Navigation routes for the app.
 * Organized by feature/role for clarity.
 */
object NavRoutes {
    // ========================================
    // AUTHENTICATION
    // ========================================
    const val LOGIN = "login"
    const val CHANGE_PASSWORD = "change_password"

    // ========================================
    // ROLE-BASED MAIN SHELLS
    // ========================================
    const val STUDENT_MAIN = "student_main"
    const val STAFF_MAIN = "staff_main"
    const val PARENT_MAIN = "parent_main"
    const val ADMIN_MAIN = "admin_main"

    // ========================================
    // STUDENT TABS
    // ========================================
    const val STUDENT_DASHBOARD = "student_dashboard"
    const val STUDENT_ATTENDANCE = "student_attendance"
    const val STUDENT_TIMETABLE = "student_timetable"
    const val STUDENT_LEAVES = "student_leaves"
    const val STUDENT_RESULTS = "student_results"
    const val STUDENT_NOTIFICATIONS = "student_notifications"
    const val STUDENT_EVENTS = "student_events"
    const val STUDENT_ELECTIVES = "student_electives"
    const val STUDENT_MDM = "student_mdm"
    const val STUDENT_FEEDBACK = "student_feedback"

    // ========================================
    // STAFF TABS
    // ========================================
    const val STAFF_DASHBOARD = "staff_dashboard"
    const val STAFF_SCHEDULE = "staff_schedule"
    const val STAFF_ATTENDANCE = "staff_attendance"
    const val STAFF_MARKS = "staff_marks"
    const val STAFF_LEAVES = "staff_leaves"
    const val STAFF_NOTIFICATIONS = "staff_notifications"

    // Staff sub-screens
    const val STAFF_MARK_ATTENDANCE = "staff_mark_attendance/{scheduleId}/{date}"
    const val STAFF_MARKS_ENTRY = "staff_marks_entry/{allocationId}"
    const val STAFF_LEAVE_DETAIL = "staff_leave_detail/{leaveId}"
    const val STAFF_SESSION_HISTORY = "staff_session_history"

    // ========================================
    // CLASS TEACHER SCREENS
    // ========================================
    const val CLASS_TEACHER_DASHBOARD = "class_teacher_dashboard"
    const val CLASS_TEACHER_ANALYTICS = "class_teacher_analytics"
    const val CLASS_TEACHER_STUDENTS = "class_teacher_students"

    // ========================================
    // HOD SCREENS
    // ========================================
    const val HOD_DASHBOARD = "hod_dashboard"
    const val HOD_FACULTY = "hod_faculty"
    const val HOD_LONG_LEAVES = "hod_long_leaves"
    const val HOD_LEAVE_APPROVALS = "hod_leave_approvals"
    const val HOD_FEEDBACK = "hod_feedback"
    const val HOD_SYLLABUS = "hod_syllabus"

    // ========================================
    // MENTOR SCREENS
    // ========================================
    const val MENTOR_DASHBOARD = "mentor_dashboard"
    const val MENTOR_MENTEES = "mentor_mentees"
    const val MENTOR_LOGS = "mentor_logs"
    const val MENTOR_MEETINGS = "mentor_meetings"
    const val MENTOR_ADD_LOG = "mentor_add_log/{studentId}"
    const val MENTOR_SCHEDULE_MEETING = "mentor_schedule_meeting"

    // ========================================
    // EVENT COORDINATOR SCREENS
    // ========================================
    const val EVENT_DASHBOARD = "event_dashboard"
    const val EVENT_DETAIL = "event_detail/{eventId}"
    const val EVENT_CREATE = "event_create"
    const val EVENT_PARTICIPANTS = "event_participants/{eventId}"

    // ========================================
    // PARENT TABS
    // ========================================
    const val PARENT_DASHBOARD = "parent_dashboard"
    const val PARENT_CHILD_DETAIL = "parent_child_detail/{childId}"
    const val PARENT_CHILD_ATTENDANCE = "parent_child_attendance/{childId}"
    const val PARENT_CHILD_TIMETABLE = "parent_child_timetable/{childId}"
    const val PARENT_CHILD_RESULTS = "parent_child_results/{childId}"
    const val PARENT_CHILD_LEAVES = "parent_child_leaves/{childId}"
    const val PARENT_NOTIFICATIONS = "parent_notifications"

    // ========================================
    // ADMIN TABS
    // ========================================
    const val ADMIN_DASHBOARD = "admin_dashboard"
    const val ADMIN_FACULTY = "admin_faculty"
    const val ADMIN_STUDENTS = "admin_students"
    const val ADMIN_CLASSES = "admin_classes"
    const val ADMIN_NOTIFICATIONS = "admin_notifications"

    // ========================================
    // HELPER FUNCTIONS
    // ========================================

    /**
     * Create route for marking attendance with schedule ID and date.
     * scheduleId can be an integer (regular schedule) or "extra_X" for extra sessions.
     */
    fun staffMarkAttendance(scheduleId: String, date: String): String {
        return "staff_mark_attendance/$scheduleId/$date"
    }

    /**
     * Create route for marks entry with allocation ID.
     */
    fun staffMarksEntry(allocationId: Int): String {
        return "staff_marks_entry/$allocationId"
    }

    /**
     * Create route for leave detail.
     */
    fun staffLeaveDetail(leaveId: Int): String {
        return "staff_leave_detail/$leaveId"
    }

    /**
     * Create route for parent child detail.
     */
    fun parentChildDetail(childId: Int): String {
        return "parent_child_detail/$childId"
    }

    /**
     * Create route for mentor add log.
     */
    fun mentorAddLog(studentId: String): String {
        return "mentor_add_log/$studentId"
    }

    /**
     * Create route for event detail.
     */
    fun eventDetail(eventId: Int): String {
        return "event_detail/$eventId"
    }

    /**
     * Create route for event participants.
     */
    fun eventParticipants(eventId: Int): String {
        return "event_participants/$eventId"
    }
}

/**
 * Tab items for bottom navigation.
 */
sealed class BottomNavItem(
    val route: String,
    val title: String,
    val iconName: String // We'll use Material Icons
) {
    // Student tabs
    object StudentDashboard : BottomNavItem(NavRoutes.STUDENT_DASHBOARD, "Home", "home")
    object StudentAttendance : BottomNavItem(NavRoutes.STUDENT_ATTENDANCE, "Attendance", "check_circle")
    object StudentTimetable : BottomNavItem(NavRoutes.STUDENT_TIMETABLE, "Schedule", "calendar_month")
    object StudentLeaves : BottomNavItem(NavRoutes.STUDENT_LEAVES, "Leaves", "event_busy")
    object StudentResults : BottomNavItem(NavRoutes.STUDENT_RESULTS, "Results", "assessment")
    object StudentNotifications : BottomNavItem(NavRoutes.STUDENT_NOTIFICATIONS, "Alerts", "notifications")

    // Staff tabs
    object StaffDashboard : BottomNavItem(NavRoutes.STAFF_DASHBOARD, "Home", "home")
    object StaffSchedule : BottomNavItem(NavRoutes.STAFF_SCHEDULE, "Schedule", "calendar_month")
    object StaffAttendance : BottomNavItem(NavRoutes.STAFF_ATTENDANCE, "Attendance", "how_to_reg")
    object StaffMarks : BottomNavItem(NavRoutes.STAFF_MARKS, "Marks", "grading")
    object StaffLeaves : BottomNavItem(NavRoutes.STAFF_LEAVES, "Leaves", "event_busy")

    // Parent tabs
    object ParentDashboard : BottomNavItem(NavRoutes.PARENT_DASHBOARD, "Home", "home")
    object ParentNotifications : BottomNavItem(NavRoutes.PARENT_NOTIFICATIONS, "Alerts", "notifications")

    // Admin tabs
    object AdminDashboard : BottomNavItem(NavRoutes.ADMIN_DASHBOARD, "Home", "home")
    object AdminFaculty : BottomNavItem(NavRoutes.ADMIN_FACULTY, "Faculty", "people")
    object AdminStudents : BottomNavItem(NavRoutes.ADMIN_STUDENTS, "Students", "school")
    object AdminClasses : BottomNavItem(NavRoutes.ADMIN_CLASSES, "Classes", "class")
}

/**
 * Get bottom navigation items based on user role.
 */
fun getBottomNavItems(role: com.eduMatrix.ams.data.models.UserRole): List<BottomNavItem> {
    return when (role) {
        com.eduMatrix.ams.data.models.UserRole.STUDENT -> listOf(
            BottomNavItem.StudentDashboard,
            BottomNavItem.StudentAttendance,
            BottomNavItem.StudentTimetable,
            BottomNavItem.StudentLeaves,
            BottomNavItem.StudentResults
        )
        com.eduMatrix.ams.data.models.UserRole.STAFF -> listOf(
            BottomNavItem.StaffDashboard,
            BottomNavItem.StaffSchedule,
            BottomNavItem.StaffAttendance,
            BottomNavItem.StaffMarks,
            BottomNavItem.StaffLeaves
        )
        com.eduMatrix.ams.data.models.UserRole.PARENT -> listOf(
            BottomNavItem.ParentDashboard,
            BottomNavItem.ParentNotifications
        )
        com.eduMatrix.ams.data.models.UserRole.ADMIN -> listOf(
            BottomNavItem.AdminDashboard,
            BottomNavItem.AdminFaculty,
            BottomNavItem.AdminStudents,
            BottomNavItem.AdminClasses
        )
    }
}

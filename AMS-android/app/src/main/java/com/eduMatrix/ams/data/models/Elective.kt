package com.eduMatrix.ams.data.models

// ========================================
// ELECTIVE SELECTION MODELS
// ========================================

/**
 * Elective window for student selection.
 * A window represents an open selection period for a specific elective bucket.
 */
data class ElectiveWindow(
    val windowId: Int,
    val targetSemesterNo: Int,
    val bucket: String,           // e.g., "Professional Elective", "Open Elective"
    val status: String,           // Open, Extension, Closed
    val minBatchSize: Int,
    val selection: Int?,          // Currently selected subject_id, null if not selected
    val options: List<ElectiveOption>
)

/**
 * An elective option available for selection.
 */
data class ElectiveOption(
    val id: Int,                  // subject_id
    val name: String,
    val code: String
)

/**
 * Response from /api/student/elective_windows
 */
data class ElectiveWindowsResponse(
    val windows: List<ElectiveWindow>
)

// ========================================
// MDM/OE (MULTIDISCIPLINARY MINOR / OPEN ELECTIVE) MODELS
// ========================================

/**
 * MDM/OE selection window with available courses.
 */
data class MDMWindow(
    val id: Int,
    val courseType: String,       // MDM, OE
    val status: String,           // Open, Extension, Closed
    val deadlineAt: String?,      // ISO datetime
    val courses: List<MDMCourse>,
    val mySelection: MDMSelection?
)

/**
 * A course available for MDM/OE selection.
 */
data class MDMCourse(
    val id: Int,                  // pool_id
    val code: String,
    val name: String,
    val type: String,             // MDM, OE
    val credits: Int,
    val hostSchoolName: String?,
    val schedulePattern: String?,
    val description: String?,
    val capacity: Int?,
    val selections: Int,          // Current enrollment count
    val available: Int?           // Remaining slots
)

/**
 * Student's current selection in a window.
 */
data class MDMSelection(
    val id: Int,
    val poolId: Int,
    val status: String,           // Selected, Confirmed
    val code: String?,
    val name: String?,
    val hostSchoolName: String?
)

/**
 * Response from /api/student/mdm_outbound/windows
 */
data class MDMWindowsResponse(
    val windows: List<MDMWindow>
)

/**
 * Enrolled MDM/OE course with marks.
 */
data class MDMEnrolledCourse(
    val id: Int,
    val courseCode: String,
    val courseName: String,
    val type: String,             // MDM, OE
    val credits: Int,
    val hostSchoolName: String?,
    val schedulePattern: String?,
    val status: String,           // Selected, Confirmed
    val selectedAt: String?,      // ISO datetime
    val confirmedAt: String?,     // ISO datetime
    val externalMarks: Int?,
    val externalGrade: String?
)

/**
 * Response from /api/student/mdm_outbound/my_courses
 */
data class MDMMyCoursesResponse(
    val courses: List<MDMEnrolledCourse>
)

// ========================================
// HOD DASHBOARD & LEAVE APPROVAL MODELS
// ========================================

/**
 * HOD Dashboard statistics.
 */
data class HodStats(
    val students: Int,
    val faculty: Int,
    val attendance: Double,
    val pending: Int              // Pending leave approvals
)

/**
 * Pending leave approval for HOD.
 */
data class HodLeaveApproval(
    val leaveId: Int,
    val student: String,
    val roll: String,
    val className: String,
    val days: Double,
    val reason: String,
    val date: String              // Display format: "10 Jan"
)

/**
 * Faculty performance data for HOD dashboard.
 */
data class HodFacultyPerformance(
    val name: String,
    val code: String,
    val load: Int,
    val avgAtt: Double,
    val isCritical: Boolean,
    val missedToday: Int,
    val detentions: Int,
    val roles: String,
    val studentReach: Int,
    val riskSubject: String,
    val totalConducted: Int
)

/**
 * Load adjustment info for HOD monitoring.
 */
data class HodLoadAdjustment(
    val id: Int,
    val status: String,
    val reason: String?,
    val createdAtDisplay: String?,
    val classDivision: String,
    val requester: AdjustmentParty,
    val adjuster: AdjustmentParty,
    val requested: AdjustmentSlot,
    val swap: AdjustmentSlot
)

/**
 * Party involved in load adjustment.
 */
data class AdjustmentParty(
    val id: String,
    val name: String,
    val code: String
)

/**
 * Time slot for load adjustment.
 */
data class AdjustmentSlot(
    val dateIso: String?,
    val dateDisplay: String?,
    val day: String?,
    val time: String?,
    val subject: String?,
    val subjectCode: String?,
    val scheduleId: Int?,
    val classDivision: String?
)

/**
 * Full HOD dashboard response.
 */
data class HodDashboardResponse(
    val deptName: String,
    val stats: HodStats,
    val facultyList: List<HodFacultyPerformance>,
    val approvals: List<HodLeaveApproval>,
    val loadAdjustments: List<HodLoadAdjustment>
)

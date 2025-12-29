package com.eduMatrix.ams.data.models

/**
 * Staff profile information
 */
data class StaffProfile(
    val staffId: String,  // UUID from backend
    val employeeCode: String,
    val name: String,
    val email: String,
    val designation: String,
    val departmentId: Int,
    val departmentName: String,
    val roles: StaffRoles
)

/**
 * Subject allocation for a staff member
 */
data class SubjectAllocation(
    val allocationId: Int,
    val subjectId: Int,
    val subjectName: String,
    val subjectCode: String,
    val sectionId: Int,
    val sectionName: String,
    val classLevel: String, // FY, SY, TY, BTech
    val sessionType: String, // Lecture, Tutorial, Practical
    val batchDivision: String? = null // A, B for practicals
)

/**
 * Today's scheduled class for staff
 */
data class ScheduledClass(
    val scheduleId: Int,
    val dayOfWeek: String,
    val startTime: String,
    val endTime: String,
    val subject: SubjectAllocation,
    val roomNumber: String,
    val roomType: String, // Classroom, Lab
    val isCompleted: Boolean = false,
    val sessionId: Int? = null // If attendance already marked
)

/**
 * Staff dashboard summary data
 */
data class StaffDashboardData(
    val profile: StaffProfile,
    val todaySchedule: List<ScheduledClass>,
    val totalSubjects: Int,
    val totalStudents: Int,
    val sessionsThisMonth: Int,
    val pendingLeaveRequests: Int,
    val roles: StaffRoles,
    val classTeacherSection: ClassTeacherInfo? = null,
    val hodDepartment: HodInfo? = null,
    val mentorBatch: MentorBatchInfo? = null
)

/**
 * Class teacher specific info
 */
data class ClassTeacherInfo(
    val sectionId: Int,
    val sectionName: String,
    val classLevel: String,
    val totalStudents: Int
)

/**
 * HOD specific info
 */
data class HodInfo(
    val departmentId: Int,
    val departmentName: String,
    val totalFaculty: Int,
    val pendingLongLeaves: Int
)

/**
 * Mentor batch info
 */
data class MentorBatchInfo(
    val batchId: Int,
    val batchName: String,
    val totalMentees: Int,
    val pendingIssues: Int
)

/**
 * Session log for attendance tracking
 */
data class SessionLog(
    val sessionId: Int,
    val scheduleId: Int,
    val conductedDate: String,
    val startTime: String,
    val endTime: String,
    val topicCovered: String?,
    val totalPresent: Int,
    val totalAbsent: Int,
    val totalStudents: Int
)

/**
 * Student for attendance marking
 */
data class StudentForAttendance(
    val studentId: String,  // UUID from backend
    val rollNumber: String,
    val name: String,
    val admissionNumber: String,
    val isPresent: Boolean = true,
    val remarks: String? = null
)

/**
 * Attendance sheet data
 */
data class AttendanceSheet(
    val allocation: SubjectAllocation,
    val scheduleInfo: ScheduledClass,
    val students: List<StudentForAttendance>,
    val topics: List<TopicForSelection> // From teaching plan
)

/**
 * Topic from teaching plan for lesson linking
 */
data class TopicForSelection(
    val planId: Int,
    val unitNumber: Int,
    val unitTitle: String,
    val subUnitNumber: Int?,
    val subUnitTitle: String?,
    val isCompleted: Boolean
)

/**
 * Attendance submission request
 */
data class AttendanceSubmission(
    val scheduleId: Int,
    val conductedDate: String,
    val topicId: Int?,
    val attendance: List<StudentAttendanceRecord>
)

/**
 * Individual student attendance record
 */
data class StudentAttendanceRecord(
    val studentId: String,  // UUID from backend
    val status: AttendanceStatus,
    val remarks: String? = null
)

/**
 * Attendance status options
 */
enum class AttendanceStatus {
    PRESENT,
    ABSENT,
    ON_DUTY;

    fun toApiString(): String = when (this) {
        PRESENT -> "Present"
        ABSENT -> "Absent"
        ON_DUTY -> "OnDuty"
    }
}

// ========================================
// CLASS TEACHER ANALYTICS MODELS
// ========================================

/**
 * Class Teacher Analytics Dashboard data
 */
data class ClassTeacherAnalytics(
    val classInfo: ClassInfo,
    val summary: ClassSummary,
    val subjects: List<SubjectStats>,
    val defaulters: List<StudentAttendanceInfo>,
    val topStudents: List<StudentAttendanceInfo>
)

/**
 * Class info for CT dashboard
 */
data class ClassInfo(
    val name: String,
    val totalStudents: Int,
    val totalSessions: Int
)

/**
 * Class summary stats
 */
data class ClassSummary(
    val defaulterCount: Int,
    val pendingLeaves: Int,
    val classHealth: String  // "Good" or "At Risk"
)

/**
 * Subject statistics for CT dashboard
 */
data class SubjectStats(
    val subjectId: Int,
    val subjectName: String,
    val teacherName: String,
    val sessionsConducted: Int,
    val avgAttendance: Double
)

/**
 * Student attendance info for defaulters/top students
 */
data class StudentAttendanceInfo(
    val name: String,
    val rollNumber: String,
    val percentage: Double,
    val attended: Int,
    val total: Int
)

// ========================================
// UPCOMING SCHEDULE & ADJUSTMENT MODELS
// ========================================

/**
 * Upcoming scheduled class with adjustment info
 */
data class UpcomingClass(
    val scheduleId: Int,
    val time: String,
    val className: String,
    val subject: String,
    val day: String,
    val dateIso: String,
    val dateDisplay: String,
    val type: String,  // Lecture, Tutorial, Practical
    val batch: String? = null,
    val status: String = "Pending",
    val adjustment: AdjustmentInfo? = null
)

/**
 * Adjustment information for a scheduled class
 */
data class AdjustmentInfo(
    val id: Int,
    val status: String,  // Pending, Approved, Rejected
    val role: String,    // requester, adjuster
    val kind: String,    // in, out
    val partnerId: String,
    val partnerName: String,
    val partnerCode: String,
    val swap: SwapSlotInfo? = null
)

/**
 * Swap slot details
 */
data class SwapSlotInfo(
    val scheduleId: Int,
    val day: String,
    val time: String,
    val subject: String,
    val className: String,
    val dateIso: String,
    val dateDisplay: String
)

/**
 * Available faculty for adjustment
 */
data class AdjustmentFaculty(
    val facultyId: String,
    val name: String,
    val code: String,
    val availableSlots: List<AvailableSlot>
)

/**
 * Available slot for swap
 */
data class AvailableSlot(
    val scheduleId: Int,
    val day: String,
    val time: String,
    val subject: String,
    val className: String,
    val dateIso: String,
    val dateDisplay: String
)

/**
 * Adjustment request submission
 */
data class AdjustmentRequest(
    val requesterId: String,
    val scheduleId: Int,
    val originalDate: String,
    val substituteId: String,
    val swapSlotId: Int,
    val compensationDate: String,
    val reason: String? = null
)

// ========================================
// SESSION HISTORY MODELS
// ========================================

/**
 * Session history record
 */
data class SessionHistoryRecord(
    val scheduleId: Int,
    val dateIso: String,
    val dateDisplay: String,
    val time: String,
    val subject: String,
    val className: String,
    val percentage: Int
)

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
    val sessionId: Int? = null, // If attendance already marked
    val adjustment: AdjustmentInfo? = null // Adjustment info if session is swapped
)

/**
 * Staff dashboard summary data
 */
data class StaffDashboardData(
    val profile: StaffProfile,
    val todaySchedule: List<ScheduledClass>,
    val upcomingSchedule: List<UpcomingClass> = emptyList(),  // Next 2 weeks schedule
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
    val remarks: String? = null,
    val status: String = "Present",  // Backend status: Present, OnDuty, ML, CL, Absent
    val statusLabel: String? = null, // Display label: "Event OD", "Approved ML", etc.
    val isOnDuty: Boolean = false    // True if on approved leave/event
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
    val scheduleId: String,  // Can be integer or "extra_X" for extra sessions
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

// ========================================
// EVENT MANAGER MODELS
// ========================================

/**
 * Event summary for list display
 */
data class EventSummary(
    val eventId: Int,
    val name: String,
    val dateDisplay: String,
    val time: String?,
    val studentCount: Int
)

/**
 * Event details for creation/editing
 */
data class EventDetail(
    val eventId: Int,
    val name: String,
    val description: String?,
    val startDate: String,
    val endDate: String,
    val startTime: String?,
    val endTime: String?,
    val coordinatorId: String,
    val studentCount: Int
)

/**
 * Event participant
 */
data class EventParticipant(
    val participationId: Int,
    val studentId: String,
    val name: String,
    val rollNumber: String,
    val className: String,
    val role: String,  // Participant, Student Coordinator, Volunteer
    val status: String  // Nominated, Attended
)

/**
 * Event creation request
 */
data class EventCreateRequest(
    val name: String,
    val description: String?,
    val startDate: String,
    val endDate: String,
    val startTime: String?,
    val endTime: String?,
    val coordinatorId: String,
    val notifyAllStudents: Boolean = false
)

/**
 * Student for event participant selection
 */
data class StudentForEvent(
    val studentId: String,
    val name: String,
    val rollNumber: String,
    val admissionNumber: String
)

// ========================================
// EXTRA SESSION MODELS
// ========================================

/**
 * Extra session (one-time class scheduled outside regular timetable)
 */
data class ExtraSession(
    val id: Int,
    val subjectId: Int,
    val subjectName: String,
    val sectionId: Int,
    val sectionName: String,
    val teacherId: String? = null,
    val teacherName: String? = null,
    val date: String,           // ISO format: 2026-01-04
    val dateDisplay: String,    // Display format: 04 Jan
    val day: String,            // Saturday
    val startTime: String,      // 17:00 or 05:00 PM
    val endTime: String,        // 18:00 or 06:00 PM
    val time: String,           // Combined: "05:00 PM - 06:00 PM"
    val topic: String? = null,
    val meetingLink: String? = null,
    val status: String = "Scheduled",
    val attendanceMarked: Boolean = false,
    val isToday: Boolean = false
)

/**
 * Extra session creation request
 */
data class ExtraSessionCreateRequest(
    val subjectId: Int,
    val sectionId: Int,
    val date: String,       // ISO format
    val startTime: String,  // HH:mm format
    val endTime: String,    // HH:mm format
    val topic: String? = null,
    val meetingLink: String? = null
)

/**
 * Section with subjects for extra session creation
 */
data class ExtraSessionAllocation(
    val sectionId: Int,
    val sectionName: String,
    val subjects: List<AllocationSubject>
)

data class AllocationSubject(
    val subjectId: Int,
    val subjectName: String,
    val subjectCode: String
)

// ========================================
// STATUS UTILITIES
// ========================================

/**
 * Utility object for normalizing and checking attendance/leave statuses.
 * Handles case-insensitive matching and various string variants.
 */
object StatusUtils {
    /**
     * Normalizes a status string to standard leave code (ML, CL, OD) or null.
     * Handles various backend formats like "Sick/Medical", "MedicalLeave", "medical leave", etc.
     */
    fun normalizeLeaveStatus(status: String?): String? {
        if (status.isNullOrBlank()) return null
        val normalized = status.trim().lowercase().replace("_", "").replace("-", "").replace(" ", "")

        return when {
            // Medical Leave variants
            normalized == "ml" ||
            normalized == "medicalleave" ||
            normalized == "medical" ||
            normalized == "sick" ||
            normalized == "sickleave" ||
            normalized == "sick/medical" ||
            normalized == "sickmedical" ||
            normalized.contains("medical") -> "ML"

            // Casual Leave variants
            normalized == "cl" ||
            normalized == "casualleave" ||
            normalized == "casual" ||
            normalized == "personal" ||
            normalized == "personalleave" -> "CL"

            // On Duty variants
            normalized == "od" ||
            normalized == "onduty" ||
            normalized == "duty" ||
            normalized == "event" ||
            normalized == "eventod" -> "OD"

            else -> null
        }
    }

    /**
     * Checks if a status is "present-like" (counts positively for attendance).
     * Includes: Present, ML (Medical Leave), CL (Casual Leave), OD (On Duty)
     */
    fun isPresentLike(status: String?): Boolean {
        if (status.isNullOrBlank()) return false
        val normalized = status.trim().lowercase().replace("_", "").replace("-", "").replace(" ", "")

        return normalized == "present" || normalizeLeaveStatus(status) != null
    }

    /**
     * Checks if a status represents any approved leave/duty (ML, CL, or OD).
     * These statuses should lock attendance and show special UI.
     */
    fun isLeaveOrDuty(status: String?): Boolean {
        return normalizeLeaveStatus(status) != null
    }
}

package com.eduMatrix.ams.data.models

/**
 * Generic API response wrapper
 */
sealed class ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>()
    data class Error(val message: String, val code: Int? = null) : ApiResult<Nothing>()
    object Loading : ApiResult<Nothing>()
}

/**
 * Notification model
 */
data class Notification(
    val id: Int,
    val title: String,
    val message: String,
    val timestamp: String,
    val type: NotificationType,
    val isRead: Boolean,
    val actionUrl: String? = null
)

/**
 * Notification types matching web app
 */
enum class NotificationType {
    INFO,
    SUCCESS,
    WARNING,
    DANGER;

    companion object {
        fun fromString(type: String): NotificationType {
            return when (type.lowercase()) {
                "info" -> INFO
                "success" -> SUCCESS
                "warning" -> WARNING
                "danger", "error" -> DANGER
                else -> INFO
            }
        }
    }
}

/**
 * Timetable entry
 */
data class TimetableEntry(
    val scheduleId: Int,
    val dayOfWeek: String,
    val startTime: String,
    val endTime: String,
    val subjectName: String,
    val subjectCode: String,
    val teacherName: String,
    val roomNumber: String,
    val sessionType: String
)

/**
 * Department model
 */
data class Department(
    val departmentId: Int,
    val name: String,
    val code: String,
    val hodName: String?
)

/**
 * Class section model
 */
data class ClassSection(
    val sectionId: Int,
    val name: String,
    val classLevel: String, // FY, SY, TY, BTech
    val departmentId: Int,
    val departmentName: String,
    val classTeacherName: String?,
    val totalStudents: Int
)

/**
 * Subject model
 */
data class Subject(
    val subjectId: Int,
    val name: String,
    val code: String,
    val credits: Int,
    val lectureHours: Int,
    val tutorialHours: Int,
    val practicalHours: Int,
    val departmentId: Int
)

/**
 * Event model
 */
data class Event(
    val eventId: Int,
    val name: String,
    val description: String?,
    val startDate: String,
    val endDate: String,
    val time: String?,
    val venue: String?,
    val coordinatorName: String,
    val status: EventStatus,
    val participantCount: Int
)

/**
 * Event status
 */
enum class EventStatus {
    UPCOMING,
    ONGOING,
    COMPLETED,
    CANCELLED;

    companion object {
        fun fromString(status: String): EventStatus {
            return when (status.lowercase()) {
                "upcoming" -> UPCOMING
                "ongoing" -> ONGOING
                "completed" -> COMPLETED
                "cancelled" -> CANCELLED
                else -> UPCOMING
            }
        }
    }
}

/**
 * Mentor log entry
 */
data class MentorLog(
    val logId: Int,
    val studentId: String,  // UUID from backend
    val studentName: String,
    val category: IssueCategory,
    val description: String,
    val status: IssueStatus,
    val createdAt: String,
    val resolvedAt: String?
)

/**
 * Issue categories for mentor logs
 */
enum class IssueCategory {
    ACADEMIC,
    PERSONAL,
    DISCIPLINARY,
    FINANCIAL,
    OTHER;

    fun toDisplayString(): String = when (this) {
        ACADEMIC -> "Academic"
        PERSONAL -> "Personal"
        DISCIPLINARY -> "Disciplinary"
        FINANCIAL -> "Financial"
        OTHER -> "Other"
    }

    companion object {
        fun fromString(category: String): IssueCategory {
            return when (category.lowercase()) {
                "academic" -> ACADEMIC
                "personal" -> PERSONAL
                "disciplinary" -> DISCIPLINARY
                "financial" -> FINANCIAL
                else -> OTHER
            }
        }
    }
}

/**
 * Issue status for mentor logs
 */
enum class IssueStatus {
    OPEN,
    IN_PROGRESS,
    RESOLVED,
    ESCALATED;

    companion object {
        fun fromString(status: String): IssueStatus {
            return when (status.lowercase()) {
                "open" -> OPEN
                "in_progress", "inprogress" -> IN_PROGRESS
                "resolved" -> RESOLVED
                "escalated" -> ESCALATED
                else -> OPEN
            }
        }
    }
}

/**
 * Mentor meeting
 */
data class MentorMeeting(
    val meetingId: Int,
    val batchId: Int,
    val scheduledDate: String,
    val scheduledTime: String,
    val agenda: String,
    val isCompleted: Boolean,
    val attendeeCount: Int?,
    val venue: String? = null,
    val discussionPoints: String? = null,
    val summary: String? = null,
    val batchName: String? = null
)

/**
 * Meeting details with attendance and issues
 */
data class MeetingDetails(
    val meeting: MentorMeeting,
    val students: List<MeetingStudent>,
    val attendance: List<MeetingAttendance>,
    val issues: List<MeetingIssue>
)

data class MeetingStudent(
    val studentId: String,
    val name: String,
    val rollNo: String
)

data class MeetingAttendance(
    val studentId: String,
    val attended: Boolean,
    val remarks: String?
)

data class MeetingIssue(
    val issueId: Int,
    val raisedByStudentId: String?,
    val raisedByName: String?,
    val issueDescription: String,
    val category: String,
    val actionTaken: String?,
    val actionStatus: String
)

/**
 * Mentee (student in mentor batch)
 */
data class Mentee(
    val studentId: String,  // UUID from backend
    val name: String,
    val rollNumber: String,
    val email: String,
    val phone: String?,
    val attendancePercentage: Double?,
    val openIssues: Int
)

/**
 * Current academic term info
 */
data class CurrentTerm(
    val termId: Int,
    val name: String, // e.g., "Odd 2024-25"
    val semesterType: String, // Odd or Even
    val academicYear: String,
    val startDate: String,
    val endDate: String
)

/**
 * Mentor batch detail
 */
data class MentorBatchDetail(
    val batchId: Int,
    val batchName: String,
    val sectionName: String,
    val classLevel: String,
    val studentCount: Int
)

/**
 * Mentor dashboard data
 */
data class MentorDashboardData(
    val batches: List<MentorBatchDetail>,
    val mentees: List<Mentee>,
    val pendingIssues: List<MentorLog>,
    val upcomingMeeting: MentorMeeting?,
    val totalMentees: Int,
    val openIssuesCount: Int
)

/**
 * Detailed mentee information
 */
data class MenteeDetail(
    val studentId: String,  // UUID from backend
    val name: String,
    val rollNumber: String,
    val email: String,
    val phone: String?,
    val className: String,
    val overallAttendance: Double,
    val totalLectures: Int,
    val attended: Int,
    val isDefaulter: Boolean,
    val subjectAttendance: List<SubjectAttendance>,
    val logs: List<MentorLog>,
    val hasDetention: Boolean,
    val hasEscalation: Boolean
)

/**
 * Subject-wise attendance for mentee
 */
data class SubjectAttendance(
    val subjectName: String,
    val subjectCode: String,
    val attended: Int,
    val total: Int,
    val percentage: Double
)

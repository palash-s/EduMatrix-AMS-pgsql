package com.eduMatrix.ams.data.models

/**
 * Leave application status
 */
enum class LeaveStatus {
    PENDING,
    APPROVED,
    REJECTED,
    ESCALATED,
    CANCELLED;

    companion object {
        fun fromString(status: String): LeaveStatus {
            return when (status.lowercase()) {
                "pending" -> PENDING
                "approved" -> APPROVED
                "rejected" -> REJECTED
                "escalated" -> ESCALATED
                "cancelled" -> CANCELLED
                else -> PENDING
            }
        }
    }
}

/**
 * Leave type options
 */
enum class LeaveType {
    SICK,
    CASUAL,
    EARNED,
    MATERNITY,
    PATERNITY,
    GENERAL;

    fun toDisplayString(): String = when (this) {
        SICK -> "Sick Leave"
        CASUAL -> "Casual Leave"
        EARNED -> "Earned Leave"
        MATERNITY -> "Maternity Leave"
        PATERNITY -> "Paternity Leave"
        GENERAL -> "General Leave"
    }

    companion object {
        fun fromString(type: String): LeaveType {
            return when (type.lowercase()) {
                "sick" -> SICK
                "casual" -> CASUAL
                "earned" -> EARNED
                "maternity" -> MATERNITY
                "paternity" -> PATERNITY
                else -> GENERAL
            }
        }
    }
}

/**
 * Leave request for staff approval
 */
data class LeaveRequest(
    val leaveId: Int,
    val applicantId: Int,
    val applicantName: String,
    val applicantType: String, // Student or Staff
    val applicantClass: String?, // For students
    val leaveType: LeaveType,
    val startDate: String,
    val endDate: String,
    val totalDays: Double,
    val reason: String,
    val status: LeaveStatus,
    val appliedOn: String,
    val documentUrl: String? = null
)

/**
 * Leave balance information
 */
data class LeaveBalance(
    val total: Double,
    val used: Double,
    val remaining: Double
)

/**
 * Leave history item
 */
data class LeaveHistoryItem(
    val leaveId: Int,
    val type: LeaveType,
    val days: Double,
    val status: LeaveStatus,
    val startDate: String,
    val endDate: String,
    val reason: String,
    val approvedBy: String?,
    val approvedOn: String?,
    val remarks: String?
)

/**
 * Leave action request (approve/reject/escalate)
 */
data class LeaveAction(
    val leaveId: Int,
    val action: LeaveActionType,
    val remarks: String? = null
)

/**
 * Leave action types
 */
enum class LeaveActionType {
    APPROVE,
    REJECT,
    ESCALATE;

    fun toApiString(): String = name.lowercase()
}

/**
 * Leave workflow log entry
 */
data class LeaveWorkflowEntry(
    val logId: Int,
    val action: String,
    val actorName: String,
    val actorRole: String,
    val timestamp: String,
    val remarks: String?
)

/**
 * Response containing leave requests and on-duty students
 */
data class LeaveApprovalsData(
    val requests: List<LeaveRequest>,
    val onDutyStudents: List<OnDutyStudent>
)

/**
 * Student currently on duty (participating in events)
 */
data class OnDutyStudent(
    val studentId: String,
    val studentName: String,
    val rollNo: String,
    val events: List<OnDutyEvent>
)

/**
 * Event info for on-duty student
 */
data class OnDutyEvent(
    val eventId: Int,
    val eventName: String,
    val role: String,
    val status: String,
    val dateRange: String,
    val isToday: Boolean = false  // True if event is active today
)

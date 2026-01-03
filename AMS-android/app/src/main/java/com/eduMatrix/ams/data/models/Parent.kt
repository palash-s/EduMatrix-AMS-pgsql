package com.eduMatrix.ams.data.models

// ========================================
// PARENT DASHBOARD MODELS
// ========================================

/**
 * Complete parent dashboard data from /api/parent/dashboard
 */
data class ParentDashboardData(
    val student: ParentChildInfo,
    val stats: ParentAttendanceStats,
    val subjects: List<ParentSubjectAttendance>,
    val detention: ParentDetentionInfo?,
    val escalation: ParentEscalationInfo?,
    val mentor: ParentMentorInfo?,
    val events: List<ParentEventInfo>,
    val leaves: List<ParentLeaveInfo>,
    val logs: List<ParentCounselingLog>,
    val results: List<ParentCAResult>,
    val termGrant: ParentTermGrantInfo?
)

/**
 * Child/student information for parent view
 */
data class ParentChildInfo(
    val name: String,
    val roll: String,        // Admission number
    val className: String    // e.g., "TY-A"
)

/**
 * Overall attendance statistics for parent view
 */
data class ParentAttendanceStats(
    val percentage: Double,
    val total: Int,          // Total lectures conducted
    val attended: Int,       // Lectures attended
    val isDefaulter: Boolean // If attendance < 75%
)

/**
 * Subject-wise attendance for parent view
 */
data class ParentSubjectAttendance(
    val subject: String,
    val code: String,
    val conducted: Int,
    val attended: Int,
    val percentage: Double
)

/**
 * Detention information for parent view
 */
data class ParentDetentionInfo(
    val reason: String,
    val status: String       // Assigned, In_Review
)

/**
 * Escalated counseling issue
 */
data class ParentEscalationInfo(
    val category: String,
    val remarks: String
)

/**
 * Mentor information for parent view
 */
data class ParentMentorInfo(
    val name: String,
    val email: String,
    val batchName: String?
)

/**
 * Event participation info for parent view
 */
data class ParentEventInfo(
    val name: String,
    val date: String,        // e.g., "28 Dec"
    val role: String,        // Participant, Volunteer, Student Coordinator
    val status: String       // Nominated, Attended
)

/**
 * Leave info for parent view
 */
data class ParentLeaveInfo(
    val type: String,        // Medical, Casual, General
    val days: Double,
    val status: String,      // Pending, Approved, Rejected
    val date: String         // Start date
)

/**
 * Counseling log entry for parent view
 */
data class ParentCounselingLog(
    val date: String,        // e.g., "28 Dec 2024"
    val category: String,    // Academic, Personal, Behavioral
    val remarks: String,
    val status: String,      // Open, Resolved, Escalated
    val mentor: String       // Mentor name
)

/**
 * CA (Continuous Assessment) results for parent view
 */
data class ParentCAResult(
    val subject: String,
    val code: String?,
    val ta1: String?,        // Score or "-" if not published
    val ta2: String?,
    val ta3: String?
)

/**
 * Term grant status for parent view
 */
data class ParentTermGrantInfo(
    val status: String,      // Granted, Provisional, Detained
    val remarks: String?
)

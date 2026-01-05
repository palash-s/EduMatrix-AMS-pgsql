package com.eduMatrix.ams.data.models

// ========================================
// STUDENT DASHBOARD MODELS
// ========================================

/**
 * Complete student dashboard data from /api/student/dashboard
 */
data class StudentDashboardData(
    val profile: StudentProfileInfo,
    val stats: AttendanceStats,
    val subjectWise: List<SubjectPerformance>,
    val recentActivity: List<RecentActivity>,
    val events: List<StudentEvent>,
    val mentor: MentorInfo?,
    val detention: DetentionInfo?,
    val meeting: UpcomingMeetingInfo?,
    val results: List<CAResult>,
    val termGrant: TermGrantInfo?,
    val extraSessions: List<StudentExtraSession> = emptyList()
)

/**
 * Extra session for student view (upcoming extra classes)
 */
data class StudentExtraSession(
    val id: Int,
    val subject: String,
    val teacher: String,
    val date: String,           // Display format: 04 Jan
    val dateIso: String,        // ISO format: 2026-01-04
    val day: String,            // Saturday
    val time: String,           // Combined: "05:00 PM - 06:00 PM"
    val topic: String? = null,
    val meetingLink: String? = null,
    val isToday: Boolean = false
)

/**
 * Student profile information
 */
data class StudentProfileInfo(
    val name: String,
    val roll: String,
    val className: String  // e.g., "TY-A"
)

/**
 * Overall attendance statistics
 */
data class AttendanceStats(
    val percentage: Double,
    val totalLectures: Int,
    val attended: Int,
    val isDefaulter: Boolean
)

/**
 * Subject-wise performance/attendance
 */
data class SubjectPerformance(
    val subject: String,
    val code: String,
    val teacher: String,
    val conducted: Int,
    val attended: Int,
    val percentage: Double
)

/**
 * Recent attendance activity entry
 */
data class RecentActivity(
    val date: String,      // e.g., "28 Dec"
    val subject: String,
    val status: String,    // Present, Absent, OnDuty
    val time: String       // e.g., "09:30 AM"
)

/**
 * Student event participation
 */
data class StudentEvent(
    val name: String,
    val date: String,
    val role: String,      // Participant, Student Coordinator, Volunteer
    val status: String     // Nominated, Attended
)

/**
 * Mentor information
 */
data class MentorInfo(
    val name: String,
    val email: String,
    val batchName: String
)

/**
 * Active detention information
 */
data class DetentionInfo(
    val id: Int,
    val reason: String,
    val status: String,    // Assigned, In_Review
    val task: String?,
    val submissionUrl: String?
)

/**
 * Upcoming mentor meeting
 */
data class UpcomingMeetingInfo(
    val date: String,      // e.g., "28 Dec"
    val time: String,      // e.g., "02:00 PM"
    val agenda: String?
)

/**
 * CA (Continuous Assessment) results
 */
data class CAResult(
    val subject: String,
    val code: String,
    val ta1: String?,      // "-" if not published
    val ta2: String?,
    val ta3: String?,
    val a1: Int?,
    val a2: Int?
)

/**
 * Term grant status
 */
data class TermGrantInfo(
    val status: String,    // Granted, Provisional, Detained
    val remarks: String?,
    val attPerc: Double?,
    val caAvg: Double?
)

// ========================================
// STUDENT TIMETABLE MODELS
// ========================================

/**
 * Student timetable entry
 */
data class StudentTimetableEntry(
    val scheduleId: Int,
    val dayOfWeek: String,
    val startTime: String,
    val endTime: String,
    val subjectName: String,
    val subjectCode: String,
    val teacherName: String,
    val roomNumber: String,
    val sessionType: String,  // Lecture, Tutorial, Practical
    val batch: String?        // For practicals
)

// ========================================
// STUDENT LEAVE MODELS
// ========================================

/**
 * Student leave request
 */
data class StudentLeaveRequest(
    val leaveId: Int,
    val startDate: String,
    val endDate: String,
    val reason: String,
    val category: String,   // Medical, Personal, Academic
    val status: String,     // Pending, Approved, Rejected
    val appliedOn: String,
    val reviewedBy: String?,
    val reviewedOn: String?,
    val remarks: String?
)

/**
 * Leave application request
 */
data class LeaveApplication(
    val startDate: String,
    val endDate: String,
    val reason: String,
    val category: String,
    val documentUrl: String?
)

// ========================================
// STUDENT FEEDBACK MODELS
// ========================================

/**
 * Pending feedback subjects
 */
data class FeedbackPendingList(
    val cycleId: Int,
    val cycleName: String,
    val endDate: String,
    val subjects: List<FeedbackSubject>
)

/**
 * Subject for feedback
 */
data class FeedbackSubject(
    val allocationId: Int,
    val subjectId: Int,
    val subjectName: String,
    val subjectCode: String,
    val teacherName: String
)

/**
 * Feedback submission
 */
data class FeedbackSubmission(
    val allocationId: Int,
    val responses: Map<Int, Int>  // questionId -> rating (1-5)
)

// ========================================
// ELECTIVE SELECTION MODELS
// ========================================

/**
 * Available elective for selection
 */
data class AvailableElective(
    val subjectId: Int,
    val subjectName: String,
    val subjectCode: String,
    val credits: Int,
    val electiveType: String,  // Elective, Open Elective
    val slots: Int,
    val enrolled: Int
)

/**
 * Student's elective selection status
 */
data class ElectiveSelection(
    val subjectId: Int,
    val subjectName: String,
    val subjectCode: String,
    val status: String,    // Pending, Approved, Rejected
    val appliedOn: String
)

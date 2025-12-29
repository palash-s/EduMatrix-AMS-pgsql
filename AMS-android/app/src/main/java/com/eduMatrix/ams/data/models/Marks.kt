package com.eduMatrix.ams.data.models

/**
 * CA Marks entry for a student
 */
data class StudentCAMarks(
    val studentId: Int,
    val rollNumber: String,
    val name: String,
    val admissionNumber: String,
    val ta1: Double? = null,
    val ta2: Double? = null,
    val ta3: Double? = null,
    val a1: Double? = null,
    val a2: Double? = null,
    val a3: Double? = null,
    val a4: Double? = null,
    val a5: Double? = null,
    val attendanceScore: Double? = null,
    val attendancePercentage: Double? = null,
    val totalCA: Double? = null,
    val learnerType: LearnerType? = null
)

/**
 * Learner classification based on CA scores
 */
enum class LearnerType {
    SLOW,       // < 40%
    AVERAGE,    // 40-80%
    ADVANCED;   // > 80%

    companion object {
        fun fromPercentage(percentage: Double): LearnerType {
            return when {
                percentage < 40 -> SLOW
                percentage <= 80 -> AVERAGE
                else -> ADVANCED
            }
        }
    }

    fun toDisplayString(): String = when (this) {
        SLOW -> "Slow Learner"
        AVERAGE -> "Average"
        ADVANCED -> "Advanced Learner"
    }
}

/**
 * CA marks sheet for a subject/section
 */
data class CAMarksSheet(
    val subjectId: Int,
    val subjectName: String,
    val subjectCode: String,
    val sectionId: Int,
    val sectionName: String,
    val students: List<StudentCAMarks>,
    val publishStatus: CAPublishStatus
)

/**
 * Publish status for different CA components
 */
data class CAPublishStatus(
    val ta1Published: Boolean = false,
    val ta2Published: Boolean = false,
    val ta3Published: Boolean = false,
    val assignmentsPublished: Boolean = false,
    val finalPublished: Boolean = false
)

/**
 * CA marks submission
 */
data class CAMarksSubmission(
    val subjectId: Int,
    val sectionId: Int,
    val component: CAComponent,
    val marks: List<StudentMarkEntry>,
    val publish: Boolean = false
)

/**
 * Individual student mark entry
 */
data class StudentMarkEntry(
    val studentId: Int,
    val score: Double?
)

/**
 * CA component types
 */
enum class CAComponent {
    TA1,
    TA2,
    TA3,
    A1,
    A2,
    A3,
    A4,
    A5;

    fun toApiString(): String = name.lowercase()

    fun toDisplayString(): String = when (this) {
        TA1 -> "Term Assessment 1"
        TA2 -> "Term Assessment 2"
        TA3 -> "Term Assessment 3"
        A1 -> "Assignment 1"
        A2 -> "Assignment 2"
        A3 -> "Assignment 3"
        A4 -> "Assignment 4"
        A5 -> "Assignment 5"
    }

    fun maxMarks(): Int = when (this) {
        TA1, TA2, TA3 -> 20
        else -> 10
    }
}

/**
 * Term grant status for a student
 */
data class TermGrant(
    val status: TermGrantStatus,
    val remarks: String?,
    val attendancePercentage: Double?,
    val caAverage: Double?,
    val failedSubjects: Int,
    val activeDetentions: Int,
    val isPublished: Boolean
)

/**
 * Term grant status options
 */
enum class TermGrantStatus {
    GRANTED,
    PROVISIONAL,
    DETAINED;

    companion object {
        fun fromString(status: String): TermGrantStatus {
            return when (status.lowercase()) {
                "granted" -> GRANTED
                "provisional" -> PROVISIONAL
                "detained" -> DETAINED
                else -> PROVISIONAL
            }
        }
    }

    fun toDisplayString(): String = when (this) {
        GRANTED -> "Granted"
        PROVISIONAL -> "Provisional"
        DETAINED -> "Detained"
    }
}

/**
 * Result row for student results screen
 */
data class ResultRow(
    val subject: String,
    val code: String,
    val ta1: String?,
    val ta2: String?,
    val ta3: String?,
    val assignments: String?,
    val attendance: String?,
    val total: String?
)

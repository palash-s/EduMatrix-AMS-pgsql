package com.eduMatrix.ams.data.api

import com.eduMatrix.ams.data.models.*
import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.reflect.TypeToken
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

// Extension functions for safe JSON parsing (handles JsonNull properly)
private fun JsonElement?.safeString(): String? = this?.takeIf { !it.isJsonNull }?.asString
private fun JsonElement?.safeInt(): Int? = this?.takeIf { !it.isJsonNull }?.asInt
private fun JsonElement?.safeDouble(): Double? = this?.takeIf { !it.isJsonNull }?.asDouble
private fun JsonElement?.safeBool(): Boolean? = this?.takeIf { !it.isJsonNull }?.asBoolean

/**
 * Central API service for all HTTP operations.
 * Handles authentication, staff, student, and parent APIs.
 */
object ApiService {
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()
    private val gson = Gson()

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    // ========================================
    // AUTHENTICATION APIs
    // ========================================

    /**
     * Login with multi-role support.
     * Returns user info including role and staff-specific roles.
     */
    fun login(
        baseUrl: String,
        username: String,
        password: String,
        deviceId: String
    ): LoginResponse {
        val payload = JsonObject().apply {
            addProperty("username", username)
            addProperty("password", password)
            addProperty("device_id", deviceId)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/v1/auth/login")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val errorMsg = parseError(body)
                throw ApiException("Login failed: $errorMsg", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val userJson = json.getAsJsonObject("user")

            // Parse staff roles if user is staff
            val role = UserRole.fromString(userJson.get("role").safeString() ?: "student")
            val staffRolesJson = userJson.get("staff_roles")
            val staffRoles = if (role == UserRole.STAFF && staffRolesJson != null && !staffRolesJson.isJsonNull) {
                val sr = staffRolesJson.asJsonObject
                StaffRoles(
                    isClassTeacher = sr.get("is_class_teacher").safeBool() ?: false,
                    isHod = sr.get("is_hod").safeBool() ?: false,
                    isEventCoordinator = sr.get("is_event_coordinator").safeBool() ?: false,
                    isAmcMember = sr.get("is_amc_member").safeBool() ?: false,
                    isAmcHead = sr.get("is_amc_head").safeBool() ?: false,
                    isMentor = sr.get("is_mentor").safeBool() ?: false
                )
            } else null

            // must_change_password is at root level, not inside user object
            val mustChangePassword = json.get("must_change_password").safeBool() ?: false

            val user = User(
                userId = userJson.get("user_id").safeString() ?: "",
                email = userJson.get("email").safeString() ?: userJson.get("username").safeString() ?: "",
                name = userJson.get("name").safeString() ?: "",
                role = role,
                staffRoles = staffRoles,
                departmentId = userJson.get("department_id").safeInt(),
                departmentName = userJson.get("department_name").safeString(),
                mustChangePassword = mustChangePassword
            )

            return LoginResponse(
                accessToken = json.get("access_token").asString,
                refreshToken = json.get("refresh_token").asString,
                user = user
            )
        }
    }

    /**
     * Refresh access token using refresh token.
     */
    fun refreshToken(baseUrl: String, refreshToken: String): Pair<String, String> {
        val payload = JsonObject().apply {
            addProperty("refresh_token", refreshToken)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/v1/auth/refresh")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Token refresh failed", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            return Pair(
                json.get("access_token").asString,
                json.get("refresh_token")?.asString ?: refreshToken
            )
        }
    }

    /**
     * Change password for first-time login.
     */
    fun changePassword(
        baseUrl: String,
        accessToken: String,
        currentPassword: String,
        newPassword: String
    ): Boolean {
        val payload = JsonObject().apply {
            addProperty("current_password", currentPassword)
            addProperty("new_password", newPassword)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/change-password")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Password change failed: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    // ========================================
    // STAFF APIs
    // ========================================

    /**
     * Get staff dashboard data including schedule, stats, and role-specific info.
     */
    fun getStaffDashboard(baseUrl: String, accessToken: String, userId: String): StaffDashboardData {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/dashboard?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load dashboard: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
                ?: throw ApiException("Invalid JSON response")

            // Safe helper to get JsonObject (handles null and JsonNull)
            fun JsonObject.safeGetObject(key: String): JsonObject {
                val element = this.get(key)
                return if (element != null && element.isJsonObject) element.asJsonObject else JsonObject()
            }

            // Parse profile
            val profileJson = json.safeGetObject("profile")
            val rolesJson = json.safeGetObject("roles")
            val widgetsJson = json.safeGetObject("widgets")

            val profile = StaffProfile(
                staffId = userId,  // Use the userId we passed in
                employeeCode = profileJson.get("code").safeString() ?: "",
                name = profileJson.get("name").safeString() ?: "",
                email = "",  // Not returned by this endpoint
                designation = profileJson.get("dept").safeString() ?: "Faculty",
                departmentId = 0,  // Not returned by this endpoint
                departmentName = profileJson.get("dept").safeString() ?: "",
                roles = StaffRoles(
                    isClassTeacher = rolesJson.get("is_class_teacher").safeBool() ?: false,
                    isHod = rolesJson.get("is_hod").safeBool() ?: false,
                    isEventCoordinator = rolesJson.get("is_coordinator").safeBool() ?: false,
                    isAmcMember = rolesJson.get("is_amc_member").safeBool() ?: false,
                    isAmcHead = rolesJson.get("is_amc_head").safeBool() ?: false,
                    isMentor = rolesJson.get("is_mentor").safeBool() ?: false
                )
            )

            // Parse today's schedule from widgets
            // Backend returns: { "id", "time", "class", "subject", "day", "status", "type", "batch", "adjustment"? }
            val scheduleElement = widgetsJson.get("today_schedule")
            val scheduleArr = if (scheduleElement != null && scheduleElement.isJsonArray)
                scheduleElement.asJsonArray else null
            val todaySchedule = scheduleArr?.mapNotNull { elem ->
                try {
                    val s = elem.asJsonObject
                    val timeStr = s.get("time").safeString() ?: ""
                    val timeParts = timeStr.split(" - ")
                    val startTime = timeParts.getOrNull(0) ?: ""
                    val endTime = timeParts.getOrNull(1) ?: ""
                    val className = s.get("class").safeString() ?: ""
                    val classParts = className.split("-")
                    val classLevel = classParts.getOrNull(0) ?: ""
                    val sectionName = classParts.getOrNull(1) ?: ""

                    // Parse adjustment info if present
                    val adjElement = s.get("adjustment")
                    val adjustment = if (adjElement != null && adjElement.isJsonObject) {
                        val adj = adjElement.asJsonObject
                        val swapElement = adj.get("swap")
                        val swap = if (swapElement != null && swapElement.isJsonObject) {
                            val sw = swapElement.asJsonObject
                            SwapSlotInfo(
                                scheduleId = sw.get("schedule_id").safeInt() ?: 0,
                                day = sw.get("day").safeString() ?: "",
                                time = sw.get("time").safeString() ?: "",
                                subject = sw.get("subject").safeString() ?: "",
                                className = sw.get("class_name").safeString() ?: "",
                                dateIso = sw.get("date_iso").safeString() ?: "",
                                dateDisplay = sw.get("date_display").safeString() ?: ""
                            )
                        } else null
                        AdjustmentInfo(
                            id = adj.get("id").safeInt() ?: 0,
                            status = adj.get("status").safeString() ?: "",
                            role = adj.get("role").safeString() ?: "",
                            kind = adj.get("kind").safeString() ?: "",
                            partnerId = adj.get("partner_id").safeString() ?: "",
                            partnerName = adj.get("partner_name").safeString() ?: "",
                            partnerCode = adj.get("partner_code").safeString() ?: "",
                            swap = swap
                        )
                    } else null

                    ScheduledClass(
                        scheduleId = s.get("id").safeInt() ?: 0,
                        dayOfWeek = s.get("day").safeString() ?: "",
                        startTime = startTime,
                        endTime = endTime,
                        subject = SubjectAllocation(
                            allocationId = 0,
                            subjectId = 0,
                            subjectName = s.get("subject").safeString() ?: "",
                            subjectCode = "",
                            sectionId = 0,
                            sectionName = sectionName,
                            classLevel = classLevel,
                            sessionType = s.get("type").safeString() ?: "Lecture",
                            batchDivision = s.get("batch").safeString()
                        ),
                        roomNumber = "",
                        roomType = "Classroom",
                        isCompleted = s.get("status").safeString() == "Done",
                        sessionId = null,
                        adjustment = adjustment
                    )
                } catch (e: Exception) {
                    null  // Skip malformed entries
                }
            } ?: emptyList()

            // Parse stats from profile.stats (use safeGetObject)
            val statsJson = profileJson.safeGetObject("stats")

            // Parse my_subjects from widgets for total count
            val mySubjectsElement = widgetsJson.get("my_subjects")
            val mySubjectsArr = if (mySubjectsElement != null && mySubjectsElement.isJsonArray)
                mySubjectsElement.asJsonArray else null
            val totalSubjects = mySubjectsArr?.size() ?: 0

            // Parse class teacher info from widgets.class_teacher_data
            // Backend returns: { "name": "TY - DA", "count": 23 } or empty {}
            val ctData = widgetsJson.safeGetObject("class_teacher_data")
            val classTeacherInfo = if (rolesJson.get("is_class_teacher").safeBool() == true && ctData.has("name")) {
                val ctName = ctData.get("name").safeString() ?: ""
                val ctParts = ctName.split(" - ")
                ClassTeacherInfo(
                    sectionId = 0,
                    sectionName = ctParts.getOrNull(1) ?: ctName,
                    classLevel = ctParts.getOrNull(0) ?: "",
                    totalStudents = ctData.get("count").safeInt() ?: 0
                )
            } else null

            // HOD info not returned by this endpoint
            val hodInfo: HodInfo? = null

            // Parse mentor batch info from widgets.mentee_data
            val menteeData = widgetsJson.safeGetObject("mentee_data")
            val mentorBatchInfo = if (rolesJson.get("is_mentor").safeBool() == true && menteeData.has("count")) {
                MentorBatchInfo(
                    batchId = 0,
                    batchName = "Mentees",
                    totalMentees = menteeData.get("count").safeInt() ?: 0,
                    pendingIssues = 0
                )
            } else null

            // Parse upcoming schedule (next 2 weeks)
            // Helper to safely get string (handles null and JsonNull)
            fun JsonObject.safeString(key: String): String? {
                val el = this.get(key)
                return if (el != null && !el.isJsonNull) el.asString else null
            }
            fun JsonObject.safeStringOrDefault(key: String, default: String): String {
                return safeString(key) ?: default
            }
            fun JsonObject.safeInt(key: String, default: Int = 0): Int {
                val el = this.get(key)
                return if (el != null && !el.isJsonNull) el.asInt else default
            }

            val upcomingElement = widgetsJson.get("upcoming_schedule")
            val upcomingArr = if (upcomingElement != null && upcomingElement.isJsonArray)
                upcomingElement.asJsonArray else null
            val upcomingSchedule = upcomingArr?.mapNotNull { elem ->
                try {
                    val s = elem.asJsonObject
                    UpcomingClass(
                        scheduleId = s.safeInt("id"),
                        time = s.safeStringOrDefault("time", ""),
                        className = s.safeStringOrDefault("class", ""),
                        subject = s.safeStringOrDefault("subject", ""),
                        day = s.safeStringOrDefault("day", ""),
                        dateIso = s.safeStringOrDefault("date_iso", ""),
                        dateDisplay = s.safeStringOrDefault("date_display", ""),
                        type = s.safeStringOrDefault("type", "Lecture"),
                        batch = s.safeString("batch"),
                        status = s.safeStringOrDefault("status", "Pending"),
                        adjustment = null  // Parse adjustment if needed
                    )
                } catch (e: Exception) {
                    null  // Skip malformed entries
                }
            } ?: emptyList()

            // Get weekly load and pending leaves
            val weeklyClasses = statsJson.get("weekly_classes").safeInt() ?: 0
            val pendingLeavesElement = widgetsJson.get("pending_leaves")
            val pendingLeavesArr = if (pendingLeavesElement != null && pendingLeavesElement.isJsonArray)
                pendingLeavesElement.asJsonArray else null
            val pendingLeavesCount = pendingLeavesArr?.size() ?: 0

            return StaffDashboardData(
                profile = profile,
                todaySchedule = todaySchedule,
                upcomingSchedule = upcomingSchedule,
                totalSubjects = totalSubjects,
                totalStudents = 0,  // Not returned by this endpoint
                sessionsThisMonth = weeklyClasses,  // Using weekly_classes as sessions indicator
                pendingLeaveRequests = pendingLeavesCount,
                roles = profile.roles,
                classTeacherSection = classTeacherInfo,
                hodDepartment = hodInfo,
                mentorBatch = mentorBatchInfo
            )
        }
    }

    /**
     * Get attendance sheet for marking attendance.
     * Backend returns: { subject_name, class_name, time, date_display, is_locked, students[], subject_id }
     * scheduleId can be an integer string or "extra_X" for extra sessions.
     */
    fun getAttendanceSheet(
        baseUrl: String,
        accessToken: String,
        scheduleId: String,
        date: String
    ): AttendanceSheet {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/attendance/sheet?schedule_id=$scheduleId&date=$date")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load attendance sheet: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
                ?: throw ApiException("Invalid response from server")

            // Backend returns flat structure, not nested allocation/schedule objects
            val subjectName = json.get("subject_name").safeString() ?: ""
            val className = json.get("class_name").safeString() ?: ""
            val timeStr = json.get("time").safeString() ?: ""
            val subjectId = json.get("subject_id").safeInt() ?: 0
            val isLocked = json.get("is_locked").safeBool() ?: false

            // Parse time string "09:00 AM - 10:00 AM" into start/end
            val timeParts = timeStr.split(" - ")
            val startTime = timeParts.getOrNull(0) ?: ""
            val endTime = timeParts.getOrNull(1) ?: ""

            // Parse class name "TY-DA (A)" into class level, section, batch
            val classMatch = Regex("""(\w+)-(\w+)(?:\s*\((\w+)\))?""").find(className)
            val classLevel = classMatch?.groupValues?.getOrNull(1) ?: ""
            val sectionName = classMatch?.groupValues?.getOrNull(2) ?: ""
            val batchDivision = classMatch?.groupValues?.getOrNull(3)?.takeIf { it.isNotBlank() }

            // Build allocation from flat response
            val allocation = SubjectAllocation(
                allocationId = 0,
                subjectId = subjectId,
                subjectName = subjectName,
                subjectCode = "",
                sectionId = 0,
                sectionName = sectionName,
                classLevel = classLevel,
                sessionType = "Lecture",
                batchDivision = batchDivision
            )

            // Build schedule info
            // Parse scheduleId - for extra sessions "extra_X" extract the number, for regular schedules parse as int
            val parsedScheduleId = if (scheduleId.startsWith("extra_")) {
                scheduleId.removePrefix("extra_").toIntOrNull() ?: 0
            } else {
                scheduleId.toIntOrNull() ?: 0
            }
            val scheduleInfo = ScheduledClass(
                scheduleId = parsedScheduleId,
                dayOfWeek = "",
                startTime = startTime,
                endTime = endTime,
                subject = allocation,
                roomNumber = "",
                roomType = "Classroom",
                isCompleted = isLocked,
                sessionId = null
            )

            // Parse students - backend uses roll_no not roll_number
            // Backend returns: student_id, name, roll_no, status, is_on_duty, status_label
            // status: "Present", "OnDuty", "ML", "CL", "Absent"
            // status_label: "Event OD", "Approved ML", "Approved CL", etc.
            val studentsArr = json.getAsJsonArray("students")
            val students = studentsArr?.map { elem ->
                val st = elem.asJsonObject
                val status = st.get("status").safeString() ?: "Present"
                val statusLabel = st.get("status_label").safeString()
                val backendIsOnDuty = st.get("is_on_duty").safeBool() ?: false
                // isOnDuty should be true for any approved leave/duty status (OD, ML, CL)
                // Use StatusUtils for robust matching of status variants (handles case/spacing)
                val isOnDuty = backendIsOnDuty || StatusUtils.isLeaveOrDuty(status)
                // isPresent should be true for Present and any approved leave/duty status
                val isPresent = StatusUtils.isPresentLike(status)
                StudentForAttendance(
                    studentId = st.get("student_id").safeString() ?: "",
                    rollNumber = st.get("roll_no").safeString() ?: "",
                    name = st.get("name").safeString() ?: "",
                    admissionNumber = st.get("roll_no").safeString() ?: "",
                    isPresent = isPresent,
                    remarks = statusLabel,
                    status = status,
                    statusLabel = statusLabel,
                    isOnDuty = isOnDuty
                )
            } ?: emptyList()

            // Topics not returned by this endpoint
            val topics = emptyList<TopicForSelection>()

            return AttendanceSheet(
                allocation = allocation,
                scheduleInfo = scheduleInfo,
                students = students,
                topics = topics
            )
        }
    }

    /**
     * Submit attendance for a session.
     * Backend expects: schedule_id, date, students[{student_id, status, is_on_duty}], topic_ids
     */
    fun submitAttendance(
        baseUrl: String,
        accessToken: String,
        submission: AttendanceSubmission
    ): Boolean {
        // Build students array matching backend expectations
        val studentsArray = submission.attendance.map { record ->
            JsonObject().apply {
                addProperty("student_id", record.studentId)
                addProperty("status", record.status.toApiString())
                // is_on_duty should be true for ON_DUTY status
                addProperty("is_on_duty", record.status == AttendanceStatus.ON_DUTY)
            }
        }

        val payload = JsonObject().apply {
            addProperty("schedule_id", submission.scheduleId)
            addProperty("date", submission.conductedDate)  // Backend expects "date" not "conducted_date"
            // Send topic_ids array for multi-select lesson tracking
            if (!submission.topicIds.isNullOrEmpty()) {
                add("topic_ids", gson.toJsonTree(submission.topicIds))
            }
            add("students", gson.toJsonTree(studentsArray))  // Backend expects "students" not "attendance"
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/attendance/submit")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Failed to submit attendance: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    /**
     * Get leave requests for staff approval (includes pending, approved, rejected) and on-duty students.
     */
    fun getLeaveRequests(baseUrl: String, accessToken: String, userId: String): LeaveApprovalsData {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/leave_requests?user_id=$userId&include_all=true")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load leave requests: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)

            // Parse leave requests
            val requestsArr = json.getAsJsonArray("requests")
            val leaveRequests = requestsArr?.mapNotNull { elem ->
                try {
                    val r = elem.asJsonObject
                    LeaveRequest(
                        leaveId = r.get("leave_id").safeInt() ?: 0,
                        applicantId = 0, // Not provided by this endpoint
                        applicantName = r.get("student_name").safeString() ?: "",
                        applicantType = "Student",
                        applicantClass = r.get("class_name").safeString(),
                        leaveType = LeaveType.fromString(r.get("leave_type").safeString() ?: "General"),
                        startDate = r.get("start_date").safeString() ?: "",
                        endDate = r.get("end_date").safeString() ?: "",
                        totalDays = r.get("days").safeDouble() ?: 0.0,
                        reason = r.get("reason").safeString() ?: "",
                        status = LeaveStatus.fromString(r.get("status").safeString() ?: "Pending"),
                        appliedOn = r.get("applied_on").safeString() ?: "",
                        documentUrl = null
                    )
                } catch (e: Exception) {
                    null
                }
            } ?: emptyList()

            // Parse on-duty students
            val onDutyArr = json.getAsJsonArray("on_duty_students")
            val onDutyStudents = onDutyArr?.mapNotNull { elem ->
                try {
                    val s = elem.asJsonObject
                    val eventsArr = s.getAsJsonArray("events")
                    val events = eventsArr?.mapNotNull { e ->
                        try {
                            val ev = e.asJsonObject
                            OnDutyEvent(
                                eventId = ev.get("event_id").safeInt() ?: 0,
                                eventName = ev.get("event_name").safeString() ?: "",
                                role = ev.get("role").safeString() ?: "Participant",
                                status = ev.get("status").safeString() ?: "Nominated",
                                dateRange = ev.get("date_range").safeString() ?: "",
                                isToday = ev.get("is_today").safeBool() ?: false
                            )
                        } catch (e: Exception) {
                            null
                        }
                    } ?: emptyList()

                    OnDutyStudent(
                        studentId = s.get("student_id").safeString() ?: "",
                        studentName = s.get("student_name").safeString() ?: "",
                        rollNo = s.get("roll_no").safeString() ?: "",
                        events = events
                    )
                } catch (e: Exception) {
                    null
                }
            } ?: emptyList()

            return LeaveApprovalsData(
                requests = leaveRequests,
                onDutyStudents = onDutyStudents
            )
        }
    }

    /**
     * Perform leave action (approve/reject/escalate).
     */
    fun performLeaveAction(
        baseUrl: String,
        accessToken: String,
        action: LeaveAction
    ): Boolean {
        val payload = JsonObject().apply {
            addProperty("leave_id", action.leaveId)
            addProperty("action", action.action.toApiString())
            action.remarks?.let { addProperty("remarks", it) }
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/leave_action")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Leave action failed: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    /**
     * Get subject allocations for staff.
     */
    fun getSubjectAllocations(baseUrl: String, accessToken: String): List<SubjectAllocation> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/allocations")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load allocations: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val allocArr = json.getAsJsonArray("allocations")

            return allocArr?.map { elem ->
                val a = elem.asJsonObject
                SubjectAllocation(
                    allocationId = a.get("allocation_id")?.asInt ?: 0,
                    subjectId = a.get("subject_id")?.asInt ?: 0,
                    subjectName = a.get("subject_name")?.asString ?: "",
                    subjectCode = a.get("subject_code")?.asString ?: "",
                    sectionId = a.get("section_id")?.asInt ?: 0,
                    sectionName = a.get("section_name")?.asString ?: "",
                    classLevel = a.get("class_level")?.asString ?: "",
                    sessionType = a.get("session_type")?.asString ?: "Lecture",
                    batchDivision = a.get("batch_division")?.asString
                )
            } ?: emptyList()
        }
    }

    // ========================================
    // NOTIFICATIONS
    // ========================================

    /**
     * Get notifications for current user.
     */
    fun getNotifications(baseUrl: String, accessToken: String): List<Notification> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/v1/notifications")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load notifications: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val notifArr = json.getAsJsonArray("notifications")

            return notifArr?.map { elem ->
                val n = elem.asJsonObject

                // Helper to safely get string from JsonObject (handles JsonNull)
                fun JsonObject.safeString(key: String): String? {
                    val el = this.get(key)
                    return if (el == null || el.isJsonNull) null else el.asString
                }

                // Parent notifications can include a `child` object.
                // If present, prefix the title with the child's first name to match web UX.
                val childPrefix = try {
                    val childEl = n.get("child")
                    if (childEl != null && !childEl.isJsonNull && childEl.isJsonObject) {
                        val child = childEl.asJsonObject
                        val childName = child.safeString("name").orEmpty().trim()
                        val firstName = childName.split(" ").firstOrNull().orEmpty()
                        if (firstName.isNotBlank()) "[$firstName] " else ""
                    } else ""
                } catch (_: Exception) {
                    ""
                }

                Notification(
                    id = n.get("id")?.asInt ?: 0,
                    title = childPrefix + (n.safeString("title") ?: ""),
                    message = n.safeString("message") ?: "",
                    timestamp = n.safeString("timestamp") ?: "",
                    type = NotificationType.fromString(n.safeString("type") ?: "info"),
                    isRead = n.get("is_read")?.asBoolean ?: false,
                    actionUrl = n.safeString("link")
                )
            } ?: emptyList()
        }
    }

    /**
     * Mark notification as read.
     */
    fun markNotificationRead(baseUrl: String, accessToken: String, notificationId: Int): Boolean {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/v1/notifications/$notificationId/read")
            .header("Authorization", "Bearer $accessToken")
            .post("".toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            return response.isSuccessful
        }
    }

    /**
     * Clear all notifications for the current user.
     */
    fun clearNotifications(baseUrl: String, accessToken: String): Boolean {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/v1/notifications/clear")
            .header("Authorization", "Bearer $accessToken")
            .delete()
            .build()

        client.newCall(request).execute().use { response ->
            return response.isSuccessful
        }
    }

    // ========================================
    // MENTOR APIs
    // ========================================

    /**
     * Get mentees (students in mentor's batches).
     * Calls /api/staff/my_mentees endpoint.
     */
    fun getMentees(baseUrl: String, accessToken: String, userId: String): MentorDashboardData {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/my_mentees?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load mentees: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)

            // Parse mentees from backend response
            // Backend returns: { "mentees": [{ "id", "name", "roll", "class", "batch", "batch_id", "attendance", "father", "mother", "phone" }] }
            val menteesArr = json.getAsJsonArray("mentees")

            // Group mentees by batch to build batch list
            val batchMap = mutableMapOf<Int, MutableList<Mentee>>()
            val batchInfoMap = mutableMapOf<Int, Pair<String, String>>() // batchId -> (batchName, className)

            val mentees = menteesArr?.map { elem ->
                val m = elem.asJsonObject
                val batchId = m.get("batch_id")?.asInt ?: 0
                val batchName = m.get("batch")?.asString ?: ""
                val className = m.get("class")?.asString ?: ""

                // Track batch info
                if (batchId > 0 && !batchInfoMap.containsKey(batchId)) {
                    batchInfoMap[batchId] = Pair(batchName, className)
                }

                val mentee = Mentee(
                    studentId = m.get("id")?.asString ?: "",
                    name = m.get("name")?.asString ?: "",
                    rollNumber = m.get("roll")?.asString ?: "",
                    email = "",  // Not returned by this endpoint
                    phone = m.get("phone")?.asString,
                    attendancePercentage = m.get("attendance")?.asDouble,
                    openIssues = 0  // Not returned by this endpoint
                )

                // Add to batch map
                batchMap.getOrPut(batchId) { mutableListOf() }.add(mentee)

                mentee
            } ?: emptyList()

            // Build batches from collected info
            val batches = batchInfoMap.map { (batchId, info) ->
                val (batchName, className) = info
                val classParts = className.split("-")
                MentorBatchDetail(
                    batchId = batchId,
                    batchName = batchName,
                    sectionName = classParts.getOrNull(1) ?: "",
                    classLevel = classParts.getOrNull(0) ?: "",
                    studentCount = batchMap[batchId]?.size ?: 0
                )
            }

            return MentorDashboardData(
                batches = batches,
                mentees = mentees,
                pendingIssues = emptyList(),  // Loaded separately via getMentorPendingIssues
                upcomingMeeting = null,
                totalMentees = mentees.size,
                openIssuesCount = 0
            )
        }
    }

    /**
     * Get pending issues (Open logs) for a mentor.
     */
    fun getMentorPendingIssues(baseUrl: String, accessToken: String, mentorId: String): List<MentorLog> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/mentor/my_pending_issues?mentor_id=$mentorId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load pending issues: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val issuesArr = json.getAsJsonArray("issues")

            return issuesArr?.map { elem ->
                val i = elem.asJsonObject
                MentorLog(
                    logId = i.get("log_id")?.asInt ?: 0,
                    studentId = i.get("student_id")?.asString ?: "",
                    studentName = i.get("student_name")?.asString ?: "",
                    category = IssueCategory.fromString(i.get("category")?.asString ?: ""),
                    description = i.get("remarks")?.asString ?: "",
                    status = IssueStatus.fromString(i.get("status")?.asString ?: "Open"),
                    createdAt = i.get("date")?.asString ?: "",
                    resolvedAt = null
                )
            } ?: emptyList()
        }
    }

    /**
     * Get all log history for a student (all statuses including resolved).
     */
    fun getStudentLogHistory(baseUrl: String, accessToken: String, studentId: String): List<MentorLog> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/mentor/get_logs?student_id=$studentId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load log history: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val logsArr = json.getAsJsonArray("logs")

            return logsArr?.map { elem ->
                val l = elem.asJsonObject
                MentorLog(
                    logId = l.get("id")?.asInt ?: 0,
                    studentId = studentId,
                    studentName = "",  // Not returned by this endpoint
                    category = IssueCategory.fromString(l.get("category")?.asString ?: ""),
                    description = l.get("remarks")?.asString ?: "",
                    status = IssueStatus.fromString(l.get("status")?.asString ?: "Open"),
                    createdAt = l.get("date")?.asString ?: "",
                    resolvedAt = null
                )
            } ?: emptyList()
        }
    }

    /**
     * Get detailed mentee profile.
     */
    fun getMenteeDetail(baseUrl: String, accessToken: String, studentId: String): MenteeDetail {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/mentor/mentee/$studentId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load mentee details: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val studentJson = json.getAsJsonObject("student") ?: JsonObject()
            val statsJson = json.getAsJsonObject("stats") ?: JsonObject()

            // Parse subject-wise attendance
            val subjectsArr = json.getAsJsonArray("subjects")
            val subjects = subjectsArr?.map { elem ->
                val s = elem.asJsonObject
                SubjectAttendance(
                    subjectName = s.get("subject_name")?.asString ?: "",
                    subjectCode = s.get("subject_code")?.asString ?: "",
                    attended = s.get("attended")?.asInt ?: 0,
                    total = s.get("total")?.asInt ?: 0,
                    percentage = s.get("percentage")?.asDouble ?: 0.0
                )
            } ?: emptyList()

            // Parse logs
            val logsArr = json.getAsJsonArray("logs")
            val logs = logsArr?.map { elem ->
                val l = elem.asJsonObject
                MentorLog(
                    logId = l.get("log_id")?.asInt ?: 0,
                    studentId = studentId,
                    studentName = studentJson.get("name")?.asString ?: "",
                    category = IssueCategory.fromString(l.get("category")?.asString ?: ""),
                    description = l.get("remarks")?.asString ?: "",
                    status = IssueStatus.fromString(l.get("status")?.asString ?: ""),
                    createdAt = l.get("date")?.asString ?: "",
                    resolvedAt = null
                )
            } ?: emptyList()

            return MenteeDetail(
                studentId = studentJson.get("student_id")?.asString ?: studentId,
                name = studentJson.get("name")?.asString ?: "",
                rollNumber = studentJson.get("roll_number")?.asString ?: "",
                email = studentJson.get("email")?.asString ?: "",
                phone = studentJson.get("phone")?.asString,
                className = studentJson.get("class")?.asString ?: "",
                overallAttendance = statsJson.get("percentage")?.asDouble ?: 0.0,
                totalLectures = statsJson.get("total")?.asInt ?: 0,
                attended = statsJson.get("attended")?.asInt ?: 0,
                isDefaulter = statsJson.get("is_defaulter")?.asBoolean ?: false,
                subjectAttendance = subjects,
                logs = logs,
                hasDetention = json.get("detention") != null && !json.get("detention").isJsonNull,
                hasEscalation = json.get("escalation") != null && !json.get("escalation").isJsonNull
            )
        }
    }

    /**
     * Add a mentor log for a student.
     */
    fun addMentorLog(
        baseUrl: String,
        accessToken: String,
        studentId: String,
        mentorId: String,
        category: String,
        remarks: String,
        actionTaken: String?
    ): Boolean {
        val payload = JsonObject().apply {
            addProperty("student_id", studentId)
            addProperty("mentor_id", mentorId)
            addProperty("category", category)
            addProperty("remarks", remarks)
            actionTaken?.let { addProperty("action_taken", it) }
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/mentor/add_log")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Failed to add log: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    /**
     * Update mentor log status.
     */
    fun updateLogStatus(
        baseUrl: String,
        accessToken: String,
        logId: Int,
        newStatus: String
    ): Boolean {
        val payload = JsonObject().apply {
            addProperty("log_id", logId)
            addProperty("status", newStatus)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/mentor/update_log_status")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Failed to update log: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    /**
     * Schedule a mentor meeting.
     */
    fun scheduleMentorMeeting(
        baseUrl: String,
        accessToken: String,
        mentorId: String,
        batchId: Int,
        date: String,
        time: String,
        agenda: String,
        venue: String? = null,
        discussionPoints: String? = null
    ): Boolean {
        val payload = JsonObject().apply {
            addProperty("mentor_id", mentorId)
            addProperty("batch_id", batchId)
            addProperty("date", date)
            addProperty("time", time)
            addProperty("agenda", agenda)
            venue?.let { addProperty("venue", it) }
            discussionPoints?.let { addProperty("discussion_points", it) }
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/mentor/schedule_meeting")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Failed to schedule meeting: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    /**
     * Get mentor meetings.
     */
    fun getMentorMeetings(baseUrl: String, accessToken: String, batchId: Int): List<MentorMeeting> {
        val url = "${baseUrl.trimEnd('/')}/api/mentor/get_meetings?batch_id=$batchId"
        android.util.Log.d("ApiService", "getMentorMeetings: calling $url")

        val request = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            android.util.Log.d("ApiService", "getMentorMeetings: response code=${response.code}, body=$body")

            if (!response.isSuccessful) {
                android.util.Log.e("ApiService", "getMentorMeetings failed: code=${response.code}, body=$body")
                throw ApiException("Failed to load meetings: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val meetingsArr = json.getAsJsonArray("meetings")
            android.util.Log.d("ApiService", "getMentorMeetings: parsed ${meetingsArr?.size() ?: 0} meetings")

            return meetingsArr?.map { elem ->
                val m = elem.asJsonObject
                MentorMeeting(
                    meetingId = m.get("id").safeInt() ?: 0,
                    batchId = m.get("batch_id").safeInt() ?: batchId,
                    scheduledDate = m.get("date").safeString() ?: "",
                    scheduledTime = m.get("time").safeString() ?: "",
                    agenda = m.get("agenda").safeString() ?: "",
                    isCompleted = m.get("status").safeString() == "Completed",
                    attendeeCount = m.get("attendance_count").safeInt(),
                    venue = m.get("venue").safeString(),
                    discussionPoints = m.get("discussion_points").safeString(),
                    summary = m.get("summary").safeString(),
                    batchName = m.get("batch_name").safeString()
                )
            } ?: emptyList()
        }
    }

    /**
     * Get meeting details with attendance and issues.
     */
    fun getMeetingDetails(baseUrl: String, accessToken: String, meetingId: Int): MeetingDetails {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/mentor/get_meeting_details?meeting_id=$meetingId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load meeting details: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val meetingJson = json.getAsJsonObject("meeting")
            val studentsArr = json.getAsJsonArray("students")
            val attendanceArr = json.getAsJsonArray("attendance")
            val issuesArr = json.getAsJsonArray("issues")

            val meeting = MentorMeeting(
                meetingId = meetingJson.get("id").safeInt() ?: meetingId,
                batchId = meetingJson.get("batch_id").safeInt() ?: 0,
                scheduledDate = meetingJson.get("date").safeString() ?: "",
                scheduledTime = meetingJson.get("time").safeString() ?: "",
                agenda = meetingJson.get("agenda").safeString() ?: "",
                isCompleted = meetingJson.get("status").safeString() == "Completed",
                attendeeCount = null,
                venue = meetingJson.get("venue").safeString(),
                discussionPoints = meetingJson.get("discussion_points").safeString(),
                summary = meetingJson.get("summary").safeString(),
                batchName = meetingJson.get("batch_name").safeString()
            )

            val students = studentsArr?.map { elem ->
                val s = elem.asJsonObject
                MeetingStudent(
                    studentId = s.get("student_id").safeString() ?: "",
                    name = s.get("name").safeString() ?: "",
                    rollNo = s.get("roll_no").safeString() ?: ""
                )
            } ?: emptyList()

            val attendance = attendanceArr?.map { elem ->
                val a = elem.asJsonObject
                MeetingAttendance(
                    studentId = a.get("student_id").safeString() ?: "",
                    attended = a.get("attended").safeBool() ?: false,
                    remarks = a.get("remarks").safeString()
                )
            } ?: emptyList()

            val issues = issuesArr?.map { elem ->
                val i = elem.asJsonObject
                MeetingIssue(
                    issueId = i.get("issue_id").safeInt() ?: 0,
                    raisedByStudentId = i.get("raised_by_student_id").safeString(),
                    raisedByName = i.get("raised_by_name").safeString(),
                    issueDescription = i.get("issue_description").safeString() ?: "",
                    category = i.get("category").safeString() ?: "General",
                    actionTaken = i.get("action_taken").safeString(),
                    actionStatus = i.get("action_status").safeString() ?: "Pending"
                )
            } ?: emptyList()

            return MeetingDetails(meeting, students, attendance, issues)
        }
    }

    /**
     * Conduct/complete a meeting with attendance data.
     */
    fun conductMeeting(
        baseUrl: String,
        accessToken: String,
        meetingId: Int,
        venue: String?,
        discussionPoints: String?,
        summary: String?,
        attendance: List<Map<String, Any?>>
    ): Boolean {
        val attendanceArr = JsonArray()
        attendance.forEach { att ->
            val obj = JsonObject().apply {
                addProperty("student_id", att["student_id"] as? String)
                addProperty("attended", att["attended"] as? Boolean ?: false)
                (att["remarks"] as? String)?.let { addProperty("remarks", it) }
            }
            attendanceArr.add(obj)
        }

        val payload = JsonObject().apply {
            addProperty("meeting_id", meetingId)
            venue?.let { addProperty("venue", it) }
            discussionPoints?.let { addProperty("discussion_points", it) }
            summary?.let { addProperty("summary", it) }
            add("attendance", attendanceArr)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/mentor/conduct_meeting")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Failed to complete meeting: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    /**
     * Add an issue to a meeting.
     */
    fun addMeetingIssue(
        baseUrl: String,
        accessToken: String,
        meetingId: Int,
        raisedByStudentId: String?,
        issueDescription: String,
        category: String,
        actionTaken: String?
    ): MeetingIssue {
        val payload = JsonObject().apply {
            addProperty("meeting_id", meetingId)
            raisedByStudentId?.let { addProperty("raised_by_student_id", it) }
            addProperty("issue_description", issueDescription)
            addProperty("category", category)
            actionTaken?.let { addProperty("action_taken", it) }
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/mentor/add_meeting_issue")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to add issue: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val i = json.getAsJsonObject("issue")
            return MeetingIssue(
                issueId = i.get("issue_id")?.asInt ?: 0,
                raisedByStudentId = raisedByStudentId,
                raisedByName = null,
                issueDescription = issueDescription,
                category = category,
                actionTaken = actionTaken,
                actionStatus = if (actionTaken.isNullOrBlank()) "Pending" else "In Progress"
            )
        }
    }

    // ========================================
    // CLASS TEACHER APIs
    // ========================================

    /**
     * Get class teacher analytics - subject performance, defaulters, top students.
     */
    fun getClassTeacherAnalytics(baseUrl: String, accessToken: String, userId: String): ClassTeacherAnalytics {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/class_teacher/analytics?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load analytics: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
                ?: throw ApiException("Invalid JSON response")

            // Parse class_info
            val classInfoJson = json.getAsJsonObject("class_info") ?: JsonObject()
            val classInfo = ClassInfo(
                name = classInfoJson.get("name")?.asString ?: "",
                totalStudents = classInfoJson.get("total_students")?.asInt ?: 0,
                totalSessions = classInfoJson.get("total_sessions")?.asInt ?: 0
            )

            // Parse summary
            val summaryJson = json.getAsJsonObject("summary") ?: JsonObject()
            val summary = ClassSummary(
                defaulterCount = summaryJson.get("defaulter_count")?.asInt ?: 0,
                pendingLeaves = summaryJson.get("pending_leaves")?.asInt ?: 0,
                classHealth = summaryJson.get("class_health")?.asString ?: "Good"
            )

            // Parse subjects
            val subjectsArr = json.getAsJsonArray("subjects")
            val subjects = subjectsArr?.map { elem ->
                val s = elem.asJsonObject
                SubjectStats(
                    subjectId = s.get("id")?.asInt ?: 0,
                    subjectName = s.get("subject")?.asString ?: "",
                    teacherName = s.get("teacher")?.asString ?: "",
                    sessionsConducted = s.get("conducted")?.asInt ?: 0,
                    avgAttendance = s.get("avg_attendance")?.asDouble ?: 0.0
                )
            } ?: emptyList()

            // Parse defaulters
            val defaultersArr = json.getAsJsonArray("defaulters")
            val defaulters = defaultersArr?.map { elem ->
                val d = elem.asJsonObject
                StudentAttendanceInfo(
                    name = d.get("name")?.asString ?: "",
                    rollNumber = d.get("roll")?.asString ?: "",
                    percentage = d.get("perc")?.asDouble ?: 0.0,
                    attended = d.get("attended")?.asInt ?: 0,
                    total = d.get("total")?.asInt ?: 0
                )
            } ?: emptyList()

            // Parse top students
            val topStudentsArr = json.getAsJsonArray("top_students")
            val topStudents = topStudentsArr?.map { elem ->
                val t = elem.asJsonObject
                StudentAttendanceInfo(
                    name = t.get("name")?.asString ?: "",
                    rollNumber = t.get("roll")?.asString ?: "",
                    percentage = t.get("perc")?.asDouble ?: 0.0,
                    attended = t.get("attended")?.asInt ?: 0,
                    total = t.get("total")?.asInt ?: 0
                )
            } ?: emptyList()

            return ClassTeacherAnalytics(
                classInfo = classInfo,
                summary = summary,
                subjects = subjects,
                defaulters = defaulters,
                topStudents = topStudents
            )
        }
    }

    // ========================================
    // PASSWORD MANAGEMENT
    // ========================================

    /**
     * Change user's password.
     * Used for first-time login password reset and regular password changes.
     */
    fun changePassword(
        baseUrl: String,
        accessToken: String,
        currentPassword: String,
        newPassword: String,
        confirmPassword: String
    ): Boolean {
        val url = "${baseUrl.trimEnd('/')}/api/change-password"

        val payload = JsonObject().apply {
            addProperty("current_password", currentPassword)
            addProperty("new_password", newPassword)
            addProperty("confirm_password", confirmPassword)
        }

        val request = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $accessToken")
            .post(payload.toString().toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()

            if (!response.isSuccessful) {
                throw ApiException(parseError(body), response.code)
            }

            return true
        }
    }

    // ========================================
    // UPCOMING SCHEDULE & ADJUSTMENT APIs
    // ========================================

    /**
     * Get upcoming schedule from dashboard widgets.
     * Returns today's schedule + upcoming schedule with adjustment info.
     */
    fun getUpcomingSchedule(baseUrl: String, accessToken: String, userId: String): Pair<List<UpcomingClass>, List<UpcomingClass>> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/dashboard?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load schedule: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val widgetsJson = json.getAsJsonObject("widgets") ?: JsonObject()

            fun parseScheduleList(arr: com.google.gson.JsonArray?): List<UpcomingClass> {
                return arr?.map { elem ->
                    val s = elem.asJsonObject
                    val adjustmentJson = s.get("adjustment")
                    val adjustment = if (adjustmentJson != null && !adjustmentJson.isJsonNull && adjustmentJson.isJsonObject) {
                        val adj = adjustmentJson.asJsonObject
                        val swapJson = adj.get("swap")
                        val swap = if (swapJson != null && !swapJson.isJsonNull && swapJson.isJsonObject) {
                            val sw = swapJson.asJsonObject
                            SwapSlotInfo(
                                scheduleId = sw.get("schedule_id").safeInt() ?: 0,
                                day = sw.get("day").safeString() ?: "",
                                time = sw.get("time").safeString() ?: "",
                                subject = sw.get("subject").safeString() ?: "",
                                className = sw.get("class").safeString() ?: "",
                                dateIso = sw.get("date_iso").safeString() ?: "",
                                dateDisplay = sw.get("date_display").safeString() ?: ""
                            )
                        } else null

                        AdjustmentInfo(
                            id = adj.get("id").safeInt() ?: 0,
                            status = adj.get("status").safeString() ?: "",
                            role = adj.get("role").safeString() ?: "",
                            kind = adj.get("kind").safeString() ?: "",
                            partnerId = adj.get("partner_id").safeString() ?: "",
                            partnerName = adj.get("partner_name").safeString() ?: "",
                            partnerCode = adj.get("partner_code").safeString() ?: "",
                            swap = swap
                        )
                    } else null

                    UpcomingClass(
                        scheduleId = s.get("id").safeInt() ?: 0,
                        time = s.get("time").safeString() ?: "",
                        className = s.get("class").safeString() ?: "",
                        subject = s.get("subject").safeString() ?: "",
                        day = s.get("day").safeString() ?: "",
                        dateIso = s.get("date_iso").safeString() ?: "",
                        dateDisplay = s.get("date_display").safeString() ?: "",
                        type = s.get("type").safeString() ?: "Lecture",
                        batch = s.get("batch").safeString(),
                        status = s.get("status").safeString() ?: "Pending",
                        adjustment = adjustment
                    )
                } ?: emptyList()
            }

            val todaySchedule = parseScheduleList(
                widgetsJson.get("today_schedule")?.takeIf { it.isJsonArray }?.asJsonArray
            )
            val upcomingSchedule = parseScheduleList(
                widgetsJson.get("upcoming_schedule")?.takeIf { it.isJsonArray }?.asJsonArray
            )

            return Pair(todaySchedule, upcomingSchedule)
        }
    }

    /**
     * Find available faculty for session adjustment.
     */
    fun findAdjustmentFaculty(
        baseUrl: String,
        accessToken: String,
        scheduleId: Int,
        date: String,
        userId: String
    ): List<AdjustmentFaculty> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/find_adjustment_faculty?schedule_id=$scheduleId&date=$date&user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to find faculty: ${parseError(body)}", response.code)
            }

            // Backend returns a JSON array directly, not wrapped in an object
            val facultyArr = gson.fromJson(body, JsonArray::class.java)

            return facultyArr?.mapNotNull { elem ->
                try {
                    val f = elem.asJsonObject
                    val slotsArr = f.getAsJsonArray("slots")
                    val slots = slotsArr?.mapNotNull { slotElem ->
                        try {
                            val sl = slotElem.asJsonObject
                            AvailableSlot(
                                scheduleId = sl.get("id").safeInt() ?: 0,  // Backend uses 'id' not 'schedule_id'
                                day = sl.get("day").safeString() ?: "",
                                time = sl.get("time").safeString() ?: "",
                                subject = sl.get("subject").safeString() ?: "",
                                className = f.get("class_division").safeString() ?: "",  // Use class_division from parent
                                dateIso = sl.get("date_iso").safeString() ?: "",
                                dateDisplay = sl.get("date_display").safeString() ?: ""
                            )
                        } catch (e: Exception) {
                            null
                        }
                    } ?: emptyList()

                    AdjustmentFaculty(
                        facultyId = f.get("id").safeString() ?: "",
                        name = f.get("name").safeString() ?: "",
                        code = f.get("dept").safeString() ?: "",  // Backend uses 'dept' not 'code'
                        availableSlots = slots
                    )
                } catch (e: Exception) {
                    null
                }
            } ?: emptyList()
        }
    }

    /**
     * Submit an adjustment request.
     */
    fun submitAdjustment(
        baseUrl: String,
        accessToken: String,
        request: AdjustmentRequest
    ): Int {
        val payload = JsonObject().apply {
            addProperty("requester_id", request.requesterId)
            addProperty("schedule_id", request.scheduleId)
            addProperty("original_date", request.originalDate)
            addProperty("substitute_id", request.substituteId)
            addProperty("swap_slot_id", request.swapSlotId)
            addProperty("compensation_date", request.compensationDate)
            request.reason?.let { addProperty("reason", it) }
        }

        val httpRequest = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/submit_adjustment")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(httpRequest).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to submit adjustment: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            return json.get("id")?.asInt ?: 0
        }
    }

    /**
     * Respond to an adjustment request (approve/reject).
     */
    fun respondToAdjustment(
        baseUrl: String,
        accessToken: String,
        requestId: Int,
        status: String  // "Approved" or "Rejected"
    ): Boolean {
        val payload = JsonObject().apply {
            addProperty("request_id", requestId)
            addProperty("status", status)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/respond_adjustment")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Failed to respond to adjustment: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    // ========================================
    // SESSION HISTORY APIs
    // ========================================

    /**
     * Get session history (conducted sessions).
     */
    fun getSessionHistory(baseUrl: String, accessToken: String, userId: String): List<SessionHistoryRecord> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/session_history?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load session history: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val historyArr = json.getAsJsonArray("history")

            return historyArr?.map { elem ->
                val h = elem.asJsonObject
                SessionHistoryRecord(
                    scheduleId = h.get("schedule_id").safeInt() ?: 0,
                    dateIso = h.get("date_iso").safeString() ?: "",
                    dateDisplay = h.get("date_display").safeString() ?: "",
                    time = h.get("time").safeString() ?: "",
                    subject = h.get("subject").safeString() ?: "",
                    className = h.get("class").safeString() ?: "",
                    percentage = h.get("percentage").safeInt() ?: 0
                )
            } ?: emptyList()
        }
    }

    // ========================================
    // EVENT MANAGER APIs
    // ========================================

    /**
     * Get events created by the coordinator.
     */
    fun getMyEvents(baseUrl: String, accessToken: String, userId: String): List<EventSummary> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/events/my_events?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load events: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val eventsArr = json.getAsJsonArray("events")

            return eventsArr?.map { elem ->
                val e = elem.asJsonObject
                EventSummary(
                    eventId = e.get("id").safeInt() ?: 0,
                    name = e.get("name").safeString() ?: "",
                    dateDisplay = e.get("date").safeString() ?: "",
                    time = e.get("time").safeString(),
                    studentCount = e.get("student_count").safeInt() ?: 0
                )
            } ?: emptyList()
        }
    }

    /**
     * Create a new event.
     */
    fun createEvent(
        baseUrl: String,
        accessToken: String,
        eventRequest: EventCreateRequest
    ): Int {
        val payload = JsonObject().apply {
            addProperty("name", eventRequest.name)
            eventRequest.description?.let { addProperty("description", it) }
            addProperty("start_date", eventRequest.startDate)
            addProperty("end_date", eventRequest.endDate)
            eventRequest.startTime?.let { addProperty("start_time", it) }
            eventRequest.endTime?.let { addProperty("end_time", it) }
            addProperty("user_id", eventRequest.coordinatorId)  // Backend expects user_id
            addProperty("notify_all_students", eventRequest.notifyAllStudents)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/events/create")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to create event: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            return json.get("id")?.asInt ?: 0
        }
    }

    /**
     * Get participants for an event.
     */
    fun getEventParticipants(baseUrl: String, accessToken: String, eventId: Int): List<EventParticipant> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/events/participants?event_id=$eventId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load participants: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val participantsArr = json.getAsJsonArray("participants")

            return participantsArr?.map { elem ->
                val p = elem.asJsonObject
                EventParticipant(
                    participationId = p.get("participation_id").safeInt() ?: 0,
                    studentId = p.get("student_id").safeString() ?: "",
                    name = p.get("name").safeString() ?: "",
                    rollNumber = p.get("roll").safeString() ?: "",
                    className = p.get("class").safeString() ?: "",
                    role = p.get("role").safeString() ?: "Participant",
                    status = p.get("status").safeString() ?: "Nominated"
                )
            } ?: emptyList()
        }
    }

    /**
     * Add student to an event.
     */
    fun addEventParticipant(
        baseUrl: String,
        accessToken: String,
        eventId: Int,
        rollNo: String,
        role: String
    ): Boolean {
        val payload = JsonObject().apply {
            addProperty("event_id", eventId)
            addProperty("roll_no", rollNo)
            addProperty("role", role)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/events/add_student")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Failed to add participant: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    /**
     * Mark event attendance (toggle OD status).
     */
    fun markEventAttendance(
        baseUrl: String,
        accessToken: String,
        participationId: Int,
        attended: Boolean
    ): Boolean {
        val payload = JsonObject().apply {
            addProperty("participation_id", participationId)
            addProperty("status", attended)  // Backend expects "status" not "attended"
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/events/mark_attendance")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Failed to mark attendance: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    /**
     * Delete an event (only if no participants).
     */
    fun deleteEvent(
        baseUrl: String,
        accessToken: String,
        eventId: Int,
        userId: String
    ): Boolean {
        val payload = JsonObject().apply {
            addProperty("event_id", eventId)
            addProperty("user_id", userId)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/events/delete")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ApiException("Failed to delete event: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    /**
     * Get list of class sections for student selection.
     */
    fun getClassSections(baseUrl: String, accessToken: String): List<ClassSection> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/core/classes")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load classes: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val classesArr = json.getAsJsonArray("classes")

            return classesArr?.map { elem ->
                val c = elem.asJsonObject
                ClassSection(
                    sectionId = c.get("id").safeInt() ?: 0,
                    name = c.get("name").safeString() ?: "",
                    classLevel = c.get("class_level").safeString() ?: "",
                    departmentId = c.get("department_id").safeInt() ?: 0,
                    departmentName = c.get("department_name").safeString() ?: "",
                    classTeacherName = c.get("class_teacher_name").safeString(),
                    totalStudents = c.get("total_students").safeInt() ?: 0
                )
            } ?: emptyList()
        }
    }

    /**
     * Get students in a section for event participant selection.
     */
    fun getStudentsForEvent(baseUrl: String, accessToken: String, sectionId: Int): List<StudentForEvent> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/core/students?section_id=$sectionId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load students: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            val studentsArr = json.getAsJsonArray("students")

            return studentsArr?.map { elem ->
                val s = elem.asJsonObject
                // Backend returns "roll" as the admission number
                val roll = s.get("roll").safeString() ?: ""
                StudentForEvent(
                    studentId = s.get("id").safeString() ?: "",
                    name = s.get("name").safeString() ?: "",
                    rollNumber = roll,
                    admissionNumber = roll  // Same as rollNumber - used for add_student API
                )
            } ?: emptyList()
        }
    }

    // ========================================
    // STUDENT APIs
    // ========================================

    /**
     * Get student dashboard data.
     * Returns complete dashboard with profile, attendance, subjects, events, etc.
     */
    fun getStudentDashboard(baseUrl: String, accessToken: String, userId: String): StudentDashboardData {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/student/dashboard?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load dashboard: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)

            // Parse profile
            val profileJson = json.getAsJsonObject("profile")
            val profile = StudentProfileInfo(
                name = profileJson.get("name").safeString() ?: "",
                roll = profileJson.get("roll").safeString() ?: "",
                className = profileJson.get("class").safeString() ?: ""
            )

            // Parse stats
            val statsJson = json.getAsJsonObject("stats")
            val stats = AttendanceStats(
                percentage = statsJson.get("percentage").safeDouble() ?: 0.0,
                totalLectures = statsJson.get("total_lectures").safeInt() ?: 0,
                attended = statsJson.get("attended").safeInt() ?: 0,
                isDefaulter = statsJson.get("is_defaulter").safeBool() ?: false
            )

            // Parse subject-wise performance
            val subjectWise = json.getAsJsonArray("subject_wise")?.map { elem ->
                val s = elem.asJsonObject
                SubjectPerformance(
                    subject = s.get("subject").safeString() ?: "",
                    code = s.get("code").safeString() ?: "",
                    teacher = s.get("teacher").safeString() ?: "Unassigned",
                    conducted = s.get("conducted").safeInt() ?: 0,
                    attended = s.get("attended").safeInt() ?: 0,
                    percentage = s.get("percentage").safeDouble() ?: 0.0
                )
            } ?: emptyList()

            // Parse recent activity
            val recentActivity = json.getAsJsonArray("recent_activity")?.map { elem ->
                val a = elem.asJsonObject
                RecentActivity(
                    date = a.get("date").safeString() ?: "",
                    subject = a.get("subject").safeString() ?: "",
                    status = a.get("status").safeString() ?: "",
                    time = a.get("time").safeString() ?: ""
                )
            } ?: emptyList()

            // Parse events
            val events = json.getAsJsonArray("events")?.map { elem ->
                val e = elem.asJsonObject
                StudentEvent(
                    name = e.get("name").safeString() ?: "",
                    date = e.get("date").safeString() ?: "",
                    role = e.get("role").safeString() ?: "Participant",
                    status = e.get("status").safeString() ?: ""
                )
            } ?: emptyList()

            // Parse mentor info
            val mentorJson = json.get("mentor")
            val mentor = if (mentorJson != null && !mentorJson.isJsonNull) {
                val m = mentorJson.asJsonObject
                MentorInfo(
                    name = m.get("name").safeString() ?: "",
                    email = m.get("email").safeString() ?: "",
                    batchName = m.get("batch_name").safeString() ?: ""
                )
            } else null

            // Parse detention info
            val detentionJson = json.get("detention")
            val detention = if (detentionJson != null && !detentionJson.isJsonNull) {
                val d = detentionJson.asJsonObject
                DetentionInfo(
                    id = d.get("id").safeInt() ?: 0,
                    reason = d.get("reason").safeString() ?: "",
                    status = d.get("status").safeString() ?: "",
                    task = d.get("task").safeString(),
                    submissionUrl = d.get("submission_url").safeString()
                )
            } else null

            // Parse upcoming meeting
            val meetingJson = json.get("meeting")
            val meeting = if (meetingJson != null && !meetingJson.isJsonNull) {
                val m = meetingJson.asJsonObject
                UpcomingMeetingInfo(
                    date = m.get("date").safeString() ?: "",
                    time = m.get("time").safeString() ?: "",
                    agenda = m.get("agenda").safeString()
                )
            } else null

            // Parse results
            val results = json.getAsJsonArray("results")?.map { elem ->
                val r = elem.asJsonObject
                CAResult(
                    subject = r.get("subject").safeString() ?: "",
                    code = r.get("code").safeString() ?: "",
                    ta1 = r.get("ta1")?.let { if (it.isJsonNull) null else it.asString },
                    ta2 = r.get("ta2")?.let { if (it.isJsonNull) null else it.asString },
                    ta3 = r.get("ta3")?.let { if (it.isJsonNull) null else it.asString },
                    a1 = r.get("a1").safeInt(),
                    a2 = r.get("a2").safeInt()
                )
            } ?: emptyList()

            // Parse term grant
            val termGrantJson = json.get("term_grant")
            val termGrant = if (termGrantJson != null && !termGrantJson.isJsonNull) {
                val t = termGrantJson.asJsonObject
                TermGrantInfo(
                    status = t.get("status").safeString() ?: "",
                    remarks = t.get("remarks").safeString(),
                    attPerc = t.get("att_perc").safeDouble(),
                    caAvg = t.get("ca_avg").safeDouble()
                )
            } else null

            // Parse extra sessions (upcoming extra classes)
            val extraSessions = json.getAsJsonArray("extra_sessions")?.map { elem ->
                val es = elem.asJsonObject
                StudentExtraSession(
                    id = es.get("id").safeInt() ?: 0,
                    subject = es.get("subject").safeString() ?: "",
                    teacher = es.get("teacher").safeString() ?: "",
                    date = es.get("date").safeString() ?: "",
                    dateIso = es.get("date_iso").safeString() ?: "",
                    day = es.get("day").safeString() ?: "",
                    time = es.get("time").safeString() ?: "",
                    topic = es.get("topic").safeString(),
                    meetingLink = es.get("meeting_link").safeString(),
                    isToday = es.get("is_today").safeBool() ?: false
                )
            } ?: emptyList()

            return StudentDashboardData(
                profile = profile,
                stats = stats,
                subjectWise = subjectWise,
                recentActivity = recentActivity,
                events = events,
                mentor = mentor,
                detention = detention,
                meeting = meeting,
                results = results,
                termGrant = termGrant,
                extraSessions = extraSessions
            )
        }
    }

    /**
     * Submit detention task URL.
     */
    fun submitDetentionTask(baseUrl: String, accessToken: String, detentionId: Int, submissionUrl: String): Boolean {
        val payload = JsonObject().apply {
            addProperty("detention_id", detentionId)
            addProperty("submission_url", submissionUrl)
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/detention/submit_task")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to submit task: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    /**
     * Get pending feedback subjects.
     */
    fun getPendingFeedback(baseUrl: String, accessToken: String, userId: String): FeedbackPendingList? {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/feedback/pending_list?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                // 404 means no active feedback cycle
                if (response.code == 404) return null
                throw ApiException("Failed to load feedback: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)

            val cycleId = json.get("cycle_id").safeInt() ?: return null
            val cycleName = json.get("cycle_name").safeString() ?: ""
            val endDate = json.get("end_date").safeString() ?: ""

            val subjects = json.getAsJsonArray("pending_subjects")?.map { elem ->
                val s = elem.asJsonObject
                FeedbackSubject(
                    allocationId = s.get("allocation_id").safeInt() ?: 0,
                    subjectId = s.get("subject_id").safeInt() ?: 0,
                    subjectName = s.get("subject_name").safeString() ?: "",
                    subjectCode = s.get("subject_code").safeString() ?: "",
                    teacherName = s.get("teacher_name").safeString() ?: ""
                )
            } ?: emptyList()

            // Return null if no pending subjects
            if (subjects.isEmpty()) return null

            return FeedbackPendingList(
                cycleId = cycleId,
                cycleName = cycleName,
                endDate = endDate,
                subjects = subjects
            )
        }
    }

    /**
     * Get current academic term.
     */
    fun getCurrentTerm(baseUrl: String, accessToken: String): CurrentTerm? {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/current_term")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                return null
            }

            val json = gson.fromJson(body, JsonObject::class.java)

            return CurrentTerm(
                termId = json.get("term_id").safeInt() ?: 0,
                name = json.get("current_term").safeString() ?: json.get("name").safeString() ?: "",
                semesterType = json.get("semester_type").safeString() ?: "",
                academicYear = json.get("academic_year").safeString() ?: "",
                startDate = json.get("start_date").safeString() ?: "",
                endDate = json.get("end_date").safeString() ?: ""
            )
        }
    }

    /**
     * Get student results (CA marks and term grant).
     * Returns Pair of (results list, term grant info)
     */
    fun getStudentResults(baseUrl: String, accessToken: String): Pair<List<CAResult>, TermGrantInfo?> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/v1/student/results")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load results: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)

            // Parse results array
            val results = json.getAsJsonArray("results")?.map { elem ->
                val r = elem.asJsonObject
                CAResult(
                    subject = r.get("subject").safeString() ?: "",
                    code = r.get("code").safeString() ?: "",
                    ta1 = r.get("ta1")?.let { if (it.isJsonNull) null else it.asString },
                    ta2 = r.get("ta2")?.let { if (it.isJsonNull) null else it.asString },
                    ta3 = r.get("ta3")?.let { if (it.isJsonNull) null else it.asString },
                    a1 = r.get("a1").safeInt(),
                    a2 = r.get("a2").safeInt()
                )
            } ?: emptyList()

            // Parse term grant
            val termGrantJson = json.get("term_grant")
            val termGrant = if (termGrantJson != null && !termGrantJson.isJsonNull) {
                val t = termGrantJson.asJsonObject
                TermGrantInfo(
                    status = t.get("status").safeString() ?: "",
                    remarks = t.get("remarks").safeString(),
                    attPerc = t.get("att_perc").safeDouble(),
                    caAvg = t.get("ca_avg").safeDouble()
                )
            } else null

            return Pair(results, termGrant)
        }
    }

    /**
     * Get student timetable.
     */
    fun getStudentTimetable(baseUrl: String, accessToken: String, userId: String): List<StudentTimetableEntry> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/v1/student/timetable?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load timetable: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            // Backend returns "entries" not "schedule"
            val entriesArr = json.getAsJsonArray("entries") ?: return emptyList()

            return entriesArr.mapNotNull { elem ->
                try {
                    val s = elem.asJsonObject

                    // Subject is an object with name and code
                    val subjectObj = s.getAsJsonObject("subject")
                    val subjectName = subjectObj?.get("name").safeString() ?: ""
                    val subjectCode = subjectObj?.get("code").safeString() ?: ""

                    // Teacher is an object with name (or null)
                    val teacherObj = s.get("teacher")
                    val teacherName = if (teacherObj != null && !teacherObj.isJsonNull && teacherObj.isJsonObject) {
                        teacherObj.asJsonObject.get("name").safeString() ?: ""
                    } else ""

                    // Room is an object with room_number (or null)
                    val roomObj = s.get("room")
                    val roomNumber = if (roomObj != null && !roomObj.isJsonNull && roomObj.isJsonObject) {
                        roomObj.asJsonObject.get("room_number").safeString() ?: ""
                    } else ""

                    StudentTimetableEntry(
                        scheduleId = s.get("schedule_id").safeInt() ?: 0,
                        dayOfWeek = s.get("day_of_week").safeString() ?: "",
                        startTime = s.get("start_time").safeString() ?: "",
                        endTime = s.get("end_time").safeString() ?: "",
                        subjectName = subjectName,
                        subjectCode = subjectCode,
                        teacherName = teacherName,
                        roomNumber = roomNumber,
                        sessionType = s.get("session_type").safeString() ?: "Lecture",
                        batch = s.get("target_batch").safeString()
                    )
                } catch (e: Exception) {
                    null
                }
            }
        }
    }

    /**
     * Response data class for student leaves API
     */
    data class StudentLeavesResponse(
        val balance: LeaveBalance,
        val history: List<StudentLeaveRequest>,
        val blockedDates: List<String>
    )

    data class LeaveBalance(
        val total: Int,
        val used: Int,
        val remaining: Int
    )

    /**
     * Get student leave requests.
     */
    fun getStudentLeaves(baseUrl: String, accessToken: String): StudentLeavesResponse {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/v1/student/leaves")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load leaves: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)

            // Parse balance
            val balanceObj = json.getAsJsonObject("balance")
            val balance = LeaveBalance(
                total = balanceObj?.get("total")?.safeInt() ?: 20,
                used = balanceObj?.get("used")?.safeInt() ?: 0,
                remaining = balanceObj?.get("remaining")?.safeInt() ?: 20
            )

            // Parse history
            val historyArr = json.getAsJsonArray("history") ?: JsonArray()
            val history = historyArr.map { elem ->
                val l = elem.asJsonObject
                StudentLeaveRequest(
                    leaveId = l.get("leave_id").safeInt() ?: 0,
                    startDate = l.get("start_date").safeString() ?: "",
                    endDate = l.get("end_date").safeString() ?: "",
                    reason = l.get("reason").safeString() ?: "",
                    category = l.get("type").safeString() ?: "General",
                    status = l.get("status").safeString() ?: "",
                    appliedOn = l.get("date_display").safeString() ?: "",
                    reviewedBy = null,
                    reviewedOn = null,
                    remarks = null
                )
            }

            // Parse blocked dates
            val blockedArr = json.getAsJsonArray("blocked_dates") ?: JsonArray()
            val blockedDates = blockedArr.map { it.asString }

            return StudentLeavesResponse(balance, history, blockedDates)
        }
    }

    /**
     * Apply for leave.
     */
    fun applyLeave(baseUrl: String, accessToken: String, leave: LeaveApplication): Boolean {
        // Calculate total days from start and end date
        val startDate = java.time.LocalDate.parse(leave.startDate)
        val endDate = java.time.LocalDate.parse(leave.endDate)
        val totalDays = java.time.temporal.ChronoUnit.DAYS.between(startDate, endDate) + 1

        val payload = JsonObject().apply {
            addProperty("start_date", leave.startDate)
            addProperty("end_date", leave.endDate)
            addProperty("total_days", totalDays)
            addProperty("reason", leave.reason)
            addProperty("leave_type", leave.category)
            leave.documentUrl?.let { addProperty("document_url", it) }
        }

        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/v1/student/leaves")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to apply leave: ${parseError(body)}", response.code)
            }
            return true
        }
    }

    // ========================================
    // PARENT APIs
    // ========================================

    /**
     * Get parent dashboard data.
     * Returns complete dashboard for the linked student.
     */
    fun getParentDashboard(baseUrl: String, accessToken: String, userId: String): ParentDashboardData {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/parent/dashboard?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load dashboard: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)

            // Parse student info
            val studentJson = json.getAsJsonObject("student")
            val student = ParentChildInfo(
                name = studentJson.get("name").safeString() ?: "",
                roll = studentJson.get("roll").safeString() ?: "",
                className = studentJson.get("class").safeString() ?: ""
            )

            // Parse stats
            val statsJson = json.getAsJsonObject("stats")
            val stats = ParentAttendanceStats(
                percentage = statsJson.get("percentage").safeDouble() ?: 0.0,
                total = statsJson.get("total").safeInt() ?: 0,
                attended = statsJson.get("attended").safeInt() ?: 0,
                isDefaulter = (statsJson.get("percentage").safeDouble() ?: 100.0) < 75.0
            )

            // Parse subjects
            val subjects = json.getAsJsonArray("subjects")?.map { elem ->
                val s = elem.asJsonObject
                ParentSubjectAttendance(
                    subject = s.get("subject").safeString() ?: "",
                    code = s.get("code").safeString() ?: s.get("subject_code").safeString() ?: "",
                    conducted = s.get("conducted").safeInt() ?: 0,
                    attended = s.get("attended").safeInt() ?: 0,
                    percentage = s.get("percentage").safeDouble() ?: 0.0
                )
            } ?: emptyList()

            // Parse detention
            val detentionJson = json.get("detention")
            val detention = if (detentionJson != null && !detentionJson.isJsonNull && detentionJson.isJsonObject) {
                val d = detentionJson.asJsonObject
                ParentDetentionInfo(
                    reason = d.get("reason").safeString() ?: "",
                    status = d.get("status").safeString() ?: ""
                )
            } else null

            // Parse escalation
            val escalationJson = json.get("escalation")
            val escalation = if (escalationJson != null && !escalationJson.isJsonNull && escalationJson.isJsonObject) {
                val e = escalationJson.asJsonObject
                ParentEscalationInfo(
                    category = e.get("category").safeString() ?: "",
                    remarks = e.get("remarks").safeString() ?: ""
                )
            } else null

            // Parse mentor
            val mentorJson = json.get("mentor")
            val mentor = if (mentorJson != null && !mentorJson.isJsonNull && mentorJson.isJsonObject) {
                val m = mentorJson.asJsonObject
                ParentMentorInfo(
                    name = m.get("name").safeString() ?: "",
                    email = m.get("email").safeString() ?: "",
                    batchName = m.get("batch_name").safeString()
                )
            } else null

            // Parse events
            val events = json.getAsJsonArray("events")?.map { elem ->
                val e = elem.asJsonObject
                ParentEventInfo(
                    name = e.get("name").safeString() ?: "",
                    date = e.get("date").safeString() ?: "",
                    role = e.get("role").safeString() ?: "Participant",
                    status = e.get("status").safeString() ?: ""
                )
            } ?: emptyList()

            // Parse leaves
            val leaves = json.getAsJsonArray("leaves")?.map { elem ->
                val l = elem.asJsonObject
                ParentLeaveInfo(
                    type = l.get("type").safeString() ?: "General",
                    days = l.get("days").safeDouble() ?: 0.0,
                    status = l.get("status").safeString() ?: "",
                    date = l.get("date").safeString() ?: ""
                )
            } ?: emptyList()

            // Parse counseling logs
            val logs = json.getAsJsonArray("logs")?.map { elem ->
                val l = elem.asJsonObject
                ParentCounselingLog(
                    date = l.get("date").safeString() ?: "",
                    category = l.get("category").safeString() ?: "",
                    remarks = l.get("remarks").safeString() ?: "",
                    status = l.get("status").safeString() ?: "",
                    mentor = l.get("mentor").safeString() ?: ""
                )
            } ?: emptyList()

            // Parse results
            val results = json.getAsJsonArray("results")?.map { elem ->
                val r = elem.asJsonObject
                ParentCAResult(
                    subject = r.get("subject").safeString() ?: "",
                    code = r.get("code").safeString(),
                    ta1 = r.get("ta1")?.let { if (it.isJsonNull) null else it.toString().trim('"') },
                    ta2 = r.get("ta2")?.let { if (it.isJsonNull) null else it.toString().trim('"') },
                    ta3 = r.get("ta3")?.let { if (it.isJsonNull) null else it.toString().trim('"') }
                )
            } ?: emptyList()

            // Parse term grant
            val termGrantJson = json.get("term_grant")
            val termGrant = if (termGrantJson != null && !termGrantJson.isJsonNull && termGrantJson.isJsonObject) {
                val t = termGrantJson.asJsonObject
                ParentTermGrantInfo(
                    status = t.get("status").safeString() ?: "",
                    remarks = t.get("remarks").safeString()
                )
            } else null

            return ParentDashboardData(
                student = student,
                stats = stats,
                subjects = subjects,
                detention = detention,
                escalation = escalation,
                mentor = mentor,
                events = events,
                leaves = leaves,
                logs = logs,
                results = results,
                termGrant = termGrant
            )
        }
    }

    // ========================================
    // EXTRA SESSION APIs
    // ========================================

    /**
     * Get extra sessions for staff (their own sessions)
     */
    fun getExtraSessions(baseUrl: String, accessToken: String, userId: String): List<ExtraSession> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/extra_sessions?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load extra sessions: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            return json.getAsJsonArray("extra_sessions")?.map { elem ->
                val es = elem.asJsonObject
                ExtraSession(
                    id = es.get("id").safeInt() ?: 0,
                    subjectId = es.get("subject_id").safeInt() ?: 0,
                    subjectName = es.get("subject_name").safeString() ?: "",
                    sectionId = es.get("section_id").safeInt() ?: 0,
                    sectionName = es.get("section_name").safeString() ?: "",
                    date = es.get("date").safeString() ?: "",
                    dateDisplay = es.get("date").safeString()?.let {
                        try {
                            val parts = it.split("-")
                            "${parts[2]} ${getMonthShort(parts[1].toInt())}"
                        } catch (e: Exception) { it }
                    } ?: "",
                    day = "",
                    startTime = es.get("start_time").safeString() ?: "",
                    endTime = es.get("end_time").safeString() ?: "",
                    time = "${es.get("start_time").safeString() ?: ""} - ${es.get("end_time").safeString() ?: ""}",
                    topic = es.get("topic").safeString(),
                    meetingLink = es.get("meeting_link").safeString(),
                    status = es.get("status").safeString() ?: "Scheduled",
                    attendanceMarked = es.get("attendance_marked").safeBool() ?: false
                )
            } ?: emptyList()
        }
    }

    /**
     * Get allocations (sections/subjects) for creating extra sessions
     */
    fun getExtraSessionAllocations(baseUrl: String, accessToken: String, userId: String): List<ExtraSessionAllocation> {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/extra_sessions/allocations?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException("Failed to load allocations: ${parseError(body)}", response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            return json.getAsJsonArray("allocations")?.map { elem ->
                val alloc = elem.asJsonObject
                val subjects = alloc.getAsJsonArray("subjects")?.map { subj ->
                    val s = subj.asJsonObject
                    AllocationSubject(
                        subjectId = s.get("subject_id").safeInt() ?: 0,
                        subjectName = s.get("subject_name").safeString() ?: "",
                        subjectCode = s.get("subject_code").safeString() ?: ""
                    )
                } ?: emptyList()

                ExtraSessionAllocation(
                    sectionId = alloc.get("section_id").safeInt() ?: 0,
                    sectionName = alloc.get("section_name").safeString() ?: "",
                    subjects = subjects
                )
            } ?: emptyList()
        }
    }

    /**
     * Create a new extra session
     */
    fun createExtraSession(
        baseUrl: String,
        accessToken: String,
        userId: String,
        request: ExtraSessionCreateRequest
    ): Int {
        val payload = JsonObject().apply {
            addProperty("user_id", userId)
            addProperty("subject_id", request.subjectId)
            addProperty("section_id", request.sectionId)
            addProperty("date", request.date)
            addProperty("start_time", request.startTime)
            addProperty("end_time", request.endTime)
            request.topic?.let { addProperty("topic", it) }
            request.meetingLink?.let { addProperty("meeting_link", it) }
        }

        val httpRequest = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/extra_sessions")
            .header("Authorization", "Bearer $accessToken")
            .post(gson.toJson(payload).toRequestBody(jsonMediaType))
            .build()

        client.newCall(httpRequest).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException(parseError(body), response.code)
            }

            val json = gson.fromJson(body, JsonObject::class.java)
            return json.get("id").safeInt() ?: 0
        }
    }

    /**
     * Cancel an extra session
     */
    fun cancelExtraSession(baseUrl: String, accessToken: String, userId: String, sessionId: Int) {
        val request = Request.Builder()
            .url("${baseUrl.trimEnd('/')}/api/staff/extra_sessions/$sessionId?user_id=$userId")
            .header("Authorization", "Bearer $accessToken")
            .delete()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException(parseError(body), response.code)
            }
        }
    }

    private fun getMonthShort(month: Int): String {
        return when (month) {
            1 -> "Jan"; 2 -> "Feb"; 3 -> "Mar"; 4 -> "Apr"
            5 -> "May"; 6 -> "Jun"; 7 -> "Jul"; 8 -> "Aug"
            9 -> "Sep"; 10 -> "Oct"; 11 -> "Nov"; 12 -> "Dec"
            else -> ""
        }
    }

    // ========================================
    // HELPER FUNCTIONS
    // ========================================

    private fun parseError(body: String): String {
        return try {
            val json = gson.fromJson(body, JsonObject::class.java)
            json.get("error")?.asString ?: json.get("message")?.asString ?: body
        } catch (e: Exception) {
            body.ifBlank { "Unknown error" }
        }
    }
}

/**
 * Custom exception for API errors.
 */
class ApiException(message: String, val code: Int? = null) : Exception(message)

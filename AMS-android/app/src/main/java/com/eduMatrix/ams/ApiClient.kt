package com.eduMatrix.ams

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

object ApiClient {
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()
    private val client = OkHttpClient()

    data class LoginResponse(
        val accessToken: String,
        val refreshToken: String,
        val role: String,
        val userId: Int,
    )

    data class TestPushResponse(
        val pushTokens: Int,
        val pushSuccess: Int,
    )

    data class ApplyLeaveResponse(
        val status: String,
        val leaveId: Int,
    )

    data class StudentEvent(
        val eventId: Int,
        val name: String,
        val startDate: String,
        val endDate: String,
        val time: String,
        val status: String,
        val role: String,
    )

    data class AttendanceSubject(
        val name: String,
        val code: String,
        val teacher: String,
        val conducted: Int,
        val attended: Int,
        val percentage: Double,
    )

    data class AttendanceSummary(
        val studentName: String,
        val studentClass: String,
        val overallPercentage: Double,
        val totalLectures: Int,
        val attended: Int,
        val subjects: List<AttendanceSubject>,
    )

    data class TimetableEntry(
        val dayOfWeek: String,
        val startTime: String,
        val endTime: String,
        val subject: String,
        val teacher: String,
        val room: String,
        val sessionType: String,
    )

    data class LeaveBalance(
        val total: Double,
        val used: Double,
        val remaining: Double,
    )

    data class LeaveHistoryItem(
        val leaveId: Int,
        val type: String,
        val days: Double,
        val status: String,
        val startDate: String,
        val endDate: String,
        val reason: String,
    )

    data class LeavesResponse(
        val balance: LeaveBalance,
        val history: List<LeaveHistoryItem>,
    )

    data class ResultRow(
        val subject: String,
        val code: String,
        val ta1: String,
        val ta2: String,
        val ta3: String,
    )

    data class TermGrant(
        val status: String,
        val remarks: String,
        val attendancePerc: Double?,
        val caAvg: Double?,
        val isPublished: Boolean,
    )

    data class ResultsResponse(
        val results: List<ResultRow>,
        val termGrant: TermGrant?,
    )

    data class MobileNotification(
        val id: Int,
        val title: String,
        val message: String,
        val timestamp: String,
        val type: String,
        val isRead: Boolean,
    )

    fun login(baseUrl: String, username: String, password: String, deviceId: String): LoginResponse {
        val payload = JSONObject()
            .put("username", username)
            .put("password", password)
            .put("device_id", deviceId)

        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/v1/auth/login")
            .post(payload.toString().toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val message = try {
                    JSONObject(body).optString("error").ifBlank { body }
                } catch (_: Exception) {
                    body
                }
                throw IllegalStateException("Login failed (${response.code}): $message")
            }

            val json = JSONObject(body)
            val user = json.optJSONObject("user")
            return LoginResponse(
                accessToken = json.getString("access_token"),
                refreshToken = json.getString("refresh_token"),
                role = user?.optString("role") ?: "",
                userId = user?.optInt("user_id") ?: 0,
            )
        }
    }

    fun registerPush(baseUrl: String, accessToken: String, deviceId: String, fcmToken: String) {
        val payload = JSONObject()
            .put("platform", "android")
            .put("device_id", deviceId)
            .put("fcm_token", fcmToken)

        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/v1/push/register")
            .header("Authorization", "Bearer $accessToken")
            .post(payload.toString().toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val message = try {
                    JSONObject(body).optString("error").ifBlank { body }
                } catch (_: Exception) {
                    body
                }
                throw IllegalStateException("Push register failed (${response.code}): $message")
            }
        }
    }

    fun sendTestPush(baseUrl: String, accessToken: String, title: String? = null, message: String? = null): TestPushResponse {
        val payload = JSONObject()
        if (!title.isNullOrBlank()) payload.put("title", title)
        if (!message.isNullOrBlank()) payload.put("message", message)

        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/v1/push/test")
            .header("Authorization", "Bearer $accessToken")
            .post(payload.toString().toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val err = try {
                    JSONObject(body).optString("error").ifBlank { body }
                } catch (_: Exception) {
                    body
                }
                throw IllegalStateException("Test push failed (${response.code}): $err")
            }

            val json = try { JSONObject(body) } catch (_: Exception) { JSONObject() }
            return TestPushResponse(
                pushTokens = json.optInt("push_tokens", 0),
                pushSuccess = json.optInt("push_success", 0),
            )
        }
    }

    fun applyLeave(
        baseUrl: String,
        accessToken: String,
        totalDays: Double,
        startDateIso: String,
        endDateIso: String,
        reason: String? = null,
        leaveType: String? = null,
    ): ApplyLeaveResponse {
        val payload = JSONObject()
            .put("total_days", totalDays)
            .put("start_date", startDateIso)
            .put("end_date", endDateIso)

        if (!reason.isNullOrBlank()) payload.put("reason", reason)
        if (!leaveType.isNullOrBlank()) payload.put("leave_type", leaveType)

        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/v1/student/leaves")
            .header("Authorization", "Bearer $accessToken")
            .post(payload.toString().toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val err = try {
                    JSONObject(body).optString("error").ifBlank { body }
                } catch (_: Exception) {
                    body
                }
                throw IllegalStateException("Apply leave failed (${response.code}): $err")
            }

            val json = JSONObject(body)
            return ApplyLeaveResponse(
                status = json.optString("status"),
                leaveId = json.optInt("leave_id"),
            )
        }
    }

    fun getStudentEvents(baseUrl: String, accessToken: String): List<StudentEvent> {
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/v1/student/events")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val err = try {
                    JSONObject(body).optString("error").ifBlank { body }
                } catch (_: Exception) {
                    body
                }
                throw IllegalStateException("Get events failed (${response.code}): $err")
            }

            val json = JSONObject(body)
            val arr = json.optJSONArray("events")
            if (arr == null) return emptyList()

            val out = ArrayList<StudentEvent>(arr.length())
            for (i in 0 until arr.length()) {
                val item = arr.optJSONObject(i) ?: continue
                out.add(
                    StudentEvent(
                        eventId = item.optInt("event_id"),
                        name = item.optString("name"),
                        startDate = item.optString("start_date"),
                        endDate = item.optString("end_date"),
                        time = item.optString("time"),
                        status = item.optString("status"),
                        role = item.optString("role"),
                    )
                )
            }
            return out
        }
    }

    fun getAttendance(baseUrl: String, accessToken: String): AttendanceSummary {
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/v1/student/attendance/subjects")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val err = try { JSONObject(body).optString("error").ifBlank { body } } catch (_: Exception) { body }
                throw IllegalStateException("Attendance failed (${response.code}): $err")
            }

            val json = JSONObject(body)
            val profile = json.optJSONObject("profile")
            val stats = json.optJSONObject("stats")
            val subjectsArr = json.optJSONArray("subjects")

            val subjects = ArrayList<AttendanceSubject>(subjectsArr?.length() ?: 0)
            if (subjectsArr != null) {
                for (i in 0 until subjectsArr.length()) {
                    val s = subjectsArr.optJSONObject(i) ?: continue
                    subjects.add(
                        AttendanceSubject(
                            name = s.optString("subject"),
                            code = s.optString("code"),
                            teacher = s.optString("teacher"),
                            conducted = s.optInt("conducted"),
                            attended = s.optInt("attended"),
                            percentage = s.optDouble("percentage", 0.0),
                        )
                    )
                }
            }

            return AttendanceSummary(
                studentName = profile?.optString("name").orEmpty(),
                studentClass = profile?.optString("class").orEmpty(),
                overallPercentage = stats?.optDouble("percentage", 0.0) ?: 0.0,
                totalLectures = stats?.optInt("total_lectures") ?: 0,
                attended = stats?.optInt("attended") ?: 0,
                subjects = subjects,
            )
        }
    }

    fun getTimetable(baseUrl: String, accessToken: String): Pair<String, List<TimetableEntry>> {
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/v1/student/timetable")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val err = try { JSONObject(body).optString("error").ifBlank { body } } catch (_: Exception) { body }
                throw IllegalStateException("Timetable failed (${response.code}): $err")
            }

            val json = JSONObject(body)
            val className = json.optString("class")
            val entriesArr = json.optJSONArray("entries")
            val entries = ArrayList<TimetableEntry>(entriesArr?.length() ?: 0)
            if (entriesArr != null) {
                for (i in 0 until entriesArr.length()) {
                    val e = entriesArr.optJSONObject(i) ?: continue
                    val subj = e.optJSONObject("subject")
                    val teacher = e.optJSONObject("teacher")
                    val room = e.optJSONObject("room")
                    entries.add(
                        TimetableEntry(
                            dayOfWeek = e.optString("day_of_week"),
                            startTime = e.optString("start_time"),
                            endTime = e.optString("end_time"),
                            subject = subj?.optString("name").orEmpty(),
                            teacher = teacher?.optString("name") ?: "",
                            room = room?.optString("room_number") ?: "",
                            sessionType = e.optString("session_type"),
                        )
                    )
                }
            }
            return Pair(className, entries)
        }
    }

    fun getLeaves(baseUrl: String, accessToken: String): LeavesResponse {
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/v1/student/leaves")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val err = try { JSONObject(body).optString("error").ifBlank { body } } catch (_: Exception) { body }
                throw IllegalStateException("Leaves failed (${response.code}): $err")
            }
            val json = JSONObject(body)
            val bal = json.optJSONObject("balance")
            val histArr = json.optJSONArray("history")
            val hist = ArrayList<LeaveHistoryItem>(histArr?.length() ?: 0)
            if (histArr != null) {
                for (i in 0 until histArr.length()) {
                    val item = histArr.optJSONObject(i) ?: continue
                    hist.add(
                        LeaveHistoryItem(
                            leaveId = item.optInt("leave_id"),
                            type = item.optString("type"),
                            days = item.optDouble("days", 0.0),
                            status = item.optString("status"),
                            startDate = item.optString("start_date"),
                            endDate = item.optString("end_date"),
                            reason = item.optString("reason"),
                        )
                    )
                }
            }

            return LeavesResponse(
                balance = LeaveBalance(
                    total = bal?.optDouble("total", 0.0) ?: 0.0,
                    used = bal?.optDouble("used", 0.0) ?: 0.0,
                    remaining = bal?.optDouble("remaining", 0.0) ?: 0.0,
                ),
                history = hist,
            )
        }
    }

    fun getResults(baseUrl: String, accessToken: String): ResultsResponse {
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/v1/student/results")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val err = try { JSONObject(body).optString("error").ifBlank { body } } catch (_: Exception) { body }
                throw IllegalStateException("Results failed (${response.code}): $err")
            }
            val json = JSONObject(body)
            val resArr = json.optJSONArray("results")
            val results = ArrayList<ResultRow>(resArr?.length() ?: 0)
            if (resArr != null) {
                for (i in 0 until resArr.length()) {
                    val r = resArr.optJSONObject(i) ?: continue
                    results.add(
                        ResultRow(
                            subject = r.optString("subject"),
                            code = r.optString("code"),
                            ta1 = r.optString("ta1"),
                            ta2 = r.optString("ta2"),
                            ta3 = r.optString("ta3"),
                        )
                    )
                }
            }

            val tg = json.optJSONObject("term_grant")
            val termGrant = if (tg != null) {
                TermGrant(
                    status = tg.optString("status"),
                    remarks = tg.optString("remarks"),
                    attendancePerc = if (tg.isNull("att_perc")) null else tg.optDouble("att_perc"),
                    caAvg = if (tg.isNull("ca_avg")) null else tg.optDouble("ca_avg"),
                    isPublished = tg.optBoolean("is_published", false),
                )
            } else {
                null
            }

            return ResultsResponse(results = results, termGrant = termGrant)
        }
    }

    fun getNotifications(baseUrl: String, accessToken: String): List<MobileNotification> {
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + "/api/v1/notifications")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                val err = try { JSONObject(body).optString("error").ifBlank { body } } catch (_: Exception) { body }
                throw IllegalStateException("Notifications failed (${response.code}): $err")
            }

            val json = JSONObject(body)
            val arr = json.optJSONArray("notifications") ?: return emptyList()
            val out = ArrayList<MobileNotification>(arr.length())
            for (i in 0 until arr.length()) {
                val n = arr.optJSONObject(i) ?: continue
                out.add(
                    MobileNotification(
                        id = n.optInt("id"),
                        title = n.optString("title"),
                        message = n.optString("message"),
                        timestamp = n.optString("timestamp"),
                        type = n.optString("type"),
                        isRead = n.optBoolean("is_read", false),
                    )
                )
            }
            return out
        }
    }
}

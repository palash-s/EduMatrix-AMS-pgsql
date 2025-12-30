package com.eduMatrix.ams.ui.staff.attendance

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiException
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.*
import com.eduMatrix.ams.ui.components.*
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Attendance marking screen for staff.
 * Allows marking present/absent for each student in a scheduled session.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StaffMarkAttendanceScreen(
    scheduleId: Int,
    date: String,
    onBack: () -> Unit,
    onSuccess: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    // Loading states
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var isSubmitting by rememberSaveable { mutableStateOf(false) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }

    // Data states
    var attendanceSheet by remember { mutableStateOf<AttendanceSheet?>(null) }
    var studentAttendance by remember { mutableStateOf<Map<String, AttendanceStatus>>(emptyMap()) }
    var selectedTopicId by rememberSaveable { mutableStateOf<Int?>(null) }
    var showTopicDialog by rememberSaveable { mutableStateOf(false) }
    var showConfirmDialog by rememberSaveable { mutableStateOf(false) }

    // Load attendance sheet on first launch
    LaunchedEffect(scheduleId, date) {
        isLoading = true
        errorMessage = null

        try {
            val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
            val sheet = withContext(Dispatchers.IO) {
                ApiService.getAttendanceSheet(
                    baseUrl = BuildConfig.API_BASE_URL,
                    accessToken = token,
                    scheduleId = scheduleId,
                    date = date
                )
            }
            attendanceSheet = sheet
            // Initialize attendance based on backend-provided status
            // Students with approved leaves/events should be marked as ON_DUTY
            // Use StatusUtils for robust matching of status variants
            studentAttendance = sheet.students.associate { student ->
                val hasApprovedLeave = student.isOnDuty || StatusUtils.isLeaveOrDuty(student.status)
                val attendanceStatus = when {
                    hasApprovedLeave -> AttendanceStatus.ON_DUTY
                    student.status.equals("Absent", ignoreCase = true) -> AttendanceStatus.ABSENT
                    else -> AttendanceStatus.PRESENT
                }
                student.studentId to attendanceStatus
            }
        } catch (e: ApiException) {
            errorMessage = e.message ?: "Failed to load attendance sheet"
        } catch (e: Exception) {
            errorMessage = "Connection error: ${e.message}"
        } finally {
            isLoading = false
        }
    }

    // Calculate stats
    val totalStudents = attendanceSheet?.students?.size ?: 0
    val presentCount = studentAttendance.values.count { it == AttendanceStatus.PRESENT }
    val absentCount = studentAttendance.values.count { it == AttendanceStatus.ABSENT }
    val onDutyCount = studentAttendance.values.count { it == AttendanceStatus.ON_DUTY }

    // Submit attendance
    fun submitAttendance() {
        if (attendanceSheet == null) return

        scope.launch {
            isSubmitting = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val submission = AttendanceSubmission(
                    scheduleId = scheduleId,
                    conductedDate = date,
                    topicId = selectedTopicId,
                    attendance = studentAttendance.map { (studentId, status) ->
                        StudentAttendanceRecord(
                            studentId = studentId,
                            status = status,
                            remarks = null
                        )
                    }
                )

                withContext(Dispatchers.IO) {
                    ApiService.submitAttendance(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        submission = submission
                    )
                }

                snackbarHostState.showSnackbar("Attendance submitted successfully!")
                onSuccess()
            } catch (e: ApiException) {
                snackbarHostState.showSnackbar(e.message ?: "Failed to submit attendance")
            } catch (e: Exception) {
                snackbarHostState.showSnackbar("Error: ${e.message}")
            } finally {
                isSubmitting = false
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "Mark Attendance",
                            style = MaterialTheme.typography.titleLarge
                        )
                        if (attendanceSheet != null) {
                            Text(
                                text = "${attendanceSheet!!.allocation.subjectName} • $date",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = primaryAccent(),
                    titleContentColor = Color.White,
                    navigationIconContentColor = Color.White
                )
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            if (attendanceSheet != null && !isLoading) {
                Surface(
                    color = MaterialTheme.colorScheme.surface,
                    shadowElevation = 8.dp
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        // Summary row
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceEvenly
                        ) {
                            AttendanceSummaryChip(
                                label = "Present",
                                count = presentCount,
                                color = StatusGreen
                            )
                            AttendanceSummaryChip(
                                label = "Absent",
                                count = absentCount,
                                color = StatusRed
                            )
                            AttendanceSummaryChip(
                                label = "Leave/OD",
                                count = onDutyCount,
                                color = StatusBlue
                            )
                        }

                        // Submit button
                        Button(
                            onClick = { showConfirmDialog = true },
                            enabled = !isSubmitting && totalStudents > 0,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(52.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = primaryAccent()),
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            if (isSubmitting) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(24.dp),
                                    color = Color.White,
                                    strokeWidth = 2.dp
                                )
                            } else {
                                Icon(
                                    Icons.Default.Save,
                                    contentDescription = null,
                                    modifier = Modifier.size(20.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = "Submit Attendance",
                                    style = MaterialTheme.typography.labelLarge,
                                    fontWeight = FontWeight.SemiBold
                                )
                            }
                        }
                    }
                }
            }
        }
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .background(MaterialTheme.colorScheme.background)
        ) {
            when {
                isLoading -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(16.dp)
                        ) {
                            CircularProgressIndicator(color = accentPurple())
                            Text(
                                text = "Loading student list...",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }

                errorMessage != null -> {
                    EmptyState(
                        icon = Icons.Outlined.Error,
                        title = "Error Loading Data",
                        message = errorMessage ?: "Unknown error occurred",
                        modifier = Modifier.fillMaxSize()
                    ) {
                        Button(
                            onClick = {
                                // Retry loading
                                isLoading = true
                                errorMessage = null
                                scope.launch {
                                    try {
                                        val token = AppPrefs.getAccessToken(context)
                                            ?: throw Exception("Not authenticated")
                                        val sheet = withContext(Dispatchers.IO) {
                                            ApiService.getAttendanceSheet(
                                                baseUrl = BuildConfig.API_BASE_URL,
                                                accessToken = token,
                                                scheduleId = scheduleId,
                                                date = date
                                            )
                                        }
                                        attendanceSheet = sheet
                                        // Initialize attendance based on backend-provided status
                                        // Use StatusUtils for robust matching of status variants
                                        studentAttendance = sheet.students.associate { student ->
                                            val hasApprovedLeave = student.isOnDuty || StatusUtils.isLeaveOrDuty(student.status)
                                            val attendanceStatus = when {
                                                hasApprovedLeave -> AttendanceStatus.ON_DUTY
                                                student.status.equals("Absent", ignoreCase = true) -> AttendanceStatus.ABSENT
                                                else -> AttendanceStatus.PRESENT
                                            }
                                            student.studentId to attendanceStatus
                                        }
                                    } catch (e: Exception) {
                                        errorMessage = e.message
                                    } finally {
                                        isLoading = false
                                    }
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = primaryAccent())
                        ) {
                            Icon(Icons.Default.Refresh, contentDescription = null)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Retry")
                        }
                    }
                }

                attendanceSheet != null -> {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        // Session info card
                        item {
                            SessionInfoCard(
                                sheet = attendanceSheet!!,
                                selectedTopicId = selectedTopicId,
                                onSelectTopic = { showTopicDialog = true }
                            )
                        }

                        // Quick actions
                        item {
                            QuickActionsRow(
                                onMarkAllPresent = {
                                    // Preserve leave/OD status for students with approved leaves/events
                                    // Use StatusUtils for robust matching of status variants
                                    studentAttendance = attendanceSheet!!.students.associate { student ->
                                        val hasApprovedLeave = student.isOnDuty || StatusUtils.isLeaveOrDuty(student.status)
                                        val status = if (hasApprovedLeave) {
                                            AttendanceStatus.ON_DUTY
                                        } else {
                                            AttendanceStatus.PRESENT
                                        }
                                        student.studentId to status
                                    }
                                },
                                onMarkAllAbsent = {
                                    // Preserve leave/OD status for students with approved leaves/events
                                    // Use StatusUtils for robust matching of status variants
                                    studentAttendance = attendanceSheet!!.students.associate { student ->
                                        val hasApprovedLeave = student.isOnDuty || StatusUtils.isLeaveOrDuty(student.status)
                                        val status = if (hasApprovedLeave) {
                                            AttendanceStatus.ON_DUTY
                                        } else {
                                            AttendanceStatus.ABSENT
                                        }
                                        student.studentId to status
                                    }
                                }
                            )
                        }

                        // Section header
                        item {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "Students (${totalStudents})",
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.SemiBold,
                                    color = accentPurple()
                                )
                                Surface(
                                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    Text(
                                        text = "Tap card to toggle P/A",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                                    )
                                }
                            }
                        }

                        // Student list
                        itemsIndexed(
                            items = attendanceSheet!!.students,
                            key = { _, student -> student.studentId }
                        ) { index, student ->
                            StudentAttendanceCard(
                                student = student,
                                index = index + 1,
                                status = studentAttendance[student.studentId]
                                    ?: AttendanceStatus.PRESENT,
                                onStatusChange = { newStatus ->
                                    studentAttendance = studentAttendance.toMutableMap().apply {
                                        put(student.studentId, newStatus)
                                    }
                                }
                            )
                        }

                        // Bottom spacer for FAB
                        item {
                            Spacer(modifier = Modifier.height(80.dp))
                        }
                    }
                }
            }
        }
    }

    // Topic selection dialog
    if (showTopicDialog && attendanceSheet != null) {
        TopicSelectionDialog(
            topics = attendanceSheet!!.topics,
            selectedTopicId = selectedTopicId,
            onTopicSelected = { topicId ->
                selectedTopicId = topicId
                showTopicDialog = false
            },
            onDismiss = { showTopicDialog = false }
        )
    }

    // Confirmation dialog
    if (showConfirmDialog) {
        AlertDialog(
            onDismissRequest = { showConfirmDialog = false },
            icon = {
                Icon(
                    Icons.Default.HowToReg,
                    contentDescription = null,
                    tint = accentPurple()
                )
            },
            title = {
                Text("Confirm Submission")
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("You are about to submit attendance for:")
                    Text(
                        text = "${attendanceSheet?.allocation?.subjectName}",
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceEvenly
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "$presentCount",
                                style = MaterialTheme.typography.titleLarge,
                                color = StatusGreen,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Present",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "$absentCount",
                                style = MaterialTheme.typography.titleLarge,
                                color = StatusRed,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Absent",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "$onDutyCount",
                                style = MaterialTheme.typography.titleLarge,
                                color = StatusBlue,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Leave/OD",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        showConfirmDialog = false
                        submitAttendance()
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = primaryAccent())
                ) {
                    Text("Submit")
                }
            },
            dismissButton = {
                TextButton(onClick = { showConfirmDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }

    // Loading overlay
    LoadingOverlay(
        isLoading = isSubmitting,
        message = "Submitting attendance..."
    )
}

/**
 * Session info card with subject and topic selection.
 */
@Composable
private fun SessionInfoCard(
    sheet: AttendanceSheet,
    selectedTopicId: Int?,
    onSelectTopic: () -> Unit
) {
    val selectedTopic = sheet.topics.find { it.planId == selectedTopicId }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Subject info
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = sheet.allocation.subjectName,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        text = "${sheet.allocation.subjectCode} • ${sheet.allocation.sectionName}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                val sessionTypeColor = when (sheet.allocation.sessionType.lowercase()) {
                    "practical", "lab" -> MitOrange
                    "tutorial" -> secondaryAccent()
                    else -> primaryAccent()
                }
                val isDark = isSystemInDarkTheme()
                Surface(
                    color = sessionTypeColor.copy(alpha = if (isDark) 0.2f else 0.1f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = sheet.allocation.sessionType,
                        style = MaterialTheme.typography.labelSmall,
                        color = sessionTypeColor,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

            // Schedule info
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Outlined.Schedule,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "${sheet.scheduleInfo.startTime} - ${sheet.scheduleInfo.endTime}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Outlined.Room,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = sheet.scheduleInfo.roomNumber,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Topic selection
            if (sheet.topics.isNotEmpty()) {
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onSelectTopic() }
                        .padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Topic Covered",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = selectedTopic?.let {
                                "${it.unitNumber}.${it.subUnitNumber ?: 0} ${it.subUnitTitle ?: it.unitTitle}"
                            } ?: "Select topic (optional)",
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (selectedTopic != null)
                                MaterialTheme.colorScheme.onSurface
                            else
                                MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    Icon(
                        Icons.Default.ChevronRight,
                        contentDescription = "Select topic",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

/**
 * Quick actions for marking all present/absent.
 */
@Composable
private fun QuickActionsRow(
    onMarkAllPresent: () -> Unit,
    onMarkAllAbsent: () -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        OutlinedButton(
            onClick = onMarkAllPresent,
            modifier = Modifier.weight(1f),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = StatusGreen),
            shape = RoundedCornerShape(8.dp)
        ) {
            Icon(
                Icons.Default.CheckCircle,
                contentDescription = null,
                modifier = Modifier.size(18.dp)
            )
            Spacer(modifier = Modifier.width(4.dp))
            Text("All Present")
        }
        OutlinedButton(
            onClick = onMarkAllAbsent,
            modifier = Modifier.weight(1f),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = StatusRed),
            shape = RoundedCornerShape(8.dp)
        ) {
            Icon(
                Icons.Default.Cancel,
                contentDescription = null,
                modifier = Modifier.size(18.dp)
            )
            Spacer(modifier = Modifier.width(4.dp))
            Text("All Absent")
        }
    }
}

/**
 * Individual student attendance card with modern design.
 * Students with approved leaves (OD/ML/CL) are locked and show their status.
 * Regular students can be marked Present or Absent only.
 */
@Composable
private fun StudentAttendanceCard(
    student: StudentForAttendance,
    index: Int,
    status: AttendanceStatus,
    onStatusChange: (AttendanceStatus) -> Unit
) {
    // Check if student has approved leave/duty (locked status)
    // Use StatusUtils for robust matching of status variants (handles case/spacing)
    val normalizedStatus = StatusUtils.normalizeLeaveStatus(student.status)
    val isLocked = student.isOnDuty || normalizedStatus != null

    // Get appropriate colors, code, and label based on leave type
    // Use theme-aware teal for CL
    val tealColor = secondaryAccent()
    data class LeaveInfo(val color: Color, val code: String, val label: String)
    val leaveInfo = when (normalizedStatus) {
        "ML" -> LeaveInfo(MitOrange, "ML", student.statusLabel ?: "Medical Leave")
        "CL" -> LeaveInfo(tealColor, "CL", student.statusLabel ?: "Casual Leave")
        "OD" -> LeaveInfo(StatusBlue, "OD", student.statusLabel ?: "Event OD")
        else -> if (student.isOnDuty) {
            LeaveInfo(StatusBlue, "OD", student.statusLabel ?: "On Duty")
        } else {
            LeaveInfo(StatusBlue, "", "")
        }
    }
    val leaveColor = leaveInfo.color
    val leaveCode = leaveInfo.code
    val leaveLabel = leaveInfo.label

    val cardBackground = if (isLocked) {
        leaveColor.copy(alpha = 0.06f)
    } else {
        MaterialTheme.colorScheme.surface
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .then(
                if (!isLocked) {
                    Modifier.clickable {
                        // Toggle between Present and Absent only
                        val nextStatus = when (status) {
                            AttendanceStatus.PRESENT -> AttendanceStatus.ABSENT
                            AttendanceStatus.ABSENT -> AttendanceStatus.PRESENT
                            AttendanceStatus.ON_DUTY -> AttendanceStatus.PRESENT
                        }
                        onStatusChange(nextStatus)
                    }
                } else Modifier
            ),
        colors = CardDefaults.cardColors(containerColor = cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = if (isLocked) 0.dp else 1.dp),
        shape = RoundedCornerShape(16.dp),
        border = if (isLocked) {
            androidx.compose.foundation.BorderStroke(1.dp, leaveColor.copy(alpha = 0.3f))
        } else null
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Serial number with status indicator
            val isDark = isSystemInDarkTheme()
            val indexBgAlpha = if (isDark) 0.2f else 0.1f
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(CircleShape)
                    .background(
                        if (isLocked) leaveColor.copy(alpha = indexBgAlpha)
                        else primaryAccent().copy(alpha = indexBgAlpha)
                    ),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = "$index",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                    color = if (isLocked) leaveColor else primaryAccent()
                )
            }

            // Student info - use theme-aware text colors
            // For locked cards, use the leave color for better contrast in both themes
            val nameColor = if (isLocked) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurface
            val rollColor = if (isLocked) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurfaceVariant

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = student.name,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.SemiBold,
                    color = nameColor,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    text = student.rollNumber,
                    style = MaterialTheme.typography.bodySmall,
                    color = rollColor
                )
            }

            // Status indicator - Locked badge OR P/A chips
            if (isLocked) {
                // Show locked status badge with leave type code and icon
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Leave type code badge (ML, CL, OD)
                    Surface(
                        color = leaveColor,
                        shape = RoundedCornerShape(6.dp)
                    ) {
                        Text(
                            text = leaveCode,
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = Color.White,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                    // Lock icon
                    Icon(
                        imageVector = Icons.Default.Lock,
                        contentDescription = "Locked",
                        modifier = Modifier.size(16.dp),
                        tint = leaveColor
                    )
                }
            } else {
                // Show P/A chips for regular students
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    StatusChip(
                        text = "P",
                        isSelected = status == AttendanceStatus.PRESENT,
                        selectedColor = StatusGreen,
                        onClick = { onStatusChange(AttendanceStatus.PRESENT) }
                    )
                    StatusChip(
                        text = "A",
                        isSelected = status == AttendanceStatus.ABSENT,
                        selectedColor = StatusRed,
                        onClick = { onStatusChange(AttendanceStatus.ABSENT) }
                    )
                }
            }
        }
    }
}

/**
 * Modern status chip for attendance selection.
 */
@Composable
private fun StatusChip(
    text: String,
    isSelected: Boolean,
    selectedColor: Color,
    onClick: () -> Unit
) {
    Surface(
        modifier = Modifier
            .size(40.dp)
            .clip(RoundedCornerShape(12.dp))
            .clickable { onClick() },
        color = if (isSelected) selectedColor else Color.Transparent,
        shape = RoundedCornerShape(12.dp),
        border = if (!isSelected) {
            androidx.compose.foundation.BorderStroke(
                width = 1.5.dp,
                color = MaterialTheme.colorScheme.outlineVariant
            )
        } else null,
        shadowElevation = if (isSelected) 2.dp else 0.dp
    ) {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = text,
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                color = if (isSelected) Color.White else MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

/**
 * Attendance summary chip for bottom bar.
 */
@Composable
private fun AttendanceSummaryChip(
    label: String,
    count: Int,
    color: Color
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(color)
        )
        Text(
            text = "$label: $count",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}

/**
 * Topic selection dialog.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TopicSelectionDialog(
    topics: List<TopicForSelection>,
    selectedTopicId: Int?,
    onTopicSelected: (Int?) -> Unit,
    onDismiss: () -> Unit
) {
    // Theme-aware alpha for selected backgrounds
    val isDark = isSystemInDarkTheme()
    val selectedBgAlpha = if (isDark) 0.2f else 0.1f
    val accentColor = primaryAccent()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text("Select Topic Covered")
        },
        text = {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                item {
                    // No topic option
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .clickable { onTopicSelected(null) }
                            .background(
                                if (selectedTopicId == null)
                                    accentColor.copy(alpha = selectedBgAlpha)
                                else
                                    Color.Transparent
                            )
                            .padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        RadioButton(
                            selected = selectedTopicId == null,
                            onClick = { onTopicSelected(null) },
                            colors = RadioButtonDefaults.colors(
                                selectedColor = accentColor
                            )
                        )
                        Text(
                            text = "No topic (general session)",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                items(topics.size) { index ->
                    val topic = topics[index]
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .clickable { onTopicSelected(topic.planId) }
                            .background(
                                if (selectedTopicId == topic.planId)
                                    accentColor.copy(alpha = selectedBgAlpha)
                                else
                                    Color.Transparent
                            )
                            .padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        RadioButton(
                            selected = selectedTopicId == topic.planId,
                            onClick = { onTopicSelected(topic.planId) },
                            colors = RadioButtonDefaults.colors(
                                selectedColor = accentColor
                            )
                        )
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "${topic.unitNumber}.${topic.subUnitNumber ?: 0} ${topic.subUnitTitle ?: topic.unitTitle}",
                                style = MaterialTheme.typography.bodyMedium,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis
                            )
                            Text(
                                text = "Unit ${topic.unitNumber}: ${topic.unitTitle}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        if (topic.isCompleted) {
                            Icon(
                                Icons.Default.CheckCircle,
                                contentDescription = "Completed",
                                tint = StatusGreen,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

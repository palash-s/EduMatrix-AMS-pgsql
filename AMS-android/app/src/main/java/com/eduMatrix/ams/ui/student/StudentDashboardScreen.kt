package com.eduMatrix.ams.ui.student

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.*
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*

/**
 * Student Dashboard Screen - High-density MD3 design.
 * Uses Bento grid layout with outlined cards and compact spacing.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StudentDashboardScreen(
    onNavigateToLeaves: () -> Unit,
    onNavigateToTimetable: () -> Unit,
    onNavigateToResults: () -> Unit,
    onNavigateToFeedback: () -> Unit,
    onNavigateToNotifications: () -> Unit,
    onLogout: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // Theme state
    val themeMode by ThemeState.themeMode
    val isSystemDark = isSystemInDarkTheme()

    // State
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var dashboardData by remember { mutableStateOf<StudentDashboardData?>(null) }
    var currentTerm by remember { mutableStateOf<CurrentTerm?>(null) }
    var pendingFeedback by remember { mutableStateOf<FeedbackPendingList?>(null) }
    var refreshTrigger by rememberSaveable { mutableStateOf(0) }
    var unreadNotificationCount by rememberSaveable { mutableStateOf(0) }

    // Dialogs
    var showLogoutDialog by rememberSaveable { mutableStateOf(false) }
    var showResultsDialog by rememberSaveable { mutableStateOf(false) }
    var showDetentionDialog by rememberSaveable { mutableStateOf(false) }

    // Get current date in ISO format for filtering
    val today = remember {
        SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
    }

    // Load data
    LaunchedEffect(refreshTrigger) {
        isLoading = true
        errorMessage = null
        try {
            val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
            val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

            withContext(Dispatchers.IO) {
                dashboardData = ApiService.getStudentDashboard(BuildConfig.API_BASE_URL, token, user.userId)
                currentTerm = try {
                    ApiService.getCurrentTerm(BuildConfig.API_BASE_URL, token)
                } catch (e: Exception) { null }
                pendingFeedback = try {
                    ApiService.getPendingFeedback(BuildConfig.API_BASE_URL, token, user.userId)
                } catch (e: Exception) { null }
            }

            // Fetch unread notification count
            try {
                val notifications = withContext(Dispatchers.IO) {
                    ApiService.getNotifications(BuildConfig.API_BASE_URL, token)
                }
                unreadNotificationCount = notifications.count { !it.isRead }
            } catch (_: Exception) {
                // Best-effort, don't fail dashboard if notifications fail
            }
        } catch (e: Exception) {
            errorMessage = e.message ?: "Failed to load dashboard"
        } finally {
            isLoading = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "Dashboard",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold
                        )
                        currentTerm?.let {
                            Text(
                                text = it.name,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                },
                actions = {
                    IconButton(onClick = { refreshTrigger++ }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                    IconButton(onClick = { ThemeState.toggle(context, isSystemDark) }) {
                        Icon(
                            imageVector = when (themeMode) {
                                ThemeMode.DARK -> Icons.Outlined.DarkMode
                                ThemeMode.LIGHT -> Icons.Outlined.LightMode
                                ThemeMode.SYSTEM -> if (isSystemDark) Icons.Outlined.DarkMode else Icons.Outlined.LightMode
                            },
                            contentDescription = "Toggle theme"
                        )
                    }
                    IconButton(onClick = onNavigateToNotifications) {
                        BadgedBox(
                            badge = {
                                if (unreadNotificationCount > 0) {
                                    Badge { Text(unreadNotificationCount.toString()) }
                                }
                            }
                        ) {
                            Icon(
                                imageVector = Icons.Outlined.Notifications,
                                contentDescription = "Notifications"
                            )
                        }
                    }
                    IconButton(onClick = { showLogoutDialog = true }) {
                        Icon(Icons.Default.Logout, contentDescription = "Logout")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        }
    ) { padding ->
        when {
            isLoading -> LoadingState(modifier = Modifier.padding(padding))
            errorMessage != null -> ErrorState(
                message = errorMessage!!,
                onRetry = { refreshTrigger++ },
                modifier = Modifier.padding(padding)
            )
            dashboardData != null -> {
                val data = dashboardData!!

                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                        .background(MaterialTheme.colorScheme.background),
                    contentPadding = PaddingValues(AmsDesign.GridSpacing),
                    verticalArrangement = Arrangement.spacedBy(AmsDesign.GridSpacing)
                ) {
                    // Profile & Attendance Overview
                    item {
                        ProfileAttendanceCard(
                            profile = data.profile,
                            stats = data.stats
                        )
                    }

                    // Alert Section - Detention
                    data.detention?.let { detention ->
                        item {
                            AmsAlertBanner(
                                icon = Icons.Default.Warning,
                                title = if (detention.status == "Assigned") "Detention - Action Required" else "Detention - Under Review",
                                message = detention.reason,
                                color = if (detention.status == "Assigned") StatusRed else StatusYellow,
                                onClick = { showDetentionDialog = true }
                            )
                        }
                    }

                    // Alert Section - Term Grant
                    data.termGrant?.let { grant ->
                        item {
                            val (color, icon) = when (grant.status) {
                                "Granted" -> StatusGreen to Icons.Default.CheckCircle
                                "Provisional" -> StatusYellow to Icons.Default.Warning
                                else -> StatusRed to Icons.Default.Cancel
                            }
                            AmsAlertBanner(
                                icon = icon,
                                title = "Term Grant: ${grant.status}",
                                message = grant.remarks,
                                color = color
                            )
                        }
                    }

                    // Alert Section - Feedback
                    pendingFeedback?.let { feedback ->
                        if (feedback.subjects.isNotEmpty()) {
                            item {
                                AmsAlertBanner(
                                    icon = Icons.Default.RateReview,
                                    title = "Feedback Required",
                                    message = "${feedback.subjects.size} subject${if (feedback.subjects.size > 1) "s" else ""} pending",
                                    color = primaryAccent(),
                                    onClick = onNavigateToFeedback
                                )
                            }
                        }
                    }

                    // Quick Actions - Bento Grid
                    item {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(AmsDesign.GridSpacing)
                        ) {
                            QuickActionCard(
                                icon = Icons.Outlined.EventBusy,
                                label = "Leaves",
                                onClick = onNavigateToLeaves,
                                modifier = Modifier.weight(1f)
                            )
                            QuickActionCard(
                                icon = Icons.Outlined.CalendarMonth,
                                label = "Timetable",
                                onClick = onNavigateToTimetable,
                                modifier = Modifier.weight(1f)
                            )
                            QuickActionCard(
                                icon = Icons.Outlined.Assessment,
                                label = "Results",
                                onClick = { showResultsDialog = true },
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }

                    // Subject Performance Section
                    if (data.subjectWise.isNotEmpty()) {
                        item {
                            AmsSectionHeader(title = "Subject Attendance")
                        }

                        items(data.subjectWise) { subject ->
                            SubjectPerformanceCard(subject = subject)
                        }
                    }

                    // Mentor Section
                    if (data.mentor != null || data.meeting != null) {
                        item {
                            AmsSectionHeader(title = "My Mentor")
                        }

                        item {
                            MentorInfoCard(
                                mentor = data.mentor,
                                meeting = data.meeting
                            )
                        }
                    }

                    // Extra Sessions Section (Upcoming Extra Classes)
                    // Filter to only show today and future sessions
                    val upcomingExtraSessions = data.extraSessions.filter { it.dateIso >= today }
                    if (upcomingExtraSessions.isNotEmpty()) {
                        item {
                            AmsSectionHeader(title = "Upcoming Extra Classes")
                        }

                        items(upcomingExtraSessions) { session ->
                            ExtraSessionCard(session = session)
                        }
                    }

                    // Recent Activity Section
                    if (data.recentActivity.isNotEmpty()) {
                        item {
                            AmsSectionHeader(title = "Recent Activity")
                        }

                        item {
                            RecentActivityList(activities = data.recentActivity.take(5))
                        }
                    }

                    // Event History Section
                    if (data.events.isNotEmpty()) {
                        item {
                            AmsSectionHeader(title = "Events")
                        }

                        items(data.events.take(5)) { event ->
                            EventCard(event = event)
                        }
                    }

                    // Bottom spacing
                    item { Spacer(modifier = Modifier.height(16.dp)) }
                }

                // Results Dialog
                if (showResultsDialog && data.results.isNotEmpty()) {
                    ResultsDialog(
                        results = data.results,
                        onDismiss = { showResultsDialog = false }
                    )
                }

                // Detention Dialog
                if (showDetentionDialog && data.detention != null) {
                    DetentionTaskDialog(
                        detention = data.detention,
                        onDismiss = { showDetentionDialog = false },
                        onSubmit = { url ->
                            scope.launch {
                                try {
                                    val token = AppPrefs.getAccessToken(context) ?: return@launch
                                    withContext(Dispatchers.IO) {
                                        ApiService.submitDetentionTask(
                                            BuildConfig.API_BASE_URL, token, data.detention.id, url
                                        )
                                    }
                                    showDetentionDialog = false
                                    refreshTrigger++
                                } catch (e: Exception) { /* Handle error */ }
                            }
                        }
                    )
                }
            }
        }
    }

    // Logout Dialog
    if (showLogoutDialog) {
        AlertDialog(
            onDismissRequest = { showLogoutDialog = false },
            title = { Text("Logout", fontWeight = FontWeight.SemiBold) },
            text = { Text("Are you sure you want to logout?") },
            confirmButton = {
                TextButton(onClick = {
                    showLogoutDialog = false
                    AppPrefs.clearSession(context)
                    onLogout()
                }) {
                    Text("Logout", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showLogoutDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }
}

// ============================================
// LOADING & ERROR STATES
// ============================================

@Composable
private fun LoadingState(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            CircularProgressIndicator(color = primaryAccent(), strokeWidth = 3.dp)
            Spacer(modifier = Modifier.height(12.dp))
            Text(
                "Loading...",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun ErrorState(
    message: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        AmsEmptyState(
            icon = Icons.Outlined.ErrorOutline,
            message = message,
            action = {
                AmsPrimaryButton(text = "Retry", onClick = onRetry, icon = Icons.Default.Refresh)
            }
        )
    }
}

// ============================================
// PROFILE & ATTENDANCE CARD
// ============================================

@Composable
private fun ProfileAttendanceCard(
    profile: StudentProfileInfo,
    stats: AttendanceStats
) {
    val progressColor = if (stats.percentage >= 75) StatusGreen else StatusRed
    val animatedProgress by animateFloatAsState(
        targetValue = (stats.percentage.toFloat() / 100f).coerceIn(0f, 1f),
        animationSpec = tween(durationMillis = 800, easing = FastOutSlowInEasing),
        label = "progress"
    )

    AmsCard(modifier = Modifier.fillMaxWidth()) {
        // Profile Header
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = profile.name,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AmsStatusChip(text = profile.className, color = primaryAccent())
                    AmsStatusChip(text = "Roll: ${profile.roll}", color = secondaryAccent())
                }
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        // Attendance Stats Row
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Circular Progress
            Box(
                modifier = Modifier.size(120.dp),
                contentAlignment = Alignment.Center
            ) {
                Canvas(modifier = Modifier.size(120.dp)) {
                    val strokeWidth = 12.dp.toPx()
                    val radius = (size.minDimension - strokeWidth) / 2

                    drawCircle(
                        color = Color.Gray.copy(alpha = 0.15f),
                        radius = radius,
                        style = Stroke(width = strokeWidth)
                    )

                    drawArc(
                        color = progressColor,
                        startAngle = -90f,
                        sweepAngle = animatedProgress * 360f,
                        useCenter = false,
                        style = Stroke(width = strokeWidth, cap = StrokeCap.Round),
                        topLeft = Offset(strokeWidth / 2, strokeWidth / 2),
                        size = Size(size.width - strokeWidth, size.height - strokeWidth)
                    )
                }

                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "${stats.percentage.toInt()}%",
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                        color = progressColor
                    )
                    Text(
                        text = "Attendance",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Stats Column
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                StatRow(label = "Attended", value = "${stats.attended}", color = StatusGreen)
                StatRow(label = "Total", value = "${stats.totalLectures}", color = primaryAccent())
                StatRow(
                    label = "Status",
                    value = if (stats.isDefaulter) "At Risk" else "Good",
                    color = if (stats.isDefaulter) StatusRed else StatusGreen
                )
            }
        }
    }
}

@Composable
private fun StatRow(label: String, value: String, color: Color) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        AmsStatusDot(color = color)
        Column {
            Text(
                text = value,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = color
            )
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

// ============================================
// QUICK ACTION CARDS
// ============================================

@Composable
private fun QuickActionCard(
    icon: ImageVector,
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    AmsCompactCard(
        modifier = modifier,
        onClick = onClick
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = primaryAccent(),
                modifier = Modifier.size(24.dp)
            )
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = label,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Medium,
                textAlign = TextAlign.Center
            )
        }
    }
}

// ============================================
// SUBJECT PERFORMANCE CARD
// ============================================

@Composable
private fun SubjectPerformanceCard(subject: SubjectPerformance) {
    val progressColor = if (subject.percentage >= 75) StatusGreen else StatusRed

    AmsCompactCard(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = subject.subject,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    text = "${subject.code} • ${subject.teacher}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            Text(
                text = "${subject.percentage.toInt()}%",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = progressColor
            )
        }

        Spacer(modifier = Modifier.height(8.dp))

        AmsProgress(
            progress = subject.percentage.toFloat() / 100f,
            color = progressColor,
            showLabel = false
        )

        Spacer(modifier = Modifier.height(4.dp))

        Text(
            text = "${subject.attended}/${subject.conducted} lectures",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

// ============================================
// MENTOR INFO CARD
// ============================================

@Composable
private fun MentorInfoCard(
    mentor: MentorInfo?,
    meeting: UpcomingMeetingInfo?
) {
    AmsBentoCard(
        modifier = Modifier.fillMaxWidth(),
        accentColor = MitOrange
    ) {
        mentor?.let {
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                AmsAvatar(
                    text = it.name,
                    backgroundColor = MitOrange.copy(alpha = 0.15f),
                    textColor = MitOrange,
                    size = 44.dp
                )
                Column {
                    Text(
                        text = it.name,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold
                    )
                    Text(
                        text = it.email,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "Batch: ${it.batchName}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        meeting?.let {
            if (mentor != null) {
                HorizontalDivider(modifier = Modifier.padding(vertical = 10.dp))
            }
            Row(
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.Event,
                    contentDescription = null,
                    tint = primaryAccent(),
                    modifier = Modifier.size(20.dp)
                )
                Column {
                    Text(
                        text = "Next: ${it.date} at ${it.time}",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Medium
                    )
                    it.agenda?.let { agenda ->
                        Text(
                            text = agenda,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
            }
        }
    }
}

// ============================================
// RECENT ACTIVITY LIST
// ============================================

@Composable
private fun RecentActivityList(activities: List<RecentActivity>) {
    AmsCard(modifier = Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            activities.forEach { activity ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    AmsStatusDot(
                        color = if (StatusUtils.isPresentLike(activity.status)) StatusGreen else StatusRed
                    )
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = activity.subject,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            text = "${activity.date} • ${activity.time}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    AmsStatusChip(
                        text = activity.status,
                        color = if (StatusUtils.isPresentLike(activity.status)) StatusGreen else StatusRed
                    )
                }
            }
        }
    }
}

// ============================================
// EVENT CARD
// ============================================

@Composable
private fun EventCard(event: StudentEvent) {
    AmsCompactCard(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Outlined.Event,
                contentDescription = null,
                tint = primaryAccent(),
                modifier = Modifier.size(20.dp)
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = event.name,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    text = "${event.date} • ${event.role}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            AmsStatusChip(
                text = event.status,
                color = if (event.status == "Attended") StatusGreen else MaterialTheme.colorScheme.outline
            )
        }
    }
}

// ============================================
// RESULTS DIALOG
// ============================================

@Composable
private fun ResultsDialog(
    results: List<CAResult>,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                "Internal Assessment",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
        },
        text = {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(results) { result ->
                    AmsCompactCard {
                        Text(
                            text = result.subject,
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold
                        )
                        Text(
                            text = result.code,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceEvenly
                        ) {
                            ResultScore("TA1", result.ta1 ?: "-")
                            ResultScore("TA2", result.ta2 ?: "-")
                            ResultScore("TA3", result.ta3 ?: "-")
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("Close") }
        }
    )
}

@Composable
private fun ResultScore(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.Bold,
            color = if (value == "-") MaterialTheme.colorScheme.onSurfaceVariant else primaryAccent()
        )
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

// ============================================
// DETENTION TASK DIALOG
// ============================================

@Composable
private fun DetentionTaskDialog(
    detention: DetentionInfo,
    onDismiss: () -> Unit,
    onSubmit: (String) -> Unit
) {
    var submissionUrl by rememberSaveable { mutableStateOf(detention.submissionUrl ?: "") }
    var isSubmitting by rememberSaveable { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                "Detention Task",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(
                    text = "Reason: ${detention.reason}",
                    style = MaterialTheme.typography.bodyMedium
                )
                detention.task?.let {
                    Text(
                        text = "Task: $it",
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium
                    )
                }
                OutlinedTextField(
                    value = submissionUrl,
                    onValueChange = { submissionUrl = it },
                    label = { Text("Submission URL") },
                    placeholder = { Text("https://drive.google.com/...") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = detention.status == "Assigned" && !isSubmitting
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    isSubmitting = true
                    onSubmit(submissionUrl)
                },
                enabled = submissionUrl.isNotBlank() && detention.status == "Assigned" && !isSubmitting,
                colors = ButtonDefaults.buttonColors(containerColor = primaryAccent())
            ) {
                if (isSubmitting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        strokeWidth = 2.dp,
                        color = Color.White
                    )
                } else {
                    Text("Submit")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}

/**
 * Card displaying an upcoming extra class session for students.
 */
@Composable
private fun ExtraSessionCard(session: StudentExtraSession) {
    val isToday = session.isToday

    OutlinedCard(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 4.dp),
        colors = CardDefaults.outlinedCardColors(
            containerColor = if (isToday) {
                MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
            } else {
                MaterialTheme.colorScheme.surface
            }
        ),
        border = CardDefaults.outlinedCardBorder().copy(
            width = if (isToday) 2.dp else 1.dp,
            brush = androidx.compose.ui.graphics.SolidColor(
                if (isToday) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline.copy(alpha = 0.5f)
            )
        )
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Header row with subject and today badge
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = session.subject,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
                if (isToday) {
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = MaterialTheme.colorScheme.primary
                    ) {
                        Text(
                            text = "TODAY",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onPrimary,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                        )
                    }
                }
            }

            // Teacher name
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Outlined.Person,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = session.teacher,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Date and time row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Outlined.CalendarToday,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "${session.day}, ${session.date}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Outlined.Schedule,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = session.time,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Topic (if available)
            session.topic?.let { topic ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Outlined.Topic,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp),
                        tint = MaterialTheme.colorScheme.secondary
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = topic,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.secondary,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }

            // Meeting link (if available)
            session.meetingLink?.let { link ->
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = MaterialTheme.colorScheme.tertiaryContainer.copy(alpha = 0.5f),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.VideoCall,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp),
                            tint = MaterialTheme.colorScheme.tertiary
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Meeting link available",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.tertiary,
                            fontWeight = FontWeight.Medium
                        )
                    }
                }
            }
        }
    }
}

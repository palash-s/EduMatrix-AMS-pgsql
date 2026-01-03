package com.eduMatrix.ams.ui.parent

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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.*
import com.eduMatrix.ams.ui.components.*
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.*

/**
 * Parent Dashboard screen matching the web application Bento grid design.
 * Shows child's attendance, academic status, mentor info, and activity.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ParentDashboardScreen(
    onLogout: () -> Unit,
    onNavigateToAttendance: () -> Unit = {},
    onNavigateToNotifications: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var showLogoutDialog by rememberSaveable { mutableStateOf(false) }
    var showAttendanceModal by rememberSaveable { mutableStateOf(false) }
    var showCounselingLogModal by rememberSaveable { mutableStateOf(false) }

    // Theme state
    val themeMode by ThemeState.themeMode
    val isSystemDark = isSystemInDarkTheme()

    // State
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var dashboardData by remember { mutableStateOf<ParentDashboardData?>(null) }
    var refreshTrigger by rememberSaveable { mutableStateOf(0) }
    var unreadNotificationCount by rememberSaveable { mutableStateOf(0) }

    // Get greeting based on time
    val greeting = remember {
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        when {
            hour < 12 -> "Good Morning"
            hour < 17 -> "Good Afternoon"
            else -> "Good Evening"
        }
    }

    // Load dashboard data
    LaunchedEffect(refreshTrigger) {
        isLoading = true
        errorMessage = null

        try {
            val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
            val currentUser = AppPrefs.getUser(context) ?: throw Exception("User not found")
            val data = withContext(Dispatchers.IO) {
                ApiService.getParentDashboard(BuildConfig.API_BASE_URL, token, currentUser.userId)
            }
            dashboardData = data

            // Fetch unread notification count
            try {
                val notifications = withContext(Dispatchers.IO) {
                    ApiService.getNotifications(BuildConfig.API_BASE_URL, token)
                }
                unreadNotificationCount = notifications.count { !it.isRead }
            } catch (_: Exception) {
                // Best-effort, don't fail dashboard if notifications fail
            }

            isLoading = false
        } catch (e: com.eduMatrix.ams.data.api.ApiException) {
            isLoading = false
            if (e.code == 401) {
                AppPrefs.clearAll(context)
                onLogout()
            } else {
                errorMessage = e.message ?: "Failed to load dashboard"
            }
        } catch (e: Exception) {
            isLoading = false
            errorMessage = e.message ?: "Failed to load dashboard"
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "Parent Portal",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { refreshTrigger++ }) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh"
                        )
                    }
                    IconButton(
                        onClick = { ThemeState.toggle(context, isSystemDark) }
                    ) {
                        Icon(
                            imageVector = when (themeMode) {
                                ThemeMode.DARK -> Icons.Outlined.DarkMode
                                ThemeMode.LIGHT -> Icons.Outlined.LightMode
                                ThemeMode.SYSTEM -> if (isSystemDark) Icons.Outlined.DarkMode else Icons.Outlined.LightMode
                            },
                            contentDescription = "Toggle dark mode"
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
                        Icon(
                            imageVector = Icons.Default.ExitToApp,
                            contentDescription = "Logout"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
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
                        CircularProgressIndicator(color = accentPurple())
                    }
                }

                errorMessage != null -> {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.ErrorOutline,
                            contentDescription = null,
                            tint = StatusRed,
                            modifier = Modifier.size(64.dp)
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(
                            text = errorMessage ?: "Unknown error",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Button(
                            onClick = { refreshTrigger++ },
                            colors = ButtonDefaults.buttonColors(containerColor = accentPurple())
                        ) {
                            Text("Retry")
                        }
                    }
                }

                dashboardData != null -> {
                    ParentDashboardContent(
                        data = dashboardData!!,
                        greeting = greeting,
                        onAttendanceClick = { showAttendanceModal = true },
                        onMentorLogClick = { showCounselingLogModal = true }
                    )
                }
            }
        }
    }

    // Logout confirmation dialog
    if (showLogoutDialog) {
        AlertDialog(
            onDismissRequest = { showLogoutDialog = false },
            title = { Text("Logout") },
            text = { Text("Are you sure you want to logout?") },
            confirmButton = {
                TextButton(
                    onClick = {
                        showLogoutDialog = false
                        AppPrefs.clearSession(context)
                        onLogout()
                    }
                ) {
                    Text("Logout", color = StatusRed)
                }
            },
            dismissButton = {
                TextButton(onClick = { showLogoutDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }

    // Attendance modal
    if (showAttendanceModal && dashboardData != null) {
        AttendanceBreakdownModal(
            subjects = dashboardData!!.subjects,
            onDismiss = { showAttendanceModal = false }
        )
    }

    // Counseling log modal
    if (showCounselingLogModal && dashboardData != null) {
        CounselingLogModal(
            logs = dashboardData!!.logs,
            onDismiss = { showCounselingLogModal = false }
        )
    }
}

/**
 * Main dashboard content with Bento grid layout.
 */
@Composable
fun ParentDashboardContent(
    data: ParentDashboardData,
    greeting: String,
    onAttendanceClick: () -> Unit,
    onMentorLogClick: () -> Unit
) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        contentPadding = PaddingValues(vertical = 16.dp)
    ) {
        // Header with student info
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    text = greeting,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onBackground
                )
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = "Monitoring",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Surface(
                        color = MaterialTheme.colorScheme.surface,
                        shape = RoundedCornerShape(4.dp),
                        tonalElevation = 1.dp
                    ) {
                        Text(
                            text = data.student.name,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                    Text(
                        text = "${data.student.className} | ${data.student.roll}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                // Term grant status pill
                data.termGrant?.let { grant ->
                    Spacer(modifier = Modifier.height(8.dp))
                    TermGrantPill(status = grant.status)
                }
            }
        }

        // Row 1: Attendance + Academic Status + Action Card
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Attendance Card
                AttendanceCard(
                    percentage = data.stats.percentage,
                    attended = data.stats.attended,
                    total = data.stats.total,
                    onClick = onAttendanceClick,
                    modifier = Modifier.weight(1f)
                )

                // Academic Status Card
                AcademicStatusCard(
                    isDefaulter = data.stats.isDefaulter,
                    leaves = data.leaves,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        // Action Card (Detention/Escalation/All Clear)
        item {
            ActionCard(
                detention = data.detention,
                escalation = data.escalation,
                onViewLog = onMentorLogClick
            )
        }

        // Exam Performance Section
        if (data.results.isNotEmpty()) {
            item {
                ExamPerformanceCard(results = data.results)
            }
        }

        // Mentor Card
        data.mentor?.let { mentor ->
            item {
                MentorCard(
                    mentor = mentor,
                    hasEscalation = data.escalation != null,
                    onViewLog = onMentorLogClick
                )
            }
        }

        // Recent Activity Section
        if (data.events.isNotEmpty() || data.leaves.isNotEmpty()) {
            item {
                RecentActivitySection(
                    events = data.events,
                    leaves = data.leaves
                )
            }
        }

        // Bottom spacing
        item {
            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

/**
 * Term grant status pill.
 */
@Composable
fun TermGrantPill(status: String) {
    val (backgroundColor, textColor, icon, label) = when (status.lowercase()) {
        "granted" -> listOf(
            StatusGreenLight, StatusGreen, Icons.Filled.CheckCircle, "Eligible for Exam"
        )
        "provisional" -> listOf(
            StatusYellowLight, StatusYellow, Icons.Filled.Warning, "Provisional"
        )
        else -> listOf(
            StatusRedLight, StatusRed, Icons.Filled.Cancel, "Detained"
        )
    }

    Surface(
        color = backgroundColor as Color,
        shape = RoundedCornerShape(20.dp)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Icon(
                imageVector = icon as androidx.compose.ui.graphics.vector.ImageVector,
                contentDescription = null,
                tint = textColor as Color,
                modifier = Modifier.size(16.dp)
            )
            Text(
                text = label as String,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                color = textColor
            )
        }
    }
}

/**
 * Attendance donut card.
 */
@Composable
fun AttendanceCard(
    percentage: Double,
    attended: Int,
    total: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val ringColor = if (percentage >= 75) MitTeal else StatusRed

    Card(
        modifier = modifier.clickable { onClick() },
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "ATTENDANCE",
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Icon(
                    imageVector = Icons.Outlined.OpenInNew,
                    contentDescription = "View details",
                    modifier = Modifier.size(14.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Donut chart representation
            Box(
                modifier = Modifier.size(80.dp),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(
                    progress = { (percentage / 100f).toFloat().coerceIn(0f, 1f) },
                    modifier = Modifier.size(80.dp),
                    strokeWidth = 8.dp,
                    color = ringColor,
                    trackColor = ringColor.copy(alpha = 0.2f)
                )
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "${percentage.toInt()}%",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = "$attended / $total Lectures",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

/**
 * Academic status card with leave balance.
 */
@Composable
fun AcademicStatusCard(
    isDefaulter: Boolean,
    leaves: List<ParentLeaveInfo>,
    modifier: Modifier = Modifier
) {
    val usedLeaves = leaves.filter { it.status.equals("Approved", ignoreCase = true) }
        .sumOf { it.days }
    val remainingLeaves = (20 - usedLeaves).coerceAtLeast(0.0)

    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = "ACADEMIC STANDING",
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Spacer(modifier = Modifier.height(12.dp))

            // Status badge
            Surface(
                color = if (isDefaulter) StatusRedLight else StatusGreenLight,
                shape = RoundedCornerShape(8.dp)
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        imageVector = if (isDefaulter) Icons.Filled.Warning else Icons.Filled.VerifiedUser,
                        contentDescription = null,
                        tint = if (isDefaulter) StatusRed else StatusGreen,
                        modifier = Modifier.size(20.dp)
                    )
                    Text(
                        text = if (isDefaulter) "Action Needed" else "Good Standing",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (isDefaulter) StatusRed else StatusGreen
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Leave balance
            Text(
                text = "Leave Balance: ${remainingLeaves.toInt()} days",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Spacer(modifier = Modifier.height(4.dp))

            LinearProgressIndicator(
                progress = { (remainingLeaves / 20.0).toFloat().coerceIn(0f, 1f) },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp)),
                color = StatusBlue,
                trackColor = StatusBlue.copy(alpha = 0.2f)
            )
        }
    }
}

/**
 * Action card showing detention, escalation, or all-clear status.
 */
@Composable
fun ActionCard(
    detention: ParentDetentionInfo?,
    escalation: ParentEscalationInfo?,
    onViewLog: () -> Unit
) {
    when {
        detention != null -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = StatusRedLight),
                shape = RoundedCornerShape(16.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Box(
                        modifier = Modifier
                            .size(48.dp)
                            .clip(CircleShape)
                            .background(Color.White),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Shield,
                            contentDescription = null,
                            tint = StatusRed,
                            modifier = Modifier.size(24.dp)
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Active Detention",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = StatusRed
                    )
                    Text(
                        text = detention.reason,
                        style = MaterialTheme.typography.bodySmall,
                        color = StatusRed.copy(alpha = 0.8f),
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }

        escalation != null -> {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onViewLog() },
                colors = CardDefaults.cardColors(containerColor = StatusYellowLight),
                shape = RoundedCornerShape(16.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Box(
                        modifier = Modifier
                            .size(48.dp)
                            .clip(CircleShape)
                            .background(Color.White),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Warning,
                            contentDescription = null,
                            tint = StatusYellow,
                            modifier = Modifier.size(24.dp)
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Escalated Issue",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFFB45309) // Darker orange for readability
                    )
                    Text(
                        text = "${escalation.category}: ${escalation.remarks}",
                        style = MaterialTheme.typography.bodySmall,
                        color = Color(0xFFB45309).copy(alpha = 0.8f),
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Surface(
                        color = Color.White,
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text(
                            text = "View Log",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFFB45309),
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp)
                        )
                    }
                }
            }
        }

        else -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                shape = RoundedCornerShape(16.dp),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Box(
                        modifier = Modifier
                            .size(48.dp)
                            .clip(CircleShape)
                            .background(StatusGreenLight),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Check,
                            contentDescription = null,
                            tint = StatusGreen,
                            modifier = Modifier.size(24.dp)
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "All Clear",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        text = "No pending disciplinary actions.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

/**
 * Exam performance card with TA scores.
 */
@Composable
fun ExamPerformanceCard(results: List<ParentCAResult>) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = "EXAM PERFORMANCE",
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                text = "Internal Assessment scores",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Results table
            results.forEach { result ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = result.subject,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.weight(1f),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )

                    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        // TA1
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "TA1",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = result.ta1 ?: "-",
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.SemiBold,
                                color = if (result.ta1 == null || result.ta1 == "-")
                                    MaterialTheme.colorScheme.onSurfaceVariant
                                else accentPurple()
                            )
                        }

                        // TA2
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "TA2",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = result.ta2 ?: "-",
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.SemiBold,
                                color = if (result.ta2 == null || result.ta2 == "-")
                                    MaterialTheme.colorScheme.onSurfaceVariant
                                else StatusBlue
                            )
                        }
                    }
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f))
            }
        }
    }
}

/**
 * Mentor card with contact info.
 */
@Composable
fun MentorCard(
    mentor: ParentMentorInfo,
    hasEscalation: Boolean,
    onViewLog: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = Color(0xFF1E293B) // Slate-800
        ),
        shape = RoundedCornerShape(16.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Avatar
                Box(
                    modifier = Modifier
                        .size(48.dp)
                        .clip(CircleShape)
                        .background(Color.White.copy(alpha = 0.1f)),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = mentor.name.firstOrNull()?.uppercase() ?: "?",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = Color.White
                    )
                }

                Column {
                    Text(
                        text = "ASSIGNED MENTOR",
                        style = MaterialTheme.typography.labelSmall,
                        color = Color.White.copy(alpha = 0.6f)
                    )
                    Text(
                        text = mentor.name,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Color.White
                    )
                    Text(
                        text = mentor.email,
                        style = MaterialTheme.typography.bodySmall,
                        color = Color.White.copy(alpha = 0.6f)
                    )
                }
            }

            Column(
                horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (hasEscalation) {
                    Surface(
                        color = StatusRed,
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text(
                            text = "Update Available",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                            color = Color.White,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                        )
                    }
                }

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = onViewLog,
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = Color.White
                        ),
                        border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(alpha = 0.3f)),
                        shape = RoundedCornerShape(8.dp),
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp)
                    ) {
                        Text(
                            text = "View Log",
                            style = MaterialTheme.typography.labelSmall
                        )
                    }
                }
            }
        }
    }
}

/**
 * Recent activity section showing events and leaves.
 */
@Composable
fun RecentActivitySection(
    events: List<ParentEventInfo>,
    leaves: List<ParentLeaveInfo>
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = "RECENT ACTIVITY",
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Spacer(modifier = Modifier.height(12.dp))

            // Events
            events.take(3).forEach { event ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Outlined.Event,
                        contentDescription = null,
                        tint = accentPurple(),
                        modifier = Modifier.size(20.dp)
                    )
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = event.name,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = "${event.date} - ${event.role}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    StatusBadge(
                        text = event.status,
                        type = if (event.status.equals("Attended", ignoreCase = true))
                            StatusType.SUCCESS else StatusType.INFO
                    )
                }
            }

            // Leaves
            leaves.take(3).forEach { leave ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Outlined.EventBusy,
                        contentDescription = null,
                        tint = MitTeal,
                        modifier = Modifier.size(20.dp)
                    )
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "${leave.type} Leave",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = "${leave.date} - ${leave.days.toInt()} day(s)",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    StatusBadge(
                        text = leave.status,
                        type = when (leave.status.lowercase()) {
                            "approved" -> StatusType.SUCCESS
                            "rejected" -> StatusType.ERROR
                            else -> StatusType.WARNING
                        }
                    )
                }
            }
        }
    }
}

/**
 * Modal for subject-wise attendance breakdown.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AttendanceBreakdownModal(
    subjects: List<ParentSubjectAttendance>,
    onDismiss: () -> Unit
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = "Subject Attendance",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
            Text(
                text = "Detailed breakdown by course",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Header
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surfaceVariant)
                    .padding(12.dp),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "Subject",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f)
                )
                Text(
                    text = "Conducted",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.width(16.dp))
                Text(
                    text = "Attended",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.width(16.dp))
                Text(
                    text = "%",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold
                )
            }

            // Rows
            subjects.forEach { subject ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(12.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = subject.subject,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            text = subject.code,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Text(
                        text = "${subject.conducted}",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Spacer(modifier = Modifier.width(24.dp))
                    Text(
                        text = "${subject.attended}",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Spacer(modifier = Modifier.width(16.dp))
                    Surface(
                        color = if (subject.percentage >= 75) StatusGreenLight else StatusRedLight,
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Text(
                            text = "${subject.percentage.toInt()}%",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = if (subject.percentage >= 75) StatusGreen else StatusRed,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f))
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

/**
 * Modal for counseling log history.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CounselingLogModal(
    logs: List<ParentCounselingLog>,
    onDismiss: () -> Unit
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = "Counseling History",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )

            Spacer(modifier = Modifier.height(16.dp))

            if (logs.isEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "No counseling records.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            } else {
                logs.forEach { log ->
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                        ),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = log.date,
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                StatusBadge(
                                    text = log.status,
                                    type = when (log.status.lowercase()) {
                                        "resolved" -> StatusType.SUCCESS
                                        "escalated" -> StatusType.ERROR
                                        else -> StatusType.INFO
                                    }
                                )
                            }
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = log.remarks,
                                style = MaterialTheme.typography.bodyMedium
                            )
                            Text(
                                text = "Category: ${log.category}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

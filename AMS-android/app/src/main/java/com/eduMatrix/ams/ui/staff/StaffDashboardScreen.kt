package com.eduMatrix.ams.ui.staff

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.unit.dp
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.*
import com.eduMatrix.ams.ui.components.*
import com.eduMatrix.ams.ui.theme.*
import androidx.compose.foundation.isSystemInDarkTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*

/**
 * Staff Dashboard screen matching the web application design.
 * Shows today's schedule, quick stats, and role-specific cards.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StaffDashboardScreen(
    onMarkAttendance: (scheduleId: String, date: String) -> Unit,
    onNavigateToLeaves: () -> Unit,
    onNavigateToMentees: () -> Unit,
    onNavigateToClassTeacher: () -> Unit,
    onNavigateToHod: () -> Unit,
    onNavigateToEvents: () -> Unit,
    onNavigateToNotifications: () -> Unit,
    onLogout: () -> Unit = {}
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var showLogoutDialog by rememberSaveable { mutableStateOf(false) }

    // Theme state
    val themeMode by ThemeState.themeMode
    val isSystemDark = isSystemInDarkTheme()

    // State
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var dashboardData by remember { mutableStateOf<StaffDashboardData?>(null) }
    var extraSessions by remember { mutableStateOf<List<ExtraSession>>(emptyList()) }
    var refreshTrigger by rememberSaveable { mutableStateOf(0) }
    var unreadNotificationCount by rememberSaveable { mutableStateOf(0) }

    // Extra session dialog state
    var showExtraSessionDialog by rememberSaveable { mutableStateOf(false) }
    var extraSessionAllocations by remember { mutableStateOf<List<ExtraSessionAllocation>>(emptyList()) }

    // Get current date
    val today = remember {
        SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
    }

    // Get greeting based on time
    val greeting = remember {
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        when {
            hour < 12 -> "Good Morning"
            hour < 17 -> "Good Afternoon"
            else -> "Good Evening"
        }
    }

    // Get user from prefs
    val user = remember { AppPrefs.getUser(context) }

    // Load dashboard data
    LaunchedEffect(refreshTrigger) {
        isLoading = true
        errorMessage = null

        try {
            val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
            val currentUser = AppPrefs.getUser(context) ?: throw Exception("User not found")
            val data = withContext(Dispatchers.IO) {
                ApiService.getStaffDashboard(BuildConfig.API_BASE_URL, token, currentUser.userId)
            }
            dashboardData = data

            // Fetch extra sessions
            try {
                extraSessions = withContext(Dispatchers.IO) {
                    ApiService.getExtraSessions(BuildConfig.API_BASE_URL, token, currentUser.userId)
                }
            } catch (_: Exception) {
                // Best-effort, don't fail dashboard if extra sessions fail
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

            isLoading = false
        } catch (e: com.eduMatrix.ams.data.api.ApiException) {
            isLoading = false
            // Handle 401 Unauthorized - token expired
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

    // Extra session creation state
    var isCreatingExtraSession by rememberSaveable { mutableStateOf(false) }
    var extraSessionError by rememberSaveable { mutableStateOf<String?>(null) }

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
                    }
                },
                actions = {
                    IconButton(onClick = { refreshTrigger++ }) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh"
                        )
                    }
                    // Dark mode toggle
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
                                // Show badge only if there are unread notifications
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
        },
        floatingActionButton = {
            if (dashboardData != null) {
                FloatingActionButton(
                    onClick = {
                        // Load allocations before showing dialog
                        scope.launch {
                            try {
                                val token = AppPrefs.getAccessToken(context) ?: return@launch
                                val currentUser = AppPrefs.getUser(context) ?: return@launch
                                extraSessionAllocations = withContext(Dispatchers.IO) {
                                    ApiService.getExtraSessionAllocations(
                                        BuildConfig.API_BASE_URL,
                                        token,
                                        currentUser.userId
                                    )
                                }
                                showExtraSessionDialog = true
                            } catch (e: Exception) {
                                extraSessionError = "Failed to load allocations: ${e.message}"
                            }
                        }
                    },
                    containerColor = primaryAccent()
                ) {
                    Icon(
                        imageVector = Icons.Default.Add,
                        contentDescription = "Schedule Extra Class",
                        tint = Color.White
                    )
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
                            text = "Failed to load dashboard",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        Text(
                            text = errorMessage ?: "",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Button(
                            onClick = { refreshTrigger++ },
                            colors = ButtonDefaults.buttonColors(containerColor = primaryAccent())
                        ) {
                            Text("Retry")
                        }
                    }
                }

                dashboardData != null -> {
                    val data = dashboardData!!

                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        // Greeting card
                        item {
                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                colors = CardDefaults.cardColors(
                                    containerColor = primaryAccent()
                                ),
                                shape = RoundedCornerShape(16.dp)
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(20.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column {
                                        Text(
                                            text = "$greeting,",
                                            style = MaterialTheme.typography.bodyLarge,
                                            color = Color.White.copy(alpha = 0.8f)
                                        )
                                        Text(
                                            text = data.profile.name,
                                            style = MaterialTheme.typography.headlineSmall,
                                            fontWeight = FontWeight.Bold,
                                            color = Color.White
                                        )
                                        Text(
                                            text = data.profile.departmentName,
                                            style = MaterialTheme.typography.bodyMedium,
                                            color = Color.White.copy(alpha = 0.7f)
                                        )
                                    }
                                    // Avatar
                                    Box(
                                        modifier = Modifier
                                            .size(56.dp)
                                            .clip(CircleShape)
                                            .background(Color.White.copy(alpha = 0.2f)),
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Text(
                                            text = data.profile.name.take(1).uppercase(),
                                            style = MaterialTheme.typography.headlineSmall,
                                            fontWeight = FontWeight.Bold,
                                            color = Color.White
                                        )
                                    }
                                }
                            }
                        }

                        // Stats grid - matching web design
                        item {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(12.dp)
                            ) {
                                StatCard(
                                    title = "Weekly Load",
                                    value = "${data.sessionsThisMonth}",
                                    icon = Icons.Outlined.BarChart,
                                    iconColor = accentPurple(),
                                    modifier = Modifier.weight(1f)
                                )
                                StatCard(
                                    title = "Avg Attendance",
                                    value = "0%",  // TODO: Get from backend when available
                                    icon = Icons.Outlined.People,
                                    iconColor = accentTeal(),
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }

                        // Role-specific cards
                        if (data.roles.isClassTeacher && data.classTeacherSection != null) {
                            item {
                                RoleCard(
                                    title = "Class Teacher",
                                    subtitle = "${data.classTeacherSection.classLevel} - ${data.classTeacherSection.sectionName}",
                                    detail = "${data.classTeacherSection.totalStudents} Students",
                                    icon = Icons.Filled.Class,
                                    accentColor = secondaryAccent(),
                                    onClick = onNavigateToClassTeacher
                                )
                            }

                            // Leave Approvals - Only for Class Teachers
                            if (data.pendingLeaveRequests > 0) {
                                item {
                                    RoleCard(
                                        title = "Leave Approvals",
                                        subtitle = "Pending Requests",
                                        detail = "${data.pendingLeaveRequests} awaiting approval",
                                        icon = Icons.Filled.EventBusy,
                                        accentColor = StatusRed,
                                        onClick = onNavigateToLeaves
                                    )
                                }
                            }
                        }

                        if (data.roles.isHod && data.hodDepartment != null) {
                            item {
                                RoleCard(
                                    title = "Head of Department",
                                    subtitle = data.hodDepartment.departmentName,
                                    detail = "${data.hodDepartment.totalFaculty} faculty | ${data.hodDepartment.pendingLongLeaves} pending leaves",
                                    icon = Icons.Filled.AdminPanelSettings,
                                    accentColor = primaryAccent(),
                                    onClick = onNavigateToHod
                                )
                            }
                        }

                        if (data.roles.isMentor && data.mentorBatch != null) {
                            item {
                                RoleCard(
                                    title = "My Mentees",
                                    subtitle = "Counseling Group",
                                    detail = "${data.mentorBatch.totalMentees} Students",
                                    icon = Icons.Filled.SupervisedUserCircle,
                                    accentColor = MitOrange,
                                    onClick = onNavigateToMentees
                                )
                            }
                        }

                        // Event Coordinator card
                        if (data.roles.isEventCoordinator) {
                            item {
                                RoleCard(
                                    title = "Event Manager",
                                    subtitle = "Manage Events",
                                    detail = "Create & Manage",
                                    icon = Icons.Filled.Event,
                                    accentColor = MitGold,
                                    onClick = onNavigateToEvents
                                )
                            }
                        }

                        // Today's schedule
                        item {
                            SectionHeader(
                                title = "Today's Schedule",
                                action = if (data.todaySchedule.size > 3) "View All" else null,
                                onAction = { /* Navigate to full schedule */ }
                            )
                        }

                        if (data.todaySchedule.isEmpty()) {
                            item {
                                Card(
                                    modifier = Modifier.fillMaxWidth(),
                                    colors = CardDefaults.cardColors(
                                        containerColor = MaterialTheme.colorScheme.surface
                                    ),
                                    shape = RoundedCornerShape(12.dp)
                                ) {
                                    EmptyState(
                                        icon = Icons.Outlined.EventAvailable,
                                        title = "No Classes Today",
                                        message = "You don't have any scheduled classes for today."
                                    )
                                }
                            }
                        } else {
                            items(data.todaySchedule.take(5)) { session ->
                                // Check if session is adjusted out (someone else is covering)
                                val adjustment = session.adjustment
                                val isAdjustedOut = adjustment != null &&
                                        adjustment.status == "Approved" &&
                                        adjustment.kind == "out" &&
                                        adjustment.role == "requester"
                                val isPendingAdjustment = adjustment != null && adjustment.status == "Pending"
                                val canMark = !session.isCompleted && !isAdjustedOut && !isPendingAdjustment

                                SessionCard(
                                    startTime = session.startTime,
                                    endTime = session.endTime,
                                    subjectName = session.subject.subjectName,
                                    sectionName = "${session.subject.classLevel}-${session.subject.sectionName}",
                                    roomNumber = session.roomNumber,
                                    sessionType = session.subject.sessionType,
                                    isCompleted = session.isCompleted,
                                    isAdjusted = isAdjustedOut,
                                    onMarkAttendance = if (canMark) {
                                        { onMarkAttendance(session.scheduleId.toString(), today) }
                                    } else null
                                )
                            }
                        }

                        // Today's Extra Sessions
                        val todayExtraSessions = extraSessions.filter { it.date == today && it.status == "Scheduled" }
                        if (todayExtraSessions.isNotEmpty()) {
                            item {
                                SectionHeader(title = "Extra Classes Today")
                            }

                            items(todayExtraSessions) { session ->
                                ExtraSessionCard(
                                    session = session,
                                    onMarkAttendance = if (!session.attendanceMarked) {
                                        { onMarkAttendance("extra_${session.id}", today) }
                                    } else null,
                                    onCancel = null // Can't cancel from dashboard for simplicity
                                )
                            }
                        }

                        // Upcoming Extra Sessions (next few days) - only show future dates
                        val upcomingExtraSessions = extraSessions.filter { it.date > today && it.status == "Scheduled" }.take(3)
                        if (upcomingExtraSessions.isNotEmpty()) {
                            item {
                                SectionHeader(title = "Upcoming Extra Classes")
                            }

                            items(upcomingExtraSessions) { session ->
                                ExtraSessionCard(
                                    session = session,
                                    onMarkAttendance = null,
                                    onCancel = null
                                )
                            }
                        }

                        // Quick actions - only show if there are relevant actions
                        val hasQuickActions = data.roles.isClassTeacher || data.roles.isMentor
                        if (hasQuickActions) {
                            item {
                                SectionHeader(title = "Quick Actions")
                            }

                            item {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                                ) {
                                    // Leave Approvals - Only for Class Teachers
                                    if (data.roles.isClassTeacher) {
                                        QuickActionButton(
                                            title = "Leave Approvals",
                                            icon = Icons.Outlined.EventBusy,
                                            onClick = onNavigateToLeaves,
                                            modifier = Modifier.weight(1f)
                                        )
                                    }
                                    // Mentor Logs - Only for Mentors
                                    if (data.roles.isMentor) {
                                        QuickActionButton(
                                            title = "Mentor Logs",
                                            icon = Icons.Outlined.NoteAlt,
                                            onClick = onNavigateToMentees,
                                            modifier = Modifier.weight(1f)
                                        )
                                    }
                                }
                            }
                        }

                        // Spacer at bottom
                        item {
                            Spacer(modifier = Modifier.height(16.dp))
                        }
                    }
                }
            }
        }
    }

    // Logout confirmation dialog
    if (showLogoutDialog) {
        AlertDialog(
            onDismissRequest = { showLogoutDialog = false },
            icon = {
                Icon(
                    imageVector = Icons.Default.ExitToApp,
                    contentDescription = null,
                    tint = StatusRed
                )
            },
            title = {
                Text("Logout")
            },
            text = {
                Text("Are you sure you want to logout?")
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showLogoutDialog = false
                        // Clear stored credentials
                        AppPrefs.clearAll(context)
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

    // Extra session creation dialog
    if (showExtraSessionDialog) {
        ExtraSessionCreateDialog(
            allocations = extraSessionAllocations,
            isLoading = isCreatingExtraSession,
            error = extraSessionError,
            onDismiss = {
                showExtraSessionDialog = false
                extraSessionError = null
            },
            onCreate = { request ->
                scope.launch {
                    isCreatingExtraSession = true
                    extraSessionError = null
                    try {
                        val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                        val currentUser = AppPrefs.getUser(context) ?: throw Exception("User not found")
                        withContext(Dispatchers.IO) {
                            ApiService.createExtraSession(
                                BuildConfig.API_BASE_URL,
                                token,
                                currentUser.userId,
                                request
                            )
                        }
                        showExtraSessionDialog = false
                        refreshTrigger++ // Refresh dashboard to show new session
                    } catch (e: Exception) {
                        extraSessionError = e.message ?: "Failed to create extra session"
                    } finally {
                        isCreatingExtraSession = false
                    }
                }
            }
        )
    }

    // Show error snackbar for allocation loading error
    extraSessionError?.let { error ->
        if (!showExtraSessionDialog) {
            LaunchedEffect(error) {
                kotlinx.coroutines.delay(3000)
                extraSessionError = null
            }
        }
    }
}

/**
 * Role-specific info card (Class Teacher, HOD, Mentor)
 */
@Composable
private fun RoleCard(
    title: String,
    subtitle: String,
    detail: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    accentColor: Color,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        shape = RoundedCornerShape(12.dp),
        onClick = onClick
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Left accent bar
            Box(
                modifier = Modifier
                    .width(4.dp)
                    .height(60.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(accentColor)
            )

            // Icon
            val isDark = isSystemInDarkTheme()
            val iconBgAlpha = if (isDark) 0.2f else 0.1f
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(accentColor.copy(alpha = iconBgAlpha)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = accentColor,
                    modifier = Modifier.size(24.dp)
                )
            }

            // Text content
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodyMedium,
                    color = accentColor
                )
                Text(
                    text = detail,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Chevron
            Icon(
                imageVector = Icons.Default.ChevronRight,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

/**
 * Card displaying an extra session (one-time class) for staff.
 */
@Composable
private fun ExtraSessionCard(
    session: ExtraSession,
    onMarkAttendance: (() -> Unit)?,
    onCancel: (() -> Unit)?
) {
    val isToday = session.date == SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (isToday) {
                MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
            } else {
                MaterialTheme.colorScheme.surface
            }
        ),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Time badge
            Column(
                modifier = Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.secondaryContainer)
                    .padding(horizontal = 10.dp, vertical = 8.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = session.startTime.take(5),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSecondaryContainer
                )
                Text(
                    text = session.endTime.take(5),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.7f)
                )
            }

            // Info column
            Column(modifier = Modifier.weight(1f)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = session.subjectName,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    // Extra session badge
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = MaterialTheme.colorScheme.tertiary
                    ) {
                        Text(
                            text = "EXTRA",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onTertiary,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
                Text(
                    text = session.sectionName,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (!isToday) {
                    Text(
                        text = session.dateDisplay,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                }
                session.topic?.let { topic ->
                    Text(
                        text = "Topic: $topic",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.secondary,
                        maxLines = 1
                    )
                }
            }

            // Action button
            if (session.attendanceMarked) {
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = MaterialTheme.colorScheme.primaryContainer
                ) {
                    Icon(
                        imageVector = Icons.Default.CheckCircle,
                        contentDescription = "Completed",
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(8.dp)
                    )
                }
            } else if (onMarkAttendance != null && isToday) {
                FilledTonalButton(
                    onClick = onMarkAttendance,
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp)
                ) {
                    Text("Mark", style = MaterialTheme.typography.labelMedium)
                }
            }
        }
    }
}

/**
 * Dialog for creating a new extra session (one-time class).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ExtraSessionCreateDialog(
    allocations: List<ExtraSessionAllocation>,
    isLoading: Boolean,
    error: String?,
    onDismiss: () -> Unit,
    onCreate: (ExtraSessionCreateRequest) -> Unit
) {
    // Form state
    var selectedSection by remember { mutableStateOf<ExtraSessionAllocation?>(null) }
    var selectedSubject by remember { mutableStateOf<AllocationSubject?>(null) }
    var selectedDate by remember { mutableStateOf("") }
    var startTime by remember { mutableStateOf("") }
    var endTime by remember { mutableStateOf("") }
    var topic by remember { mutableStateOf("") }
    var meetingLink by remember { mutableStateOf("") }

    // Dropdown state
    var sectionExpanded by remember { mutableStateOf(false) }
    var subjectExpanded by remember { mutableStateOf(false) }

    // Date/time picker state
    var showDatePicker by remember { mutableStateOf(false) }
    var showStartTimePicker by remember { mutableStateOf(false) }
    var showEndTimePicker by remember { mutableStateOf(false) }

    // Get today's date for min date validation
    val today = remember {
        Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0)
            set(Calendar.MINUTE, 0)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }.timeInMillis
    }

    // Validation
    val isValid = selectedSection != null &&
            selectedSubject != null &&
            selectedDate.isNotBlank() &&
            startTime.isNotBlank() &&
            endTime.isNotBlank()

    AlertDialog(
        onDismissRequest = { if (!isLoading) onDismiss() },
        title = {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Event,
                    contentDescription = null,
                    tint = primaryAccent()
                )
                Text("Schedule Extra Class")
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 400.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Section dropdown
                ExposedDropdownMenuBox(
                    expanded = sectionExpanded,
                    onExpandedChange = { if (!isLoading) sectionExpanded = it }
                ) {
                    OutlinedTextField(
                        value = selectedSection?.sectionName ?: "",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Class/Section *") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = sectionExpanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        enabled = !isLoading
                    )
                    ExposedDropdownMenu(
                        expanded = sectionExpanded,
                        onDismissRequest = { sectionExpanded = false }
                    ) {
                        allocations.forEach { allocation ->
                            DropdownMenuItem(
                                text = { Text(allocation.sectionName) },
                                onClick = {
                                    selectedSection = allocation
                                    selectedSubject = null // Reset subject when section changes
                                    sectionExpanded = false
                                }
                            )
                        }
                    }
                }

                // Subject dropdown
                ExposedDropdownMenuBox(
                    expanded = subjectExpanded,
                    onExpandedChange = { if (!isLoading && selectedSection != null) subjectExpanded = it }
                ) {
                    OutlinedTextField(
                        value = selectedSubject?.let { "${it.subjectName} (${it.subjectCode})" } ?: "",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Subject *") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = subjectExpanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        enabled = !isLoading && selectedSection != null
                    )
                    ExposedDropdownMenu(
                        expanded = subjectExpanded,
                        onDismissRequest = { subjectExpanded = false }
                    ) {
                        selectedSection?.subjects?.forEach { subject ->
                            DropdownMenuItem(
                                text = { Text("${subject.subjectName} (${subject.subjectCode})") },
                                onClick = {
                                    selectedSubject = subject
                                    subjectExpanded = false
                                }
                            )
                        }
                    }
                }

                // Date field
                OutlinedTextField(
                    value = selectedDate,
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Date *") },
                    trailingIcon = {
                        IconButton(onClick = { if (!isLoading) showDatePicker = true }) {
                            Icon(Icons.Default.CalendarToday, contentDescription = "Select date")
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth(),
                    enabled = !isLoading
                )

                // Time fields row
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    OutlinedTextField(
                        value = startTime,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Start *") },
                        trailingIcon = {
                            IconButton(onClick = { if (!isLoading) showStartTimePicker = true }) {
                                Icon(Icons.Default.Schedule, contentDescription = "Select start time")
                            }
                        },
                        modifier = Modifier.weight(1f),
                        enabled = !isLoading
                    )
                    OutlinedTextField(
                        value = endTime,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("End *") },
                        trailingIcon = {
                            IconButton(onClick = { if (!isLoading) showEndTimePicker = true }) {
                                Icon(Icons.Default.Schedule, contentDescription = "Select end time")
                            }
                        },
                        modifier = Modifier.weight(1f),
                        enabled = !isLoading
                    )
                }

                // Topic field
                OutlinedTextField(
                    value = topic,
                    onValueChange = { topic = it },
                    label = { Text("Topic (optional)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    enabled = !isLoading
                )

                // Meeting link field
                OutlinedTextField(
                    value = meetingLink,
                    onValueChange = { meetingLink = it },
                    label = { Text("Meeting Link (optional)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    enabled = !isLoading
                )

                // Error message
                error?.let {
                    Text(
                        text = it,
                        color = StatusRed,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (isValid) {
                        onCreate(
                            ExtraSessionCreateRequest(
                                subjectId = selectedSubject!!.subjectId,
                                sectionId = selectedSection!!.sectionId,
                                date = selectedDate,
                                startTime = startTime,
                                endTime = endTime,
                                topic = topic.ifBlank { null },
                                meetingLink = meetingLink.ifBlank { null }
                            )
                        )
                    }
                },
                enabled = isValid && !isLoading,
                colors = ButtonDefaults.buttonColors(containerColor = primaryAccent())
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        color = Color.White,
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Schedule")
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isLoading
            ) {
                Text("Cancel")
            }
        }
    )

    // Date picker dialog
    if (showDatePicker) {
        val datePickerState = rememberDatePickerState(
            initialSelectedDateMillis = System.currentTimeMillis(),
            selectableDates = object : SelectableDates {
                override fun isSelectableDate(utcTimeMillis: Long): Boolean {
                    return utcTimeMillis >= today
                }
            }
        )
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        datePickerState.selectedDateMillis?.let { millis ->
                            val sdf = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault())
                            selectedDate = sdf.format(Date(millis))
                        }
                        showDatePicker = false
                    }
                ) {
                    Text("OK")
                }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) {
                    Text("Cancel")
                }
            }
        ) {
            DatePicker(state = datePickerState)
        }
    }

    // Start time picker dialog
    if (showStartTimePicker) {
        val timePickerState = rememberTimePickerState(
            initialHour = 9,
            initialMinute = 0
        )
        TimePickerDialog(
            onDismiss = { showStartTimePicker = false },
            onConfirm = {
                startTime = String.format("%02d:%02d", timePickerState.hour, timePickerState.minute)
                showStartTimePicker = false
            }
        ) {
            TimePicker(state = timePickerState)
        }
    }

    // End time picker dialog
    if (showEndTimePicker) {
        val timePickerState = rememberTimePickerState(
            initialHour = 10,
            initialMinute = 0
        )
        TimePickerDialog(
            onDismiss = { showEndTimePicker = false },
            onConfirm = {
                endTime = String.format("%02d:%02d", timePickerState.hour, timePickerState.minute)
                showEndTimePicker = false
            }
        ) {
            TimePicker(state = timePickerState)
        }
    }
}

/**
 * Custom dialog wrapper for TimePicker.
 */
@Composable
private fun TimePickerDialog(
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
    content: @Composable () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Select Time") },
        text = {
            Box(
                modifier = Modifier.fillMaxWidth(),
                contentAlignment = Alignment.Center
            ) {
                content()
            }
        },
        confirmButton = {
            TextButton(onClick = onConfirm) {
                Text("OK")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

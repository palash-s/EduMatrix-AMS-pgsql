package com.eduMatrix.ams.ui.staff

import androidx.compose.foundation.background
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
import java.text.SimpleDateFormat
import java.util.*

/**
 * Staff Dashboard screen matching the web application design.
 * Shows today's schedule, quick stats, and role-specific cards.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StaffDashboardScreen(
    onMarkAttendance: (scheduleId: Int, date: String) -> Unit,
    onNavigateToLeaves: () -> Unit,
    onNavigateToMentees: () -> Unit,
    onNavigateToClassTeacher: () -> Unit,
    onNavigateToHod: () -> Unit,
    onNavigateToNotifications: () -> Unit,
    onLogout: () -> Unit = {}
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var showLogoutDialog by rememberSaveable { mutableStateOf(false) }

    // State
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var dashboardData by remember { mutableStateOf<StaffDashboardData?>(null) }
    var refreshTrigger by rememberSaveable { mutableStateOf(0) }

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
                    IconButton(onClick = onNavigateToNotifications) {
                        BadgedBox(
                            badge = {
                                // Show badge if there are unread notifications
                                Badge { Text("3") }
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
                            colors = ButtonDefaults.buttonColors(containerColor = MitPurple)
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
                                    containerColor = MitPurple
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
                                    accentColor = MitTeal,
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
                                    accentColor = MitPurple,
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
                                SessionCard(
                                    startTime = session.startTime,
                                    endTime = session.endTime,
                                    subjectName = session.subject.subjectName,
                                    sectionName = "${session.subject.classLevel}-${session.subject.sectionName}",
                                    roomNumber = session.roomNumber,
                                    sessionType = session.subject.sessionType,
                                    isCompleted = session.isCompleted,
                                    onMarkAttendance = if (!session.isCompleted) {
                                        { onMarkAttendance(session.scheduleId, today) }
                                    } else null
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
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(accentColor.copy(alpha = 0.1f)),
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

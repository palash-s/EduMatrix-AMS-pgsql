package com.eduMatrix.ams.ui.staff

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.ui.navigation.NavRoutes
import com.eduMatrix.ams.ui.staff.attendance.StaffMarkAttendanceScreen
import com.eduMatrix.ams.ui.staff.events.EventDashboardScreen
import com.eduMatrix.ams.ui.staff.hod.HodLeaveApprovalsScreen
import com.eduMatrix.ams.ui.staff.leaves.StaffLeaveApprovalsScreen
import com.eduMatrix.ams.ui.staff.mentor.MentorDashboardScreen
import com.eduMatrix.ams.ui.theme.accentPurple
import androidx.compose.ui.unit.dp
import com.eduMatrix.ams.ui.notifications.NotificationsScreen
import kotlinx.coroutines.launch


/**
 * Main screen for Staff users with bottom navigation.
 * Contains tabs for:
 * - Home (Dashboard)
 * - Upcoming (Schedule with session adjustment)
 * - History (Session history with attendance percentages)
 * - Leaves (class teacher only)
 * Note: Marks entry is web-only feature.
 */
@Composable
fun StaffMainScreen(
    onLogout: () -> Unit
) {
    val navController = rememberNavController()
    val context = LocalContext.current

    // Get user to check if they are a class teacher
    val user = remember { AppPrefs.getUser(context) }
    val isClassTeacher = user?.staffRoles?.isClassTeacher == true

    // Staff navigation items (Marks is web-only, Leaves is class teacher only)
    val navItems = buildList {
        add(
            StaffNavItem(
                route = NavRoutes.STAFF_DASHBOARD,
                title = "Home",
                selectedIcon = Icons.Filled.Home,
                unselectedIcon = Icons.Outlined.Home
            )
        )
        add(
            StaffNavItem(
                route = NavRoutes.STAFF_SCHEDULE,
                title = "Upcoming",
                selectedIcon = Icons.Filled.CalendarMonth,
                unselectedIcon = Icons.Outlined.CalendarMonth
            )
        )
        add(
            StaffNavItem(
                route = NavRoutes.STAFF_SESSION_HISTORY,
                title = "History",
                selectedIcon = Icons.Filled.History,
                unselectedIcon = Icons.Outlined.History
            )
        )
        // Only show Leaves tab for class teachers
        if (isClassTeacher) {
            add(
                StaffNavItem(
                    route = NavRoutes.STAFF_LEAVES,
                    title = "Leaves",
                    selectedIcon = Icons.Filled.EventBusy,
                    unselectedIcon = Icons.Outlined.EventBusy
                )
            )
        }
    }

    Scaffold(
        bottomBar = {
            StaffBottomNavigation(
                navController = navController,
                items = navItems
            )
        }
    ) { paddingValues ->
        NavHost(
            navController = navController,
            startDestination = NavRoutes.STAFF_DASHBOARD,
            modifier = Modifier.padding(paddingValues)
        ) {
            // Dashboard
            composable(NavRoutes.STAFF_DASHBOARD) {
                StaffDashboardScreen(
                    onMarkAttendance = { scheduleId, date ->
                        navController.navigate(NavRoutes.staffMarkAttendance(scheduleId, date))
                    },
                    onNavigateToLeaves = {
                        navController.navigate(NavRoutes.STAFF_LEAVES) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    onNavigateToMentees = {
                        navController.navigate(NavRoutes.MENTOR_DASHBOARD)
                    },
                    onNavigateToClassTeacher = {
                        navController.navigate(NavRoutes.CLASS_TEACHER_DASHBOARD)
                    },
                    onNavigateToHod = {
                        navController.navigate(NavRoutes.HOD_DASHBOARD)
                    },
                    onNavigateToEvents = {
                        navController.navigate(NavRoutes.EVENT_DASHBOARD)
                    },
                    onNavigateToNotifications = {
                        navController.navigate(NavRoutes.STAFF_NOTIFICATIONS)
                    },
                    onLogout = onLogout
                )
            }

            // Upcoming Schedule screen (with session adjustment)
            composable(NavRoutes.STAFF_SCHEDULE) {
                UpcomingScheduleScreen(
                    onMarkAttendance = { scheduleId, date ->
                        navController.navigate(NavRoutes.staffMarkAttendance(scheduleId, date))
                    }
                )
            }

            // Session History screen
            composable(NavRoutes.STAFF_SESSION_HISTORY) {
                SessionHistoryScreen(
                    onViewSession = { scheduleId, date ->
                        navController.navigate(NavRoutes.staffMarkAttendance(scheduleId, date))
                    }
                )
            }

            // Mark attendance screen
            composable(NavRoutes.STAFF_MARK_ATTENDANCE) { backStackEntry ->
                val scheduleId = backStackEntry.arguments?.getString("scheduleId") ?: ""
                val date = backStackEntry.arguments?.getString("date") ?: ""
                StaffMarkAttendanceScreen(
                    scheduleId = scheduleId,
                    date = date,
                    onBack = { navController.popBackStack() },
                    onSuccess = { navController.popBackStack() }
                )
            }

            // Leave approvals screen
            composable(NavRoutes.STAFF_LEAVES) {
                StaffLeaveApprovalsScreen(
                    onViewDetails = { leaveId ->
                        navController.navigate(NavRoutes.staffLeaveDetail(leaveId))
                    }
                )
            }

            // Notifications screen
            composable(NavRoutes.STAFF_NOTIFICATIONS) {
                StaffNotificationsScreen(
                    onBack = { navController.popBackStack() }
                )
            }

            // Class Teacher Dashboard
            composable(NavRoutes.CLASS_TEACHER_DASHBOARD) {
                ClassTeacherDashboardScreen(
                    onBack = { navController.popBackStack() }
                )
            }

            // HOD Dashboard
            composable(NavRoutes.HOD_DASHBOARD) {
                HodDashboardScreen(
                    onBack = { navController.popBackStack() },
                    onNavigateToLeaveApprovals = {
                        navController.navigate(NavRoutes.HOD_LEAVE_APPROVALS)
                    }
                )
            }

            // HOD Leave Approvals
            composable(NavRoutes.HOD_LEAVE_APPROVALS) {
                HodLeaveApprovalsScreen(
                    onBack = { navController.popBackStack() }
                )
            }

            // Mentor Dashboard
            composable(NavRoutes.MENTOR_DASHBOARD) {
                MentorDashboardScreen(
                    onBack = { navController.popBackStack() },
                    onAddLog = { studentId ->
                        navController.navigate(NavRoutes.mentorAddLog(studentId))
                    }
                )
            }

            // Event Dashboard
            composable(NavRoutes.EVENT_DASHBOARD) {
                EventDashboardScreen(
                    onBack = { navController.popBackStack() }
                )
            }
        }
    }
}

/**
 * Bottom navigation item data class
 */
data class StaffNavItem(
    val route: String,
    val title: String,
    val selectedIcon: ImageVector,
    val unselectedIcon: ImageVector
)

/**
 * Bottom navigation bar for staff
 */
@Composable
private fun StaffBottomNavigation(
    navController: NavHostController,
    items: List<StaffNavItem>
) {
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = navBackStackEntry?.destination

    NavigationBar(
        containerColor = MaterialTheme.colorScheme.surface,
        tonalElevation = 0.dp
    ) {
        items.forEach { item ->
            val selected = currentDestination?.hierarchy?.any { it.route == item.route } == true

            NavigationBarItem(
                selected = selected,
                onClick = {
                    navController.navigate(item.route) {
                        popUpTo(navController.graph.findStartDestination().id) {
                            saveState = true
                        }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
                icon = {
                    Icon(
                        imageVector = if (selected) item.selectedIcon else item.unselectedIcon,
                        contentDescription = item.title
                    )
                },
                label = { Text(item.title) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = accentPurple(),
                    selectedTextColor = accentPurple(),
                    indicatorColor = accentPurple().copy(alpha = 0.1f)
                )
            )
        }
    }
}

// Note: StaffMarkAttendanceScreen moved to ui.staff.attendance package
// Note: Marks entry screens removed (web-only feature)
// Note: StaffLeaveApprovalsScreen moved to ui.staff.leaves package
// Note: UpcomingScheduleScreen and SessionHistoryScreen are in separate files

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StaffNotificationsScreen(
    onBack: () -> Unit,
    onLogout: (() -> Unit)? = null
) {
    NotificationsScreen(
        title = "Notifications",
        onBack = onBack,
        onLogout = onLogout
    )
}

// Note: ClassTeacherDashboardScreen moved to separate file

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HodDashboardScreen(
    onBack: () -> Unit,
    onNavigateToLeaveApprovals: () -> Unit = {}
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // State
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var deptName by remember { mutableStateOf("") }
    var stats by remember { mutableStateOf<com.eduMatrix.ams.data.models.HodStats?>(null) }
    var pendingCount by remember { mutableStateOf(0) }

    // Load dashboard data
    fun loadDashboard() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                val response = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                    com.eduMatrix.ams.data.api.ApiService.getHodDashboard(
                        baseUrl = com.eduMatrix.ams.BuildConfig.API_BASE_URL,
                        accessToken = token,
                        userId = user.userId
                    )
                }

                deptName = response.deptName
                stats = response.stats
                pendingCount = response.approvals.size
            } catch (e: com.eduMatrix.ams.data.api.ApiException) {
                errorMessage = e.message ?: "Failed to load dashboard"
            } catch (e: Exception) {
                errorMessage = "Connection error: ${e.message}"
            } finally {
                isLoading = false
            }
        }
    }

    // Initial load
    LaunchedEffect(Unit) {
        loadDashboard()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("HOD Dashboard")
                        if (deptName.isNotBlank()) {
                            Text(
                                text = deptName,
                                style = MaterialTheme.typography.bodySmall,
                                color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.8f)
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { loadDashboard() }) {
                        Icon(
                            Icons.Default.Refresh,
                            contentDescription = "Refresh",
                            tint = androidx.compose.ui.graphics.Color.White
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = accentPurple(),
                    titleContentColor = androidx.compose.ui.graphics.Color.White,
                    navigationIconContentColor = androidx.compose.ui.graphics.Color.White
                )
            )
        }
    ) { padding ->
        when {
            isLoading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = androidx.compose.ui.Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        CircularProgressIndicator(color = accentPurple())
                        Text(
                            text = "Loading department stats...",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }

            errorMessage != null -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = androidx.compose.ui.Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        Icon(
                            Icons.Outlined.Error,
                            contentDescription = null,
                            tint = com.eduMatrix.ams.ui.theme.StatusRed,
                            modifier = Modifier.size(48.dp)
                        )
                        Text(
                            text = errorMessage ?: "Unknown error",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Button(
                            onClick = { loadDashboard() },
                            colors = ButtonDefaults.buttonColors(containerColor = accentPurple())
                        ) {
                            Icon(Icons.Default.Refresh, contentDescription = null)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Retry")
                        }
                    }
                }
            }

            else -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    // Stats grid
                    stats?.let { s ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                            shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(16.dp),
                                horizontalArrangement = Arrangement.SpaceEvenly
                            ) {
                                HodStatItem(
                                    label = "Students",
                                    value = "${s.students}",
                                    color = com.eduMatrix.ams.ui.theme.primaryAccent()
                                )
                                HodStatItem(
                                    label = "Faculty",
                                    value = "${s.faculty}",
                                    color = accentPurple()
                                )
                                HodStatItem(
                                    label = "Attendance",
                                    value = "${s.attendance.toInt()}%",
                                    color = com.eduMatrix.ams.ui.theme.StatusGreen
                                )
                                HodStatItem(
                                    label = "Pending",
                                    value = "${s.pending}",
                                    color = com.eduMatrix.ams.ui.theme.StatusYellow
                                )
                            }
                        }
                    }

                    // Info card
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = accentPurple().copy(alpha = 0.1f)
                        )
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp),
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                        ) {
                            Icon(
                                Icons.Outlined.Info,
                                contentDescription = null,
                                tint = accentPurple()
                            )
                            Column {
                                Text(
                                    text = "Head of Department",
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold,
                                    color = accentPurple()
                                )
                                Text(
                                    text = "Manage escalated leave approvals and department overview.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }

                    // Quick action card for leave approvals
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onNavigateToLeaveApprovals() },
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surface
                        ),
                        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                        ) {
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(16.dp),
                                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(48.dp)
                                        .background(
                                            color = com.eduMatrix.ams.ui.theme.StatusYellow.copy(alpha = 0.1f),
                                            shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)
                                        ),
                                    contentAlignment = androidx.compose.ui.Alignment.Center
                                ) {
                                    Icon(
                                        Icons.Outlined.EventBusy,
                                        contentDescription = null,
                                        tint = com.eduMatrix.ams.ui.theme.StatusYellow,
                                        modifier = Modifier.size(24.dp)
                                    )
                                }
                                Column {
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = "Leave Approvals",
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold
                                        )
                                        if (pendingCount > 0) {
                                            Surface(
                                                color = com.eduMatrix.ams.ui.theme.StatusRed,
                                                shape = androidx.compose.foundation.shape.CircleShape
                                            ) {
                                                Text(
                                                    text = "$pendingCount",
                                                    style = MaterialTheme.typography.labelSmall,
                                                    color = androidx.compose.ui.graphics.Color.White,
                                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                                )
                                            }
                                        }
                                    }
                                    Text(
                                        text = "Review escalated leave requests",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                            Icon(
                                Icons.Default.ChevronRight,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun HodStatItem(
    label: String,
    value: String,
    color: androidx.compose.ui.graphics.Color
) {
    Column(
        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally
    ) {
        Text(
            text = value,
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold,
            color = color
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}


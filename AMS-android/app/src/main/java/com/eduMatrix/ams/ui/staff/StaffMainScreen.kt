package com.eduMatrix.ams.ui.staff

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
import com.eduMatrix.ams.ui.staff.leaves.StaffLeaveApprovalsScreen
import com.eduMatrix.ams.ui.staff.mentor.MentorDashboardScreen
import com.eduMatrix.ams.ui.theme.accentPurple
import androidx.compose.ui.unit.dp


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
                val scheduleId = backStackEntry.arguments?.getString("scheduleId")?.toIntOrNull() ?: 0
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
    onBack: () -> Unit
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Notifications") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentAlignment = androidx.compose.ui.Alignment.Center
        ) {
            Text("Notifications Screen - Coming Soon")
        }
    }
}

// Note: ClassTeacherDashboardScreen moved to separate file

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HodDashboardScreen(
    onBack: () -> Unit
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("HOD Dashboard") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentAlignment = androidx.compose.ui.Alignment.Center
        ) {
            Text("HOD Dashboard - Coming Soon")
        }
    }
}


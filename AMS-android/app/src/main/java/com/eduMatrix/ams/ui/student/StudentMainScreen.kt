package com.eduMatrix.ams.ui.student

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.eduMatrix.ams.ui.theme.accentPurple
import com.eduMatrix.ams.ui.notifications.NotificationsScreen

/**
 * Navigation routes for student portal
 */
object StudentNavRoutes {
    const val DASHBOARD = "student_dashboard"
    const val TIMETABLE = "student_timetable"
    const val RESULTS = "student_results"
    const val LEAVES = "student_leaves"
    const val FEEDBACK = "student_feedback"
    const val NOTIFICATIONS = "student_notifications"
    const val ELECTIVES = "student_electives"
    const val MDM = "student_mdm"
}

/**
 * Main screen for Student users with bottom navigation.
 * Contains tabs for:
 * - Home (Dashboard with attendance, alerts, etc.)
 * - Timetable
 * - Leaves (Apply/View)
 */
@Composable
fun StudentMainScreen(
    onLogout: () -> Unit
) {
    val navController = rememberNavController()

    // Navigation items (Alerts removed - now accessible via bell icon in top bar)
    val navItems = listOf(
        StudentNavItem(
            route = StudentNavRoutes.DASHBOARD,
            title = "Home",
            selectedIcon = Icons.Filled.Home,
            unselectedIcon = Icons.Outlined.Home
        ),
        StudentNavItem(
            route = StudentNavRoutes.TIMETABLE,
            title = "Timetable",
            selectedIcon = Icons.Filled.CalendarMonth,
            unselectedIcon = Icons.Outlined.CalendarMonth
        ),
        StudentNavItem(
            route = StudentNavRoutes.RESULTS,
            title = "Results",
            selectedIcon = Icons.Filled.Assessment,
            unselectedIcon = Icons.Outlined.Assessment
        ),
        StudentNavItem(
            route = StudentNavRoutes.LEAVES,
            title = "Leaves",
            selectedIcon = Icons.Filled.EventBusy,
            unselectedIcon = Icons.Outlined.EventBusy
        )
    )

    Scaffold(
        bottomBar = {
            StudentBottomNavigation(
                navController = navController,
                items = navItems
            )
        }
    ) { paddingValues ->
        NavHost(
            navController = navController,
            startDestination = StudentNavRoutes.DASHBOARD,
            modifier = Modifier.padding(paddingValues)
        ) {
            // Dashboard
            composable(StudentNavRoutes.DASHBOARD) {
                StudentDashboardScreen(
                    onNavigateToLeaves = {
                        navController.navigate(StudentNavRoutes.LEAVES) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    onNavigateToTimetable = {
                        navController.navigate(StudentNavRoutes.TIMETABLE) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    onNavigateToResults = {
                        navController.navigate(StudentNavRoutes.RESULTS) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    onNavigateToFeedback = {
                        navController.navigate(StudentNavRoutes.FEEDBACK)
                    },
                    onNavigateToNotifications = {
                        navController.navigate(StudentNavRoutes.NOTIFICATIONS) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    onNavigateToElectives = {
                        navController.navigate(StudentNavRoutes.ELECTIVES)
                    },
                    onNavigateToMDM = {
                        navController.navigate(StudentNavRoutes.MDM)
                    },
                    onLogout = onLogout
                )
            }

            // Timetable
            composable(StudentNavRoutes.TIMETABLE) {
                StudentTimetableScreen()
            }

            // Notifications
            composable(StudentNavRoutes.NOTIFICATIONS) {
                NotificationsScreen(
                    title = "Notifications",
                    onLogout = onLogout
                )
            }

            // Results
            composable(StudentNavRoutes.RESULTS) {
                StudentResultsScreen()
            }

            // Leaves
            composable(StudentNavRoutes.LEAVES) {
                StudentLeavesScreen()
            }

            // Feedback
            composable(StudentNavRoutes.FEEDBACK) {
                StudentFeedbackScreen(
                    onBack = { navController.popBackStack() }
                )
            }

            // Electives
            composable(StudentNavRoutes.ELECTIVES) {
                StudentElectivesScreen(
                    onBack = { navController.popBackStack() }
                )
            }

            // MDM / Open Elective
            composable(StudentNavRoutes.MDM) {
                StudentMDMScreen(
                    onBack = { navController.popBackStack() }
                )
            }
        }
    }
}

/**
 * Bottom navigation item data class
 */
data class StudentNavItem(
    val route: String,
    val title: String,
    val selectedIcon: ImageVector,
    val unselectedIcon: ImageVector
)

/**
 * Bottom navigation bar for students
 */
@Composable
private fun StudentBottomNavigation(
    navController: NavHostController,
    items: List<StudentNavItem>
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

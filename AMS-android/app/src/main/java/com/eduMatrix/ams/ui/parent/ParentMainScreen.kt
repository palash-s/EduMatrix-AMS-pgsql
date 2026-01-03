package com.eduMatrix.ams.ui.parent

import androidx.compose.animation.*
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.eduMatrix.ams.ui.navigation.NavRoutes
import com.eduMatrix.ams.ui.notifications.NotificationsScreen

/**
 * Navigation item for parent bottom navigation.
 */
data class ParentNavItem(
    val route: String,
    val title: String,
    val selectedIcon: ImageVector,
    val unselectedIcon: ImageVector
)

// Internal routes for parent navigation (not exposed to main nav)
private object ParentInternalRoutes {
    const val ATTENDANCE = "parent_internal_attendance"
}

/**
 * Main screen for Parent users with bottom navigation.
 * Contains tabs for:
 * - Home (Dashboard with Bento grid layout)
 * - Attendance (Subject breakdown)
 * - Notifications/Alerts
 */
@Composable
fun ParentMainScreen(
    onLogout: () -> Unit
) {
    val navController = rememberNavController()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    // Check if we're on a detail screen (hide bottom nav)
    val showBottomNav = currentRoute in listOf(
        NavRoutes.PARENT_DASHBOARD,
        ParentInternalRoutes.ATTENDANCE,
        NavRoutes.PARENT_NOTIFICATIONS
    )

    // Parent navigation items (Alerts removed - now accessible via bell icon in top bar)
    val navItems = listOf(
        ParentNavItem(
            route = NavRoutes.PARENT_DASHBOARD,
            title = "Home",
            selectedIcon = Icons.Filled.Home,
            unselectedIcon = Icons.Outlined.Home
        ),
        ParentNavItem(
            route = ParentInternalRoutes.ATTENDANCE,
            title = "Attendance",
            selectedIcon = Icons.Filled.BarChart,
            unselectedIcon = Icons.Outlined.BarChart
        )
    )

    Scaffold(
        bottomBar = {
            AnimatedVisibility(
                visible = showBottomNav,
                enter = slideInVertically(initialOffsetY = { it }),
                exit = slideOutVertically(targetOffsetY = { it })
            ) {
                ParentBottomNavigation(
                    navController = navController,
                    items = navItems
                )
            }
        }
    ) { paddingValues ->
        NavHost(
            navController = navController,
            startDestination = NavRoutes.PARENT_DASHBOARD,
            modifier = Modifier.padding(paddingValues)
        ) {
            // Dashboard
            composable(NavRoutes.PARENT_DASHBOARD) {
                ParentDashboardScreen(
                    onLogout = onLogout,
                    onNavigateToAttendance = {
                        navController.navigate(ParentInternalRoutes.ATTENDANCE)
                    },
                    onNavigateToNotifications = {
                        navController.navigate(NavRoutes.PARENT_NOTIFICATIONS)
                    }
                )
            }

            // Attendance Screen (Subject breakdown)
            composable(ParentInternalRoutes.ATTENDANCE) {
                ParentAttendanceScreen(
                    onBack = {
                        navController.popBackStack()
                    }
                )
            }

            // Notifications (placeholder for now)
            composable(NavRoutes.PARENT_NOTIFICATIONS) {
                NotificationsScreen(
                    title = "Notifications",
                    onBack = { navController.popBackStack() },
                    onLogout = onLogout
                )
            }
        }
    }
}

/**
 * Bottom navigation for parent screens.
 */
@Composable
fun ParentBottomNavigation(
    navController: NavHostController,
    items: List<ParentNavItem>
) {
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    NavigationBar {
        items.forEach { item ->
            NavigationBarItem(
                icon = {
                    Icon(
                        imageVector = if (currentRoute == item.route) item.selectedIcon else item.unselectedIcon,
                        contentDescription = item.title
                    )
                },
                label = { Text(item.title) },
                selected = currentRoute == item.route,
                onClick = {
                    if (currentRoute != item.route) {
                        navController.navigate(item.route) {
                            // Pop up to the start destination to avoid building up a large stack
                            popUpTo(NavRoutes.PARENT_DASHBOARD) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    }
                }
            )
        }
    }
}

/**
 * Placeholder for notifications screen.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ParentNotificationsPlaceholder() {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Notifications") }
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentAlignment = androidx.compose.ui.Alignment.Center
        ) {
            Text("Notifications coming soon")
        }
    }
}

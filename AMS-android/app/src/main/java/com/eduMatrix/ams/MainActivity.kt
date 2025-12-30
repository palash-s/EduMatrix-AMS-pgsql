package com.eduMatrix.ams

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.eduMatrix.ams.data.api.ApiException
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.UserRole
import com.eduMatrix.ams.ui.auth.LoginScreen
import com.eduMatrix.ams.ui.navigation.NavRoutes
import com.eduMatrix.ams.ui.staff.StaffMainScreen
import com.eduMatrix.ams.ui.student.StudentMainScreen
import com.eduMatrix.ams.ui.theme.AMSandroidTheme
import com.eduMatrix.ams.ui.theme.ThemeState
import com.eduMatrix.ams.ui.theme.rememberIsDarkTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Main Activity for EduMatrix AMS Android App.
 *
 * This is the entry point of the application. It handles:
 * - Theme setup with edge-to-edge display
 * - Root navigation between auth and main flows
 * - Role-based routing to appropriate portals
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Initialize theme from saved preferences
        ThemeState.initialize(this)
        enableEdgeToEdge()
        setContent {
            val isDarkTheme = rememberIsDarkTheme()
            AMSandroidTheme(darkTheme = isDarkTheme) {
                AppRoot()
            }
        }
    }
}

/**
 * Root composable that manages app-level navigation.
 * Handles authentication flow and routes to role-specific main screens.
 */
@Composable
fun AppRoot() {
    val context = LocalContext.current
    val navController = rememberNavController()

    // Determine start destination based on login state
    val startDestination = remember {
        if (AppPrefs.isLoggedIn(context)) {
            val user = AppPrefs.getUser(context)
            if (user?.mustChangePassword == true) {
                NavRoutes.CHANGE_PASSWORD
            } else {
                when (user?.role) {
                    UserRole.STAFF -> NavRoutes.STAFF_MAIN
                    UserRole.STUDENT -> NavRoutes.STUDENT_MAIN
                    UserRole.PARENT -> NavRoutes.PARENT_MAIN
                    UserRole.ADMIN -> NavRoutes.ADMIN_MAIN
                    else -> NavRoutes.LOGIN
                }
            }
        } else {
            NavRoutes.LOGIN
        }
    }

    NavHost(
        navController = navController,
        startDestination = startDestination
    ) {
        // Login screen
        composable(NavRoutes.LOGIN) {
            LoginScreen(
                onLoginSuccess = { role ->
                    val destination = when (role) {
                        UserRole.STAFF -> NavRoutes.STAFF_MAIN
                        UserRole.STUDENT -> NavRoutes.STUDENT_MAIN
                        UserRole.PARENT -> NavRoutes.PARENT_MAIN
                        UserRole.ADMIN -> NavRoutes.ADMIN_MAIN
                    }
                    navController.navigate(destination) {
                        popUpTo(NavRoutes.LOGIN) { inclusive = true }
                    }
                },
                onMustChangePassword = {
                    navController.navigate(NavRoutes.CHANGE_PASSWORD) {
                        popUpTo(NavRoutes.LOGIN) { inclusive = true }
                    }
                }
            )
        }

        // Change password screen
        composable(NavRoutes.CHANGE_PASSWORD) {
            ChangePasswordScreen(
                onSuccess = {
                    val user = AppPrefs.getUser(context)
                    val destination = when (user?.role) {
                        UserRole.STAFF -> NavRoutes.STAFF_MAIN
                        UserRole.STUDENT -> NavRoutes.STUDENT_MAIN
                        UserRole.PARENT -> NavRoutes.PARENT_MAIN
                        UserRole.ADMIN -> NavRoutes.ADMIN_MAIN
                        else -> NavRoutes.LOGIN
                    }
                    navController.navigate(destination) {
                        popUpTo(NavRoutes.CHANGE_PASSWORD) { inclusive = true }
                    }
                },
                onLogout = {
                    AppPrefs.clearSession(context)
                    navController.navigate(NavRoutes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }

        // Staff main screen
        composable(NavRoutes.STAFF_MAIN) {
            StaffMainScreen(
                onLogout = {
                    AppPrefs.clearSession(context)
                    navController.navigate(NavRoutes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }

        // Student main screen (placeholder - uses existing screens)
        composable(NavRoutes.STUDENT_MAIN) {
            StudentMainScreen(
                onLogout = {
                    AppPrefs.clearSession(context)
                    navController.navigate(NavRoutes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }

        // Parent main screen (placeholder)
        composable(NavRoutes.PARENT_MAIN) {
            PlaceholderScreen(
                title = "Parent Portal",
                message = "Parent portal coming soon",
                onLogout = {
                    AppPrefs.clearSession(context)
                    navController.navigate(NavRoutes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }

        // Admin main screen (placeholder)
        composable(NavRoutes.ADMIN_MAIN) {
            PlaceholderScreen(
                title = "Admin Portal",
                message = "Admin portal coming soon",
                onLogout = {
                    AppPrefs.clearSession(context)
                    navController.navigate(NavRoutes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }
    }
}

/**
 * Change password screen for first-time login.
 * Forces users to change their default password before accessing the app.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChangePasswordScreen(
    onSuccess: () -> Unit,
    onLogout: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var currentPassword by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var currentPasswordVisible by remember { mutableStateOf(false) }
    var newPasswordVisible by remember { mutableStateOf(false) }
    var confirmPasswordVisible by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Change Password") },
                actions = {
                    TextButton(onClick = onLogout) {
                        Text("Logout")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Security notice
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Text("🔐", style = MaterialTheme.typography.headlineSmall)
                    Column {
                        Text(
                            "Password Change Required",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                        )
                        Text(
                            "For security, you must change your default password before continuing.",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Error message
            errorMessage?.let { error ->
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("❌")
                        Text(
                            text = error,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
            }

            // Current password
            OutlinedTextField(
                value = currentPassword,
                onValueChange = {
                    currentPassword = it
                    errorMessage = null
                },
                label = { Text("Current Password") },
                placeholder = { Text("Enter your default password") },
                singleLine = true,
                visualTransformation = if (currentPasswordVisible)
                    androidx.compose.ui.text.input.VisualTransformation.None
                else
                    androidx.compose.ui.text.input.PasswordVisualTransformation(),
                trailingIcon = {
                    IconButton(onClick = { currentPasswordVisible = !currentPasswordVisible }) {
                        Text(if (currentPasswordVisible) "🙈" else "👁️")
                    }
                },
                modifier = Modifier.fillMaxWidth()
            )

            // New password
            OutlinedTextField(
                value = newPassword,
                onValueChange = {
                    newPassword = it
                    errorMessage = null
                },
                label = { Text("New Password") },
                placeholder = { Text("Minimum 8 characters") },
                singleLine = true,
                visualTransformation = if (newPasswordVisible)
                    androidx.compose.ui.text.input.VisualTransformation.None
                else
                    androidx.compose.ui.text.input.PasswordVisualTransformation(),
                trailingIcon = {
                    IconButton(onClick = { newPasswordVisible = !newPasswordVisible }) {
                        Text(if (newPasswordVisible) "🙈" else "👁️")
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                isError = newPassword.isNotEmpty() && newPassword.length < 8,
                supportingText = if (newPassword.isNotEmpty() && newPassword.length < 8) {
                    { Text("Password must be at least 8 characters") }
                } else null
            )

            // Confirm password
            OutlinedTextField(
                value = confirmPassword,
                onValueChange = {
                    confirmPassword = it
                    errorMessage = null
                },
                label = { Text("Confirm New Password") },
                placeholder = { Text("Re-enter new password") },
                singleLine = true,
                visualTransformation = if (confirmPasswordVisible)
                    androidx.compose.ui.text.input.VisualTransformation.None
                else
                    androidx.compose.ui.text.input.PasswordVisualTransformation(),
                trailingIcon = {
                    IconButton(onClick = { confirmPasswordVisible = !confirmPasswordVisible }) {
                        Text(if (confirmPasswordVisible) "🙈" else "👁️")
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                isError = confirmPassword.isNotEmpty() && confirmPassword != newPassword,
                supportingText = if (confirmPassword.isNotEmpty() && confirmPassword != newPassword) {
                    { Text("Passwords do not match") }
                } else null
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Submit button
            Button(
                onClick = {
                    // Validate
                    when {
                        currentPassword.isBlank() -> {
                            errorMessage = "Please enter your current password"
                            return@Button
                        }
                        newPassword.isBlank() -> {
                            errorMessage = "Please enter a new password"
                            return@Button
                        }
                        newPassword.length < 8 -> {
                            errorMessage = "Password must be at least 8 characters"
                            return@Button
                        }
                        newPassword != confirmPassword -> {
                            errorMessage = "Passwords do not match"
                            return@Button
                        }
                        currentPassword == newPassword -> {
                            errorMessage = "New password must be different from current password"
                            return@Button
                        }
                    }

                    isLoading = true
                    errorMessage = null

                    scope.launch {
                        try {
                            val token = AppPrefs.getAccessToken(context)
                            if (token == null) {
                                errorMessage = "Session expired. Please login again."
                                isLoading = false
                                return@launch
                            }

                            withContext(Dispatchers.IO) {
                                ApiService.changePassword(
                                    baseUrl = BuildConfig.API_BASE_URL,
                                    accessToken = token,
                                    currentPassword = currentPassword,
                                    newPassword = newPassword,
                                    confirmPassword = confirmPassword
                                )
                            }

                            // Update local user data to reflect password change
                            val user = AppPrefs.getUser(context)
                            if (user != null) {
                                AppPrefs.saveUser(context, user.copy(mustChangePassword = false))
                            }

                            isLoading = false
                            onSuccess()

                        } catch (e: ApiException) {
                            isLoading = false
                            errorMessage = e.message ?: "Failed to change password"
                        } catch (e: Exception) {
                            isLoading = false
                            errorMessage = "Connection error: ${e.message}"
                        }
                    }
                },
                enabled = !isLoading &&
                    currentPassword.isNotBlank() &&
                    newPassword.length >= 8 &&
                    confirmPassword == newPassword,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp)
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(24.dp),
                        color = MaterialTheme.colorScheme.onPrimary,
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Change Password & Continue")
                }
            }
        }
    }
}

/**
 * Placeholder screen for unimplemented portals.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlaceholderScreen(
    title: String,
    message: String,
    onLogout: () -> Unit
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title) },
                actions = {
                    TextButton(onClick = onLogout) {
                        Text("Logout")
                    }
                }
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentAlignment = Alignment.Center
        ) {
            Text(message)
        }
    }
}


package com.eduMatrix.ams.ui.auth

import android.content.pm.PackageManager
import android.os.Build
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.R
import com.eduMatrix.ams.data.api.ApiException
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.UserRole
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Login screen with multi-role support.
 * Supports Staff, Student, Parent, and Admin login.
 * Matches the web application design.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LoginScreen(
    onLoginSuccess: (UserRole) -> Unit,
    onMustChangePassword: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val focusManager = LocalFocusManager.current
    val scrollState = rememberScrollState()

    // Form state
    var username by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var passwordVisible by rememberSaveable { mutableStateOf(false) }
    var isLoading by rememberSaveable { mutableStateOf(false) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }

    // Note: Backend handles username lookup by:
    // 1. Email/phone (username field)
    // 2. Employee code (numeric, e.g., "1022")
    // 3. Student admission number
    // So we send the username as-is without modification

    // Check notification permission status
    val notificationPermissionGranted = if (Build.VERSION.SDK_INT >= 33) {
        ContextCompat.checkSelfPermission(
            context,
            android.Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED
    } else true

    // Auto-login check
    LaunchedEffect(Unit) {
        if (AppPrefs.isLoggedIn(context)) {
            val user = AppPrefs.getUser(context)
            if (user != null) {
                if (user.mustChangePassword) {
                    onMustChangePassword()
                } else {
                    onLoginSuccess(user.role)
                }
            }
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                brush = Brush.verticalGradient(
                    colors = listOf(MitPurple, MitPurpleDark),
                    startY = 400f
                )
            )
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(scrollState)
        ) {
            // White header with logos - with status bar padding
            Surface(
                modifier = Modifier
                    .fillMaxWidth(),
                color = Color.White
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .statusBarsPadding() // Avoid status bar overlap
                        .padding(horizontal = 16.dp, vertical = 16.dp)
                ) {
                    // Logos at top corners
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // MIT Logo (left)
                        Image(
                            painter = painterResource(id = R.drawable.mit_logo),
                            contentDescription = "MIT Logo",
                            modifier = Modifier.height(56.dp),
                            contentScale = ContentScale.Fit
                        )
                        // EduMatrix Logo (right)
                        Image(
                            painter = painterResource(id = R.drawable.edumatrix_logo),
                            contentDescription = "EduMatrix Logo",
                            modifier = Modifier.height(56.dp),
                            contentScale = ContentScale.Fit
                        )
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Welcome text section
                    Text(
                        text = "WELCOME TO",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 2.sp,
                        color = TextSecondaryLight
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    Text(
                        text = "MIT Art, Design and Technology University, Pune",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimaryLight
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Aurora gradient line
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(4.dp)
                            .clip(RoundedCornerShape(2.dp))
                            .background(
                                brush = Brush.horizontalGradient(
                                    colors = listOf(MitPurple, MitOrange, MitTeal, MitPurple)
                                )
                            )
                    )
                }
            }

            // Purple section with login form
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .background(
                        brush = Brush.verticalGradient(
                            colors = listOf(MitPurple, MitPurpleDark)
                        )
                    )
                    .padding(horizontal = 16.dp, vertical = 24.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // App title in purple section
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "EduMatrix AMS",
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                        color = Color.White
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Empowering Education with Smart Attendance.",
                        style = MaterialTheme.typography.bodyMedium,
                        fontStyle = FontStyle.Italic,
                        color = Color.White.copy(alpha = 0.85f),
                        textAlign = TextAlign.Center
                    )
                }

                Spacer(modifier = Modifier.height(8.dp))

                // White card for form fields
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
                    shape = RoundedCornerShape(16.dp)
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        // Error message
                        errorMessage?.let { error ->
                            Card(
                                colors = CardDefaults.cardColors(containerColor = StatusRedLight),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(12.dp),
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(
                                        imageVector = Icons.Outlined.Error,
                                        contentDescription = null,
                                        tint = StatusRed,
                                        modifier = Modifier.size(20.dp)
                                    )
                                    Text(
                                        text = error,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = StatusRed,
                                        modifier = Modifier.weight(1f)
                                    )
                                    IconButton(
                                        onClick = { errorMessage = null },
                                        modifier = Modifier.size(20.dp)
                                    ) {
                                        Icon(
                                            imageVector = Icons.Default.Close,
                                            contentDescription = "Dismiss",
                                            tint = StatusRed,
                                            modifier = Modifier.size(16.dp)
                                        )
                                    }
                                }
                            }
                        }

                        // Username field
                        OutlinedTextField(
                            value = username,
                            onValueChange = {
                                username = it
                                errorMessage = null
                            },
                            label = { Text("University ID / Email") },
                            placeholder = { Text("e.g. EMP1022") },
                            leadingIcon = {
                                Icon(
                                    imageVector = Icons.Outlined.Person,
                                    contentDescription = null,
                                    tint = MitPurple
                                )
                            },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(
                                keyboardType = KeyboardType.Email,
                                imeAction = ImeAction.Next
                            ),
                            keyboardActions = KeyboardActions(
                                onNext = { focusManager.moveFocus(FocusDirection.Down) }
                            ),
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedTextColor = TextPrimaryLight,
                                unfocusedTextColor = TextPrimaryLight,
                                focusedBorderColor = MitPurple,
                                unfocusedBorderColor = DividerLight,
                                cursorColor = MitPurple,
                                unfocusedContainerColor = SurfaceVariantLight,
                                focusedContainerColor = Color.White,
                                focusedLabelColor = MitPurple,
                                unfocusedLabelColor = TextSecondaryLight,
                                focusedPlaceholderColor = TextTertiaryLight,
                                unfocusedPlaceholderColor = TextTertiaryLight
                            )
                        )

                        // Password field
                        OutlinedTextField(
                            value = password,
                            onValueChange = {
                                password = it
                                errorMessage = null
                            },
                            label = { Text("Password") },
                            placeholder = { Text("••••••••") },
                            leadingIcon = {
                                Icon(
                                    imageVector = Icons.Outlined.Lock,
                                    contentDescription = null,
                                    tint = MitPurple
                                )
                            },
                            trailingIcon = {
                                IconButton(onClick = { passwordVisible = !passwordVisible }) {
                                    Icon(
                                        imageVector = if (passwordVisible)
                                            Icons.Outlined.VisibilityOff
                                        else
                                            Icons.Outlined.Visibility,
                                        contentDescription = if (passwordVisible) "Hide password" else "Show password",
                                        tint = TextSecondaryLight
                                    )
                                }
                            },
                            visualTransformation = if (passwordVisible)
                                VisualTransformation.None
                            else
                                PasswordVisualTransformation(),
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(
                                keyboardType = KeyboardType.Password,
                                imeAction = ImeAction.Done
                            ),
                            keyboardActions = KeyboardActions(
                                onDone = { focusManager.clearFocus() }
                            ),
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedTextColor = TextPrimaryLight,
                                unfocusedTextColor = TextPrimaryLight,
                                focusedBorderColor = MitPurple,
                                unfocusedBorderColor = DividerLight,
                                cursorColor = MitPurple,
                                unfocusedContainerColor = SurfaceVariantLight,
                                focusedContainerColor = Color.White,
                                focusedLabelColor = MitPurple,
                                unfocusedLabelColor = TextSecondaryLight,
                                focusedPlaceholderColor = TextTertiaryLight,
                                unfocusedPlaceholderColor = TextTertiaryLight
                            )
                        )

                        // Login button
                        Button(
                            onClick = {
                                if (username.isBlank() || password.isBlank()) {
                                    errorMessage = "Please enter both username and password"
                                    return@Button
                                }

                                isLoading = true
                                errorMessage = null

                                scope.launch {
                                    try {
                                        val deviceId = AppPrefs.getDeviceId(context)
                                        // Send username as-is - backend handles lookup by:
                                        // email, employee code, or admission number
                                        val result = withContext(Dispatchers.IO) {
                                            ApiService.login(
                                                baseUrl = BuildConfig.API_BASE_URL,
                                                username = username.trim(),
                                                password = password,
                                                deviceId = deviceId
                                            )
                                        }

                                        // Save tokens and user data
                                        AppPrefs.saveAccessToken(context, result.accessToken)
                                        AppPrefs.saveRefreshToken(context, result.refreshToken)
                                        AppPrefs.saveUser(context, result.user)

                                        isLoading = false

                                        // Navigate based on password change requirement
                                        if (result.user.mustChangePassword) {
                                            onMustChangePassword()
                                        } else {
                                            onLoginSuccess(result.user.role)
                                        }
                                    } catch (e: ApiException) {
                                        isLoading = false
                                        errorMessage = e.message ?: "Login failed"
                                    } catch (e: Exception) {
                                        isLoading = false
                                        errorMessage = "Connection error: ${e.message}"
                                    }
                                }
                            },
                            enabled = username.isNotBlank() && password.isNotBlank() && !isLoading,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(52.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MitPurple,
                                disabledContainerColor = MitPurple.copy(alpha = 0.5f)
                            ),
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            if (isLoading) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(24.dp),
                                    color = Color.White,
                                    strokeWidth = 2.dp
                                )
                            } else {
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = "Sign In to Dashboard",
                                        style = MaterialTheme.typography.labelLarge,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                    Icon(
                                        Icons.Default.ArrowForward,
                                        contentDescription = null,
                                        modifier = Modifier.size(18.dp)
                                    )
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.weight(1f))

                // Footer
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    if (!notificationPermissionGranted) {
                        Text(
                            text = "Enable notifications for alerts",
                            style = MaterialTheme.typography.bodySmall,
                            color = MitOrange
                        )
                    }
                    Text(
                        text = "© 2025 DataBae on Cloud 9.",
                        style = MaterialTheme.typography.bodySmall,
                        color = Color.White.copy(alpha = 0.7f)
                    )
                }
            }
        }
    }
}

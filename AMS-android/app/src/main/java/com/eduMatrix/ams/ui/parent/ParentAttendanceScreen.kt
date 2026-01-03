package com.eduMatrix.ams.ui.parent

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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

/**
 * Parent Attendance Screen showing detailed subject-wise attendance breakdown.
 * Matches the web app's attendance modal but as a full screen.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ParentAttendanceScreen(
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // State
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var dashboardData by remember { mutableStateOf<ParentDashboardData?>(null) }
    var refreshTrigger by rememberSaveable { mutableStateOf(0) }

    // Load data
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
            isLoading = false
        } catch (e: com.eduMatrix.ams.data.api.ApiException) {
            isLoading = false
            if (e.code == 401) {
                AppPrefs.clearAll(context)
                onBack()
            } else {
                errorMessage = e.message ?: "Failed to load attendance"
            }
        } catch (e: Exception) {
            isLoading = false
            errorMessage = e.message ?: "Failed to load attendance"
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "Subject Attendance",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold
                        )
                        dashboardData?.let { data ->
                            Text(
                                text = "${data.student.name} • ${data.student.className}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            imageVector = Icons.Default.ArrowBack,
                            contentDescription = "Back"
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
                    AttendanceContent(
                        data = dashboardData!!
                    )
                }
            }
        }
    }
}

/**
 * Attendance content with summary and subject breakdown.
 */
@Composable
private fun AttendanceContent(data: ParentDashboardData) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        contentPadding = PaddingValues(vertical = 16.dp)
    ) {
        // Overall Attendance Summary Card
        item {
            OverallAttendanceSummary(
                stats = data.stats,
                termGrant = data.termGrant
            )
        }

        // Subject-wise breakdown header
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Subject-wise Breakdown",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onBackground
                )
                Text(
                    text = "${data.subjects.size} subjects",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        // Subject cards
        items(data.subjects) { subject ->
            SubjectAttendanceCard(subject = subject)
        }

        // Bottom spacing
        item {
            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

/**
 * Overall attendance summary card with donut chart.
 */
@Composable
private fun OverallAttendanceSummary(
    stats: ParentAttendanceStats,
    termGrant: ParentTermGrantInfo?
) {
    val ringColor = if (stats.percentage >= 75) MitTeal else StatusRed

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column {
                    Text(
                        text = "OVERALL ATTENDANCE",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    // Large percentage display
                    Text(
                        text = "${stats.percentage.toInt()}%",
                        style = MaterialTheme.typography.displaySmall,
                        fontWeight = FontWeight.Bold,
                        color = ringColor
                    )

                    Text(
                        text = "${stats.attended} / ${stats.total} Lectures",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                // Circular progress
                Box(
                    modifier = Modifier.size(100.dp),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator(
                        progress = { (stats.percentage / 100f).toFloat().coerceIn(0f, 1f) },
                        modifier = Modifier.size(100.dp),
                        strokeWidth = 10.dp,
                        color = ringColor,
                        trackColor = ringColor.copy(alpha = 0.15f)
                    )
                    Icon(
                        imageVector = if (stats.isDefaulter) Icons.Filled.Warning else Icons.Filled.CheckCircle,
                        contentDescription = null,
                        tint = ringColor,
                        modifier = Modifier.size(32.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Status and term grant info
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Defaulter status
                Surface(
                    color = if (stats.isDefaulter) StatusRedLight else StatusGreenLight,
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        Icon(
                            imageVector = if (stats.isDefaulter) Icons.Filled.Warning else Icons.Filled.VerifiedUser,
                            contentDescription = null,
                            tint = if (stats.isDefaulter) StatusRed else StatusGreen,
                            modifier = Modifier.size(16.dp)
                        )
                        Text(
                            text = if (stats.isDefaulter) "Below 75%" else "Good Standing",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = if (stats.isDefaulter) StatusRed else StatusGreen
                        )
                    }
                }

                // Term grant status
                termGrant?.let { grant ->
                    val (bgColor, textColor, label) = when (grant.status.lowercase()) {
                        "granted" -> Triple(StatusGreenLight, StatusGreen, "Exam Eligible")
                        "provisional" -> Triple(StatusYellowLight, StatusYellow, "Provisional")
                        else -> Triple(StatusRedLight, StatusRed, "Detained")
                    }
                    Surface(
                        color = bgColor,
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Text(
                            text = label,
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = textColor,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
                        )
                    }
                }
            }
        }
    }
}

/**
 * Individual subject attendance card.
 */
@Composable
private fun SubjectAttendanceCard(subject: ParentSubjectAttendance) {
    val progressColor = if (subject.percentage >= 75) MitTeal else StatusRed

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(12.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Subject header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = subject.subject,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        text = subject.code,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                // Percentage badge
                Surface(
                    color = if (subject.percentage >= 75) StatusGreenLight else StatusRedLight,
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text(
                        text = "${subject.percentage.toInt()}%",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = progressColor,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                    )
                }
            }

            // Progress bar
            LinearProgressIndicator(
                progress = { (subject.percentage / 100f).toFloat().coerceIn(0f, 1f) },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(8.dp)
                    .clip(RoundedCornerShape(4.dp)),
                color = progressColor,
                trackColor = progressColor.copy(alpha = 0.15f)
            )

            // Stats row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                StatItem(
                    label = "Conducted",
                    value = "${subject.conducted}",
                    icon = Icons.Outlined.School
                )
                StatItem(
                    label = "Attended",
                    value = "${subject.attended}",
                    icon = Icons.Outlined.CheckCircle
                )
                StatItem(
                    label = "Missed",
                    value = "${subject.conducted - subject.attended}",
                    icon = Icons.Outlined.Cancel
                )
            }
        }
    }
}

/**
 * Small stat item with icon, label and value.
 */
@Composable
private fun StatItem(
    label: String,
    value: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(16.dp)
        )
        Column {
            Text(
                text = value,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

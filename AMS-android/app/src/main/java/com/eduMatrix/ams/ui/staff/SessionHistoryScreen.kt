package com.eduMatrix.ams.ui.staff

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
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
import com.eduMatrix.ams.data.models.SessionHistoryRecord
import com.eduMatrix.ams.ui.theme.accentPurple
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Session History screen - shows history of conducted sessions with attendance percentages.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SessionHistoryScreen(
    onViewSession: (scheduleId: String, date: String) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var isLoading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var history by remember { mutableStateOf<List<SessionHistoryRecord>>(emptyList()) }

    // Group history by date for display
    val groupedHistory = remember(history) {
        history.groupBy { it.dateDisplay }
    }

    // Stats
    val totalSessions = history.size
    val avgAttendance = if (history.isNotEmpty()) {
        history.map { it.percentage }.average().toInt()
    } else 0

    // Load session history
    fun loadHistory() {
        scope.launch {
            isLoading = true
            error = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                val records = withContext(Dispatchers.IO) {
                    ApiService.getSessionHistory(BuildConfig.API_BASE_URL, token, user.userId)
                }
                history = records
            } catch (e: Exception) {
                error = e.message ?: "Failed to load history"
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(Unit) {
        loadHistory()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Session History") }
            )
        }
    ) { padding ->
        when {
            isLoading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator(color = accentPurple())
                }
            }
            error != null -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            Icons.Default.Error,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.error,
                            modifier = Modifier.size(48.dp)
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(error ?: "Error", color = MaterialTheme.colorScheme.error)
                        Spacer(modifier = Modifier.height(16.dp))
                        Button(onClick = { loadHistory() }) {
                            Text("Retry")
                        }
                    }
                }
            }
            history.isEmpty() -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            Icons.Default.History,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(64.dp)
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(
                            "No sessions conducted yet",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
            else -> {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Summary stats card
                    item {
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(
                                containerColor = accentPurple().copy(alpha = 0.1f)
                            )
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(16.dp),
                                horizontalArrangement = Arrangement.SpaceEvenly
                            ) {
                                StatItem(
                                    value = totalSessions.toString(),
                                    label = "Sessions",
                                    icon = Icons.Default.School
                                )
                                StatItem(
                                    value = "$avgAttendance%",
                                    label = "Avg Attendance",
                                    icon = Icons.Default.TrendingUp
                                )
                            }
                        }
                    }

                    // Group by date
                    groupedHistory.forEach { (date, sessions) ->
                        item {
                            Text(
                                text = date,
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
                            )
                        }

                        items(sessions) { session ->
                            SessionHistoryCard(
                                session = session,
                                onClick = { onViewSession(session.scheduleId.toString(), session.dateIso) }
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * Stat item for summary card.
 */
@Composable
private fun StatItem(
    value: String,
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = accentPurple(),
            modifier = Modifier.size(24.dp)
        )
        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = value,
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = accentPurple()
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

/**
 * Card for displaying a session history record.
 */
@Composable
private fun SessionHistoryCard(
    session: SessionHistoryRecord,
    onClick: () -> Unit
) {
    val attendanceColor = when {
        session.percentage >= 75 -> Color(0xFF4CAF50)  // Green
        session.percentage >= 50 -> Color(0xFFFFC107)  // Amber
        else -> Color(0xFFF44336)  // Red
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Attendance percentage circle
            Box(
                modifier = Modifier
                    .size(56.dp)
                    .clip(CircleShape)
                    .background(attendanceColor.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = "${session.percentage}%",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = attendanceColor
                )
            }

            Spacer(modifier = Modifier.width(16.dp))

            // Session details
            Column(
                modifier = Modifier.weight(1f)
            ) {
                Text(
                    text = session.subject,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium
                )
                Text(
                    text = session.className,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = session.time,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Chevron
            Icon(
                Icons.Default.ChevronRight,
                contentDescription = "View details",
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

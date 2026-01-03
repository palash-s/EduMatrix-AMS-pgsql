package com.eduMatrix.ams.ui.notifications

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiException
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.Notification
import com.eduMatrix.ams.data.models.NotificationType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NotificationsScreen(
    title: String = "Notifications",
    onBack: (() -> Unit)? = null,
    onLogout: (() -> Unit)? = null
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()

    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var notifications by remember { mutableStateOf<List<Notification>>(emptyList()) }
    var refreshTrigger by rememberSaveable { mutableStateOf(0) }
    var showClearDialog by rememberSaveable { mutableStateOf(false) }
    var isClearing by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(refreshTrigger) {
        isLoading = true
        errorMessage = null
        try {
            val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
            val items = withContext(Dispatchers.IO) {
                ApiService.getNotifications(BuildConfig.API_BASE_URL, token)
            }
            notifications = items
        } catch (e: ApiException) {
            if (e.code == 401) {
                AppPrefs.clearAll(context)
                onLogout?.invoke()
            } else {
                errorMessage = e.message ?: "Failed to load notifications"
            }
        } catch (e: Exception) {
            errorMessage = e.message ?: "Failed to load notifications"
        } finally {
            isLoading = false
        }
    }

    // Confirmation dialog for clearing all notifications
    if (showClearDialog) {
        AlertDialog(
            onDismissRequest = { showClearDialog = false },
            title = { Text("Clear All Notifications") },
            text = { Text("Are you sure you want to delete all notifications? This action cannot be undone.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        showClearDialog = false
                        isClearing = true
                        scope.launch {
                            try {
                                val token = AppPrefs.getAccessToken(context) ?: return@launch
                                withContext(Dispatchers.IO) {
                                    ApiService.clearNotifications(BuildConfig.API_BASE_URL, token)
                                }
                                notifications = emptyList()
                            } catch (_: Exception) {
                                // Refresh to show actual state
                                refreshTrigger++
                            } finally {
                                isClearing = false
                            }
                        }
                    }
                ) {
                    Text("Clear All", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showClearDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title, fontWeight = FontWeight.SemiBold) },
                navigationIcon = {
                    if (onBack != null) {
                        IconButton(onClick = onBack) {
                            Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                        }
                    }
                },
                actions = {
                    if (notifications.isNotEmpty()) {
                        IconButton(
                            onClick = { showClearDialog = true },
                            enabled = !isClearing
                        ) {
                            Icon(Icons.Default.Delete, contentDescription = "Clear all")
                        }
                    }
                    IconButton(onClick = { refreshTrigger++ }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            when {
                isLoading -> {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                }

                errorMessage != null -> {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(24.dp)
                            .align(Alignment.Center),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(errorMessage!!, style = MaterialTheme.typography.bodyMedium)
                        Button(onClick = { refreshTrigger++ }) {
                            Text("Retry")
                        }
                    }
                }

                notifications.isEmpty() -> {
                    Text(
                        "No notifications",
                        modifier = Modifier.align(Alignment.Center),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                else -> {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .background(MaterialTheme.colorScheme.background),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        items(notifications, key = { it.id }) { n ->
                            NotificationRow(
                                notification = n,
                                onMarkRead = {
                                    if (!n.isRead) {
                                        scope.launch {
                                            try {
                                                val token = AppPrefs.getAccessToken(context) ?: return@launch
                                                withContext(Dispatchers.IO) {
                                                    ApiService.markNotificationRead(BuildConfig.API_BASE_URL, token, n.id)
                                                }
                                            } catch (_: Exception) {
                                                // best-effort
                                            } finally {
                                                refreshTrigger++
                                            }
                                        }
                                    }
                                }
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun NotificationRow(
    notification: Notification,
    onMarkRead: () -> Unit
) {
    val containerColor = if (notification.isRead) {
        MaterialTheme.colorScheme.surface
    } else {
        MaterialTheme.colorScheme.surfaceVariant
    }

    ElevatedCard(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onMarkRead() },
        colors = CardDefaults.elevatedCardColors(containerColor = containerColor),
        shape = RoundedCornerShape(16.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            TypeDot(type = notification.type, unread = !notification.isRead)

            Column(modifier = Modifier.weight(1f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.Top
                ) {
                    Text(
                        text = notification.title,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = if (notification.isRead) FontWeight.Medium else FontWeight.SemiBold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )

                    Spacer(modifier = Modifier.width(8.dp))

                    val ts = formatTimestamp(notification.timestamp)
                    if (ts.isNotBlank()) {
                        Text(
                            text = ts,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                Spacer(modifier = Modifier.height(6.dp))

                Text(
                    text = notification.message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }
    }
}

@Composable
private fun TypeDot(type: NotificationType, unread: Boolean) {
    val color = when (type) {
        NotificationType.SUCCESS -> MaterialTheme.colorScheme.primary
        NotificationType.WARNING -> MaterialTheme.colorScheme.tertiary
        NotificationType.DANGER -> MaterialTheme.colorScheme.error
        NotificationType.INFO -> MaterialTheme.colorScheme.secondary
    }

    Box(
        modifier = Modifier
            .size(12.dp)
            .clip(CircleShape)
            .background(if (unread) color else color.copy(alpha = 0.35f))
    )
}

private fun formatTimestamp(raw: String): String {
    val s = raw.trim()
    if (s.isBlank()) return ""

    // Backend returns ISO local datetime (no timezone). Keep it simple and stable:
    // 2026-01-02T10:20:30.123456 -> 2026-01-02 10:20
    return try {
        val date = s.substringBefore('T')
        val time = s.substringAfter('T', "").take(5)
        if (date.isNotBlank() && time.isNotBlank()) "$date $time" else s.take(16)
    } catch (_: Exception) {
        s.take(16)
    }
}

package com.eduMatrix.ams.ui.staff.hod

import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiException
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.*
import com.eduMatrix.ams.ui.components.EmptyState
import com.eduMatrix.ams.ui.components.LoadingOverlay
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * HOD Leave Approvals Screen.
 * Shows escalated leave requests that require HOD approval.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HodLeaveApprovalsScreen(
    onBack: () -> Unit = {}
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    // Loading states
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var isProcessing by rememberSaveable { mutableStateOf(false) }

    // Data
    var deptName by rememberSaveable { mutableStateOf("") }
    var stats by remember { mutableStateOf<HodStats?>(null) }
    var approvals by remember { mutableStateOf<List<HodLeaveApproval>>(emptyList()) }

    // Dialog state
    var showActionDialog by rememberSaveable { mutableStateOf(false) }
    var selectedLeave by remember { mutableStateOf<HodLeaveApproval?>(null) }
    var actionType by rememberSaveable { mutableStateOf<String?>(null) } // "Approved" or "Rejected"
    var actionRemarks by rememberSaveable { mutableStateOf("") }

    // Load HOD dashboard data
    fun loadDashboard() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                val response = withContext(Dispatchers.IO) {
                    ApiService.getHodDashboard(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        userId = user.userId
                    )
                }

                deptName = response.deptName
                stats = response.stats
                approvals = response.approvals
            } catch (e: ApiException) {
                errorMessage = e.message ?: "Failed to load HOD dashboard"
            } catch (e: Exception) {
                errorMessage = "Connection error: ${e.message}"
            } finally {
                isLoading = false
            }
        }
    }

    // Perform leave action (approve/reject)
    fun performAction() {
        val leave = selectedLeave ?: return
        val action = actionType ?: return

        scope.launch {
            isProcessing = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                val message = withContext(Dispatchers.IO) {
                    ApiService.hodApproveLeave(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        leaveId = leave.leaveId,
                        action = action,
                        hodId = user.userId,
                        remarks = actionRemarks.ifBlank { null }
                    )
                }

                snackbarHostState.showSnackbar(message)

                // Refresh data
                loadDashboard()

                // Reset dialog state
                showActionDialog = false
                selectedLeave = null
                actionType = null
                actionRemarks = ""
            } catch (e: ApiException) {
                snackbarHostState.showSnackbar(e.message ?: "Action failed")
            } catch (e: Exception) {
                snackbarHostState.showSnackbar("Error: ${e.message}")
            } finally {
                isProcessing = false
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
                        Text("HOD Leave Approvals")
                        if (deptName.isNotBlank()) {
                            Text(
                                text = deptName,
                                style = MaterialTheme.typography.bodySmall,
                                color = Color.White.copy(alpha = 0.8f)
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = primaryAccent(),
                    titleContentColor = Color.White,
                    navigationIconContentColor = Color.White
                ),
                actions = {
                    IconButton(onClick = { loadDashboard() }) {
                        Icon(
                            Icons.Default.Refresh,
                            contentDescription = "Refresh",
                            tint = Color.White
                        )
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { paddingValues ->
        when {
            isLoading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        CircularProgressIndicator(color = accentPurple())
                        Text(
                            text = "Loading escalated leaves...",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }

            errorMessage != null -> {
                EmptyState(
                    icon = Icons.Outlined.Error,
                    title = "Error Loading Data",
                    message = errorMessage ?: "Unknown error occurred",
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                ) {
                    Button(
                        onClick = { loadDashboard() },
                        colors = ButtonDefaults.buttonColors(containerColor = primaryAccent())
                    ) {
                        Icon(Icons.Default.Refresh, contentDescription = null)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Retry")
                    }
                }
            }

            approvals.isEmpty() -> {
                EmptyState(
                    icon = Icons.Outlined.EventBusy,
                    title = "No Pending Approvals",
                    message = "There are no escalated leave requests requiring your approval.",
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                )
            }

            else -> {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                        .background(MaterialTheme.colorScheme.background),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Stats summary
                    item {
                        stats?.let { HodStatsSummary(stats = it) }
                    }

                    // Info card
                    item {
                        HodInfoCard()
                    }

                    // Leave approval cards
                    items(approvals, key = { it.leaveId }) { leave ->
                        HodLeaveCard(
                            leave = leave,
                            onApprove = {
                                selectedLeave = leave
                                actionType = "Approved"
                                showActionDialog = true
                            },
                            onReject = {
                                selectedLeave = leave
                                actionType = "Rejected"
                                showActionDialog = true
                            }
                        )
                    }

                    item {
                        Spacer(modifier = Modifier.height(16.dp))
                    }
                }
            }
        }
    }

    // Action confirmation dialog
    if (showActionDialog && selectedLeave != null) {
        val isApprove = actionType == "Approved"

        AlertDialog(
            onDismissRequest = {
                if (!isProcessing) {
                    showActionDialog = false
                    selectedLeave = null
                    actionType = null
                    actionRemarks = ""
                }
            },
            icon = {
                Icon(
                    imageVector = if (isApprove) Icons.Default.CheckCircle else Icons.Default.Cancel,
                    contentDescription = null,
                    tint = if (isApprove) StatusGreen else StatusRed
                )
            },
            title = {
                Text(if (isApprove) "Approve Leave Request" else "Reject Leave Request")
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text(
                        text = "You are about to ${if (isApprove) "approve" else "reject"} the escalated leave request from:"
                    )

                    // Leave details card
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                    ) {
                        Column(
                            modifier = Modifier.padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            Text(
                                text = selectedLeave!!.student,
                                fontWeight = FontWeight.SemiBold
                            )
                            Text(
                                text = "${selectedLeave!!.roll} | ${selectedLeave!!.className}",
                                style = MaterialTheme.typography.bodySmall
                            )
                            Text(
                                text = "${selectedLeave!!.days.toInt()} day(s)",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }

                    // Warning about escalated leaves
                    Surface(
                        color = StatusYellow.copy(alpha = 0.1f),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                Icons.Default.Info,
                                contentDescription = null,
                                tint = StatusYellow,
                                modifier = Modifier.size(20.dp)
                            )
                            Text(
                                text = "This leave was escalated and requires HOD approval.",
                                style = MaterialTheme.typography.bodySmall,
                                color = StatusYellow
                            )
                        }
                    }

                    // Remarks input
                    OutlinedTextField(
                        value = actionRemarks,
                        onValueChange = { actionRemarks = it },
                        label = { Text("Remarks (optional)") },
                        placeholder = { Text("Add any comments...") },
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 2,
                        maxLines = 4,
                        shape = RoundedCornerShape(12.dp)
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = { performAction() },
                    enabled = !isProcessing,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isApprove) StatusGreen else StatusRed
                    )
                ) {
                    if (isProcessing) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = Color.White,
                            strokeWidth = 2.dp
                        )
                    } else {
                        Text(if (isApprove) "Approve" else "Reject")
                    }
                }
            },
            dismissButton = {
                TextButton(
                    onClick = {
                        showActionDialog = false
                        selectedLeave = null
                        actionType = null
                        actionRemarks = ""
                    },
                    enabled = !isProcessing
                ) {
                    Text("Cancel")
                }
            }
        )
    }

    // Loading overlay
    LoadingOverlay(
        isLoading = isProcessing,
        message = "Processing..."
    )
}

/**
 * HOD stats summary card.
 */
@Composable
private fun HodStatsSummary(stats: HodStats) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            StatItem(
                label = "Students",
                count = stats.students,
                color = primaryAccent()
            )
            StatItem(
                label = "Faculty",
                count = stats.faculty,
                color = accentPurple()
            )
            StatItem(
                label = "Attendance",
                value = "${stats.attendance.toInt()}%",
                color = StatusGreen
            )
            StatItem(
                label = "Pending",
                count = stats.pending,
                color = StatusYellow
            )
        }
    }
}

@Composable
private fun StatItem(
    label: String,
    count: Int? = null,
    value: String? = null,
    color: Color
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = value ?: "$count",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = color
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

/**
 * Info card explaining HOD leave approval.
 */
@Composable
private fun HodInfoCard() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = accentPurple().copy(alpha = 0.1f)
        ),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.Top
        ) {
            Icon(
                Icons.Outlined.Info,
                contentDescription = null,
                tint = accentPurple(),
                modifier = Modifier.size(24.dp)
            )
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    text = "Escalated Leave Approvals",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = accentPurple()
                )
                Text(
                    text = "These leave requests were escalated by class teachers and require HOD approval. Review each request carefully before making a decision.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/**
 * Individual HOD leave approval card.
 */
@Composable
private fun HodLeaveCard(
    leave: HodLeaveApproval,
    onApprove: () -> Unit,
    onReject: () -> Unit
) {
    val isDark = isSystemInDarkTheme()
    val bgAlpha = if (isDark) 0.2f else 0.1f

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Header row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Avatar
                    Box(
                        modifier = Modifier
                            .size(44.dp)
                            .clip(CircleShape)
                            .background(primaryAccent().copy(alpha = bgAlpha)),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = leave.student.take(1).uppercase(),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = primaryAccent()
                        )
                    }
                    Column {
                        Text(
                            text = leave.student,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            text = "${leave.roll} | ${leave.className}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                // Escalated badge
                Surface(
                    color = StatusYellow.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.KeyboardArrowUp,
                            contentDescription = null,
                            tint = StatusYellow,
                            modifier = Modifier.size(14.dp)
                        )
                        Text(
                            text = "Escalated",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Medium,
                            color = StatusYellow
                        )
                    }
                }
            }

            // Leave details
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = "Date",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = leave.date,
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = "Days",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = if (leave.days == leave.days.toInt().toDouble()) {
                            "${leave.days.toInt()}"
                        } else {
                            "${leave.days}"
                        },
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = accentPurple()
                    )
                }
            }

            // Reason
            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
                shape = RoundedCornerShape(8.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Text(
                        text = "Reason",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = leave.reason,
                        style = MaterialTheme.typography.bodyMedium,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }

            // Action buttons
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedButton(
                    onClick = onReject,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = StatusRed),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Icon(
                        Icons.Default.Close,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Reject")
                }
                Button(
                    onClick = onApprove,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = StatusGreen),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Icon(
                        Icons.Default.Check,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Approve")
                }
            }
        }
    }
}

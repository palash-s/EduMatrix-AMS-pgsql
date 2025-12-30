package com.eduMatrix.ams.ui.staff.leaves

import androidx.compose.foundation.background
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
import com.eduMatrix.ams.ui.components.*
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Leave approvals screen for staff (Class Teacher/Mentor).
 * Shows pending leave requests and allows approve/reject actions.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StaffLeaveApprovalsScreen(
    onViewDetails: (leaveId: Int) -> Unit = {}
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    // Loading states
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }

    // Data
    var leaveRequests by remember { mutableStateOf<List<LeaveRequest>>(emptyList()) }

    // Filter state
    var selectedFilter by rememberSaveable { mutableStateOf("Pending") }
    val filterOptions = listOf("All", "Pending", "Approved", "Rejected")

    // Dialog states
    var showActionDialog by rememberSaveable { mutableStateOf(false) }
    var selectedLeave by remember { mutableStateOf<LeaveRequest?>(null) }
    var actionType by rememberSaveable { mutableStateOf<LeaveActionType?>(null) }
    var actionRemarks by rememberSaveable { mutableStateOf("") }
    var isProcessing by rememberSaveable { mutableStateOf(false) }

    // Load leave requests
    fun loadLeaveRequests() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val requests = withContext(Dispatchers.IO) {
                    ApiService.getLeaveRequests(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token
                    )
                }
                leaveRequests = requests
            } catch (e: ApiException) {
                errorMessage = e.message ?: "Failed to load leave requests"
            } catch (e: Exception) {
                errorMessage = "Connection error: ${e.message}"
            } finally {
                isLoading = false
            }
        }
    }

    // Initial load
    LaunchedEffect(Unit) {
        loadLeaveRequests()
    }

    // Perform leave action
    fun performAction() {
        if (selectedLeave == null || actionType == null) return

        scope.launch {
            isProcessing = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val action = LeaveAction(
                    leaveId = selectedLeave!!.leaveId,
                    action = actionType!!,
                    remarks = actionRemarks.ifBlank { null }
                )

                withContext(Dispatchers.IO) {
                    ApiService.performLeaveAction(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        action = action
                    )
                }

                val actionText = when (actionType) {
                    LeaveActionType.APPROVE -> "approved"
                    LeaveActionType.REJECT -> "rejected"
                    LeaveActionType.ESCALATE -> "escalated"
                    else -> "processed"
                }
                snackbarHostState.showSnackbar("Leave request $actionText successfully")

                // Refresh list
                loadLeaveRequests()

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

    // Filter requests
    val filteredRequests = remember(leaveRequests, selectedFilter) {
        when (selectedFilter) {
            "Pending" -> leaveRequests.filter { it.status == LeaveStatus.PENDING }
            "Approved" -> leaveRequests.filter { it.status == LeaveStatus.APPROVED }
            "Rejected" -> leaveRequests.filter { it.status == LeaveStatus.REJECTED }
            else -> leaveRequests
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "Leave Approvals",
                        style = MaterialTheme.typography.titleLarge
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MitPurple,
                    titleContentColor = Color.White
                ),
                actions = {
                    IconButton(onClick = { loadLeaveRequests() }) {
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
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .background(AppBackgroundLight)
        ) {
            // Filter tabs
            ScrollableTabRow(
                selectedTabIndex = filterOptions.indexOf(selectedFilter),
                containerColor = MaterialTheme.colorScheme.surface,
                contentColor = accentPurple(),
                edgePadding = 16.dp
            ) {
                filterOptions.forEach { filter ->
                    Tab(
                        selected = selectedFilter == filter,
                        onClick = { selectedFilter = filter },
                        text = {
                            Text(
                                text = filter,
                                fontWeight = if (selectedFilter == filter)
                                    FontWeight.SemiBold
                                else
                                    FontWeight.Normal,
                                color = if (selectedFilter == filter)
                                    accentPurple()
                                else
                                    MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    )
                }
            }

            when {
                isLoading -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(16.dp)
                        ) {
                            CircularProgressIndicator(color = accentPurple())
                            Text(
                                text = "Loading leave requests...",
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
                        modifier = Modifier.fillMaxSize()
                    ) {
                        Button(
                            onClick = { loadLeaveRequests() },
                            colors = ButtonDefaults.buttonColors(containerColor = MitPurple)
                        ) {
                            Icon(Icons.Default.Refresh, contentDescription = null)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Retry")
                        }
                    }
                }

                filteredRequests.isEmpty() -> {
                    EmptyState(
                        icon = Icons.Outlined.EventBusy,
                        title = "No Leave Requests",
                        message = when (selectedFilter) {
                            "Pending" -> "No pending leave requests to review"
                            "Approved" -> "No approved leave requests"
                            "Rejected" -> "No rejected leave requests"
                            else -> "No leave requests found"
                        },
                        modifier = Modifier.fillMaxSize()
                    )
                }

                else -> {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        // Stats summary
                        item {
                            LeaveStatsSummary(
                                pending = leaveRequests.count { it.status == LeaveStatus.PENDING },
                                approved = leaveRequests.count { it.status == LeaveStatus.APPROVED },
                                rejected = leaveRequests.count { it.status == LeaveStatus.REJECTED }
                            )
                        }

                        items(
                            items = filteredRequests,
                            key = { it.leaveId }
                        ) { request ->
                            LeaveRequestCard(
                                request = request,
                                onApprove = {
                                    selectedLeave = request
                                    actionType = LeaveActionType.APPROVE
                                    showActionDialog = true
                                },
                                onReject = {
                                    selectedLeave = request
                                    actionType = LeaveActionType.REJECT
                                    showActionDialog = true
                                },
                                onViewDetails = { onViewDetails(request.leaveId) }
                            )
                        }

                        item {
                            Spacer(modifier = Modifier.height(16.dp))
                        }
                    }
                }
            }
        }
    }

    // Action confirmation dialog
    if (showActionDialog && selectedLeave != null) {
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
                    imageVector = if (actionType == LeaveActionType.APPROVE)
                        Icons.Default.CheckCircle
                    else
                        Icons.Default.Cancel,
                    contentDescription = null,
                    tint = if (actionType == LeaveActionType.APPROVE) StatusGreen else StatusRed
                )
            },
            title = {
                Text(
                    text = if (actionType == LeaveActionType.APPROVE)
                        "Approve Leave Request"
                    else
                        "Reject Leave Request"
                )
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text(
                        text = "You are about to ${if (actionType == LeaveActionType.APPROVE) "approve" else "reject"} the leave request from:"
                    )
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
                                text = selectedLeave!!.applicantName,
                                fontWeight = FontWeight.SemiBold
                            )
                            Text(
                                text = "${selectedLeave!!.startDate} to ${selectedLeave!!.endDate}",
                                style = MaterialTheme.typography.bodySmall
                            )
                            Text(
                                text = "${selectedLeave!!.totalDays.toInt()} day(s) - ${selectedLeave!!.leaveType.toDisplayString()}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }

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
                        containerColor = if (actionType == LeaveActionType.APPROVE)
                            StatusGreen
                        else
                            StatusRed
                    )
                ) {
                    if (isProcessing) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = Color.White,
                            strokeWidth = 2.dp
                        )
                    } else {
                        Text(
                            if (actionType == LeaveActionType.APPROVE) "Approve" else "Reject"
                        )
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
 * Leave stats summary card.
 */
@Composable
private fun LeaveStatsSummary(
    pending: Int,
    approved: Int,
    rejected: Int
) {
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
                label = "Pending",
                count = pending,
                color = StatusYellow
            )
            StatItem(
                label = "Approved",
                count = approved,
                color = StatusGreen
            )
            StatItem(
                label = "Rejected",
                count = rejected,
                color = StatusRed
            )
        }
    }
}

@Composable
private fun StatItem(
    label: String,
    count: Int,
    color: Color
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = "$count",
            style = MaterialTheme.typography.headlineMedium,
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
 * Individual leave request card.
 */
@Composable
private fun LeaveRequestCard(
    request: LeaveRequest,
    onApprove: () -> Unit,
    onReject: () -> Unit,
    onViewDetails: () -> Unit
) {
    val statusColor = when (request.status) {
        LeaveStatus.PENDING -> StatusYellow
        LeaveStatus.APPROVED -> StatusGreen
        LeaveStatus.REJECTED -> StatusRed
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
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
                            .background(MitPurple.copy(alpha = 0.1f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = request.applicantName.take(1).uppercase(),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = accentPurple()
                        )
                    }
                    Column {
                        Text(
                            text = request.applicantName,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        if (!request.applicantClass.isNullOrBlank()) {
                            Text(
                                text = request.applicantClass,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }

                // Status badge
                Surface(
                    color = statusColor.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = request.status.name.lowercase().replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Medium,
                        color = statusColor,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            // Leave type chip
            Surface(
                color = MitTeal.copy(alpha = 0.1f),
                shape = RoundedCornerShape(4.dp)
            ) {
                Text(
                    text = request.leaveType.toDisplayString(),
                    style = MaterialTheme.typography.labelSmall,
                    color = MitTeal,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                )
            }

            // Duration info
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text(
                        text = "Duration",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "${request.startDate} → ${request.endDate}",
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
                        text = "${request.totalDays.toInt()}",
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold
                    )
                }
            }

            // Reason
            Text(
                text = request.reason,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )

            // Actions (only for pending)
            if (request.status == LeaveStatus.PENDING) {
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

            // Applied on
            Text(
                text = "Applied on: ${request.appliedOn}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
            )
        }
    }
}

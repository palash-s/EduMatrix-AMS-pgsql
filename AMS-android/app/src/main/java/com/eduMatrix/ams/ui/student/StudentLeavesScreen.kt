package com.eduMatrix.ams.ui.student

import android.app.DatePickerDialog
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.LeaveApplication
import com.eduMatrix.ams.data.models.StudentLeaveRequest
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*

/**
 * Student Leaves Screen
 * Shows leave history and allows applying for new leaves
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StudentLeavesScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var leavesResponse by remember { mutableStateOf<ApiService.StudentLeavesResponse?>(null) }
    var showApplyDialog by rememberSaveable { mutableStateOf(false) }
    var refreshTrigger by rememberSaveable { mutableStateOf(0) }

    // Load leaves
    LaunchedEffect(refreshTrigger) {
        isLoading = true
        errorMessage = null
        try {
            val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")

            leavesResponse = withContext(Dispatchers.IO) {
                ApiService.getStudentLeaves(BuildConfig.API_BASE_URL, token)
            }
        } catch (e: Exception) {
            errorMessage = e.message ?: "Failed to load leaves"
        } finally {
            isLoading = false
        }
    }

    val leaves = leavesResponse?.history ?: emptyList()
    val balance = leavesResponse?.balance

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("My Leaves") }
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showApplyDialog = true },
                containerColor = accentPurple(),
                contentColor = Color.White
            ) {
                Icon(Icons.Default.Add, contentDescription = null)
                Spacer(modifier = Modifier.width(8.dp))
                Text("Apply Leave")
            }
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
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
            errorMessage != null -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            imageVector = Icons.Outlined.ErrorOutline,
                            contentDescription = null,
                            modifier = Modifier.size(64.dp),
                            tint = MaterialTheme.colorScheme.error
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(errorMessage ?: "Error", textAlign = TextAlign.Center)
                        Spacer(modifier = Modifier.height(16.dp))
                        Button(onClick = { refreshTrigger++ }) {
                            Text("Retry")
                        }
                    }
                }
            }
            leaves.isEmpty() -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.padding(32.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.EventBusy,
                            contentDescription = null,
                            modifier = Modifier.size(64.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(
                            text = "No leave requests",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "Tap + to apply for leave",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
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
                    // Leave Balance Card
                    balance?.let { bal ->
                        item {
                            LeaveBalanceCard(balance = bal)
                        }
                    }

                    // Leave History Header
                    if (leaves.isNotEmpty()) {
                        item {
                            Text(
                                text = "Leave History",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
                            )
                        }
                    }

                    items(leaves) { leave ->
                        LeaveCard(leave = leave)
                    }
                    item {
                        Spacer(modifier = Modifier.height(72.dp))
                    }
                }
            }
        }
    }

    // Apply Leave Dialog
    if (showApplyDialog) {
        ApplyLeaveDialog(
            onDismiss = { showApplyDialog = false },
            onSubmit = { startDate, endDate, reason, category ->
                scope.launch {
                    try {
                        val token = AppPrefs.getAccessToken(context) ?: return@launch

                        withContext(Dispatchers.IO) {
                            ApiService.applyLeave(
                                BuildConfig.API_BASE_URL,
                                token,
                                LeaveApplication(
                                    startDate = startDate,
                                    endDate = endDate,
                                    reason = reason,
                                    category = category,
                                    documentUrl = null
                                )
                            )
                        }
                        showApplyDialog = false
                        refreshTrigger++
                        snackbarHostState.showSnackbar("Leave application submitted")
                    } catch (e: Exception) {
                        snackbarHostState.showSnackbar("Error: ${e.message}")
                    }
                }
            },
            blockedDates = leavesResponse?.blockedDates ?: emptyList(),
            remainingBalance = balance?.remaining ?: 20
        )
    }
}

@Composable
private fun LeaveCard(leave: StudentLeaveRequest) {
    val statusColor = when (leave.status.lowercase()) {
        "approved" -> StatusGreen
        "rejected" -> StatusRed
        else ->     StatusYellow
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "${leave.startDate} - ${leave.endDate}",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold
                    )
                    Text(
                        text = leave.category,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = statusColor.copy(alpha = 0.1f)
                ) {
                    Text(
                        text = leave.status,
                        style = MaterialTheme.typography.labelMedium,
                        color = statusColor,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            Text(
                text = leave.reason,
                style = MaterialTheme.typography.bodyMedium
            )

            leave.remarks?.let { remarks ->
                Spacer(modifier = Modifier.height(8.dp))
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant
                ) {
                    Text(
                        text = "Remarks: $remarks",
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(8.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = leave.appliedOn,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun LeaveBalanceCard(balance: ApiService.LeaveBalance) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
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
            BalanceItem(
                value = balance.total.toString(),
                label = "Total",
                color = MaterialTheme.colorScheme.onSurface
            )
            BalanceItem(
                value = balance.used.toString(),
                label = "Used",
                color = StatusYellow
            )
            BalanceItem(
                value = balance.remaining.toString(),
                label = "Remaining",
                color = StatusGreen
            )
        }
    }
}

@Composable
private fun BalanceItem(value: String, label: String, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ApplyLeaveDialog(
    onDismiss: () -> Unit,
    onSubmit: (startDate: String, endDate: String, reason: String, category: String) -> Unit,
    blockedDates: List<String>,
    remainingBalance: Int
) {
    val context = LocalContext.current

    var startDate by rememberSaveable { mutableStateOf("") }
    var endDate by rememberSaveable { mutableStateOf("") }
    var reason by rememberSaveable { mutableStateOf("") }
    var category by rememberSaveable { mutableStateOf("Casual") }
    var isSubmitting by rememberSaveable { mutableStateOf(false) }
    var categoryExpanded by rememberSaveable { mutableStateOf(false) }
    var validationError by rememberSaveable { mutableStateOf<String?>(null) }

    // Leave categories matching web app
    val categories = listOf(
        "Casual" to "Casual Leave (Personal)",
        "Sick" to "Medical / Sick Leave",
        "Event" to "Event / On Duty (OD)"
    )
    val calendar = Calendar.getInstance()
    val dateFormat = SimpleDateFormat("yyyy-MM-dd", Locale.US)

    // Calculate total days and validate
    val totalDays = remember(startDate, endDate) {
        if (startDate.isNotBlank() && endDate.isNotBlank()) {
            try {
                val start = java.time.LocalDate.parse(startDate)
                val end = java.time.LocalDate.parse(endDate)
                if (end >= start) {
                    java.time.temporal.ChronoUnit.DAYS.between(start, end).toInt() + 1
                } else 0
            } catch (e: Exception) { 0 }
        } else 0
    }

    // Check for overlapping dates
    val hasOverlap = remember(startDate, endDate, blockedDates) {
        if (startDate.isNotBlank() && endDate.isNotBlank()) {
            try {
                val start = java.time.LocalDate.parse(startDate)
                val end = java.time.LocalDate.parse(endDate)
                var current = start
                while (!current.isAfter(end)) {
                    if (blockedDates.contains(current.toString())) {
                        return@remember true
                    }
                    current = current.plusDays(1)
                }
                false
            } catch (e: Exception) { false }
        } else false
    }

    // Check if end date is before start date
    val isDateOrderInvalid = remember(startDate, endDate) {
        if (startDate.isNotBlank() && endDate.isNotBlank()) {
            try {
                val start = java.time.LocalDate.parse(startDate)
                val end = java.time.LocalDate.parse(endDate)
                end < start
            } catch (e: Exception) { false }
        } else false
    }

    // Check if exceeds balance
    val exceedsBalance = totalDays > remainingBalance

    // Requires HOD approval (> 15 days)
    val requiresHodApproval = totalDays > 15

    // Determine validation error message
    LaunchedEffect(startDate, endDate) {
        validationError = when {
            isDateOrderInvalid -> "End date cannot be before start date"
            hasOverlap -> "Selected dates overlap with an existing leave"
            exceedsBalance -> "Insufficient balance (Max: $remainingBalance days)"
            else -> null
        }
    }

    val isFormValid = startDate.isNotBlank() &&
        endDate.isNotBlank() &&
        reason.isNotBlank() &&
        !isDateOrderInvalid &&
        !hasOverlap &&
        !exceedsBalance &&
        totalDays > 0

    fun showDatePicker(isStart: Boolean) {
        DatePickerDialog(
            context,
            { _, year, month, dayOfMonth ->
                calendar.set(year, month, dayOfMonth)
                val formatted = dateFormat.format(calendar.time)
                if (isStart) startDate = formatted else endDate = formatted
            },
            calendar.get(Calendar.YEAR),
            calendar.get(Calendar.MONTH),
            calendar.get(Calendar.DAY_OF_MONTH)
        ).show()
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.92f)
                .wrapContentHeight(),
            shape = RoundedCornerShape(24.dp)
        ) {
            Column(
                modifier = Modifier
                    .padding(24.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Apply for Leave",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close")
                    }
                }

                Spacer(modifier = Modifier.height(20.dp))

                // Validation error message
                validationError?.let { error ->
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = StatusRed.copy(alpha = 0.1f)
                        ),
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
                                imageVector = Icons.Default.Error,
                                contentDescription = null,
                                tint = StatusRed,
                                modifier = Modifier.size(20.dp)
                            )
                            Text(
                                text = error,
                                style = MaterialTheme.typography.bodySmall,
                                color = StatusRed
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                }

                // Category dropdown
                ExposedDropdownMenuBox(
                    expanded = categoryExpanded,
                    onExpandedChange = { categoryExpanded = it }
                ) {
                    OutlinedTextField(
                        value = categories.find { it.first == category }?.second ?: category,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Leave Type") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = categoryExpanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        shape = RoundedCornerShape(12.dp)
                    )
                    ExposedDropdownMenu(
                        expanded = categoryExpanded,
                        onDismissRequest = { categoryExpanded = false }
                    ) {
                        categories.forEach { (code, label) ->
                            DropdownMenuItem(
                                text = { Text(label) },
                                onClick = {
                                    category = code
                                    categoryExpanded = false
                                }
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Date fields
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    OutlinedTextField(
                        value = startDate,
                        onValueChange = {},
                        label = { Text("Start Date") },
                        placeholder = { Text("Select") },
                        readOnly = true,
                        singleLine = true,
                        trailingIcon = {
                            IconButton(onClick = { showDatePicker(true) }) {
                                Icon(Icons.Default.CalendarMonth, contentDescription = "Pick date")
                            }
                        },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)
                    )
                    OutlinedTextField(
                        value = endDate,
                        onValueChange = {},
                        label = { Text("End Date") },
                        placeholder = { Text("Select") },
                        readOnly = true,
                        singleLine = true,
                        trailingIcon = {
                            IconButton(onClick = { showDatePicker(false) }) {
                                Icon(Icons.Default.CalendarMonth, contentDescription = "Pick date")
                            }
                        },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)
                    )
                }

                // Duration and HOD notice
                if (totalDays > 0) {
                    Spacer(modifier = Modifier.height(12.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Duration badge
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = accentPurple().copy(alpha = 0.1f)
                        ) {
                            Text(
                                text = "$totalDays day${if (totalDays > 1) "s" else ""}",
                                style = MaterialTheme.typography.labelMedium,
                                color = accentPurple(),
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                            )
                        }

                        // HOD approval notice
                        if (requiresHodApproval) {
                            Surface(
                                shape = RoundedCornerShape(8.dp),
                                color = StatusYellow.copy(alpha = 0.1f)
                            ) {
                                Row(
                                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.Warning,
                                        contentDescription = null,
                                        tint = StatusYellow,
                                        modifier = Modifier.size(14.dp)
                                    )
                                    Text(
                                        text = "Requires HOD Approval",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = StatusYellow,
                                        fontWeight = FontWeight.Medium
                                    )
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Reason
                OutlinedTextField(
                    value = reason,
                    onValueChange = { reason = it },
                    label = { Text("Reason") },
                    placeholder = { Text("Enter reason for leave") },
                    minLines = 3,
                    maxLines = 5,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp)
                )

                Spacer(modifier = Modifier.height(24.dp))

                // Buttons
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = onDismiss, enabled = !isSubmitting) {
                        Text("Cancel")
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            isSubmitting = true
                            onSubmit(startDate, endDate, reason, category)
                        },
                        enabled = !isSubmitting && isFormValid,
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = accentPurple())
                    ) {
                        if (isSubmitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.dp,
                                color = Color.White
                            )
                        } else {
                            Text("Submit")
                        }
                    }
                }
            }
        }
    }
}

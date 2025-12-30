package com.eduMatrix.ams.ui.staff

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.*
import com.eduMatrix.ams.ui.theme.accentPurple
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Upcoming Schedule screen - shows today's classes and upcoming sessions with adjustment capability.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UpcomingScheduleScreen(
    onMarkAttendance: (scheduleId: Int, date: String) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var isLoading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var todaySchedule by remember { mutableStateOf<List<UpcomingClass>>(emptyList()) }
    var upcomingSchedule by remember { mutableStateOf<List<UpcomingClass>>(emptyList()) }

    // Day filter for upcoming schedule
    val availableDays = remember(upcomingSchedule) {
        upcomingSchedule.map { it.day }.distinct()
    }
    var selectedDay by remember { mutableStateOf<String?>(null) }

    // Adjustment modal state
    var showAdjustmentModal by remember { mutableStateOf(false) }
    var selectedClassForAdjustment by remember { mutableStateOf<UpcomingClass?>(null) }

    // Load schedule
    fun loadSchedule() {
        scope.launch {
            isLoading = true
            error = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                val (today, upcoming) = withContext(Dispatchers.IO) {
                    ApiService.getUpcomingSchedule(BuildConfig.API_BASE_URL, token, user.userId)
                }
                todaySchedule = today
                upcomingSchedule = upcoming

                // Set default selected day
                if (selectedDay == null && upcoming.isNotEmpty()) {
                    selectedDay = upcoming.firstOrNull()?.day
                }
            } catch (e: Exception) {
                error = e.message ?: "Failed to load schedule"
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(Unit) {
        loadSchedule()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Upcoming Schedule") }
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
                        Button(onClick = { loadSchedule() }) {
                            Text("Retry")
                        }
                    }
                }
            }
            else -> {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    // Today's Schedule Section
                    item {
                        Text(
                            text = "Today's Classes",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    if (todaySchedule.isEmpty()) {
                        item {
                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                colors = CardDefaults.cardColors(
                                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                                )
                            ) {
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(32.dp),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        "No classes scheduled for today",
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                    } else {
                        items(todaySchedule) { classItem ->
                            ScheduleClassCard(
                                classItem = classItem,
                                isToday = true,
                                onMarkAttendance = { onMarkAttendance(classItem.scheduleId, classItem.dateIso) },
                                onAdjust = {
                                    selectedClassForAdjustment = classItem
                                    showAdjustmentModal = true
                                },
                                onRespondToAdjustment = { approved ->
                                    scope.launch {
                                        try {
                                            val token = AppPrefs.getAccessToken(context) ?: return@launch
                                            withContext(Dispatchers.IO) {
                                                classItem.adjustment?.let { adj ->
                                                    ApiService.respondToAdjustment(
                                                        BuildConfig.API_BASE_URL, token, adj.id,
                                                        if (approved) "Approved" else "Rejected"
                                                    )
                                                }
                                            }
                                            loadSchedule()
                                        } catch (e: Exception) {
                                            // Handle error
                                        }
                                    }
                                }
                            )
                        }
                    }

                    // Upcoming Schedule Section
                    item {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Upcoming Classes",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    // Day filter chips
                    if (availableDays.isNotEmpty()) {
                        item {
                            LazyRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                items(availableDays) { day ->
                                    FilterChip(
                                        selected = selectedDay == day,
                                        onClick = { selectedDay = day },
                                        label = { Text(day) },
                                        colors = FilterChipDefaults.filterChipColors(
                                            selectedContainerColor = accentPurple(),
                                            selectedLabelColor = Color.White
                                        )
                                    )
                                }
                            }
                        }
                    }

                    val filteredUpcoming = upcomingSchedule.filter {
                        selectedDay == null || it.day == selectedDay
                    }

                    if (filteredUpcoming.isEmpty()) {
                        item {
                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                colors = CardDefaults.cardColors(
                                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                                )
                            ) {
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(32.dp),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        "No upcoming classes",
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                    } else {
                        items(filteredUpcoming) { classItem ->
                            ScheduleClassCard(
                                classItem = classItem,
                                isToday = false,
                                onMarkAttendance = null,
                                onAdjust = {
                                    selectedClassForAdjustment = classItem
                                    showAdjustmentModal = true
                                },
                                onRespondToAdjustment = { approved ->
                                    scope.launch {
                                        try {
                                            val token = AppPrefs.getAccessToken(context) ?: return@launch
                                            withContext(Dispatchers.IO) {
                                                classItem.adjustment?.let { adj ->
                                                    ApiService.respondToAdjustment(
                                                        BuildConfig.API_BASE_URL, token, adj.id,
                                                        if (approved) "Approved" else "Rejected"
                                                    )
                                                }
                                            }
                                            loadSchedule()
                                        } catch (e: Exception) {
                                            // Handle error
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

    // Adjustment Modal
    if (showAdjustmentModal && selectedClassForAdjustment != null) {
        AdjustmentDialog(
            classItem = selectedClassForAdjustment!!,
            onDismiss = {
                showAdjustmentModal = false
                selectedClassForAdjustment = null
            },
            onSuccess = {
                showAdjustmentModal = false
                selectedClassForAdjustment = null
                loadSchedule()
            }
        )
    }
}

/**
 * Card for displaying a scheduled class with adjustment info.
 */
@Composable
private fun ScheduleClassCard(
    classItem: UpcomingClass,
    isToday: Boolean,
    onMarkAttendance: (() -> Unit)?,
    onAdjust: () -> Unit,
    onRespondToAdjustment: (approved: Boolean) -> Unit
) {
    val adjustment = classItem.adjustment
    val hasAdjustment = adjustment != null
    val isPendingAdjustment = adjustment?.status == "Pending"
    val isApprovedAdjustment = adjustment?.status == "Approved"
    val isRequester = adjustment?.role == "requester"
    val isAdjuster = adjustment?.role == "adjuster"

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = when {
                isApprovedAdjustment && adjustment?.kind == "in" -> Color(0xFFE8F5E9)  // Green for swapped-in
                isPendingAdjustment -> Color(0xFFFFF8E1)  // Amber for pending
                else -> MaterialTheme.colorScheme.surface
            }
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            // Header row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Time and date
                Column {
                    Text(
                        text = classItem.time,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = accentPurple()
                    )
                    if (!isToday) {
                        Text(
                            text = "${classItem.day}, ${classItem.dateDisplay}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                // Status badge
                if (hasAdjustment) {
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = when {
                            isApprovedAdjustment -> Color(0xFF4CAF50)
                            isPendingAdjustment -> Color(0xFFFFC107)
                            else -> Color(0xFFF44336)
                        }
                    ) {
                        Text(
                            text = when {
                                isApprovedAdjustment && adjustment?.kind == "in" -> "Swapped In"
                                isApprovedAdjustment -> "Adjusted"
                                isPendingAdjustment && isRequester -> "Pending Swap"
                                isPendingAdjustment && isAdjuster -> "Swap Request"
                                else -> adjustment?.status ?: ""
                            },
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = Color.White
                        )
                    }
                } else if (classItem.status == "Done") {
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = Color(0xFF4CAF50)
                    ) {
                        Text(
                            text = "Done",
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = Color.White
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Subject and class info
            Text(
                text = classItem.subject,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = "${classItem.className} ${classItem.batch?.let { "• $it" } ?: ""} • ${classItem.type}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            // Adjustment info
            if (hasAdjustment && adjustment != null) {
                Spacer(modifier = Modifier.height(8.dp))
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        if (adjustment.kind == "out" && isRequester) {
                            Text(
                                text = "Swap with: ${adjustment.partnerName} (${adjustment.partnerCode})",
                                style = MaterialTheme.typography.bodySmall
                            )
                            adjustment.swap?.let { swap ->
                                Text(
                                    text = "For: ${swap.day}, ${swap.dateDisplay} ${swap.time}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Text(
                                    text = "${swap.subject} - ${swap.className}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        } else if (adjustment.kind == "out" && isAdjuster) {
                            Text(
                                text = "Swap request from: ${adjustment.partnerName}",
                                style = MaterialTheme.typography.bodySmall
                            )
                        } else if (adjustment.kind == "in") {
                            Text(
                                text = "Taking over from: ${adjustment.partnerName}",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Action buttons
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Show approve/reject buttons if pending and user is adjuster
                if (isPendingAdjustment && isAdjuster) {
                    OutlinedButton(
                        onClick = { onRespondToAdjustment(false) },
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = Color(0xFFF44336)
                        )
                    ) {
                        Icon(Icons.Default.Close, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Reject")
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = { onRespondToAdjustment(true) },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color(0xFF4CAF50)
                        )
                    ) {
                        Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Approve")
                    }
                } else {
                    // Mark Attendance button for today's classes
                    if (isToday && onMarkAttendance != null && classItem.status != "Done" && !isPendingAdjustment) {
                        Button(
                            onClick = onMarkAttendance,
                            colors = ButtonDefaults.buttonColors(containerColor = accentPurple())
                        ) {
                            Icon(Icons.Default.HowToReg, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Mark")
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                    }

                    // Adjust button for future classes without pending adjustment
                    if (!hasAdjustment && classItem.status != "Done") {
                        OutlinedButton(
                            onClick = onAdjust,
                            colors = ButtonDefaults.outlinedButtonColors(
                                contentColor = accentPurple()
                            )
                        ) {
                            Icon(Icons.Default.SwapHoriz, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Adjust")
                        }
                    }
                }
            }
        }
    }
}

/**
 * Dialog for creating an adjustment request.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AdjustmentDialog(
    classItem: UpcomingClass,
    onDismiss: () -> Unit,
    onSuccess: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var isLoading by remember { mutableStateOf(false) }
    var isSearching by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    var availableFaculty by remember { mutableStateOf<List<AdjustmentFaculty>>(emptyList()) }
    var selectedFaculty by remember { mutableStateOf<AdjustmentFaculty?>(null) }
    var selectedSlot by remember { mutableStateOf<AvailableSlot?>(null) }
    var reason by remember { mutableStateOf("") }

    // Search for available faculty
    fun searchFaculty() {
        scope.launch {
            isSearching = true
            error = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                val faculty = withContext(Dispatchers.IO) {
                    ApiService.findAdjustmentFaculty(
                        BuildConfig.API_BASE_URL, token,
                        classItem.scheduleId,
                        classItem.dateIso,
                        user.userId
                    )
                }
                availableFaculty = faculty
                if (faculty.isEmpty()) {
                    error = "No faculty available for swap"
                }
            } catch (e: Exception) {
                error = e.message ?: "Failed to search faculty"
            } finally {
                isSearching = false
            }
        }
    }

    // Submit adjustment request
    fun submitAdjustment() {
        val faculty = selectedFaculty ?: return
        val slot = selectedSlot ?: return

        scope.launch {
            isLoading = true
            error = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                withContext(Dispatchers.IO) {
                    ApiService.submitAdjustment(
                        BuildConfig.API_BASE_URL, token,
                        AdjustmentRequest(
                            requesterId = user.userId,
                            scheduleId = classItem.scheduleId,
                            originalDate = classItem.dateIso,
                            substituteId = faculty.facultyId,
                            swapSlotId = slot.scheduleId,
                            compensationDate = slot.dateIso,
                            reason = reason.takeIf { it.isNotBlank() }
                        )
                    )
                }
                onSuccess()
            } catch (e: Exception) {
                error = e.message ?: "Failed to submit adjustment"
            } finally {
                isLoading = false
            }
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text("Request Session Adjustment")
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 400.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Current slot info
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
                    )
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(
                            "Your Slot",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            "${classItem.day}, ${classItem.dateDisplay} ${classItem.time}",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            "${classItem.subject} - ${classItem.className}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }

                // Search button
                if (availableFaculty.isEmpty() && !isSearching) {
                    Button(
                        onClick = { searchFaculty() },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = accentPurple())
                    ) {
                        Icon(Icons.Default.Search, contentDescription = null)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Search Available Faculty")
                    }
                }

                // Loading indicator
                if (isSearching) {
                    Box(
                        modifier = Modifier.fillMaxWidth(),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(32.dp))
                    }
                }

                // Faculty list
                if (availableFaculty.isNotEmpty()) {
                    Text(
                        "Select Faculty",
                        style = MaterialTheme.typography.labelMedium
                    )
                    LazyColumn(
                        modifier = Modifier.heightIn(max = 120.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        items(availableFaculty) { faculty ->
                            Surface(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        selectedFaculty = faculty
                                        selectedSlot = null
                                    },
                                shape = RoundedCornerShape(8.dp),
                                color = if (selectedFaculty == faculty)
                                    accentPurple().copy(alpha = 0.1f)
                                else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                            ) {
                                Row(
                                    modifier = Modifier.padding(12.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    RadioButton(
                                        selected = selectedFaculty == faculty,
                                        onClick = {
                                            selectedFaculty = faculty
                                            selectedSlot = null
                                        },
                                        colors = RadioButtonDefaults.colors(
                                            selectedColor = accentPurple()
                                        )
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Column {
                                        Text(
                                            faculty.name,
                                            style = MaterialTheme.typography.bodyMedium,
                                            fontWeight = FontWeight.Medium
                                        )
                                        Text(
                                            faculty.code,
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                            }
                        }
                    }
                }

                // Swap slot selection
                if (selectedFaculty != null && selectedFaculty!!.availableSlots.isNotEmpty()) {
                    Text(
                        "Select Swap Slot",
                        style = MaterialTheme.typography.labelMedium
                    )
                    LazyColumn(
                        modifier = Modifier.heightIn(max = 100.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        items(selectedFaculty!!.availableSlots) { slot ->
                            Surface(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { selectedSlot = slot },
                                shape = RoundedCornerShape(8.dp),
                                color = if (selectedSlot == slot)
                                    accentPurple().copy(alpha = 0.1f)
                                else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                            ) {
                                Row(
                                    modifier = Modifier.padding(12.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    RadioButton(
                                        selected = selectedSlot == slot,
                                        onClick = { selectedSlot = slot },
                                        colors = RadioButtonDefaults.colors(
                                            selectedColor = accentPurple()
                                        )
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Column {
                                        Text(
                                            "${slot.day}, ${slot.dateDisplay} ${slot.time}",
                                            style = MaterialTheme.typography.bodyMedium
                                        )
                                        Text(
                                            "${slot.subject} - ${slot.className}",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                            }
                        }
                    }
                }

                // Reason field
                if (selectedSlot != null) {
                    OutlinedTextField(
                        value = reason,
                        onValueChange = { reason = it },
                        label = { Text("Reason (optional)") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                }

                // Error message
                error?.let {
                    Text(
                        it,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { submitAdjustment() },
                enabled = selectedFaculty != null && selectedSlot != null && !isLoading,
                colors = ButtonDefaults.buttonColors(containerColor = accentPurple())
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        color = Color.White,
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Submit Request")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

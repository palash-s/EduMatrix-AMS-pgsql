package com.eduMatrix.ams.ui.staff

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
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
import com.eduMatrix.ams.data.models.*
import com.eduMatrix.ams.ui.theme.StatusGreen
import com.eduMatrix.ams.ui.theme.StatusRed
import com.eduMatrix.ams.ui.theme.accentPurple
import com.eduMatrix.ams.ui.theme.accentTeal
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Upcoming Schedule screen - shows today's classes and upcoming sessions with adjustment capability.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UpcomingScheduleScreen(
    onMarkAttendance: (scheduleId: String, date: String) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var isLoading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var todaySchedule by remember { mutableStateOf<List<UpcomingClass>>(emptyList()) }
    var upcomingSchedule by remember { mutableStateOf<List<UpcomingClass>>(emptyList()) }

    // Date filter for upcoming schedule (group by date for 2-week view)
    val availableDates = remember(upcomingSchedule) {
        upcomingSchedule.map { it.dateIso }.distinct().sorted()
    }
    var selectedDate by remember { mutableStateOf<String?>(null) }

    // Get display text for a date
    fun getDateLabel(dateIso: String): String {
        val parts = upcomingSchedule.firstOrNull { it.dateIso == dateIso }
        return parts?.let { "${it.day.take(3)} ${it.dateDisplay}" } ?: dateIso
    }

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

                // Set default selected date (first upcoming date)
                if (selectedDate == null && upcoming.isNotEmpty()) {
                    selectedDate = upcoming.firstOrNull()?.dateIso
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
                                onMarkAttendance = { onMarkAttendance(classItem.scheduleId.toString(), classItem.dateIso) },
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

                    // Upcoming Schedule Section (Next 2 Weeks)
                    item {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Upcoming Classes (Next 2 Weeks)",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    // Date filter chips (for 2-week view)
                    if (availableDates.isNotEmpty()) {
                        item {
                            LazyRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                items(availableDates) { dateIso ->
                                    FilterChip(
                                        selected = selectedDate == dateIso,
                                        onClick = { selectedDate = dateIso },
                                        label = { Text(getDateLabel(dateIso)) },
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
                        selectedDate == null || it.dateIso == selectedDate
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

    val isCompleted = classItem.status == "Done"

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (isCompleted) Modifier.alpha(0.6f) else Modifier),
        colors = CardDefaults.cardColors(
            containerColor = when {
                isCompleted -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
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
                    // Don't show if:
                    // - Session is adjusted out (approved, kind=out, role=requester) - someone else is covering
                    // - Session has pending adjustment
                    val isAdjustedOut = isApprovedAdjustment && adjustment?.kind == "out" && isRequester
                    val canMarkAttendance = isToday &&
                                            onMarkAttendance != null &&
                                            classItem.status != "Done" &&
                                            !isPendingAdjustment &&
                                            !isAdjustedOut
                    if (canMarkAttendance) {
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
 * Modern bottom sheet dialog for creating an adjustment request.
 * Uses a stepped approach for cleaner UX.
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

    // Current step: 0 = initial/search, 1 = select faculty, 2 = select slot, 3 = confirm
    val currentStep = when {
        selectedSlot != null -> 3
        selectedFaculty != null -> 2
        availableFaculty.isNotEmpty() -> 1
        else -> 0
    }

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
                    error = "No faculty available for swap on this date"
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

    // Full screen modal with modern design
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 32.dp),
            shape = RoundedCornerShape(24.dp),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 6.dp
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(20.dp)
            ) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            text = "Request Swap",
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        Text(
                            text = "Find a colleague to swap sessions",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Close",
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                Spacer(modifier = Modifier.height(20.dp))

                // Your session card - always visible
                SessionInfoCard(
                    label = "Your Session",
                    day = classItem.day,
                    date = classItem.dateDisplay,
                    time = classItem.time,
                    subject = classItem.subject,
                    className = classItem.className,
                    accentColor = accentPurple()
                )

                Spacer(modifier = Modifier.height(16.dp))

                // Error message
                AnimatedVisibility(visible = error != null) {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 12.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = StatusRed.copy(alpha = 0.1f)
                        ),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Default.ErrorOutline,
                                contentDescription = null,
                                tint = StatusRed,
                                modifier = Modifier.size(20.dp)
                            )
                            Text(
                                text = error ?: "",
                                style = MaterialTheme.typography.bodySmall,
                                color = StatusRed
                            )
                        }
                    }
                }

                // Content based on current step
                LazyColumn(
                    modifier = Modifier
                        .weight(1f, fill = false)
                        .heightIn(max = 350.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Step 0: Search button
                    if (currentStep == 0 && !isSearching) {
                        item {
                            Spacer(modifier = Modifier.height(8.dp))
                            Button(
                                onClick = { searchFaculty() },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(52.dp),
                                shape = RoundedCornerShape(14.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = accentPurple())
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Search,
                                    contentDescription = null,
                                    modifier = Modifier.size(20.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = "Find Available Faculty",
                                    style = MaterialTheme.typography.labelLarge
                                )
                            }
                        }
                    }

                    // Loading state
                    if (isSearching) {
                        item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 32.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Column(
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                    verticalArrangement = Arrangement.spacedBy(12.dp)
                                ) {
                                    CircularProgressIndicator(
                                        modifier = Modifier.size(40.dp),
                                        color = accentPurple(),
                                        strokeWidth = 3.dp
                                    )
                                    Text(
                                        text = "Searching for available faculty...",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                    }

                    // Step 1+: Faculty selection
                    if (availableFaculty.isNotEmpty() && currentStep >= 1) {
                        item {
                            SectionHeader(
                                title = "Select Faculty",
                                subtitle = "${availableFaculty.size} colleague${if (availableFaculty.size > 1) "s" else ""} available"
                            )
                        }

                        items(availableFaculty) { faculty ->
                            FacultyCard(
                                faculty = faculty,
                                isSelected = selectedFaculty == faculty,
                                onClick = {
                                    selectedFaculty = faculty
                                    selectedSlot = null
                                    error = null
                                }
                            )
                        }
                    }

                    // Step 2+: Swap slot selection
                    if (selectedFaculty != null && selectedFaculty!!.availableSlots.isNotEmpty() && currentStep >= 2) {
                        item {
                            Spacer(modifier = Modifier.height(8.dp))
                            SectionHeader(
                                title = "Select Swap Slot",
                                subtitle = "Choose ${selectedFaculty?.name}'s session to swap with"
                            )
                        }

                        items(selectedFaculty!!.availableSlots) { slot ->
                            SwapSlotCard(
                                slot = slot,
                                isSelected = selectedSlot == slot,
                                onClick = {
                                    selectedSlot = slot
                                    error = null
                                }
                            )
                        }
                    }

                    // Step 3: Reason and summary
                    if (selectedSlot != null && currentStep == 3) {
                        item {
                            Spacer(modifier = Modifier.height(8.dp))

                            // Swap preview
                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                colors = CardDefaults.cardColors(
                                    containerColor = StatusGreen.copy(alpha = 0.08f)
                                ),
                                shape = RoundedCornerShape(14.dp)
                            ) {
                                Column(
                                    modifier = Modifier.padding(14.dp),
                                    verticalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                                    ) {
                                        Icon(
                                            imageVector = Icons.Default.SwapHoriz,
                                            contentDescription = null,
                                            tint = StatusGreen,
                                            modifier = Modifier.size(20.dp)
                                        )
                                        Text(
                                            text = "Swap Summary",
                                            style = MaterialTheme.typography.labelLarge,
                                            fontWeight = FontWeight.SemiBold,
                                            color = StatusGreen
                                        )
                                    }

                                    HorizontalDivider(
                                        color = StatusGreen.copy(alpha = 0.2f),
                                        thickness = 1.dp
                                    )

                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column {
                                            Text(
                                                text = "You give",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                            Text(
                                                text = "${classItem.day.take(3)}, ${classItem.dateDisplay}",
                                                style = MaterialTheme.typography.bodyMedium,
                                                fontWeight = FontWeight.Medium
                                            )
                                        }

                                        Icon(
                                            imageVector = Icons.AutoMirrored.Filled.ArrowForward,
                                            contentDescription = null,
                                            tint = StatusGreen,
                                            modifier = Modifier.size(18.dp)
                                        )

                                        Column(horizontalAlignment = Alignment.End) {
                                            Text(
                                                text = "You get",
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                            Text(
                                                text = "${selectedSlot?.day?.take(3)}, ${selectedSlot?.dateDisplay}",
                                                style = MaterialTheme.typography.bodyMedium,
                                                fontWeight = FontWeight.Medium
                                            )
                                        }
                                    }
                                }
                            }
                        }

                        item {
                            OutlinedTextField(
                                value = reason,
                                onValueChange = { reason = it },
                                label = { Text("Reason (optional)") },
                                placeholder = { Text("e.g., Medical appointment") },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(14.dp),
                                singleLine = true,
                                colors = OutlinedTextFieldDefaults.colors(
                                    focusedBorderColor = accentPurple(),
                                    cursorColor = accentPurple()
                                )
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Action buttons
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Back/Cancel button
                    OutlinedButton(
                        onClick = {
                            when {
                                selectedSlot != null -> selectedSlot = null
                                selectedFaculty != null -> selectedFaculty = null
                                else -> onDismiss()
                            }
                        },
                        modifier = Modifier
                            .weight(1f)
                            .height(50.dp),
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    ) {
                        Text(
                            text = if (currentStep > 0) "Back" else "Cancel",
                            style = MaterialTheme.typography.labelLarge
                        )
                    }

                    // Submit button
                    Button(
                        onClick = { submitAdjustment() },
                        modifier = Modifier
                            .weight(1.5f)
                            .height(50.dp),
                        enabled = selectedFaculty != null && selectedSlot != null && !isLoading,
                        shape = RoundedCornerShape(14.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = accentPurple(),
                            disabledContainerColor = accentPurple().copy(alpha = 0.3f)
                        )
                    ) {
                        if (isLoading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                color = Color.White,
                                strokeWidth = 2.dp
                            )
                        } else {
                            Text(
                                text = "Submit Request",
                                style = MaterialTheme.typography.labelLarge
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * Session info card for displaying session details
 */
@Composable
private fun SessionInfoCard(
    label: String,
    day: String,
    date: String,
    time: String,
    subject: String,
    className: String,
    accentColor: Color
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = accentColor.copy(alpha = 0.08f)
        ),
        shape = RoundedCornerShape(14.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Accent bar
            Box(
                modifier = Modifier
                    .width(4.dp)
                    .height(48.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(accentColor)
            )

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = label,
                    style = MaterialTheme.typography.labelSmall,
                    color = accentColor,
                    fontWeight = FontWeight.SemiBold
                )
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = "$day, $date",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Text(
                    text = time,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = subject,
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurface,
                    maxLines = 1
                )
                Text(
                    text = className,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/**
 * Section header for dialog sections
 */
@Composable
private fun SectionHeader(title: String, subtitle: String) {
    Column {
        Text(
            text = title,
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurface
        )
        Text(
            text = subtitle,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

/**
 * Faculty selection card
 */
@Composable
private fun FacultyCard(
    faculty: AdjustmentFaculty,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    val borderColor = if (isSelected) accentPurple() else Color.Transparent
    val backgroundColor = if (isSelected)
        accentPurple().copy(alpha = 0.08f)
    else
        MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f)

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .border(
                width = if (isSelected) 2.dp else 0.dp,
                color = borderColor,
                shape = RoundedCornerShape(12.dp)
            )
            .clickable(onClick = onClick),
        color = backgroundColor,
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Avatar
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(CircleShape)
                    .background(
                        if (isSelected) accentPurple()
                        else MaterialTheme.colorScheme.surfaceVariant
                    ),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = faculty.name.take(1).uppercase(),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (isSelected) Color.White
                    else MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = faculty.name,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Text(
                    text = faculty.code,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Slot count badge
            Surface(
                color = accentPurple().copy(alpha = 0.1f),
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    text = "${faculty.availableSlots.size} slot${if (faculty.availableSlots.size > 1) "s" else ""}",
                    style = MaterialTheme.typography.labelSmall,
                    color = accentPurple(),
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                )
            }

            if (isSelected) {
                Icon(
                    imageVector = Icons.Default.CheckCircle,
                    contentDescription = "Selected",
                    tint = accentPurple(),
                    modifier = Modifier.size(22.dp)
                )
            }
        }
    }
}

/**
 * Swap slot selection card
 */
@Composable
private fun SwapSlotCard(
    slot: AvailableSlot,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    val borderColor = if (isSelected) accentTeal() else Color.Transparent
    val backgroundColor = if (isSelected)
        accentTeal().copy(alpha = 0.08f)
    else
        MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f)

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .border(
                width = if (isSelected) 2.dp else 0.dp,
                color = borderColor,
                shape = RoundedCornerShape(12.dp)
            )
            .clickable(onClick = onClick),
        color = backgroundColor,
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Date icon
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(
                        if (isSelected) accentTeal()
                        else MaterialTheme.colorScheme.surfaceVariant
                    ),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.CalendarMonth,
                    contentDescription = null,
                    tint = if (isSelected) Color.White
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(22.dp)
                )
            }

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "${slot.day}, ${slot.dateDisplay}",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Text(
                    text = slot.time,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = slot.subject,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurface,
                    maxLines = 1
                )
                Text(
                    text = slot.className,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            if (isSelected) {
                Icon(
                    imageVector = Icons.Default.CheckCircle,
                    contentDescription = "Selected",
                    tint = accentTeal(),
                    modifier = Modifier.size(22.dp)
                )
            }
        }
    }
}

package com.eduMatrix.ams.ui.staff.events

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiException
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.*
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*

/**
 * Event Manager Dashboard screen for event coordinators.
 * Uses mobile-first list-detail navigation pattern.
 * Features:
 * - View list of events created by the coordinator
 * - Create new events
 * - View/manage event participants
 * - Mark On-Duty attendance for participants
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EventDashboardScreen(
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    // Navigation state - null means showing event list, non-null shows event detail
    var selectedEvent by remember { mutableStateOf<EventSummary?>(null) }

    // Loading states
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }

    // Data
    var events by remember { mutableStateOf<List<EventSummary>>(emptyList()) }
    var participants by remember { mutableStateOf<List<EventParticipant>>(emptyList()) }
    var loadingParticipants by rememberSaveable { mutableStateOf(false) }

    // Dialogs
    var showCreateEventDialog by rememberSaveable { mutableStateOf(false) }
    var showAddParticipantsDialog by rememberSaveable { mutableStateOf(false) }
    var showDeleteConfirmDialog by rememberSaveable { mutableStateOf(false) }
    var eventToDelete by remember { mutableStateOf<EventSummary?>(null) }

    // Load events
    fun loadEvents() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                val eventsList = withContext(Dispatchers.IO) {
                    ApiService.getMyEvents(BuildConfig.API_BASE_URL, token, user.userId)
                }
                events = eventsList

                // If we had a selected event, refresh its data
                if (selectedEvent != null) {
                    val updated = eventsList.find { it.eventId == selectedEvent!!.eventId }
                    selectedEvent = updated
                }
            } catch (e: Exception) {
                errorMessage = e.message ?: "Failed to load events"
            } finally {
                isLoading = false
            }
        }
    }

    // Load participants for selected event
    fun loadParticipants(eventId: Int) {
        scope.launch {
            loadingParticipants = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: return@launch
                val participantsList = withContext(Dispatchers.IO) {
                    ApiService.getEventParticipants(BuildConfig.API_BASE_URL, token, eventId)
                }
                participants = participantsList
            } catch (e: Exception) {
                snackbarHostState.showSnackbar("Error: ${e.message}")
            } finally {
                loadingParticipants = false
            }
        }
    }

    // Toggle OD status
    fun toggleAttendance(participant: EventParticipant) {
        scope.launch {
            try {
                val token = AppPrefs.getAccessToken(context) ?: return@launch
                val newStatus = participant.status != "Attended"
                withContext(Dispatchers.IO) {
                    ApiService.markEventAttendance(
                        BuildConfig.API_BASE_URL,
                        token,
                        participant.participationId,
                        newStatus
                    )
                }
                // Reload participants
                selectedEvent?.let { loadParticipants(it.eventId) }
                snackbarHostState.showSnackbar(
                    if (newStatus) "Marked as On-Duty" else "OD status removed"
                )
            } catch (e: Exception) {
                snackbarHostState.showSnackbar("Error: ${e.message}")
            }
        }
    }

    // Delete event
    fun deleteEvent(event: EventSummary) {
        scope.launch {
            try {
                val token = AppPrefs.getAccessToken(context) ?: return@launch
                val user = AppPrefs.getUser(context) ?: return@launch
                withContext(Dispatchers.IO) {
                    ApiService.deleteEvent(BuildConfig.API_BASE_URL, token, event.eventId, user.userId)
                }
                snackbarHostState.showSnackbar("Event deleted")
                if (selectedEvent?.eventId == event.eventId) {
                    selectedEvent = null
                    participants = emptyList()
                }
                loadEvents()
            } catch (e: Exception) {
                snackbarHostState.showSnackbar("Error: ${e.message}")
            }
        }
    }

    // Initial load
    LaunchedEffect(Unit) {
        loadEvents()
    }

    // Load participants when event is selected
    LaunchedEffect(selectedEvent) {
        selectedEvent?.let { loadParticipants(it.eventId) }
    }

    // Handle back press
    val handleBack: () -> Unit = {
        if (selectedEvent != null) {
            selectedEvent = null
            participants = emptyList()
        } else {
            onBack()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        if (selectedEvent != null) selectedEvent!!.name else "Event Manager",
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                },
                navigationIcon = {
                    IconButton(onClick = handleBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    if (selectedEvent == null) {
                        IconButton(onClick = { loadEvents() }) {
                            Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                        }
                    } else {
                        IconButton(onClick = { showAddParticipantsDialog = true }) {
                            Icon(Icons.Default.PersonAdd, contentDescription = "Add Participants")
                        }
                    }
                }
            )
        },
        floatingActionButton = {
            if (selectedEvent == null) {
                ExtendedFloatingActionButton(
                    onClick = { showCreateEventDialog = true },
                    containerColor = accentPurple(),
                    contentColor = Color.White
                ) {
                    Icon(Icons.Default.Add, contentDescription = null)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("New Event")
                }
            }
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { padding ->
        AnimatedContent(
            targetState = selectedEvent,
            transitionSpec = {
                if (targetState != null) {
                    slideInHorizontally { it } + fadeIn() togetherWith
                            slideOutHorizontally { -it } + fadeOut()
                } else {
                    slideInHorizontally { -it } + fadeIn() togetherWith
                            slideOutHorizontally { it } + fadeOut()
                }
            },
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            label = "EventNavigation"
        ) { event ->
            if (event == null) {
                // Events List View
                EventsListView(
                    events = events,
                    isLoading = isLoading,
                    errorMessage = errorMessage,
                    onEventClick = { selectedEvent = it },
                    onDeleteEvent = { eventItem ->
                        if (eventItem.studentCount == 0) {
                            eventToDelete = eventItem
                            showDeleteConfirmDialog = true
                        } else {
                            scope.launch {
                                snackbarHostState.showSnackbar("Cannot delete event with participants")
                            }
                        }
                    },
                    onRetry = { loadEvents() }
                )
            } else {
                // Event Detail View (Participants)
                EventDetailView(
                    event = event,
                    participants = participants,
                    isLoading = loadingParticipants,
                    onAddParticipants = { showAddParticipantsDialog = true },
                    onToggleAttendance = { toggleAttendance(it) },
                    onRefresh = { loadParticipants(event.eventId) }
                )
            }
        }
    }

    // Create Event Dialog
    if (showCreateEventDialog) {
        CreateEventDialog(
            onDismiss = { showCreateEventDialog = false },
            onEventCreated = {
                showCreateEventDialog = false
                loadEvents()
                scope.launch {
                    snackbarHostState.showSnackbar("Event created successfully")
                }
            }
        )
    }

    // Add Participants Dialog
    if (showAddParticipantsDialog && selectedEvent != null) {
        AddParticipantsDialog(
            eventId = selectedEvent!!.eventId,
            onDismiss = { showAddParticipantsDialog = false },
            onParticipantsAdded = {
                showAddParticipantsDialog = false
                loadEvents()
                selectedEvent?.let { loadParticipants(it.eventId) }
                scope.launch {
                    snackbarHostState.showSnackbar("Participants added successfully")
                }
            }
        )
    }

    // Delete Confirmation Dialog
    if (showDeleteConfirmDialog && eventToDelete != null) {
        AlertDialog(
            onDismissRequest = {
                showDeleteConfirmDialog = false
                eventToDelete = null
            },
            title = { Text("Delete Event") },
            text = { Text("Are you sure you want to delete \"${eventToDelete!!.name}\"?") },
            confirmButton = {
                TextButton(
                    onClick = {
                        eventToDelete?.let { deleteEvent(it) }
                        showDeleteConfirmDialog = false
                        eventToDelete = null
                    },
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text("Delete")
                }
            },
            dismissButton = {
                TextButton(onClick = {
                    showDeleteConfirmDialog = false
                    eventToDelete = null
                }) {
                    Text("Cancel")
                }
            }
        )
    }
}

/**
 * Events list view - mobile-optimized card layout
 */
@Composable
private fun EventsListView(
    events: List<EventSummary>,
    isLoading: Boolean,
    errorMessage: String?,
    onEventClick: (EventSummary) -> Unit,
    onDeleteEvent: (EventSummary) -> Unit,
    onRetry: () -> Unit
) {
    when {
        isLoading -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(color = accentPurple())
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = "Loading events...",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
        errorMessage != null -> {
            Box(
                modifier = Modifier.fillMaxSize(),
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
                    Text(
                        text = errorMessage,
                        style = MaterialTheme.typography.bodyLarge,
                        textAlign = TextAlign.Center
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Button(onClick = onRetry) {
                        Text("Retry")
                    }
                }
            }
        }
        events.isEmpty() -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.padding(32.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(120.dp)
                            .clip(CircleShape)
                            .background(accentPurple().copy(alpha = 0.1f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.Event,
                            contentDescription = null,
                            modifier = Modifier.size(56.dp),
                            tint = accentPurple()
                        )
                    }
                    Spacer(modifier = Modifier.height(24.dp))
                    Text(
                        text = "No Events Yet",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Create your first event by tapping the button below",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center
                    )
                }
            }
        }
        else -> {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Summary header
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
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(
                                    text = "${events.size}",
                                    style = MaterialTheme.typography.headlineMedium,
                                    fontWeight = FontWeight.Bold,
                                    color = accentPurple()
                                )
                                Text(
                                    text = "Total Events",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(
                                    text = "${events.sumOf { it.studentCount }}",
                                    style = MaterialTheme.typography.headlineMedium,
                                    fontWeight = FontWeight.Bold,
                                    color = accentPurple()
                                )
                                Text(
                                    text = "Participants",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }

                items(events, key = { it.eventId }) { event ->
                    EventCard(
                        event = event,
                        onClick = { onEventClick(event) },
                        onDelete = { onDeleteEvent(event) }
                    )
                }

                // Bottom spacing for FAB
                item {
                    Spacer(modifier = Modifier.height(72.dp))
                }
            }
        }
    }
}

/**
 * Event card - modern mobile-friendly design
 */
@Composable
private fun EventCard(
    event: EventSummary,
    onClick: () -> Unit,
    onDelete: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            // Top row: Event name and delete button
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Text(
                    text = event.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )

                // Delete button only if no participants
                if (event.studentCount == 0) {
                    IconButton(
                        onClick = onDelete,
                        modifier = Modifier.size(36.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.Delete,
                            contentDescription = "Delete",
                            tint = MaterialTheme.colorScheme.error,
                            modifier = Modifier.size(20.dp)
                        )
                    }
                } else {
                    Icon(
                        imageVector = Icons.Default.ChevronRight,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Bottom row: Date, time, participants
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Date chip
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = MaterialTheme.colorScheme.primaryContainer
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.CalendarToday,
                            contentDescription = null,
                            modifier = Modifier.size(14.dp),
                            tint = MaterialTheme.colorScheme.onPrimaryContainer
                        )
                        Text(
                            text = event.dateDisplay,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                            maxLines = 1
                        )
                    }
                }

                // Time chip (if available)
                if (!event.time.isNullOrBlank()) {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.secondaryContainer
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Outlined.Schedule,
                                contentDescription = null,
                                modifier = Modifier.size(14.dp),
                                tint = MaterialTheme.colorScheme.onSecondaryContainer
                            )
                            Text(
                                text = event.time,
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSecondaryContainer,
                                maxLines = 1
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.weight(1f))

                // Participants count
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = if (event.studentCount > 0)
                        StatusGreen.copy(alpha = 0.15f)
                    else
                        MaterialTheme.colorScheme.surfaceVariant
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.People,
                            contentDescription = null,
                            modifier = Modifier.size(14.dp),
                            tint = if (event.studentCount > 0)
                                StatusGreen
                            else
                                MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "${event.studentCount}",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Medium,
                            color = if (event.studentCount > 0)
                                StatusGreen
                            else
                                MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }
    }
}

/**
 * Event detail view - shows participants with OD marking
 */
@Composable
private fun EventDetailView(
    event: EventSummary,
    participants: List<EventParticipant>,
    isLoading: Boolean,
    onAddParticipants: () -> Unit,
    onToggleAttendance: (EventParticipant) -> Unit,
    onRefresh: () -> Unit
) {
    Column(modifier = Modifier.fillMaxSize()) {
        // Event info header
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(
                containerColor = accentPurple().copy(alpha = 0.08f)
            )
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp)
            ) {
                // Date and time row
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.primaryContainer
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = Icons.Outlined.CalendarToday,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp),
                                tint = MaterialTheme.colorScheme.onPrimaryContainer
                            )
                            Text(
                                text = event.dateDisplay,
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onPrimaryContainer
                            )
                        }
                    }

                    if (!event.time.isNullOrBlank()) {
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = MaterialTheme.colorScheme.secondaryContainer
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    imageVector = Icons.Outlined.Schedule,
                                    contentDescription = null,
                                    modifier = Modifier.size(16.dp),
                                    tint = MaterialTheme.colorScheme.onSecondaryContainer
                                )
                                Text(
                                    text = event.time,
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSecondaryContainer
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Stats row
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceEvenly
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text = "${participants.size}",
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold,
                            color = accentPurple()
                        )
                        Text(
                            text = "Participants",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        val attendedCount = participants.count { it.status == "Attended" }
                        Text(
                            text = "$attendedCount",
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold,
                            color = StatusGreen
                        )
                        Text(
                            text = "On-Duty",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        val pendingCount = participants.count { it.status != "Attended" }
                        Text(
                            text = "$pendingCount",
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "Pending",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }

        // Participants list
        when {
            isLoading -> {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator(color = accentPurple())
                }
            }
            participants.isEmpty() -> {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.padding(32.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(100.dp)
                                .clip(CircleShape)
                                .background(MaterialTheme.colorScheme.surfaceVariant),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Outlined.PeopleOutline,
                                contentDescription = null,
                                modifier = Modifier.size(48.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        Spacer(modifier = Modifier.height(20.dp))
                        Text(
                            text = "No Participants Yet",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Add students to this event",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(20.dp))
                        FilledTonalButton(onClick = onAddParticipants) {
                            Icon(Icons.Default.PersonAdd, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Add Participants")
                        }
                    }
                }
            }
            else -> {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(participants, key = { it.participationId }) { participant ->
                        ParticipantCard(
                            participant = participant,
                            onToggleAttendance = { onToggleAttendance(participant) }
                        )
                    }
                }
            }
        }
    }
}

/**
 * Participant card - modern mobile design
 */
@Composable
private fun ParticipantCard(
    participant: EventParticipant,
    onToggleAttendance: () -> Unit
) {
    val isAttended = participant.status == "Attended"

    Card(
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (isAttended)
                StatusGreen.copy(alpha = 0.08f)
            else
                MaterialTheme.colorScheme.surface
        ),
        elevation = CardDefaults.cardElevation(
            defaultElevation = if (isAttended) 0.dp else 1.dp
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Student avatar and info
            Row(
                modifier = Modifier.weight(1f),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Avatar with initials
                Box(
                    modifier = Modifier
                        .size(44.dp)
                        .clip(CircleShape)
                        .background(
                            if (isAttended) StatusGreen.copy(alpha = 0.2f)
                            else accentPurple().copy(alpha = 0.15f)
                        ),
                    contentAlignment = Alignment.Center
                ) {
                    val initials = participant.name.split(" ")
                        .take(2)
                        .mapNotNull { it.firstOrNull()?.uppercase() }
                        .joinToString("")
                    Text(
                        text = initials.ifEmpty { "?" },
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = if (isAttended) StatusGreen else accentPurple()
                    )
                }

                // Name and details
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = participant.name,
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = FontWeight.Medium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = participant.rollNumber,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "•",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = participant.className,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    // Role chip
                    val roleColor = when (participant.role) {
                        "Student Coordinator" -> MaterialTheme.colorScheme.tertiary
                        "Volunteer" -> MaterialTheme.colorScheme.secondary
                        else -> accentPurple()
                    }
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = roleColor.copy(alpha = 0.12f)
                    ) {
                        Text(
                            text = participant.role,
                            style = MaterialTheme.typography.labelSmall,
                            color = roleColor,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }

            // OD Status button
            if (isAttended) {
                FilledTonalButton(
                    onClick = onToggleAttendance,
                    colors = ButtonDefaults.filledTonalButtonColors(
                        containerColor = StatusGreen.copy(alpha = 0.15f),
                        contentColor = StatusGreen
                    ),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.CheckCircle,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("OD", style = MaterialTheme.typography.labelMedium)
                }
            } else {
                OutlinedButton(
                    onClick = onToggleAttendance,
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                    border = ButtonDefaults.outlinedButtonBorder.copy(
                        brush = androidx.compose.ui.graphics.SolidColor(accentPurple())
                    )
                ) {
                    Text(
                        "Mark OD",
                        style = MaterialTheme.typography.labelMedium,
                        color = accentPurple()
                    )
                }
            }
        }
    }
}

/**
 * Create Event Dialog - improved mobile design
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CreateEventDialog(
    onDismiss: () -> Unit,
    onEventCreated: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var eventName by rememberSaveable { mutableStateOf("") }
    var description by rememberSaveable { mutableStateOf("") }
    var startDate by rememberSaveable { mutableStateOf("") }
    var endDate by rememberSaveable { mutableStateOf("") }
    var startTime by rememberSaveable { mutableStateOf("") }
    var endTime by rememberSaveable { mutableStateOf("") }
    var notifyStudents by rememberSaveable { mutableStateOf(false) }
    var isLoading by rememberSaveable { mutableStateOf(false) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }

    val calendar = Calendar.getInstance()
    val dateFormat = SimpleDateFormat("yyyy-MM-dd", Locale.US)
    val displayDateFormat = SimpleDateFormat("dd MMM yyyy", Locale.US)
    val timeFormat = SimpleDateFormat("HH:mm", Locale.US)

    // Date picker
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

    // Time picker
    fun showTimePicker(isStart: Boolean) {
        TimePickerDialog(
            context,
            { _, hourOfDay, minute ->
                calendar.set(Calendar.HOUR_OF_DAY, hourOfDay)
                calendar.set(Calendar.MINUTE, minute)
                val formatted = timeFormat.format(calendar.time)
                if (isStart) startTime = formatted else endTime = formatted
            },
            calendar.get(Calendar.HOUR_OF_DAY),
            calendar.get(Calendar.MINUTE),
            true
        ).show()
    }

    fun createEvent() {
        if (eventName.isBlank()) {
            errorMessage = "Event name is required"
            return
        }
        if (startDate.isBlank()) {
            errorMessage = "Start date is required"
            return
        }
        if (endDate.isBlank()) {
            errorMessage = "End date is required"
            return
        }

        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                val request = EventCreateRequest(
                    name = eventName,
                    description = description.takeIf { it.isNotBlank() },
                    startDate = startDate,
                    endDate = endDate,
                    startTime = startTime.takeIf { it.isNotBlank() },
                    endTime = endTime.takeIf { it.isNotBlank() },
                    coordinatorId = user.userId,
                    notifyAllStudents = notifyStudents
                )

                withContext(Dispatchers.IO) {
                    ApiService.createEvent(BuildConfig.API_BASE_URL, token, request)
                }

                onEventCreated()
            } catch (e: Exception) {
                errorMessage = e.message ?: "Failed to create event"
            } finally {
                isLoading = false
            }
        }
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
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Create Event",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close")
                    }
                }

                Spacer(modifier = Modifier.height(20.dp))

                // Error message
                errorMessage?.let { error ->
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        ),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                Icons.Default.Error,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.error
                            )
                            Text(
                                text = error,
                                color = MaterialTheme.colorScheme.onErrorContainer,
                                style = MaterialTheme.typography.bodyMedium
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(16.dp))
                }

                // Event Name
                OutlinedTextField(
                    value = eventName,
                    onValueChange = { eventName = it },
                    label = { Text("Event Name *") },
                    placeholder = { Text("Enter event name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp)
                )

                Spacer(modifier = Modifier.height(16.dp))

                // Description
                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("Description") },
                    placeholder = { Text("Enter event description") },
                    minLines = 2,
                    maxLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp)
                )

                Spacer(modifier = Modifier.height(20.dp))

                // Date section
                Text(
                    text = "Date",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    OutlinedTextField(
                        value = startDate,
                        onValueChange = {},
                        label = { Text("Start *") },
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
                        label = { Text("End *") },
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

                Spacer(modifier = Modifier.height(20.dp))

                // Time section (optional)
                Text(
                    text = "Time (Optional)",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    OutlinedTextField(
                        value = startTime,
                        onValueChange = {},
                        label = { Text("Start") },
                        placeholder = { Text("--:--") },
                        readOnly = true,
                        singleLine = true,
                        trailingIcon = {
                            IconButton(onClick = { showTimePicker(true) }) {
                                Icon(Icons.Default.Schedule, contentDescription = "Pick time")
                            }
                        },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)
                    )
                    OutlinedTextField(
                        value = endTime,
                        onValueChange = {},
                        label = { Text("End") },
                        placeholder = { Text("--:--") },
                        readOnly = true,
                        singleLine = true,
                        trailingIcon = {
                            IconButton(onClick = { showTimePicker(false) }) {
                                Icon(Icons.Default.Schedule, contentDescription = "Pick time")
                            }
                        },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(12.dp)
                    )
                }

                Spacer(modifier = Modifier.height(20.dp))

                // Notify students checkbox
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .clickable { notifyStudents = !notifyStudents }
                        .padding(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Checkbox(
                        checked = notifyStudents,
                        onCheckedChange = { notifyStudents = it }
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Notify all students about this event",
                        style = MaterialTheme.typography.bodyMedium
                    )
                }

                Spacer(modifier = Modifier.height(24.dp))

                // Buttons
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(onClick = onDismiss, enabled = !isLoading) {
                        Text("Cancel")
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = { createEvent() },
                        enabled = !isLoading && eventName.isNotBlank() && startDate.isNotBlank() && endDate.isNotBlank(),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = accentPurple()
                        )
                    ) {
                        if (isLoading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.dp,
                                color = Color.White
                            )
                        } else {
                            Text("Create Event")
                        }
                    }
                }
            }
        }
    }
}

/**
 * Add Participants Dialog - improved mobile design
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddParticipantsDialog(
    eventId: Int,
    onDismiss: () -> Unit,
    onParticipantsAdded: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // State
    var classes by remember { mutableStateOf<List<ClassSection>>(emptyList()) }
    var students by remember { mutableStateOf<List<StudentForEvent>>(emptyList()) }
    var selectedClassId by rememberSaveable { mutableStateOf<Int?>(null) }
    var selectedRole by rememberSaveable { mutableStateOf("Participant") }
    var selectedStudents by remember { mutableStateOf<Set<String>>(emptySet()) }

    var loadingClasses by rememberSaveable { mutableStateOf(true) }
    var loadingStudents by rememberSaveable { mutableStateOf(false) }
    var isSubmitting by rememberSaveable { mutableStateOf(false) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }

    var classDropdownExpanded by rememberSaveable { mutableStateOf(false) }
    var roleDropdownExpanded by rememberSaveable { mutableStateOf(false) }

    val roles = listOf("Participant", "Student Coordinator", "Volunteer")

    // Load classes on mount
    LaunchedEffect(Unit) {
        try {
            val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
            val classesList = withContext(Dispatchers.IO) {
                ApiService.getClassSections(BuildConfig.API_BASE_URL, token)
            }
            classes = classesList
        } catch (e: Exception) {
            errorMessage = "Failed to load classes: ${e.message}"
        } finally {
            loadingClasses = false
        }
    }

    // Load students when class is selected
    LaunchedEffect(selectedClassId) {
        selectedClassId?.let { classId ->
            loadingStudents = true
            selectedStudents = emptySet()
            try {
                val token = AppPrefs.getAccessToken(context) ?: return@LaunchedEffect
                val studentsList = withContext(Dispatchers.IO) {
                    ApiService.getStudentsForEvent(BuildConfig.API_BASE_URL, token, classId)
                }
                students = studentsList
            } catch (e: Exception) {
                errorMessage = "Failed to load students: ${e.message}"
            } finally {
                loadingStudents = false
            }
        }
    }

    // Submit selected students
    fun addSelectedStudents() {
        if (selectedStudents.isEmpty()) {
            errorMessage = "Please select at least one student"
            return
        }

        scope.launch {
            isSubmitting = true
            errorMessage = null
            var successCount = 0
            var failCount = 0

            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")

                for (studentId in selectedStudents) {
                    val student = students.find { it.studentId == studentId } ?: continue
                    try {
                        withContext(Dispatchers.IO) {
                            ApiService.addEventParticipant(
                                BuildConfig.API_BASE_URL,
                                token,
                                eventId,
                                student.admissionNumber,
                                selectedRole
                            )
                        }
                        successCount++
                    } catch (e: Exception) {
                        failCount++
                    }
                }

                if (successCount > 0) {
                    onParticipantsAdded()
                } else {
                    errorMessage = "Failed to add students"
                }
            } catch (e: Exception) {
                errorMessage = e.message ?: "Failed to add participants"
            } finally {
                isSubmitting = false
            }
        }
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.95f)
                .fillMaxHeight(0.85f),
            shape = RoundedCornerShape(24.dp)
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                // Header
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(20.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Add Participants",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close")
                    }
                }

                HorizontalDivider()

                // Error message
                errorMessage?.let { error ->
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        ),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                Icons.Default.Error,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.error
                            )
                            Text(
                                text = error,
                                color = MaterialTheme.colorScheme.onErrorContainer,
                                style = MaterialTheme.typography.bodyMedium
                            )
                        }
                    }
                }

                // Selectors - stacked on mobile
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Class dropdown
                    ExposedDropdownMenuBox(
                        expanded = classDropdownExpanded,
                        onExpandedChange = { classDropdownExpanded = it },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        OutlinedTextField(
                            value = classes.find { it.sectionId == selectedClassId }?.name ?: "",
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Select Class") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = classDropdownExpanded) },
                            modifier = Modifier
                                .menuAnchor()
                                .fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp)
                        )
                        ExposedDropdownMenu(
                            expanded = classDropdownExpanded,
                            onDismissRequest = { classDropdownExpanded = false }
                        ) {
                            classes.forEach { classSection ->
                                DropdownMenuItem(
                                    text = { Text(classSection.name) },
                                    onClick = {
                                        selectedClassId = classSection.sectionId
                                        classDropdownExpanded = false
                                    }
                                )
                            }
                        }
                    }

                    // Role dropdown
                    ExposedDropdownMenuBox(
                        expanded = roleDropdownExpanded,
                        onExpandedChange = { roleDropdownExpanded = it },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        OutlinedTextField(
                            value = selectedRole,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Role") },
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = roleDropdownExpanded) },
                            modifier = Modifier
                                .menuAnchor()
                                .fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp)
                        )
                        ExposedDropdownMenu(
                            expanded = roleDropdownExpanded,
                            onDismissRequest = { roleDropdownExpanded = false }
                        ) {
                            roles.forEach { role ->
                                DropdownMenuItem(
                                    text = { Text(role) },
                                    onClick = {
                                        selectedRole = role
                                        roleDropdownExpanded = false
                                    }
                                )
                            }
                        }
                    }
                }

                // Select All checkbox
                if (students.isNotEmpty()) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                selectedStudents = if (selectedStudents.size == students.size) {
                                    emptySet()
                                } else {
                                    students.map { it.studentId }.toSet()
                                }
                            }
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(
                            checked = selectedStudents.size == students.size && students.isNotEmpty(),
                            onCheckedChange = { checked ->
                                selectedStudents = if (checked) {
                                    students.map { it.studentId }.toSet()
                                } else {
                                    emptySet()
                                }
                            }
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Select All",
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium
                        )
                        Spacer(modifier = Modifier.weight(1f))
                        Surface(
                            shape = RoundedCornerShape(16.dp),
                            color = accentPurple().copy(alpha = 0.1f)
                        ) {
                            Text(
                                text = "${selectedStudents.size}/${students.size}",
                                style = MaterialTheme.typography.labelMedium,
                                color = accentPurple(),
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp)
                            )
                        }
                    }
                }

                HorizontalDivider()

                // Students list
                Box(modifier = Modifier.weight(1f)) {
                    when {
                        loadingClasses || loadingStudents -> {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    CircularProgressIndicator(color = accentPurple())
                                    Spacer(modifier = Modifier.height(12.dp))
                                    Text(
                                        text = if (loadingClasses) "Loading classes..." else "Loading students...",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                        selectedClassId == null -> {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Icon(
                                        imageVector = Icons.Outlined.School,
                                        contentDescription = null,
                                        modifier = Modifier.size(48.dp),
                                        tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                                    )
                                    Spacer(modifier = Modifier.height(12.dp))
                                    Text(
                                        text = "Select a class to see students",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                        students.isEmpty() -> {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Icon(
                                        imageVector = Icons.Outlined.PeopleOutline,
                                        contentDescription = null,
                                        modifier = Modifier.size(48.dp),
                                        tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                                    )
                                    Spacer(modifier = Modifier.height(12.dp))
                                    Text(
                                        text = "No students in this class",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                        else -> {
                            LazyColumn(
                                modifier = Modifier.fillMaxSize(),
                                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp)
                            ) {
                                items(students, key = { it.studentId }) { student ->
                                    val isSelected = student.studentId in selectedStudents
                                    Card(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(horizontal = 8.dp, vertical = 4.dp)
                                            .clickable {
                                                selectedStudents = if (isSelected) {
                                                    selectedStudents - student.studentId
                                                } else {
                                                    selectedStudents + student.studentId
                                                }
                                            },
                                        shape = RoundedCornerShape(12.dp),
                                        colors = CardDefaults.cardColors(
                                            containerColor = if (isSelected)
                                                accentPurple().copy(alpha = 0.1f)
                                            else
                                                MaterialTheme.colorScheme.surface
                                        )
                                    ) {
                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .padding(12.dp),
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Checkbox(
                                                checked = isSelected,
                                                onCheckedChange = { checked ->
                                                    selectedStudents = if (checked) {
                                                        selectedStudents + student.studentId
                                                    } else {
                                                        selectedStudents - student.studentId
                                                    }
                                                },
                                                colors = CheckboxDefaults.colors(
                                                    checkedColor = accentPurple()
                                                )
                                            )
                                            Spacer(modifier = Modifier.width(8.dp))
                                            Column(modifier = Modifier.weight(1f)) {
                                                Text(
                                                    text = student.name,
                                                    style = MaterialTheme.typography.bodyMedium,
                                                    fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Normal
                                                )
                                                Text(
                                                    text = student.rollNumber,
                                                    style = MaterialTheme.typography.bodySmall,
                                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                HorizontalDivider()

                // Action buttons
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(onClick = onDismiss, enabled = !isSubmitting) {
                        Text("Cancel")
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = { addSelectedStudents() },
                        enabled = !isSubmitting && selectedStudents.isNotEmpty(),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = accentPurple()
                        )
                    ) {
                        if (isSubmitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.dp,
                                color = Color.White
                            )
                        } else {
                            Text("Add ${selectedStudents.size} Student${if (selectedStudents.size != 1) "s" else ""}")
                        }
                    }
                }
            }
        }
    }
}

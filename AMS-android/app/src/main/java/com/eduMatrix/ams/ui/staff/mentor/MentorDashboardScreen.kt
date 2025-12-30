package com.eduMatrix.ams.ui.staff.mentor

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import android.app.DatePickerDialog
import android.app.TimePickerDialog
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
import java.util.Calendar

/**
 * Mentor dashboard screen showing mentees and pending issues.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MentorDashboardScreen(
    onBack: () -> Unit,
    onAddLog: (studentId: String) -> Unit = {},
    onViewMentee: (studentId: String) -> Unit = {}
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    // Loading states
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }

    // Data
    var dashboardData by remember { mutableStateOf<MentorDashboardData?>(null) }

    // Tab state
    var selectedTab by rememberSaveable { mutableStateOf(0) }
    val tabs = listOf("Mentees", "Issues", "Meetings")

    // Search
    var searchQuery by rememberSaveable { mutableStateOf("") }

    // Add Log Dialog
    var showAddLogDialog by rememberSaveable { mutableStateOf(false) }
    var selectedMenteeForLog by remember { mutableStateOf<Mentee?>(null) }

    // Schedule Meeting Dialog
    var showScheduleMeetingDialog by rememberSaveable { mutableStateOf(false) }

    // Meetings list
    var meetings by remember { mutableStateOf<List<MentorMeeting>>(emptyList()) }
    var loadingMeetings by rememberSaveable { mutableStateOf(false) }

    // Issues list
    var pendingIssues by remember { mutableStateOf<List<MentorLog>>(emptyList()) }
    var loadingIssues by rememberSaveable { mutableStateOf(false) }

    // History dialog
    var showHistoryDialog by rememberSaveable { mutableStateOf(false) }
    var historyStudentId by rememberSaveable { mutableStateOf("") }
    var historyStudentName by rememberSaveable { mutableStateOf("") }
    var historyLogs by remember { mutableStateOf<List<MentorLog>>(emptyList()) }
    var loadingHistory by rememberSaveable { mutableStateOf(false) }

    // Conduct Meeting dialog
    var showConductMeetingDialog by rememberSaveable { mutableStateOf(false) }
    var conductMeetingId by rememberSaveable { mutableIntStateOf(0) }
    var meetingDetails by remember { mutableStateOf<MeetingDetails?>(null) }
    var loadingMeetingDetails by rememberSaveable { mutableStateOf(false) }

    // Load meeting details for conduct/view
    fun loadMeetingDetails(meetingId: Int) {
        scope.launch {
            loadingMeetingDetails = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: return@launch
                val details = withContext(Dispatchers.IO) {
                    ApiService.getMeetingDetails(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        meetingId = meetingId
                    )
                }
                meetingDetails = details
            } catch (e: Exception) {
                snackbarHostState.showSnackbar("Error: ${e.message}")
            } finally {
                loadingMeetingDetails = false
            }
        }
    }

    // Load log history for a student
    fun loadHistory(studentId: String) {
        scope.launch {
            loadingHistory = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: return@launch
                val logs = withContext(Dispatchers.IO) {
                    ApiService.getStudentLogHistory(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        studentId = studentId
                    )
                }
                historyLogs = logs
            } catch (e: Exception) {
                snackbarHostState.showSnackbar("Error loading history: ${e.message}")
            } finally {
                loadingHistory = false
            }
        }
    }

    // Load pending issues when Issues tab is selected
    fun loadIssues() {
        scope.launch {
            loadingIssues = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: return@launch
                val user = AppPrefs.getUser(context) ?: return@launch
                val issues = withContext(Dispatchers.IO) {
                    ApiService.getMentorPendingIssues(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        mentorId = user.userId
                    )
                }
                pendingIssues = issues
            } catch (e: Exception) {
                // Silently fail, user can retry
            } finally {
                loadingIssues = false
            }
        }
    }

    // Load meetings when tab is selected
    fun loadMeetings() {
        val batches = dashboardData?.batches ?: run {
            android.util.Log.e("MentorDashboard", "loadMeetings: dashboardData is null")
            return
        }
        if (batches.isEmpty()) {
            android.util.Log.e("MentorDashboard", "loadMeetings: batches is empty")
            return
        }

        scope.launch {
            loadingMeetings = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: run {
                    android.util.Log.e("MentorDashboard", "loadMeetings: no access token")
                    return@launch
                }
                val allMeetings = mutableListOf<MentorMeeting>()
                android.util.Log.d("MentorDashboard", "loadMeetings: fetching for ${batches.size} batches")
                batches.forEach { batch ->
                    android.util.Log.d("MentorDashboard", "loadMeetings: fetching batch ${batch.batchId}")
                    val batchMeetings = withContext(Dispatchers.IO) {
                        ApiService.getMentorMeetings(BuildConfig.API_BASE_URL, token, batch.batchId)
                    }
                    android.util.Log.d("MentorDashboard", "loadMeetings: got ${batchMeetings.size} meetings for batch ${batch.batchId}")
                    allMeetings.addAll(batchMeetings)
                }
                meetings = allMeetings.sortedByDescending { it.scheduledDate }
                android.util.Log.d("MentorDashboard", "loadMeetings: total ${allMeetings.size} meetings loaded")
            } catch (e: Exception) {
                android.util.Log.e("MentorDashboard", "loadMeetings failed: ${e.message}", e)
                snackbarHostState.showSnackbar("Failed to load meetings: ${e.message}")
            } finally {
                loadingMeetings = false
            }
        }
    }

    // Load dashboard data
    fun loadDashboard() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")
                val data = withContext(Dispatchers.IO) {
                    ApiService.getMentees(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        userId = user.userId
                    )
                }
                dashboardData = data
            } catch (e: ApiException) {
                errorMessage = e.message ?: "Failed to load mentees"
            } catch (e: Exception) {
                errorMessage = "Connection error: ${e.message}"
            } finally {
                isLoading = false
            }
        }
    }

    // Initial load
    LaunchedEffect(Unit) {
        loadDashboard()
    }

    // Filter mentees by search
    val filteredMentees = remember(dashboardData, searchQuery) {
        dashboardData?.mentees?.filter {
            searchQuery.isBlank() ||
            it.name.contains(searchQuery, ignoreCase = true) ||
            it.rollNumber.contains(searchQuery, ignoreCase = true)
        } ?: emptyList()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "My Mentees",
                        style = MaterialTheme.typography.titleLarge
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            Icons.Default.ArrowBack,
                            contentDescription = "Back",
                            tint = Color.White
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MitPurple,
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
        snackbarHost = { SnackbarHost(snackbarHostState) },
        floatingActionButton = {
            // Only show FAB on Meetings tab for scheduling
            if (dashboardData != null && selectedTab == 2 && dashboardData!!.batches.isNotEmpty()) {
                FloatingActionButton(
                    onClick = { showScheduleMeetingDialog = true },
                    containerColor = MitPurple
                ) {
                    Icon(
                        Icons.Default.EventAvailable,
                        contentDescription = "Schedule Meeting",
                        tint = Color.White
                    )
                }
            }
        }
    ) { paddingValues ->
        Column(
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
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(16.dp)
                        ) {
                            CircularProgressIndicator(color = accentPurple())
                            Text(
                                text = "Loading mentees...",
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
                            onClick = { loadDashboard() },
                            colors = ButtonDefaults.buttonColors(containerColor = MitPurple)
                        ) {
                            Icon(Icons.Default.Refresh, contentDescription = null)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Retry")
                        }
                    }
                }

                dashboardData != null -> {
                    // Stats summary
                    MentorStatsSummary(
                        totalMentees = dashboardData!!.totalMentees,
                        openIssues = dashboardData!!.openIssuesCount,
                        batches = dashboardData!!.batches
                    )

                    // Tab row with theme-aware colors
                    TabRow(
                        selectedTabIndex = selectedTab,
                        containerColor = MaterialTheme.colorScheme.surface,
                        contentColor = accentPurple()
                    ) {
                        tabs.forEachIndexed { index, title ->
                            Tab(
                                selected = selectedTab == index,
                                onClick = {
                                    selectedTab = index
                                    // Load issues when Issues tab is selected
                                    if (index == 1) {
                                        loadIssues()
                                    }
                                    // Load meetings when Meetings tab is selected
                                    if (index == 2) {
                                        loadMeetings()
                                    }
                                },
                                text = {
                                    Text(
                                        text = title,
                                        fontWeight = if (selectedTab == index)
                                            FontWeight.SemiBold
                                        else
                                            FontWeight.Normal,
                                        color = if (selectedTab == index)
                                            accentPurple()
                                        else
                                            MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            )
                        }
                    }

                    when (selectedTab) {
                        0 -> MenteesTab(
                            mentees = filteredMentees,
                            searchQuery = searchQuery,
                            onSearchChange = { searchQuery = it },
                            onMenteeClick = onViewMentee,
                            onAddLog = { mentee ->
                                selectedMenteeForLog = mentee
                                showAddLogDialog = true
                            }
                        )
                        1 -> IssuesTab(
                            issues = pendingIssues,
                            allLogs = emptyList(),  // Not used currently
                            isLoading = loadingIssues,
                            onIssueClick = { /* View issue details */ },
                            onResolve = { logId ->
                                scope.launch {
                                    try {
                                        val token = AppPrefs.getAccessToken(context)
                                            ?: throw Exception("Not authenticated")
                                        withContext(Dispatchers.IO) {
                                            ApiService.updateLogStatus(
                                                baseUrl = BuildConfig.API_BASE_URL,
                                                accessToken = token,
                                                logId = logId,
                                                newStatus = "Resolved"
                                            )
                                        }
                                        snackbarHostState.showSnackbar("Issue resolved")
                                        loadIssues() // Refresh issues
                                    } catch (e: Exception) {
                                        snackbarHostState.showSnackbar("Error: ${e.message}")
                                    }
                                }
                            },
                            onEscalate = { logId ->
                                scope.launch {
                                    try {
                                        val token = AppPrefs.getAccessToken(context)
                                            ?: throw Exception("Not authenticated")
                                        withContext(Dispatchers.IO) {
                                            ApiService.updateLogStatus(
                                                baseUrl = BuildConfig.API_BASE_URL,
                                                accessToken = token,
                                                logId = logId,
                                                newStatus = "Escalated"
                                            )
                                        }
                                        snackbarHostState.showSnackbar("Issue escalated")
                                        loadIssues() // Refresh issues
                                    } catch (e: Exception) {
                                        snackbarHostState.showSnackbar("Error: ${e.message}")
                                    }
                                }
                            },
                            onViewHistory = { studentId, studentName ->
                                historyStudentId = studentId
                                historyStudentName = studentName
                                showHistoryDialog = true
                                loadHistory(studentId)
                            }
                        )
                        2 -> MeetingsTab(
                            meetings = meetings,
                            isLoading = loadingMeetings,
                            onRefresh = { loadMeetings() },
                            onConductMeeting = { meeting ->
                                conductMeetingId = meeting.meetingId
                                meetingDetails = null
                                showConductMeetingDialog = true
                                loadMeetingDetails(meeting.meetingId)
                            },
                            onViewMeeting = { meeting ->
                                conductMeetingId = meeting.meetingId
                                meetingDetails = null
                                showConductMeetingDialog = true
                                loadMeetingDetails(meeting.meetingId)
                            }
                        )
                    }
                }

                else -> {
                    EmptyState(
                        icon = Icons.Outlined.People,
                        title = "No Mentees Assigned",
                        message = "You don't have any mentees assigned yet.",
                        modifier = Modifier.fillMaxSize()
                    )
                }
            }
        }
    }

    // Add Log Dialog
    if (showAddLogDialog && selectedMenteeForLog != null) {
        AddLogDialog(
            mentee = selectedMenteeForLog!!,
            onDismiss = {
                showAddLogDialog = false
                selectedMenteeForLog = null
            },
            onSubmit = { category, remarks, action ->
                scope.launch {
                    try {
                        val token = AppPrefs.getAccessToken(context)
                            ?: throw Exception("Not authenticated")
                        val user = AppPrefs.getUser(context)
                            ?: throw Exception("User not found")

                        withContext(Dispatchers.IO) {
                            ApiService.addMentorLog(
                                baseUrl = BuildConfig.API_BASE_URL,
                                accessToken = token,
                                studentId = selectedMenteeForLog!!.studentId,
                                mentorId = user.userId,
                                category = category,
                                remarks = remarks,
                                actionTaken = action
                            )
                        }

                        snackbarHostState.showSnackbar("Log added successfully")
                        showAddLogDialog = false
                        selectedMenteeForLog = null
                        loadDashboard() // Refresh
                    } catch (e: Exception) {
                        snackbarHostState.showSnackbar("Error: ${e.message}")
                    }
                }
            }
        )
    }

    // Schedule Meeting Dialog
    if (showScheduleMeetingDialog && dashboardData?.batches?.isNotEmpty() == true) {
        ScheduleMeetingDialog(
            batches = dashboardData!!.batches,
            onDismiss = { showScheduleMeetingDialog = false },
            onSubmit = { batchId, date, time, agenda, venue ->
                scope.launch {
                    try {
                        val token = AppPrefs.getAccessToken(context)
                            ?: throw Exception("Not authenticated")
                        val user = AppPrefs.getUser(context)
                            ?: throw Exception("User not found")

                        withContext(Dispatchers.IO) {
                            ApiService.scheduleMentorMeeting(
                                baseUrl = BuildConfig.API_BASE_URL,
                                accessToken = token,
                                mentorId = user.userId,
                                batchId = batchId,
                                date = date,
                                time = time,
                                agenda = agenda,
                                venue = venue
                            )
                        }

                        snackbarHostState.showSnackbar("Meeting scheduled successfully")
                        showScheduleMeetingDialog = false
                        loadMeetings() // Refresh meetings
                    } catch (e: Exception) {
                        snackbarHostState.showSnackbar("Error: ${e.message}")
                    }
                }
            }
        )
    }

    // Log History Dialog
    if (showHistoryDialog) {
        LogHistoryDialog(
            studentName = historyStudentName,
            logs = historyLogs,
            isLoading = loadingHistory,
            onDismiss = {
                showHistoryDialog = false
                historyLogs = emptyList()
            }
        )
    }

    // Conduct Meeting Dialog
    if (showConductMeetingDialog) {
        ConductMeetingDialog(
            meetingDetails = meetingDetails,
            isLoading = loadingMeetingDetails,
            onDismiss = {
                showConductMeetingDialog = false
                meetingDetails = null
            },
            onSubmit = { venue, discussionPoints, summary, attendanceData, issues ->
                scope.launch {
                    try {
                        val token = AppPrefs.getAccessToken(context)
                            ?: throw Exception("Not authenticated")

                        withContext(Dispatchers.IO) {
                            ApiService.conductMeeting(
                                baseUrl = BuildConfig.API_BASE_URL,
                                accessToken = token,
                                meetingId = conductMeetingId,
                                venue = venue,
                                discussionPoints = discussionPoints,
                                summary = summary,
                                attendance = attendanceData
                            )
                        }

                        snackbarHostState.showSnackbar("Meeting completed successfully")
                        showConductMeetingDialog = false
                        meetingDetails = null
                        loadMeetings() // Refresh meetings
                    } catch (e: Exception) {
                        snackbarHostState.showSnackbar("Error: ${e.message}")
                    }
                }
            },
            onAddIssue = { studentId, description, category, action ->
                scope.launch {
                    try {
                        val token = AppPrefs.getAccessToken(context)
                            ?: throw Exception("Not authenticated")

                        val issue = withContext(Dispatchers.IO) {
                            ApiService.addMeetingIssue(
                                baseUrl = BuildConfig.API_BASE_URL,
                                accessToken = token,
                                meetingId = conductMeetingId,
                                raisedByStudentId = studentId,
                                issueDescription = description,
                                category = category,
                                actionTaken = action
                            )
                        }

                        // Update local meeting details with new issue
                        meetingDetails = meetingDetails?.copy(
                            issues = meetingDetails!!.issues + issue
                        )
                        snackbarHostState.showSnackbar("Issue recorded")
                    } catch (e: Exception) {
                        snackbarHostState.showSnackbar("Error: ${e.message}")
                    }
                }
            }
        )
    }
}

/**
 * Stats summary card.
 */
@Composable
private fun MentorStatsSummary(
    totalMentees: Int,
    openIssues: Int,
    batches: List<MentorBatchDetail>
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp),
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
            // Stats row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                StatColumn(
                    label = "Total Mentees",
                    value = "$totalMentees",
                    color = accentPurple()
                )
                StatColumn(
                    label = "Open Issues",
                    value = "$openIssues",
                    color = if (openIssues > 0) StatusRed else StatusGreen
                )
            }

            // Batch chips - show class-section (batch name) format
            if (batches.isNotEmpty()) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    batches.forEach { batch ->
                        val displayName = "${batch.classLevel}-${batch.sectionName} (${batch.batchName})"
                        Surface(
                            color = MitTeal.copy(alpha = 0.15f),
                            shape = RoundedCornerShape(16.dp),
                            modifier = Modifier.padding(horizontal = 4.dp)
                        ) {
                            Text(
                                text = displayName,
                                style = MaterialTheme.typography.labelMedium,
                                color = accentTeal(),
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatColumn(
    label: String,
    value: String,
    color: Color
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
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

/**
 * Mentees tab with list and search.
 */
@Composable
private fun MenteesTab(
    mentees: List<Mentee>,
    searchQuery: String,
    onSearchChange: (String) -> Unit,
    onMenteeClick: (String) -> Unit,
    onAddLog: (Mentee) -> Unit
) {
    Column(modifier = Modifier.fillMaxSize()) {
        // Search bar
        OutlinedTextField(
            value = searchQuery,
            onValueChange = onSearchChange,
            placeholder = { Text("Search by name or roll number...") },
            leadingIcon = {
                Icon(
                    Icons.Default.Search,
                    contentDescription = null,
                    tint = accentPurple()
                )
            },
            trailingIcon = {
                if (searchQuery.isNotBlank()) {
                    IconButton(onClick = { onSearchChange("") }) {
                        Icon(Icons.Default.Clear, contentDescription = "Clear")
                    }
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            singleLine = true,
            shape = RoundedCornerShape(12.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = MitPurple,
                cursorColor = MitPurple
            )
        )

        if (mentees.isEmpty()) {
            EmptyState(
                icon = Icons.Outlined.SearchOff,
                title = "No Mentees Found",
                message = if (searchQuery.isNotBlank())
                    "No mentees match your search"
                else
                    "No mentees assigned to you",
                modifier = Modifier.fillMaxSize()
            )
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(
                    items = mentees,
                    key = { it.studentId }
                ) { mentee ->
                    MenteeCard(
                        mentee = mentee,
                        onClick = { onMenteeClick(mentee.studentId) },
                        onAddLog = { onAddLog(mentee) }
                    )
                }

                item {
                    Spacer(modifier = Modifier.height(80.dp)) // For FAB
                }
            }
        }
    }
}

/**
 * Individual mentee card.
 */
@Composable
private fun MenteeCard(
    mentee: Mentee,
    onClick: () -> Unit,
    onAddLog: () -> Unit
) {
    val attendanceColor = when {
        (mentee.attendancePercentage ?: 0.0) >= 75 -> StatusGreen
        (mentee.attendancePercentage ?: 0.0) >= 50 -> StatusYellow
        else -> StatusRed
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() },
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Avatar
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(CircleShape)
                    .background(MitPurple.copy(alpha = 0.1f)),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = mentee.name.take(1).uppercase(),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = accentPurple()
                )
            }

            // Info
            Column(modifier = Modifier.weight(1f)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = mentee.name,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (mentee.openIssues > 0) {
                        Surface(
                            color = StatusRedLight,
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Text(
                                text = "${mentee.openIssues} issue${if (mentee.openIssues > 1) "s" else ""}",
                                style = MaterialTheme.typography.labelSmall,
                                color = StatusRed,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                }
                Text(
                    text = mentee.rollNumber,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Attendance percentage
            Column(
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "${(mentee.attendancePercentage ?: 0.0).toInt()}%",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = attendanceColor
                )
                Text(
                    text = "Attendance",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Add log button
            IconButton(
                onClick = onAddLog,
                modifier = Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .background(MitPurple.copy(alpha = 0.1f))
            ) {
                Icon(
                    Icons.Default.NoteAdd,
                    contentDescription = "Add Log",
                    tint = accentPurple()
                )
            }
        }
    }
}

/**
 * Issues tab showing counseling logs grouped by student.
 */
@Composable
private fun IssuesTab(
    issues: List<MentorLog>,
    allLogs: List<MentorLog>,  // All logs including resolved for history
    isLoading: Boolean,
    onIssueClick: (Int) -> Unit,
    onResolve: (Int) -> Unit,
    onEscalate: (Int) -> Unit,
    onViewHistory: (String, String) -> Unit  // studentId, studentName
) {
    // Track which students are expanded
    var expandedStudents by remember { mutableStateOf(setOf<String>()) }

    // Group pending issues by student (Open + Escalated - these need action)
    val groupedIssues = remember(issues) {
        issues
            .filter { it.status == IssueStatus.OPEN || it.status == IssueStatus.ESCALATED }
            .groupBy { it.studentId }
    }

    when {
        isLoading -> {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(color = accentPurple())
            }
        }
        groupedIssues.isEmpty() -> {
            EmptyState(
                icon = Icons.Outlined.CheckCircle,
                title = "No Open Issues",
                message = "All issues have been resolved",
                modifier = Modifier.fillMaxSize()
            )
        }
        else -> {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                groupedIssues.forEach { (studentId, studentIssues) ->
                    val isExpanded = expandedStudents.contains(studentId)
                    val studentName = studentIssues.firstOrNull()?.studentName ?: "Unknown"
                    val openCount = studentIssues.count { it.status == IssueStatus.OPEN }
                    val escalatedCount = studentIssues.count { it.status == IssueStatus.ESCALATED }

                    // Student header card
                    item(key = "header_$studentId") {
                        StudentIssueHeader(
                            studentName = studentName,
                            openCount = openCount,
                            escalatedCount = escalatedCount,
                            isExpanded = isExpanded,
                            onClick = {
                                expandedStudents = if (isExpanded) {
                                    expandedStudents - studentId
                                } else {
                                    expandedStudents + studentId
                                }
                            },
                            onViewHistory = { onViewHistory(studentId, studentName) }
                        )
                    }

                    // Expanded issue cards
                    if (isExpanded) {
                        items(
                            items = studentIssues,
                            key = { "issue_${it.logId}" }
                        ) { issue ->
                            IssueCard(
                                issue = issue,
                                onClick = { onIssueClick(issue.logId) },
                                onResolve = { onResolve(issue.logId) },
                                onEscalate = { onEscalate(issue.logId) }
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * Student header card showing name and issue count.
 */
@Composable
private fun StudentIssueHeader(
    studentName: String,
    openCount: Int,
    escalatedCount: Int,
    isExpanded: Boolean,
    onClick: () -> Unit,
    onViewHistory: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() },
        colors = CardDefaults.cardColors(
            containerColor = if (isExpanded)
                accentPurple().copy(alpha = 0.1f)
            else
                MaterialTheme.colorScheme.surface
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = if (isExpanded) 2.dp else 1.dp),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Avatar
                    Box(
                        modifier = Modifier
                            .size(40.dp)
                            .clip(CircleShape)
                            .background(accentPurple().copy(alpha = 0.2f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = studentName.take(1).uppercase(),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = accentPurple()
                        )
                    }

                    Column {
                        Text(
                            text = studentName,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                        // Show counts for open and escalated
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            if (openCount > 0) {
                                Text(
                                    text = "$openCount open",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = StatusYellow
                                )
                            }
                            if (escalatedCount > 0) {
                                Text(
                                    text = "$escalatedCount escalated",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = StatusRed
                                )
                            }
                        }
                    }
                }

                Icon(
                    imageVector = if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    contentDescription = if (isExpanded) "Collapse" else "Expand",
                    tint = accentPurple()
                )
            }

            // View History button
            TextButton(
                onClick = onViewHistory,
                modifier = Modifier.align(Alignment.End)
            ) {
                Icon(
                    Icons.Outlined.History,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                    tint = accentTeal()
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "View History",
                    style = MaterialTheme.typography.labelMedium,
                    color = accentTeal()
                )
            }
        }
    }
}

/**
 * Issue card with action buttons (Resolve/Escalate).
 */
@Composable
private fun IssueCard(
    issue: MentorLog,
    onClick: () -> Unit,
    onResolve: () -> Unit,
    onEscalate: () -> Unit
) {
    val statusColor = when (issue.status) {
        IssueStatus.OPEN -> StatusYellow
        IssueStatus.IN_PROGRESS -> StatusBlue
        IssueStatus.ESCALATED -> StatusRed
        IssueStatus.RESOLVED -> StatusGreen
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 24.dp), // Indent to show hierarchy
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Category and Status chips
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Category chip
                    Surface(
                        color = accentTeal().copy(alpha = 0.1f),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Text(
                            text = issue.category.toDisplayString(),
                            style = MaterialTheme.typography.labelSmall,
                            color = accentTeal(),
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }

                    // Status chip
                    Surface(
                        color = statusColor.copy(alpha = 0.1f),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Text(
                            text = issue.status.name,
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Medium,
                            color = statusColor,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                }

                // Date
                Text(
                    text = issue.createdAt,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                )
            }

            Text(
                text = issue.description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis
            )

            // Action buttons - different based on status
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (issue.status == IssueStatus.ESCALATED) {
                    // Escalated issues only show Resolve button (full width)
                    OutlinedButton(
                        onClick = onResolve,
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = StatusGreen
                        ),
                        border = androidx.compose.foundation.BorderStroke(1.dp, StatusGreen)
                    ) {
                        Icon(
                            Icons.Outlined.CheckCircle,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Mark Resolved", style = MaterialTheme.typography.labelMedium)
                    }
                } else {
                    // Open issues show both Resolve and Escalate buttons
                    OutlinedButton(
                        onClick = onResolve,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = StatusGreen
                        ),
                        border = androidx.compose.foundation.BorderStroke(1.dp, StatusGreen)
                    ) {
                        Icon(
                            Icons.Outlined.CheckCircle,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Resolved", style = MaterialTheme.typography.labelMedium)
                    }

                    OutlinedButton(
                        onClick = onEscalate,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = StatusRed
                        ),
                        border = androidx.compose.foundation.BorderStroke(1.dp, StatusRed)
                    ) {
                        Icon(
                            Icons.Outlined.KeyboardArrowUp,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Escalate", style = MaterialTheme.typography.labelMedium)
                    }
                }
            }
        }
    }
}

/**
 * Meetings tab showing scheduled mentor meetings.
 */
@Composable
private fun MeetingsTab(
    meetings: List<MentorMeeting>,
    isLoading: Boolean,
    onRefresh: () -> Unit,
    onConductMeeting: (MentorMeeting) -> Unit,
    onViewMeeting: (MentorMeeting) -> Unit
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
        meetings.isEmpty() -> {
            EmptyState(
                icon = Icons.Outlined.EventNote,
                title = "No Meetings Scheduled",
                message = "Tap + to schedule a meeting with your mentees",
                modifier = Modifier.fillMaxSize()
            )
        }
        else -> {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(
                    items = meetings,
                    key = { "${it.meetingId}_${it.scheduledDate}_${it.scheduledTime}" }
                ) { meeting ->
                    MeetingCard(
                        meeting = meeting,
                        onConductClick = { onConductMeeting(meeting) },
                        onViewClick = { onViewMeeting(meeting) }
                    )
                }

                item {
                    Spacer(modifier = Modifier.height(80.dp)) // For FAB
                }
            }
        }
    }
}

/**
 * Meeting card.
 */
@Composable
private fun MeetingCard(
    meeting: MentorMeeting,
    onConductClick: () -> Unit,
    onViewClick: () -> Unit
) {
    // Use theme-aware colors for dark mode readability
    val statusColor = if (meeting.isCompleted) StatusGreen else accentPurple()

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
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        Icons.Outlined.Event,
                        contentDescription = null,
                        tint = statusColor,
                        modifier = Modifier.size(20.dp)
                    )
                    Text(
                        text = meeting.scheduledDate,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold
                    )
                }
                Surface(
                    color = statusColor.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = if (meeting.isCompleted) "Completed" else "Scheduled",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Medium,
                        color = statusColor,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Icon(
                        Icons.Outlined.Schedule,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(16.dp)
                    )
                    Text(
                        text = meeting.scheduledTime,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                if (!meeting.venue.isNullOrBlank()) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Icon(
                            Icons.Outlined.LocationOn,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(16.dp)
                        )
                        Text(
                            text = meeting.venue,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
            }

            Text(
                text = meeting.agenda,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )

            if (meeting.attendeeCount != null && meeting.isCompleted) {
                Text(
                    text = "${meeting.attendeeCount} attended",
                    style = MaterialTheme.typography.labelSmall,
                    color = StatusGreen
                )
            }

            // Action buttons
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 4.dp),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically
            ) {
                if (meeting.isCompleted) {
                    OutlinedButton(
                        onClick = onViewClick,
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = StatusGreen),
                        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp)
                    ) {
                        Icon(
                            Icons.Outlined.Visibility,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("View Details", style = MaterialTheme.typography.labelMedium)
                    }
                } else {
                    Button(
                        onClick = onConductClick,
                        colors = ButtonDefaults.buttonColors(containerColor = MitPurple),
                        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp)
                    ) {
                        Icon(
                            Icons.Outlined.PlayArrow,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Conduct", style = MaterialTheme.typography.labelMedium)
                    }
                }
            }
        }
    }
}

/**
 * Add log dialog.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddLogDialog(
    mentee: Mentee,
    onDismiss: () -> Unit,
    onSubmit: (category: String, remarks: String, action: String?) -> Unit
) {
    var selectedCategory by rememberSaveable { mutableStateOf("Academic") }
    var remarks by rememberSaveable { mutableStateOf("") }
    var actionTaken by rememberSaveable { mutableStateOf("") }
    var expanded by rememberSaveable { mutableStateOf(false) }
    var isSubmitting by rememberSaveable { mutableStateOf(false) }

    val categories = listOf("Academic", "Personal", "Disciplinary", "Financial", "Other")

    AlertDialog(
        onDismissRequest = { if (!isSubmitting) onDismiss() },
        title = {
            Text("Add Counseling Log")
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Student info
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MitPurple.copy(alpha = 0.1f)
                    )
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(36.dp)
                                .clip(CircleShape)
                                .background(MitPurple),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = mentee.name.take(1).uppercase(),
                                style = MaterialTheme.typography.titleMedium,
                                color = Color.White
                            )
                        }
                        Column {
                            Text(
                                text = mentee.name,
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold
                            )
                            Text(
                                text = mentee.rollNumber,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }

                // Category dropdown
                ExposedDropdownMenuBox(
                    expanded = expanded,
                    onExpandedChange = { expanded = !expanded }
                ) {
                    OutlinedTextField(
                        value = selectedCategory,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Category") },
                        trailingIcon = {
                            ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded)
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        shape = RoundedCornerShape(12.dp)
                    )
                    ExposedDropdownMenu(
                        expanded = expanded,
                        onDismissRequest = { expanded = false }
                    ) {
                        categories.forEach { category ->
                            DropdownMenuItem(
                                text = { Text(category) },
                                onClick = {
                                    selectedCategory = category
                                    expanded = false
                                }
                            )
                        }
                    }
                }

                // Remarks
                OutlinedTextField(
                    value = remarks,
                    onValueChange = { remarks = it },
                    label = { Text("Remarks *") },
                    placeholder = { Text("Describe the issue or discussion...") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3,
                    maxLines = 5,
                    shape = RoundedCornerShape(12.dp)
                )

                // Action taken
                OutlinedTextField(
                    value = actionTaken,
                    onValueChange = { actionTaken = it },
                    label = { Text("Action Taken (Optional)") },
                    placeholder = { Text("What action was taken?") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2,
                    maxLines = 3,
                    shape = RoundedCornerShape(12.dp)
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (remarks.isNotBlank()) {
                        isSubmitting = true
                        onSubmit(
                            selectedCategory,
                            remarks,
                            actionTaken.ifBlank { null }
                        )
                    }
                },
                enabled = remarks.isNotBlank() && !isSubmitting,
                colors = ButtonDefaults.buttonColors(containerColor = MitPurple)
            ) {
                if (isSubmitting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        color = Color.White,
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Save Log")
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isSubmitting
            ) {
                Text("Cancel")
            }
        }
    )
}

/**
 * Schedule meeting dialog with DatePicker and TimePicker.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ScheduleMeetingDialog(
    batches: List<MentorBatchDetail>,
    onDismiss: () -> Unit,
    onSubmit: (batchId: Int, date: String, time: String, agenda: String, venue: String?) -> Unit
) {
    val context = LocalContext.current
    var selectedBatch by remember { mutableStateOf(batches.firstOrNull()) }
    var date by rememberSaveable { mutableStateOf("") }
    var time by rememberSaveable { mutableStateOf("") }
    var agenda by rememberSaveable { mutableStateOf("") }
    var venue by rememberSaveable { mutableStateOf("") }
    var batchExpanded by rememberSaveable { mutableStateOf(false) }
    var isSubmitting by rememberSaveable { mutableStateOf(false) }

    // Date picker
    val calendar = Calendar.getInstance()
    val datePickerDialog = remember {
        DatePickerDialog(
            context,
            { _, year, month, dayOfMonth ->
                date = String.format("%04d-%02d-%02d", year, month + 1, dayOfMonth)
            },
            calendar.get(Calendar.YEAR),
            calendar.get(Calendar.MONTH),
            calendar.get(Calendar.DAY_OF_MONTH)
        ).apply {
            datePicker.minDate = System.currentTimeMillis() // Can't schedule in the past
        }
    }

    // Time picker
    val timePickerDialog = remember {
        TimePickerDialog(
            context,
            { _, hourOfDay, minute ->
                time = String.format("%02d:%02d", hourOfDay, minute)
            },
            calendar.get(Calendar.HOUR_OF_DAY),
            calendar.get(Calendar.MINUTE),
            true // 24-hour format
        )
    }

    AlertDialog(
        onDismissRequest = { if (!isSubmitting) onDismiss() },
        title = {
            Text("Schedule Meeting")
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Batch selection
                if (batches.size > 1) {
                    ExposedDropdownMenuBox(
                        expanded = batchExpanded,
                        onExpandedChange = { batchExpanded = !batchExpanded }
                    ) {
                        OutlinedTextField(
                            value = selectedBatch?.let { "${it.classLevel}-${it.sectionName} (${it.batchName})" } ?: "Select Batch",
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Batch") },
                            trailingIcon = {
                                ExposedDropdownMenuDefaults.TrailingIcon(expanded = batchExpanded)
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .menuAnchor(),
                            shape = RoundedCornerShape(12.dp)
                        )
                        ExposedDropdownMenu(
                            expanded = batchExpanded,
                            onDismissRequest = { batchExpanded = false }
                        ) {
                            batches.forEach { batch ->
                                DropdownMenuItem(
                                    text = { Text("${batch.classLevel}-${batch.sectionName} (${batch.batchName}) - ${batch.studentCount} students") },
                                    onClick = {
                                        selectedBatch = batch
                                        batchExpanded = false
                                    }
                                )
                            }
                        }
                    }
                } else if (batches.isNotEmpty()) {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MitPurple.copy(alpha = 0.1f)
                        )
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Icon(
                                Icons.Outlined.People,
                                contentDescription = null,
                                tint = accentPurple()
                            )
                            Column {
                                Text(
                                    text = "${batches.first().classLevel}-${batches.first().sectionName} (${batches.first().batchName})",
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = FontWeight.SemiBold
                                )
                                Text(
                                    text = "${batches.first().studentCount} students",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }

                // Date picker field
                OutlinedTextField(
                    value = date,
                    onValueChange = { },
                    readOnly = true,
                    label = { Text("Date *") },
                    placeholder = { Text("Select date") },
                    leadingIcon = {
                        Icon(Icons.Outlined.CalendarMonth, contentDescription = null)
                    },
                    trailingIcon = {
                        IconButton(onClick = { datePickerDialog.show() }) {
                            Icon(
                                Icons.Default.EditCalendar,
                                contentDescription = "Select date",
                                tint = accentPurple()
                            )
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { datePickerDialog.show() },
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp)
                )

                // Time picker field
                OutlinedTextField(
                    value = time,
                    onValueChange = { },
                    readOnly = true,
                    label = { Text("Time *") },
                    placeholder = { Text("Select time") },
                    leadingIcon = {
                        Icon(Icons.Outlined.Schedule, contentDescription = null)
                    },
                    trailingIcon = {
                        IconButton(onClick = { timePickerDialog.show() }) {
                            Icon(
                                Icons.Default.AccessTime,
                                contentDescription = "Select time",
                                tint = accentPurple()
                            )
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { timePickerDialog.show() },
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp)
                )

                // Venue
                OutlinedTextField(
                    value = venue,
                    onValueChange = { venue = it },
                    label = { Text("Venue") },
                    placeholder = { Text("e.g., Room C-101, HOD Chamber") },
                    leadingIcon = {
                        Icon(Icons.Outlined.LocationOn, contentDescription = null)
                    },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp)
                )

                // Agenda
                OutlinedTextField(
                    value = agenda,
                    onValueChange = { agenda = it },
                    label = { Text("Agenda *") },
                    placeholder = { Text("Meeting agenda/topic...") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2,
                    maxLines = 4,
                    shape = RoundedCornerShape(12.dp)
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (selectedBatch != null && date.isNotBlank() && time.isNotBlank() && agenda.isNotBlank()) {
                        isSubmitting = true
                        onSubmit(selectedBatch!!.batchId, date, time, agenda, venue.ifBlank { null })
                    }
                },
                enabled = selectedBatch != null && date.isNotBlank() && time.isNotBlank() && agenda.isNotBlank() && !isSubmitting,
                colors = ButtonDefaults.buttonColors(containerColor = MitPurple)
            ) {
                if (isSubmitting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        color = Color.White,
                        strokeWidth = 2.dp
                    )
                } else {
                    Text("Schedule")
                }
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !isSubmitting
            ) {
                Text("Cancel")
            }
        }
    )
}

/**
 * Dialog showing log history for a student.
 */
@Composable
private fun LogHistoryDialog(
    studentName: String,
    logs: List<MentorLog>,
    isLoading: Boolean,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text("Log History - $studentName")
        },
        text = {
            when {
                isLoading -> {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(200.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(color = accentPurple())
                    }
                }
                logs.isEmpty() -> {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(100.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "No logs found",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                else -> {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 400.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(logs, key = { it.logId }) { log ->
                            HistoryLogCard(log = log)
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text("Close")
            }
        }
    )
}

/**
 * Card for displaying a log in history.
 */
@Composable
private fun HistoryLogCard(log: MentorLog) {
    val statusColor = when (log.status) {
        IssueStatus.OPEN -> StatusYellow
        IssueStatus.IN_PROGRESS -> StatusBlue
        IssueStatus.ESCALATED -> StatusRed
        IssueStatus.RESOLVED -> StatusGreen
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Category
                Surface(
                    color = accentTeal().copy(alpha = 0.1f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = log.category.toDisplayString(),
                        style = MaterialTheme.typography.labelSmall,
                        color = accentTeal(),
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }

                // Status
                Surface(
                    color = statusColor.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = log.status.name,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Medium,
                        color = statusColor,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }
            }

            Text(
                text = log.description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )

            Text(
                text = log.createdAt,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
            )
        }
    }
}

/**
 * Dialog for conducting a meeting - mark attendance, add issues, and complete meeting.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ConductMeetingDialog(
    meetingDetails: MeetingDetails?,
    isLoading: Boolean,
    onDismiss: () -> Unit,
    onSubmit: (venue: String?, discussionPoints: String?, summary: String?, attendance: List<Map<String, Any?>>, issues: List<MeetingIssue>) -> Unit,
    onAddIssue: (studentId: String?, description: String, category: String, action: String?) -> Unit
) {
    var venue by rememberSaveable { mutableStateOf(meetingDetails?.meeting?.venue ?: "") }
    var discussionPoints by rememberSaveable { mutableStateOf(meetingDetails?.meeting?.discussionPoints ?: "") }
    var summary by rememberSaveable { mutableStateOf(meetingDetails?.meeting?.summary ?: "") }
    var attendanceMap by remember { mutableStateOf<Map<String, Boolean>>(emptyMap()) }
    var isSubmitting by rememberSaveable { mutableStateOf(false) }
    var showAddIssueDialog by rememberSaveable { mutableStateOf(false) }

    // Initialize attendance map when details load
    LaunchedEffect(meetingDetails) {
        meetingDetails?.let { details ->
            venue = details.meeting.venue ?: ""
            discussionPoints = details.meeting.discussionPoints ?: ""
            summary = details.meeting.summary ?: ""

            val initialAttendance = mutableMapOf<String, Boolean>()
            details.students.forEach { student ->
                val existingAtt = details.attendance.find { it.studentId == student.studentId }
                initialAttendance[student.studentId] = existingAtt?.attended ?: false
            }
            attendanceMap = initialAttendance
        }
    }

    val isViewMode = meetingDetails?.meeting?.isCompleted == true

    Dialog(
        onDismissRequest = { if (!isSubmitting) onDismiss() },
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth(0.95f)
                .fillMaxHeight(0.9f),
            shape = RoundedCornerShape(16.dp),
            color = MaterialTheme.colorScheme.surface
        ) {
            Column(
                modifier = Modifier.fillMaxSize()
            ) {
                // Header
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            text = if (isViewMode) "Meeting Details" else "Conduct Meeting",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold
                        )
                        if (meetingDetails != null) {
                            Text(
                                text = "${meetingDetails.meeting.scheduledDate} at ${meetingDetails.meeting.scheduledTime}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                    IconButton(onClick = { if (!isSubmitting) onDismiss() }) {
                        Icon(Icons.Default.Close, contentDescription = "Close")
                    }
                }

                HorizontalDivider()

                when {
                    isLoading -> {
                        Box(
                            modifier = Modifier.fillMaxSize(),
                            contentAlignment = Alignment.Center
                        ) {
                            CircularProgressIndicator(color = accentPurple())
                        }
                    }
                    meetingDetails == null -> {
                        Box(
                            modifier = Modifier.fillMaxSize(),
                            contentAlignment = Alignment.Center
                        ) {
                            Text("Failed to load meeting details")
                        }
                    }
                    else -> {
                        LazyColumn(
                            modifier = Modifier
                                .weight(1f)
                                .fillMaxWidth(),
                            contentPadding = PaddingValues(16.dp),
                            verticalArrangement = Arrangement.spacedBy(16.dp)
                        ) {
                            // Meeting Info Section
                            item {
                                Text(
                                    text = "Meeting Info",
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.SemiBold
                                )
                            }

                            item {
                                OutlinedTextField(
                                    value = venue,
                                    onValueChange = { if (!isViewMode) venue = it },
                                    label = { Text("Venue") },
                                    leadingIcon = { Icon(Icons.Outlined.LocationOn, contentDescription = null) },
                                    modifier = Modifier.fillMaxWidth(),
                                    singleLine = true,
                                    readOnly = isViewMode,
                                    shape = RoundedCornerShape(12.dp)
                                )
                            }

                            item {
                                OutlinedTextField(
                                    value = discussionPoints,
                                    onValueChange = { if (!isViewMode) discussionPoints = it },
                                    label = { Text("Discussion Points") },
                                    modifier = Modifier.fillMaxWidth(),
                                    minLines = 2,
                                    maxLines = 4,
                                    readOnly = isViewMode,
                                    shape = RoundedCornerShape(12.dp)
                                )
                            }

                            item {
                                OutlinedTextField(
                                    value = summary,
                                    onValueChange = { if (!isViewMode) summary = it },
                                    label = { Text("Meeting Summary") },
                                    modifier = Modifier.fillMaxWidth(),
                                    minLines = 2,
                                    maxLines = 4,
                                    readOnly = isViewMode,
                                    shape = RoundedCornerShape(12.dp)
                                )
                            }

                            // Attendance Section
                            item {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = "Attendance (${attendanceMap.count { it.value }}/${meetingDetails.students.size})",
                                        style = MaterialTheme.typography.titleMedium,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                    if (!isViewMode) {
                                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                            TextButton(onClick = {
                                                attendanceMap = meetingDetails.students.associate { it.studentId to true }
                                            }) {
                                                Text("All Present", style = MaterialTheme.typography.labelSmall)
                                            }
                                            TextButton(onClick = {
                                                attendanceMap = meetingDetails.students.associate { it.studentId to false }
                                            }) {
                                                Text("All Absent", style = MaterialTheme.typography.labelSmall)
                                            }
                                        }
                                    }
                                }
                            }

                            items(meetingDetails.students) { student ->
                                Card(
                                    modifier = Modifier.fillMaxWidth(),
                                    colors = CardDefaults.cardColors(
                                        containerColor = if (attendanceMap[student.studentId] == true)
                                            StatusGreen.copy(alpha = 0.1f)
                                        else
                                            MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                                    ),
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .clickable(enabled = !isViewMode) {
                                                attendanceMap = attendanceMap.toMutableMap().apply {
                                                    put(student.studentId, !(get(student.studentId) ?: false))
                                                }
                                            }
                                            .padding(12.dp),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column {
                                            Text(
                                                text = student.name,
                                                style = MaterialTheme.typography.bodyMedium,
                                                fontWeight = FontWeight.Medium
                                            )
                                            Text(
                                                text = student.rollNo,
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                        }
                                        Checkbox(
                                            checked = attendanceMap[student.studentId] ?: false,
                                            onCheckedChange = { checked ->
                                                if (!isViewMode) {
                                                    attendanceMap = attendanceMap.toMutableMap().apply {
                                                        put(student.studentId, checked)
                                                    }
                                                }
                                            },
                                            enabled = !isViewMode,
                                            colors = CheckboxDefaults.colors(
                                                checkedColor = StatusGreen,
                                                checkmarkColor = Color.White
                                            )
                                        )
                                    }
                                }
                            }

                            // Issues Section
                            item {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = "Issues Raised (${meetingDetails.issues.size})",
                                        style = MaterialTheme.typography.titleMedium,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                    if (!isViewMode) {
                                        OutlinedButton(
                                            onClick = { showAddIssueDialog = true },
                                            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                                        ) {
                                            Icon(
                                                Icons.Default.Add,
                                                contentDescription = null,
                                                modifier = Modifier.size(16.dp)
                                            )
                                            Spacer(modifier = Modifier.width(4.dp))
                                            Text("Add Issue", style = MaterialTheme.typography.labelSmall)
                                        }
                                    }
                                }
                            }

                            if (meetingDetails.issues.isEmpty()) {
                                item {
                                    Card(
                                        colors = CardDefaults.cardColors(
                                            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f)
                                        ),
                                        shape = RoundedCornerShape(8.dp)
                                    ) {
                                        Text(
                                            text = "No issues recorded yet",
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .padding(16.dp),
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            textAlign = TextAlign.Center
                                        )
                                    }
                                }
                            } else {
                                items(meetingDetails.issues) { issue ->
                                    Card(
                                        modifier = Modifier.fillMaxWidth(),
                                        colors = CardDefaults.cardColors(
                                            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                                        ),
                                        shape = RoundedCornerShape(8.dp)
                                    ) {
                                        Column(
                                            modifier = Modifier.padding(12.dp),
                                            verticalArrangement = Arrangement.spacedBy(4.dp)
                                        ) {
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.SpaceBetween
                                            ) {
                                                Text(
                                                    text = issue.raisedByName ?: "General",
                                                    style = MaterialTheme.typography.labelMedium,
                                                    fontWeight = FontWeight.SemiBold,
                                                    color = MitPurple
                                                )
                                                Surface(
                                                    color = when (issue.actionStatus) {
                                                        "Resolved" -> StatusGreen.copy(alpha = 0.1f)
                                                        "In Progress" -> MitPurple.copy(alpha = 0.1f)
                                                        else -> StatusYellow.copy(alpha = 0.1f)
                                                    },
                                                    shape = RoundedCornerShape(4.dp)
                                                ) {
                                                    Text(
                                                        text = issue.actionStatus,
                                                        style = MaterialTheme.typography.labelSmall,
                                                        color = when (issue.actionStatus) {
                                                            "Resolved" -> StatusGreen
                                                            "In Progress" -> MitPurple
                                                            else -> StatusYellow
                                                        },
                                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                                    )
                                                }
                                            }
                                            Text(
                                                text = issue.issueDescription,
                                                style = MaterialTheme.typography.bodySmall
                                            )
                                            if (!issue.actionTaken.isNullOrBlank()) {
                                                Text(
                                                    text = "Action: ${issue.actionTaken}",
                                                    style = MaterialTheme.typography.bodySmall,
                                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                    fontStyle = FontStyle.Italic
                                                )
                                            }
                                        }
                                    }
                                }
                            }

                            item {
                                Spacer(modifier = Modifier.height(16.dp))
                            }
                        }

                        // Action buttons
                        if (!isViewMode) {
                            HorizontalDivider()
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(16.dp),
                                horizontalArrangement = Arrangement.spacedBy(12.dp, Alignment.End)
                            ) {
                                TextButton(
                                    onClick = onDismiss,
                                    enabled = !isSubmitting
                                ) {
                                    Text("Cancel")
                                }
                                Button(
                                    onClick = {
                                        isSubmitting = true
                                        val attendanceData = meetingDetails.students.map { student ->
                                            mapOf(
                                                "student_id" to student.studentId,
                                                "attended" to (attendanceMap[student.studentId] ?: false),
                                                "remarks" to null
                                            )
                                        }
                                        onSubmit(
                                            venue.ifBlank { null },
                                            discussionPoints.ifBlank { null },
                                            summary.ifBlank { null },
                                            attendanceData,
                                            meetingDetails.issues
                                        )
                                    },
                                    enabled = !isSubmitting,
                                    colors = ButtonDefaults.buttonColors(containerColor = StatusGreen)
                                ) {
                                    if (isSubmitting) {
                                        CircularProgressIndicator(
                                            modifier = Modifier.size(20.dp),
                                            color = Color.White,
                                            strokeWidth = 2.dp
                                        )
                                    } else {
                                        Icon(
                                            Icons.Default.Check,
                                            contentDescription = null,
                                            modifier = Modifier.size(18.dp)
                                        )
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Text("Complete Meeting")
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Add Issue Dialog
    if (showAddIssueDialog && meetingDetails != null) {
        AddMeetingIssueDialog(
            students = meetingDetails.students,
            onDismiss = { showAddIssueDialog = false },
            onSubmit = { studentId, description, category, action ->
                onAddIssue(studentId, description, category, action)
                showAddIssueDialog = false
            }
        )
    }
}

/**
 * Dialog to add a new issue during meeting.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddMeetingIssueDialog(
    students: List<MeetingStudent>,
    onDismiss: () -> Unit,
    onSubmit: (studentId: String?, description: String, category: String, action: String?) -> Unit
) {
    var selectedStudent by remember { mutableStateOf<MeetingStudent?>(null) }
    var description by rememberSaveable { mutableStateOf("") }
    var selectedCategory by rememberSaveable { mutableStateOf("Academic") }
    var actionTaken by rememberSaveable { mutableStateOf("") }
    var studentExpanded by rememberSaveable { mutableStateOf(false) }
    var categoryExpanded by rememberSaveable { mutableStateOf(false) }

    val categories = listOf("Academic", "Personal", "Disciplinary", "Financial", "Other")

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add Issue") },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Student selection
                ExposedDropdownMenuBox(
                    expanded = studentExpanded,
                    onExpandedChange = { studentExpanded = !studentExpanded }
                ) {
                    OutlinedTextField(
                        value = selectedStudent?.name ?: "General Issue",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Raised By") },
                        trailingIcon = {
                            ExposedDropdownMenuDefaults.TrailingIcon(expanded = studentExpanded)
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        shape = RoundedCornerShape(12.dp)
                    )
                    ExposedDropdownMenu(
                        expanded = studentExpanded,
                        onDismissRequest = { studentExpanded = false }
                    ) {
                        DropdownMenuItem(
                            text = { Text("General Issue") },
                            onClick = {
                                selectedStudent = null
                                studentExpanded = false
                            }
                        )
                        students.forEach { student ->
                            DropdownMenuItem(
                                text = { Text(student.name) },
                                onClick = {
                                    selectedStudent = student
                                    studentExpanded = false
                                }
                            )
                        }
                    }
                }

                // Category selection
                ExposedDropdownMenuBox(
                    expanded = categoryExpanded,
                    onExpandedChange = { categoryExpanded = !categoryExpanded }
                ) {
                    OutlinedTextField(
                        value = selectedCategory,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Category") },
                        trailingIcon = {
                            ExposedDropdownMenuDefaults.TrailingIcon(expanded = categoryExpanded)
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        shape = RoundedCornerShape(12.dp)
                    )
                    ExposedDropdownMenu(
                        expanded = categoryExpanded,
                        onDismissRequest = { categoryExpanded = false }
                    ) {
                        categories.forEach { category ->
                            DropdownMenuItem(
                                text = { Text(category) },
                                onClick = {
                                    selectedCategory = category
                                    categoryExpanded = false
                                }
                            )
                        }
                    }
                }

                // Issue description
                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("Issue Description *") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2,
                    maxLines = 4,
                    shape = RoundedCornerShape(12.dp)
                )

                // Action taken
                OutlinedTextField(
                    value = actionTaken,
                    onValueChange = { actionTaken = it },
                    label = { Text("Action Taken (Optional)") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2,
                    maxLines = 3,
                    shape = RoundedCornerShape(12.dp)
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onSubmit(selectedStudent?.studentId, description, selectedCategory, actionTaken.ifBlank { null })
                },
                enabled = description.isNotBlank(),
                colors = ButtonDefaults.buttonColors(containerColor = MitPurple)
            ) {
                Text("Add")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

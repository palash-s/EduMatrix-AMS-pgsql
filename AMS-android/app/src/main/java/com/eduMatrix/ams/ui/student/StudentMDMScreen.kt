package com.eduMatrix.ams.ui.student

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiException
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.MDMCourse
import com.eduMatrix.ams.data.models.MDMEnrolledCourse
import com.eduMatrix.ams.data.models.MDMWindow
import com.eduMatrix.ams.ui.components.EmptyState
import com.eduMatrix.ams.ui.components.LoadingOverlay
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * Student MDM/OE (Multidisciplinary Minor / Open Elective) Screen
 * Allows students to view and select cross-school courses.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StudentMDMScreen(
    onBack: () -> Unit = {}
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    // Tab state
    var selectedTab by rememberSaveable { mutableIntStateOf(0) }
    val tabs = listOf("Select Course", "My Courses")

    // Loading states
    var isLoadingWindows by rememberSaveable { mutableStateOf(true) }
    var isLoadingCourses by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var isSubmitting by rememberSaveable { mutableStateOf(false) }

    // Data
    var windows by remember { mutableStateOf<List<MDMWindow>>(emptyList()) }
    var myCourses by remember { mutableStateOf<List<MDMEnrolledCourse>>(emptyList()) }

    // Selection dialog state
    var showConfirmDialog by rememberSaveable { mutableStateOf(false) }
    var selectedWindowForSelection by remember { mutableStateOf<MDMWindow?>(null) }
    var selectedCourse by remember { mutableStateOf<MDMCourse?>(null) }

    // Load MDM windows
    fun loadWindows() {
        scope.launch {
            isLoadingWindows = true
            errorMessage = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")

                val response = withContext(Dispatchers.IO) {
                    ApiService.getMDMWindows(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token
                    )
                }
                windows = response.windows
            } catch (e: ApiException) {
                errorMessage = e.message ?: "Failed to load MDM windows"
            } catch (e: Exception) {
                errorMessage = "Connection error: ${e.message}"
            } finally {
                isLoadingWindows = false
            }
        }
    }

    // Load my courses
    fun loadMyCourses() {
        scope.launch {
            isLoadingCourses = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")

                val response = withContext(Dispatchers.IO) {
                    ApiService.getMDMMyCourses(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token
                    )
                }
                myCourses = response.courses
            } catch (e: ApiException) {
                // Silent fail for my courses - might just be empty
            } catch (e: Exception) {
                // Silent fail
            } finally {
                isLoadingCourses = false
            }
        }
    }

    // Submit course selection
    fun submitSelection() {
        val window = selectedWindowForSelection ?: return
        val course = selectedCourse ?: return

        scope.launch {
            isSubmitting = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")

                val message = withContext(Dispatchers.IO) {
                    ApiService.selectMDMCourse(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        windowId = window.id,
                        poolId = course.id
                    )
                }

                snackbarHostState.showSnackbar(message)
                showConfirmDialog = false
                selectedWindowForSelection = null
                selectedCourse = null

                // Refresh both windows and my courses
                loadWindows()
                loadMyCourses()
            } catch (e: ApiException) {
                snackbarHostState.showSnackbar(e.message ?: "Selection failed")
            } catch (e: Exception) {
                snackbarHostState.showSnackbar("Error: ${e.message}")
            } finally {
                isSubmitting = false
            }
        }
    }

    // Initial load
    LaunchedEffect(Unit) {
        loadWindows()
        loadMyCourses()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("MDM / Open Elective") },
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
                    IconButton(onClick = {
                        loadWindows()
                        loadMyCourses()
                    }) {
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
        ) {
            // Tabs
            TabRow(
                selectedTabIndex = selectedTab,
                containerColor = MaterialTheme.colorScheme.surface,
                contentColor = primaryAccent()
            ) {
                tabs.forEachIndexed { index, title ->
                    Tab(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        text = {
                            Text(
                                text = title,
                                fontWeight = if (selectedTab == index) FontWeight.SemiBold else FontWeight.Normal
                            )
                        },
                        icon = {
                            Icon(
                                imageVector = when (index) {
                                    0 -> if (selectedTab == 0) Icons.Filled.School else Icons.Outlined.School
                                    else -> if (selectedTab == 1) Icons.Filled.Bookmark else Icons.Outlined.BookmarkBorder
                                },
                                contentDescription = null
                            )
                        }
                    )
                }
            }

            // Content
            when (selectedTab) {
                0 -> SelectCourseTab(
                    isLoading = isLoadingWindows,
                    errorMessage = errorMessage,
                    windows = windows,
                    onSelectCourse = { window, course ->
                        selectedWindowForSelection = window
                        selectedCourse = course
                        showConfirmDialog = true
                    },
                    onRetry = { loadWindows() }
                )
                1 -> MyCoursesTab(
                    isLoading = isLoadingCourses,
                    courses = myCourses,
                    onRetry = { loadMyCourses() }
                )
            }
        }
    }

    // Confirmation dialog
    if (showConfirmDialog && selectedWindowForSelection != null && selectedCourse != null) {
        val hasExisting = selectedWindowForSelection?.mySelection != null

        AlertDialog(
            onDismissRequest = {
                if (!isSubmitting) {
                    showConfirmDialog = false
                    selectedWindowForSelection = null
                    selectedCourse = null
                }
            },
            icon = {
                Icon(
                    imageVector = if (hasExisting) Icons.Default.SwapHoriz else Icons.Default.CheckCircle,
                    contentDescription = null,
                    tint = accentPurple()
                )
            },
            title = {
                Text(if (hasExisting) "Change Selection" else "Confirm Selection")
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        text = if (hasExisting)
                            "You are about to change your course selection:"
                        else
                            "You are about to select:"
                    )

                    // Course details card
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                    ) {
                        Column(
                            modifier = Modifier.padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                text = selectedCourse?.name ?: "",
                                fontWeight = FontWeight.SemiBold
                            )
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(16.dp)
                            ) {
                                Column {
                                    Text(
                                        text = "Code",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        text = selectedCourse?.code ?: "",
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                                Column {
                                    Text(
                                        text = "Credits",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        text = "${selectedCourse?.credits ?: 0}",
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                                Column {
                                    Text(
                                        text = "Type",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        text = selectedCourse?.type ?: "",
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                            }
                            selectedCourse?.hostSchoolName?.let { school ->
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(
                                        Icons.Outlined.Business,
                                        contentDescription = null,
                                        modifier = Modifier.size(16.dp),
                                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                    Text(
                                        text = school,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }
                    }

                    // Capacity warning
                    selectedCourse?.let { course ->
                        if (course.available != null && course.available <= 5) {
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
                                        Icons.Default.Warning,
                                        contentDescription = null,
                                        tint = StatusYellow,
                                        modifier = Modifier.size(20.dp)
                                    )
                                    Text(
                                        text = "Only ${course.available} seat(s) remaining!",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = StatusYellow
                                    )
                                }
                            }
                        }
                    }
                }
            },
            confirmButton = {
                Button(
                    onClick = { submitSelection() },
                    enabled = !isSubmitting,
                    colors = ButtonDefaults.buttonColors(containerColor = accentPurple())
                ) {
                    if (isSubmitting) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = Color.White,
                            strokeWidth = 2.dp
                        )
                    } else {
                        Text(if (hasExisting) "Change" else "Confirm")
                    }
                }
            },
            dismissButton = {
                TextButton(
                    onClick = {
                        showConfirmDialog = false
                        selectedWindowForSelection = null
                        selectedCourse = null
                    },
                    enabled = !isSubmitting
                ) {
                    Text("Cancel")
                }
            }
        )
    }

    // Loading overlay
    LoadingOverlay(
        isLoading = isSubmitting,
        message = "Submitting selection..."
    )
}

/**
 * Tab for selecting a course from open MDM/OE windows.
 */
@Composable
private fun SelectCourseTab(
    isLoading: Boolean,
    errorMessage: String?,
    windows: List<MDMWindow>,
    onSelectCourse: (MDMWindow, MDMCourse) -> Unit,
    onRetry: () -> Unit
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
                        text = "Loading available courses...",
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
                message = errorMessage,
                modifier = Modifier.fillMaxSize()
            ) {
                Button(
                    onClick = onRetry,
                    colors = ButtonDefaults.buttonColors(containerColor = primaryAccent())
                ) {
                    Icon(Icons.Default.Refresh, contentDescription = null)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Retry")
                }
            }
        }

        windows.isEmpty() -> {
            EmptyState(
                icon = Icons.Outlined.School,
                title = "No Open Windows",
                message = "There are no MDM or Open Elective selection windows open at this time.",
                modifier = Modifier.fillMaxSize()
            )
        }

        else -> {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .background(MaterialTheme.colorScheme.background),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Info card
                item {
                    MDMInfoCard()
                }

                // Windows with courses
                items(windows, key = { it.id }) { window ->
                    MDMWindowCard(
                        window = window,
                        onSelectCourse = { course -> onSelectCourse(window, course) }
                    )
                }

                item {
                    Spacer(modifier = Modifier.height(16.dp))
                }
            }
        }
    }
}

/**
 * Tab showing the student's enrolled MDM/OE courses.
 */
@Composable
private fun MyCoursesTab(
    isLoading: Boolean,
    courses: List<MDMEnrolledCourse>,
    onRetry: () -> Unit
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
                        text = "Loading your courses...",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        courses.isEmpty() -> {
            EmptyState(
                icon = Icons.Outlined.BookmarkBorder,
                title = "No Courses Yet",
                message = "You haven't enrolled in any MDM or Open Elective courses yet. Select a course from the 'Select Course' tab.",
                modifier = Modifier.fillMaxSize()
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
                items(courses, key = { it.id }) { course ->
                    EnrolledCourseCard(course = course)
                }

                item {
                    Spacer(modifier = Modifier.height(16.dp))
                }
            }
        }
    }
}

/**
 * Info card explaining MDM/OE selection.
 */
@Composable
private fun MDMInfoCard() {
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
                    text = "Cross-School Courses",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = accentPurple()
                )
                Text(
                    text = "Select courses from other schools/universities. Seats are limited and allocated on first-come-first-served basis.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/**
 * Card for an MDM/OE window with available courses.
 */
@Composable
private fun MDMWindowCard(
    window: MDMWindow,
    onSelectCourse: (MDMCourse) -> Unit
) {
    val isOpen = window.status in listOf("Open", "Extension")
    val isExtension = window.status == "Extension"

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
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = if (window.courseType == "MDM") "Multidisciplinary Minor" else "Open Elective",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold
                        )
                        Surface(
                            color = if (window.courseType == "MDM")
                                accentPurple().copy(alpha = 0.1f)
                            else
                                StatusGreen.copy(alpha = 0.1f),
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Text(
                                text = window.courseType,
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Medium,
                                color = if (window.courseType == "MDM") accentPurple() else StatusGreen,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                    window.deadlineAt?.let { deadline ->
                        Text(
                            text = "Deadline: ${formatDeadline(deadline)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                // Status badge
                val statusColor = when {
                    isExtension -> StatusYellow
                    isOpen -> StatusGreen
                    else -> MaterialTheme.colorScheme.onSurfaceVariant
                }
                Surface(
                    color = statusColor.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = window.status,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Medium,
                        color = statusColor,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            // Current selection (if any)
            window.mySelection?.let { selection ->
                Surface(
                    color = StatusGreen.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.CheckCircle,
                            contentDescription = null,
                            tint = StatusGreen,
                            modifier = Modifier.size(20.dp)
                        )
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "Your Selection",
                                style = MaterialTheme.typography.labelSmall,
                                color = StatusGreen
                            )
                            Text(
                                text = "${selection.name ?: "Selected"} (${selection.code ?: ""})",
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.Medium
                            )
                            selection.hostSchoolName?.let { school ->
                                Text(
                                    text = school,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                        Surface(
                            color = StatusGreen.copy(alpha = 0.2f),
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Text(
                                text = selection.status,
                                style = MaterialTheme.typography.labelSmall,
                                color = StatusGreen,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                }
            }

            // Divider
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

            // Courses
            Text(
                text = "Available Courses (${window.courses.size})",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            window.courses.forEach { course ->
                val isSelected = window.mySelection?.poolId == course.id
                val isFull = course.available != null && course.available <= 0

                CourseOptionCard(
                    course = course,
                    isSelected = isSelected,
                    isFull = isFull,
                    isOpen = isOpen,
                    onSelect = { onSelectCourse(course) }
                )
            }
        }
    }
}

/**
 * Card for a single course option.
 */
@Composable
private fun CourseOptionCard(
    course: MDMCourse,
    isSelected: Boolean,
    isFull: Boolean,
    isOpen: Boolean,
    onSelect: () -> Unit
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .then(
                if (isOpen && !isSelected && !isFull) {
                    Modifier.clickable { onSelect() }
                } else {
                    Modifier
                }
            )
            .then(
                if (isSelected) {
                    Modifier.border(
                        width = 2.dp,
                        color = accentPurple(),
                        shape = RoundedCornerShape(8.dp)
                    )
                } else {
                    Modifier.border(
                        width = 1.dp,
                        color = MaterialTheme.colorScheme.outlineVariant,
                        shape = RoundedCornerShape(8.dp)
                    )
                }
            ),
        color = when {
            isSelected -> accentPurple().copy(alpha = 0.05f)
            isFull -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
            else -> MaterialTheme.colorScheme.surface
        }
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Course header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = course.name,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Medium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        text = course.code,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                when {
                    isSelected -> {
                        Icon(
                            Icons.Default.CheckCircle,
                            contentDescription = "Selected",
                            tint = accentPurple(),
                            modifier = Modifier.size(24.dp)
                        )
                    }
                    isFull -> {
                        Surface(
                            color = StatusRed.copy(alpha = 0.1f),
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Text(
                                text = "FULL",
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Bold,
                                color = StatusRed,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                    isOpen -> {
                        Icon(
                            Icons.Outlined.RadioButtonUnchecked,
                            contentDescription = "Select",
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(24.dp)
                        )
                    }
                }
            }

            // Course details
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Credits
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Outlined.Star,
                        contentDescription = null,
                        modifier = Modifier.size(14.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "${course.credits} Credits",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                // Capacity
                course.capacity?.let { capacity ->
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Outlined.People,
                            contentDescription = null,
                            modifier = Modifier.size(14.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "${course.selections}/$capacity",
                            style = MaterialTheme.typography.labelSmall,
                            color = if (course.available != null && course.available <= 5)
                                StatusYellow
                            else
                                MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }

            // Host school
            course.hostSchoolName?.let { school ->
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Outlined.Business,
                        contentDescription = null,
                        modifier = Modifier.size(14.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = school,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Schedule pattern
            course.schedulePattern?.let { pattern ->
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Outlined.Schedule,
                        contentDescription = null,
                        modifier = Modifier.size(14.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = pattern,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

/**
 * Card for an enrolled course.
 */
@Composable
private fun EnrolledCourseCard(course: MDMEnrolledCourse) {
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
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = course.courseName,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold
                    )
                    Text(
                        text = course.courseCode,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                // Status badge
                val statusColor = when (course.status) {
                    "Confirmed" -> StatusGreen
                    "Selected" -> StatusYellow
                    else -> MaterialTheme.colorScheme.onSurfaceVariant
                }
                Surface(
                    color = statusColor.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = course.status,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Medium,
                        color = statusColor,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            // Details
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Type
                Surface(
                    color = if (course.type == "MDM")
                        accentPurple().copy(alpha = 0.1f)
                    else
                        StatusGreen.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = course.type,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Medium,
                        color = if (course.type == "MDM") accentPurple() else StatusGreen,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }

                // Credits
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Outlined.Star,
                        contentDescription = null,
                        modifier = Modifier.size(14.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "${course.credits} Credits",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Host school
            course.hostSchoolName?.let { school ->
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Outlined.Business,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = school,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Schedule pattern
            course.schedulePattern?.let { pattern ->
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Outlined.Schedule,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = pattern,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Marks/Grade (if available)
            if (course.externalMarks != null || course.externalGrade != null) {
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(24.dp)
                ) {
                    course.externalMarks?.let { marks ->
                        Column {
                            Text(
                                text = "External Marks",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = "$marks",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.SemiBold,
                                color = accentPurple()
                            )
                        }
                    }

                    course.externalGrade?.let { grade ->
                        Column {
                            Text(
                                text = "Grade",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = grade,
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.SemiBold,
                                color = accentPurple()
                            )
                        }
                    }
                }
            }

            // Dates
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                course.selectedAt?.let { selectedAt ->
                    Text(
                        text = "Selected: ${formatDate(selectedAt)}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                    )
                }

                course.confirmedAt?.let { confirmedAt ->
                    Text(
                        text = "Confirmed: ${formatDate(confirmedAt)}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                    )
                }
            }
        }
    }
}

/**
 * Format ISO datetime to display format.
 */
private fun formatDeadline(isoDate: String): String {
    return try {
        val dateTime = LocalDateTime.parse(isoDate.replace("Z", "").substringBefore("+"))
        dateTime.format(DateTimeFormatter.ofPattern("MMM d, h:mm a"))
    } catch (e: Exception) {
        isoDate
    }
}

/**
 * Format ISO date to display format.
 */
private fun formatDate(isoDate: String): String {
    return try {
        val dateTime = LocalDateTime.parse(isoDate.replace("Z", "").substringBefore("+"))
        dateTime.format(DateTimeFormatter.ofPattern("MMM d"))
    } catch (e: Exception) {
        isoDate
    }
}

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
import com.eduMatrix.ams.data.models.ElectiveOption
import com.eduMatrix.ams.data.models.ElectiveWindow
import com.eduMatrix.ams.ui.components.EmptyState
import com.eduMatrix.ams.ui.components.LoadingOverlay
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Student Electives Screen
 * Allows students to view open elective windows and make selections.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StudentElectivesScreen(
    onBack: () -> Unit = {}
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    // Loading states
    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var isSubmitting by rememberSaveable { mutableStateOf(false) }

    // Data
    var windows by remember { mutableStateOf<List<ElectiveWindow>>(emptyList()) }

    // Selection dialog state
    var showConfirmDialog by rememberSaveable { mutableStateOf(false) }
    var selectedWindow by remember { mutableStateOf<ElectiveWindow?>(null) }
    var selectedOption by remember { mutableStateOf<ElectiveOption?>(null) }

    // Load elective windows
    fun loadWindows() {
        scope.launch {
            isLoading = true
            errorMessage = null
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                val response = withContext(Dispatchers.IO) {
                    ApiService.getElectiveWindows(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        userId = user.userId
                    )
                }
                windows = response.windows
            } catch (e: ApiException) {
                errorMessage = e.message ?: "Failed to load elective windows"
            } catch (e: Exception) {
                errorMessage = "Connection error: ${e.message}"
            } finally {
                isLoading = false
            }
        }
    }

    // Submit selection
    fun submitSelection() {
        val window = selectedWindow ?: return
        val option = selectedOption ?: return

        scope.launch {
            isSubmitting = true
            try {
                val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")
                val user = AppPrefs.getUser(context) ?: throw Exception("User not found")

                val message = withContext(Dispatchers.IO) {
                    ApiService.submitElectiveSelection(
                        baseUrl = BuildConfig.API_BASE_URL,
                        accessToken = token,
                        userId = user.userId,
                        windowId = window.windowId,
                        subjectId = option.id
                    )
                }

                snackbarHostState.showSnackbar(message)
                showConfirmDialog = false
                selectedWindow = null
                selectedOption = null

                // Refresh windows
                loadWindows()
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
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Elective Selection") },
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
                    IconButton(onClick = { loadWindows() }) {
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
                            text = "Loading elective windows...",
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
                        onClick = { loadWindows() },
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
                    message = "There are no elective selection windows open for your class at this time.",
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
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    // Info card
                    item {
                        InfoCard()
                    }

                    // Windows
                    items(windows, key = { it.windowId }) { window ->
                        ElectiveWindowCard(
                            window = window,
                            onSelect = { option ->
                                selectedWindow = window
                                selectedOption = option
                                showConfirmDialog = true
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

    // Confirmation dialog
    if (showConfirmDialog && selectedWindow != null && selectedOption != null) {
        val isChange = selectedWindow?.selection != null

        AlertDialog(
            onDismissRequest = {
                if (!isSubmitting) {
                    showConfirmDialog = false
                    selectedWindow = null
                    selectedOption = null
                }
            },
            icon = {
                Icon(
                    imageVector = if (isChange) Icons.Default.SwapHoriz else Icons.Default.CheckCircle,
                    contentDescription = null,
                    tint = accentPurple()
                )
            },
            title = {
                Text(if (isChange) "Change Selection" else "Confirm Selection")
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        text = if (isChange)
                            "You are about to change your elective selection:"
                        else
                            "You are about to select:"
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
                                text = selectedOption?.name ?: "",
                                fontWeight = FontWeight.SemiBold
                            )
                            Text(
                                text = "Code: ${selectedOption?.code}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = "Category: ${selectedWindow?.bucket}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }

                    if (selectedWindow?.status == "Extension") {
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
                                    text = "This window is in extension period. Changes may be limited.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = StatusYellow
                                )
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
                        Text(if (isChange) "Change" else "Confirm")
                    }
                }
            },
            dismissButton = {
                TextButton(
                    onClick = {
                        showConfirmDialog = false
                        selectedWindow = null
                        selectedOption = null
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
 * Info card explaining the elective selection process.
 */
@Composable
private fun InfoCard() {
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
                    text = "Elective Selection",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = accentPurple()
                )
                Text(
                    text = "Select one subject per window. You can change your selection while the window is open.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/**
 * Card for an elective window with options.
 */
@Composable
private fun ElectiveWindowCard(
    window: ElectiveWindow,
    onSelect: (ElectiveOption) -> Unit
) {
    val currentSelection = window.options.find { it.id == window.selection }
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
                    Text(
                        text = window.bucket,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold
                    )
                    Text(
                        text = "Semester ${window.targetSemesterNo}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
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
            if (currentSelection != null) {
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
                                text = "${currentSelection.name} (${currentSelection.code})",
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.Medium
                            )
                        }
                    }
                }
            }

            // Divider
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

            // Options
            Text(
                text = "Available Options",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            window.options.forEach { option ->
                val isSelected = option.id == window.selection

                Surface(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .then(
                            if (isOpen && !isSelected) {
                                Modifier.clickable { onSelect(option) }
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
                    color = if (isSelected)
                        accentPurple().copy(alpha = 0.05f)
                    else
                        MaterialTheme.colorScheme.surface
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = option.name,
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Normal,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis
                            )
                            Text(
                                text = option.code,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }

                        if (isSelected) {
                            Icon(
                                Icons.Default.CheckCircle,
                                contentDescription = "Selected",
                                tint = accentPurple(),
                                modifier = Modifier.size(24.dp)
                            )
                        } else if (isOpen) {
                            Icon(
                                Icons.Outlined.RadioButtonUnchecked,
                                contentDescription = "Select",
                                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.size(24.dp)
                            )
                        }
                    }
                }
            }

            // Min batch info
            Text(
                text = "Minimum batch size: ${window.minBatchSize} students",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
            )
        }
    }
}

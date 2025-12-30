package com.eduMatrix.ams.ui.student

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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.eduMatrix.ams.AppPrefs
import com.eduMatrix.ams.BuildConfig
import com.eduMatrix.ams.data.api.ApiService
import com.eduMatrix.ams.data.models.CAResult
import com.eduMatrix.ams.data.models.TermGrantInfo
import com.eduMatrix.ams.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Student Results Screen - shows CA marks and Term Grant status
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StudentResultsScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var isLoading by rememberSaveable { mutableStateOf(true) }
    var errorMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var results by remember { mutableStateOf<List<CAResult>>(emptyList()) }
    var termGrant by remember { mutableStateOf<TermGrantInfo?>(null) }

    // Load results
    LaunchedEffect(Unit) {
        isLoading = true
        errorMessage = null
        try {
            val token = AppPrefs.getAccessToken(context) ?: throw Exception("Not authenticated")

            val response = withContext(Dispatchers.IO) {
                ApiService.getStudentResults(BuildConfig.API_BASE_URL, token)
            }
            results = response.first
            termGrant = response.second
        } catch (e: Exception) {
            errorMessage = e.message ?: "Failed to load results"
        } finally {
            isLoading = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("My Results") }
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
            errorMessage != null -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.ErrorOutline,
                            contentDescription = null,
                            modifier = Modifier.size(64.dp),
                            tint = StatusRed
                        )
                        Text(
                            text = errorMessage ?: "Error",
                            textAlign = TextAlign.Center,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Button(
                            onClick = {
                                scope.launch {
                                    isLoading = true
                                    errorMessage = null
                                    try {
                                        val token = AppPrefs.getAccessToken(context)
                                            ?: throw Exception("Not authenticated")
                                        val response = withContext(Dispatchers.IO) {
                                            ApiService.getStudentResults(BuildConfig.API_BASE_URL, token)
                                        }
                                        results = response.first
                                        termGrant = response.second
                                    } catch (e: Exception) {
                                        errorMessage = e.message ?: "Failed to load results"
                                    } finally {
                                        isLoading = false
                                    }
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = accentPurple())
                        ) {
                            Text("Retry")
                        }
                    }
                }
            }
            results.isEmpty() && termGrant == null -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    contentAlignment = Alignment.Center
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Outlined.Assessment,
                            contentDescription = null,
                            modifier = Modifier.size(80.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                        )
                        Text(
                            text = "No Results Available",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = "Results will appear here once published",
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
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    // Term Grant Card
                    termGrant?.let { grant ->
                        item {
                            TermGrantCard(grant = grant)
                        }
                    }

                    // Results Section Header
                    if (results.isNotEmpty()) {
                        item {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "Internal Assessment",
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold
                                )
                                Surface(
                                    shape = RoundedCornerShape(8.dp),
                                    color = accentPurple().copy(alpha = 0.1f)
                                ) {
                                    Text(
                                        text = "${results.size} subjects",
                                        style = MaterialTheme.typography.labelMedium,
                                        color = accentPurple(),
                                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                                    )
                                }
                            }
                        }

                        // Subject Results
                        items(results) { result ->
                            ResultCard(result = result)
                        }

                        // Bottom spacing
                        item {
                            Spacer(modifier = Modifier.height(16.dp))
                        }
                    }
                }
            }
        }
    }
}

/**
 * Term Grant status card
 */
@Composable
private fun TermGrantCard(grant: TermGrantInfo) {
    val (statusColor, statusIcon) = when (grant.status.lowercase()) {
        "granted" -> StatusGreen to Icons.Default.CheckCircle
        "provisional" -> StatusYellow to Icons.Default.Warning
        else -> StatusRed to Icons.Default.Cancel
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(
            containerColor = statusColor.copy(alpha = 0.08f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp)
        ) {
            // Header
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(48.dp)
                        .clip(CircleShape)
                        .background(statusColor.copy(alpha = 0.2f)),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = statusIcon,
                        contentDescription = null,
                        tint = statusColor,
                        modifier = Modifier.size(28.dp)
                    )
                }
                Column {
                    Text(
                        text = "Term Grant Status",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = grant.status,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        color = statusColor
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
            HorizontalDivider(color = statusColor.copy(alpha = 0.2f))
            Spacer(modifier = Modifier.height(16.dp))

            // Stats row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                grant.attPerc?.let { perc ->
                    StatItem(
                        label = "Attendance",
                        value = "${perc.toInt()}%",
                        color = if (perc >= 75) StatusGreen else StatusRed
                    )
                }
                grant.caAvg?.let { avg ->
                    StatItem(
                        label = "CA Average",
                        value = String.format("%.1f", avg),
                        color = if (avg >= 40) StatusGreen else StatusYellow
                    )
                }
            }

            // Remarks
            grant.remarks?.let { remarks ->
                if (remarks.isNotBlank()) {
                    Spacer(modifier = Modifier.height(12.dp))
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.Top
                        ) {
                            Icon(
                                imageVector = Icons.Outlined.Info,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.size(18.dp)
                            )
                            Text(
                                text = remarks,
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

@Composable
private fun StatItem(label: String, value: String, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = color
        )
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

/**
 * Individual result card for a subject
 */
@Composable
private fun ResultCard(result: CAResult) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            // Subject header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = result.subject,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        text = result.code,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                // Average badge
                val scores = listOfNotNull(
                    result.ta1?.toDoubleOrNull(),
                    result.ta2?.toDoubleOrNull(),
                    result.ta3?.toDoubleOrNull()
                )
                if (scores.isNotEmpty()) {
                    val avg = scores.average()
                    val avgColor = when {
                        avg >= 80 -> StatusGreen
                        avg >= 60 -> MitGold
                        avg >= 40 -> StatusYellow
                        else -> StatusRed
                    }
                    Surface(
                        shape = RoundedCornerShape(10.dp),
                        color = avgColor.copy(alpha = 0.1f)
                    ) {
                        Column(
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Text(
                                text = String.format("%.0f", avg),
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                                color = avgColor
                            )
                            Text(
                                text = "AVG",
                                style = MaterialTheme.typography.labelSmall,
                                color = avgColor.copy(alpha = 0.8f)
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // TA scores row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                TAScoreItem(label = "TA 1", score = result.ta1)
                TAScoreItem(label = "TA 2", score = result.ta2)
                TAScoreItem(label = "TA 3", score = result.ta3)
            }
        }
    }
}

@Composable
private fun TAScoreItem(label: String, score: String?) {
    val displayScore = score ?: "-"
    val isPublished = score != null && score != "-"
    val scoreValue = score?.toDoubleOrNull()

    val scoreColor = when {
        !isPublished -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
        scoreValue != null && scoreValue >= 80 -> StatusGreen
        scoreValue != null && scoreValue >= 60 -> MitGold
        scoreValue != null && scoreValue >= 40 -> StatusYellow
        scoreValue != null -> StatusRed
        else -> MaterialTheme.colorScheme.onSurface
    }

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.width(80.dp)
    ) {
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = if (isPublished)
                scoreColor.copy(alpha = 0.1f)
            else
                MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        ) {
            Box(
                modifier = Modifier
                    .size(56.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = displayScore,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = scoreColor
                )
            }
        }
        Spacer(modifier = Modifier.height(6.dp))
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

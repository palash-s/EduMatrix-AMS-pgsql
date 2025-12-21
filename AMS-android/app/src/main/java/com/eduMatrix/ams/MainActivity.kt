package com.eduMatrix.ams

import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.eduMatrix.ams.ui.theme.AMSandroidTheme
import com.eduMatrix.ams.ui.theme.MitPurple
import com.eduMatrix.ams.ui.theme.MitTeal
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.compose.currentBackStackEntryAsState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private object Routes {
    const val Login = "login"
    const val Main = "main"
    const val Dashboard = "dashboard"
    const val Attendance = "attendance"
    const val Timetable = "timetable"
    const val Leaves = "leaves"
    const val Results = "results"
    const val Notifications = "notifications"
    const val Events = "events"
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AMSandroidTheme {
                AppRoot()
            }
        }
    }
}

@Composable
fun AppRoot() {
    val context = LocalContext.current
    val navController = rememberNavController()

    val hasToken = remember {
        !AppPrefs.getAccessToken(context).isNullOrBlank()
    }

    NavHost(
        navController = navController,
        startDestination = if (hasToken) Routes.Main else Routes.Login,
    ) {
        composable(Routes.Login) {
            LoginScreen(
                onLoginSuccess = {
                    navController.navigate(Routes.Main) {
                        popUpTo(Routes.Login) { inclusive = true }
                    }
                }
            )
        }
        composable(Routes.Main) {
            MainShell(
                onLogout = {
                    AppPrefs.saveAccessToken(context, "")
                    AppPrefs.saveRefreshToken(context, "")
                    navController.navigate(Routes.Login) {
                        popUpTo(Routes.Main) { inclusive = true }
                    }
                },
            )
        }
    }
}


@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LoginScreen(onLoginSuccess: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val studentDomain = "@school.mituniversity.edu.in"

    var username by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var status by rememberSaveable { mutableStateOf("") }

    var accessToken by rememberSaveable {
        mutableStateOf(AppPrefs.getAccessToken(context).orEmpty())
    }

    LaunchedEffect(Unit) {
        // If already logged in, go home.
        if (accessToken.isNotBlank()) {
            onLoginSuccess()
        }
    }

    val postNotifGranted = if (Build.VERSION.SDK_INT >= 33) {
        ContextCompat.checkSelfPermission(context, android.Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    } else {
        true
    }
    val notificationsEnabled = NotificationManagerCompat.from(context).areNotificationsEnabled()

    Surface(color = MaterialTheme.colorScheme.background) {
        Scaffold { innerPadding ->
            Column(
                modifier = Modifier
                    .padding(innerPadding)
                    .fillMaxSize()
                    .padding(16.dp),
                verticalArrangement = Arrangement.Center
            ) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(18.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = "AMS",
                            style = MaterialTheme.typography.headlineMedium,
                            color = MitPurple
                        )
                        Text(
                            text = "Student Portal",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurface
                        )

                        OutlinedTextField(
                            value = username,
                            onValueChange = { username = it },
                            label = { Text("Admission No / Email") },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                            modifier = Modifier.fillMaxWidth()
                        )

                        if (username.isNotBlank() && !username.contains("@")) {
                            Text(
                                text = "Using: ${username.trim()}$studentDomain",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }

                        OutlinedTextField(
                            value = password,
                            onValueChange = { password = it },
                            label = { Text("Password") },
                            visualTransformation = PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )

                        Text(
                            text = "Default password (if unchanged): Student@123",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )

                        Button(
                            onClick = {
                                status = "Logging in..."
                                scope.launch {
                                    try {
                                        val deviceId = AppPrefs.getDeviceId(context)
                                        val raw = username.trim()
                                        val loginUsername = if (raw.contains("@")) raw else (raw + studentDomain)
                                        val result = withContext(Dispatchers.IO) {
                                            ApiClient.login(
                                                baseUrl = BuildConfig.API_BASE_URL,
                                                username = loginUsername,
                                                password = password,
                                                deviceId = deviceId,
                                            )
                                        }

                                        accessToken = result.accessToken
                                        AppPrefs.saveAccessToken(context, result.accessToken)
                                        AppPrefs.saveRefreshToken(context, result.refreshToken)
                                        status = "Login OK"
                                        onLoginSuccess()
                                    } catch (e: Exception) {
                                        status = e.message ?: "Login failed"
                                    }
                                }
                            },
                            enabled = username.isNotBlank() && password.isNotBlank(),
                            modifier = Modifier.fillMaxWidth(),
                        ) { Text("Login") }

                        if (status.isNotBlank()) {
                            val isOk = status.startsWith("Login OK")
                            Text(
                                text = status,
                                style = MaterialTheme.typography.bodyMedium,
                                color = if (isOk) MitTeal else MaterialTheme.colorScheme.error
                            )
                        }
                    }
                }

                Spacer(Modifier.height(12.dp))
                // Keep permission state visible but subtle (useful for push, matches "system" info)
                Text(
                    text = "Notifications: enabled=$notificationsEnabled, permission=$postNotifGranted",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MainShell(onLogout: () -> Unit) {
    val tabController = rememberNavController()
    val navBackStackEntry by tabController.currentBackStackEntryAsState()
    val currentDestination = navBackStackEntry?.destination

    val tabs = listOf(
        Routes.Dashboard to "Dashboard",
        Routes.Attendance to "Attendance",
        Routes.Timetable to "Timetable",
        Routes.Leaves to "Leaves",
        Routes.Results to "Results",
        Routes.Notifications to "Notifications",
    )

    val currentTitle = tabs.firstOrNull { it.first == (currentDestination?.route ?: "") }?.second ?: "Student"

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(currentTitle) },
                actions = { OutlinedButton(onClick = onLogout) { Text("Logout") } },
            )
        },
        bottomBar = {
            NavigationBar {
                tabs.forEach { (route, label) ->
                    val selected = currentDestination?.hierarchy?.any { it.route == route } == true
                    NavigationBarItem(
                        selected = selected,
                        onClick = {
                            tabController.navigate(route) {
                                popUpTo(tabController.graph.startDestinationId) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Text(label.take(1)) },
                        label = { Text(label) },
                    )
                }
            }
        }
    ) { innerPadding ->
        NavHost(
            navController = tabController,
            startDestination = Routes.Dashboard,
            modifier = Modifier.padding(innerPadding),
        ) {
            composable(Routes.Dashboard) {
                DashboardScreen(
                    onNavigate = { route ->
                        tabController.navigate(route) {
                            popUpTo(tabController.graph.startDestinationId) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    }
                )
            }
            composable(Routes.Attendance) { AttendanceScreen() }
            composable(Routes.Timetable) { TimetableScreen() }
            composable(Routes.Leaves) { LeavesScreen() }
            composable(Routes.Results) { ResultsScreen() }
            composable(Routes.Notifications) { NotificationsScreen() }
        }
    }
}

@Composable
private fun DashboardScreen(onNavigate: (String) -> Unit) {
    val context = LocalContext.current
    var status by rememberSaveable { mutableStateOf("Loading...") }
    var attendance by remember { mutableStateOf<ApiClient.AttendanceSummary?>(null) }
    var notifications by remember { mutableStateOf<List<ApiClient.MobileNotification>>(emptyList()) }
    var refreshTick by rememberSaveable { mutableStateOf(0) }

    LaunchedEffect(refreshTick) {
        try {
            val token = AppPrefs.getAccessToken(context).orEmpty()
            val att = withContext(Dispatchers.IO) {
                ApiClient.getAttendance(
                    baseUrl = BuildConfig.API_BASE_URL,
                    accessToken = token,
                )
            }
            val notifs = withContext(Dispatchers.IO) {
                ApiClient.getNotifications(
                    baseUrl = BuildConfig.API_BASE_URL,
                    accessToken = token,
                )
            }
            attendance = att
            notifications = notifs
            status = ""
        } catch (e: Exception) {
            status = e.message ?: "Failed to load"
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(
                    text = attendance?.studentName ?: "Student",
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onBackground
                )
                val cls = attendance?.studentClass
                if (!cls.isNullOrBlank()) {
                    Text(
                        text = cls,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            OutlinedButton(onClick = { refreshTick++ }) { Text("Refresh") }
        }

        if (status.isNotBlank()) {
            Text(status, color = MaterialTheme.colorScheme.error)
        }

        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Attendance", style = MaterialTheme.typography.titleMedium, color = MitPurple)
                val pct = (attendance?.overallPercentage ?: 0.0).coerceIn(0.0, 100.0)
                Text(
                    text = String.format("%.1f%%", pct),
                    style = MaterialTheme.typography.headlineMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                LinearProgressIndicator(
                    progress = (pct / 100.0).toFloat(),
                    modifier = Modifier.fillMaxWidth(),
                    color = MitTeal
                )
                val attended = attendance?.attended ?: 0
                val total = attendance?.totalLectures ?: 0
                Text(
                    text = "$attended / $total lectures attended",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                OutlinedButton(onClick = { onNavigate(Routes.Attendance) }) { Text("View details") }
            }
        }

        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Quick Actions", style = MaterialTheme.typography.titleMedium, color = MitPurple)
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(modifier = Modifier.weight(1f), onClick = { onNavigate(Routes.Timetable) }) { Text("Timetable") }
                    OutlinedButton(modifier = Modifier.weight(1f), onClick = { onNavigate(Routes.Leaves) }) { Text("Leaves") }
                }
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(modifier = Modifier.weight(1f), onClick = { onNavigate(Routes.Results) }) { Text("Results") }
                    OutlinedButton(modifier = Modifier.weight(1f), onClick = { onNavigate(Routes.Notifications) }) { Text("Alerts") }
                }
            }
        }

        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Recent Notifications", style = MaterialTheme.typography.titleMedium, color = MitPurple)
                val recent = notifications.take(3)
                if (recent.isEmpty()) {
                    Text("No notifications", color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    recent.forEach { n ->
                        val read = if (n.isRead) "Read" else "New"
                        Text(
                            text = "[$read] ${n.title}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        if (n.message.isNotBlank()) {
                            Text(
                                text = n.message,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        Spacer(Modifier.height(4.dp))
                    }
                }
                OutlinedButton(onClick = { onNavigate(Routes.Notifications) }) { Text("View all") }
            }
        }
    }
}


@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AttendanceScreen() {
    val context = LocalContext.current
    var status by rememberSaveable { mutableStateOf("") }
    var summary by remember { mutableStateOf<ApiClient.AttendanceSummary?>(null) }

    LaunchedEffect(status) {
        if (status != "Loading...") return@LaunchedEffect
        try {
            val token = AppPrefs.getAccessToken(context).orEmpty()
            summary = withContext(Dispatchers.IO) {
                ApiClient.getAttendance(BuildConfig.API_BASE_URL, token)
            }
            status = ""
        } catch (e: Exception) {
            status = e.message ?: "Failed"
        }
    }

    if (status == "") status = "Loading..."

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { status = "Loading..." }) { Text("Refresh") }
        }
        if (status.isNotBlank()) Text("Status: $status")
        summary?.let { s ->
            Text("${s.studentName} (${s.studentClass})")
            Text("Overall: ${s.overallPercentage}%  (${s.attended}/${s.totalLectures})")
            Spacer(Modifier.height(8.dp))
            s.subjects.take(30).forEach { subj ->
                Text("${subj.name} (${subj.code}) - ${subj.percentage}%")
            }
        }
    }
}


@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TimetableScreen() {
    val context = LocalContext.current
    var status by rememberSaveable { mutableStateOf("Loading...") }
    var className by rememberSaveable { mutableStateOf("") }
    var entries by remember { mutableStateOf<List<ApiClient.TimetableEntry>>(emptyList()) }

    LaunchedEffect(status) {
        if (status != "Loading...") return@LaunchedEffect
        try {
            val token = AppPrefs.getAccessToken(context).orEmpty()
            val resp = withContext(Dispatchers.IO) {
                ApiClient.getTimetable(BuildConfig.API_BASE_URL, token)
            }
            className = resp.first
            entries = resp.second
            status = ""
        } catch (e: Exception) {
            status = e.message ?: "Failed"
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { status = "Loading..." }) { Text("Refresh") }
        }
        if (className.isNotBlank()) Text("Class: $className")
        if (status.isNotBlank()) Text("Status: $status")
        entries.take(60).forEach { e ->
            val teacher = e.teacher.takeIf { it.isNotBlank() } ?: "-"
            val room = e.room.takeIf { it.isNotBlank() } ?: "-"
            Text("${e.dayOfWeek} ${e.startTime}-${e.endTime}  ${e.subject}  ($teacher, $room)")
        }
    }
}


@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LeavesScreen() {
    val context = LocalContext.current
    var status by rememberSaveable { mutableStateOf("Loading...") }
    var leaves by remember { mutableStateOf<ApiClient.LeavesResponse?>(null) }

    var startDate by rememberSaveable { mutableStateOf("") }
    var endDate by rememberSaveable { mutableStateOf("") }
    var totalDays by rememberSaveable { mutableStateOf("1") }
    var reason by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(status) {
        if (status != "Loading...") return@LaunchedEffect
        try {
            val token = AppPrefs.getAccessToken(context).orEmpty()
            leaves = withContext(Dispatchers.IO) {
                ApiClient.getLeaves(BuildConfig.API_BASE_URL, token)
            }
            status = ""
        } catch (e: Exception) {
            status = e.message ?: "Failed"
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { status = "Loading..." }) { Text("Refresh") }
        }
        if (status.isNotBlank()) Text("Status: $status")
        leaves?.let { l ->
            Text("Balance: ${l.balance.remaining}/${l.balance.total} (used ${l.balance.used})")
        }

        Text("Apply Leave (minimal)")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedTextField(
                value = startDate,
                onValueChange = { startDate = it },
                label = { Text("Start YYYY-MM-DD") },
                singleLine = true,
                modifier = Modifier.weight(1f)
            )
            OutlinedTextField(
                value = endDate,
                onValueChange = { endDate = it },
                label = { Text("End YYYY-MM-DD") },
                singleLine = true,
                modifier = Modifier.weight(1f)
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedTextField(
                value = totalDays,
                onValueChange = { totalDays = it },
                label = { Text("Days") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
                modifier = Modifier.weight(1f)
            )
            OutlinedTextField(
                value = reason,
                onValueChange = { reason = it },
                label = { Text("Reason") },
                singleLine = true,
                modifier = Modifier.weight(2f)
            )
        }

        Button(
            onClick = { status = "Applying..." },
            modifier = Modifier.fillMaxWidth(),
            enabled = startDate.isNotBlank() && endDate.isNotBlank() && totalDays.isNotBlank(),
        ) { Text("Submit Leave") }

        if (status == "Applying...") {
            LaunchedEffect(startDate, endDate, totalDays, reason) {
                try {
                    val token = AppPrefs.getAccessToken(context).orEmpty()
                    val days = totalDays.toDoubleOrNull() ?: 1.0
                    withContext(Dispatchers.IO) {
                        ApiClient.applyLeave(
                            baseUrl = BuildConfig.API_BASE_URL,
                            accessToken = token,
                            totalDays = days,
                            startDateIso = startDate,
                            endDateIso = endDate,
                            reason = reason.takeIf { it.isNotBlank() },
                            leaveType = "General",
                        )
                    }
                    status = "Loading..." // refresh list
                } catch (e: Exception) {
                    status = e.message ?: "Apply failed"
                }
            }
        }

        Spacer(Modifier.height(8.dp))
        Text("History")
        leaves?.history?.take(20)?.forEach { h ->
            Text("#${h.leaveId} ${h.type} ${h.days}d ${h.status} (${h.startDate} → ${h.endDate})")
        }
    }
}


@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ResultsScreen() {
    val context = LocalContext.current
    var status by rememberSaveable { mutableStateOf("Loading...") }
    var results by remember { mutableStateOf<ApiClient.ResultsResponse?>(null) }

    LaunchedEffect(status) {
        if (status != "Loading...") return@LaunchedEffect
        try {
            val token = AppPrefs.getAccessToken(context).orEmpty()
            results = withContext(Dispatchers.IO) {
                ApiClient.getResults(BuildConfig.API_BASE_URL, token)
            }
            status = ""
        } catch (e: Exception) {
            status = e.message ?: "Failed"
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { status = "Loading..." }) { Text("Refresh") }
        }
        if (status.isNotBlank()) Text("Status: $status")
        results?.termGrant?.let { tg ->
            Text("Term Grant: ${tg.status} (published=${tg.isPublished})")
            if (tg.remarks.isNotBlank()) Text("Remarks: ${tg.remarks}")
        }
        Spacer(Modifier.height(8.dp))
        results?.results?.take(40)?.forEach { r ->
            Text("${r.subject} (${r.code})  TA1:${r.ta1} TA2:${r.ta2} TA3:${r.ta3}")
        }
    }
}


@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NotificationsScreen() {
    val context = LocalContext.current
    var status by rememberSaveable { mutableStateOf("Loading...") }
    var items by remember { mutableStateOf<List<ApiClient.MobileNotification>>(emptyList()) }

    LaunchedEffect(status) {
        if (status != "Loading...") return@LaunchedEffect
        try {
            val token = AppPrefs.getAccessToken(context).orEmpty()
            items = withContext(Dispatchers.IO) {
                ApiClient.getNotifications(BuildConfig.API_BASE_URL, token)
            }
            status = ""
        } catch (e: Exception) {
            status = e.message ?: "Failed"
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = { status = "Loading..." }) { Text("Refresh") }
        }
        if (status.isNotBlank()) Text("Status: $status")
        items.take(30).forEach { n ->
            val read = if (n.isRead) "read" else "new"
            Text("[${n.type}] (${read}) ${n.title}: ${n.message}")
        }
    }
}


@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun EventsScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    var status by rememberSaveable { mutableStateOf("Loading...") }
    var events by remember { mutableStateOf<List<ApiClient.StudentEvent>>(emptyList()) }

    LaunchedEffect(status) {
        if (status != "Loading...") return@LaunchedEffect
        try {
            val token = AppPrefs.getAccessToken(context).orEmpty()
            events = withContext(Dispatchers.IO) {
                ApiClient.getStudentEvents(BuildConfig.API_BASE_URL, token)
            }
            status = ""
        } catch (e: Exception) {
            status = e.message ?: "Failed"
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Events") },
                navigationIcon = { OutlinedButton(onClick = onBack) { Text("Back") } },
                actions = { OutlinedButton(onClick = { status = "Loading..." }) { Text("Refresh") } },
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .padding(innerPadding)
                .fillMaxSize()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            if (status.isNotBlank()) Text("Status: $status")
            events.take(30).forEach { e ->
                Text("${e.name} (${e.startDate}) [${e.status}]")
            }
        }
    }
}
package com.eduMatrix.ams

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class MyFirebaseMessagingService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        AppPrefs.saveFcmToken(this, token)

        val accessToken = AppPrefs.getAccessToken(this) ?: return
        val deviceId = AppPrefs.getDeviceId(this)

        Thread {
            try {
                ApiClient.registerPush(
                    baseUrl = BuildConfig.API_BASE_URL,
                    accessToken = accessToken,
                    deviceId = deviceId,
                    fcmToken = token
                )
            } catch (_: Exception) {
                // Best-effort; user can re-register from UI.
            }
        }.start()
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)

        val title = message.notification?.title
            ?: message.data["title"]
            ?: "AMS"

        val body = message.notification?.body
            ?: message.data["body"]
            ?: message.data["message"]
            ?: ""

        showNotification(title = title, body = body)
    }

    private fun showNotification(title: String, body: String) {
        val channelId = "ams_default"
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "AMS Notifications",
                NotificationManager.IMPORTANCE_DEFAULT
            )
            manager.createNotificationChannel(channel)
        }

        val notification = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .build()

        manager.notify((System.currentTimeMillis() % Int.MAX_VALUE).toInt(), notification)
    }
}

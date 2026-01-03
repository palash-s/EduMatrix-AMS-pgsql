package com.eduMatrix.ams

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class MyFirebaseMessagingService : FirebaseMessagingService() {

    companion object {
        private const val TAG = "FCM"
        const val CHANNEL_ID = "ams_alerts"

        /**
         * Ensures notification channel exists with HIGH importance.
         * Call this from MainActivity.onCreate() to create channel early.
         */
        fun createNotificationChannel(context: Context) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

                // Delete existing channel if importance is not HIGH (Android won't update importance)
                val existingChannel = manager.getNotificationChannel(CHANNEL_ID)
                if (existingChannel != null && existingChannel.importance != NotificationManager.IMPORTANCE_HIGH) {
                    Log.d(TAG, "Recreating channel - old importance: ${existingChannel.importance}")
                    manager.deleteNotificationChannel(CHANNEL_ID)
                }

                // Create channel with HIGH importance for heads-up
                if (manager.getNotificationChannel(CHANNEL_ID) == null) {
                    val channel = NotificationChannel(
                        CHANNEL_ID,
                        "AMS Alerts",
                        NotificationManager.IMPORTANCE_HIGH
                    ).apply {
                        description = "Important alerts from EduMatrix AMS"
                        enableLights(true)
                        lightColor = Color.BLUE
                        enableVibration(true)
                        vibrationPattern = longArrayOf(0, 250, 250, 250)
                        setShowBadge(true)
                        lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
                        setSound(
                            RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
                            AudioAttributes.Builder()
                                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                                .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                                .build()
                        )
                    }
                    manager.createNotificationChannel(channel)
                    Log.d(TAG, "Created notification channel with HIGH importance")
                }
            }
        }
    }

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d(TAG, "New FCM token received")
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
                Log.d(TAG, "FCM token registered with backend")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to register FCM token: ${e.message}")
            }
        }.start()
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        Log.d(TAG, "Message received - notification: ${message.notification != null}, data: ${message.data}")

        val title = message.notification?.title
            ?: message.data["title"]
            ?: "EduMatrix AMS"

        val body = message.notification?.body
            ?: message.data["body"]
            ?: message.data["message"]
            ?: ""

        val type = message.data["type"] ?: "info"

        Log.d(TAG, "Showing notification: title=$title, body=$body, type=$type")
        showNotification(title = title, body = body, type = type)
    }

    private fun showNotification(title: String, body: String, type: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        // Ensure channel exists
        createNotificationChannel(this)

        // Log channel info for debugging
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = manager.getNotificationChannel(CHANNEL_ID)
            Log.d(TAG, "Channel info: id=${channel?.id}, importance=${channel?.importance}, canShowBadge=${channel?.canShowBadge()}")
        }

        // Intent to open the app when notification is tapped
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("from_notification", true)
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            System.currentTimeMillis().toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Full-screen intent for guaranteed heads-up on some devices
        val fullScreenIntent = PendingIntent.getActivity(
            this,
            System.currentTimeMillis().toInt() + 1,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Choose icon color based on notification type
        val iconColor = when (type.lowercase()) {
            "success" -> Color.parseColor("#22C55E")
            "warning" -> Color.parseColor("#F59E0B")
            "danger", "error" -> Color.parseColor("#EF4444")
            else -> Color.parseColor("#6366F1")
        }

        val defaultSound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setColor(iconColor)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .setFullScreenIntent(fullScreenIntent, true)  // For heads-up
            .setPriority(NotificationCompat.PRIORITY_MAX)  // Maximum priority
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setSound(defaultSound)
            .setVibrate(longArrayOf(0, 250, 250, 250))
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

        val notificationId = (System.currentTimeMillis() % Int.MAX_VALUE).toInt()
        manager.notify(notificationId, notification)
        Log.d(TAG, "Notification posted with id: $notificationId")
    }
}

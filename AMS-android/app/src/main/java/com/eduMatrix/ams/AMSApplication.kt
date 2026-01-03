package com.eduMatrix.ams

import android.app.Application
import android.util.Log
import com.google.firebase.FirebaseApp

class AMSApplication : Application() {
    override fun onCreate() {
        super.onCreate()

        // Initialize Firebase manually
        try {
            if (FirebaseApp.getApps(this).isEmpty()) {
                FirebaseApp.initializeApp(this)
                Log.d("FCM", "Firebase initialized manually")
            } else {
                Log.d("FCM", "Firebase already initialized")
            }
        } catch (e: Exception) {
            Log.e("FCM", "Firebase initialization failed: ${e.message}", e)
        }
    }
}

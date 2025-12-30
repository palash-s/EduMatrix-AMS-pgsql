package com.eduMatrix.ams

import android.content.Context
import android.provider.Settings
import com.eduMatrix.ams.data.models.StaffRoles
import com.eduMatrix.ams.data.models.User
import com.eduMatrix.ams.data.models.UserRole
import com.google.gson.Gson

/**
 * Shared preferences helper for persisting user session data.
 * Stores authentication tokens, user info, and app settings.
 */
object AppPrefs {
    private const val PREFS_NAME = "ams_prefs"

    // Token keys
    private const val KEY_ACCESS_TOKEN = "access_token"

    // Theme keys
    private const val KEY_DARK_MODE = "dark_mode"
    private const val KEY_REFRESH_TOKEN = "refresh_token"
    private const val KEY_FCM_TOKEN = "fcm_token"

    // User info keys
    private const val KEY_USER_ID = "user_id"
    private const val KEY_USER_EMAIL = "user_email"
    private const val KEY_USER_NAME = "user_name"
    private const val KEY_USER_ROLE = "user_role"
    private const val KEY_DEPARTMENT_ID = "department_id"
    private const val KEY_DEPARTMENT_NAME = "department_name"
    private const val KEY_MUST_CHANGE_PASSWORD = "must_change_password"
    private const val KEY_STAFF_ROLES = "staff_roles"

    private val gson = Gson()

    // ========================================
    // DEVICE ID
    // ========================================

    fun getDeviceId(context: Context): String {
        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
        return androidId?.takeIf { it.isNotBlank() } ?: "unknown"
    }

    // ========================================
    // TOKEN MANAGEMENT
    // ========================================

    fun saveAccessToken(context: Context, token: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_ACCESS_TOKEN, token)
            .apply()
    }

    fun getAccessToken(context: Context): String? {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_ACCESS_TOKEN, null)
    }

    fun saveRefreshToken(context: Context, token: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_REFRESH_TOKEN, token)
            .apply()
    }

    fun getRefreshToken(context: Context): String? {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_REFRESH_TOKEN, null)
    }

    fun saveFcmToken(context: Context, token: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_FCM_TOKEN, token)
            .apply()
    }

    fun getFcmToken(context: Context): String? {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_FCM_TOKEN, null)
    }

    // ========================================
    // USER DATA MANAGEMENT
    // ========================================

    /**
     * Save complete user data after login.
     */
    fun saveUser(context: Context, user: User) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_USER_ID, user.userId)
            .putString(KEY_USER_EMAIL, user.email)
            .putString(KEY_USER_NAME, user.name)
            .putString(KEY_USER_ROLE, user.role.name)
            .putInt(KEY_DEPARTMENT_ID, user.departmentId ?: 0)
            .putString(KEY_DEPARTMENT_NAME, user.departmentName ?: "")
            .putBoolean(KEY_MUST_CHANGE_PASSWORD, user.mustChangePassword)
            .putString(KEY_STAFF_ROLES, user.staffRoles?.let { gson.toJson(it) } ?: "")
            .apply()
    }

    /**
     * Get stored user data. Returns null if not logged in.
     */
    fun getUser(context: Context): User? {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val userId = prefs.getString(KEY_USER_ID, null)
        if (userId.isNullOrBlank()) return null

        val roleString = prefs.getString(KEY_USER_ROLE, null) ?: return null
        val staffRolesJson = prefs.getString(KEY_STAFF_ROLES, null)

        return User(
            userId = userId,
            email = prefs.getString(KEY_USER_EMAIL, "") ?: "",
            name = prefs.getString(KEY_USER_NAME, "") ?: "",
            role = try { UserRole.valueOf(roleString) } catch (e: Exception) { UserRole.STUDENT },
            departmentId = prefs.getInt(KEY_DEPARTMENT_ID, 0).takeIf { it > 0 },
            departmentName = prefs.getString(KEY_DEPARTMENT_NAME, null)?.takeIf { it.isNotBlank() },
            mustChangePassword = prefs.getBoolean(KEY_MUST_CHANGE_PASSWORD, false),
            staffRoles = staffRolesJson?.takeIf { it.isNotBlank() }?.let {
                try { gson.fromJson(it, StaffRoles::class.java) } catch (e: Exception) { null }
            }
        )
    }

    /**
     * Get just the user role without loading full user object.
     */
    fun getUserRole(context: Context): UserRole? {
        val roleString = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_USER_ROLE, null)
        return roleString?.let {
            try { UserRole.valueOf(it) } catch (e: Exception) { null }
        }
    }

    /**
     * Get staff roles for staff users.
     */
    fun getStaffRoles(context: Context): StaffRoles? {
        val json = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_STAFF_ROLES, null)
        return json?.takeIf { it.isNotBlank() }?.let {
            try { gson.fromJson(it, StaffRoles::class.java) } catch (e: Exception) { null }
        }
    }

    /**
     * Check if user must change password.
     */
    fun mustChangePassword(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_MUST_CHANGE_PASSWORD, false)
    }

    /**
     * Clear password change requirement after successful change.
     */
    fun clearMustChangePassword(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_MUST_CHANGE_PASSWORD, false)
            .apply()
    }

    // ========================================
    // SESSION MANAGEMENT
    // ========================================

    /**
     * Check if user is logged in (has valid tokens).
     */
    fun isLoggedIn(context: Context): Boolean {
        return !getAccessToken(context).isNullOrBlank() && getUser(context) != null
    }

    /**
     * Clear all session data (logout).
     */
    fun clearSession(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_ACCESS_TOKEN)
            .remove(KEY_REFRESH_TOKEN)
            .remove(KEY_USER_ID)
            .remove(KEY_USER_EMAIL)
            .remove(KEY_USER_NAME)
            .remove(KEY_USER_ROLE)
            .remove(KEY_DEPARTMENT_ID)
            .remove(KEY_DEPARTMENT_NAME)
            .remove(KEY_MUST_CHANGE_PASSWORD)
            .remove(KEY_STAFF_ROLES)
            .apply()
    }

    /**
     * Clear all preferences including FCM token.
     */
    fun clearAll(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .clear()
            .apply()
    }

    // ========================================
    // THEME MANAGEMENT
    // ========================================

    /**
     * Dark mode setting: null = follow system, true = dark, false = light
     */
    fun getDarkMode(context: Context): Boolean? {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return if (prefs.contains(KEY_DARK_MODE)) {
            prefs.getBoolean(KEY_DARK_MODE, false)
        } else {
            null  // Follow system
        }
    }

    /**
     * Save dark mode preference.
     * @param darkMode true = dark, false = light, null = follow system
     */
    fun setDarkMode(context: Context, darkMode: Boolean?) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
        if (darkMode == null) {
            prefs.remove(KEY_DARK_MODE)
        } else {
            prefs.putBoolean(KEY_DARK_MODE, darkMode)
        }
        prefs.apply()
    }
}

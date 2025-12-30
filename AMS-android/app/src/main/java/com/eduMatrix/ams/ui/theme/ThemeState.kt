package com.eduMatrix.ams.ui.theme

import android.content.Context
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.*
import com.eduMatrix.ams.AppPrefs

/**
 * Theme mode options for the app.
 */
enum class ThemeMode {
    SYSTEM,  // Follow system setting
    LIGHT,   // Always light
    DARK     // Always dark
}

/**
 * Global theme state holder.
 * Provides theme state that can be observed and changed from anywhere in the app.
 */
object ThemeState {
    private var _themeMode = mutableStateOf(ThemeMode.LIGHT)  // Default to light mode
    val themeMode: State<ThemeMode> = _themeMode

    /**
     * Initialize theme state from saved preferences.
     * Defaults to LIGHT mode if no preference is saved.
     */
    fun initialize(context: Context) {
        val savedDarkMode = AppPrefs.getDarkMode(context)
        _themeMode.value = when (savedDarkMode) {
            true -> ThemeMode.DARK
            false -> ThemeMode.LIGHT
            null -> ThemeMode.LIGHT  // Default to light mode
        }
    }

    /**
     * Set theme mode and persist to preferences.
     */
    fun setThemeMode(context: Context, mode: ThemeMode) {
        _themeMode.value = mode
        val darkMode = when (mode) {
            ThemeMode.DARK -> true
            ThemeMode.LIGHT -> false
            ThemeMode.SYSTEM -> null
        }
        AppPrefs.setDarkMode(context, darkMode)
    }

    /**
     * Toggle between dark and light mode.
     * If currently following system, switches to opposite of current system theme.
     */
    fun toggle(context: Context, isSystemDark: Boolean) {
        val newMode = when (_themeMode.value) {
            ThemeMode.SYSTEM -> if (isSystemDark) ThemeMode.LIGHT else ThemeMode.DARK
            ThemeMode.LIGHT -> ThemeMode.DARK
            ThemeMode.DARK -> ThemeMode.LIGHT
        }
        setThemeMode(context, newMode)
    }

    /**
     * Cycle through theme modes: System -> Light -> Dark -> System
     */
    fun cycle(context: Context) {
        val newMode = when (_themeMode.value) {
            ThemeMode.SYSTEM -> ThemeMode.LIGHT
            ThemeMode.LIGHT -> ThemeMode.DARK
            ThemeMode.DARK -> ThemeMode.SYSTEM
        }
        setThemeMode(context, newMode)
    }
}

/**
 * Composable to get current dark theme state based on theme mode.
 */
@Composable
fun rememberIsDarkTheme(): Boolean {
    val themeMode by ThemeState.themeMode
    val isSystemDark = isSystemInDarkTheme()

    return when (themeMode) {
        ThemeMode.SYSTEM -> isSystemDark
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
    }
}

package com.eduMatrix.ams.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * Dark color scheme using MIT brand colors
 * Uses brighter variants for text/accent colors to ensure readability
 * Logo colors (MitPurple) are preserved where used as brand elements
 */
private val DarkColorScheme = darkColorScheme(
    // Primary colors - use brighter purple for interactive elements
    primary = MitPurpleDarkMode,           // Brighter purple for buttons, links
    onPrimary = Color.White,
    primaryContainer = MitPurple,          // Original purple for filled containers
    onPrimaryContainer = Color.White,

    // Secondary colors - use brighter teal for dark mode
    secondary = MitTealDarkMode,           // Brighter teal for visibility
    onSecondary = Color.Black,
    secondaryContainer = MitTeal,
    onSecondaryContainer = Color.White,

    // Tertiary colors
    tertiary = MitOrange,
    onTertiary = Color.Black,
    tertiaryContainer = MitGold,
    onTertiaryContainer = Color.Black,

    // Background colors
    background = AppBackgroundDark,
    onBackground = TextPrimaryDark,
    surface = SurfaceDark,
    onSurface = TextPrimaryDark,
    surfaceVariant = SurfaceVariantDark,
    onSurfaceVariant = TextSecondaryDark,

    // Other colors
    outline = DividerDark,
    outlineVariant = DividerDark,
    error = StatusRed,
    onError = Color.White,
    errorContainer = StatusRedLight,
    onErrorContainer = StatusRed
)

/**
 * Light color scheme using MIT brand colors
 */
private val LightColorScheme = lightColorScheme(
    // Primary colors
    primary = MitPurple,
    onPrimary = Color.White,
    primaryContainer = MitPurpleLight,
    onPrimaryContainer = Color.White,

    // Secondary colors
    secondary = MitTeal,
    onSecondary = Color.White,
    secondaryContainer = MitTealDark,
    onSecondaryContainer = Color.White,

    // Tertiary colors
    tertiary = MitGold,
    onTertiary = Color.White,
    tertiaryContainer = MitOrange,
    onTertiaryContainer = Color.White,

    // Background colors
    background = AppBackgroundLight,
    onBackground = TextPrimaryLight,
    surface = SurfaceLight,
    onSurface = TextPrimaryLight,
    surfaceVariant = SurfaceVariantLight,
    onSurfaceVariant = TextSecondaryLight,

    // Other colors
    outline = DividerLight,
    outlineVariant = DividerLight,
    error = StatusRed,
    onError = Color.White,
    errorContainer = StatusRedLight,
    onErrorContainer = StatusRed
)

/**
 * Main theme composable for the AMS Android app.
 *
 * @param darkTheme Whether to use dark theme (follows system by default)
 * @param dynamicColor Whether to use Material You dynamic colors (disabled to maintain brand)
 * @param content The content to display with this theme
 */
@Composable
fun AMSandroidTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = false, // Disabled to maintain MIT brand colors
    content: @Composable () -> Unit
) {
    val colorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColorScheme
        else -> LightColorScheme
    }

    // Update status bar appearance
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as? android.app.Activity)?.window
            if (window != null) {
                WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !darkTheme
            }
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}

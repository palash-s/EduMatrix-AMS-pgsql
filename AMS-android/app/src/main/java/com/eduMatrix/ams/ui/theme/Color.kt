package com.eduMatrix.ams.ui.theme

import androidx.compose.ui.graphics.Color

// ============================================
// MIT BRAND COLORS (Matching Web Application)
// ============================================

// Primary Purple Palette
val MitPurple = Color(0xFF48166D)          // Primary brand color (logo color - preserve)
val MitPurpleDark = Color(0xFF2D0D45)      // Dark variant for pressed states
val MitPurpleHover = Color(0xFF350F50)     // Hover state
val MitPurpleLight = Color(0xFF6B2D8E)     // Lighter variant

// Dark Mode Purple Variants (brighter for readability)
val MitPurpleDarkMode = Color(0xFFA855F7)  // Purple-500 - readable on dark backgrounds
val MitPurpleDarkModeLight = Color(0xFFC084FC) // Purple-400 - accent text on dark

// Secondary Colors
val MitTeal = Color(0xFF00A887)            // Success, positive actions
val MitTealDark = Color(0xFF008F72)        // Teal dark variant
val MitTealDarkMode = Color(0xFF2DD4BF)    // Teal-400 - brighter for dark mode
val MitOrange = Color(0xFFF17736)          // Warning, attention
val MitGold = Color(0xFFBF9D55)            // Accent, highlights

// ============================================
// STATUS COLORS
// ============================================

val StatusGreen = Color(0xFF22C55E)        // Present, Success, Granted
val StatusGreenLight = Color(0xFFDCFCE7)   // Light green background
val StatusRed = Color(0xFFEF4444)          // Absent, Error, Detained
val StatusRedLight = Color(0xFFFEE2E2)     // Light red background
val StatusYellow = Color(0xFFF59E0B)       // Warning, Provisional
val StatusYellowLight = Color(0xFFFEF3C7)  // Light yellow background
val StatusBlue = Color(0xFF3B82F6)         // Info
val StatusBlueLight = Color(0xFFDBEAFE)    // Light blue background

// ============================================
// BACKGROUND COLORS
// ============================================

// Light Theme Backgrounds
val AppBackgroundLight = Color(0xFFF8FAFC)    // Slate-50 (main background)
val SurfaceLight = Color(0xFFFFFFFF)          // White (cards, surfaces)
val SurfaceVariantLight = Color(0xFFF1F5F9)   // Slate-100 (secondary surfaces)
val DividerLight = Color(0xFFE2E8F0)          // Slate-200 (dividers, borders)

// Dark Theme Backgrounds
val AppBackgroundDark = Color(0xFF0B1220)     // Dark navy (main background)
val SurfaceDark = Color(0xFF1E293B)           // Slate-800 (cards)
val SurfaceVariantDark = Color(0xFF334155)    // Slate-700 (secondary surfaces)
val DividerDark = Color(0xFF475569)           // Slate-600 (dividers)

// ============================================
// TEXT COLORS
// ============================================

// Light Theme Text
val TextPrimaryLight = Color(0xFF0F172A)      // Slate-900 (primary text)
val TextSecondaryLight = Color(0xFF475569)    // Slate-600 (secondary text)
val TextTertiaryLight = Color(0xFF94A3B8)     // Slate-400 (disabled, hints)

// Dark Theme Text
val TextPrimaryDark = Color(0xFFF8FAFC)       // Slate-50 (primary text)
val TextSecondaryDark = Color(0xFFCBD5E1)     // Slate-300 (secondary text)
val TextTertiaryDark = Color(0xFF64748B)      // Slate-500 (disabled, hints)

// ============================================
// ROLE-SPECIFIC ACCENT COLORS
// ============================================

val AdminAccent = Color(0xFF8B5CF6)           // Violet for Admin
val StaffAccent = MitPurple                   // Purple for Staff
val StudentAccent = MitTeal                   // Teal for Student
val ParentAccent = Color(0xFF0EA5E9)          // Sky for Parent

// ============================================
// LEARNER TYPE COLORS
// ============================================

val SlowLearnerColor = StatusRed
val AverageLearnerColor = StatusYellow
val AdvancedLearnerColor = StatusGreen

// ============================================
// ATTENDANCE COLORS
// ============================================

val PresentColor = StatusGreen
val AbsentColor = StatusRed
val OnDutyColor = StatusBlue
val DefaulterColor = StatusRed
val SafeAttendanceColor = StatusGreen

// ============================================
// THEME-AWARE COLOR HELPERS
// ============================================

/**
 * Returns the appropriate purple color based on dark mode.
 * Use this for text/icons that need to be readable.
 * For filled buttons/containers, use MitPurple directly (it has white text on top).
 */
@androidx.compose.runtime.Composable
fun accentPurple(): Color {
    return if (androidx.compose.foundation.isSystemInDarkTheme()) MitPurpleDarkMode else MitPurple
}

/**
 * Returns the appropriate teal color based on dark mode.
 */
@androidx.compose.runtime.Composable
fun accentTeal(): Color {
    return if (androidx.compose.foundation.isSystemInDarkTheme()) MitTealDarkMode else MitTeal
}

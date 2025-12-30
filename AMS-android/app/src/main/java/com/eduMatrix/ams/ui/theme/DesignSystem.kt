package com.eduMatrix.ams.ui.theme

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * EduMatrix AMS Design System
 *
 * High-density Material Design 3 components optimized for power users.
 * All components are dark/light mode compatible using MaterialTheme colors.
 *
 * Key principles:
 * - Outlined cards (not elevated) with 1dp stroke
 * - 12dp corner radius (sharper, professional)
 * - Compact heights: List items 56dp, Buttons 40dp, Chips 24dp
 * - Bento grid layout with 16dp spacing
 */

// ============================================
// DESIGN TOKENS
// ============================================

object AmsDesign {
    // Corner Radii
    val CardRadius = 12.dp
    val ChipRadius = 6.dp
    val ButtonRadius = 8.dp

    // Heights
    val ListItemHeight = 56.dp
    val ButtonHeight = 40.dp
    val ChipHeight = 24.dp
    val CompactChipHeight = 20.dp

    // Spacing
    val GridSpacing = 16.dp
    val CardPadding = 16.dp
    val CompactPadding = 12.dp

    // Border
    val OutlineWidth = 1.dp
}

// ============================================
// THEME-AWARE COLOR HELPERS
// ============================================

/**
 * Returns the appropriate primary accent color based on theme.
 */
@Composable
fun primaryAccent(): Color = if (isSystemInDarkTheme()) MitPurpleDarkMode else MitPurple

/**
 * Returns the appropriate secondary accent color based on theme.
 */
@Composable
fun secondaryAccent(): Color = if (isSystemInDarkTheme()) MitTealDarkMode else MitTeal

// ============================================
// OUTLINED CARD (Primary card style)
// ============================================

/**
 * High-density outlined card following MD3 guidelines.
 * Uses 1dp border instead of elevation for a cleaner, professional look.
 * Fully dark/light mode compatible.
 */
@Composable
fun AmsCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    containerColor: Color = MaterialTheme.colorScheme.surface,
    borderColor: Color = MaterialTheme.colorScheme.outlineVariant,
    content: @Composable ColumnScope.() -> Unit
) {
    Card(
        modifier = modifier.then(
            if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier
        ),
        shape = RoundedCornerShape(AmsDesign.CardRadius),
        colors = CardDefaults.cardColors(containerColor = containerColor),
        border = BorderStroke(AmsDesign.OutlineWidth, borderColor),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Column(
            modifier = Modifier.padding(AmsDesign.CardPadding),
            content = content
        )
    }
}

/**
 * Compact card variant for dense layouts.
 */
@Composable
fun AmsCompactCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    containerColor: Color = MaterialTheme.colorScheme.surface,
    borderColor: Color = MaterialTheme.colorScheme.outlineVariant,
    content: @Composable ColumnScope.() -> Unit
) {
    Card(
        modifier = modifier.then(
            if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier
        ),
        shape = RoundedCornerShape(AmsDesign.CardRadius),
        colors = CardDefaults.cardColors(containerColor = containerColor),
        border = BorderStroke(AmsDesign.OutlineWidth, borderColor),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Column(
            modifier = Modifier.padding(AmsDesign.CompactPadding),
            content = content
        )
    }
}

// ============================================
// BENTO CARD (For dashboard widgets)
// ============================================

/**
 * Bento-style card for dashboard widgets.
 * Can have an accent color on the left border.
 */
@Composable
fun AmsBentoCard(
    modifier: Modifier = Modifier,
    title: String? = null,
    accentColor: Color? = null,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit
) {
    Card(
        modifier = modifier.then(
            if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier
        ),
        shape = RoundedCornerShape(AmsDesign.CardRadius),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(AmsDesign.OutlineWidth, MaterialTheme.colorScheme.outlineVariant),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Row(modifier = Modifier.fillMaxWidth()) {
            // Accent stripe
            if (accentColor != null) {
                Box(
                    modifier = Modifier
                        .width(4.dp)
                        .fillMaxHeight()
                        .background(accentColor)
                )
            }

            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(AmsDesign.CardPadding)
            ) {
                if (title != null) {
                    Text(
                        text = title,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                }
                content()
            }
        }
    }
}

// ============================================
// STATUS CHIPS (Compact 24dp height)
// ============================================

/**
 * Compact status chip for attendance status, leave type, etc.
 * Dark/light mode compatible.
 */
@Composable
fun AmsStatusChip(
    text: String,
    color: Color,
    modifier: Modifier = Modifier,
    filled: Boolean = false
) {
    val isDark = isSystemInDarkTheme()
    val bgAlpha = if (isDark) 0.2f else 0.1f
    val borderAlpha = if (isDark) 0.4f else 0.3f

    Surface(
        modifier = modifier.height(AmsDesign.ChipHeight),
        shape = RoundedCornerShape(AmsDesign.ChipRadius),
        color = if (filled) color else color.copy(alpha = bgAlpha),
        border = if (!filled) BorderStroke(1.dp, color.copy(alpha = borderAlpha)) else null
    ) {
        Box(
            modifier = Modifier.padding(horizontal = 8.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = text,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Medium,
                color = if (filled) Color.White else color
            )
        }
    }
}

/**
 * Selectable status chip for marking attendance.
 */
@Composable
fun AmsSelectableChip(
    text: String,
    isSelected: Boolean,
    selectedColor: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier
            .size(36.dp)
            .clip(RoundedCornerShape(AmsDesign.ButtonRadius))
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(AmsDesign.ButtonRadius),
        color = if (isSelected) selectedColor else Color.Transparent,
        border = if (!isSelected) BorderStroke(1.5.dp, MaterialTheme.colorScheme.outlineVariant) else null
    ) {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = text,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                color = if (isSelected) Color.White else MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

// ============================================
// COMPACT LIST ITEM (56dp height)
// ============================================

/**
 * High-density list item for student/staff lists.
 */
@Composable
fun AmsListItem(
    headlineText: String,
    modifier: Modifier = Modifier,
    supportingText: String? = null,
    leadingContent: @Composable (() -> Unit)? = null,
    trailingContent: @Composable (() -> Unit)? = null,
    onClick: (() -> Unit)? = null
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .height(AmsDesign.ListItemHeight)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        leadingContent?.invoke()

        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = headlineText,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                color = MaterialTheme.colorScheme.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            supportingText?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }

        trailingContent?.invoke()
    }
}

// ============================================
// BUTTONS (40dp height)
// ============================================

/**
 * Primary button with 40dp height.
 */
@Composable
fun AmsPrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    icon: ImageVector? = null
) {
    Button(
        onClick = onClick,
        modifier = modifier.height(AmsDesign.ButtonHeight),
        enabled = enabled,
        shape = RoundedCornerShape(AmsDesign.ButtonRadius),
        colors = ButtonDefaults.buttonColors(
            containerColor = primaryAccent(),
            contentColor = Color.White
        )
    ) {
        if (icon != null) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                modifier = Modifier.size(18.dp)
            )
            Spacer(modifier = Modifier.width(6.dp))
        }
        Text(
            text = text,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold
        )
    }
}

/**
 * Secondary outlined button.
 */
@Composable
fun AmsSecondaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    icon: ImageVector? = null,
    color: Color? = null
) {
    val buttonColor = color ?: primaryAccent()
    OutlinedButton(
        onClick = onClick,
        modifier = modifier.height(AmsDesign.ButtonHeight),
        enabled = enabled,
        shape = RoundedCornerShape(AmsDesign.ButtonRadius),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = buttonColor),
        border = BorderStroke(1.dp, buttonColor.copy(alpha = 0.5f))
    ) {
        if (icon != null) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                modifier = Modifier.size(18.dp)
            )
            Spacer(modifier = Modifier.width(6.dp))
        }
        Text(
            text = text,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Medium
        )
    }
}

// ============================================
// STAT DISPLAY COMPONENTS
// ============================================

/**
 * Stat display for dashboard cards.
 */
@Composable
fun AmsStatDisplay(
    value: String,
    label: String,
    modifier: Modifier = Modifier,
    valueColor: Color = MaterialTheme.colorScheme.onSurface
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = value,
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = valueColor
        )
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

/**
 * Horizontal stat row with icon.
 */
@Composable
fun AmsStatRow(
    icon: ImageVector,
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    iconColor: Color = MaterialTheme.colorScheme.primary
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                modifier = Modifier.size(18.dp),
                tint = iconColor
            )
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
}

// ============================================
// AVATAR & INDICATORS
// ============================================

/**
 * Circular avatar with initials or index.
 * Dark/light mode compatible.
 */
@Composable
fun AmsAvatar(
    text: String,
    modifier: Modifier = Modifier,
    size: Dp = 36.dp,
    backgroundColor: Color? = null,
    textColor: Color? = null
) {
    val isDark = isSystemInDarkTheme()
    val bgColor = backgroundColor ?: primaryAccent().copy(alpha = if (isDark) 0.2f else 0.1f)
    val txtColor = textColor ?: primaryAccent()

    Box(
        modifier = modifier
            .size(size)
            .clip(CircleShape)
            .background(bgColor),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = text.take(2).uppercase(),
            style = if (size >= 40.dp) MaterialTheme.typography.titleSmall else MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            color = txtColor
        )
    }
}

/**
 * Status indicator dot.
 */
@Composable
fun AmsStatusDot(
    color: Color,
    modifier: Modifier = Modifier,
    size: Dp = 8.dp
) {
    Box(
        modifier = modifier
            .size(size)
            .clip(CircleShape)
            .background(color)
    )
}

// ============================================
// SECTION HEADER
// ============================================

/**
 * Section header for dashboard sections.
 */
@Composable
fun AmsSectionHeader(
    title: String,
    modifier: Modifier = Modifier,
    action: @Composable (() -> Unit)? = null
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurface
        )
        action?.invoke()
    }
}

// ============================================
// EMPTY STATE
// ============================================

/**
 * Empty state component for when there's no data.
 */
@Composable
fun AmsEmptyState(
    icon: ImageVector,
    message: String,
    modifier: Modifier = Modifier,
    action: @Composable (() -> Unit)? = null
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            modifier = Modifier.size(48.dp),
            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
        )
        Text(
            text = message,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center
        )
        action?.invoke()
    }
}

// ============================================
// PROGRESS INDICATORS
// ============================================

/**
 * Compact linear progress with label.
 */
@Composable
fun AmsProgress(
    progress: Float,
    modifier: Modifier = Modifier,
    color: Color = primaryAccent(),
    trackColor: Color = MaterialTheme.colorScheme.surfaceVariant,
    showLabel: Boolean = true
) {
    Column(modifier = modifier) {
        if (showLabel) {
            Text(
                text = "${(progress * 100).toInt()}%",
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Medium,
                color = color,
                modifier = Modifier.align(Alignment.End)
            )
            Spacer(modifier = Modifier.height(4.dp))
        }
        LinearProgressIndicator(
            progress = { progress.coerceIn(0f, 1f) },
            modifier = Modifier
                .fillMaxWidth()
                .height(6.dp)
                .clip(RoundedCornerShape(3.dp)),
            color = color,
            trackColor = trackColor
        )
    }
}

// ============================================
// ALERT BANNER
// ============================================

/**
 * Alert banner for important notifications.
 * Dark/light mode compatible.
 */
@Composable
fun AmsAlertBanner(
    icon: ImageVector,
    title: String,
    message: String? = null,
    color: Color,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null
) {
    val isDark = isSystemInDarkTheme()
    val bgAlpha = if (isDark) 0.15f else 0.1f
    val borderAlpha = if (isDark) 0.4f else 0.3f

    Surface(
        modifier = modifier.fillMaxWidth().then(
            if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier
        ),
        shape = RoundedCornerShape(AmsDesign.CardRadius),
        color = color.copy(alpha = bgAlpha),
        border = BorderStroke(1.dp, color.copy(alpha = borderAlpha))
    ) {
        Row(
            modifier = Modifier.padding(AmsDesign.CompactPadding),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(24.dp)
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = color
                )
                message?.let {
                    Text(
                        text = it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}

// ============================================
// LOCKED STATUS BADGE (For attendance)
// ============================================

/**
 * Locked status badge for students with approved leaves.
 * Shows lock icon with status label.
 */
@Composable
fun AmsLockedBadge(
    label: String,
    color: Color,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null
) {
    val isDark = isSystemInDarkTheme()
    val bgAlpha = if (isDark) 0.2f else 0.15f

    Surface(
        modifier = modifier,
        color = color.copy(alpha = bgAlpha),
        shape = RoundedCornerShape(20.dp)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (icon != null) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    modifier = Modifier.size(14.dp),
                    tint = color
                )
            }
            Text(
                text = label,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                color = color
            )
        }
    }
}

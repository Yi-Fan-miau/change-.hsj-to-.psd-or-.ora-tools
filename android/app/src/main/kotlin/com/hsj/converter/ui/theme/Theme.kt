package com.hsj.converter.ui.theme

import android.app.Activity
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

object HsjColors {
    val Background = Color(0xFF0D0F16)
    val Surface = Color(0xFF151925)
    val Surface2 = Color(0xFF1C2230)
    val Surface3 = Color(0xFF232B3C)
    val Field = Color(0xFF10141E)
    val Border = Color(0xFF2A3145)
    val BorderSoft = Color(0xFF222838)
    val Text = Color(0xFFEDF1FA)
    val Text2 = Color(0xFFC7D0E3)
    val Muted = Color(0xFF98A2B8)
    val Hint = Color(0xFF8A94AB)
    val Primary = Color(0xFF6D4DFF)
    val PrimaryHi = Color(0xFF8B72FF)
    val Cyan = Color(0xFF2BD9F0)
    val Success = Color(0xFF37D6A0)
    val Warning = Color(0xFFF5C451)
    val Error = Color(0xFFFF7B8A)
    val Pink = Color(0xFFFF6BAE)
}

private val DarkScheme = darkColorScheme(
    primary = HsjColors.Primary,
    onPrimary = Color.White,
    primaryContainer = Color(0xFF2B2350),
    onPrimaryContainer = HsjColors.Text,
    secondary = HsjColors.Cyan,
    onSecondary = Color(0xFF06232A),
    background = HsjColors.Background,
    onBackground = HsjColors.Text,
    surface = HsjColors.Surface,
    onSurface = HsjColors.Text,
    surfaceVariant = HsjColors.Surface2,
    onSurfaceVariant = HsjColors.Text2,
    outline = HsjColors.Border,
    error = HsjColors.Error,
    onError = Color.White,
)

private val HsjTypography = Typography(
    headlineLarge = TextStyle(
        fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Bold,
        fontSize = 26.sp, letterSpacing = (-0.2).sp),
    headlineSmall = TextStyle(
        fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp),
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Bold,
        fontSize = 18.sp),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold,
        fontSize = 15.sp),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif, fontSize = 15.sp, lineHeight = 22.sp),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif, fontSize = 13.sp, lineHeight = 19.sp),
    bodySmall = TextStyle(
        fontFamily = FontFamily.SansSerif, fontSize = 12.sp, lineHeight = 17.sp),
    labelSmall = TextStyle(
        fontFamily = FontFamily.SansSerif, fontSize = 11.sp, lineHeight = 15.sp),
)

@Composable
fun HsjTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkScheme,
        typography = HsjTypography,
        content = content,
    )
}

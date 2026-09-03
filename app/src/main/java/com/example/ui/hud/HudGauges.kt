package com.example.ui.hud

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bluetooth
import androidx.compose.material.icons.filled.BluetoothConnected
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.model.BluetoothState
import com.example.model.DrivingMode
import com.example.model.TelemetryData
import com.example.ui.theme.AlertRed
import com.example.ui.theme.CyberCyan
import com.example.ui.theme.HudBorder
import com.example.ui.theme.HudSurface
import com.example.ui.theme.NeonGreen
import com.example.ui.theme.TextMuted
import com.example.ui.theme.TextPrimary
import com.example.ui.theme.TextSecondary
import com.example.ui.theme.WarningAmber

/**
 * Top Telemetry and Status Bar
 */
@Composable
fun TopStatusBar(
    drivingMode: DrivingMode,
    bluetoothState: BluetoothState,
    deviceName: String?,
    telemetry: TelemetryData,
    onOpenBtDialog: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 6.dp),
        color = Color(0xDD080D1A),
        shape = RoundedCornerShape(12.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, HudBorder)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            // Driving Mode & Vision Model Badges
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                DrivingModePill(mode = drivingMode)
                VisionModelBadge(model = telemetry.activeVisionModel)
            }

            // Telemetry Counters
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                TelemetryItem(label = "INFERENCE", value = "${telemetry.aiInferenceMs}ms", color = CyberCyan)
                TelemetryItem(label = "CAM FPS", value = "${telemetry.fps}", color = NeonGreen)
                TelemetryItem(label = "STEER", value = String.format("%.1f°", telemetry.steeringAngleDeg), color = TextPrimary)
                TelemetryItem(label = "TARGETS", value = "${telemetry.detectedObstaclesCount}", color = if (telemetry.isPathClear) NeonGreen else WarningAmber)
            }

            // Bluetooth Status Button / Chip
            BluetoothStatusChip(
                state = bluetoothState,
                deviceName = deviceName,
                txHz = telemetry.btTransmitHz,
                pingMs = telemetry.btPingMs,
                onClick = onOpenBtDialog
            )
        }
    }
}

@Composable
fun DrivingModePill(mode: DrivingMode) {
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val alphaAnim by infiniteTransition.animateFloat(
        initialValue = 0.7f,
        targetValue = 1.0f,
        animationSpec = infiniteRepeatable(
            animation = tween(800, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "alpha"
    )

    val (bgColor, borderColor, textColor) = when (mode) {
        DrivingMode.FULL_AUTONOMOUS -> Triple(Color(0xFF004D40), Color(0xFF00E5FF), Color(0xFF80DEEA))
        DrivingMode.LANE_KEEP -> Triple(Color(0xFF0D47A1), Color(0xFF29B6F6), Color(0xFFB3E5FC))
        DrivingMode.ADAPTIVE_CRUISE -> Triple(Color(0xFF4A148C), Color(0xFFAB47BC), Color(0xFFE1BEE7))
        DrivingMode.MANUAL -> Triple(Color(0xFF212121), Color(0xFF757575), Color(0xFFE0E0E0))
    }

    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(bgColor.copy(alpha = if (mode == DrivingMode.FULL_AUTONOMOUS) alphaAnim else 0.85f))
            .border(1.dp, borderColor, RoundedCornerShape(8.dp))
            .padding(horizontal = 10.dp, vertical = 4.dp),
        contentAlignment = Alignment.Center
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(borderColor)
            )
            Spacer(modifier = Modifier.width(6.dp))
            Text(
                text = mode.label,
                color = textColor,
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace
            )
        }
    }
}

@Composable
fun VisionModelBadge(model: com.example.model.VisionModelType) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(Color(0xFF0F172A))
            .border(1.dp, Color(0xFF334155), RoundedCornerShape(8.dp))
            .padding(horizontal = 8.dp, vertical = 4.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = model.shortLabel,
            color = CyberCyan,
            fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold,
            fontFamily = FontFamily.Monospace
        )
    }
}

@Composable
private fun TelemetryItem(label: String, value: String, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = label,
            color = TextMuted,
            fontSize = 9.sp,
            fontWeight = FontWeight.SemiBold
        )
        Text(
            text = value,
            color = color,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace
        )
    }
}

@Composable
fun BluetoothStatusChip(
    state: BluetoothState,
    deviceName: String?,
    txHz: Int,
    pingMs: Int,
    onClick: () -> Unit
) {
    val (color, text) = when (state) {
        BluetoothState.CONNECTED -> Pair(NeonGreen, deviceName ?: "HID Host ($txHz Hz)")
        BluetoothState.CONNECTING -> Pair(WarningAmber, "Connecting...")
        BluetoothState.ADVERTISING -> Pair(CyberCyan, "HID Advertising")
        BluetoothState.DISCONNECTED -> Pair(TextSecondary, "BT Disconnected")
        BluetoothState.DISABLED -> Pair(AlertRed, "BT Disabled")
        BluetoothState.UNAVAILABLE -> Pair(TextMuted, "No Bluetooth")
        BluetoothState.ERROR -> Pair(AlertRed, "BT Error")
    }

    Surface(
        onClick = onClick,
        color = HudSurface,
        shape = RoundedCornerShape(8.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, color.copy(alpha = 0.5f)),
        modifier = Modifier.testTag("bluetooth_status_button")
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = if (state == BluetoothState.CONNECTED) Icons.Default.BluetoothConnected else Icons.Default.Bluetooth,
                contentDescription = "Bluetooth Status",
                tint = color,
                modifier = Modifier.size(16.dp)
            )
            Spacer(modifier = Modifier.width(6.dp))
            Text(
                text = text,
                color = color,
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
                fontFamily = FontFamily.Monospace
            )
        }
    }
}

/**
 * Large Cockpit Digital Speedometer
 */
@Composable
fun SpeedometerCockpit(
    speedKmh: Float,
    targetSpeedKmh: Float,
    gear: String,
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier
            .size(110.dp)
            .clip(CircleShape)
            .background(Color(0xCC09101F))
            .border(2.dp, Brush.radialGradient(listOf(CyberCyan, Color(0xFF0F172A))), CircleShape),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = String.format("%.0f", speedKmh),
                color = TextPrimary,
                fontSize = 34.sp,
                fontWeight = FontWeight.ExtraBold,
                fontFamily = FontFamily.Monospace
            )
            Text(
                text = "KM/H",
                color = CyberCyan,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = "GEAR: $gear | TGT: ${targetSpeedKmh.toInt()}",
                color = TextSecondary,
                fontSize = 9.sp,
                fontFamily = FontFamily.Monospace
            )
        }
    }
}

/**
 * Vertical Throttle & Brake LED Bar Meters
 */
@Composable
fun ThrottleBrakeBars(
    throttlePct: Int,
    brakePct: Int,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .height(130.dp)
            .background(Color(0xCC09101F), RoundedCornerShape(8.dp))
            .border(1.dp, HudBorder, RoundedCornerShape(8.dp))
            .padding(horizontal = 8.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        // Throttle (GAS) Meter
        VerticalLedBar(
            label = "THROTTLE",
            percent = throttlePct,
            activeColor = CyberCyan,
            barColor = NeonGreen
        )

        // Brake Meter
        VerticalLedBar(
            label = "BRAKE",
            percent = brakePct,
            activeColor = WarningAmber,
            barColor = AlertRed
        )
    }
}

@Composable
private fun VerticalLedBar(
    label: String,
    percent: Int,
    activeColor: Color,
    barColor: Color
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.width(32.dp)
    ) {
        Text(
            text = "$percent%",
            color = activeColor,
            fontSize = 9.sp,
            fontWeight = FontWeight.Bold,
            fontFamily = FontFamily.Monospace
        )
        Spacer(modifier = Modifier.height(4.dp))

        // Vertical Bar Container
        Box(
            modifier = Modifier
                .width(14.dp)
                .weight(1f)
                .clip(RoundedCornerShape(3.dp))
                .background(Color(0xFF1E293B)),
            contentAlignment = Alignment.BottomCenter
        ) {
            val fillFraction = (percent / 100f).coerceIn(0f, 1f)
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .fillMaxHeight(fillFraction)
                    .background(
                        Brush.verticalGradient(
                            listOf(barColor, activeColor)
                        )
                    )
            )
        }

        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = label.take(3),
            color = TextMuted,
            fontSize = 8.sp,
            fontWeight = FontWeight.Bold
        )
    }
}

/**
 * Emergency Collision Warning Banner (AEB Active)
 */
@Composable
fun CollisionWarningBanner(
    telemetry: TelemetryData,
    modifier: Modifier = Modifier
) {
    AnimatedVisibility(
        visible = telemetry.collisionWarning || telemetry.emergencyBrakingActive,
        enter = fadeIn(),
        exit = fadeOut(),
        modifier = modifier
    ) {
        val isAeb = telemetry.emergencyBrakingActive
        val bannerBg = if (isAeb) Color(0xEEB71C1C) else Color(0xEEF57F17)
        val bannerText = if (isAeb) "⚠ EMERGENCY BRAKE APPLIED (AEB ACTIVE) ⚠" else "⚠ COLLISION WARNING - OBSTACLE AHEAD ⚠"

        Box(
            modifier = Modifier
                .fillMaxWidth(0.7f)
                .clip(RoundedCornerShape(10.dp))
                .background(bannerBg)
                .border(2.dp, Color.White, RoundedCornerShape(10.dp))
                .padding(horizontal = 16.dp, vertical = 8.dp),
            contentAlignment = Alignment.Center
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.Warning,
                    contentDescription = "Warning",
                    tint = Color.White,
                    modifier = Modifier.size(22.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = bannerText,
                    color = Color.White,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.ExtraBold,
                    fontFamily = FontFamily.Monospace
                )
            }
        }
    }
}

package com.example.ui.hud

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ElectricBolt
import androidx.compose.material.icons.filled.Keyboard
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.PowerSettingsNew
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.bluetooth.HidDescriptor
import com.example.model.ControllerState
import com.example.model.DrivingMode
import com.example.model.VehicleGear
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
 * Direct Keyboard WASD + Space Vehicle Control Interface
 * - W: Accelerate / Throttle (0x1A)
 * - A: Steer Left (0x04)
 * - S: Brake / Reverse (0x16)
 * - D: Steer Right (0x07)
 * - Space: Handbrake (0x2C)
 */
@Composable
fun ManualControlPad(
    currentMode: DrivingMode,
    currentGear: VehicleGear,
    isAiActive: Boolean,
    typedText: String,
    onClearTypedText: () -> Unit,
    onTestSequence: () -> Unit,
    onToggleAiActive: () -> Unit,
    onManualStateChange: (ControllerState) -> Unit,
    onGearChange: (VehicleGear) -> Unit,
    onHorn: () -> Unit,
    onLightsToggle: () -> Unit,
    modifier: Modifier = Modifier
) {
    // Keyboard key states
    var keyW by remember { mutableStateOf(false) }
    var keyA by remember { mutableStateOf(false) }
    var keyS by remember { mutableStateOf(false) }
    var keyD by remember { mutableStateOf(false) }
    var keySpace by remember { mutableStateOf(false) }

    fun emitState() {
        val steerVal = when {
            keyA && !keyD -> -1.0f
            keyD && !keyA -> 1.0f
            else -> 0.0f
        }
        val throttleVal = if (keyW) 1.0f else 0.0f
        val brakeVal = if (keyS) 1.0f else 0.0f

        onManualStateChange(
            ControllerState(
                keyW = keyW,
                keyA = keyA,
                keyS = keyS,
                keyD = keyD,
                keySpace = keySpace,
                steering = steerVal,
                throttle = throttleVal,
                brake = brakeVal,
                reverse = (currentGear == VehicleGear.REVERSE)
            )
        )
    }

    val rawReport = HidDescriptor.buildKeyboardReport(
        keyW = keyW,
        keyA = keyA,
        keyS = keyS,
        keyD = keyD,
        keySpace = keySpace
    )
    val hexString = rawReport.joinToString(" ") { String.format("%02X", it) }

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 6.dp, vertical = 2.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        // --- Row 1: Live On-Screen Typed Text & Real-Time Hex Byte Stream Bar ---
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(8.dp),
            color = Color(0xDD040814),
            border = BorderStroke(1.dp, if (rawReport.any { it != 0.toByte() }) NeonGreen else HudBorder)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Live Screen Typed Text
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    Text(
                        text = "TYPED:",
                        color = CyberCyan,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.ExtraBold,
                        fontFamily = FontFamily.Monospace
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = if (typedText.isEmpty()) "> [Press WASD below]" else "> $typedText █",
                        color = if (typedText.isEmpty()) TextMuted else Color.White,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.ExtraBold,
                        fontFamily = FontFamily.Monospace,
                        maxLines = 1
                    )
                }

                // Live 8-Byte Hex Stream
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = Color(0xFF0D1726),
                        border = BorderStroke(1.dp, HudBorder)
                    ) {
                        Text(
                            text = "HEX: [$hexString]",
                            color = if (rawReport.any { it != 0.toByte() }) NeonGreen else TextSecondary,
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }

                    // Test WASD Button
                    Button(
                        onClick = onTestSequence,
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF16325C)),
                        shape = RoundedCornerShape(4.dp),
                        modifier = Modifier.height(26.dp)
                    ) {
                        Text("TEST WASD", color = CyberCyan, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                    }

                    // Clear Text Button
                    Button(
                        onClick = onClearTypedText,
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF222F3E)),
                        shape = RoundedCornerShape(4.dp),
                        modifier = Modifier.height(26.dp)
                    ) {
                        Text("CLR", color = TextSecondary, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        // --- Row 2: AI Sleep / Battery Saver Toggle + Active Key Status Badges ---
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            // AI Vision Battery Saver Sleep Toggle Button
            Surface(
                onClick = onToggleAiActive,
                shape = RoundedCornerShape(8.dp),
                color = if (isAiActive) Color(0xCC0D2818) else Color(0xCC2A1E08),
                border = BorderStroke(
                    1.dp,
                    if (isAiActive) NeonGreen else WarningAmber
                ),
                modifier = Modifier.testTag("ai_battery_saver_toggle_button")
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Icon(
                        imageVector = if (isAiActive) Icons.Default.ElectricBolt else Icons.Default.PowerSettingsNew,
                        contentDescription = "AI Vision Power Status",
                        tint = if (isAiActive) NeonGreen else WarningAmber,
                        modifier = Modifier.size(14.dp)
                    )
                    Text(
                        text = if (isAiActive) "AI VISION: ACTIVE" else "AI SLEEP (SAVING CHARGE)",
                        color = if (isAiActive) NeonGreen else WarningAmber,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.ExtraBold,
                        fontFamily = FontFamily.Monospace
                    )
                }
            }

            // Real-Time Active Key Badges with USB HID Keycodes
            Row(
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                KeyStatusBadge(key = "W (0x1A)", isActive = keyW, activeColor = NeonGreen)
                KeyStatusBadge(key = "A (0x04)", isActive = keyA, activeColor = CyberCyan)
                KeyStatusBadge(key = "S (0x16)", isActive = keyS, activeColor = AlertRed)
                KeyStatusBadge(key = "D (0x07)", isActive = keyD, activeColor = CyberCyan)
                KeyStatusBadge(key = "SPACE (0x2C)", isActive = keySpace, activeColor = WarningAmber)
            }
        }

        // --- Row 3: Main Driving Control: Full Ergonomic WASD + Space Keyboard ---
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Left: Steering Keys [A] (Left) and [D] (Right)
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                TactileKeyButton(
                    keyChar = "A",
                    label = "LEFT (0x04)",
                    isPressed = keyA,
                    activeColor = CyberCyan,
                    modifier = Modifier.size(72.dp, 60.dp).testTag("key_a_left"),
                    onPressChange = { pressed ->
                        keyA = pressed
                        emitState()
                    }
                )

                TactileKeyButton(
                    keyChar = "D",
                    label = "RIGHT (0x07)",
                    isPressed = keyD,
                    activeColor = CyberCyan,
                    modifier = Modifier.size(72.dp, 60.dp).testTag("key_d_right"),
                    onPressChange = { pressed ->
                        keyD = pressed
                        emitState()
                    }
                )
            }

            // Center: Longitudinal Keys [W] (Accelerate) and [S] (Brake / Reverse)
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                TactileKeyButton(
                    keyChar = "W",
                    label = "▲ ACCEL (0x1A)",
                    isPressed = keyW,
                    activeColor = NeonGreen,
                    modifier = Modifier.size(96.dp, 52.dp).testTag("key_w_accel"),
                    onPressChange = { pressed ->
                        keyW = pressed
                        emitState()
                    }
                )

                TactileKeyButton(
                    keyChar = "S",
                    label = "▼ BRAKE (0x16)",
                    isPressed = keyS,
                    activeColor = AlertRed,
                    modifier = Modifier.size(96.dp, 52.dp).testTag("key_s_brake"),
                    onPressChange = { pressed ->
                        keyS = pressed
                        emitState()
                    }
                )
            }

            // Right: Handbrake [SPACE]
            TactileKeyButton(
                keyChar = "SPACE",
                label = "HANDBRAKE (0x2C)",
                isPressed = keySpace,
                activeColor = WarningAmber,
                modifier = Modifier.size(112.dp, 108.dp).testTag("key_space_handbrake"),
                onPressChange = { pressed ->
                    keySpace = pressed
                    emitState()
                }
            )
        }
    }
}

/**
 * Tactile Mechanical Keyboard Key Composable with low-latency touch & release detection
 */
@Composable
private fun TactileKeyButton(
    keyChar: String,
    label: String,
    isPressed: Boolean,
    activeColor: Color,
    modifier: Modifier = Modifier,
    onPressChange: (Boolean) -> Unit
) {
    val bgColor by animateColorAsState(
        targetValue = if (isPressed) activeColor.copy(alpha = 0.95f) else Color(0xEE0D1626),
        label = "key_bg_color"
    )

    val borderColor by animateColorAsState(
        targetValue = if (isPressed) Color.White else HudBorder,
        label = "key_border_color"
    )

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(
                if (isPressed) {
                    Brush.verticalGradient(
                        listOf(activeColor, activeColor.copy(alpha = 0.75f))
                    )
                } else {
                    Brush.verticalGradient(
                        listOf(Color(0xFF142136), Color(0xFF090F1A))
                    )
                }
            )
            .border(1.5.dp, borderColor, RoundedCornerShape(10.dp))
            .pointerInput(onPressChange) {
                awaitEachGesture {
                    awaitFirstDown(requireUnconsumed = false)
                    onPressChange(true)
                    waitForUpOrCancellation()
                    onPressChange(false)
                }
            },
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = keyChar,
                color = if (isPressed) Color.Black else Color.White,
                fontSize = if (keyChar.length > 1) 12.sp else 18.sp,
                fontWeight = FontWeight.ExtraBold,
                fontFamily = FontFamily.Monospace
            )
            Text(
                text = label,
                color = if (isPressed) Color.Black.copy(alpha = 0.85f) else activeColor,
                fontSize = 7.5.sp,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace
            )
        }
    }
}

/**
 * Key status indicator pill
 */
@Composable
private fun KeyStatusBadge(
    key: String,
    isActive: Boolean,
    activeColor: Color
) {
    Surface(
        shape = RoundedCornerShape(4.dp),
        color = if (isActive) activeColor else Color(0xFF131E2E),
        border = BorderStroke(1.dp, if (isActive) Color.White else HudBorder)
    ) {
        Text(
            text = key,
            color = if (isActive) Color.Black else TextSecondary,
            fontSize = 8.sp,
            fontWeight = FontWeight.ExtraBold,
            fontFamily = FontFamily.Monospace,
            modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
        )
    }
}

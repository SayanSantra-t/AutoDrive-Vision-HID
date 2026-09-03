package com.example.ui.dialogs

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Keyboard
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.window.Dialog
import com.example.bluetooth.HidDescriptor
import com.example.model.ControllerState
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
 * Interactive Real-time Bluetooth HID Keyboard (WASD + Space) Packet & Keystroke Inspector
 */
@Composable
fun GamepadVisualizerDialog(
    controllerState: ControllerState,
    typedText: String,
    lastEvent: String,
    onTestKey: (String) -> Unit,
    onSendSequence: (String) -> Unit,
    onClearText: () -> Unit,
    onUpdateState: (ControllerState) -> Unit,
    onDismiss: () -> Unit
) {
    // Local interactive test override states
    var localW by remember { mutableStateOf(false) }
    var localA by remember { mutableStateOf(false) }
    var localS by remember { mutableStateOf(false) }
    var localD by remember { mutableStateOf(false) }
    var localSpace by remember { mutableStateOf(false) }

    val activeW = controllerState.isAccelerating || localW
    val activeA = controllerState.isSteeringLeft || localA
    val activeS = controllerState.isBraking || localS
    val activeD = controllerState.isSteeringRight || localD
    val activeSpace = controllerState.isHandbrake || localSpace

    val rawReport = HidDescriptor.buildKeyboardReport(
        keyW = activeW,
        keyA = activeA,
        keyS = activeS,
        keyD = activeD,
        keySpace = activeSpace
    )

    val hexBytes = rawReport.joinToString(" ") { String.format("0x%02X", it) }

    fun syncLocal() {
        onUpdateState(
            ControllerState(
                keyW = localW,
                keyA = localA,
                keyS = localS,
                keyD = localD,
                keySpace = localSpace,
                steering = if (localA) -1f else if (localD) 1f else 0f,
                throttle = if (localW) 1f else 0f,
                brake = if (localS) 1f else 0f
            )
        )
    }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.98f)
                .padding(vertical = 8.dp)
                .testTag("gamepad_visualizer_dialog"),
            colors = CardDefaults.cardColors(containerColor = HudSurface),
            shape = RoundedCornerShape(16.dp),
            border = BorderStroke(1.5.dp, CyberCyan)
        ) {
            Column(
                modifier = Modifier
                    .padding(14.dp)
                    .verticalScroll(rememberScrollState()),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.Keyboard,
                            contentDescription = "Keyboard",
                            tint = CyberCyan,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = "BLUETOOTH KEYBOARD TESTER",
                            color = CyberCyan,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.ExtraBold,
                            fontFamily = FontFamily.Monospace
                        )
                    }
                    IconButton(
                        onClick = onDismiss,
                        modifier = Modifier.size(28.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Clear,
                            contentDescription = "Close",
                            tint = TextSecondary,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                }

                Text(
                    text = "Tap any key below to test WASD output and inspect USB/BT HID bytes",
                    color = TextSecondary,
                    fontSize = 11.sp,
                    modifier = Modifier.align(Alignment.Start)
                )

                Spacer(modifier = Modifier.height(10.dp))

                // --- Live On-Screen Typed Text Box ---
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp),
                    color = Color(0xFF040914),
                    border = BorderStroke(1.dp, NeonGreen)
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "ON-SCREEN TYPED TEXT OUTPUT:",
                                color = NeonGreen,
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace
                            )
                            Button(
                                onClick = onClearText,
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1E293B)),
                                shape = RoundedCornerShape(4.dp),
                                modifier = Modifier.height(24.dp)
                            ) {
                                Text("CLEAR", color = TextSecondary, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                        Spacer(modifier = Modifier.height(6.dp))
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(Color(0xFF02040A), RoundedCornerShape(6.dp))
                                .border(1.dp, HudBorder, RoundedCornerShape(6.dp))
                                .padding(horizontal = 10.dp, vertical = 8.dp)
                        ) {
                            Text(
                                text = if (typedText.isEmpty()) "> (No keys pressed yet. Tap keys below!)" else "> $typedText █",
                                color = if (typedText.isEmpty()) TextMuted else Color.White,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // --- Interactive WASD Key Matrix (Tap or Hold) ---
                Text(
                    text = "INTERACTIVE WASD KEYS (TAP / HOLD TO TEST):",
                    color = TextPrimary,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.align(Alignment.Start)
                )
                Spacer(modifier = Modifier.height(6.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceEvenly,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Left Keys: A / D
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        InteractiveDialogKey(
                            keyChar = "A",
                            label = "STEER LEFT",
                            hidHex = "0x04",
                            isActive = activeA,
                            activeColor = CyberCyan,
                            onPress = { pressed ->
                                localA = pressed
                                syncLocal()
                                if (pressed) onTestKey("A")
                            }
                        )
                        InteractiveDialogKey(
                            keyChar = "D",
                            label = "STEER RIGHT",
                            hidHex = "0x07",
                            isActive = activeD,
                            activeColor = CyberCyan,
                            onPress = { pressed ->
                                localD = pressed
                                syncLocal()
                                if (pressed) onTestKey("D")
                            }
                        )
                    }

                    // Center Keys: W / S
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        InteractiveDialogKey(
                            keyChar = "W",
                            label = "ACCEL / GAS",
                            hidHex = "0x1A",
                            isActive = activeW,
                            activeColor = NeonGreen,
                            onPress = { pressed ->
                                localW = pressed
                                syncLocal()
                                if (pressed) onTestKey("W")
                            }
                        )
                        InteractiveDialogKey(
                            keyChar = "S",
                            label = "BRAKE / REV",
                            hidHex = "0x16",
                            isActive = activeS,
                            activeColor = AlertRed,
                            onPress = { pressed ->
                                localS = pressed
                                syncLocal()
                                if (pressed) onTestKey("S")
                            }
                        )
                    }

                    // Right Key: SPACE
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        InteractiveDialogKey(
                            keyChar = "SPACE",
                            label = "HANDBRAKE",
                            hidHex = "0x2C",
                            isActive = activeSpace,
                            activeColor = WarningAmber,
                            onPress = { pressed ->
                                localSpace = pressed
                                syncLocal()
                                if (pressed) onTestKey("SPACE")
                            }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // --- Quick Test Pulse Keystroke Actions ---
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Button(
                        onClick = { onSendSequence("WASD") },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF132F4C)),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.weight(1f).height(38.dp)
                    ) {
                        Icon(Icons.Default.PlayArrow, contentDescription = "Run", tint = CyberCyan, modifier = Modifier.size(14.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("TYPE 'WASD'", color = CyberCyan, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    }

                    Button(
                        onClick = { onTestKey("W") },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0D2818)),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.weight(1f).height(38.dp)
                    ) {
                        Text("PULSE 'W'", color = NeonGreen, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    }

                    Button(
                        onClick = { onTestKey("SPACE") },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2E1C0A)),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.weight(1f).height(38.dp)
                    ) {
                        Text("PULSE SPACE", color = WarningAmber, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // --- Live 8-Byte HID Keyboard Report Frame ---
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp),
                    color = Color(0xFF070E1A),
                    border = BorderStroke(1.dp, HudBorder)
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                text = "RAW HID KEYBOARD REPORT (8 BYTES)",
                                color = CyberCyan,
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace
                            )
                            Text(
                                text = if (rawReport.any { it != 0.toByte() }) "TRANSMITTING KEYS" else "KEYBOARD IDLE",
                                color = if (rawReport.any { it != 0.toByte() }) NeonGreen else TextMuted,
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace
                            )
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = hexBytes,
                            color = if (rawReport.any { it != 0.toByte() }) NeonGreen else Color(0xFF88A0C0),
                            fontSize = 13.sp,
                            fontWeight = FontWeight.ExtraBold,
                            fontFamily = FontFamily.Monospace
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Byte 0: Modifiers | Byte 1: Reserved | Bytes 2..7: Active USB Keycodes (W=0x1A, A=0x04, S=0x16, D=0x07, Space=0x2C)",
                            color = TextMuted,
                            fontSize = 8.sp,
                            fontFamily = FontFamily.Monospace
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                OutlinedButton(
                    onClick = onDismiss,
                    border = BorderStroke(1.dp, CyberCyan),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth(0.6f)
                ) {
                    Text(text = "CLOSE INSPECTOR", color = CyberCyan, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun InteractiveDialogKey(
    keyChar: String,
    label: String,
    hidHex: String,
    isActive: Boolean,
    activeColor: Color,
    onPress: (Boolean) -> Unit
) {
    val bgColor by animateColorAsState(
        targetValue = if (isActive) activeColor else Color(0xFF0F172A),
        label = "dlg_key_bg"
    )

    Box(
        modifier = Modifier
            .size(76.dp, 56.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(bgColor)
            .border(1.5.dp, if (isActive) Color.White else HudBorder, RoundedCornerShape(8.dp))
            .pointerInput(Unit) {
                detectTapGestures(
                    onPress = {
                        onPress(true)
                        tryAwaitRelease()
                        onPress(false)
                    }
                )
            },
        contentAlignment = Alignment.Center
    ) {
        Column(
            modifier = Modifier.padding(2.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = keyChar,
                color = if (isActive) Color.Black else TextPrimary,
                fontSize = if (keyChar.length > 1) 11.sp else 16.sp,
                fontWeight = FontWeight.ExtraBold,
                fontFamily = FontFamily.Monospace
            )
            Text(
                text = label,
                color = if (isActive) Color.Black.copy(alpha = 0.8f) else activeColor,
                fontSize = 7.sp,
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace
            )
            Text(
                text = hidHex,
                color = if (isActive) Color.Black.copy(alpha = 0.7f) else TextMuted,
                fontSize = 7.sp,
                fontFamily = FontFamily.Monospace
            )
        }
    }
}

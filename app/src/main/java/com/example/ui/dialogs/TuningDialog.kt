package com.example.ui.dialogs

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.example.model.VehicleConfig
import com.example.model.VisionModelType
import com.example.ui.theme.CyberCyan
import com.example.ui.theme.HudBorder
import com.example.ui.theme.HudSurface
import com.example.ui.theme.NeonGreen
import com.example.ui.theme.TextMuted
import com.example.ui.theme.TextPrimary
import com.example.ui.theme.TextSecondary
import com.example.ui.theme.WarningAmber

/**
 * Autonomous Driving PID, Model Selection, & AI Vision Calibration Dialog
 */
@Composable
fun TuningDialog(
    currentConfig: VehicleConfig,
    onSaveConfig: (VehicleConfig) -> Unit,
    onDismiss: () -> Unit
) {
    var kp by remember { mutableFloatStateOf(currentConfig.kp) }
    var ki by remember { mutableFloatStateOf(currentConfig.ki) }
    var kd by remember { mutableFloatStateOf(currentConfig.kd) }
    var stanleyK by remember { mutableFloatStateOf(currentConfig.stanleyK) }
    var cruiseSpeed by remember { mutableFloatStateOf(currentConfig.cruiseTargetSpeedKmh) }
    var maxSteerDeg by remember { mutableFloatStateOf(currentConfig.maxSteeringAngleDeg) }
    var followDistance by remember { mutableFloatStateOf(currentConfig.safetyFollowDistanceM) }
    var emergencyTtc by remember { mutableFloatStateOf(currentConfig.emergencyBrakeTtcSec) }
    var confidenceThresh by remember { mutableFloatStateOf(currentConfig.confidenceThreshold) }
    var horizonRatio by remember { mutableFloatStateOf(currentConfig.cameraHorizonRatio) }
    var visionModel by remember { mutableStateOf(currentConfig.visionModelType) }
    var invertSteer by remember { mutableStateOf(currentConfig.invertSteering) }
    var invertThrottle by remember { mutableStateOf(currentConfig.invertThrottle) }
    var useSerial by remember { mutableStateOf(currentConfig.useSerialFallback) }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.95f)
                .padding(vertical = 16.dp)
                .testTag("tuning_dialog_card"),
            colors = CardDefaults.cardColors(containerColor = HudSurface),
            shape = RoundedCornerShape(16.dp),
            border = androidx.compose.foundation.BorderStroke(1.dp, CyberCyan)
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Text(
                    text = "AI VISION & AUTONOMOUS TUNING",
                    color = CyberCyan,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.ExtraBold,
                    fontFamily = FontFamily.Monospace
                )
                Text(
                    text = "Select neural detection model, tune AEB sensitivity and steering gains",
                    color = TextSecondary,
                    fontSize = 11.sp
                )

                Spacer(modifier = Modifier.height(16.dp))

                // AI Model Selection Section
                SectionHeader(title = "AI VISION & OBJECT DETECTION MODEL")

                VisionModelSelector(
                    selectedModel = visionModel,
                    onSelect = { visionModel = it }
                )

                Spacer(modifier = Modifier.height(14.dp))

                // Obstacle Avoidance & AEB Calibration
                SectionHeader(title = "OBSTACLE DETECTION & BRAKING (AEB)")

                SliderField(
                    label = "Detection Confidence Threshold",
                    value = confidenceThresh,
                    range = 0.25f..0.90f,
                    formatted = "${(confidenceThresh * 100).toInt()}%",
                    onValueChange = { confidenceThresh = it }
                )

                SliderField(
                    label = "Safety Follow Distance Gap (m)",
                    value = followDistance,
                    range = 1.0f..6.0f,
                    formatted = String.format("%.1f m", followDistance),
                    onValueChange = { followDistance = it }
                )

                SliderField(
                    label = "Emergency Brake TTC Threshold (s)",
                    value = emergencyTtc,
                    range = 0.4f..2.0f,
                    formatted = String.format("%.2f s", emergencyTtc),
                    onValueChange = { emergencyTtc = it }
                )

                SliderField(
                    label = "Camera Horizon Line (% from top)",
                    value = horizonRatio,
                    range = 0.20f..0.70f,
                    formatted = "${(horizonRatio * 100).toInt()}%",
                    onValueChange = { horizonRatio = it }
                )

                Spacer(modifier = Modifier.height(14.dp))

                // PID Steering Section
                SectionHeader(title = "STANLEY & PID STEERING CONTROLLER")

                SliderField(
                    label = "Kp (Proportional Gain)",
                    value = kp,
                    range = 0.1f..2.5f,
                    formatted = String.format("%.2f", kp),
                    onValueChange = { kp = it }
                )

                SliderField(
                    label = "Ki (Integral Gain)",
                    value = ki,
                    range = 0.0f..0.3f,
                    formatted = String.format("%.3f", ki),
                    onValueChange = { ki = it }
                )

                SliderField(
                    label = "Kd (Derivative Gain)",
                    value = kd,
                    range = 0.05f..1.5f,
                    formatted = String.format("%.2f", kd),
                    onValueChange = { kd = it }
                )

                SliderField(
                    label = "Stanley Velocity Gain (k)",
                    value = stanleyK,
                    range = 0.2f..3.0f,
                    formatted = String.format("%.2f", stanleyK),
                    onValueChange = { stanleyK = it }
                )

                SliderField(
                    label = "Max Steering Angle (±deg)",
                    value = maxSteerDeg,
                    range = 15f..60f,
                    formatted = "${maxSteerDeg.toInt()}°",
                    onValueChange = { maxSteerDeg = it }
                )

                Spacer(modifier = Modifier.height(14.dp))

                // Longitudinal / Speed Section
                SectionHeader(title = "CRUISE SPEED (ACC)")

                SliderField(
                    label = "Cruise Target Speed (km/h)",
                    value = cruiseSpeed,
                    range = 10f..60f,
                    formatted = "${cruiseSpeed.toInt()} km/h",
                    onValueChange = { cruiseSpeed = it }
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Inversion Toggles
                SectionHeader(title = "AXIS & PROTOCOL CONFIGURATION")

                RowToggle(
                    label = "Invert Steering Axis (Left/Right)",
                    checked = invertSteer,
                    onCheckedChange = { invertSteer = it }
                )

                RowToggle(
                    label = "Invert Throttle Axis",
                    checked = invertThrottle,
                    onCheckedChange = { invertThrottle = it }
                )

                RowToggle(
                    label = "SPP Serial Bridge Fallback (ESP32/Arduino)",
                    checked = useSerial,
                    onCheckedChange = { useSerial = it }
                )

                Spacer(modifier = Modifier.height(20.dp))

                // Action Buttons
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.testTag("tuning_cancel_button")
                    ) {
                        Text("Cancel", color = TextSecondary)
                    }
                    Spacer(modifier = Modifier.width(12.dp))
                    Button(
                        onClick = {
                            val updated = currentConfig.copy(
                                kp = kp,
                                ki = ki,
                                kd = kd,
                                stanleyK = stanleyK,
                                maxSteeringAngleDeg = maxSteerDeg,
                                cruiseTargetSpeedKmh = cruiseSpeed,
                                safetyFollowDistanceM = followDistance,
                                emergencyBrakeTtcSec = emergencyTtc,
                                confidenceThreshold = confidenceThresh,
                                cameraHorizonRatio = horizonRatio,
                                visionModelType = visionModel,
                                invertSteering = invertSteer,
                                invertThrottle = invertThrottle,
                                useSerialFallback = useSerial
                            )
                            onSaveConfig(updated)
                            onDismiss()
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = CyberCyan),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.testTag("tuning_save_button")
                    ) {
                        Text("Apply & Save", color = Color(0xFF00363D), fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun VisionModelSelector(
    selectedModel: VisionModelType,
    onSelect: (VisionModelType) -> Unit
) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        VisionModelType.values().forEach { model ->
            val isSelected = (model == selectedModel)
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(if (isSelected) Color(0xFF003B46) else Color(0xFF0F172A))
                    .border(
                        1.dp,
                        if (isSelected) CyberCyan else Color(0xFF334155),
                        RoundedCornerShape(8.dp)
                    )
                    .clickable { onSelect(model) }
                    .padding(10.dp)
                    .testTag("model_option_${model.name}")
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = model.displayName,
                            color = if (isSelected) CyberCyan else TextPrimary,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace
                        )
                        Text(
                            text = model.description,
                            color = TextSecondary,
                            fontSize = 10.sp
                        )
                    }
                    if (isSelected) {
                        Text(
                            text = "ACTIVE",
                            color = NeonGreen,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.ExtraBold,
                            fontFamily = FontFamily.Monospace,
                            modifier = Modifier.padding(start = 8.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SectionHeader(title: String) {
    Text(
        text = title,
        color = NeonGreen,
        fontSize = 11.sp,
        fontWeight = FontWeight.Bold,
        fontFamily = FontFamily.Monospace,
        modifier = Modifier.padding(bottom = 6.dp)
    )
}

@Composable
private fun SliderField(
    label: String,
    value: Float,
    range: ClosedFloatingPointRange<Float>,
    formatted: String,
    onValueChange: (Float) -> Unit
) {
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(text = label, color = TextPrimary, fontSize = 12.sp)
            Text(text = formatted, color = CyberCyan, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        }
        Slider(
            value = value,
            onValueChange = onValueChange,
            valueRange = range,
            colors = SliderDefaults.colors(
                thumbColor = CyberCyan,
                activeTrackColor = CyberCyan,
                inactiveTrackColor = Color(0xFF334155)
            )
        )
    }
}

@Composable
private fun RowToggle(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(text = label, color = TextPrimary, fontSize = 12.sp)
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = CyberCyan,
                checkedTrackColor = Color(0xFF004F58)
            )
        )
    }
}

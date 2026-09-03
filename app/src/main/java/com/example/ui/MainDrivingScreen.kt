package com.example.ui

import android.bluetooth.BluetoothDevice
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Assessment
import androidx.compose.material.icons.filled.Bluetooth
import androidx.compose.material.icons.filled.Keyboard
import androidx.compose.material.icons.filled.Sensors
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.MainViewModel
import com.example.model.DrivingMode
import com.example.ui.dialogs.BluetoothDeviceDialog
import com.example.ui.dialogs.DriveLogsDialog
import com.example.ui.dialogs.GamepadVisualizerDialog
import com.example.ui.dialogs.TuningDialog
import com.example.ui.hud.CameraPreviewView
import com.example.ui.hud.CollisionWarningBanner
import com.example.ui.hud.HudOverlayCanvas
import com.example.ui.hud.ManualControlPad
import com.example.ui.hud.SpeedometerCockpit
import com.example.ui.hud.ThrottleBrakeBars
import com.example.ui.hud.TopStatusBar
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
 * Main Autonomous Driving Cockpit Screen
 */
@Composable
fun MainDrivingScreen(
    viewModel: MainViewModel,
    hasCameraPermission: Boolean,
    onRequestCameraPermission: () -> Unit,
    modifier: Modifier = Modifier
) {
    val drivingMode by viewModel.drivingMode.collectAsState()
    val gear by viewModel.vehicleGear.collectAsState()
    val telemetry by viewModel.telemetry.collectAsState()
    val activeControllerState by viewModel.activeControllerState.collectAsState()
    val config by viewModel.config.collectAsState()
    val laneResult by viewModel.visionEngine.laneResult.collectAsState()
    val detectedObjects by viewModel.visionEngine.detectedObjects.collectAsState()
    val isSimulatedMode by viewModel.isSimulatedMode.collectAsState()
    val isAiActive by viewModel.isAiActive.collectAsState()
    val bluetoothState by viewModel.bluetoothHidManager.bluetoothState.collectAsState()
    val connectedDeviceName by viewModel.bluetoothHidManager.connectedDeviceName.collectAsState()
    val driveLogs by viewModel.settingsRepository.driveLogs.collectAsState()
    val typedText by viewModel.typedTextBuffer.collectAsState()
    val lastKeystrokeEvent by viewModel.lastKeystrokeEvent.collectAsState()

    // Dialog state
    val isTuningOpen by viewModel.isTuningOpen.collectAsState()
    val isBluetoothOpen by viewModel.isBluetoothOpen.collectAsState()
    val isVisualizerOpen by viewModel.isVisualizerOpen.collectAsState()
    val isLogsOpen by viewModel.isLogsOpen.collectAsState()

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Color.Black)
    ) {
        // 1. Camera Feed Layer (or Simulation Canvas)
        if (hasCameraPermission || isSimulatedMode) {
            CameraPreviewView(
                visionEngine = viewModel.visionEngine,
                isSimulatedMode = isSimulatedMode
            )
        } else {
            // Permission placeholder
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color(0xFF070B14)),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        imageVector = Icons.Default.Videocam,
                        contentDescription = "Camera Required",
                        tint = CyberCyan,
                        modifier = Modifier.size(54.dp)
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    Text(
                        text = "CAMERA ACCESS REQUIRED FOR AI VISION",
                        color = TextPrimary,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(
                        onClick = onRequestCameraPermission,
                        colors = ButtonDefaults.buttonColors(containerColor = CyberCyan),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.testTag("request_camera_permission_button")
                    ) {
                        Text("Grant Camera Permission", color = Color(0xFF00363D), fontWeight = FontWeight.Bold)
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Button(
                        onClick = { viewModel.toggleSimulatedMode() },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1E293B)),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.testTag("enable_sim_track_button")
                    ) {
                        Text("Or Run Synthetic Track Simulator", color = TextPrimary)
                    }
                }
            }
        }

        // 2. AR HUD Overlay Canvas (Driving corridors, Obstacle Boxes, Steering Arc, Trajectory)
        HudOverlayCanvas(
            laneResult = laneResult,
            detectedObjects = detectedObjects,
            telemetry = telemetry,
            config = config
        )

        // 3. Cockpit HUD UI Components Layer
        Column(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            // Top Bar: Autonomy Mode & Real-time Telemetry Stats & Bluetooth Status
            TopStatusBar(
                drivingMode = drivingMode,
                bluetoothState = bluetoothState,
                deviceName = connectedDeviceName,
                telemetry = telemetry,
                onOpenBtDialog = { viewModel.isBluetoothOpen.value = true }
            )

            // Middle Section: Gauges, Speedometer, Warning Banner, and Quick Tools
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(horizontal = 12.dp, vertical = 2.dp),
                contentAlignment = Alignment.Center
            ) {
                // Left Speedometer Cockpit
                Box(
                    modifier = Modifier.align(Alignment.CenterStart)
                ) {
                    SpeedometerCockpit(
                        speedKmh = telemetry.currentSpeedKmh,
                        targetSpeedKmh = telemetry.targetSpeedKmh,
                        gear = gear.name.take(1)
                    )
                }

                // Center Collision Warning Banner + Quick Tools Row
                Column(
                    modifier = Modifier.align(Alignment.TopCenter),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    CollisionWarningBanner(
                        telemetry = telemetry
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    CockpitToolBar(
                        isSimMode = isSimulatedMode,
                        isAiActive = isAiActive,
                        onToggleSim = { viewModel.toggleSimulatedMode() },
                        onToggleAi = { viewModel.toggleAiActive() },
                        onOpenTuning = { viewModel.isTuningOpen.value = true },
                        onOpenVisualizer = { viewModel.isVisualizerOpen.value = true },
                        onOpenLogs = { viewModel.isLogsOpen.value = true },
                        onOpenBluetooth = { viewModel.isBluetoothOpen.value = true }
                    )
                }

                // Right Side: Throttle/Brake Indicators
                Box(
                    modifier = Modifier.align(Alignment.CenterEnd)
                ) {
                    ThrottleBrakeBars(
                        throttlePct = telemetry.throttlePercent,
                        brakePct = telemetry.brakePercent
                    )
                }
            }

            // Bottom Section: Autonomy Mode Selection Bar + Touch Joystick & Pedals
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(
                        Brush.verticalGradient(
                            listOf(Color.Transparent, Color(0xEE060A14), Color(0xFF04070E))
                        )
                    )
            ) {
                // Autonomy Mode Switcher Strip
                AutonomyModeSelectorStrip(
                    currentMode = drivingMode,
                    onModeSelected = { viewModel.setDrivingMode(it) }
                )

                // Virtual Keyboard Controls
                ManualControlPad(
                    currentMode = drivingMode,
                    currentGear = gear,
                    isAiActive = isAiActive,
                    typedText = typedText,
                    onClearTypedText = { viewModel.clearTypedText() },
                    onTestSequence = { viewModel.testSendSequence("WASD") },
                    onToggleAiActive = { viewModel.toggleAiActive() },
                    onManualStateChange = { viewModel.updateManualInput(it) },
                    onGearChange = { viewModel.setVehicleGear(it) },
                    onHorn = { /* Handled in state */ },
                    onLightsToggle = { /* Handled in state */ }
                )
            }
        }

        // --- Dialogs ---
        if (isTuningOpen) {
            TuningDialog(
                currentConfig = config,
                onSaveConfig = { viewModel.saveConfig(it) },
                onDismiss = { viewModel.isTuningOpen.value = false }
            )
        }

        if (isBluetoothOpen) {
            BluetoothDeviceDialog(
                bluetoothState = bluetoothState,
                connectedDeviceName = connectedDeviceName,
                pairedDevices = viewModel.bluetoothHidManager.getPairedDevices(),
                onConnectDevice = { viewModel.connectBluetooth(it) },
                onDisconnect = { viewModel.disconnectBluetooth() },
                onRefresh = { viewModel.refreshBluetooth() },
                onDismiss = { viewModel.isBluetoothOpen.value = false }
            )
        }

        if (isVisualizerOpen) {
            GamepadVisualizerDialog(
                controllerState = activeControllerState,
                typedText = typedText,
                lastEvent = lastKeystrokeEvent,
                onTestKey = { viewModel.testSendKey(it) },
                onSendSequence = { viewModel.testSendSequence(it) },
                onClearText = { viewModel.clearTypedText() },
                onUpdateState = { viewModel.updateManualInput(it) },
                onDismiss = { viewModel.isVisualizerOpen.value = false }
            )
        }

        if (isLogsOpen) {
            DriveLogsDialog(
                logs = driveLogs,
                onClearLogs = { viewModel.clearLogs() },
                onDismiss = { viewModel.isLogsOpen.value = false }
            )
        }
    }
}

/**
 * Autonomy Mode Selector Strip (Chips for MANUAL, LANE KEEP, ACC, FULL AUTO, STOP)
 */
@Composable
private fun AutonomyModeSelectorStrip(
    currentMode: DrivingMode,
    onModeSelected: (DrivingMode) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceEvenly,
        verticalAlignment = Alignment.CenterVertically
    ) {
        DrivingMode.entries.forEach { mode ->
            val isSelected = (mode == currentMode)
            val chipColor = when (mode) {
                DrivingMode.FULL_AUTONOMOUS -> CyberCyan
                DrivingMode.LANE_KEEP -> Color(0xFF29B6F6)
                DrivingMode.ADAPTIVE_CRUISE -> Color(0xFFAB47BC)
                DrivingMode.MANUAL -> Color(0xFF9E9E9E)
            }

            Surface(
                onClick = { onModeSelected(mode) },
                shape = RoundedCornerShape(8.dp),
                color = if (isSelected) chipColor else Color(0xFF1E293B),
                border = androidx.compose.foundation.BorderStroke(
                    1.dp,
                    if (isSelected) Color.White else HudBorder
                ),
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 3.dp)
                    .height(34.dp)
                    .testTag("mode_chip_${mode.name}")
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(
                        text = mode.label.split(" ").first(),
                        color = if (isSelected) Color(0xFF002229) else TextSecondary,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.ExtraBold,
                        fontFamily = FontFamily.Monospace
                    )
                }
            }
        }
    }
}

/**
 * Cockpit Floating Tool Strip (Simulator toggle, AI Power Saver, Tuning, Gamepad inspection, Logs, Bluetooth)
 */
@Composable
private fun CockpitToolBar(
    isSimMode: Boolean,
    isAiActive: Boolean,
    onToggleSim: () -> Unit,
    onToggleAi: () -> Unit,
    onOpenTuning: () -> Unit,
    onOpenVisualizer: () -> Unit,
    onOpenLogs: () -> Unit,
    onOpenBluetooth: () -> Unit
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .background(Color(0xCC09101F), RoundedCornerShape(10.dp))
            .border(1.dp, HudBorder, RoundedCornerShape(10.dp))
            .padding(horizontal = 8.dp, vertical = 4.dp)
    ) {
        // AI Vision Battery Saver Sleep / Awaken Toggle Button
        FilledIconButton(
            onClick = onToggleAi,
            colors = IconButtonDefaults.filledIconButtonColors(
                containerColor = if (isAiActive) Color(0xCC0D2818) else Color(0xCC332008)
            ),
            modifier = Modifier
                .size(34.dp)
                .testTag("ai_power_saver_toolbar_button")
        ) {
            Icon(
                imageVector = if (isAiActive) Icons.Default.Sensors else Icons.Default.Sensors,
                contentDescription = if (isAiActive) "AI Active (Tap to Sleep)" else "AI Asleep (Tap to Wake)",
                tint = if (isAiActive) NeonGreen else WarningAmber,
                modifier = Modifier.size(16.dp)
            )
        }

        // Toggle Simulated Camera vs Hardware
        FilledIconButton(
            onClick = onToggleSim,
            colors = IconButtonDefaults.filledIconButtonColors(
                containerColor = if (isSimMode) CyberCyan else Color(0xFF1E293B)
            ),
            modifier = Modifier
                .size(34.dp)
                .testTag("sim_mode_toggle_button")
        ) {
            Icon(
                imageVector = Icons.Default.Videocam,
                contentDescription = "Simulated Track Toggle",
                tint = if (isSimMode) Color.Black else TextPrimary,
                modifier = Modifier.size(16.dp)
            )
        }

        // Bluetooth Dialog
        FilledIconButton(
            onClick = onOpenBluetooth,
            colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color(0xFF1E293B)),
            modifier = Modifier
                .size(34.dp)
                .testTag("open_bt_button")
        ) {
            Icon(
                imageVector = Icons.Default.Bluetooth,
                contentDescription = "Bluetooth Pairing",
                tint = CyberCyan,
                modifier = Modifier.size(16.dp)
            )
        }

        // Bluetooth Keyboard WASD Visualizer
        FilledIconButton(
            onClick = onOpenVisualizer,
            colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color(0xFF1E293B)),
            modifier = Modifier
                .size(34.dp)
                .testTag("open_keyboard_visualizer_button")
        ) {
            Icon(
                imageVector = Icons.Default.Keyboard,
                contentDescription = "Keyboard WASD Inspector",
                tint = NeonGreen,
                modifier = Modifier.size(16.dp)
            )
        }

        // PID & AI Tuning
        FilledIconButton(
            onClick = onOpenTuning,
            colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color(0xFF1E293B)),
            modifier = Modifier
                .size(34.dp)
                .testTag("open_tuning_button")
        ) {
            Icon(
                imageVector = Icons.Default.Tune,
                contentDescription = "Tuning",
                tint = WarningAmber,
                modifier = Modifier.size(16.dp)
            )
        }

        // Telemetry Logs
        FilledIconButton(
            onClick = onOpenLogs,
            colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color(0xFF1E293B)),
            modifier = Modifier
                .size(34.dp)
                .testTag("open_logs_button")
        ) {
            Icon(
                imageVector = Icons.Default.Assessment,
                contentDescription = "Logs",
                tint = TextPrimary,
                modifier = Modifier.size(16.dp)
            )
        }
    }
}

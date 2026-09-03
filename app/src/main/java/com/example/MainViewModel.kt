package com.example

import android.app.Application
import android.bluetooth.BluetoothDevice
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.ai.AutonomousDrivingController
import com.example.bluetooth.BluetoothHidControllerManager
import com.example.data.AutonomousSettingsRepository
import com.example.model.ControllerState
import com.example.model.DrivingLogEntry
import com.example.model.DrivingMode
import com.example.model.TelemetryData
import com.example.model.VehicleConfig
import com.example.model.VehicleGear
import com.example.vision.VisionDetectionEngine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Master ViewModel orchestrating Computer Vision, AI Autonomous Controller, and Bluetooth HID Emulation
 */
class MainViewModel(application: Application) : AndroidViewModel(application) {

    val settingsRepository = AutonomousSettingsRepository(application)
    val config: StateFlow<VehicleConfig> = settingsRepository.config

    val visionEngine = VisionDetectionEngine(config.value)
    val drivingController = AutonomousDrivingController(config.value)
    val bluetoothHidManager = BluetoothHidControllerManager(application, viewModelScope)

    // Driving State
    private val _drivingMode = MutableStateFlow(DrivingMode.MANUAL)
    val drivingMode: StateFlow<DrivingMode> = _drivingMode.asStateFlow()

    private val _vehicleGear = MutableStateFlow(VehicleGear.DRIVE)
    val vehicleGear: StateFlow<VehicleGear> = _vehicleGear.asStateFlow()

    private val _manualInput = MutableStateFlow(ControllerState())
    val manualInput: StateFlow<ControllerState> = _manualInput.asStateFlow()

    private val _activeControllerState = MutableStateFlow(ControllerState())
    val activeControllerState: StateFlow<ControllerState> = _activeControllerState.asStateFlow()

    private val _telemetry = MutableStateFlow(TelemetryData())
    val telemetry: StateFlow<TelemetryData> = _telemetry.asStateFlow()

    private val _isSimulatedMode = MutableStateFlow(false)
    val isSimulatedMode: StateFlow<Boolean> = _isSimulatedMode.asStateFlow()

    val isAiActive: StateFlow<Boolean> = visionEngine.isAiActive

    // Live On-Screen Typed Text & Keystroke Stream Buffer
    private val _typedTextBuffer = MutableStateFlow("W A S D")
    val typedTextBuffer: StateFlow<String> = _typedTextBuffer.asStateFlow()

    private val _lastKeystrokeEvent = MutableStateFlow("Keyboard Ready")
    val lastKeystrokeEvent: StateFlow<String> = _lastKeystrokeEvent.asStateFlow()

    // Dialog state
    val isTuningOpen = MutableStateFlow(false)
    val isBluetoothOpen = MutableStateFlow(false)
    val isVisualizerOpen = MutableStateFlow(false)
    val isLogsOpen = MutableStateFlow(false)

    init {
        // Observe config changes
        viewModelScope.launch {
            config.collect { newConfig ->
                visionEngine.updateConfig(newConfig)
                drivingController.config = newConfig
            }
        }

        // Run master 50Hz Real-Time Autonomous Drive Loop
        startAutonomousLoop()
    }

    private fun startAutonomousLoop() {
        viewModelScope.launch(Dispatchers.Default) {
            var logCounter = 0
            while (isActive) {
                try {
                    val mode = _drivingMode.value
                    val manual = _manualInput.value
                    val gear = _vehicleGear.value
                    val lane = visionEngine.laneResult.value
                    val obstacles = visionEngine.detectedObjects.value

                    // If simulated mode active, step simulation
                    if (_isSimulatedMode.value) {
                        visionEngine.runSimulationInference()
                    }

                    // Compute next control actions & telemetry
                    val (ctrlState, telem) = drivingController.computeControlCycle(
                        mode = mode,
                        manualInput = manual,
                        gear = gear,
                        laneResult = lane,
                        obstacles = obstacles
                    )

                    _activeControllerState.value = ctrlState

                    val fullTelemetry = telem.copy(
                        fps = visionEngine.fps.value,
                        aiInferenceMs = visionEngine.inferenceLatencyMs.value,
                        btTransmitHz = bluetoothHidManager.transmitRateHz.value,
                        btPingMs = bluetoothHidManager.latencyPingMs.value,
                        isSimulatedCamera = _isSimulatedMode.value
                    )
                    _telemetry.value = fullTelemetry

                    // Dispatch to Bluetooth HID Gamepad Transceiver
                    bluetoothHidManager.updateControllerState(ctrlState)

                    // Periodic telemetry logging (every ~1 sec)
                    logCounter++
                    if (logCounter >= 50) {
                        logCounter = 0
                        if (mode != DrivingMode.MANUAL || telem.currentSpeedKmh > 2f) {
                            settingsRepository.addLog(
                                DrivingLogEntry(
                                    mode = mode,
                                    speedKmh = telem.currentSpeedKmh,
                                    steeringDeg = telem.steeringAngleDeg,
                                    throttlePct = telem.throttlePercent,
                                    brakePct = telem.brakePercent,
                                    obstaclesCount = obstacles.size
                                )
                            )
                        }
                    }
                } catch (e: Throwable) {
                    android.util.Log.e("MainViewModel", "Error in autonomous driving loop cycle", e)
                }

                delay(20) // 50Hz control loop
            }
        }
    }

    fun setDrivingMode(mode: DrivingMode) {
        _drivingMode.value = mode
        if (mode == DrivingMode.FULL_AUTONOMOUS || mode == DrivingMode.LANE_KEEP || mode == DrivingMode.ADAPTIVE_CRUISE) {
            // Auto-awaken AI Vision if entering autonomous modes
            visionEngine.setAiActive(true)
            drivingController.resetPid()
        }
    }

    fun toggleAiActive() {
        visionEngine.setAiActive(!visionEngine.isAiActive.value)
    }

    fun setAiActive(active: Boolean) {
        visionEngine.setAiActive(active)
    }

    fun setVehicleGear(gear: VehicleGear) {
        _vehicleGear.value = gear
    }

    fun updateManualInput(state: ControllerState) {
        val prev = _manualInput.value
        _manualInput.value = state

        // Record on-screen text when a key transition occurs
        if (state.keyW && !prev.keyW) recordKeyStroke("W")
        if (state.keyA && !prev.keyA) recordKeyStroke("A")
        if (state.keyS && !prev.keyS) recordKeyStroke("S")
        if (state.keyD && !prev.keyD) recordKeyStroke("D")
        if (state.keySpace && !prev.keySpace) recordKeyStroke("␣")
    }

    fun recordKeyStroke(keyName: String) {
        val current = _typedTextBuffer.value
        val updated = if (current.isEmpty()) keyName else "$current $keyName"
        // Keep last 30 characters for clean on-screen scrolling display
        _typedTextBuffer.value = if (updated.length > 40) updated.takeLast(35) else updated
        _lastKeystrokeEvent.value = "KEY: [$keyName] -> USB HID Broadcast"
    }

    fun clearTypedText() {
        _typedTextBuffer.value = ""
        _lastKeystrokeEvent.value = "Buffer Cleared"
    }

    fun testSendKey(keyChar: String) {
        viewModelScope.launch {
            when (keyChar.uppercase()) {
                "W" -> {
                    updateManualInput(ControllerState(keyW = true, throttle = 1.0f))
                    recordKeyStroke("W")
                    delay(150)
                    updateManualInput(ControllerState())
                }
                "A" -> {
                    updateManualInput(ControllerState(keyA = true, steering = -1.0f))
                    recordKeyStroke("A")
                    delay(150)
                    updateManualInput(ControllerState())
                }
                "S" -> {
                    updateManualInput(ControllerState(keyS = true, brake = 1.0f))
                    recordKeyStroke("S")
                    delay(150)
                    updateManualInput(ControllerState())
                }
                "D" -> {
                    updateManualInput(ControllerState(keyD = true, steering = 1.0f))
                    recordKeyStroke("D")
                    delay(150)
                    updateManualInput(ControllerState())
                }
                "SPACE" -> {
                    updateManualInput(ControllerState(keySpace = true))
                    recordKeyStroke("␣")
                    delay(150)
                    updateManualInput(ControllerState())
                }
            }
        }
    }

    fun testSendSequence(seq: String = "WASD") {
        viewModelScope.launch {
            for (ch in seq) {
                testSendKey(ch.toString())
                delay(200)
            }
        }
    }

    fun toggleSimulatedMode() {
        val next = !_isSimulatedMode.value
        _isSimulatedMode.value = next
        visionEngine.isSimulatedMode = next
    }

    fun saveConfig(newConfig: VehicleConfig) {
        settingsRepository.updateConfig(newConfig)
    }

    fun connectBluetooth(device: BluetoothDevice) {
        bluetoothHidManager.connectToDevice(device)
    }

    fun disconnectBluetooth() {
        bluetoothHidManager.disconnect()
    }

    fun refreshBluetooth() {
        bluetoothHidManager.initializeProfile()
    }

    fun clearLogs() {
        settingsRepository.clearLogs()
    }

    override fun onCleared() {
        super.onCleared()
        bluetoothHidManager.cleanup()
    }
}

package com.example.data

import android.content.Context
import android.content.SharedPreferences
import com.example.model.DrivingLogEntry
import com.example.model.DrivingMode
import com.example.model.VehicleConfig
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Settings and driving logs repository
 */
class AutonomousSettingsRepository(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences("autodrive_prefs", Context.MODE_PRIVATE)

    private val _config = MutableStateFlow(loadConfig())
    val config: StateFlow<VehicleConfig> = _config.asStateFlow()

    private val _driveLogs = MutableStateFlow<List<DrivingLogEntry>>(emptyList())
    val driveLogs: StateFlow<List<DrivingLogEntry>> = _driveLogs.asStateFlow()

    fun updateConfig(newConfig: VehicleConfig) {
        _config.value = newConfig
        saveConfig(newConfig)
    }

    fun addLog(entry: DrivingLogEntry) {
        val current = _driveLogs.value.toMutableList()
        current.add(0, entry)
        if (current.size > 50) current.removeAt(current.lastIndex)
        _driveLogs.value = current
    }

    fun clearLogs() {
        _driveLogs.value = emptyList()
    }

    private fun loadConfig(): VehicleConfig {
        return VehicleConfig(
            kp = prefs.getFloat("kp", 0.75f),
            ki = prefs.getFloat("ki", 0.05f),
            kd = prefs.getFloat("kd", 0.35f),
            stanleyK = prefs.getFloat("stanleyK", 1.2f),
            lookaheadDistanceMeters = prefs.getFloat("lookahead", 4.5f),
            maxSteeringAngleDeg = prefs.getFloat("maxSteer", 35f),
            maxSpeedKmh = prefs.getFloat("maxSpeed", 45f),
            cruiseTargetSpeedKmh = prefs.getFloat("cruiseSpeed", 25f),
            safetyFollowDistanceM = prefs.getFloat("safetyDist", 3.5f),
            emergencyBrakeTtcSec = prefs.getFloat("emergencyTtc", 1.2f),
            invertSteering = prefs.getBoolean("invertSteer", false),
            invertThrottle = prefs.getBoolean("invertThrottle", false),
            steeringDeadband = prefs.getFloat("deadband", 0.03f),
            steeringTrimOffset = prefs.getFloat("steeringTrim", 0.0f),
            confidenceThreshold = prefs.getFloat("confThreshold", 0.50f),
            cameraHorizonRatio = prefs.getFloat("horizonRatio", 0.45f),
            laneSensitivity = prefs.getFloat("laneSens", 0.70f),
            visionModelType = try {
                com.example.model.VisionModelType.valueOf(prefs.getString("visionModel", com.example.model.VisionModelType.GOOGLE_MLKIT.name) ?: com.example.model.VisionModelType.GOOGLE_MLKIT.name)
            } catch (e: Exception) {
                com.example.model.VisionModelType.GOOGLE_MLKIT
            },
            useSerialFallback = prefs.getBoolean("useSerial", false)
        )
    }

    private fun saveConfig(cfg: VehicleConfig) {
        prefs.edit()
            .putFloat("kp", cfg.kp)
            .putFloat("ki", cfg.ki)
            .putFloat("kd", cfg.kd)
            .putFloat("stanleyK", cfg.stanleyK)
            .putFloat("lookahead", cfg.lookaheadDistanceMeters)
            .putFloat("maxSteer", cfg.maxSteeringAngleDeg)
            .putFloat("maxSpeed", cfg.maxSpeedKmh)
            .putFloat("cruiseSpeed", cfg.cruiseTargetSpeedKmh)
            .putFloat("safetyDist", cfg.safetyFollowDistanceM)
            .putFloat("emergencyTtc", cfg.emergencyBrakeTtcSec)
            .putBoolean("invertSteer", cfg.invertSteering)
            .putBoolean("invertThrottle", cfg.invertThrottle)
            .putFloat("deadband", cfg.steeringDeadband)
            .putFloat("steeringTrim", cfg.steeringTrimOffset)
            .putFloat("confThreshold", cfg.confidenceThreshold)
            .putFloat("horizonRatio", cfg.cameraHorizonRatio)
            .putFloat("laneSens", cfg.laneSensitivity)
            .putString("visionModel", cfg.visionModelType.name)
            .putBoolean("useSerial", cfg.useSerialFallback)
            .apply()
    }
}

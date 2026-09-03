package com.example.ai

import com.example.model.ControllerState
import com.example.model.DetectedObject
import com.example.model.DrivingMode
import com.example.model.LaneDetectionResult
import com.example.model.TelemetryData
import com.example.model.VehicleConfig
import com.example.model.VehicleGear
import com.example.model.VisionModelType
import kotlin.math.abs
import kotlin.math.atan
import kotlin.math.max
import kotlin.math.min

/**
 * Autonomous Driving Control System
 * Implements Stanley Steering Control, PID Lane Centering, Adaptive Cruise (ACC), and AEB
 */
class AutonomousDrivingController(
    var config: VehicleConfig = VehicleConfig()
) {
    private var prevLateralError = 0f
    private var integralError = 0f
    private var lastUpdateTime = System.currentTimeMillis()

    // Smooth virtual vehicle state
    private var simulatedSpeedKmh = 0f
    private var currentSteering = 0f
    private var currentThrottle = 0f
    private var currentBrake = 0f
    private var pwmElapsedMs = 0f

    /**
     * Compute next controller action and telemetry given vision inputs and driving mode
     */
    fun computeControlCycle(
        mode: DrivingMode,
        manualInput: ControllerState,
        gear: VehicleGear,
        laneResult: LaneDetectionResult,
        obstacles: List<DetectedObject>
    ): Pair<ControllerState, TelemetryData> {
        val now = System.currentTimeMillis()
        val dt = ((now - lastUpdateTime) / 1000.0f).coerceIn(0.01f, 0.1f)
        lastUpdateTime = now

        // Check if lane only mode (bypasses obstacle braking)
        val isLaneOnly = (config.visionModelType == VisionModelType.LANE_ONLY)

        // Find critical lead obstacle directly in vehicle's forward travel corridor
        val validObstacles = if (isLaneOnly) emptyList() else obstacles
        val leadObstacle = validObstacles
            .filter { abs(((it.left + it.right) / 2.0f) - 0.50f) < 0.25f }
            .minByOrNull { it.distanceMeters }

        val directThreat = validObstacles.firstOrNull { it.isCollisionThreat }
        val minTtc = directThreat?.timeToCollisionSec ?: (leadObstacle?.timeToCollisionSec ?: Float.MAX_VALUE)

        // AEB only triggers for confirmed direct collision threat or imminent impact (< 1.2m)
        val isAebTriggered = !isLaneOnly && (directThreat != null || (leadObstacle != null && leadObstacle.distanceMeters < 1.2f && leadObstacle.isCollisionThreat))

        // 1. Calculate Autonomous Steering (Stanley + PID)
        val autoSteering = calculateStanleyPidSteering(laneResult, dt)

        // 2. Calculate Autonomous Throttle & Braking (ACC + AEB)
        val (autoThrottle, autoBrake) = calculateLongitudinalControl(leadObstacle, isAebTriggered, dt)

        // 3. Resolve final outputs based on DrivingMode
        var finalSteering: Float
        var finalThrottle: Float
        var finalBrake: Float
        var emergencyActive = false

        when (mode) {
            DrivingMode.FULL_AUTONOMOUS -> {
                if (isAebTriggered) {
                    finalSteering = autoSteering
                    finalThrottle = 0f
                    finalBrake = 1.0f
                    emergencyActive = true
                } else {
                    finalSteering = autoSteering
                    // Curve Speed Deceleration: lift off throttle into sharp curves to weight front steering tires
                    finalThrottle = if (abs(finalSteering) > config.curveSpeedDecelThreshold) 0f else autoThrottle
                    finalBrake = autoBrake
                }
            }
            DrivingMode.LANE_KEEP -> {
                // Autonomous steering lane centering with direct user throttle/brake
                finalSteering = autoSteering
                finalThrottle = manualInput.throttle
                finalBrake = manualInput.brake
                emergencyActive = false
            }
            DrivingMode.ADAPTIVE_CRUISE -> {
                finalSteering = manualInput.steering
                if (isAebTriggered) {
                    finalThrottle = 0f
                    finalBrake = 1.0f
                    emergencyActive = true
                } else {
                    finalThrottle = autoThrottle
                    finalBrake = autoBrake
                    emergencyActive = false
                }
            }
            DrivingMode.MANUAL -> {
                // 100% Direct Driver Control: No AI braking or throttle override
                finalSteering = manualInput.steering
                finalThrottle = manualInput.throttle
                finalBrake = manualInput.brake
                emergencyActive = false
            }
        }

        // Apply deadband, trim offset, and axis inversion
        var processedSteering = finalSteering + config.steeringTrimOffset
        if (abs(processedSteering) < config.steeringDeadband) {
            processedSteering = 0f
        }
        if (config.invertSteering) {
            processedSteering = -processedSteering
        }
        processedSteering = processedSteering.coerceIn(-1.0f, 1.0f)

        var processedThrottle = finalThrottle
        if (config.invertThrottle) {
            processedThrottle = -processedThrottle
        }
        processedThrottle = processedThrottle.coerceIn(0f, 1f)

        val processedBrake = finalBrake.coerceIn(0f, 1f)

        // Update simulated vehicle dynamics
        updateSimulatedVehicleSpeed(processedThrottle, processedBrake, dt)

        // 80ms Time-Sliced PWM WASD Key Generator (Comma AI / openpilot micro-pulsing)
        pwmElapsedMs = (pwmElapsedMs + dt * 1000f) % 80f
        val tPhase = pwmElapsedMs

        // Steer PWM: On-time proportional to steering angle magnitude
        val steerMag = abs(processedSteering)
        val steerOnTimeMs = if (steerMag > 0.03f) steerMag * 80f else 0f
        val isSteerPulseActive = tPhase < steerOnTimeMs

        // Throttle PWM: On-time proportional to throttle demand
        val throttleOnTimeMs = if (processedThrottle > 0.05f) processedThrottle * 80f else 0f
        val isThrottlePulseActive = (tPhase < throttleOnTimeMs) && (processedBrake < 0.15f)

        // Brake PWM: On-time proportional to brake demand
        val brakeOnTimeMs = if (processedBrake > 0.08f) processedBrake * 80f else 0f
        var isBrakePulseActive = tPhase < brakeOnTimeMs
        // Reverse Lockout: Drop S if vehicle is stopped to prevent accidental reverse
        if (simulatedSpeedKmh < 1.0f && !emergencyActive && (gear != VehicleGear.REVERSE)) {
            isBrakePulseActive = false
        }

        val isKeyW = when (mode) {
            DrivingMode.MANUAL -> manualInput.keyW || manualInput.throttle > 0.1f
            else -> isThrottlePulseActive && !emergencyActive
        }

        val isKeyA = when (mode) {
            DrivingMode.MANUAL -> manualInput.keyA || manualInput.steering < -0.15f
            DrivingMode.ADAPTIVE_CRUISE -> manualInput.keyA || manualInput.steering < -0.15f
            else -> isSteerPulseActive && (processedSteering < -0.03f)
        }

        val isKeyD = when (mode) {
            DrivingMode.MANUAL -> manualInput.keyD || manualInput.steering > 0.15f
            DrivingMode.ADAPTIVE_CRUISE -> manualInput.keyD || manualInput.steering > 0.15f
            else -> isSteerPulseActive && (processedSteering > 0.03f)
        }

        val isKeyS = when (mode) {
            DrivingMode.MANUAL -> manualInput.keyS || manualInput.brake > 0.1f
            DrivingMode.LANE_KEEP -> manualInput.keyS || manualInput.brake > 0.1f
            else -> isBrakePulseActive || emergencyActive
        }

        val isKeySpace = when (mode) {
            DrivingMode.MANUAL -> manualInput.keySpace
            else -> emergencyActive || manualInput.keySpace
        }

        val outputControllerState = ControllerState(
            keyW = isKeyW,
            keyA = isKeyA,
            keyS = isKeyS,
            keyD = isKeyD,
            keySpace = isKeySpace,
            steering = processedSteering,
            throttle = processedThrottle,
            brake = processedBrake,
            reverse = (gear == VehicleGear.REVERSE)
        )

        val steeringAngleDeg = processedSteering * config.maxSteeringAngleDeg
        val telemetry = TelemetryData(
            currentSpeedKmh = simulatedSpeedKmh,
            targetSpeedKmh = config.cruiseTargetSpeedKmh,
            steeringAngleDeg = steeringAngleDeg,
            lateralOffsetCm = laneResult.lateralOffsetMeters * 100f,
            throttlePercent = (processedThrottle * 100).toInt(),
            brakePercent = (processedBrake * 100).toInt(),
            gear = gear,
            minTimeToCollisionSec = minTtc,
            collisionWarning = (minTtc < 2.5f && leadObstacle != null && !isLaneOnly),
            emergencyBrakingActive = emergencyActive,
            detectedObstaclesCount = validObstacles.size,
            activeVisionModel = config.visionModelType,
            leadObstacleDistanceM = leadObstacle?.distanceMeters ?: Float.MAX_VALUE,
            isPathClear = !isAebTriggered && (leadObstacle == null || leadObstacle.distanceMeters > config.safetyFollowDistanceM * 1.5f)
        )

        return Pair(outputControllerState, telemetry)
    }

    /**
     * Stanley Steering + PID Cross-Track Error + Curvature Feedforward Controller
     */
     private fun calculateStanleyPidSteering(lane: LaneDetectionResult, dt: Float): Float {
        val eLat = lane.lateralOffsetMeters // in meters (- left, + right)
        val thetaHeadingRad = Math.toRadians(lane.headingAngleDeg.toDouble()).toFloat()

        // PID component
        val p = config.kp * eLat
        integralError = (integralError + eLat * dt).coerceIn(-1.5f, 1.5f)
        val i = config.ki * integralError
        val derivative = if (dt > 0.001f) (eLat - prevLateralError) / dt else 0f
        prevLateralError = eLat
        val d = config.kd * derivative

        val pidCorrection = p + i + d

        // Stanley cross-track component: delta_stanley = atan(k * e_lat / (v + 1))
        val currentSpeedMs = max(simulatedSpeedKmh / 3.6f, 1.0f)
        val stanleyOffset = atan((config.stanleyK * eLat) / currentSpeedMs)

        // Comma AI Curvature Feedforward: delta_ff = atan(wheelbase * kappa)
        val kappa = if (lane.curvatureRadiusM > 10f) 1.0f / lane.curvatureRadiusM else 0f
        val curveDirectionSign = if (lane.headingAngleDeg < -2f) -1.0f else (if (lane.headingAngleDeg > 2f) 1.0f else 0.0f)
        val deltaFeedforward = atan(2.7f * kappa * curveDirectionSign) * 0.40f

        val combinedAngleRad = (thetaHeadingRad * 0.35f) + (stanleyOffset * 0.35f) + (pidCorrection * 0.20f) + deltaFeedforward
        val maxAngleRad = Math.toRadians(config.maxSteeringAngleDeg.toDouble()).toFloat()

        // Normalize to -1.0 .. +1.0 and blend Artificial Potential Field barrier repulsion
        val normSteer = (combinedAngleRad / maxAngleRad).coerceIn(-1.0f, 1.0f)
        val finalSteer = (normSteer + lane.barrierRepulsionSteer).coerceIn(-1.0f, 1.0f)
        return finalSteer
    }

    /**
     * Adaptive Cruise Control (ACC) & Speed Target Planner
     * Accel smoothly when clear, smoothly decelerates if approaching lead vehicle
     */
    private fun calculateLongitudinalControl(
        leadObstacle: DetectedObject?,
        isAeb: Boolean,
        dt: Float
    ): Pair<Float, Float> {
        if (isAeb) {
            return Pair(0f, 1.0f)
        }

        var targetSpeed = config.cruiseTargetSpeedKmh

        // If obstacle ahead in corridor, adjust speed to maintain safety gap
        if (leadObstacle != null) {
            val dist = leadObstacle.distanceMeters
            val safetyGap = config.safetyFollowDistanceM
            if (dist < safetyGap) {
                // Inside safety buffer: Apply proportional brake
                val brakeIntensity = ((safetyGap - dist) / safetyGap).coerceIn(0.25f, 0.85f)
                return Pair(0f, brakeIntensity)
            } else if (dist < safetyGap * 1.8f) {
                // Approaching safety gap: Smoothly scale down target cruise speed
                val factor = ((dist - safetyGap) / (safetyGap * 0.8f)).coerceIn(0.2f, 1.0f)
                targetSpeed = config.cruiseTargetSpeedKmh * factor
            }
        }

        // Proportional throttle / cruise controller
        val speedError = targetSpeed - simulatedSpeedKmh
        return if (speedError > 0) {
            val throttle = (speedError / 10.0f).coerceIn(0.25f, 0.90f)
            Pair(throttle, 0f)
        } else {
            val brake = (abs(speedError) / 10.0f).coerceIn(0.05f, 0.4f)
            Pair(0f, brake)
        }
    }

    private fun updateSimulatedVehicleSpeed(throttle: Float, brake: Float, dt: Float) {
        val accel = (throttle * 8.0f) - (brake * 18.0f) - (simulatedSpeedKmh * 0.05f) // aerodynamic drag
        simulatedSpeedKmh = (simulatedSpeedKmh + accel * dt * 3.6f).coerceIn(0f, config.maxSpeedKmh)
    }

    fun resetPid() {
        integralError = 0f
        prevLateralError = 0f
    }
}

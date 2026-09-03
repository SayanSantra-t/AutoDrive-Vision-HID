package com.example.model

/**
 * Autonomy Driving Modes
 */
enum class DrivingMode(val label: String, val shortDesc: String) {
    MANUAL("MANUAL", "Direct user touch/keyboard control with AI safety monitor"),
    LANE_KEEP("LANE KEEP (ALC)", "Autonomous steering lane centering with manual throttle"),
    ADAPTIVE_CRUISE("CRUISE (ACC)", "Autonomous throttle/brake speed & distance with manual steering"),
    FULL_AUTONOMOUS("FULL AUTO", "Autonomous steering, throttle, braking and obstacle avoidance")
}

/**
 * Gear state
 */
enum class VehicleGear {
    PARK, REVERSE, NEUTRAL, DRIVE, SPORT
}

/**
 * Supported On-Device AI Vision & Object Detection Engine Types
 */
enum class VisionModelType(val displayName: String, val shortLabel: String, val description: String) {
    GOOGLE_MLKIT("Google ML Kit (MobileNet-SSD)", "Google ML Kit", "Google's real-time on-device neural object detection & tracking engine"),
    YOLO_SPATIAL("YOLO Spatial Neural Grid", "YOLO Grid", "Fast multi-scale spatial confidence grid with IoU NMS & ground-plane filtering"),
    LANE_ONLY("Lane Tracking Only (Bypass AEB)", "Lane Only", "Autonomous lane centering only without obstacle emergency braking")
}

/**
 * Obstacle object types detected by on-device Vision/YOLO engine
 */
enum class ObjectClass(val label: String, val colorHex: Long) {
    VEHICLE("Vehicle", 0xFF00E5FF),
    PEDESTRIAN("Pedestrian", 0xFFFF5252),
    BICYCLE("Cyclist", 0xFFFFD700),
    TRAFFIC_LIGHT_RED("Red Light", 0xFFFF1744),
    TRAFFIC_LIGHT_GREEN("Green Light", 0xFF00E676),
    STOP_SIGN("Stop Sign", 0xFFFF1744),
    OBSTACLE("Obstacle", 0xFFFF9100),
    ROAD_CONE("Pylon / Cone", 0xFFFFAB00),
    SPEED_SIGN("Speed Sign", 0xFF40C4FF)
}

/**
 * Detected object with 2D/3D normalized bounding box, confidence, and distance in meters
 */
data class DetectedObject(
    val id: Int,
    val objectClass: ObjectClass,
    val confidence: Float,
    val left: Float,   // 0.0 to 1.0 (normalized screen coords)
    val top: Float,    // 0.0 to 1.0
    val right: Float,  // 0.0 to 1.0
    val bottom: Float, // 0.0 to 1.0
    val distanceMeters: Float, // Estimated distance
    val timeToCollisionSec: Float = Float.MAX_VALUE, // TTC in seconds
    val isCollisionThreat: Boolean = false
)

/**
 * Lane detection result with polynomial boundary curves and center offset
 */
data class LaneDetectionResult(
    val hasLeftLane: Boolean = true,
    val hasRightLane: Boolean = true,
    val leftLanePoints: List<Pair<Float, Float>> = emptyList(),   // Normalized (x,y)
    val rightLanePoints: List<Pair<Float, Float>> = emptyList(),
    val centerTrajectory: List<Pair<Float, Float>> = emptyList(),
    val lateralOffsetMeters: Float = 0f, // Distance from lane center (- left, + right)
    val headingAngleDeg: Float = 0f,     // Angle of road relative to car heading
    val curvatureRadiusM: Float = 500f,  // Curvature radius in meters
    val confidence: Float = 0.9f,
    val leftBarrierDistanceM: Float = 3.5f,
    val rightBarrierDistanceM: Float = 3.5f,
    val barrierRepulsionSteer: Float = 0f,
    val isRoadDepartureThreat: Boolean = false
)

/**
 * Keyboard / WASD Controller Command State
 * Maps directly to Bluetooth HID Keyboard output:
 * - W: Accelerate / Throttle
 * - A: Steer Left
 * - S: Brake / Reverse
 * - D: Steer Right
 * - Space: Handbrake / Emergency Brake
 */
data class ControllerState(
    val keyW: Boolean = false,      // Accelerate / Throttle (USB HID: 0x1A)
    val keyA: Boolean = false,      // Steer Left (USB HID: 0x04)
    val keyS: Boolean = false,      // Brake / Reverse (USB HID: 0x16)
    val keyD: Boolean = false,      // Steer Right (USB HID: 0x07)
    val keySpace: Boolean = false,  // Handbrake (USB HID: 0x2C)
    // Continuous values for HUD telemetry and smooth AI estimation
    val steering: Float = 0f,       // -1.0 (Left) to +1.0 (Right)
    val throttle: Float = 0f,       // 0.0 to 1.0
    val brake: Float = 0f,          // 0.0 to 1.0
    val reverse: Boolean = false
) {
    /**
     * Check if 'W' (Accelerate) is active either via discrete key or analog threshold
     */
    val isAccelerating: Boolean get() = keyW || throttle > 0.1f

    /**
     * Check if 'S' (Brake/Reverse) is active
     */
    val isBraking: Boolean get() = keyS || brake > 0.1f

    /**
     * Check if 'A' (Steer Left) is active
     */
    val isSteeringLeft: Boolean get() = keyA || steering < -0.15f

    /**
     * Check if 'D' (Steer Right) is active
     */
    val isSteeringRight: Boolean get() = keyD || steering > 0.15f

    /**
     * Check if 'Space' (Handbrake) is active
     */
    val isHandbrake: Boolean get() = keySpace
}

/**
 * Live vehicle and AI vision telemetry
 */
data class TelemetryData(
    val currentSpeedKmh: Float = 0f,
    val targetSpeedKmh: Float = 30f,
    val steeringAngleDeg: Float = 0f, // -45 to +45 degrees
    val lateralOffsetCm: Float = 0f,  // Cross track error
    val throttlePercent: Int = 0,     // 0 - 100
    val brakePercent: Int = 0,        // 0 - 100
    val gear: VehicleGear = VehicleGear.PARK,
    val minTimeToCollisionSec: Float = Float.MAX_VALUE,
    val collisionWarning: Boolean = false,
    val emergencyBrakingActive: Boolean = false,
    val fps: Int = 30,
    val aiInferenceMs: Long = 12,
    val btTransmitHz: Int = 50,
    val btPingMs: Int = 4,
    val detectedObstaclesCount: Int = 0,
    val activeVisionModel: VisionModelType = VisionModelType.GOOGLE_MLKIT,
    val leadObstacleDistanceM: Float = Float.MAX_VALUE,
    val isPathClear: Boolean = true,
    val isNightModeVision: Boolean = false,
    val isSimulatedCamera: Boolean = false
)

/**
 * Bluetooth Connection State
 */
enum class BluetoothState(val label: String) {
    UNAVAILABLE("Bluetooth Unavailable"),
    DISABLED("Bluetooth Disabled"),
    DISCONNECTED("Disconnected (Ready)"),
    ADVERTISING("Advertising HID Keyboard (WASD)..."),
    CONNECTING("Connecting to Host..."),
    CONNECTED("Connected (HID Keyboard)"),
    ERROR("Connection Error")
}

/**
 * Controller configuration and PID tuning parameters
 */
data class VehicleConfig(
    // PID Steering Controller Gains
    val kp: Float = 0.75f,       // Proportional gain
    val ki: Float = 0.05f,       // Integral gain
    val kd: Float = 0.35f,       // Derivative gain
    val stanleyK: Float = 1.2f,  // Stanley lookahead velocity gain
    val lookaheadDistanceMeters: Float = 4.5f,
    
    // Limits
    val maxSteeringAngleDeg: Float = 35f,
    val maxSpeedKmh: Float = 45f,
    val cruiseTargetSpeedKmh: Float = 25f,
    val safetyFollowDistanceM: Float = 2.2f,
    val emergencyBrakeTtcSec: Float = 0.9f,

    // Inversions & Offsets
    val invertSteering: Boolean = false,
    val invertThrottle: Boolean = false,
    val steeringDeadband: Float = 0.03f,
    val steeringTrimOffset: Float = 0.0f,
    
    // AI Vision Settings
    val confidenceThreshold: Float = 0.50f,
    val cameraHorizonRatio: Float = 0.45f, // 0.45 = horizon at 45% from top
    val windshieldHoodCutoffRatio: Float = 0.68f, // Clamps scan below 68% height to exclude car hood/wipers when windshield-mounted
    val minLaneWidthM: Float = 2.2f, // Reject narrow shoulders/gutters (< 2.2m)
    val maxLaneWidthM: Float = 4.5f,
    val safeBarrierStandoffM: Float = 2.2f, // APF virtual safety standoff from walls/barriers
    val barrierRepulsionGain: Float = 0.38f,
    val curveSpeedDecelThreshold: Float = 0.28f, // Lift off throttle during sharp steering
    val laneSensitivity: Float = 0.70f,
    val visionModelType: VisionModelType = VisionModelType.GOOGLE_MLKIT,
    val useSerialFallback: Boolean = false,
    val serialBaudRate: Int = 115200
)

/**
 * Log entry for driving recorder
 */
data class DrivingLogEntry(
    val timestamp: Long = System.currentTimeMillis(),
    val mode: DrivingMode,
    val speedKmh: Float,
    val steeringDeg: Float,
    val throttlePct: Int,
    val brakePct: Int,
    val obstaclesCount: Int,
    val note: String = ""
)

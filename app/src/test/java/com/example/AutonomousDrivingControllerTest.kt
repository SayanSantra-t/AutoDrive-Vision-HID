package com.example

import com.example.ai.AutonomousDrivingController
import com.example.model.ControllerState
import com.example.model.DrivingMode
import com.example.model.LaneDetectionResult
import com.example.model.VehicleConfig
import com.example.model.VehicleGear
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

class AutonomousDrivingControllerTest {

    @Test
    fun testLaneCenteringStraight() {
        val controller = AutonomousDrivingController()
        val lane = LaneDetectionResult(
            hasLeftLane = true,
            hasRightLane = true,
            lateralOffsetMeters = 0.0f,
            headingAngleDeg = 0.0f,
            curvatureRadiusM = 500f,
            barrierRepulsionSteer = 0f
        )
        val (state, telemetry) = controller.computeControlCycle(
            mode = DrivingMode.FULL_AUTONOMOUS,
            manualInput = ControllerState(),
            gear = VehicleGear.DRIVE,
            laneResult = lane,
            obstacles = emptyList()
        )

        assertTrue(Steering should be near 0 on center, abs(state.steering) < 0.05f)
        assertTrue(Throttle should be active, state.throttle > 0.05f)
        assertEquals(Brake should be 0, 0f, state.brake, 0.01f)
    }

    @Test
    fun testApfBarrierRepulsionLeft() {
        val controller = AutonomousDrivingController()
        val lane = LaneDetectionResult(
            hasLeftLane = true,
            hasRightLane = true,
            lateralOffsetMeters = 0.0f,
            headingAngleDeg = 0.0f,
            barrierRepulsionSteer = -0.25f
        )
        val (state, _) = controller.computeControlCycle(
            mode = DrivingMode.FULL_AUTONOMOUS,
            manualInput = ControllerState(),
            gear = VehicleGear.DRIVE,
            laneResult = lane,
            obstacles = emptyList()
        )

        assertTrue(Steering should be leftward away from right barrier, state.steering < -0.15f)
    }

    @Test
    fun testCurveSpeedDeceleration() {
        val config = VehicleConfig(curveSpeedDecelThreshold = 0.25f)
        val controller = AutonomousDrivingController(config = config)

        val lane = LaneDetectionResult(
            hasLeftLane = true,
            hasRightLane = true,
            lateralOffsetMeters = 1.2f,
            headingAngleDeg = 25.0f,
            barrierRepulsionSteer = 0f
        )
        val (state, _) = controller.computeControlCycle(
            mode = DrivingMode.FULL_AUTONOMOUS,
            manualInput = ControllerState(),
            gear = VehicleGear.DRIVE,
            laneResult = lane,
            obstacles = emptyList()
        )

        assertTrue(Steering exceeds threshold, abs(state.steering) > 0.25f)
        assertEquals(Throttle should be 0 during sharp turn, 0f, state.throttle, 0.01f)
    }

    @Test
    fun testRoadDepartureMitigationActiveRecovery() {
        val controller = AutonomousDrivingController()
        val lane = LaneDetectionResult(
            hasLeftLane = false,
            hasRightLane = true,
            lateralOffsetMeters = -1.8f,
            headingAngleDeg = -10.0f,
            isRoadDepartureThreat = true
        )
        val (state, _) = controller.computeControlCycle(
            mode = DrivingMode.FULL_AUTONOMOUS,
            manualInput = ControllerState(),
            gear = VehicleGear.DRIVE,
            laneResult = lane,
            obstacles = emptyList()
        )

        assertTrue(RDM must command strong left steering, state.steering < -0.30f)
    }
}

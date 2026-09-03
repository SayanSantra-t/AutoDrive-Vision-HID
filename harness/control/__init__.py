"""Control Subsystem for AutoDrive PC Test Harness."""

from typing import List, Optional
from harness.config import VehicleConfig, ControlConfig
from harness.vision.lane_detector import LaneDetectionResult
from harness.vision.obstacle_grid import DetectedThreat
from harness.control.stanley_pid import (
    ControlCommand,
    StanleyPidSteeringController,
)
from harness.control.pwm_modulator import PwmWasdModulator
from harness.control.speed_regulator import SpeedRegulator


class DrivingController:
    """Master Autonomous Driving Controller integrating steering, speed regulation, and AEB."""

    def __init__(
        self,
        vehicle_config: Optional[VehicleConfig] = None,
        control_config: Optional[ControlConfig] = None,
    ):
        self.veh_config = vehicle_config or VehicleConfig()
        self.ctrl_config = control_config or ControlConfig()

        self.steering_controller = StanleyPidSteeringController(
            vehicle_config=self.veh_config,
            control_config=self.ctrl_config,
        )
        self.speed_regulator = SpeedRegulator(
            vehicle_config=self.veh_config,
            control_config=self.ctrl_config,
        )
        self.pwm_modulator = PwmWasdModulator(config=self.ctrl_config)

        self._estimated_speed_mps = self.veh_config.nominal_speed_mps

    def reset(self) -> None:
        """Reset internal controllers and state."""
        self.steering_controller.reset()
        self.pwm_modulator.reset()
        self._estimated_speed_mps = self.veh_config.nominal_speed_mps

    def update(
        self,
        lane: LaneDetectionResult,
        threats: List[DetectedThreat],
        dt: float = 0.020,
    ) -> ControlCommand:
        """Compute full vehicle actuation command from lane geometry and threat list."""
        # 1. Longitudinal Speed & Braking Regulation
        throttle, brake, emergency_brake, target_speed = self.speed_regulator.update_longitudinal(
            current_speed_mps=self._estimated_speed_mps,
            curvature_kappa=lane.lookahead_curvature_kappa,
            threats=threats,
            dt=dt,
        )

        # Update simple internal speed integration
        if emergency_brake:
            self._estimated_speed_mps = max(0.0, self._estimated_speed_mps - self.veh_config.emergency_decel_mps2 * dt)
        elif brake > 0.10:
            self._estimated_speed_mps = max(0.0, self._estimated_speed_mps - brake * 5.0 * dt)
        elif throttle > 0.10:
            self._estimated_speed_mps = min(self.veh_config.max_speed_mps, self._estimated_speed_mps + throttle * 3.5 * dt)

        # 2. Lateral Stanley + PID + Feedforward Steering
        steering_angle = self.steering_controller.update_steering(
            lateral_error_m=lane.lateral_offset_m,
            heading_error_rad=lane.heading_angle_rad,
            curvature_kappa=lane.lookahead_curvature_kappa,
            curve_direction=lane.curve_direction,
            current_speed_mps=self._estimated_speed_mps,
            dt=dt,
        )

        return ControlCommand(
            throttle=throttle,
            brake=brake,
            steering_angle=steering_angle,
            handbrake=False,
            emergency_brake=emergency_brake,
            target_speed_mps=target_speed,
            current_speed_mps=self._estimated_speed_mps,
            lateral_error_m=lane.lateral_offset_m,
            heading_error_rad=lane.heading_angle_rad,
        )


__all__ = [
    "ControlCommand",
    "StanleyPidSteeringController",
    "PwmWasdModulator",
    "SpeedRegulator",
    "DrivingController",
]

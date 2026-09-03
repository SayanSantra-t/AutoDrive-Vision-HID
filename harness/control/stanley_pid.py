"""Stanley + PID + Feedforward Steering Controller.

Combines geometric heading alignment (40%), Stanley cross-track correction (35%),
PID feedback (25%), and predictive feedforward curvature anticipation with rate-limiting and deadband.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Dict, Any

from harness.config import VehicleConfig, ControlConfig


@dataclass
class ControlCommand:
    """Standardized vehicle actuation command."""
    throttle: float        # [0.0, 1.0]
    brake: float           # [0.0, 1.0]
    steering_angle: float  # [-1.0 (left), 1.0 (right)]
    handbrake: bool = False
    emergency_brake: bool = False
    target_speed_mps: float = 18.0
    current_speed_mps: float = 18.0
    lateral_error_m: float = 0.0
    heading_error_rad: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "throttle": round(self.throttle, 3),
            "brake": round(self.brake, 3),
            "steering_angle": round(self.steering_angle, 3),
            "handbrake": self.handbrake,
            "emergency_brake": self.emergency_brake,
            "target_speed_mps": round(self.target_speed_mps, 2),
            "current_speed_mps": round(self.current_speed_mps, 2),
            "lateral_error_m": round(self.lateral_error_m, 3),
            "heading_error_rad": round(self.heading_error_rad, 4),
        }


class StanleyPidSteeringController:
    """Multi-component steering controller with Stanley geometry, PID feedback, and curvature feedforward."""

    def __init__(
        self,
        vehicle_config: Optional[VehicleConfig] = None,
        control_config: Optional[ControlConfig] = None,
    ):
        self.veh = vehicle_config or VehicleConfig()
        self.ctrl = control_config or ControlConfig()

        self._integral_error = 0.0
        self._prev_lateral_error = 0.0
        self._filtered_derivative = 0.0
        self._prev_steering_cmd = 0.0

    def reset(self) -> None:
        """Reset internal integrator and derivative filters."""
        self._integral_error = 0.0
        self._prev_lateral_error = 0.0
        self._filtered_derivative = 0.0
        self._prev_steering_cmd = 0.0

    def update_steering(
        self,
        lateral_error_m: float,
        heading_error_rad: float,
        curvature_kappa: float = 0.0,
        curve_direction: str = "STRAIGHT",
        current_speed_mps: float = 18.0,
        dt: float = 0.020,
    ) -> float:
        """Calculate normalized steering angle [-1.0, 1.0] from tracking errors."""
        dt_safe = max(1e-4, dt)

        # 1. Stanley Cross-Track Term: atan(k * e / (v + v_soft))
        v_eff = max(0.1, current_speed_mps) + self.ctrl.stanley_soft_v
        delta_stanley = math.atan((self.ctrl.stanley_k * lateral_error_m) / v_eff)

        # 2. PID Lateral Error Terms
        # Proportional
        p_term = self.ctrl.kp * lateral_error_m

        # Integral with anti-windup clamping
        self._integral_error += lateral_error_m * dt_safe
        self._integral_error = max(-1.5, min(1.5, self._integral_error))
        i_term = self.ctrl.ki * self._integral_error

        # Derivative with 1st-order Low-Pass Filter
        raw_derivative = (lateral_error_m - self._prev_lateral_error) / dt_safe
        self._filtered_derivative = 0.35 * raw_derivative + 0.65 * self._filtered_derivative
        d_term = self.ctrl.kd * self._filtered_derivative
        self._prev_lateral_error = lateral_error_m

        pid_sum = p_term + i_term + d_term

        # 3. Feedforward Curvature Anticipation: atan(L * kappa * sign)
        dir_sign = -1.0 if curve_direction == "LEFT" else (1.0 if curve_direction == "RIGHT" else 0.0)
        delta_ff = self.ctrl.feedforward_k * math.atan(self.veh.wheelbase_m * curvature_kappa * dir_sign)

        # 4. Blended Steering Synthesis
        delta_raw = (
            self.ctrl.heading_weight * heading_error_rad
            + self.ctrl.stanley_weight * delta_stanley
            + self.ctrl.pid_weight * pid_sum
            + delta_ff
        )

        # Normalize relative to max wheel turning angle
        norm_steer = delta_raw / max(1e-3, self.veh.max_steer_angle_rad)

        # 5. Deadband Gating
        if abs(norm_steer) < self.ctrl.steering_deadband:
            norm_steer = 0.0

        # 6. Dynamic Slew-Rate Limiting
        max_delta_step = self.ctrl.steering_rate_limit * dt_safe
        slew_limited = max(
            self._prev_steering_cmd - max_delta_step,
            min(self._prev_steering_cmd + max_delta_step, norm_steer)
        )

        # Final Clamp to [-1.0, 1.0]
        final_steering = max(-1.0, min(1.0, slew_limited))
        self._prev_steering_cmd = final_steering

        return final_steering

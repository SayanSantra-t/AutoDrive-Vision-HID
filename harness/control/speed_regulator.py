"""Speed Regulator, Adaptive Cruise Control (ACC), and Graduated AEB.

Dynamically adapts vehicle speed based on road curvature, maintains safe following distance,
and executes graduated deceleration to eliminate abrupt false braking.
"""

from __future__ import annotations

import math
from typing import Optional, List, Tuple

from harness.config import VehicleConfig, ControlConfig
from harness.vision.obstacle_grid import DetectedThreat


class SpeedRegulator:
    """Longitudinal speed planner with curvature adaptation and graduated braking."""

    def __init__(
        self,
        vehicle_config: Optional[VehicleConfig] = None,
        control_config: Optional[ControlConfig] = None,
    ):
        self.veh = vehicle_config or VehicleConfig()
        self.ctrl = control_config or ControlConfig()

    def calculate_curve_speed_limit(self, curvature_kappa: float) -> float:
        """Compute maximum cornering speed to maintain lateral acceleration within limits."""
        if curvature_kappa < 1e-4:
            return self.veh.nominal_speed_mps

        # v_max = sqrt(a_lat_max / kappa)
        max_v = math.sqrt(self.veh.max_lateral_accel_mps2 / curvature_kappa)
        return max(self.veh.min_speed_mps, min(self.veh.nominal_speed_mps, max_v))

    def update_longitudinal(
        self,
        current_speed_mps: float,
        curvature_kappa: float,
        threats: List[DetectedThreat],
        dt: float = 0.020,
    ) -> Tuple[float, float, bool, float]:
        """Compute (throttle, brake, emergency_brake, target_speed_mps)."""
        # 1. Base Target Speed from Curvature
        target_speed = self.calculate_curve_speed_limit(curvature_kappa)

        # 2. Find closest confirmed threat in path
        primary_threat: Optional[DetectedThreat] = None
        min_threat_dist = 999.0

        for threat in threats:
            if threat.is_threat and threat.distance_m < min_threat_dist:
                min_threat_dist = threat.distance_m
                primary_threat = threat

        # 3. Collision Avoidance & AEB Logic
        if primary_threat is not None:
            d = primary_threat.distance_m
            ttc = primary_threat.ttc_sec

            # Emergency Braking Condition: Very close or imminent collision
            if d <= self.ctrl.aeb_distance_threshold_m or ttc <= self.ctrl.aeb_ttc_threshold_sec:
                return (0.0, 1.0, True, 0.0)

            # Graduated Deceleration Buffer (e.g. 2.5m - 6.0m)
            if d <= self.ctrl.safety_follow_distance_m:
                span = max(0.5, self.ctrl.safety_follow_distance_m - self.ctrl.aeb_distance_threshold_m)
                grad_brake = 0.20 + 0.60 * ((self.ctrl.safety_follow_distance_m - d) / span)
                grad_brake = min(0.85, max(0.15, grad_brake))
                target_speed = min(target_speed, 4.0)
                return (0.0, grad_brake, False, target_speed)

            # Approaching Threat Buffer (e.g. 6.0m - 12.0m)
            if d <= self.ctrl.safety_follow_distance_m * 2.0:
                speed_scale = (d - self.ctrl.safety_follow_distance_m) / self.ctrl.safety_follow_distance_m
                target_speed = min(target_speed, max(6.0, target_speed * speed_scale))

        # 4. Standard ACC Cruise Regulation
        speed_error = target_speed - current_speed_mps

        if speed_error > 0.5:
            # Accelerate
            throttle = min(1.0, max(0.15, speed_error * 0.35))
            brake = 0.0
        elif speed_error < -1.0:
            # Decelerate / Coast
            throttle = 0.0
            brake = min(0.60, max(0.15, abs(speed_error) * 0.20))
        else:
            # Cruise / maintain
            throttle = 0.25
            brake = 0.0

        return (throttle, brake, False, target_speed)

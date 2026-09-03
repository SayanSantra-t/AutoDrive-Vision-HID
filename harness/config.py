"""Master Configuration Definitions for AutoDrive PC Test & Benchmarking Harness.

Contains dataclasses for Vehicle, Vision, Control, Mobile Emulation, and Screen Capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any


@dataclass
class VehicleConfig:
    """Vehicle geometric, physical, and speed parameters."""
    wheelbase_m: float = 2.7
    track_width_m: float = 1.8
    max_steer_angle_rad: float = 0.4887  # ~28.0 degrees
    nominal_speed_mps: float = 18.0     # ~65 km/h
    max_speed_mps: float = 35.0         # ~126 km/h
    min_speed_mps: float = 2.0
    max_lateral_accel_mps2: float = 4.5
    emergency_decel_mps2: float = 8.0
    mass_kg: float = 1350.0


@dataclass
class VisionConfig:
    """Vision pipeline, lane detection, IPM, and obstacle parameters."""
    roi_top_ratio: float = 0.42       # Top horizon cutoff (42% from top, above road)
    roi_bottom_ratio: float = 0.72    # Bottom hood cutoff (72% from top, above car hood/bumper)
    scanline_count: int = 8           # Number of horizontal scanlines
    matched_kernel_width: int = 7     # Width of matched lane ribbon kernel
    min_edge_threshold: float = 8.0   # Minimum edge luminance gradient
    edge_mean_scale: float = 0.15     # Dynamic row threshold factor: max(8.0, 0.15 * mu_y)
    min_lane_width_px: int = 40
    max_lane_width_px: int = 450
    nominal_lane_width_m: float = 3.7
    meters_per_pixel_x: float = 0.005 # IPM calibration: lateral meters/pixel
    meters_per_pixel_y: float = 0.020 # IPM calibration: longitudinal meters/pixel
    lookahead_distance_px: float = 80.0
    poly_ema_alpha: float = 0.35      # Temporal smoothing factor for polynomial fit
    # Obstacle grid & AEB
    grid_cols: int = 8
    grid_rows: int = 6
    min_obstacle_persistence: int = 3 # Consecutive frames before AEB arming
    shadow_grad_ratio_threshold: float = 0.45
    min_obstacle_aspect_ratio: float = 0.30 # H/W ratio (reject < 0.25 flat markings)
    obstacle_corridor_width_m: float = 1.8  # In-lane vehicle track width (reject shoulder/curbs)
    camera_height_m: float = 1.3
    camera_pitch_rad: float = 0.08    # ~4.5 degrees downward


@dataclass
class ControlConfig:
    """Stanley steering, PID cross-track, feedforward, PWM, and braking parameters."""
    # Steering gains
    kp: float = 0.45                  # PID Proportional gain
    ki: float = 0.01                  # PID Integral gain
    kd: float = 0.18                  # PID Derivative gain (low-pass filtered)
    stanley_k: float = 0.80           # Stanley cross-track gain
    stanley_soft_v: float = 1.5       # Stanley softening velocity (m/s)
    feedforward_k: float = 0.60       # Feedforward curvature gain
    steering_deadband: float = 0.03   # Deadband in normalized [-1.0, 1.0] steering
    steering_rate_limit: float = 3.0  # Max change per second in normalized steering
    # Steering component weights
    heading_weight: float = 0.40
    stanley_weight: float = 0.35
    pid_weight: float = 0.25
    # PWM Modulation
    pwm_period_ms: float = 80.0       # Base PWM cycle window (80ms = 12.5Hz)
    min_pulse_width_ms: float = 15.0  # Minimum key-down pulse duration
    min_release_gap_ms: float = 15.0  # Minimum key-up release gap
    # Speed & Safety
    reverse_lockout_speed_mps: float = 0.83  # ~3.0 km/h: lock out 'S' when stopping
    aeb_ttc_threshold_sec: float = 0.80     # Time-To-Collision threshold for AEB
    aeb_distance_threshold_m: float = 2.5   # Distance threshold for AEB
    safety_follow_distance_m: float = 6.0   # ACC safety distance buffer
    soft_brake_distance_m: float = 4.5      # Distance to begin graduated deceleration


@dataclass
class EmulationConfig:
    """Mobile SoC constraint emulation and thermal soak configuration."""
    active_profile: str = "PROFILE_SNAPDRAGON_750G"
    enforce_affinity: bool = True
    enforce_throttling: bool = True
    enforce_memory_watchdog: bool = True
    thermal_simulation_enabled: bool = True
    ambient_temp_c: float = 28.0
    steady_state_temp_c: float = 44.0
    thermal_tau_sec: float = 90.0
    memory_warning_ratio: float = 0.85
    memory_critical_ratio: float = 1.00


@dataclass
class CaptureConfig:
    """Screen and game window capture parameters."""
    backend: str = "mss"              # "mss", "win32", "opencv", "synthetic"
    target_fps: int = 60
    window_title: str = "CarX Street"
    fallback_to_desktop: bool = True
    capture_width: int = 1280
    capture_height: int = 720
    custom_roi: Optional[Tuple[int, int, int, int]] = None  # (left, top, width, height)


@dataclass
class HarnessMasterConfig:
    """Master aggregated configuration for the AutoDrive test harness."""
    vehicle: VehicleConfig = field(default_factory=VehicleConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    emulation: EmulationConfig = field(default_factory=EmulationConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "vehicle": self.vehicle.__dict__,
            "vision": self.vision.__dict__,
            "control": self.control.__dict__,
            "emulation": self.emulation.__dict__,
            "capture": self.capture.__dict__,
        }

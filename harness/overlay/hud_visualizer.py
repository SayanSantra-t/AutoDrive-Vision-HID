"""AutoDrive Real-Time OpenCV Cockpit & Telemetry HUD Visualizer.

Renders an augmented reality HUD on captured CarX Street game frames,
matching the Jetpack Compose Android UI styling with AR drive corridor,
lane boundary splines, threat bounding boxes, steering PWM gauge,
digital speedometer, and WASD direct input telemetry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np


class HudColors:
    """BGR Color Palette matching AutoDrive Jetpack Compose Cyber Theme."""

    # Primary Accents (BGR)
    CYBER_CYAN: Tuple[int, int, int] = (255, 229, 0)       # #00E5FF
    NEON_GREEN: Tuple[int, int, int] = (3, 255, 118)       # #76FF03
    EMERALD_GREEN: Tuple[int, int, int] = (129, 185, 16)   # #10B981
    ALERT_RED: Tuple[int, int, int] = (68, 23, 255)        # #FF1744
    CRIMSON_DARK: Tuple[int, int, int] = (28, 28, 185)     # #B91C1C
    WARNING_AMBER: Tuple[int, int, int] = (7, 193, 255)     # #FFC107
    LANE_BLUE: Tuple[int, int, int] = (246, 182, 41)       # #29B6F6
    PURPLE_ACCENT: Tuple[int, int, int] = (188, 71, 171)   # #AB47BC

    # Surfaces & Panels (BGR)
    DEEP_SURFACE: Tuple[int, int, int] = (26, 13, 8)       # #080D1A
    PANEL_BG: Tuple[int, int, int] = (42, 23, 15)          # #0F172A
    PANEL_BORDER: Tuple[int, int, int] = (85, 65, 51)      # #334155
    BAR_TRACK: Tuple[int, int, int] = (59, 41, 30)         # #1E293B

    # Typography (BGR)
    TEXT_PRIMARY: Tuple[int, int, int] = (255, 255, 255)
    TEXT_SECONDARY: Tuple[int, int, int] = (224, 224, 224)
    TEXT_MUTED: Tuple[int, int, int] = (184, 163, 148)     # #94A3B8
    TEXT_DARK: Tuple[int, int, int] = (20, 20, 20)


@dataclass
class HudVisualizerConfig:
    """Configuration options for HUD Visualizer elements."""

    show_top_bar: bool = True
    show_horizon: bool = True
    show_corridor: bool = True
    show_threats: bool = True
    show_steering_arc: bool = True
    show_speedometer: bool = True
    show_throttle_brake_bars: bool = True
    show_wasd_keys: bool = True
    show_lateral_gauge: bool = True
    show_emulation_badge: bool = True
    show_collision_banner: bool = True
    camera_horizon_ratio: float = 0.45
    corridor_alpha: float = 0.35
    font_scale: float = 1.0


class HudVisualizer:
    """High-performance real-time OpenCV HUD Visualizer for AutoDrive test harness."""

    def __init__(self, config: Optional[HudVisualizerConfig] = None) -> None:
        self.config = config or HudVisualizerConfig()
        self._font = cv2.FONT_HERSHEY_SIMPLEX
        self._font_mono = cv2.FONT_HERSHEY_PLAIN
        self._banner_pulse_phase: float = 0.0

    def render(
        self,
        frame: np.ndarray,
        lane: Optional[Any] = None,
        threats: Optional[Sequence[Any]] = None,
        control: Optional[Any] = None,
        keyboard: Optional[Any] = None,
        telemetry: Optional[Dict[str, Any]] = None,
        profile_stats: Optional[Any] = None,
    ) -> np.ndarray:
        """Render full AR HUD cockpit overlay onto the input frame.

        Args:
            frame: Input BGR image (H, W, 3).
            lane: LaneDetectionResult or dict with lane geometry.
            threats: List of DetectedThreat objects or candidate bounding boxes.
            control: ControlCommand or dict with throttle, brake, steering.
            keyboard: KeyboardState or dict with key_w, key_a, key_s, key_d, key_space.
            telemetry: Optional dict with fps, latency_ms, mode, speed_kmh, etc.
            profile_stats: Optional mobile profile profiling statistics.

        Returns:
            Rendered BGR frame with full overlay.
        """
        if frame is None or frame.size == 0:
            return frame

        canvas = frame.copy()
        height, width = canvas.shape[:2]
        horizon_y = int(height * self.config.camera_horizon_ratio)

        # Normalize telemetry dict
        telem = self._normalize_telemetry(telemetry, control, lane, threats)

        # 1. Horizon & Pitch Reticle
        if self.config.show_horizon:
            self._draw_horizon_reticle(canvas, width, height, horizon_y)

        # 2. 3D Augmented Reality Corridor & Splines
        if self.config.show_corridor and lane is not None:
            self._draw_autonomous_corridor(
                canvas, width, height, horizon_y, lane, telem.get("collision_warning", False)
            )

        # 3. Detected Obstacle Bounding Boxes & Distance Tags
        if self.config.show_threats and threats:
            self._draw_threat_boxes(canvas, width, height, threats)

        # 4. Collision / AEB Warning Banner
        if self.config.show_collision_banner:
            is_aeb = telem.get("emergency_braking", False)
            is_warn = telem.get("collision_warning", False)
            if is_aeb or is_warn:
                self._draw_collision_banner(canvas, width, height, is_aeb, is_warn)

        # 5. Top Telemetry & Status Bar
        if self.config.show_top_bar:
            self._draw_top_bar(canvas, width, height, telem, profile_stats)

        # 6. Dynamic Steering Arc & Heading Angle Gauge
        if self.config.show_steering_arc:
            steering_angle_deg = telem.get("steering_angle_deg", 0.0)
            pwm_duty = telem.get("pwm_duty_pct", 0.0)
            self._draw_steering_arc(canvas, width, height, steering_angle_deg, pwm_duty)

        # 7. Lateral Center Deviation Bar
        if self.config.show_lateral_gauge and lane is not None:
            lat_offset = getattr(lane, "lateral_offset_m", None)
            if lat_offset is None and isinstance(lane, dict):
                lat_offset = lane.get("lateral_offset_m", 0.0)
            if lat_offset is not None:
                self._draw_lateral_offset_gauge(canvas, width, height, float(lat_offset))

        # 8. Digital Speedometer & Cockpit Gauge (Bottom Left)
        if self.config.show_speedometer:
            speed_kmh = telem.get("speed_kmh", 0.0)
            target_speed = telem.get("target_speed_kmh", 60.0)
            gear = telem.get("gear", "D1")
            self._draw_speedometer(canvas, 80, height - 75, speed_kmh, target_speed, gear)

        # 9. Throttle & Brake LED Meters (Left of Speedometer)
        if self.config.show_throttle_brake_bars:
            throttle_pct = int(telem.get("throttle", 0.0) * 100)
            brake_pct = int(telem.get("brake", 0.0) * 100)
            self._draw_throttle_brake_bars(canvas, 160, height - 135, throttle_pct, brake_pct)

        # 10. DirectInput WASD Key Telemetry (Bottom Right)
        if self.config.show_wasd_keys:
            self._draw_wasd_telemetry(canvas, width - 145, height - 130, keyboard)

        # 11. Mobile SoC Emulation & Performance Widget (Top Right below bar)
        if self.config.show_emulation_badge and profile_stats is not None:
            self._draw_emulation_badge(canvas, width, height, profile_stats)

        return canvas

    # =========================================================================
    # Internal Render Methods
    # =========================================================================

    def _draw_top_bar(
        self,
        canvas: np.ndarray,
        width: int,
        height: int,
        telem: Dict[str, Any],
        profile_stats: Optional[Any],
    ) -> None:
        """Draw rounded top HUD status bar with telemetry metrics."""
        bar_h = 42
        margin = 12
        bar_w = width - (margin * 2)

        # Translucent bar background
        overlay = canvas.copy()
        cv2.rectangle(
            overlay,
            (margin, margin),
            (margin + bar_w, margin + bar_h),
            HudColors.DEEP_SURFACE,
            -1,
        )
        cv2.addWeighted(overlay, 0.85, canvas, 0.15, 0, canvas)

        # Outer border
        cv2.rectangle(
            canvas,
            (margin, margin),
            (margin + bar_w, margin + bar_h),
            HudColors.PANEL_BORDER,
            1,
        )

        curr_x = margin + 12
        text_y = margin + 27

        # 1. Driving Mode Pill
        mode = telem.get("mode", "AUTONOMOUS")
        mode_str = f"● {mode.upper()}"
        mode_color = HudColors.CYBER_CYAN if "AUTO" in mode.upper() else HudColors.TEXT_MUTED
        cv2.putText(canvas, mode_str, (curr_x, text_y), self._font, 0.46, mode_color, 1, cv2.LINE_AA)
        curr_x += 160

        # 2. Vision Model Badge
        model_str = telem.get("vision_model", "MATCHED-IPM")
        cv2.putText(canvas, f"[{model_str}]", (curr_x, text_y), self._font, 0.42, HudColors.TEXT_MUTED, 1, cv2.LINE_AA)
        curr_x += 130

        # 3. Inference Latency Counter
        latency_ms = telem.get("latency_ms", 0.0)
        lat_text = f"LAT: {latency_ms:.1f}ms"
        cv2.putText(canvas, lat_text, (curr_x, text_y), self._font, 0.44, HudColors.CYBER_CYAN, 1, cv2.LINE_AA)
        curr_x += 115

        # 4. FPS Counter
        fps = telem.get("fps", 0.0)
        fps_text = f"FPS: {fps:.0f}"
        cv2.putText(canvas, fps_text, (curr_x, text_y), self._font, 0.44, HudColors.NEON_GREEN, 1, cv2.LINE_AA)
        curr_x += 95

        # 5. Steer Angle
        steer_deg = telem.get("steering_angle_deg", 0.0)
        steer_text = f"STR: {steer_deg:+.1f}°"
        cv2.putText(canvas, steer_text, (curr_x, text_y), self._font, 0.44, HudColors.TEXT_PRIMARY, 1, cv2.LINE_AA)
        curr_x += 115

        # 6. Targets Counter
        threat_count = telem.get("threat_count", 0)
        threat_color = HudColors.NEON_GREEN if threat_count == 0 else HudColors.WARNING_AMBER
        target_text = f"TGTS: {threat_count}"
        cv2.putText(canvas, target_text, (curr_x, text_y), self._font, 0.44, threat_color, 1, cv2.LINE_AA)
        curr_x += 105

        # 7. DirectInput Status Chip (Right-aligned)
        status_text = "DIRECTINPUT [ACTIVE]"
        (st_w, _), _ = cv2.getTextSize(status_text, self._font, 0.42, 1)
        right_x = margin + bar_w - st_w - 12
        if right_x > curr_x:
            cv2.putText(
                canvas,
                status_text,
                (right_x, text_y),
                self._font,
                0.42,
                HudColors.NEON_GREEN,
                1,
                cv2.LINE_AA,
            )

    def _draw_horizon_reticle(self, canvas: np.ndarray, width: int, height: int, horizon_y: int) -> None:
        """Draw dashed horizon line and vanishing point reticle crosshair."""
        mid_x = width // 2

        # Dashed horizon line
        dash_len = 16
        gap_len = 12
        start_x = int(width * 0.18)
        end_x = int(width * 0.82)
        x = start_x
        while x < end_x:
            x2 = min(x + dash_len, end_x)
            cv2.line(canvas, (x, horizon_y), (x2, horizon_y), (140, 100, 0), 1, cv2.LINE_AA)
            x += dash_len + gap_len

        # Vanishing point reticle
        cv2.circle(canvas, (mid_x, horizon_y), 6, HudColors.CYBER_CYAN, 1, cv2.LINE_AA)
        cv2.line(canvas, (mid_x - 14, horizon_y), (mid_x - 6, horizon_y), HudColors.CYBER_CYAN, 1, cv2.LINE_AA)
        cv2.line(canvas, (mid_x + 6, horizon_y), (mid_x + 14, horizon_y), HudColors.CYBER_CYAN, 1, cv2.LINE_AA)
        cv2.line(canvas, (mid_x, horizon_y - 14), (mid_x, horizon_y - 6), HudColors.CYBER_CYAN, 1, cv2.LINE_AA)
        cv2.line(canvas, (mid_x, horizon_y + 6), (mid_x, horizon_y + 14), HudColors.CYBER_CYAN, 1, cv2.LINE_AA)

    def _draw_autonomous_corridor(
        self,
        canvas: np.ndarray,
        width: int,
        height: int,
        horizon_y: int,
        lane: Any,
        collision_warning: bool,
    ) -> None:
        """Render 3D augmented reality drive corridor and boundary splines."""
        left_pts, right_pts, center_pts = self._extract_lane_points(lane, width, height, horizon_y)

        if len(left_pts) >= 2 and len(right_pts) >= 2:
            # Create corridor polygon (Left bottom -> top, Right top -> bottom)
            poly_pts = np.vstack([left_pts, right_pts[::-1]])
            overlay = canvas.copy()

            # Dynamic corridor color: Emerald Green / Cyan normally, Red on warning
            corridor_color = HudColors.CRIMSON_DARK if collision_warning else HudColors.EMERALD_GREEN
            cv2.fillPoly(overlay, [poly_pts.astype(np.int32)], corridor_color)
            cv2.addWeighted(overlay, self.config.corridor_alpha, canvas, 1.0 - self.config.corridor_alpha, 0, canvas)

            # Left & Right lane boundary lines with glow
            boundary_color = HudColors.ALERT_RED if collision_warning else HudColors.CYBER_CYAN
            cv2.polylines(canvas, [left_pts.astype(np.int32)], isClosed=False, color=boundary_color, thickness=3, lineType=cv2.LINE_AA)
            cv2.polylines(canvas, [right_pts.astype(np.int32)], isClosed=False, color=boundary_color, thickness=3, lineType=cv2.LINE_AA)

        # Draw Center Waypoint Dots
        if len(center_pts) > 0:
            dot_color = HudColors.ALERT_RED if collision_warning else HudColors.NEON_GREEN
            for pt in center_pts:
                px, py = int(pt[0]), int(pt[1])
                if 0 <= px < width and horizon_y <= py < height:
                    cv2.circle(canvas, (px, py), 3, dot_color, -1, cv2.LINE_AA)

        # Draw Curvature & Curve Direction Badge
        radius_m = getattr(lane, "curvature_radius_m", None)
        curve_dir = getattr(lane, "curve_direction", "STRAIGHT")
        if radius_m is None and isinstance(lane, dict):
            radius_m = lane.get("curvature_radius_m", 0.0)
            curve_dir = lane.get("curve_direction", "STRAIGHT")

        if radius_m is not None and radius_m > 0:
            rad_str = f"CURVE: {curve_dir} (R={radius_m:.0f}m)" if radius_m < 2000 else "TRACK: STRAIGHT"
            badge_x = width // 2 - 100
            badge_y = horizon_y + 35
            cv2.putText(canvas, rad_str, (badge_x, badge_y), self._font, 0.44, HudColors.CYBER_CYAN, 1, cv2.LINE_AA)

    def _draw_threat_boxes(
        self,
        canvas: np.ndarray,
        width: int,
        height: int,
        threats: Sequence[Any],
    ) -> None:
        """Render obstacle bounding boxes with corner brackets and distance tags."""
        for threat in threats:
            bbox, dist_m, is_threat, cls_name, conf, ttc = self._extract_threat_info(threat, width, height)
            if bbox is None:
                continue

            x1, y1, x2, y2 = bbox
            box_w = max(10, x2 - x1)
            box_h = max(10, y2 - y1)
            bracket_len = max(8, min(box_w // 4, 30))

            color = HudColors.ALERT_RED if is_threat else HudColors.CYBER_CYAN
            thickness = 2

            # Semi-transparent fill
            overlay = canvas.copy()
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
            cv2.addWeighted(overlay, 0.12 if is_threat else 0.06, canvas, 0.88 if is_threat else 0.94, 0, canvas)

            # Corner Brackets
            # Top-Left
            cv2.line(canvas, (x1, y1), (x1 + bracket_len, y1), color, thickness, cv2.LINE_AA)
            cv2.line(canvas, (x1, y1), (x1, y1 + bracket_len), color, thickness, cv2.LINE_AA)
            # Top-Right
            cv2.line(canvas, (x2, y1), (x2 - bracket_len, y1), color, thickness, cv2.LINE_AA)
            cv2.line(canvas, (x2, y1), (x2, y1 + bracket_len), color, thickness, cv2.LINE_AA)
            # Bottom-Left
            cv2.line(canvas, (x1, y2), (x1 + bracket_len, y2), color, thickness, cv2.LINE_AA)
            cv2.line(canvas, (x1, y2), (x1, y2 - bracket_len), color, thickness, cv2.LINE_AA)
            # Bottom-Right
            cv2.line(canvas, (x2, y2), (x2 - bracket_len, y2), color, thickness, cv2.LINE_AA)
            cv2.line(canvas, (x2, y2), (x2, y2 - bracket_len), color, thickness, cv2.LINE_AA)

            # Target Info Badge
            label_parts = [f"{cls_name} ({int(conf * 100)}%)", f"{dist_m:.1f}m"]
            if ttc < 99.0:
                label_parts.append(f"TTC: {ttc:.1f}s")
            if is_threat:
                label_parts.append("[AEB THREAT]")
            badge_text = " | ".join(label_parts)

            (tw, th), _ = cv2.getTextSize(badge_text, self._font, 0.38, 1)
            badge_y1 = max(0, y1 - th - 8)
            badge_y2 = y1

            cv2.rectangle(
                canvas,
                (x1, badge_y1),
                (x1 + tw + 10, badge_y2),
                HudColors.CRIMSON_DARK if is_threat else HudColors.PANEL_BG,
                -1,
            )
            cv2.rectangle(
                canvas,
                (x1, badge_y1),
                (x1 + tw + 10, badge_y2),
                color,
                1,
            )
            cv2.putText(
                canvas,
                badge_text,
                (x1 + 5, badge_y2 - 4),
                self._font,
                0.38,
                HudColors.TEXT_PRIMARY if is_threat else HudColors.CYBER_CYAN,
                1,
                cv2.LINE_AA,
            )

    def _draw_collision_banner(
        self,
        canvas: np.ndarray,
        width: int,
        height: int,
        is_aeb: bool,
        is_warn: bool,
    ) -> None:
        """Render high-visibility warning banner across upper-middle screen."""
        self._banner_pulse_phase += 0.15
        banner_w = int(width * 0.65)
        banner_h = 36
        banner_x = (width - banner_w) // 2
        banner_y = int(height * 0.22)

        bg_color = HudColors.CRIMSON_DARK if is_aeb else (0, 100, 200)
        border_color = HudColors.ALERT_RED if is_aeb else HudColors.WARNING_AMBER
        banner_text = (
            "!! EMERGENCY BRAKE APPLIED (AEB ACTIVE) !!"
            if is_aeb
            else "!! COLLISION WARNING - OBSTACLE AHEAD !!"
        )

        overlay = canvas.copy()
        cv2.rectangle(overlay, (banner_x, banner_y), (banner_x + banner_w, banner_y + banner_h), bg_color, -1)
        cv2.addWeighted(overlay, 0.85, canvas, 0.15, 0, canvas)
        cv2.rectangle(canvas, (banner_x, banner_y), (banner_x + banner_w, banner_y + banner_h), border_color, 2)

        (tw, th), _ = cv2.getTextSize(banner_text, self._font, 0.52, 2)
        text_x = banner_x + (banner_w - tw) // 2
        text_y = banner_y + (banner_h + th) // 2 - 2
        cv2.putText(canvas, banner_text, (text_x, text_y), self._font, 0.52, HudColors.TEXT_PRIMARY, 2, cv2.LINE_AA)

    def _draw_steering_arc(
        self,
        canvas: np.ndarray,
        width: int,
        height: int,
        steering_angle_deg: float,
        pwm_duty: float,
    ) -> None:
        """Render dynamic steering angle arc and PWM duty cycle indicator at bottom center."""
        center_x = width // 2
        center_y = height - 32
        radius = 70

        # Background Arc (180 deg sweep)
        cv2.ellipse(
            canvas,
            (center_x, center_y),
            (radius, radius),
            0,
            180,
            360,
            HudColors.PANEL_BORDER,
            2,
            cv2.LINE_AA,
        )

        # Center Neutral Mark
        cv2.line(canvas, (center_x, center_y - radius - 4), (center_x, center_y - radius + 4), HudColors.TEXT_MUTED, 1, cv2.LINE_AA)

        # Dynamic Steering Needle
        # angle: 270 deg is straight up. Clamped to [-35, +35] deg
        clamped_deg = max(-35.0, min(35.0, steering_angle_deg))
        angle_rad = math.radians(270.0 + clamped_deg)
        ptr_x = int(center_x + radius * math.cos(angle_rad))
        ptr_y = int(center_y + radius * math.sin(angle_rad))

        cv2.line(canvas, (center_x, center_y), (ptr_x, ptr_y), HudColors.CYBER_CYAN, 3, cv2.LINE_AA)
        cv2.circle(canvas, (ptr_x, ptr_y), 4, HudColors.NEON_GREEN, -1, cv2.LINE_AA)

        # Steering Angle Text & PWM
        steer_str = f"{steering_angle_deg:+.1f}°"
        (tw, _), _ = cv2.getTextSize(steer_str, self._font, 0.40, 1)
        cv2.putText(canvas, steer_str, (center_x - tw // 2, center_y - 12), self._font, 0.40, HudColors.TEXT_PRIMARY, 1, cv2.LINE_AA)

        if pwm_duty > 0.0:
            pwm_str = f"PWM: {int(pwm_duty)}%"
            (pw, _), _ = cv2.getTextSize(pwm_str, self._font, 0.35, 1)
            cv2.putText(canvas, pwm_str, (center_x - pw // 2, center_y - 28), self._font, 0.35, HudColors.CYBER_CYAN, 1, cv2.LINE_AA)

    def _draw_lateral_offset_gauge(
        self,
        canvas: np.ndarray,
        width: int,
        height: int,
        offset_m: float,
    ) -> None:
        """Render bottom lateral deviation offset bar."""
        center_x = width // 2
        gauge_y = height - 12
        gauge_w = 120

        # Background track
        cv2.line(canvas, (center_x - gauge_w // 2, gauge_y), (center_x + gauge_w // 2, gauge_y), HudColors.BAR_TRACK, 3, cv2.LINE_AA)
        # Center tick
        cv2.line(canvas, (center_x, gauge_y - 5), (center_x, gauge_y + 5), HudColors.TEXT_MUTED, 1, cv2.LINE_AA)

        # Moving offset indicator dot (scale: 1.0m = 50px)
        dot_x = int(center_x + max(-gauge_w // 2, min(gauge_w // 2, offset_m * 50)))
        dot_color = HudColors.ALERT_RED if abs(offset_m) > 0.40 else HudColors.CYBER_CYAN
        cv2.circle(canvas, (dot_x, gauge_y), 4, dot_color, -1, cv2.LINE_AA)

    def _draw_speedometer(
        self,
        canvas: np.ndarray,
        center_x: int,
        center_y: int,
        speed_kmh: float,
        target_speed: float,
        gear: str,
    ) -> None:
        """Render circular digital speedometer dial."""
        radius = 52

        # Outer circular dial
        overlay = canvas.copy()
        cv2.circle(overlay, (center_x, center_y), radius, HudColors.DEEP_SURFACE, -1)
        cv2.addWeighted(overlay, 0.75, canvas, 0.25, 0, canvas)
        cv2.circle(canvas, (center_x, center_y), radius, HudColors.PANEL_BORDER, 2, cv2.LINE_AA)
        cv2.circle(canvas, (center_x, center_y), radius - 3, HudColors.CYBER_CYAN, 1, cv2.LINE_AA)

        # Speed Digits
        spd_str = f"{int(speed_kmh)}"
        (sw, sh), _ = cv2.getTextSize(spd_str, self._font, 0.85, 2)
        cv2.putText(canvas, spd_str, (center_x - sw // 2, center_y + 2), self._font, 0.85, HudColors.TEXT_PRIMARY, 2, cv2.LINE_AA)

        # Units
        unit_str = "KM/H"
        (uw, _), _ = cv2.getTextSize(unit_str, self._font, 0.32, 1)
        cv2.putText(canvas, unit_str, (center_x - uw // 2, center_y + 16), self._font, 0.32, HudColors.CYBER_CYAN, 1, cv2.LINE_AA)

        # Gear & Target Speed Info
        gear_str = f"{gear} | TGT:{int(target_speed)}"
        (gw, _), _ = cv2.getTextSize(gear_str, self._font, 0.28, 1)
        cv2.putText(canvas, gear_str, (center_x - gw // 2, center_y + 32), self._font, 0.28, HudColors.TEXT_MUTED, 1, cv2.LINE_AA)

    def _draw_throttle_brake_bars(
        self,
        canvas: np.ndarray,
        x: int,
        y: int,
        throttle_pct: int,
        brake_pct: int,
    ) -> None:
        """Render vertical LED-style throttle and brake meters."""
        bar_w = 12
        bar_h = 75
        gap = 16

        # Throttle (GAS)
        self._draw_single_vertical_meter(
            canvas, x, y, bar_w, bar_h, throttle_pct, HudColors.NEON_GREEN, HudColors.CYBER_CYAN, "GAS"
        )

        # Brake
        self._draw_single_vertical_meter(
            canvas, x + bar_w + gap, y, bar_w, bar_h, brake_pct, HudColors.WARNING_AMBER, HudColors.ALERT_RED, "BRK"
        )

    def _draw_single_vertical_meter(
        self,
        canvas: np.ndarray,
        x: int,
        y: int,
        w: int,
        h: int,
        pct: int,
        color_low: Tuple[int, int, int],
        color_high: Tuple[int, int, int],
        label: str,
    ) -> None:
        """Draw a single vertical gauge meter with fill level."""
        clamped_pct = max(0, min(100, pct))
        fill_h = int((clamped_pct / 100.0) * h)

        # Track background
        cv2.rectangle(canvas, (x, y), (x + w, y + h), HudColors.BAR_TRACK, -1)
        cv2.rectangle(canvas, (x, y), (x + w, y + h), HudColors.PANEL_BORDER, 1)

        # Active fill from bottom
        if fill_h > 0:
            fill_y = y + h - fill_h
            active_color = color_high if clamped_pct > 60 else color_low
            cv2.rectangle(canvas, (x + 1, fill_y), (x + w - 1, y + h - 1), active_color, -1)

        # Label below
        (lw, _), _ = cv2.getTextSize(label, self._font, 0.28, 1)
        cv2.putText(canvas, label, (x + (w - lw) // 2, y + h + 12), self._font, 0.28, HudColors.TEXT_MUTED, 1, cv2.LINE_AA)

        # Percentage above
        pct_str = f"{clamped_pct}%"
        (pw, _), _ = cv2.getTextSize(pct_str, self._font, 0.28, 1)
        cv2.putText(canvas, pct_str, (x + (w - pw) // 2, y - 4), self._font, 0.28, color_high, 1, cv2.LINE_AA)

    def _draw_wasd_telemetry(
        self,
        canvas: np.ndarray,
        start_x: int,
        start_y: int,
        keyboard: Optional[Any],
    ) -> None:
        """Render WASD + Space direct input key visualizer."""
        kw, ka, ks, kd, kspace = self._extract_keyboard_state(keyboard)

        box_size = 28
        spacing = 4

        # Layout:
        #        [ W ]
        #    [ A ][ S ][ D ]
        #     [  SPACE  ]

        w_pos = (start_x + box_size + spacing, start_y)
        a_pos = (start_x, start_y + box_size + spacing)
        s_pos = (start_x + box_size + spacing, start_y + box_size + spacing)
        d_pos = (start_x + (box_size + spacing) * 2, start_y + box_size + spacing)
        space_pos = (start_x, start_y + (box_size + spacing) * 2)
        space_w = box_size * 3 + spacing * 2

        self._draw_key_box(canvas, w_pos[0], w_pos[1], box_size, box_size, "W", kw, HudColors.NEON_GREEN)
        self._draw_key_box(canvas, a_pos[0], a_pos[1], box_size, box_size, "A", ka, HudColors.CYBER_CYAN)
        self._draw_key_box(canvas, s_pos[0], s_pos[1], box_size, box_size, "S", ks, HudColors.ALERT_RED)
        self._draw_key_box(canvas, d_pos[0], d_pos[1], box_size, box_size, "D", kd, HudColors.CYBER_CYAN)
        self._draw_key_box(canvas, space_pos[0], space_pos[1], space_w, 20, "SPACE / HANDBRAKE", kspace, HudColors.ALERT_RED, is_wide=True)

    def _draw_key_box(
        self,
        canvas: np.ndarray,
        x: int,
        y: int,
        w: int,
        h: int,
        key_label: str,
        is_pressed: bool,
        active_color: Tuple[int, int, int],
        is_wide: bool = False,
    ) -> None:
        """Draw an individual keyboard button with pressed highlight."""
        bg_color = active_color if is_pressed else HudColors.PANEL_BG
        border_color = active_color if is_pressed else HudColors.PANEL_BORDER
        text_color = HudColors.TEXT_DARK if is_pressed else (HudColors.CYBER_CYAN if is_wide else HudColors.TEXT_PRIMARY)

        cv2.rectangle(canvas, (x, y), (x + w, y + h), bg_color, -1)
        cv2.rectangle(canvas, (x, y), (x + w, y + h), border_color, 1)

        scale = 0.32 if is_wide else 0.44
        thick = 1 if is_wide else 2
        (tw, th), _ = cv2.getTextSize(key_label, self._font, scale, thick)
        tx = x + (w - tw) // 2
        ty = y + (h + th) // 2 - 1
        cv2.putText(canvas, key_label, (tx, ty), self._font, scale, text_color, thick, cv2.LINE_AA)

    def _draw_emulation_badge(
        self,
        canvas: np.ndarray,
        width: int,
        height: int,
        profile_stats: Any,
    ) -> None:
        """Render mobile SoC hardware emulation details."""
        p_name = getattr(profile_stats, "name", "SNAPDRAGON 750G")
        rss_mb = getattr(profile_stats, "memory_rss_mb", 142.0)
        budget_ms = getattr(profile_stats, "target_budget_ms", 25.0)
        adherence_pct = getattr(profile_stats, "budget_compliance_pct", 99.2)

        badge_w = 210
        badge_h = 58
        badge_x = width - badge_w - 14
        badge_y = 60

        overlay = canvas.copy()
        cv2.rectangle(overlay, (badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h), HudColors.DEEP_SURFACE, -1)
        cv2.addWeighted(overlay, 0.80, canvas, 0.20, 0, canvas)
        cv2.rectangle(canvas, (badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h), HudColors.PANEL_BORDER, 1)

        # Title
        cv2.putText(canvas, f"SOC: {p_name.upper()}", (badge_x + 8, badge_y + 16), self._font, 0.36, HudColors.CYBER_CYAN, 1, cv2.LINE_AA)
        # RAM RSS
        cv2.putText(canvas, f"MEM: {rss_mb:.1f}MB", (badge_x + 8, badge_y + 34), self._font, 0.34, HudColors.TEXT_SECONDARY, 1, cv2.LINE_AA)
        # Budget Compliance
        cv2.putText(canvas, f"BUDGET: <= {budget_ms:.0f}ms ({adherence_pct:.1f}%)", (badge_x + 8, badge_y + 50), self._font, 0.32, HudColors.NEON_GREEN, 1, cv2.LINE_AA)

    # =========================================================================
    # Extraction Helpers
    # =========================================================================

    def _normalize_telemetry(
        self,
        telemetry: Optional[Dict[str, Any]],
        control: Optional[Any],
        lane: Optional[Any],
        threats: Optional[Sequence[Any]],
    ) -> Dict[str, Any]:
        """Combine raw inputs into a unified dictionary."""
        out = dict(telemetry or {})

        if control is not None:
            if hasattr(control, "throttle"):
                out.setdefault("throttle", float(control.throttle))
            if hasattr(control, "brake"):
                out.setdefault("brake", float(control.brake))
            if hasattr(control, "steering_angle"):
                out.setdefault("steering_angle_deg", float(control.steering_angle) * 35.0)
                out.setdefault("pwm_duty_pct", abs(float(control.steering_angle)) * 100.0)
            if hasattr(control, "emergency_brake"):
                out.setdefault("emergency_braking", bool(control.emergency_brake))
            if hasattr(control, "speed_kmh"):
                out.setdefault("speed_kmh", float(control.speed_kmh))
            if hasattr(control, "target_speed_kmh"):
                out.setdefault("target_speed_kmh", float(control.target_speed_kmh))

        if threats:
            out.setdefault("threat_count", len(threats))
            has_threat = any(getattr(t, "is_threat", False) or (isinstance(t, dict) and t.get("is_threat", False)) for t in threats)
            out.setdefault("collision_warning", has_threat)
        else:
            out.setdefault("threat_count", 0)
            out.setdefault("collision_warning", False)

        return out

    def _extract_lane_points(
        self,
        lane: Any,
        width: int,
        height: int,
        horizon_y: int,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Extract or synthesize pixel coordinates for left, right, and center lane paths."""
        # Check if lane object provides point lists
        left_pts = getattr(lane, "left_lane_points", None) or getattr(lane, "left_points", None)
        right_pts = getattr(lane, "right_lane_points", None) or getattr(lane, "right_points", None)
        center_pts = getattr(lane, "center_trajectory", None) or getattr(lane, "center_points", None)

        if isinstance(lane, dict):
            left_pts = left_pts or lane.get("left_lane_points") or lane.get("left_points")
            right_pts = right_pts or lane.get("right_lane_points") or lane.get("right_points")
            center_pts = center_pts or lane.get("center_trajectory") or lane.get("center_points")

        # If points are normalized [0.0, 1.0], scale to pixels
        if left_pts and len(left_pts) >= 2:
            left_arr = np.array(left_pts, dtype=np.float32)
            if np.max(left_arr[:, 0]) <= 1.5:
                left_arr[:, 0] *= width
                left_arr[:, 1] *= height
        else:
            # Synthesize nominal perspective left boundary
            left_arr = np.array([
                [width * 0.15, height * 0.98],
                [width * 0.25, height * 0.80],
                [width * 0.35, height * 0.65],
                [width * 0.42, horizon_y + 10],
            ], dtype=np.float32)

        if right_pts and len(right_pts) >= 2:
            right_arr = np.array(right_pts, dtype=np.float32)
            if np.max(right_arr[:, 0]) <= 1.5:
                right_arr[:, 0] *= width
                right_arr[:, 1] *= height
        else:
            # Synthesize nominal perspective right boundary
            right_arr = np.array([
                [width * 0.85, height * 0.98],
                [width * 0.75, height * 0.80],
                [width * 0.65, height * 0.65],
                [width * 0.58, horizon_y + 10],
            ], dtype=np.float32)

        if center_pts and len(center_pts) > 0:
            center_arr = np.array(center_pts, dtype=np.float32)
            if np.max(center_arr[:, 0]) <= 1.5:
                center_arr[:, 0] *= width
                center_arr[:, 1] *= height
        else:
            # Interpolate centerline
            center_arr = (left_arr + right_arr) / 2.0

        return left_arr, right_arr, center_arr

    def _extract_threat_info(
        self,
        threat: Any,
        width: int,
        height: int,
    ) -> Tuple[Optional[Tuple[int, int, int, int]], float, bool, str, float, float]:
        """Extract normalized threat parameters into pixel coordinates."""
        if isinstance(threat, dict):
            bbox = threat.get("bounding_box") or threat.get("bbox")
            dist_m = float(threat.get("distance_m", 15.0))
            is_threat = bool(threat.get("is_threat", False))
            cls_name = str(threat.get("class_name", threat.get("label", "VEHICLE")))
            conf = float(threat.get("confidence", 0.85))
            ttc = float(threat.get("time_to_collision_sec", 99.0))
        else:
            bbox = getattr(threat, "bounding_box", None) or getattr(threat, "bbox", None)
            dist_m = float(getattr(threat, "distance_m", 15.0))
            is_threat = bool(getattr(threat, "is_threat", False))
            cls_name = str(getattr(threat, "class_name", getattr(threat, "label", "VEHICLE")))
            conf = float(getattr(threat, "confidence", 0.85))
            ttc = float(getattr(threat, "time_to_collision_sec", 99.0))

        if bbox is None:
            return None, dist_m, is_threat, cls_name, conf, ttc

        x1, y1, x2, y2 = bbox
        # Check if normalized coordinates
        if max(x1, y1, x2, y2) <= 1.5:
            x1 = int(x1 * width)
            x2 = int(x2 * width)
            y1 = int(y1 * height)
            y2 = int(y2 * height)
        else:
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

        return (x1, y1, x2, y2), dist_m, is_threat, cls_name, conf, ttc

    def _extract_keyboard_state(
        self,
        keyboard: Optional[Any],
    ) -> Tuple[bool, bool, bool, bool, bool]:
        """Extract boolean states for W, A, S, D, Space."""
        if keyboard is None:
            return False, False, False, False, False

        if isinstance(keyboard, dict):
            return (
                bool(keyboard.get("key_w", keyboard.get("w", False))),
                bool(keyboard.get("key_a", keyboard.get("a", False))),
                bool(keyboard.get("key_s", keyboard.get("s", False))),
                bool(keyboard.get("key_d", keyboard.get("d", False))),
                bool(keyboard.get("key_space", keyboard.get("space", False))),
            )

        return (
            bool(getattr(keyboard, "key_w", getattr(keyboard, "w", False))),
            bool(getattr(keyboard, "key_a", getattr(keyboard, "a", False))),
            bool(getattr(keyboard, "key_s", getattr(keyboard, "s", False))),
            bool(getattr(keyboard, "key_d", getattr(keyboard, "d", False))),
            bool(getattr(keyboard, "key_space", getattr(keyboard, "space", False))),
        )

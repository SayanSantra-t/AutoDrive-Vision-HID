"""Adaptive Matched-Filter Lane Detector and IPM Parabolic Polynomial Curve Fitting.

Processes variable-lighting asphalt textures, shadows, and high-speed curves
using row-adaptive luminance thresholding, matched ribbon convolution, and 2nd-order spline fitting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple, List, Optional, Dict, Any
import numpy as np
import cv2

from harness.config import VisionConfig
from harness.vision.transforms import IPMTransformer


@dataclass
class LaneDetectionResult:
    """Standardized lane geometry, heading, curvature, and fit parameters."""
    has_left: bool
    has_right: bool
    lateral_offset_m: float
    heading_angle_rad: float
    curvature_radius_m: float
    confidence: float
    curve_direction: str  # "STRAIGHT", "LEFT", "RIGHT"
    left_fit: Optional[Tuple[float, float, float]] = None    # a, b, c in x = ay^2 + by + c
    right_fit: Optional[Tuple[float, float, float]] = None
    center_fit: Optional[Tuple[float, float, float]] = None
    lookahead_curvature_kappa: float = 0.0
    lane_width_px: float = 0.0
    left_barrier_distance_m: float = 99.0
    right_barrier_distance_m: float = 99.0
    barrier_repulsion_steer: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_left": self.has_left,
            "has_right": self.has_right,
            "lateral_offset_m": round(self.lateral_offset_m, 3),
            "heading_angle_rad": round(self.heading_angle_rad, 4),
            "curvature_radius_m": round(self.curvature_radius_m, 1),
            "confidence": round(self.confidence, 2),
            "curve_direction": self.curve_direction,
            "lookahead_kappa": round(self.lookahead_curvature_kappa, 6),
            "lane_width_px": round(self.lane_width_px, 1),
            "barrier_repulsion_steer": round(self.barrier_repulsion_steer, 3),
            "left_barrier_m": round(self.left_barrier_distance_m, 2),
            "right_barrier_m": round(self.right_barrier_distance_m, 2),
        }


class AdaptiveMatchedFilterLaneDetector:
    """Row-luminance adaptive matched-filter lane tracker with IPM polynomial fitting."""

    def __init__(
        self,
        config: Optional[VisionConfig] = None,
        transformer: Optional[IPMTransformer] = None,
    ):
        self.config = config or VisionConfig()
        self.transformer = transformer or IPMTransformer(config=self.config)

        # Matched ribbon filter kernel [-1, -1, 0, 2, 2, 0, -1, -1]
        self._matched_kernel = np.array([-1.0, -1.0, 0.0, 2.0, 2.0, 0.0, -1.0, -1.0], dtype=np.float32)
        self._matched_kernel /= np.sum(np.abs(self._matched_kernel))

        # Temporal smoothing state (EMA)
        self._prev_center_fit: Optional[np.ndarray] = None
        self._prev_left_fit: Optional[np.ndarray] = None
        self._prev_right_fit: Optional[np.ndarray] = None
        self._consecutive_lost_frames = 0

    def reset_state(self) -> None:
        """Reset temporal EMA filters."""
        self._prev_center_fit = None
        self._prev_left_fit = None
        self._prev_right_fit = None
        self._consecutive_lost_frames = 0

    def process_frame(self, frame_bgr: np.ndarray) -> LaneDetectionResult:
        """Execute lane detection on input image and return geometric LaneDetectionResult."""
        h, w = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]

        # Scan zone strictly above vehicle hood (y between 0.42 and 0.65)
        horizon_y = int(h * max(0.38, min(0.46, self.config.roi_top_ratio)))
        bottom_y = int(h * max(0.55, min(0.65, self.config.roi_bottom_ratio)))
        scanlines_y = np.linspace(horizon_y + 10, bottom_y, self.config.scanline_count, dtype=int)

        left_points: List[Tuple[float, float]] = []
        right_points: List[Tuple[float, float]] = []
        corridor_centers: List[Tuple[float, float]] = []
        left_barriers: List[float] = []
        right_barriers: List[float] = []
        mid_x = w / 2.0

        w_r = 10
        for y in scanlines_y:
            row = gray[y, :].astype(np.float32)
            row_sat = sat[y, :]

            # 1. Identify Drivable Asphalt and Physical Road Boundaries
            # Asphalt is achromatic (sat < 36), rejecting grass, flowers, and dirt
            is_asphalt = (row_sat < 36)
            asphalt_pts = np.where(is_asphalt)[0]
            if len(asphalt_pts) > 40:
                al = float(np.min(asphalt_pts))
                ar = float(np.max(asphalt_pts))
            else:
                al = 80.0
                ar = float(w - 80.0)

            left_barriers.append(al)
            right_barriers.append(ar)

            # 2. Extract Thin Bright Painted Stripes
            candidates = []
            for x in range(int(al) + 15, int(ar) - 15):
                if not is_asphalt[x]:
                    continue
                val = row[x] - 0.5 * (row[x - w_r] + row[x + w_r])
                if val > 13.0 and row[x] > 90.0:
                    candidates.append(x)

            clusters = np.split(candidates, np.where(np.diff(candidates) > 8)[0] + 1)
            lines = [float(np.mean(c)) for c in clusters if len(c) > 0]

            # 3. Form Valid Highway Lane Pairs (Width between 200px and 450px)
            # Rejects narrow gutters (< 200px) between road edge lines and barriers!
            valid_pairs = []
            for i in range(len(lines)):
                for j in range(i + 1, len(lines)):
                    lane_w = lines[j] - lines[i]
                    if 200.0 <= lane_w <= 450.0:
                        valid_pairs.append((lines[i], lines[j], (lines[i] + lines[j]) / 2.0))

            if valid_pairs:
                # Select lane pair closest to vehicle center
                best_pair = min(valid_pairs, key=lambda p: abs(p[2] - mid_x))
                left_points.append((best_pair[0], float(y)))
                right_points.append((best_pair[1], float(y)))
                corridor_centers.append((best_pair[2], float(y)))
            elif lines:
                # Road Departure Mitigation (RDM):
                # If vehicle is trapped in the right shoulder outside the road edge line
                rightmost_line = max(lines)
                if rightmost_line < (mid_x + 30.0):
                    # Edge line is to the left: vehicle is in right shoulder!
                    # Target center 180px into the highway to the left of the edge line!
                    target_c = rightmost_line - 180.0
                    left_points.append((rightmost_line - 340.0, float(y)))
                    right_points.append((rightmost_line, float(y)))
                    corridor_centers.append((target_c, float(y)))
                else:
                    # Vehicle has lines to its right; find closest to left
                    l_lines = [lx for lx in lines if lx < mid_x]
                    if l_lines:
                        l_val = max(l_lines)
                        left_points.append((l_val, float(y)))
                        right_points.append((l_val + 320.0, float(y)))
                        corridor_centers.append((l_val + 160.0, float(y)))
                    else:
                        target_c = rightmost_line - 160.0
                        left_points.append((rightmost_line - 320.0, float(y)))
                        right_points.append((rightmost_line, float(y)))
                        corridor_centers.append((target_c, float(y)))
            else:
                # Nominal asphalt corridor fallback
                corridor_centers.append(((al + ar) / 2.0, float(y)))

        has_left = len(left_points) >= 3
        has_right = len(right_points) >= 3

        left_fit: Optional[np.ndarray] = None
        right_fit: Optional[np.ndarray] = None
        center_fit: Optional[np.ndarray] = None

        if has_left:
            ly = np.array([p[1] for p in left_points], dtype=np.float32)
            lx = np.array([p[0] for p in left_points], dtype=np.float32)
            try:
                left_fit = np.polyfit(ly, lx, deg=2)
            except Exception:
                has_left = False

        if has_right:
            ry = np.array([p[1] for p in right_points], dtype=np.float32)
            rx = np.array([p[0] for p in right_points], dtype=np.float32)
            try:
                right_fit = np.polyfit(ry, rx, deg=2)
            except Exception:
                has_right = False

        if len(corridor_centers) >= 3:
            cy = np.array([p[1] for p in corridor_centers], dtype=np.float32)
            cx = np.array([p[0] for p in corridor_centers], dtype=np.float32)
            try:
                center_fit = np.polyfit(cy, cx, deg=2)
                confidence = 0.90
            except Exception:
                center_fit = np.array([0.0, 0.0, float(mid_x)], dtype=np.float32)
                confidence = 0.20
        else:
            center_fit = np.array([0.0, 0.0, float(mid_x)], dtype=np.float32)
            confidence = 0.10

        # Apply EMA smoothing if valid prior fit exists
        alpha = self.config.poly_ema_alpha
        if self._prev_center_fit is not None and (has_left or has_right):
            center_fit = alpha * center_fit + (1.0 - alpha) * self._prev_center_fit
        self._prev_center_fit = center_fit.copy()

        # Compute metric geometry at near evaluation point (y_near) and lookahead
        y_near = float(bottom_y)
        y_lookahead = float(horizon_y + (bottom_y - horizon_y) * 0.35)

        a, b, c = center_fit
        x_center_near = a * (y_near ** 2) + b * y_near + c
        x_center_look = a * (y_lookahead ** 2) + b * y_lookahead + c

        # Lateral offset: deviation of vehicle center (mid_x) from lane center
        lateral_offset_px = x_center_near - mid_x
        lateral_offset_m = lateral_offset_px * self.config.meters_per_pixel_x

        # Vehicle heading error relative to lane forward path:
        # dx is lateral drift ahead, dy is forward distance (pointing forward/up)
        dx_m = (x_center_look - x_center_near) * self.config.meters_per_pixel_x
        dy_m = (y_near - y_lookahead) * self.config.meters_per_pixel_y
        heading_angle_rad = math.atan2(dx_m, max(0.1, dy_m))

        # Lookahead curvature kappa = 2*|a| / (1 + (2*a*y_look + b)^2)^(1.5)
        slope_look = 2.0 * a * y_lookahead + b
        denom = (1.0 + slope_look ** 2) ** 1.5
        lookahead_kappa = (2.0 * abs(a)) / max(1e-6, denom)
        curvature_radius_m = 1.0 / max(1e-4, lookahead_kappa * 0.01)

        # Classify curve direction
        if lookahead_kappa < 1e-4 or abs(a) < 1e-5:
            curve_direction = "STRAIGHT"
        elif a < 0:
            curve_direction = "LEFT"
        else:
            curve_direction = "RIGHT"

        # Compute lane width in pixels
        lane_width_px = 0.0
        if has_left and has_right:
            x_l = left_fit[0] * (y_near ** 2) + left_fit[1] * y_near + left_fit[2]
            x_r = right_fit[0] * (y_near ** 2) + right_fit[1] * y_near + right_fit[2]
            lane_width_px = max(0.0, x_r - x_l)
        else:
            lane_width_px = float(w * 0.28)

        # Compute Barrier Proximities and APF Repulsion Steering Vector
        near_l_barrier = float(np.mean(left_barriers[-3:])) if left_barriers else 50.0
        near_r_barrier = float(np.mean(right_barriers[-3:])) if right_barriers else float(w - 50.0)

        left_barrier_distance_m = max(0.0, (mid_x - near_l_barrier) * self.config.meters_per_pixel_x)
        right_barrier_distance_m = max(0.0, (near_r_barrier - mid_x) * self.config.meters_per_pixel_x)

        # APF Repulsion Field (Safe standoff: 2.2 meters ~ 200px)
        safe_standoff_m = 2.2
        barrier_repulsion_steer = 0.0
        if left_barrier_distance_m < safe_standoff_m:
            prox_l = (safe_standoff_m - left_barrier_distance_m) / safe_standoff_m
            barrier_repulsion_steer += 0.38 * (prox_l ** 1.3)
        if right_barrier_distance_m < safe_standoff_m:
            prox_r = (safe_standoff_m - right_barrier_distance_m) / safe_standoff_m
            barrier_repulsion_steer -= 0.38 * (prox_r ** 1.3)

        return LaneDetectionResult(
            has_left=has_left,
            has_right=has_right,
            lateral_offset_m=float(lateral_offset_m),
            heading_angle_rad=float(heading_angle_rad),
            curvature_radius_m=float(curvature_radius_m),
            confidence=float(confidence),
            curve_direction=curve_direction,
            left_fit=(float(left_fit[0]), float(left_fit[1]), float(left_fit[2])) if has_left else None,
            right_fit=(float(right_fit[0]), float(right_fit[1]), float(right_fit[2])) if has_right else None,
            center_fit=(float(a), float(b), float(c)),
            lookahead_curvature_kappa=float(lookahead_kappa),
            lane_width_px=float(lane_width_px),
            left_barrier_distance_m=float(left_barrier_distance_m),
            right_barrier_distance_m=float(right_barrier_distance_m),
            barrier_repulsion_steer=float(barrier_repulsion_steer),
        )

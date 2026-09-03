"""Inverse Perspective Mapping (IPM) & Geometric Coordinate Transforms.

Maps camera perspective road geometry to metric top-down bird's-eye view planes
for parabolic polynomial curve fitting ($x = ay^2 + by + c$).
"""

from __future__ import annotations

from typing import Tuple, List, Optional
import numpy as np
import cv2

from harness.config import VisionConfig


class IPMTransformer:
    """Computes and applies forward/inverse perspective transformation matrices."""

    def __init__(
        self,
        image_shape: Tuple[int, int] = (720, 1280),  # (H, W)
        config: Optional[VisionConfig] = None,
    ):
        self.height, self.width = image_shape
        self.config = config or VisionConfig()

        self.src_points = self._compute_default_src_quad()
        self.dst_points = self._compute_default_dst_quad()

        self.M = cv2.getPerspectiveTransform(self.src_points, self.dst_points)
        self.M_inv = cv2.getPerspectiveTransform(self.dst_points, self.src_points)

    def _compute_default_src_quad(self) -> np.ndarray:
        """Compute standard source trapezoid on the road plane."""
        w, h = float(self.width), float(self.height)
        top_y = h * self.config.roi_top_ratio
        bot_y = h * self.config.roi_bottom_ratio

        # Trapezoid vertices: [bottom-left, bottom-right, top-right, top-left]
        return np.array([
            [w * 0.12, bot_y],
            [w * 0.88, bot_y],
            [w * 0.58, top_y],
            [w * 0.42, top_y],
        ], dtype=np.float32)

    def _compute_default_dst_quad(self) -> np.ndarray:
        """Compute destination rectangular bird's-eye canvas."""
        w, h = float(self.width), float(self.height)
        return np.array([
            [w * 0.25, h],
            [w * 0.75, h],
            [w * 0.75, 0.0],
            [w * 0.25, 0.0],
        ], dtype=np.float32)

    def update_resolution(self, new_shape: Tuple[int, int]) -> None:
        """Update transformation matrices for new camera resolution."""
        self.height, self.width = new_shape
        self.src_points = self._compute_default_src_quad()
        self.dst_points = self._compute_default_dst_quad()
        self.M = cv2.getPerspectiveTransform(self.src_points, self.dst_points)
        self.M_inv = cv2.getPerspectiveTransform(self.dst_points, self.src_points)

    def warp_ipm(self, image: np.ndarray, output_shape: Optional[Tuple[int, int]] = None) -> np.ndarray:
        """Transform camera view to top-down bird's-eye view."""
        out_w, out_h = output_shape if output_shape else (self.width, self.height)
        return cv2.warpPerspective(image, self.M, (out_w, out_h), flags=cv2.INTER_LINEAR)

    def unwarp_ipm(self, ipm_image: np.ndarray, output_shape: Optional[Tuple[int, int]] = None) -> np.ndarray:
        """Transform top-down bird's-eye view back to camera perspective."""
        out_w, out_h = output_shape if output_shape else (self.width, self.height)
        return cv2.warpPerspective(ipm_image, self.M_inv, (out_w, out_h), flags=cv2.INTER_LINEAR)

    def image_to_ipm_points(self, points: np.ndarray) -> np.ndarray:
        """Transform 2D (N, 2) image points to IPM ground coordinates."""
        if len(points) == 0:
            return np.empty((0, 2), dtype=np.float32)
        pts = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
        warped = cv2.perspectiveTransform(pts, self.M)
        return warped.reshape(-1, 2)

    def ipm_to_image_points(self, points: np.ndarray) -> np.ndarray:
        """Transform 2D (N, 2) IPM points back to image perspective coordinates."""
        if len(points) == 0:
            return np.empty((0, 2), dtype=np.float32)
        pts = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
        unwarped = cv2.perspectiveTransform(pts, self.M_inv)
        return unwarped.reshape(-1, 2)

    def ipm_px_to_meters(self, x_px: float, y_px: float) -> Tuple[float, float]:
        """Convert IPM pixel coordinates to metric ground coordinates (lateral x_m, longitudinal y_m)."""
        center_x_px = self.width / 2.0
        x_m = (x_px - center_x_px) * self.config.meters_per_pixel_x
        # y=0 is far, y=height is near
        y_m = (self.height - y_px) * self.config.meters_per_pixel_y
        return x_m, y_m

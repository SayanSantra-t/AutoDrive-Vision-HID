"""Spatial Obstacle Grid Detector with 3-Frame Temporal Persistence & Shadow Rejection.

Filters out flat road markings, skid marks, tree/bridge shadows, and lighting variations
while tracking elevated 3D obstacles across consecutive frames to prevent false AEB triggers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple, List, Optional, Dict, Any
import numpy as np
import cv2

from harness.config import VisionConfig


@dataclass
class DetectedThreat:
    """Standardized representation of a detected obstacle or collision threat."""
    is_threat: bool
    distance_m: float
    lateral_offset_m: float
    bounding_box: Tuple[int, int, int, int]  # (x, y, w, h)
    persistence_frames: int
    ttc_sec: float
    confidence: float
    category: str = "OBSTACLE"  # "VEHICLE", "OBSTACLE", "NONE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_threat": self.is_threat,
            "distance_m": round(self.distance_m, 2),
            "lateral_offset_m": round(self.lateral_offset_m, 2),
            "bbox": self.bounding_box,
            "persistence": self.persistence_frames,
            "ttc_sec": round(self.ttc_sec, 2),
            "confidence": round(self.confidence, 2),
            "category": self.category,
        }


@dataclass
class _TrackedObject:
    """Internal temporal tracker representation."""
    track_id: int
    bbox: Tuple[int, int, int, int]
    centroid: Tuple[float, float]
    distance_m: float
    prev_distance_m: float
    persistence_count: int
    last_seen_frame: int
    confidence: float


class SpatialObstacleGridDetector:
    """Grid-based neural and spatial gradient obstacle detector with shadow rejection."""

    def __init__(self, config: Optional[VisionConfig] = None):
        self.config = config or VisionConfig()
        self._next_track_id = 1
        self._tracks: List[_TrackedObject] = []
        self._frame_count = 0

    def reset_state(self) -> None:
        """Reset temporal tracking state."""
        self._tracks.clear()
        self._next_track_id = 1
        self._frame_count = 0

    def _compute_iou(self, boxA: Tuple[int, int, int, int], boxB: Tuple[int, int, int, int]) -> float:
        """Calculate Intersection over Union (IoU) between two bounding boxes (x, y, w, h)."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
        yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = boxA[2] * boxA[3]
        boxBArea = boxB[2] * boxB[3]

        denom = float(boxAArea + boxBArea - interArea)
        return interArea / max(1.0, denom)

    def _is_shadow_or_road_marking(
        self,
        road_gray: np.ndarray,
        grad_x: np.ndarray,
        grad_y: np.ndarray,
        bbox: Tuple[int, int, int, int],
        road_bgr: Optional[np.ndarray] = None,
    ) -> bool:
        """Determine whether candidate box is a flat 2D shadow/road marking or real 3D obstacle."""
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            return True

        h_road, w_road = road_gray.shape[:2]
        scale = w_road / 640.0

        min_obs_w = int(18 * scale)
        min_obs_h = int(12 * scale)
        max_obs_w = int(w_road * 0.35)

        # 1. Bounded Dimensions & Aspect Ratio
        if w < min_obs_w or h < min_obs_h or w > max_obs_w:
            return True

        aspect_ratio = float(h) / float(w)
        if aspect_ratio < 0.30 or aspect_ratio > 1.85:
            return True

        box_patch = road_gray[y:y+h, x:x+w]
        if box_patch.size == 0:
            return True

        # 2. Painted Road Marking / Lane Stripe Rejection
        # Flat white/yellow paint markings have uniform high luminance with low internal texture variance
        box_mean = float(np.mean(box_patch))
        box_std = float(np.std(box_patch))

        # Check chromaticity if BGR available
        has_color = False
        if road_bgr is not None:
            bgr_patch = road_bgr[y:y+h, x:x+w].astype(np.float32)
            b_p, g_p, r_p = cv2.split(bgr_patch)
            c_diff = np.maximum(np.abs(r_p - b_p), np.abs(r_p - g_p))
            if float(np.max(c_diff)) > 25.0:
                has_color = True

        # Pure neutral painted stripes on asphalt (lane markers, crosswalks, arrows)
        if not has_color and box_mean > 120.0 and box_std < 14.0:
            return True  # Reject flat painted road stripe

        # 3. Cast Shadow Horizontal Continuity vs Local Ground Plane
        left_x1 = max(0, x - int(w * 0.8))
        left_x2 = max(0, x - 4)
        right_x1 = min(w_road, x + w + 4)
        right_x2 = min(w_road, x + int(w * 1.8))

        if (left_x2 - left_x1) > 5 and (right_x2 - right_x1) > 5:
            mean_left = float(np.mean(road_gray[y:y+h, left_x1:left_x2]))
            mean_right = float(np.mean(road_gray[y:y+h, right_x1:right_x2]))

            if abs(box_mean - mean_left) < 6.0 and abs(box_mean - mean_right) < 6.0:
                roi_gx = np.abs(grad_x[y:y+h, x:x+w])
                roi_gy = np.abs(grad_y[y:y+h, x:x+w])
                mean_gx = float(np.mean(roi_gx)) if roi_gx.size > 0 else 0.0
                mean_gy = float(np.mean(roi_gy)) if roi_gy.size > 0 else 0.0
                if mean_gx < 15.0 or (mean_gy > 0 and (mean_gx / mean_gy) < 0.55):
                    return True  # Horizontal shadow band

        # 4. Elevation & Vertical Texture Signature
        upper_h = max(1, h // 2)
        upper_half = road_gray[y:y + upper_h, x:x + w]
        if upper_half.size > 0:
            upper_std = float(np.std(upper_half))
            if not has_color and upper_std < 5.0 and box_std < 7.0:
                return True  # Flat homogeneous asphalt patch

        return False

    def detect_candidates(self, frame_bgr: np.ndarray) -> List[Tuple[Tuple[int, int, int, int], float]]:
        """Extract raw 3D obstacle candidates from frame."""
        h_img, w_img = frame_bgr.shape[:2]
        horizon_y = int(h_img * self.config.roi_top_ratio)
        bottom_y = int(h_img * self.config.roi_bottom_ratio)

        road_bgr = frame_bgr[horizon_y:bottom_y, :]
        road_gray = cv2.cvtColor(road_bgr, cv2.COLOR_BGR2GRAY)
        h_road, w_road = road_gray.shape[:2]

        grad_x = cv2.Sobel(road_gray, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(road_gray, cv2.CV_32F, 0, 1, ksize=3)

        scale = w_road / 640.0

        # 1. Identify rows with horizontal shadow bands (grad_y spanning across >= 5 columns)
        grid_cols = self.config.grid_cols
        cell_w = w_road // grid_cols
        shadow_row_mask = np.zeros(h_road, dtype=bool)

        blur_for_shadow = cv2.GaussianBlur(road_gray, (9, 9), 0)
        shadow_grad_y = np.abs(cv2.Sobel(blur_for_shadow, cv2.CV_32F, 0, 1, ksize=3))

        for r_start in range(0, h_road - 15, 10):
            r_end = min(h_road, r_start + 20)
            col_gy = [
                float(np.mean(shadow_grad_y[r_start:r_end, c * cell_w:(c + 1) * cell_w]))
                for c in range(grid_cols)
            ]
            elevated_cols = sum(1 for gy in col_gy if gy > 35.0)
            if elevated_cols >= 5:
                shadow_row_mask[r_start:r_end] = True

        # 2. Chromatic and 3D Texture Feature Map
        b_ch, g_ch, r_ch = cv2.split(road_bgr.astype(np.float32))
        color_diff = np.maximum(np.abs(r_ch - b_ch), np.abs(r_ch - g_ch))
        
        # Vehicles with chromatic signature (red, blue, taillights)
        veh_chroma_mask = (color_diff > 25.0).astype(np.uint8)

        # 3D texture & dark vehicle contact shadow mask
        row_medians = np.median(road_gray, axis=1, keepdims=True)
        dark_contact = (road_gray.astype(np.float32) < (row_medians - 20.0)).astype(np.uint8)

        feat_mask = np.bitwise_or(veh_chroma_mask, dark_contact)
        feat_mask[shadow_row_mask, :] = 0

        # Mask out UI HUD elements: Minimap (bottom-left) and Speedometer (bottom-right)
        feat_mask[int(h_road * 0.55):, :int(w_road * 0.22)] = 0
        feat_mask[int(h_road * 0.50):, int(w_road * 0.72):] = 0

        # Mask out outer roadside shoulders (curbs, barriers, guard rails)
        feat_mask[:, :int(w_road * 0.12)] = 0
        feat_mask[:, int(w_road * 0.86):] = 0

        # Morphological closing to connect vehicle body and taillights
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed_mask = cv2.morphologyEx(feat_mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates: List[Tuple[Tuple[int, int, int, int], float]] = []

        min_obs_w = int(18 * scale)
        min_obs_h = int(12 * scale)
        max_obs_w = int(w_road * 0.32)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < (60.0 * (scale ** 2)):
                continue
            bx, by, bw, bh = cv2.boundingRect(cnt)

            if bw < min_obs_w or bh < min_obs_h or bw > max_obs_w:
                continue

            aspect_ratio = float(bh) / float(bw)
            if aspect_ratio < 0.30 or aspect_ratio > 1.75:
                continue

            bbox = (bx, by, bw, bh)
            if not self._is_shadow_or_road_marking(road_gray, grad_x, grad_y, bbox, road_bgr=road_bgr):
                abs_bbox = (bx, by + horizon_y, bw, bh)
                conf = min(1.0, float(area) / (500.0 * scale) + 0.3)
                candidates.append((abs_bbox, conf))

        return candidates

    def process_frame(
        self,
        frame_bgr: np.ndarray,
        vehicle_speed_mps: float = 18.0,
    ) -> List[DetectedThreat]:
        """Process frame and return temporally validated DetectedThreat objects."""
        self._frame_count += 1
        h_img, w_img = frame_bgr.shape[:2]
        horizon_y = int(h_img * self.config.roi_top_ratio)

        candidates = self.detect_candidates(frame_bgr)
        matched_track_ids = set()

        # Update existing tracks with new candidates
        for box, conf in candidates:
            bx, by, bw, bh = box
            centroid = (bx + bw / 2.0, by + bh / 2.0)
            bot_y = by + bh

            # Ground perspective distance model: D = k / (y_bottom - y_horizon)
            denom = max(1.0, float(bot_y - horizon_y))
            distance_m = max(1.0, min(80.0, (h_img * 0.55 * self.config.camera_height_m) / denom))

            # Match with active tracks
            best_track: Optional[_TrackedObject] = None
            best_iou = 0.20

            for track in self._tracks:
                iou = self._compute_iou(box, track.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_track = track

            if best_track is not None:
                best_track.prev_distance_m = best_track.distance_m
                best_track.distance_m = distance_m
                best_track.bbox = box
                best_track.centroid = centroid
                best_track.confidence = conf
                best_track.persistence_count += 1
                best_track.last_seen_frame = self._frame_count
                matched_track_ids.add(best_track.track_id)
            else:
                new_track = _TrackedObject(
                    track_id=self._next_track_id,
                    bbox=box,
                    centroid=centroid,
                    distance_m=distance_m,
                    prev_distance_m=distance_m,
                    persistence_count=1,
                    last_seen_frame=self._frame_count,
                    confidence=conf,
                )
                self._next_track_id += 1
                self._tracks.append(new_track)
                matched_track_ids.add(new_track.track_id)

        # Decay/prune stale tracks
        self._tracks = [
            t for t in self._tracks
            if (self._frame_count - t.last_seen_frame) <= 2
        ]

        # Generate verified DetectedThreat outputs
        threats: List[DetectedThreat] = []
        half_corridor_m = self.config.obstacle_corridor_width_m / 2.0

        for track in self._tracks:
            cx, cy = track.centroid
            lateral_offset_px = cx - (w_img / 2.0)
            lateral_offset_m = lateral_offset_px * self.config.meters_per_pixel_x

            # Relative velocity approximation: v_rel = (prev_d - d) / dt
            v_rel = max(0.0, track.prev_distance_m - track.distance_m) * 30.0
            closing_speed = vehicle_speed_mps + v_rel
            ttc_sec = track.distance_m / max(1.0, closing_speed)

            # Check 3-frame persistence and corridor presence
            is_persistent = track.persistence_count >= self.config.min_obstacle_persistence
            in_corridor = abs(lateral_offset_m) <= half_corridor_m
            is_real_threat = is_persistent and in_corridor and (track.distance_m < 25.0)

            threats.append(
                DetectedThreat(
                    is_threat=is_real_threat,
                    distance_m=float(track.distance_m),
                    lateral_offset_m=float(lateral_offset_m),
                    bounding_box=track.bbox,
                    persistence_frames=int(track.persistence_count),
                    ttc_sec=float(ttc_sec),
                    confidence=float(track.confidence),
                    category="VEHICLE" if track.bbox[3] > 30 else "OBSTACLE",
                )
            )

        return threats

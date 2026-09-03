"""Vision Subsystem for AutoDrive PC Test Harness."""

from typing import Tuple, List, Optional
import numpy as np

from harness.config import VisionConfig
from harness.vision.transforms import IPMTransformer
from harness.vision.lane_detector import (
    LaneDetectionResult,
    AdaptiveMatchedFilterLaneDetector,
)
from harness.vision.obstacle_grid import (
    DetectedThreat,
    SpatialObstacleGridDetector,
)


class VisionPipeline:
    """Unified Vision Pipeline combining IPM lane detection and obstacle tracking."""

    def __init__(self, config: Optional[VisionConfig] = None):
        self.config = config or VisionConfig()
        self.transformer = IPMTransformer(config=self.config)
        self.lane_detector = AdaptiveMatchedFilterLaneDetector(
            config=self.config, transformer=self.transformer
        )
        self.obstacle_detector = SpatialObstacleGridDetector(config=self.config)

    def process_frame(
        self,
        frame_bgr: np.ndarray,
        vehicle_speed_mps: float = 18.0,
    ) -> Tuple[LaneDetectionResult, List[DetectedThreat]]:
        """Process video frame and return lane geometry + obstacle threats."""
        lane_result = self.lane_detector.process_frame(frame_bgr)
        threats = self.obstacle_detector.process_frame(
            frame_bgr, vehicle_speed_mps=vehicle_speed_mps
        )
        return lane_result, threats

    def reset_state(self) -> None:
        """Reset temporal state across video sequences."""
        self.lane_detector.reset_state()
        self.obstacle_detector.reset_state()


__all__ = [
    "IPMTransformer",
    "LaneDetectionResult",
    "AdaptiveMatchedFilterLaneDetector",
    "DetectedThreat",
    "SpatialObstacleGridDetector",
    "VisionPipeline",
]

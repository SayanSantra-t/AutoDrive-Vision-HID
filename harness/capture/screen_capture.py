"""Screen Capture Subsystem for AutoDrive PC Test & Benchmarking Harness.

Supports high-speed MSS screen grab, Win32 GDI BitBlt capture,
OpenCV camera/video streams, and dynamic Synthetic procedural rendering.
"""

from __future__ import annotations

import sys
import time
import math
import ctypes
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List, Dict, Any
import numpy as np
import cv2

from harness.config import CaptureConfig
from harness.capture.window_finder import WindowFinder, WindowRect

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False


class CaptureBackend(ABC):
    """Abstract base class for all screen capture backends."""

    @abstractmethod
    def capture_frame(self) -> Tuple[np.ndarray, float]:
        """Capture and return (frame_bgr: np.ndarray, timestamp_sec: float)."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if backend is operational and available."""
        pass

    def release(self) -> None:
        """Release underlying system resources."""
        pass


class MssCaptureBackend(CaptureBackend):
    """High-performance multi-monitor desktop grabber using MSS."""

    def __init__(self, roi: Optional[Dict[str, int]] = None):
        self._sct = None
        self._roi = roi
        if HAS_MSS:
            self._sct = mss.mss()

    def set_roi(self, roi: Dict[str, int]) -> None:
        """Set or update capture bounding box dictionary (left, top, width, height)."""
        self._roi = roi

    def is_available(self) -> bool:
        return HAS_MSS and self._sct is not None

    def capture_frame(self) -> Tuple[np.ndarray, float]:
        if not self.is_available():
            raise RuntimeError("MSS is not available on this platform.")

        t_now = time.perf_counter()
        try:
            monitor = self._roi if self._roi else self._sct.monitors[1]
            raw_img = self._sct.grab(monitor)
            # MSS returns BGRA buffer; convert to BGR uint8 ndarray
            frame_bgra = np.frombuffer(raw_img.raw, dtype=np.uint8).reshape((raw_img.height, raw_img.width, 4))
            frame_bgr = frame_bgra[:, :, :3]
            return frame_bgr.copy(), t_now
        except Exception as e:
            # If BitBlt / MSS fails, invalidate MSS backend and raise for failover
            self.release()
            raise RuntimeError(f"MSS grab failed: {e}") from e

    def release(self) -> None:
        if self._sct:
            self._sct.close()
            self._sct = None


class Win32CaptureBackend(CaptureBackend):
    """Direct Win32 GDI / BitBlt window capture backend for DirectX game windows."""

    def __init__(self, hwnd: Optional[int] = None):
        self._hwnd = hwnd
        self._is_windows = sys.platform.startswith("win")

    def set_hwnd(self, hwnd: int) -> None:
        self._hwnd = hwnd

    def is_available(self) -> bool:
        return self._is_windows and (self._hwnd is not None or ctypes.windll.user32.GetDesktopWindow() != 0)

    def capture_frame(self) -> Tuple[np.ndarray, float]:
        if not self._is_windows:
            raise RuntimeError("Win32 capture is only supported on Windows.")

        t_now = time.perf_counter()
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        target_hwnd = self._hwnd if self._hwnd else user32.GetDesktopWindow()

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        if self._hwnd:
            if not user32.IsWindow(self._hwnd):
                raise RuntimeError(f"Target window (HWND={self._hwnd}) was closed by user.")
            user32.GetClientRect(target_hwnd, ctypes.byref(rect))
        else:
            user32.GetWindowRect(target_hwnd, ctypes.byref(rect))

        width = rect.right - rect.left
        height = rect.bottom - rect.top

        if width <= 0 or height <= 0:
            width, height = 1280, 720

        hwnd_dc = user32.GetDC(target_hwnd)
        mfc_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        save_bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
        gdi32.SelectObject(mfc_dc, save_bitmap)

        # Ensure attached to interactive Default desktop
        try:
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass

        # For target game window, first attempt PrintWindow with PW_RENDERFULLCONTENT (0x02)
        success = False
        if self._hwnd:
            try:
                # PW_RENDERFULLCONTENT = 2 asks DWM to render DirectX / layered content
                if user32.PrintWindow(target_hwnd, mfc_dc, 2) != 0:
                    success = True
            except Exception:
                pass

        if not success:
            # Fallback to BitBlt SRCCOPY
            gdi32.BitBlt(mfc_dc, 0, 0, width, height, hwnd_dc, 0, 0, 0x00CC0020)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = width
        bmi.biHeight = -height  # top-down DIB
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buffer_size = width * height * 4
        buffer = ctypes.create_string_buffer(buffer_size)

        gdi32.GetDIBits(
            mfc_dc,
            save_bitmap,
            0,
            height,
            buffer,
            ctypes.byref(bmi),
            0,
        )

        # Clean up GDI handles
        gdi32.DeleteObject(save_bitmap)
        gdi32.DeleteDC(mfc_dc)
        user32.ReleaseDC(target_hwnd, hwnd_dc)

        img_arr = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 4))
        frame_bgr = img_arr[:, :, :3].copy()
        return frame_bgr, t_now


class OpenCvCaptureBackend(CaptureBackend):
    """Capture frames from OpenCV VideoCapture (webcam, virtual cam, or video file)."""

    def __init__(self, source: Any = 0):
        self._source = source
        self._cap = cv2.VideoCapture(source)

    def is_available(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def capture_frame(self) -> Tuple[np.ndarray, float]:
        if not self.is_available():
            raise RuntimeError(f"OpenCV capture source {self._source} is not open.")

        t_now = time.perf_counter()
        ret, frame = self._cap.read()
        if not ret or frame is None:
            # Loop video file if reached EOF
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()
            if not ret or frame is None:
                raise RuntimeError("Failed to read frame from OpenCV source.")

        return frame, t_now

    def release(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None


class SyntheticCaptureBackend(CaptureBackend):
    """Dynamic procedural CarX Street road generator for offline testing and benchmarks."""

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        curve_freq: float = 0.25,
        add_shadows: bool = True,
        add_obstacles: bool = False,
    ):
        self.width = width
        self.height = height
        self.curve_freq = curve_freq
        self.add_shadows = add_shadows
        self.add_obstacles = add_obstacles
        self.frame_count = 0
        self.start_time = time.perf_counter()

    def is_available(self) -> bool:
        return True

    def capture_frame(self) -> Tuple[np.ndarray, float]:
        t_now = time.perf_counter()
        self.frame_count += 1
        t = (t_now - self.start_time)

        # Base frame: Sky (top 45%) and Road (bottom 55%)
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        horizon_y = int(self.height * 0.45)

        # Sky gradient (dark blue to horizon orange/sky blue)
        for y in range(horizon_y):
            ratio = y / horizon_y
            frame[y, :, 0] = int(120 + 40 * ratio)  # B
            frame[y, :, 1] = int(80 + 30 * ratio)   # G
            frame[y, :, 2] = int(40 + 20 * ratio)   # R

        # Road surface (asphalt gray with procedural grain texture)
        road_mask = np.arange(self.height - horizon_y, dtype=np.float32)[:, None]
        road_depth = road_mask / (self.height - horizon_y)
        asphalt_base = (45 + 25 * road_depth).astype(np.uint8)
        frame[horizon_y:, :] = np.repeat(asphalt_base, self.width, axis=1)[:, :, None]

        # Add asphalt high-frequency grain
        noise = (np.random.randint(-5, 6, (self.height - horizon_y, self.width), dtype=np.int16))
        road_slice = frame[horizon_y:, :, 0].astype(np.int16) + noise
        frame[horizon_y:, :, :] = np.clip(road_slice[:, :, None], 20, 180).astype(np.uint8)

        # Road curvature oscillation: delta_x = sin(omega * t) * amplitude
        curve_offset = math.sin(t * self.curve_freq) * 120.0
        center_x = self.width / 2.0 + curve_offset

        # Draw left and right lane boundaries
        num_points = 30
        y_pts = np.linspace(horizon_y + 10, self.height - 10, num_points)
        left_pts = []
        right_pts = []

        lane_half_bottom = self.width * 0.38
        lane_half_top = self.width * 0.05

        for y in y_pts:
            depth_ratio = (y - horizon_y) / (self.height - horizon_y)
            half_w = lane_half_top + (lane_half_bottom - lane_half_top) * (depth_ratio ** 1.5)
            # Quadratic curve bend
            bend = curve_offset * (depth_ratio ** 2)
            c_x = (self.width / 2.0) + bend
            left_pts.append((int(c_x - half_w), int(y)))
            right_pts.append((int(c_x + half_w), int(y)))

        # Draw solid left line (yellow/white)
        for i in range(len(left_pts) - 1):
            thickness = max(2, int(6 * (y_pts[i] - horizon_y) / (self.height - horizon_y)))
            cv2.line(frame, left_pts[i], left_pts[i + 1], (235, 235, 235), thickness)

        # Draw dashed right line (white)
        dash_period = 4
        for i in range(len(right_pts) - 1):
            if (i + int(t * 15)) % dash_period < 2:
                thickness = max(2, int(6 * (y_pts[i] - horizon_y) / (self.height - horizon_y)))
                cv2.line(frame, right_pts[i], right_pts[i + 1], (240, 240, 240), thickness)

        # Add realistic bridge / tree shadows across the road
        if self.add_shadows:
            shadow_y = int(horizon_y + (self.height - horizon_y) * (0.3 + 0.3 * math.sin(t * 0.5)))
            shadow_thickness = 45
            y_start = max(horizon_y, shadow_y - shadow_thickness)
            y_end = min(self.height, shadow_y + shadow_thickness)
            frame[y_start:y_end, :] = (frame[y_start:y_end, :].astype(np.float32) * 0.55).astype(np.uint8)

        # Add moving dynamic obstacle if requested
        if self.add_obstacles:
            # Lead car moving back and forth
            obs_depth = 0.5 + 0.3 * math.sin(t * 0.3)
            obs_y = int(horizon_y + (self.height - horizon_y) * obs_depth)
            obs_x = int(self.width / 2.0 + curve_offset * (obs_depth ** 2))
            obs_w = int(70 * obs_depth)
            obs_h = int(50 * obs_depth)
            top_left = (obs_x - obs_w // 2, obs_y - obs_h)
            bottom_right = (obs_x + obs_w // 2, obs_y)
            cv2.rectangle(frame, top_left, bottom_right, (30, 30, 180), -1)  # Red vehicle box
            # Taillights
            light_w = max(2, int(8 * obs_depth))
            light_h = max(2, int(6 * obs_depth))
            cv2.rectangle(frame, (top_left[0] + 4, bottom_right[1] - light_h - 4),
                          (top_left[0] + 4 + light_w, bottom_right[1] - 4), (0, 0, 255), -1)
            cv2.rectangle(frame, (bottom_right[0] - 4 - light_w, bottom_right[1] - light_h - 4),
                          (bottom_right[0] - 4, bottom_right[1] - 4), (0, 0, 255), -1)

        return frame, t_now


class ScreenCaptureManager:
    """High-level screen capture orchestrator with window tracking, auto-failover, and pacing."""

    def __init__(self, config: Optional[CaptureConfig] = None):
        self.config = config or CaptureConfig()
        self.window_finder = WindowFinder(self.config.window_title)
        self.backend: Optional[CaptureBackend] = None
        self._target_hwnd: Optional[int] = None
        self._initialize_backend()

    def _initialize_backend(self) -> None:
        """Initialize the selected capture backend with fallback cascading."""
        backend_name = self.config.backend.lower()

        # Try to locate target game window
        self._target_hwnd = self.window_finder.find_window(self.config.window_title)

        if backend_name == "mss" and HAS_MSS:
            roi_dict = None
            if self._target_hwnd:
                rect = self.window_finder.get_client_rect(self._target_hwnd)
                if rect:
                    roi_dict = rect.mss_dict
            self.backend = MssCaptureBackend(roi=roi_dict)

        elif backend_name == "win32" and sys.platform.startswith("win"):
            self.backend = Win32CaptureBackend(hwnd=self._target_hwnd)

        elif backend_name == "opencv":
            self.backend = OpenCvCaptureBackend(0)

        elif backend_name == "synthetic":
            self.backend = SyntheticCaptureBackend(
                width=self.config.capture_width,
                height=self.config.capture_height,
            )

        # Fallback cascade if chosen backend is unavailable
        if self.backend is None or not self.backend.is_available():
            if HAS_MSS:
                self.backend = MssCaptureBackend()
            elif sys.platform.startswith("win"):
                self.backend = Win32CaptureBackend()
            else:
                self.backend = SyntheticCaptureBackend(
                    width=self.config.capture_width,
                    height=self.config.capture_height,
                )

    def capture_frame(self) -> Tuple[np.ndarray, float]:
        """Capture frame, handle ROI cropping/resizing, and return (frame, timestamp) with auto-failover."""
        if self.backend is None or not self.backend.is_available():
            self._initialize_backend()

        try:
            frame, timestamp = self.backend.capture_frame()
        except Exception as err:
            # Cascading failover if the current backend fails
            if not isinstance(self.backend, SyntheticCaptureBackend):
                print(f"[!] Primary capture error ({err}). Failing over to Synthetic Track Generator...")
                self.backend = SyntheticCaptureBackend(
                    width=self.config.capture_width,
                    height=self.config.capture_height,
                    add_shadows=True,
                    add_obstacles=False,
                )
                frame, timestamp = self.backend.capture_frame()
            else:
                raise err

        # Apply custom ROI if configured
        if self.config.custom_roi:
            x, y, w, h = self.config.custom_roi
            h_f, w_f = frame.shape[:2]
            x_end = min(w_f, x + w)
            y_end = min(h_f, y + h)
            frame = frame[y:y_end, x:x_end]

        # Resize to target capture resolution if different
        target_w, target_h = self.config.capture_width, self.config.capture_height
        if frame.shape[1] != target_w or frame.shape[0] != target_h:
            frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        return frame, timestamp

    def get_target_hwnd(self) -> Optional[int]:
        """Return cached or refreshed game window handle."""
        if self._target_hwnd is None:
            self._target_hwnd = self.window_finder.find_window(self.config.window_title)
        return self._target_hwnd

    def release(self) -> None:
        """Release capture backend."""
        if self.backend:
            self.backend.release()
            self.backend = None

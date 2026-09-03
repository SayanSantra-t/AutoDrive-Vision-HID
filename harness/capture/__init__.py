"""Capture module initialization for AutoDrive PC test harness."""

from harness.capture.window_finder import WindowFinder, WindowRect
from harness.capture.screen_capture import (
    CaptureBackend,
    MssCaptureBackend,
    Win32CaptureBackend,
    OpenCvCaptureBackend,
    SyntheticCaptureBackend,
    ScreenCaptureManager,
)

__all__ = [
    "WindowFinder",
    "WindowRect",
    "CaptureBackend",
    "MssCaptureBackend",
    "Win32CaptureBackend",
    "OpenCvCaptureBackend",
    "SyntheticCaptureBackend",
    "ScreenCaptureManager",
]

"""Input Safety Guard and Emergency Release Watchdog for AutoDrive PC Harness.

Monitors foreground window focus, emergency stop keys, and loop heartbeats,
guaranteeing automatic key release on focus change, hang, or error.
"""

from __future__ import annotations

import time
import sys
from typing import Optional, Callable
from harness.input.direct_input import DirectInputDriver
from harness.capture.window_finder import WindowFinder


class InputSafetyGuard:
    """Safety supervisor that prevents stuck keys and enforces emergency stop policies."""

    def __init__(
        self,
        driver: DirectInputDriver,
        target_hwnd: Optional[int] = None,
        heartbeat_timeout_s: float = 0.50,
        on_safety_trip: Optional[Callable[[str], None]] = None,
    ):
        self.driver = driver
        self.target_hwnd = target_hwnd
        self.heartbeat_timeout_s = heartbeat_timeout_s
        self.on_safety_trip = on_safety_trip
        self.window_finder = WindowFinder()
        self._last_heartbeat = time.perf_counter()
        self._is_emergency_stopped = False
        self._focus_lost_count = 0
        self._heartbeat_timeout_count = 0

    def set_target_hwnd(self, hwnd: int) -> None:
        """Update target window handle to monitor."""
        self.target_hwnd = hwnd

    def heartbeat(self) -> None:
        """Record liveness heartbeat from main control loop."""
        self._last_heartbeat = time.perf_counter()

    def check_safety(self) -> bool:
        """Verify all safety conditions: focus, heartbeat, and emergency stop.

        Returns True if safe to drive, False if safety was tripped and keys released.
        """
        if self._is_emergency_stopped:
            self.driver.release_all()
            return False

        now = time.perf_counter()

        # 1. Heartbeat timeout check
        if (now - self._last_heartbeat) > self.heartbeat_timeout_s:
            self._heartbeat_timeout_count += 1
            self.driver.release_all()
            if self.on_safety_trip:
                self.on_safety_trip(f"Heartbeat timeout ({(now - self._last_heartbeat)*1000:.1f}ms)")
            return False

        # 2. Window focus check (if target_hwnd is specified)
        if self.target_hwnd and sys.platform.startswith("win"):
            if not self.window_finder.is_window_foreground(self.target_hwnd):
                self._focus_lost_count += 1
                self.driver.release_all()
                if self.on_safety_trip:
                    self.on_safety_trip("Target game window lost foreground focus")
                return False

        return True

    def trigger_emergency_stop(self, reason: str = "Manual Emergency Stop") -> None:
        """Immediately abort all keyboard actions and latch emergency stop flag."""
        self._is_emergency_stopped = True
        self.driver.release_all()
        if self.on_safety_trip:
            self.on_safety_trip(f"EMERGENCY STOP TRIGGERED: {reason}")

    def reset_emergency_stop(self) -> None:
        """Reset emergency stop state."""
        self._is_emergency_stopped = False
        self._last_heartbeat = time.perf_counter()

    @property
    def is_emergency_stopped(self) -> bool:
        return self._is_emergency_stopped

    def __enter__(self) -> InputSafetyGuard:
        self._last_heartbeat = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Guarantee all keys released when exiting context
        self.driver.release_all()

"""Window locator and ROI geometry helper for CarX Street and desktop windows.

Uses Win32 APIs (user32) with cross-platform fallback for headless testing.
"""

from __future__ import annotations

import sys
import ctypes
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class WindowRect:
    """Window bounding box and client area dimensions."""
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """Return (left, top, width, height) tuple."""
        return (self.left, self.top, self.width, self.height)

    @property
    def mss_dict(self) -> dict:
        """Return dictionary format expected by MSS grab."""
        return {
            "left": self.left,
            "top": self.top,
            "width": max(1, self.width),
            "height": max(1, self.height),
        }


class WindowFinder:
    """Locates target window by title substring and calculates client ROI coordinates."""

    def __init__(self, target_title: str = "CarX Street"):
        self.target_title = target_title
        self._is_windows = sys.platform.startswith("win")
        self._cached_hwnd: Optional[int] = None

    def find_window(self, title_substring: Optional[str] = None) -> Optional[int]:
        """Find window handle (HWND) matching title substring."""
        if not self._is_windows:
            return None

        search_str = (title_substring or self.target_title).lower()
        found_hwnds: List[Tuple[int, str]] = []

        try:
            user32 = ctypes.windll.user32

            # Ensure thread is attached to the interactive Default desktop
            try:
                hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
                if hdesk:
                    user32.SetThreadDesktop(hdesk)
            except Exception:
                pass

            # 1. Try exact FindWindow first
            exact_hwnd = user32.FindWindowW(None, title_substring or self.target_title)
            if exact_hwnd and user32.IsWindowVisible(exact_hwnd):
                self._cached_hwnd = exact_hwnd
                return exact_hwnd

            # 2. Try UnityWndClass (standard for CarX Street Unity engine)
            unity_hwnd = user32.FindWindowW("UnityWndClass", None)
            if unity_hwnd and user32.IsWindowVisible(unity_hwnd):
                self._cached_hwnd = unity_hwnd
                return unity_hwnd

            # 3. Fallback to EnumWindows with 64-bit HWND and LPARAM
            from ctypes import wintypes
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def callback(hwnd, extra):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        if search_str in title.lower():
                            found_hwnds.append((hwnd, title))
                return True

            user32.EnumWindows(WNDENUMPROC(callback), 0)

            if found_hwnds:
                self._cached_hwnd = found_hwnds[0][0]
                return self._cached_hwnd

        except Exception:
            pass

        return None

    def get_client_rect(self, hwnd: Optional[int] = None) -> Optional[WindowRect]:
        """Get the screen coordinates of the client area (excluding title bar / borders)."""
        target_hwnd = hwnd or self._cached_hwnd or self.find_window()
        if not target_hwnd or not self._is_windows:
            return None

        try:
            user32 = ctypes.windll.user32

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            client_rect = RECT()
            if not user32.GetClientRect(target_hwnd, ctypes.byref(client_rect)):
                return None

            pt = POINT(client_rect.left, client_rect.top)
            user32.ClientToScreen(target_hwnd, ctypes.byref(pt))

            width = client_rect.right - client_rect.left
            height = client_rect.bottom - client_rect.top

            if width <= 0 or height <= 0:
                return None

            return WindowRect(
                left=pt.x,
                top=pt.y,
                right=pt.x + width,
                bottom=pt.y + height,
                width=width,
                height=height,
            )

        except Exception:
            return None

    def get_window_rect(self, hwnd: Optional[int] = None) -> Optional[WindowRect]:
        """Get overall window bounding rectangle."""
        target_hwnd = hwnd or self._cached_hwnd or self.find_window()
        if not target_hwnd or not self._is_windows:
            return None

        try:
            user32 = ctypes.windll.user32

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT()
            if not user32.GetWindowRect(target_hwnd, ctypes.byref(rect)):
                return None

            width = rect.right - rect.left
            height = rect.bottom - rect.top

            return WindowRect(
                left=rect.left,
                top=rect.top,
                right=rect.right,
                bottom=rect.bottom,
                width=width,
                height=height,
            )

        except Exception:
            return None

    def is_window_foreground(self, hwnd: Optional[int] = None) -> bool:
        """Check if target window is currently the foreground active window."""
        if not self._is_windows:
            return True

        target_hwnd = hwnd or self._cached_hwnd or self.find_window()
        if not target_hwnd:
            return False

        try:
            fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
            return fg_hwnd == target_hwnd
        except Exception:
            return False

    def list_all_windows(self) -> List[Tuple[int, str]]:
        """List all visible top-level windows."""
        if not self._is_windows:
            return []

        results: List[Tuple[int, str]] = []
        try:
            user32 = ctypes.windll.user32
            enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)

            def callback(hwnd, extra):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        results.append((hwnd, buff.value))
                return True

            user32.EnumWindows(enum_proc(callback), 0)
        except Exception:
            pass

        return results

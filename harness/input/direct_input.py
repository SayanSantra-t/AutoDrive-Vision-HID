"""Win32 DirectInput Hardware Scancode Driver using SendInput.

Controls DirectX game engines (including CarX Street) via direct hardware scancodes
with zero Bluetooth latency, state diff tracking, and failsafe key release.
"""

from __future__ import annotations

import sys
import ctypes
from dataclasses import dataclass
from typing import Set, Dict, Optional, List

# DirectInput Hardware Scan Codes (Set 1 / DirectInput)
DIK_ESCAPE = 0x01
DIK_W = 0x11
DIK_R = 0x13
DIK_A = 0x1E
DIK_S = 0x1F
DIK_D = 0x20
DIK_SPACE = 0x39

# Win32 SendInput constants
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001


@dataclass
class KeyboardState:
    """Represents the binary state of driving keys."""
    key_w: bool = False      # Throttle
    key_a: bool = False      # Steer Left
    key_s: bool = False      # Brake / Decel
    key_d: bool = False      # Steer Right
    key_space: bool = False  # Handbrake / AEB

    def to_dict(self) -> Dict[str, bool]:
        return {
            "w": self.key_w,
            "a": self.key_a,
            "s": self.key_s,
            "d": self.key_d,
            "space": self.key_space,
        }

    def copy(self) -> KeyboardState:
        return KeyboardState(
            key_w=self.key_w,
            key_a=self.key_a,
            key_s=self.key_s,
            key_d=self.key_d,
            key_space=self.key_space,
        )


# Win32 Ctypes Structures
if sys.platform.startswith("win"):
    PUL = ctypes.POINTER(ctypes.c_ulong)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", PUL),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", ctypes.c_ulong),
            ("wParamL", ctypes.c_short),
            ("wParamH", ctypes.c_ushort),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", PUL),
        ]

    class _INPUTunion(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("union", _INPUTunion),
        ]


class DirectInputDriver:
    """Win32 SendInput keyboard driver using direct hardware scancodes."""

    def __init__(self, mock_mode: bool = False):
        self._is_windows = sys.platform.startswith("win") and not mock_mode
        self.mock_mode = mock_mode or not sys.platform.startswith("win")
        self._active_keys: Set[int] = set()
        self._state_history: List[KeyboardState] = []
        self._last_state: KeyboardState = KeyboardState()

    @property
    def active_keys(self) -> Set[int]:
        """Return set of currently pressed scancodes."""
        return set(self._active_keys)

    def _send_scancode(self, scancode: int, keyup: bool = False) -> bool:
        """Dispatch SendInput scancode event to Windows message queue."""
        if self.mock_mode or not self._is_windows:
            if keyup:
                self._active_keys.discard(scancode)
            else:
                self._active_keys.add(scancode)
            return True

        try:
            extra = ctypes.c_ulong(0)
            ii_ = _INPUTunion()
            flags = KEYEVENTF_SCANCODE
            if keyup:
                flags |= KEYEVENTF_KEYUP

            ii_.ki = KEYBDINPUT(0, scancode, flags, 0, ctypes.pointer(extra))
            x = INPUT(ctypes.c_ulong(INPUT_KEYBOARD), ii_)

            result = ctypes.windll.user32.SendInput(
                1, ctypes.pointer(x), ctypes.sizeof(x)
            )

            if keyup:
                self._active_keys.discard(scancode)
            else:
                self._active_keys.add(scancode)

            return result == 1
        except Exception:
            return False

    def press_key(self, scancode: int) -> bool:
        """Press down a key with scancode."""
        return self._send_scancode(scancode, keyup=False)

    def release_key(self, scancode: int) -> bool:
        """Release a pressed key."""
        return self._send_scancode(scancode, keyup=True)

    def apply_state(self, state: KeyboardState, target_hwnd: Optional[int] = None) -> None:
        """Apply desired KeyboardState, issuing only necessary press/release events.
        
        If target_hwnd is provided, keystrokes are ONLY sent if target_hwnd is the
        active foreground window. If focus is lost, all keys are instantly released.
        """
        if target_hwnd is not None and self._is_windows:
            try:
                fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
                if fg_hwnd != target_hwnd:
                    if self._active_keys:
                        self.release_all()
                    return
            except Exception:
                pass

        # Key W (Throttle)
        if state.key_w and DIK_W not in self._active_keys:
            self.press_key(DIK_W)
        elif not state.key_w and DIK_W in self._active_keys:
            self.release_key(DIK_W)

        # Key A (Steer Left)
        if state.key_a and DIK_A not in self._active_keys:
            self.press_key(DIK_A)
        elif not state.key_a and DIK_A in self._active_keys:
            self.release_key(DIK_A)

        # Key S (Brake)
        if state.key_s and DIK_S not in self._active_keys:
            self.press_key(DIK_S)
        elif not state.key_s and DIK_S in self._active_keys:
            self.release_key(DIK_S)

        # Key D (Steer Right)
        if state.key_d and DIK_D not in self._active_keys:
            self.press_key(DIK_D)
        elif not state.key_d and DIK_D in self._active_keys:
            self.release_key(DIK_D)

        # Key Space (Handbrake / AEB)
        if state.key_space and DIK_SPACE not in self._active_keys:
            self.press_key(DIK_SPACE)
        elif not state.key_space and DIK_SPACE in self._active_keys:
            self.release_key(DIK_SPACE)

        self._last_state = state.copy()
        self._state_history.append(self._last_state)
        if len(self._state_history) > 1000:
            self._state_history.pop(0)

    def get_current_state(self) -> KeyboardState:
        """Get current logical keyboard state."""
        return KeyboardState(
            key_w=DIK_W in self._active_keys,
            key_a=DIK_A in self._active_keys,
            key_s=DIK_S in self._active_keys,
            key_d=DIK_D in self._active_keys,
            key_space=DIK_SPACE in self._active_keys,
        )

    def release_all(self) -> None:
        """Release all active and tracked driving keys."""
        # Release all known keys
        keys_to_release = list(self._active_keys) + [
            DIK_W, DIK_A, DIK_S, DIK_D, DIK_SPACE
        ]
        for scancode in set(keys_to_release):
            self.release_key(scancode)

    def reset_car(self) -> None:
        """Tap 'R' key to reset vehicle position in CarX Street."""
        import time
        self.press_key(DIK_R)
        time.sleep(0.10)
        self.release_key(DIK_R)
        self._active_keys.clear()
        self._last_state = KeyboardState()

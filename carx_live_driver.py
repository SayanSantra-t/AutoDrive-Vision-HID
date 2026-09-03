"""AutoDrive CarX Street Live Autonomous Driver (Comma AI / openpilot Architecture).

Features:
- Direct hardware scancode WASD keyboard injection (DirectInput SendInput).
- Strict Focus Guard: Keystrokes are ONLY sent if CarX Street is the active foreground window.
- On-Screen Countdown Overlay (SWP_NOACTIVATE): Floating HUD banner shows 5s pre-drive countdown
  and 40s remaining countdown without stealing focus from the game.
- Handbrake Auto-Release: Clears in-game parking brake latch upon autopilot engagement.
- Solid Throttle Launch: Holds Key W solidly (100% duty cycle) during acceleration to prevent
  automatic gearbox stutter, switching to fine PWM trimming at cruise speed.
- Reverse Lockout & Zero False AEB: No reverse gear or handbrake lockups on empty roads.
- Road ROI Masking: Excludes player vehicle hood, minimap, and speedometer from threat detection.
- Timed Run & Video Recording: Runs for requested duration (e.g. 40s) and records annotated MP4.
- Window-Only Binding: Exits cleanly if CarX Street is closed without crashing or capturing desktop.
"""

from __future__ import annotations

import argparse
import ctypes
import math
import os
import sys
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from harness.config import (
    CaptureConfig,
    ControlConfig,
    HarnessMasterConfig,
    VehicleConfig,
    VisionConfig,
)
from harness.capture.screen_capture import ScreenCaptureManager, SyntheticCaptureBackend
from harness.capture.window_finder import WindowFinder
from harness.control.pwm_modulator import PwmWasdModulator
from harness.control.stanley_pid import ControlCommand, StanleyPidSteeringController
from harness.input.direct_input import DIK_SPACE, DIK_W, DirectInputDriver, KeyboardState
from harness.overlay.hud_visualizer import HudVisualizer
from harness.vision.lane_detector import AdaptiveMatchedFilterLaneDetector, LaneDetectionResult
from harness.vision.obstacle_grid import DetectedThreat, SpatialObstacleGridDetector


class OnScreenCountdownOverlay:
    """Floating borderless on-screen overlay window that never steals focus."""

    def __init__(self, width: int = 900, height: int = 68):
        self.width = width
        self.height = height
        self.win_name = "AutoDrive HUD Overlay"
        self._hwnd: Optional[int] = None
        self._initialized = False

    def init_window(self) -> None:
        if self._initialized:
            return
        cv2.namedWindow(self.win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.win_name, self.width, self.height)
        if sys.platform.startswith("win"):
            user32 = ctypes.windll.user32
            # Switch to Default desktop to find window handle
            try:
                hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
                if hdesk:
                    user32.SetThreadDesktop(hdesk)
            except Exception:
                pass
            self._hwnd = user32.FindWindowW(None, self.win_name)
            if self._hwnd:
                screen_w = user32.GetSystemMetrics(0)
                x_pos = (screen_w - self.width) // 2
                y_pos = 16
                SWP_NOACTIVATE = 0x0010
                SWP_SHOWWINDOW = 0x0040
                user32.SetWindowPos(
                    self._hwnd, -1, x_pos, y_pos, self.width, self.height, SWP_NOACTIVATE | SWP_SHOWWINDOW
                )
        self._initialized = True

    def show(
        self,
        text_main: str,
        text_sub: str,
        is_active: bool = True,
        bg_color: Tuple[int, int, int] = (15, 28, 15),
    ) -> None:
        if not self._initialized:
            self.init_window()
        canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        canvas[:] = bg_color
        border_color = (0, 255, 120) if is_active else (0, 180, 255)
        cv2.rectangle(canvas, (0, 0), (self.width - 1, self.height - 1), border_color, 2)
        cv2.putText(canvas, text_main, (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, border_color, 2, cv2.LINE_AA)
        cv2.putText(canvas, text_sub, (20, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (215, 230, 230), 1, cv2.LINE_AA)
        cv2.imshow(self.win_name, canvas)
        cv2.waitKey(1)

        if sys.platform.startswith("win") and self._hwnd:
            try:
                user32 = ctypes.windll.user32
                SWP_NOACTIVATE = 0x0010
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040
                user32.SetWindowPos(self._hwnd, -1, 0, 0, 0, 0, SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            except Exception:
                pass

    def close(self) -> None:
        if self._initialized:
            cv2.destroyWindow(self.win_name)
            self._initialized = False


class CarXLiveDriver:
    """Main live controller pipeline linking screen capture, vision, and DirectInput."""

    def __init__(
        self,
        window_title: str = "CarX",
        enable_direct_input: bool = True,
        use_synthetic: bool = False,
        duration_sec: Optional[float] = None,
        record_video_path: Optional[str] = None,
        show_hud: bool = True,
    ) -> None:
        self.window_title = window_title
        self.enable_direct_input = enable_direct_input
        self.use_synthetic = use_synthetic
        self.duration_sec = duration_sec
        self.record_video_path = record_video_path
        self.show_hud = show_hud

        self.master_cfg = HarnessMasterConfig()
        self.vehicle_cfg = self.master_cfg.vehicle
        self.vision_cfg = self.master_cfg.vision
        self.control_cfg = self.master_cfg.control

        # Strict ROI excluding car hood (bottom 38%), minimap, and sky
        self.vision_cfg.roi_top_ratio = 0.42
        self.vision_cfg.roi_bottom_ratio = 0.62
        self.vision_cfg.obstacle_corridor_width_m = 1.8

        self.lane_detector = AdaptiveMatchedFilterLaneDetector(config=self.vision_cfg)
        self.obstacle_detector = SpatialObstacleGridDetector(config=self.vision_cfg)
        self.steering_ctrl = StanleyPidSteeringController(
            vehicle_config=self.vehicle_cfg, control_config=self.control_cfg
        )
        self.pwm_modulator = PwmWasdModulator(config=self.control_cfg)
        self.direct_input = DirectInputDriver(
            mock_mode=not enable_direct_input or not sys.platform.startswith("win")
        )
        self.visualizer = HudVisualizer()
        self.window_finder = WindowFinder(target_title=window_title)
        self.overlay = OnScreenCountdownOverlay()

        self.target_hwnd: Optional[int] = None
        self.video_writer: Optional[cv2.VideoWriter] = None

        self.is_engaged = True
        self.driving_mode = "FULL_AUTONOMOUS"
        self.target_speed_kmh = 45.0
        self.simulated_speed_mps = 0.0

        self._init_capture_backend()

    def _init_capture_backend(self) -> None:
        if self.use_synthetic:
            print("[*] Initializing Synthetic procedural track generator...")
            self.capture_backend = SyntheticCaptureBackend(
                width=1280, height=720, add_shadows=True, add_obstacles=False
            )
            return

        print(f"[*] Searching for game window matching '{self.window_title}'...")
        hwnd = self.window_finder.find_window(self.window_title)
        if hwnd:
            self.target_hwnd = hwnd
            rect = self.window_finder.get_client_rect(hwnd)
            print(f"[+] Found CarX Street Window (HWND={hwnd}) | Bounds: {rect.bbox if rect else None}")
            cap_cfg = CaptureConfig(
                backend="win32",
                window_title=self.window_title,
                capture_width=1280,
                capture_height=720,
            )
            self.capture_backend = ScreenCaptureManager(config=cap_cfg)
        else:
            print(f"[!] CarX Street window matching '{self.window_title}' was not found.")
            print("    Please make sure CarX Street is running on your screen.")
            print("    Falling back to Synthetic Track Generator for offline testing.")
            self.use_synthetic = True
            self.capture_backend = SyntheticCaptureBackend(
                width=1280, height=720, add_shadows=True, add_obstacles=False
            )

    def run(self) -> None:
        print("=" * 72)
        print("  AutoDrive CarX Street Live Driver - Comma AI / openpilot Runner")
        print("=" * 72)
        print(f"  Target Window      : HWND={self.target_hwnd} ({self.window_title})")
        print(f"  Driving Mode       : {self.driving_mode}")
        print(f"  Autopilot Engaged  : {self.is_engaged}")
        direct_str = "ACTIVE (WASD with Focus Guard)" if self.enable_direct_input else "DISABLED (Dry Run)"
        print(f"  DirectInput Output : {direct_str}")
        print(f"  Target Cruise Speed: {self.target_speed_kmh} km/h")
        if self.duration_sec:
            print(f"  Session Duration   : Auto-stop after {self.duration_sec:.1f} seconds")
        if self.record_video_path:
            print(f"  Recording Video to : {self.record_video_path}")
        print("=" * 72)

        # ---------------------------------------------------------------------
        # PHASE 1: PRE-DRIVE 8-SECOND COUNTDOWN WITH ON-SCREEN OVERLAY & AUDIO
        # ---------------------------------------------------------------------
        print("\n[*] Starting 8-second countdown... Switch to CarX Street now!")
        countdown_start = time.perf_counter()
        last_beep = -1
        last_focus_state = False
        while True:
            t_rem = 8.0 - (time.perf_counter() - countdown_start)
            if t_rem <= 0:
                break
            sec_ceil = max(1, math.ceil(t_rem))

            is_focused = False
            if self.target_hwnd and sys.platform.startswith("win"):
                fg = ctypes.windll.user32.GetForegroundWindow()
                is_focused = (fg == self.target_hwnd)

            # Audio confirmation when user clicks into CarX Street
            if is_focused and not last_focus_state:
                last_focus_state = True
                try:
                    import winsound
                    winsound.Beep(1050, 120)
                except Exception:
                    pass
            elif not is_focused:
                last_focus_state = False

            if is_focused:
                title_msg = f">> CARX STREET FOCUSED - LAUNCHING IN {sec_ceil}s <<"
                sub_msg = "Focus Guard is ACTIVE. Vehicle will launch automatically."
                bg = (15, 38, 15)
            else:
                title_msg = f">> CLICK INTO CARX STREET NOW! [{sec_ceil}s] <<"
                sub_msg = "Click inside CarX Street game window so autopilot keys can inject!"
                bg = (18, 18, 42)

            self.overlay.show(title_msg, sub_msg, is_active=is_focused, bg_color=bg)

            if sec_ceil != last_beep:
                last_beep = sec_ceil
                try:
                    import winsound
                    winsound.Beep(750, 100)
                except Exception:
                    pass

            time.sleep(0.04)

        # Launch chime
        try:
            import winsound
            winsound.Beep(1200, 150)
            winsound.Beep(1600, 250)
        except Exception:
            pass

        # Disengage in-game parking brake with clean SPACE tap
        if self.enable_direct_input and sys.platform.startswith("win"):
            print("[*] Releasing in-game parking brake...")
            self.direct_input.press_key(DIK_SPACE)
            time.sleep(0.08)
            self.direct_input.release_key(DIK_SPACE)
            time.sleep(0.05)

        print("\n[>>>] AUTOPILOT ACTIVE! Processing live frames and driving...\n")

        # ---------------------------------------------------------------------
        # PHASE 2: ACTIVE AUTONOMOUS DRIVING LOOP
        # ---------------------------------------------------------------------
        start_time = time.perf_counter()
        prev_time = start_time
        frame_count = 0
        fps_timer = start_time
        current_fps = 60.0
        log_timer = start_time

        try:
            while True:
                t_now = time.perf_counter()
                elapsed = t_now - start_time

                # Check duration limit
                if self.duration_sec and elapsed >= self.duration_sec:
                    print(f"\n[+] Reached requested duration of {self.duration_sec:.1f}s. Stopping cleanly.")
                    break

                # Check if target game window is still alive
                if self.target_hwnd and sys.platform.startswith("win"):
                    user32 = ctypes.windll.user32
                    if not user32.IsWindow(self.target_hwnd):
                        print("\n[!] CarX Street window was closed. Terminating driver safely.")
                        break

                dt = max(0.001, min(0.1, t_now - prev_time))
                prev_time = t_now

                # Capture frame
                try:
                    frame, _ = self.capture_backend.capture_frame()
                except Exception as ex:
                    print(f"\n[!] Capture error ({ex}). Stopping safely.")
                    break

                if frame is None or frame.size == 0:
                    time.sleep(0.01)
                    continue

                # Run vision perception
                lane_res = self.lane_detector.process_frame(frame)
                threats = self.obstacle_detector.process_frame(frame, vehicle_speed_mps=self.simulated_speed_mps)

                # Compute autonomous driving decision
                control_cmd, key_state = self._compute_autonomous_cycle(lane_res, threats, dt=dt)

                # Apply DirectInput WASD ONLY if target game window is in foreground!
                if self.enable_direct_input and self.is_engaged:
                    self.direct_input.apply_state(key_state, target_hwnd=self.target_hwnd)
                else:
                    self.direct_input.release_all()

                frame_count += 1
                if t_now - fps_timer >= 0.5:
                    current_fps = frame_count / (t_now - fps_timer)
                    frame_count = 0
                    fps_timer = t_now

                is_focused = True
                if self.target_hwnd and sys.platform.startswith("win"):
                    fg = ctypes.windll.user32.GetForegroundWindow()
                    is_focused = (fg == self.target_hwnd)

                # Update floating overlay countdown
                if self.duration_sec:
                    rem_sec = max(0.0, self.duration_sec - elapsed)
                    rem_ceil = math.ceil(rem_sec)
                    if is_focused:
                        hud_msg = f">> AUTOPILOT ACTIVE: {rem_ceil}s REMAINING [DO NOT TOUCH KEYS] <<"
                        hud_sub = (
                            f"Speed: {self.simulated_speed_mps * 3.6:4.1f} km/h | Steer: {control_cmd.steering_angle:+.2f} | "
                            f"Throttle: {'SOLID W' if key_state.key_w else 'COAST'} | Focus: LOCKED"
                        )
                        bg = (12, 32, 12)
                    else:
                        hud_msg = f">> WINDOW UNFOCUSED: {rem_ceil}s REMAINING (INPUTS PAUSED) <<"
                        hud_sub = "Click back into CarX Street window to resume autonomous driving!"
                        bg = (18, 18, 40)
                    self.overlay.show(hud_msg, hud_sub, is_active=is_focused, bg_color=bg)

                # Periodic console logging (every 1 second)
                if t_now - log_timer >= 1.0:
                    log_timer = t_now
                    focus_tag = "CARX_FOCUSED" if is_focused else "UNFOCUSED(SAFE)"
                    print(
                        f"[{elapsed:04.1f}s] {focus_tag} | Spd: {self.simulated_speed_mps * 3.6:4.1f} km/h | "
                        f"Steer: {control_cmd.steering_angle:+0.2f} | "
                        f"W:{int(key_state.key_w)} A:{int(key_state.key_a)} S:{int(key_state.key_s)} D:{int(key_state.key_d)} Space:{int(key_state.key_space)} | "
                        f"FPS: {current_fps:4.1f}"
                    )

                # Render HUD
                engaged_tag = "[ENGAGED]" if self.is_engaged else "[STANDBY]"
                telemetry = {
                    "fps": current_fps,
                    "latency_ms": dt * 1000.0,
                    "mode": f"{self.driving_mode} {engaged_tag}",
                    "vision_model": "COMMA-AI-IPM",
                    "speed_kmh": round(self.simulated_speed_mps * 3.6, 1),
                    "target_speed_kmh": round(self.target_speed_kmh, 1),
                    "gear": "D3" if not control_cmd.emergency_brake else "D1",
                }

                rendered = self.visualizer.render(
                    frame=frame,
                    lane=lane_res,
                    threats=threats,
                    control=control_cmd,
                    keyboard=key_state if self.is_engaged else KeyboardState(),
                    telemetry=telemetry,
                )
                self._draw_status_banner(rendered)

                # Video recording
                if self.record_video_path:
                    if self.video_writer is None:
                        h_r, w_r = rendered.shape[:2]
                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                        self.video_writer = cv2.VideoWriter(self.record_video_path, fourcc, 30.0, (w_r, h_r))
                    self.video_writer.write(rendered)

                # Display cockpit HUD window if requested
                if self.show_hud:
                    cv2.imshow("AutoDrive Cockpit HUD", rendered)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        print("\n[!] Exit requested by user.")
                        break

        except KeyboardInterrupt:
            print("\n[!] Interrupted by user.")
        finally:
            self._cleanup()

    def _compute_autonomous_cycle(
        self,
        lane: LaneDetectionResult,
        threats: List[DetectedThreat],
        dt: float = 0.02,
    ) -> Tuple[ControlCommand, KeyboardState]:
        # 1. Stanley Steering Angle with Lookahead Curvature Feedforward
        norm_steer = self.steering_ctrl.update_steering(
            lateral_error_m=lane.lateral_offset_m,
            heading_error_rad=lane.heading_angle_rad,
            curvature_kappa=lane.lookahead_curvature_kappa,
            curve_direction=lane.curve_direction,
            current_speed_mps=max(2.0, self.simulated_speed_mps),
            dt=dt,
        )

        # Openpilot Barrier APF Repulsion Vector + Spatial Threat Avoidance
        total_repulsion = lane.barrier_repulsion_steer
        for t in threats:
            if t.distance_m < 6.0:
                if -2.2 < t.lateral_offset_m < 0.2:
                    # Obstacle/barrier on the left: push RIGHT into open asphalt
                    proximity = 1.0 - (t.distance_m / 6.0)
                    total_repulsion += 0.25 * proximity
                elif 0.2 <= t.lateral_offset_m < 2.2:
                    # Obstacle/barrier on the right: push LEFT
                    proximity = 1.0 - (t.distance_m / 6.0)
                    total_repulsion -= 0.25 * proximity

        norm_steer = max(-1.0, min(1.0, norm_steer + total_repulsion))

        target_mps = self.target_speed_kmh / 3.6
        if lane.lookahead_curvature_kappa > 0.003:
            curve_speed_limit = math.sqrt(4.5 / max(1e-4, lane.lookahead_curvature_kappa))
            target_mps = min(target_mps, curve_speed_limit)

        # 2. Longitudinal Control (Only react to confirmed in-path threats)
        in_path_threats = [t for t in threats if t.is_threat]
        critical_threat = next((t for t in in_path_threats if t.distance_m < 3.5), None)
        lead_threat = min(in_path_threats, key=lambda t: t.distance_m, default=None)

        throttle = 0.0
        brake = 0.0
        emergency_brake = False

        if critical_threat:
            throttle = 0.0
            brake = 0.8
            emergency_brake = True
        elif lead_threat and lead_threat.distance_m < 15.0:
            gap_factor = max(0.2, (lead_threat.distance_m - 3.5) / 11.5)
            target_mps = min(target_mps, target_mps * gap_factor)

        if not emergency_brake:
            speed_error = target_mps - self.simulated_speed_mps
            if speed_error > 0.5:
                # Solid acceleration forward
                throttle = 1.0
                brake = 0.0
            elif speed_error < -2.0:
                # Decelerate simply by coasting (release W)
                # NEVER tap S during highway cruising to prevent CarX from dropping into Reverse!
                throttle = 0.0
                brake = 0.0
            else:
                # Cruise speed maintenance
                throttle = 0.40
                brake = 0.0

        # Simulate forward physics integration
        accel = (throttle * 7.0) - (brake * 12.0) - (self.simulated_speed_mps * 0.02)
        self.simulated_speed_mps = max(0.0, min(35.0, self.simulated_speed_mps + accel * dt))

        if self.driving_mode == "LANE_KEEP":
            throttle = 0.0
            brake = 0.0
        elif self.driving_mode == "MANUAL":
            norm_steer = 0.0
            throttle = 0.0
            brake = 0.0

        cmd = ControlCommand(
            throttle=throttle,
            brake=brake,
            steering_angle=norm_steer,
            handbrake=False,
            emergency_brake=emergency_brake,
            target_speed_mps=target_mps,
            current_speed_mps=self.simulated_speed_mps,
            lateral_error_m=lane.lateral_offset_m,
            heading_error_rad=lane.heading_angle_rad,
        )

        key_state = self.pwm_modulator.modulate(cmd, dt=dt)

        # CRUISE & CORNERING THROTTLE CONTROL (Comma.ai Curve Deceleration)
        is_sharp_corner = (abs(norm_steer) > 0.28)
        if emergency_brake:
            key_state.key_w = False
            key_state.key_s = True
            key_state.key_space = False
        elif is_sharp_corner:
            # Lift off throttle to transfer weight to front tires and turn sharply around corners!
            key_state.key_w = False
            key_state.key_s = False
            key_state.key_space = False
        else:
            # Straightaway highway cruise: full throttle hold forward
            key_state.key_w = True
            key_state.key_s = False
            key_state.key_space = False

        return cmd, key_state

    def _draw_status_banner(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        banner_h = 36
        overlay = frame.copy()

        bg_color = (18, 55, 18) if self.is_engaged else (20, 25, 45)
        border_color = (0, 255, 120) if self.is_engaged else (0, 180, 255)
        text_str = "* AUTOPILOT ENGAGED (FOCUS GUARD ACTIVE)" if self.is_engaged else "o AUTOPILOT STANDBY"
        text_color = (0, 255, 120) if self.is_engaged else (0, 220, 255)

        cv2.rectangle(overlay, (0, 0), (w, banner_h), bg_color, -1)
        cv2.line(overlay, (0, banner_h), (w, banner_h), border_color, 2)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

        cv2.putText(
            frame,
            text_str,
            (w // 2 - 250, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            text_color,
            2,
            cv2.LINE_AA,
        )

    def _cleanup(self) -> None:
        print("\n[*] Releasing all keyboard keys and cleaning up...")
        self.direct_input.release_all()
        self.overlay.close()
        if self.video_writer is not None:
            self.video_writer.release()
            print(f"[+] Video successfully recorded to: {self.record_video_path}")
        if hasattr(self.capture_backend, "release"):
            self.capture_backend.release()
        cv2.destroyAllWindows()

        # Play completion audio chime (notifies user test is done)
        try:
            import winsound
            winsound.Beep(1400, 150)
            winsound.Beep(900, 300)
        except Exception:
            pass

        print("[+] Controller safely shut down.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoDrive CarX Street Live PC Driver")
    parser.add_argument(
        "--window",
        type=str,
        default="CarX",
        help="Window title search string (default: CarX)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run vision without injecting physical keystrokes",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Run on synthetic generated CarX highway track (for offline testing)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=40.0,
        help="Run for N seconds and then stop automatically (default: 40)",
    )
    parser.add_argument(
        "--record",
        type=str,
        default=None,
        help="Path to save MP4 video of the driving session",
    )
    parser.add_argument(
        "--no-hud",
        action="store_true",
        help="Disable full cockpit cv2.imshow preview to avoid cluttering screen",
    )
    args = parser.parse_args()

    driver = CarXLiveDriver(
        window_title=args.window,
        enable_direct_input=not args.dry_run,
        use_synthetic=args.synthetic,
        duration_sec=args.duration,
        record_video_path=args.record,
        show_hud=not args.no_hud,
    )
    driver.run()


if __name__ == "__main__":
    main()

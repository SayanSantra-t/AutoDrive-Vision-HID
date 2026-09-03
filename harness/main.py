"""AutoDrive-Vision-HID: Unified PC Test & Benchmarking Harness CLI.

Provides unified entry points for:
  1. Live Driving Mode (--drive): Real-time CarX Street screen capture,
     vision processing, Stanley+PID control, and Win32 DirectInput keystroke dispatch.
  2. Mobile SoC Emulation Mode (--profile snapdragon_750g|dimensity_8020):
     Enforces hardware compute budgets (25ms / 16ms) and memory caps (180MB / 250MB).
  3. Automated Benchmark Suite (--benchmark):
     Instruments all 6 pipeline stages and updates PERFORMANCE_LOG.md.
  4. Video / Synthetic Replay Mode (--video / --scenario):
     Evaluates vision and control against recorded or generated track datasets.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# Config and Core Subsystem Modules
from harness.config import (
    CaptureConfig,
    ControlConfig,
    EmulationConfig,
    HarnessMasterConfig,
    VehicleConfig,
    VisionConfig,
)
from harness.capture.screen_capture import (
    CaptureBackend,
    ScreenCaptureManager,
    SyntheticCaptureBackend,
)
from harness.vision import (
    DetectedThreat,
    LaneDetectionResult,
    VisionPipeline,
)
from harness.control import (
    ControlCommand,
    DrivingController,
    PwmWasdModulator,
)
from harness.input.direct_input import (
    DirectInputDriver,
    KeyboardState,
)

# Overlay and Benchmark Modules
from harness.benchmark.ledger_writer import LedgerWriter, update_performance_log
from harness.benchmark.profiler_suite import (
    PROFILES,
    BenchmarkResult,
    PipelineProfiler,
    ProfilerSuite,
)
from harness.overlay.hud_visualizer import (
    HudColors,
    HudVisualizer,
    HudVisualizerConfig,
)


def parse_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for AutoDrive PC test harness."""
    parser = argparse.ArgumentParser(
        prog="autodrive",
        description="AutoDrive PC Test & Benchmarking Harness for CarX Street",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Core Modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--drive",
        action="store_true",
        help="Run live interactive driving loop with screen capture and DirectInput",
    )
    mode_group.add_argument(
        "--benchmark",
        action="store_true",
        help="Run automated benchmark suite across mobile profiles and update PERFORMANCE_LOG.md",
    )

    # Hardware Emulation Profile
    parser.add_argument(
        "--profile",
        type=str,
        default="snapdragon_750g",
        choices=["snapdragon_750g", "dimensity_8020", "pc_native"],
        help="Mobile SoC emulation profile target",
    )

    # Window and Capture Source
    parser.add_argument(
        "--window",
        type=str,
        default="CarX",
        help="Window title substring to target for capture (e.g. 'CarX', 'CarX Street')",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="synthetic",
        choices=["window", "screen", "synthetic", "video", "camera"],
        help="Frame acquisition source",
    )
    parser.add_argument(
        "--video",
        type=str,
        default=None,
        help="Path to recorded video file for replay mode",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="curved_highway",
        choices=["straight_highway", "curved_highway", "shadow_bridge", "traffic_obstacle"],
        help="Synthetic track scenario to simulate when source is 'synthetic'",
    )

    # Visualization & Display
    parser.add_argument(
        "--overlay",
        dest="overlay",
        action="store_true",
        default=True,
        help="Display OpenCV real-time HUD visualizer window",
    )
    parser.add_argument(
        "--no-overlay",
        dest="overlay",
        action="store_false",
        help="Disable OpenCV visualizer window (headless execution)",
    )

    # Execution Controls & Safety
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run vision and controller without injecting physical DirectInput keystrokes",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=300,
        help="Number of frames to process in benchmark or replay mode",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Maximum duration in seconds for live driving mode (0 = indefinite until 'q')",
    )
    parser.add_argument(
        "--log-ledger",
        action="store_true",
        default=False,
        help="Automatically write benchmark and driving results to PERFORMANCE_LOG.md",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to save annotated video output (e.g. 'output.mp4')",
    )

    return parser.parse_args(args)


class AutoDriveHarnessRunner:
    """Master orchestrator executing live driving, emulation, and benchmark workflows."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.profile_key = args.profile
        self.profiler = PipelineProfiler(self.profile_key)
        self.visualizer = HudVisualizer() if args.overlay else None
        self._running = False
        self._video_writer: Optional[cv2.VideoWriter] = None

        # Master configuration
        self.master_config = HarnessMasterConfig()

        # Instantiate genuine core subsystems
        self.vision_pipeline = VisionPipeline(config=self.master_config.vision)
        self.driving_controller = DrivingController(
            vehicle_config=self.master_config.vehicle,
            control_config=self.master_config.control,
        )
        self.pwm_modulator = PwmWasdModulator(
            config=self.master_config.control
        )
        self.direct_input = DirectInputDriver(
            mock_mode=self.args.dry_run or not sys.platform.startswith("win")
        )

        # Initialize screen capture backend
        if self.args.source == "synthetic":
            add_obs = (self.args.scenario == "traffic_obstacle")
            add_shd = (self.args.scenario == "shadow_bridge")
            self.capture_backend: CaptureBackend = SyntheticCaptureBackend(
                width=self.master_config.capture.capture_width,
                height=self.master_config.capture.capture_height,
                add_shadows=add_shd,
                add_obstacles=add_obs,
            )
        else:
            cap_config = CaptureConfig(
                backend=self.args.source,
                window_title=self.args.window,
                capture_width=self.master_config.capture.capture_width,
                capture_height=self.master_config.capture.capture_height,
            )
            self.capture_backend = ScreenCaptureManager(config=cap_config)

    def run(self) -> int:
        """Execute selected mode based on CLI arguments."""
        print("=" * 70)
        print(" AutoDrive PC Test & Benchmarking Harness for CarX Street")
        print("=" * 70)
        print(f" Mode: {'BENCHMARK' if self.args.benchmark else 'LIVE DRIVING'}")
        print(f" Target SoC Profile: {PROFILES.get(self.profile_key, PROFILES['pc_native']).name}")
        print(f" Frame Source: {self.args.source} | Visualizer Overlay: {self.args.overlay}")
        print(f" DirectInput Injection: {'DISABLED (Dry-Run)' if self.args.dry_run else 'ACTIVE'}")
        print("=" * 70)

        if self.args.benchmark:
            return self.run_benchmark_mode()
        else:
            return self.run_driving_mode()

    def run_benchmark_mode(self) -> int:
        """Execute automated benchmark across mobile profiles and update PERFORMANCE_LOG.md."""
        print("\n[*] Starting Automated Multi-Profile Benchmark Suite...")
        suite = ProfilerSuite()
        results = suite.run_all_profiles(
            num_frames_per_profile=self.args.frames,
            scenario_name=self.args.scenario,
        )

        print("\n" + "=" * 70)
        print(" BENCHMARK RESULTS SUMMARY")
        print("=" * 70)
        for key, res in results.items():
            print(f"\n[+] Profile: {res.profile_name}")
            print(f"    Target Latency Budget: <= {res.target_budget_ms:.1f} ms ({res.target_fps:.0f} FPS)")
            print(f"    Measured Latency: Avg={res.overall_latency.avg_ms:.2f}ms | p50={res.overall_latency.median_ms:.2f}ms | p95={res.overall_latency.p95_ms:.2f}ms | p99={res.overall_latency.p99_ms:.2f}ms")
            print(f"    Memory RSS: Peak={res.memory.peak_rss_mb:.1f} MB (Limit: <= {res.memory.budget_limit_mb:.0f} MB)")
            print(f"    Budget Adherence: {res.budget_compliance_pct:.1f}%")
            print(f"    Steering Oscillation Index: {res.control.steering_oscillation_index:.4f}")
            print(f"    Status: {'PASSED' if res.passed_all_criteria else 'FAILED'}")

        # Update PERFORMANCE_LOG.md
        ledger_writer = LedgerWriter()
        log_file = ledger_writer.write_ledger(results=results)
        print(f"\n[+] PERFORMANCE_LOG.md successfully updated at: {log_file}")
        print("=" * 70)
        return 0

    def run_driving_mode(self) -> int:
        """Execute live driving loop with frame acquisition, vision, control, and overlay."""
        print("\n[*] Initializing Live Driving Loop...")
        print("[*] Press 'q' or ESC in the overlay window to exit cleanly.")

        self._running = True
        frame_idx = 0
        start_time = time.perf_counter()
        prev_time = start_time

        try:
            while self._running:
                now_time = time.perf_counter()
                dt = max(0.005, min(0.10, now_time - prev_time))
                prev_time = now_time

                self.profiler.start_frame()

                # 1. Capture Stage
                self.profiler.start_stage("capture")
                frame, _ = self.capture_backend.capture_frame()
                self.profiler.end_stage("capture")

                # 2. Preprocess Stage
                self.profiler.start_stage("preprocess")
                if frame.ndim == 2:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                elif frame.shape[2] == 4:
                    frame = frame[:, :, :3]
                self.profiler.end_stage("preprocess")

                # 3. Lane Tracking Stage
                self.profiler.start_stage("lane_tracking")
                lane_info = self._process_lane_geometry(frame)
                self.profiler.end_stage("lane_tracking")

                # 4. Object Detection Stage
                self.profiler.start_stage("object_detect")
                threats = self._process_obstacles(frame)
                self.profiler.end_stage("object_detect")

                # 5. Controller Stage
                self.profiler.start_stage("controller")
                control_cmd, keyboard_state = self._compute_control(lane_info, threats, dt=dt)
                self.profiler.end_stage("controller")

                # 6. DirectInput Dispatch Stage
                self.profiler.start_stage("input_dispatch")
                if not self.args.dry_run:
                    self._dispatch_direct_input(keyboard_state)
                self.profiler.end_stage("input_dispatch")

                # End frame profiling
                frame_ms = self.profiler.end_frame(
                    steering_angle=control_cmd.steering_angle,
                    is_aeb=control_cmd.emergency_brake,
                )

                # 7. Render Real-time AR HUD Visualizer
                if self.visualizer is not None:
                    telemetry = {
                        "fps": 1000.0 / max(1.0, frame_ms),
                        "latency_ms": frame_ms,
                        "mode": "FULL_AUTONOMOUS",
                        "vision_model": "MATCHED-IPM",
                        "speed_kmh": round(control_cmd.current_speed_mps * 3.6, 1),
                        "target_speed_kmh": round(control_cmd.target_speed_mps * 3.6, 1),
                        "gear": "D3" if not control_cmd.emergency_brake else "D1",
                    }
                    rendered = self.visualizer.render(
                        frame=frame,
                        lane=lane_info,
                        threats=threats,
                        control=control_cmd,
                        keyboard=keyboard_state,
                        telemetry=telemetry,
                        profile_stats=self.profiler.spec,
                    )

                    cv2.imshow("AutoDrive CarX Street HUD", rendered)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):  # 'q' or ESC
                        print("\n[!] User requested exit.")
                        break

                frame_idx += 1

                # Duration limit check
                if self.args.duration > 0 and (time.perf_counter() - start_time) >= self.args.duration:
                    print(f"\n[!] Duration limit ({self.args.duration}s) reached.")
                    break

                # Frame limit check (if specified and not indefinite)
                if self.args.frames > 0 and frame_idx >= self.args.frames:
                    print(f"\n[!] Target frame count ({self.args.frames}) reached.")
                    break

        except KeyboardInterrupt:
            print("\n[!] KeyboardInterrupt received. Shutting down gracefully...")

        finally:
            self._cleanup()

        # Compute and display session summary
        result = self.profiler.compute_results()
        print("\n" + "=" * 70)
        print(" SESSION EXECUTION SUMMARY")
        print("=" * 70)
        print(f" Total Frames: {result.total_frames} | Elapsed Time: {result.duration_sec:.2f}s")
        print(f" Effective FPS: {result.effective_fps:.1f} (Target: {result.target_fps:.0f} FPS)")
        print(f" Average Latency: {result.overall_latency.avg_ms:.2f} ms | p95: {result.overall_latency.p95_ms:.2f} ms")
        print(f" Peak Memory RSS: {result.memory.peak_rss_mb:.1f} MB (Limit: {result.memory.budget_limit_mb:.0f} MB)")
        print(f" Steering Oscillation Index: {result.control.steering_oscillation_index:.4f}")
        print("=" * 70)

        if self.args.log_ledger:
            ledger_writer = LedgerWriter()
            ledger_writer.write_ledger(results={self.profile_key: result})
            print("[+] Updated PERFORMANCE_LOG.md with live session metrics.")

        return 0

    def _process_lane_geometry(self, frame: np.ndarray) -> LaneDetectionResult:
        """Extract lane curvature and lateral offset using genuine AdaptiveMatchedFilterLaneDetector."""
        return self.vision_pipeline.lane_detector.process_frame(frame)

    def _process_obstacles(self, frame: np.ndarray, vehicle_speed_mps: float = 18.0) -> List[DetectedThreat]:
        """Extract detected obstacles and threat vectors using genuine SpatialObstacleGridDetector."""
        return self.vision_pipeline.obstacle_detector.process_frame(frame, vehicle_speed_mps=vehicle_speed_mps)

    def _compute_control(
        self,
        lane_info: LaneDetectionResult,
        threats: List[DetectedThreat],
        dt: float = 0.02,
    ) -> Tuple[ControlCommand, KeyboardState]:
        """Compute Stanley + PID steering, speed regulation, and 80ms WASD PWM keys."""
        control_cmd = self.driving_controller.update(lane_info, threats, dt=dt)
        keyboard_state = self.pwm_modulator.modulate(control_cmd, dt=dt)
        return control_cmd, keyboard_state

    def _dispatch_direct_input(self, keyboard_state: KeyboardState) -> None:
        """Dispatch hardware scancodes via Win32 DirectInput driver."""
        self.direct_input.apply_state(keyboard_state)

    def _cleanup(self) -> None:
        """Clean up OpenCV windows, release video writers, and release all DirectInput keys."""
        self.direct_input.release_all()
        if hasattr(self.capture_backend, "release"):
            self.capture_backend.release()
        if self.visualizer is not None:
            cv2.destroyAllWindows()
        if self._video_writer is not None:
            self._video_writer.release()


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parsed_args = parse_arguments(args)
    runner = AutoDriveHarnessRunner(parsed_args)
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())

"""Mobile Compute Constraint Throttler, Core Affinity, and Thermal Soak Engine.

Accurately simulates ARM SoC IPC scaling, core constriction, thermal clock degradation,
and sub-millisecond frame pacing for Snapdragon 750G and Dimensity 8020 profiles.
"""

from __future__ import annotations

import sys
import time
import math
import ctypes
from dataclasses import dataclass, field
from typing import Dict, Optional, List
import psutil

from harness.profiler.mobile_profile import MobileDeviceProfile, PROFILE_SNAPDRAGON_750G


@dataclass
class FrameProfileStats:
    """Detailed stage-by-stage latency, memory, and thermal statistics for a frame."""
    frame_index: int
    timestamp_sec: float
    stage_durations_ms: Dict[str, float] = field(default_factory=dict)
    total_compute_ms: float = 0.0
    simulated_mobile_ms: float = 0.0
    throttle_delay_ms: float = 0.0
    effective_frame_time_ms: float = 0.0
    instant_fps: float = 0.0
    rss_memory_mb: float = 0.0
    device_temperature_c: float = 28.0
    is_budget_compliant: bool = True
    is_memory_compliant: bool = True

    def to_dict(self) -> dict:
        return {
            "frame_index": self.frame_index,
            "timestamp_sec": round(self.timestamp_sec, 4),
            "stages": {k: round(v, 3) for k, v in self.stage_durations_ms.items()},
            "compute_ms": round(self.total_compute_ms, 3),
            "simulated_ms": round(self.simulated_mobile_ms, 3),
            "delay_ms": round(self.throttle_delay_ms, 3),
            "frame_time_ms": round(self.effective_frame_time_ms, 3),
            "fps": round(self.instant_fps, 1),
            "rss_mb": round(self.rss_memory_mb, 2),
            "temp_c": round(self.device_temperature_c, 1),
            "budget_ok": self.is_budget_compliant,
            "memory_ok": self.is_memory_compliant,
        }


class MobileThrottler:
    """Emulates mobile SoC compute throughput, core affinity, thermal throttling, and frame pacing."""

    def __init__(
        self,
        profile: Optional[MobileDeviceProfile] = None,
        enforce_affinity: bool = True,
        enforce_throttling: bool = True,
        thermal_simulation: bool = True,
    ):
        self.profile = profile or PROFILE_SNAPDRAGON_750G
        self.enforce_affinity = enforce_affinity
        self.enforce_throttling = enforce_throttling
        self.thermal_simulation = thermal_simulation

        self._process = psutil.Process()
        self._start_time = time.perf_counter()
        self._frame_start_time = time.perf_counter()
        self._stage_start_time = time.perf_counter()
        self._last_frame_end_time = time.perf_counter()

        self._current_frame_index = 0
        self._stage_timings: Dict[str, float] = {}

        self._winmm = None
        self._setup_timing_resolution()
        if self.enforce_affinity:
            self._apply_core_affinity()

    def _setup_timing_resolution(self) -> None:
        """Enable 1ms timer resolution on Windows."""
        if sys.platform.startswith("win"):
            try:
                self._winmm = ctypes.windll.winmm
                self._winmm.timeBeginPeriod(1)
            except Exception:
                pass

    def _apply_core_affinity(self) -> None:
        """Pin process threads to the target number of CPU cores."""
        try:
            available_cores = psutil.cpu_count(logical=True) or 4
            num_cores = min(self.profile.cpu_cores, available_cores)
            target_cores = list(range(num_cores))
            self._process.cpu_affinity(target_cores)
        except Exception:
            # Affinity setting may be restricted on some platforms
            pass

    def start_frame(self) -> None:
        """Mark the beginning of a frame execution cycle."""
        self._current_frame_index += 1
        self._stage_timings.clear()
        self._frame_start_time = time.perf_counter()
        self._stage_start_time = self._frame_start_time

    def record_stage(self, stage_name: str) -> float:
        """Record the elapsed time for the current stage in milliseconds."""
        now = time.perf_counter()
        duration_ms = (now - self._stage_start_time) * 1000.0
        self._stage_timings[stage_name] = duration_ms
        self._stage_start_time = now
        return duration_ms

    def get_current_temperature(self) -> float:
        """Compute current simulated SoC junction temperature via exponential soak curve."""
        if not self.thermal_simulation:
            return self.profile.ambient_temp_c

        elapsed_sec = time.perf_counter() - self._start_time
        t_amb = self.profile.ambient_temp_c
        t_max = self.profile.steady_state_temp_c
        tau = max(1.0, self.profile.thermal_tau_sec)

        temp = t_amb + (t_max - t_amb) * (1.0 - math.exp(-elapsed_sec / tau))
        return temp

    def get_effective_scale_factor(self, current_temp_c: float) -> float:
        """Calculate combined clock and thermal throttling scale factor."""
        base_scale = self.profile.scale_factor
        if not self.thermal_simulation:
            return base_scale

        t_thresh = self.profile.throttle_temp_threshold_c
        t_max = self.profile.steady_state_temp_c

        if current_temp_c <= t_thresh:
            thermal_penalty = 0.0
        else:
            delta = min(1.0, (current_temp_c - t_thresh) / max(0.1, (t_max - t_thresh)))
            thermal_penalty = delta * self.profile.thermal_max_slowdown

        return base_scale * (1.0 + thermal_penalty)

    def _sleep_precise(self, target_seconds: float) -> None:
        """Sub-millisecond spin-sleep loop for exact hardware timing alignment."""
        if target_seconds <= 0:
            return

        t_start = time.perf_counter()
        # Coarse sleep for the bulk duration (>2ms) to release CPU
        if target_seconds > 0.002:
            time.sleep(target_seconds - 0.0015)

        # Fine-grained busy-wait for remaining microseconds
        while (time.perf_counter() - t_start) < target_seconds:
            pass

    def end_frame_and_throttle(self) -> FrameProfileStats:
        """Finish frame compute, inject simulated mobile delay, and return stats."""
        t_compute_end = time.perf_counter()
        host_compute_sec = t_compute_end - self._frame_start_time
        host_compute_ms = host_compute_sec * 1000.0

        current_temp = self.get_current_temperature()
        scale_factor = self.get_effective_scale_factor(current_temp)

        simulated_mobile_sec = host_compute_sec * scale_factor
        simulated_mobile_ms = simulated_mobile_sec * 1000.0

        target_frame_period_sec = 1.0 / max(1.0, self.profile.target_fps)
        throttle_delay_sec = 0.0

        if self.enforce_throttling:
            # Inject difference between simulated mobile execution and host execution
            delay_needed = max(0.0, simulated_mobile_sec - host_compute_sec)
            # Ensure frame pacing respects target FPS ceiling
            elapsed_total = (time.perf_counter() - self._last_frame_end_time)
            remaining_to_pace = max(0.0, target_frame_period_sec - elapsed_total)
            throttle_delay_sec = max(delay_needed, remaining_to_pace)

            self._sleep_precise(throttle_delay_sec)

        t_frame_end = time.perf_counter()
        effective_frame_time_sec = t_frame_end - self._frame_start_time
        effective_frame_time_ms = effective_frame_time_sec * 1000.0
        self._last_frame_end_time = t_frame_end

        instant_fps = 1.0 / max(1e-5, effective_frame_time_sec)

        # Query process RSS
        try:
            rss_mb = self._process.memory_info().rss / (1024.0 * 1024.0)
        except Exception:
            rss_mb = 0.0

        is_budget_ok = simulated_mobile_ms <= self.profile.target_budget_ms
        is_memory_ok = rss_mb <= self.profile.max_ram_mb

        stats = FrameProfileStats(
            frame_index=self._current_frame_index,
            timestamp_sec=t_frame_end - self._start_time,
            stage_durations_ms=dict(self._stage_timings),
            total_compute_ms=host_compute_ms,
            simulated_mobile_ms=simulated_mobile_ms,
            throttle_delay_ms=throttle_delay_sec * 1000.0,
            effective_frame_time_ms=effective_frame_time_ms,
            instant_fps=instant_fps,
            rss_memory_mb=rss_mb,
            device_temperature_c=current_temp,
            is_budget_compliant=is_budget_ok,
            is_memory_compliant=is_memory_ok,
        )

        return stats

    def close(self) -> None:
        """Release timer resources."""
        if self._winmm:
            try:
                self._winmm.timeEndPeriod(1)
            except Exception:
                pass
            self._winmm = None

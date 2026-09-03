"""AutoDrive PC Test & Benchmarking Harness for CarX Street.

Integrates real-time screen capture, mobile SoC hardware emulation,
high-precision computer vision, smooth PWM keyboard control, and
automated performance tracking.
"""

from harness.benchmark import (
    BenchmarkResult,
    LedgerWriter,
    MobileProfileSpec,
    PipelineProfiler,
    ProfilerSuite,
    update_performance_log,
)
from harness.overlay import (
    HudColors,
    HudVisualizer,
    HudVisualizerConfig,
)

__version__ = "1.0.0"
__all__ = [
    "BenchmarkResult",
    "HudColors",
    "HudVisualizer",
    "HudVisualizerConfig",
    "LedgerWriter",
    "MobileProfileSpec",
    "PipelineProfiler",
    "ProfilerSuite",
    "update_performance_log",
]

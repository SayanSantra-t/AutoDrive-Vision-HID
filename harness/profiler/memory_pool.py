"""Zero-Allocation Frame Buffer Pool and RSS Memory Watchdog.

Maintains pre-allocated static numpy memory arenas to avoid GC jitter
and enforces mobile RAM ceilings (<=180MB for Profile A, <=250MB for Profile B).
"""

from __future__ import annotations

import gc
import psutil
from typing import Dict, List, Tuple, Optional
import numpy as np


class FrameBufferPool:
    """Pre-allocated zero-allocation buffer pool for computer vision arrays."""

    def __init__(self, initial_specs: Optional[List[Tuple[Tuple[int, ...], np.dtype, int]]] = None):
        # Pool storage: key = (shape, dtype) -> List[np.ndarray]
        self._pool: Dict[Tuple[Tuple[int, ...], str], List[np.ndarray]] = {}
        self._in_use: Dict[int, Tuple[Tuple[int, ...], str]] = {}
        self._total_allocated_bytes = 0

        if initial_specs:
            for shape, dtype, count in initial_specs:
                self.preallocate(shape, dtype, count)

    def preallocate(self, shape: Tuple[int, ...], dtype: np.dtype, count: int = 4) -> None:
        """Pre-allocate fixed numpy buffers in memory arena."""
        key = (shape, np.dtype(dtype).name)
        if key not in self._pool:
            self._pool[key] = []

        for _ in range(count):
            buf = np.zeros(shape, dtype=dtype)
            self._pool[key].append(buf)
            self._total_allocated_bytes += buf.nbytes

    def acquire(self, shape: Tuple[int, ...], dtype: np.dtype = np.uint8) -> np.ndarray:
        """Acquire a reusable buffer from the pool without triggering heap allocation."""
        key = (shape, np.dtype(dtype).name)
        if key not in self._pool or not self._pool[key]:
            # Allocate on-demand if pool exhausted
            buf = np.zeros(shape, dtype=dtype)
            self._total_allocated_bytes += buf.nbytes
            self._in_use[id(buf)] = key
            return buf

        buf = self._pool[key].pop()
        self._in_use[id(buf)] = key
        return buf

    def release(self, buf: np.ndarray) -> None:
        """Return a buffer back to the reusable pool."""
        buf_id = id(buf)
        if buf_id in self._in_use:
            key = self._in_use.pop(buf_id)
            if key not in self._pool:
                self._pool[key] = []
            self._pool[key].append(buf)

    @property
    def total_allocated_mb(self) -> float:
        """Total memory consumed by pre-allocated buffer pools in Megabytes."""
        return self._total_allocated_bytes / (1024.0 * 1024.0)

    def clear(self) -> None:
        """Clear all buffers and trigger garbage collection."""
        self._pool.clear()
        self._in_use.clear()
        self._total_allocated_bytes = 0
        gc.collect()


class MemoryWatchdog:
    """Monitors process Resident Set Size (RSS) and enforces target mobile device caps."""

    def __init__(
        self,
        max_budget_mb: float = 180.0,
        warning_threshold_ratio: float = 0.85,
    ):
        self.max_budget_mb = max_budget_mb
        self.warning_threshold_ratio = warning_threshold_ratio
        self.warning_mb = max_budget_mb * warning_threshold_ratio
        self._process = psutil.Process()

        self.samples_mb: List[float] = []
        self.warning_count = 0
        self.breach_count = 0

    def sample_memory_rss_mb(self) -> float:
        """Sample current process RSS memory in Megabytes."""
        try:
            mem_info = self._process.memory_info()
            rss_mb = mem_info.rss / (1024.0 * 1024.0)
        except Exception:
            rss_mb = 0.0

        self.samples_mb.append(rss_mb)
        if len(self.samples_mb) > 2000:
            self.samples_mb.pop(0)

        if rss_mb > self.max_budget_mb:
            self.breach_count += 1
        elif rss_mb > self.warning_mb:
            self.warning_count += 1

        return rss_mb

    def is_within_budget(self) -> bool:
        """Return True if current memory usage is within budget ceiling."""
        if not self.samples_mb:
            self.sample_memory_rss_mb()
        return self.samples_mb[-1] <= self.max_budget_mb

    def get_summary(self) -> Dict[str, float]:
        """Return min, average, and peak RSS statistics."""
        if not self.samples_mb:
            current = self.sample_memory_rss_mb()
            return {"min_mb": current, "avg_mb": current, "peak_mb": current, "breaches": 0}

        return {
            "min_mb": round(min(self.samples_mb), 2),
            "avg_mb": round(sum(self.samples_mb) / len(self.samples_mb), 2),
            "peak_mb": round(max(self.samples_mb), 2),
            "budget_mb": self.max_budget_mb,
            "warning_count": self.warning_count,
            "breach_count": self.breach_count,
        }

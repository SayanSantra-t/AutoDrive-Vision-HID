"""Mobile Hardware Profile Definitions for Snapdragon 750G and Dimensity 8020 SoCs.

Emulates CPU core constraints, compute scale factors, memory ceilings,
and thermal soak curves for Samsung Galaxy F23 5G and Infinix Zero 30 5G targets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Dict


@dataclass
class MobileDeviceProfile:
    """Hardware specification and constraint profile for target mobile devices."""
    name: str
    target_budget_ms: float        # Frame inference budget (<=25ms for 750G, <=16ms for 8020)
    max_ram_mb: float              # Process RSS / Heap ceiling (<=180MB for 750G, <=250MB for 8020)
    cpu_cores: int                 # Big performance cores to emulate (2 vs 4)
    scale_factor: float            # x86 to ARM IPC/clock scaling factor
    thermal_tau_sec: float         # First-order thermal time constant
    thermal_max_slowdown: float    # Max clock degradation under thermal soak
    ambient_temp_c: float = 28.0   # Ambient starting temperature
    steady_state_temp_c: float = 44.0  # Max thermal saturation temperature
    throttle_temp_threshold_c: float = 40.0  # Temperature where thermal throttling begins
    resolution: Tuple[int, int] = (640, 360) # Scaled vision resolution
    target_fps: float = 30.0       # Target frame rate


# Profile A: Samsung Galaxy F23 5G (Qualcomm Snapdragon 750G / 6GB RAM)
# 2x Kryo 570 Gold (2.2 GHz) + 6x Silver (1.8 GHz), Adreno 619
PROFILE_SNAPDRAGON_750G = MobileDeviceProfile(
    name="Profile A (Snapdragon 750G / Samsung F23 5G)",
    target_budget_ms=25.0,
    max_ram_mb=180.0,
    cpu_cores=2,
    scale_factor=3.40,
    thermal_tau_sec=90.0,
    thermal_max_slowdown=0.25,
    ambient_temp_c=28.0,
    steady_state_temp_c=44.0,
    throttle_temp_threshold_c=40.0,
    resolution=(640, 360),
    target_fps=30.0,
)

# Profile B: Infinix Zero 30 5G (MediaTek Dimensity 8020 / 12GB RAM)
# 4x Cortex-A78 (2.6 GHz) + 4x Cortex-A55 (2.0 GHz), Mali-G77 MC9
PROFILE_DIMENSITY_8020 = MobileDeviceProfile(
    name="Profile B (Dimensity 8020 / Infinix Zero 30 5G)",
    target_budget_ms=16.0,
    max_ram_mb=250.0,
    cpu_cores=4,
    scale_factor=1.85,
    thermal_tau_sec=140.0,
    thermal_max_slowdown=0.10,
    ambient_temp_c=28.0,
    steady_state_temp_c=39.0,
    throttle_temp_threshold_c=38.0,
    resolution=(960, 540),
    target_fps=60.0,
)

# Unconstrained Reference Host PC Profile
PROFILE_UNCONSTRAINED = MobileDeviceProfile(
    name="Host PC (Unconstrained Native)",
    target_budget_ms=5.0,
    max_ram_mb=1024.0,
    cpu_cores=8,
    scale_factor=1.0,
    thermal_tau_sec=9999.0,
    thermal_max_slowdown=0.0,
    ambient_temp_c=25.0,
    steady_state_temp_c=30.0,
    throttle_temp_threshold_c=80.0,
    resolution=(1280, 720),
    target_fps=120.0,
)

PROFILES: Dict[str, MobileDeviceProfile] = {
    "PROFILE_SNAPDRAGON_750G": PROFILE_SNAPDRAGON_750G,
    "SNAPDRAGON_750G": PROFILE_SNAPDRAGON_750G,
    "PROFILE_A": PROFILE_SNAPDRAGON_750G,
    "F23": PROFILE_SNAPDRAGON_750G,
    "PROFILE_DIMENSITY_8020": PROFILE_DIMENSITY_8020,
    "DIMENSITY_8020": PROFILE_DIMENSITY_8020,
    "PROFILE_B": PROFILE_DIMENSITY_8020,
    "ZERO30": PROFILE_DIMENSITY_8020,
    "PROFILE_UNCONSTRAINED": PROFILE_UNCONSTRAINED,
    "UNCONSTRAINED": PROFILE_UNCONSTRAINED,
    "HOST": PROFILE_UNCONSTRAINED,
}


def get_profile(name_or_key: str) -> MobileDeviceProfile:
    """Retrieve MobileDeviceProfile by name or alias."""
    key = name_or_key.strip().upper().replace(" ", "_").replace("-", "_")
    if key in PROFILES:
        return PROFILES[key]
    for p_key, profile in PROFILES.items():
        if key in p_key:
            return profile
    # Default to Snapdragon 750G
    return PROFILE_SNAPDRAGON_750G

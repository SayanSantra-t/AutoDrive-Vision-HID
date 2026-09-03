# Project: AutoDrive PC Test & Benchmarking Harness

## Architecture
AutoDrive PC Test & Benchmarking Harness (`harness/`) bridges real-time CarX Street PC gameplay with the autonomous driving algorithm, emulating target mobile SoC compute/memory constraints and providing high-fidelity vision, smooth PWM keystroke modulation, and automated performance tracking.

```
                  ┌──────────────────────────────────────────────┐
                  │          CarX Street Game Window             │
                  └──────────────┬───────────────────────────────┘
                                 │ Frame Capture (MSS / DXGI / OpenCV)
                                 ▼
                  ┌──────────────────────────────────────────────┐
                  │       harness.capture (Screen Capture)       │
                  └──────────────┬───────────────────────────────┘
                                 │ RGB / BGR Image Stream
                                 ▼
                  ┌──────────────────────────────────────────────┐
                  │   harness.profiler (Mobile SoC Emulation)    │
                  │   - Profile A: Snapdragon 750G (<=25ms,180MB)│
                  │   - Profile B: Dimensity 8020 (<=16ms, 250MB)│
                  └──────────────┬───────────────────────────────┘
                                 │ Paced / Monitored Frame
                                 ▼
                  ┌──────────────────────────────────────────────┐
                  │        harness.vision (Vision Pipeline)      │
                  │   - Adaptive Matched-Filter Lane Tracker     │
                  │   - IPM & 2nd-Order Polynomial Curve Fitting │
                  │   - 3-Frame Persistent 3D Obstacle Detector  │
                  │   - Shadow & Road Marking Rejection (No AEB) │
                  └──────────────┬───────────────────────────────┘
                                 │ Lane Geometry + Threat Vector
                                 ▼
                  ┌──────────────────────────────────────────────┐
                  │       harness.control (Driving Controller)   │
                  │   - Stanley Steering + PID Cross-Track Error │
                  │   - Feedforward Curvature Anticipation       │
                  │   - Reverse Lockout & Graduated Braking      │
                  │   - 80ms PWM Duty-Cycle WASD Modulator       │
                  └──────────────┬───────────────────────────────┘
                                 │ Key Events (DIK_W/A/S/D/Space)
                                 ▼
                  ┌──────────────────────────────────────────────┐
                  │     harness.input (DirectInput Scancodes)    │
                  │   - Win32 SendInput KEYEVENTF_SCANCODE       │
                  │   - Foreground Safety Guard & Emergency Stop │
                  └──────────────┬───────────────────────────────┘
                                 │ Direct Keyboard Keystrokes
                                 ▼
                  ┌──────────────────────────────────────────────┐
                  │          CarX Street Game Window             │
                  └──────────────────────────────────────────────┘
```

## Feature Inventory
| # | Feature | Description | Milestone | Source | Status |
|---|---------|-------------|-----------|--------|:------:|
| 1 | Low-Latency Screen Capture | Capture CarX Street game window or screen region (<5ms) with MSS/DXGI/OpenCV | M1 | R1 | ✅ DONE |
| 2 | DirectInput Hardware Scancode Injection | Win32 `SendInput` hardware scancodes (`DIK_W`, `DIK_A`, `DIK_S`, `DIK_D`, `DIK_SPACE`) | M1 | R1 | ✅ DONE |
| 3 | Input Safety Guard & Failsafes | Auto-release on focus loss, emergency stop key combination, clean state cleanup | M1 | R1 | ✅ DONE |
| 4 | Profile A Snapdragon 750G Emulation | 2 Big cores (Kryo 570), <=25ms budget (30+ FPS), <=180MB RAM limit, throttling | M2 | R2 | ✅ DONE |
| 5 | Profile B Dimensity 8020 Emulation | 4 Big cores (Cortex-A78), <=16ms budget (60 FPS), <=250MB RAM limit, throttling | M2 | R2 | ✅ DONE |
| 6 | Thermal Soak & Memory Watchdog | Exponential thermal degradation model and real-time RSS memory watchdog | M2 | R2 | ✅ DONE |
| 7 | Zero-Allocation Buffer Pooling | Pre-allocated frame/array pools ensuring bounded zero-GC memory allocation | M2 | R2 | ✅ DONE |
| 8 | Adaptive Matched-Filter Lane Tracking | Row-adaptive luminance thresholding & multi-point edge scanning across lighting | M3 | R3 | ✅ DONE |
| 9 | IPM & Polynomial Curve Fitting | Inverse Perspective Mapping + 2nd-order parabolic fit ($x = ay^2 + by + c$) | M3 | R3 | ✅ DONE |
| 10 | Shadow & 2D Marking Rejection | Texture energy vs vertical gradient gating to avoid false obstacle triggers | M3 | R3 | ✅ DONE |
| 11 | Multi-Frame Temporal Obstacle Persistence | 3-frame temporal tracker and elevation gating to eliminate false AEB | M3 | R3 | ✅ DONE |
| 12 | Stanley + PID + Feedforward Steering | Combined angle: heading (0.4) + stanley (0.35) + PID (0.25) + feedforward ($\kappa$) | M4 | R3 | ✅ DONE |
| 13 | 80ms PWM WASD Duty-Cycle Modulation | Time-sliced duty cycle steering with 15ms min pulse/release constraints | M4 | R3 | ✅ DONE |
| 14 | Reverse Lockout & Graduated Deceleration | Prevents accidental reverse gear engagement and smooths speed regulation | M4 | R3 | ✅ DONE |
| 15 | Real-Time HUD Cockpit Visualizer | OpenCV overlay rendering lane lines, curvature, obstacle boxes, and WASD telemetry | M5 | R1, R3 | ✅ DONE |
| 16 | Automated Profiling & Benchmark Suite | Stage-by-stage latency percentiles (p50/p95/p99), jitter, and memory tracking | M5 | R2, R4 | ✅ DONE |
| 17 | Persistent Performance Ledger | Full `PERFORMANCE_LOG.md` recording updates, benchmarks, and CarX evaluation | M5 | R4 | ✅ DONE |
| 18 | Opaque-Box E2E Testing Suite (Tiers 1-4) | Comprehensive test suite covering feature, boundary, combinatorial, and workload | E2E | All | ✅ DONE |
| 19 | Adversarial Coverage Hardening (Tier 5) | White-box stress testing and edge-case hardening | Final | All | ✅ DONE |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|:------:|
| E2E | E2E Testing Suite Track | Test harness runner, Tiers 1-4 comprehensive opaque-box test suites, `TEST_READY.md` | none | ✅ DONE |
| M1 | Direct PC Capture & DirectInput Driver | `harness.capture` + `harness.input` modules, hardware scan codes, window capture | none | ✅ DONE |
| M2 | Mobile Compute & Memory Emulation | `harness.profiler` Snapdragon 750G & Dimensity 8020 models, memory watchdog, buffers | M1 | ✅ DONE |
| M3 | Vision Robustness & Obstacle Detection | `harness.vision` adaptive lane matched-filter, IPM polynomial curve fit, 3-frame AEB | M1 | ✅ DONE |
| M4 | Smooth WASD Control & Anti-Oscillation | `harness.control` Stanley+PID+Feedforward, 80ms PWM duty-cycle modulator, reverse lockout | M3 | ✅ DONE |
| M5 | Integration, HUD, Profiling & Ledger | `harness.main`, `harness.overlay`, `harness.benchmark`, `PERFORMANCE_LOG.md` | M2, M4 | ✅ DONE |
| Final | 100% E2E Pass & Adversarial Hardening | Pass 100% Tiers 1-4, execute Tier 5 Adversarial Coverage Hardening | E2E, M5 | ✅ DONE |

## Code Layout
```
AutoDrive-Vision-HID/
├── harness/
│   ├── __init__.py
│   ├── config.py             # Vehicle, vision, control & device configuration dataclasses
│   ├── capture/
│   │   ├── __init__.py
│   │   ├── screen_capture.py # Screen capture (MSS / Win32 / OpenCV / Synthetic generator)
│   │   └── window_finder.py  # Window handle locator & ROI cropping for CarX Street
│   ├── profiler/
│   │   ├── __init__.py
│   │   ├── mobile_profile.py # Snapdragon 750G & Dimensity 8020 profile definitions
│   │   ├── throttler.py      # Core affinity, micro-scaling delay & thermal soak engine
│   │   └── memory_pool.py    # Zero-allocation buffer pool & RSS memory watchdog
│   ├── vision/
│   │   ├── __init__.py
│   │   ├── lane_detector.py  # Adaptive matched-filter & IPM polynomial curve fitting
│   │   ├── obstacle_grid.py  # Spatial neural grid with 3-frame persistence & shadow rejection
│   │   └── transforms.py     # Inverse Perspective Mapping (IPM) & perspective matrices
│   ├── control/
│   │   ├── __init__.py
│   │   ├── stanley_pid.py    # Stanley steering, PID cross-track, feedforward curvature
│   │   ├── pwm_modulator.py  # 80ms time-sliced PWM duty-cycle WASD modulator & reverse lockout
│   │   └── speed_regulator.py# ACC, curve speed adaptation & graduated AEB
│   ├── input/
│   │   ├── __init__.py
│   │   ├── direct_input.py   # Win32 SendInput KEYEVENTF_SCANCODE driver
│   │   └── safety_guard.py   # Focus detection, failsafe release, emergency stop
│   ├── overlay/
│   │   ├── __init__.py
│   │   └── hud_visualizer.py # OpenCV real-time telemetry HUD overlay
│   ├── benchmark/
│   │   ├── __init__.py
│   │   ├── profiler_suite.py # Automated statistical profiler (p50/p95/p99 latency, jitter, RSS)
│   │   └── ledger_writer.py  # PERFORMANCE_LOG.md automated markdown generator & updater
│   └── main.py               # Unified CLI entry point for live driving, emulation & benchmarking
├── tests/
│   ├── test_harness_core.py         # 20 core unit tests
│   ├── e2e/
│   │   ├── test_tier1_features.py   # Feature coverage (85 tests)
│   │   ├── test_tier2_boundaries.py # Boundary & corner cases (85 tests)
│   │   ├── test_tier3_pairwise.py   # Cross-feature combinations (26 tests)
│   │   ├── test_tier4_workloads.py  # Real-world CarX Street application workloads (12 tests)
│   │   ├── test_tier5_adversarial.py# White-box stress & adversarial tests (10 tests)
│   │   └── test_helpers.py          # Shared test fixtures & contract mocks
│   └── run_e2e_tests.py             # E2E test runner CLI with pass/fail exit codes
├── PERFORMANCE_LOG.md        # Persistent performance & update ledger (R4)
├── PROJECT.md                # Master architectural blueprint & milestone registry
├── TEST_INFRA.md             # Opaque-box E2E test suite specification & methodology
└── TEST_READY.md             # E2E test suite ready attestation signal
```

"""Time-Sliced 80ms PWM WASD Duty-Cycle Modulator with Reverse Lockout.

Translates continuous steering, throttle, and brake commands into smooth, non-oscillating
DirectInput keyboard pulses with 15ms minimum pulse/release constraints to prevent key lockups.
"""

from __future__ import annotations

from typing import Optional
from harness.config import ControlConfig
from harness.input.direct_input import KeyboardState
from harness.control.stanley_pid import ControlCommand


class PwmWasdModulator:
    """80ms PWM duty-cycle generator for discrete binary keyboard driving."""

    def __init__(self, config: Optional[ControlConfig] = None):
        self.config = config or ControlConfig()
        self._elapsed_in_cycle_ms = 0.0

    def reset(self) -> None:
        """Reset PWM cycle timer."""
        self._elapsed_in_cycle_ms = 0.0

    def _compute_on_time_ms(self, demand: float, deadband: float = 0.03) -> float:
        """Compute active pulse duration under minimum pulse and release constraints."""
        val = abs(demand)
        if val < deadband:
            return 0.0

        raw_on_ms = val * self.config.pwm_period_ms

        # Enforce minimum pulse duration
        if raw_on_ms < self.config.min_pulse_width_ms:
            return 0.0

        # Enforce minimum release gap
        if (self.config.pwm_period_ms - raw_on_ms) < self.config.min_release_gap_ms:
            return self.config.pwm_period_ms  # 100% full hold

        return raw_on_ms

    def modulate(self, cmd: ControlCommand, dt: float) -> KeyboardState:
        """Convert analog ControlCommand to digital KeyboardState over PWM time slices."""
        dt_ms = dt * 1000.0
        self._elapsed_in_cycle_ms = (self._elapsed_in_cycle_ms + dt_ms) % self.config.pwm_period_ms
        t_phase = self._elapsed_in_cycle_ms

        # 1. Emergency Braking Override (No handbrake lockup, obey reverse lockout)
        if cmd.emergency_brake:
            # Only apply S if vehicle is moving forward (above reverse lockout threshold)
            safe_brake_s = (cmd.current_speed_mps >= self.config.reverse_lockout_speed_mps)
            return KeyboardState(
                key_w=False,
                key_a=False,
                key_s=safe_brake_s,
                key_d=False,
                key_space=False,  # Never slam handbrake during emergency stop in CarX
            )

        # 2. Steering PWM Modulation (Keys A and D)
        steer_on_ms = self._compute_on_time_ms(cmd.steering_angle, deadband=self.config.steering_deadband)
        is_steer_pulse_active = (t_phase < steer_on_ms)

        key_a = False
        key_d = False
        if is_steer_pulse_active:
            if cmd.steering_angle < -self.config.steering_deadband:
                key_a = True
            elif cmd.steering_angle > self.config.steering_deadband:
                key_d = True

        # 3. Throttle PWM Modulation (Key W)
        throttle_on_ms = self._compute_on_time_ms(cmd.throttle, deadband=0.08)
        key_w = (t_phase < throttle_on_ms) and (cmd.brake < 0.15)

        # 4. Brake PWM Modulation & Reverse Lockout (Key S)
        brake_on_ms = self._compute_on_time_ms(cmd.brake, deadband=0.10)
        key_s_raw = (t_phase < brake_on_ms)

        # Reverse Lockout: Prevent continuous S from engaging reverse gear at low speeds (<3 km/h)
        key_s = key_s_raw
        if cmd.current_speed_mps < self.config.reverse_lockout_speed_mps:
            # Drop Key S when vehicle has successfully brought speed to standstill
            key_s = False

        # 5. Handbrake (Key Space)
        key_space = cmd.handbrake

        return KeyboardState(
            key_w=key_w,
            key_a=key_a,
            key_s=key_s,
            key_d=key_d,
            key_space=key_space,
        )

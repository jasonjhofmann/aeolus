"""Time-aware exponential moving average (EMA) + slope — Aeolus core math.

Pure, dependency-free, fully unit-tested in isolation (tests/test_ema.py).
Mirrors Versatile Thermostat's `ema.py` scheme (REQUIREMENTS FR-M2): alpha is
derived from a half-life and the ACTUAL elapsed time between samples, so it
handles the irregular cadence of CO2 sensors correctly.

    alpha = 1 - exp(ln(0.5) * dt / halflife)   # dt = seconds since last sample
    alpha = min(alpha, max_alpha)              # cap weight a long gap can give
    ema   = alpha * value + (1 - alpha) * ema_prev

The slope (FR-S1) is the rate of change of the *smoothed* series, lightly
smoothed itself to avoid noise spikes from irregular sampling.
"""

from __future__ import annotations

import math
from datetime import datetime

_LN_HALF = math.log(0.5)


class TimeAwareEMA:
    """Half-life-parameterised EMA that tolerates irregular sample intervals."""

    def __init__(
        self,
        halflife_sec: float,
        *,
        max_alpha: float = 0.5,
        precision: int = 1,
    ) -> None:
        if halflife_sec <= 0:
            raise ValueError("halflife_sec must be > 0")
        if not 0.0 < max_alpha <= 1.0:
            raise ValueError("max_alpha must be in (0, 1]")
        self._halflife = float(halflife_sec)
        self._max_alpha = float(max_alpha)
        self._precision = precision
        self._ema: float | None = None
        self._last: datetime | None = None

    @property
    def value(self) -> float | None:
        """Current smoothed value, rounded to `precision` (None until seeded)."""
        return None if self._ema is None else round(self._ema, self._precision)

    @property
    def raw(self) -> float | None:
        """Unrounded smoothed value (for chaining into the slope calc)."""
        return self._ema

    @property
    def last_timestamp(self) -> datetime | None:
        return self._last

    def add(self, measurement: float, timestamp: datetime) -> float | None:
        """Fold one sample in; returns the new rounded value.

        First sample seeds the EMA. Non-positive dt (duplicate / out-of-order
        timestamps) is ignored to avoid corrupting state (FR-M2c).
        """
        if self._ema is None or self._last is None:
            self._ema = measurement
            self._last = timestamp
            return self.value

        dt = (timestamp - self._last).total_seconds()
        if dt <= 0:
            return self.value

        alpha = 1.0 - math.exp(_LN_HALF * dt / self._halflife)
        if alpha > self._max_alpha:
            alpha = self._max_alpha
        self._ema = alpha * measurement + (1.0 - alpha) * self._ema
        self._last = timestamp
        return self.value

    def seed(self, value: float | None, timestamp: datetime) -> None:
        """Restore prior state across restarts (NFR-2).

        Only seeds if not already initialized from a live sample (so a fresh
        reading taken at startup is never clobbered by a stale restored value),
        and records a real timestamp so the next sample *blends* rather than
        re-initializing.
        """
        if value is not None and self._ema is None:
            self._ema = float(value)
            self._last = timestamp


class SlopeTracker:
    """Signed rate-of-change of an EMA series, lightly smoothed (FR-S1/S2).

    Units are caller-defined per second; Aeolus converts to ppm/min for display.
    Negative slope = falling CO2 = mitigation working.
    """

    def __init__(self, *, smoothing_halflife_sec: float, precision: int = 4) -> None:
        self._smoother = TimeAwareEMA(
            smoothing_halflife_sec, max_alpha=1.0, precision=precision
        )
        self._prev_value: float | None = None
        self._prev_ts: datetime | None = None

    def update(self, ema_value: float, timestamp: datetime) -> float | None:
        """Feed the latest EMA point; returns smoothed slope (per second)."""
        if self._prev_value is None or self._prev_ts is None:
            self._prev_value, self._prev_ts = ema_value, timestamp
            return self._smoother.value
        dt = (timestamp - self._prev_ts).total_seconds()
        if dt <= 0:
            return self._smoother.value
        instantaneous = (ema_value - self._prev_value) / dt
        self._prev_value, self._prev_ts = ema_value, timestamp
        return self._smoother.add(instantaneous, timestamp)

    @property
    def per_second(self) -> float | None:
        return self._smoother.raw

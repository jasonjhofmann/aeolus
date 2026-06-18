"""Live derived/command state for Aeolus — the runtime image of the domain model.

A dependency-light leaf module (imports only const + ema) so the guardrail
(safety.py) and the engine can both depend on these types WITHOUT a circular
import. Parsed config lives in models.py; this is the mutable per-tick state the
engine maintains and the controller/safety read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .const import MetricKind
from .ema import SlopeTracker, TimeAwareEMA


@dataclass(slots=True)
class MetricRuntime:
    """Live derived state for ONE metric of a Space (FR-P/FR-T)."""

    kind: MetricKind
    ema: TimeAwareEMA
    slope: SlopeTracker
    floor: float
    last_raw: float | None = None
    active_tier: int = -1  # staircase hysteresis (FR-T3); -1 = no tier engaged
    # Per-metric management gate (FR-E9): True → contributes actuator demand;
    # False → monitor-only (value/status still surfaced, no demand). Toggled by
    # the advanced "Manage <metric>" switch; the space Mode is the master (FR-L6).
    manage: bool = True
    member_seen: dict[str, datetime] = field(default_factory=dict)

    @property
    def value(self) -> float | None:
        return self.ema.value

    @property
    def slope_per_min(self) -> float | None:
        per_sec = self.slope.per_second
        return None if per_sec is None else round(per_sec * 60.0, 2)


@dataclass(slots=True)
class SpaceRuntime:
    """Per-space runtime: one MetricRuntime per metric + the mitigation latch.

    The space-level read API (ema_ppm/slope/member_seen) proxies the *primary*
    metric (the CO₂ one if present, else the first) so the existing Space CO₂
    sensor + slope/ACH entities keep working unchanged.
    """

    metrics: list[MetricRuntime]
    primary: int = 0
    mitigating: bool = False  # any metric tier engaged (FR-L1)

    @property
    def primary_metric(self) -> MetricRuntime | None:
        return self.metrics[self.primary] if self.metrics else None

    @property
    def ema_ppm(self) -> float | None:
        m = self.primary_metric
        return None if m is None else m.value

    @property
    def slope_ppm_per_min(self) -> float | None:
        m = self.primary_metric
        return None if m is None else m.slope_per_min

    @property
    def last_raw_ppm(self) -> float | None:
        m = self.primary_metric
        return None if m is None else m.last_raw

    @property
    def member_seen(self) -> dict[str, datetime]:
        m = self.primary_metric
        return m.member_seen if m is not None else {}


@dataclass(slots=True)
class ActuatorRuntime:
    """Aeolus's command state for one actuator. `commanded_setpoint` is 0..100
    (0 = off; a fan %, or just on/off for switches/covers) — v3 variable drive."""

    commanded_setpoint: int = 0
    on_since: datetime | None = None
    last_change: datetime | None = None
    last_command_sent: datetime | None = (
        None  # last time a service fired (rearm cadence)
    )
    overridden_until: datetime | None = None
    divergence_since: datetime | None = (
        None  # state≠command since (override confirmation, FR-L7b)
    )
    aq_vetoed: bool = False  # last-seen outdoor-AQ veto state (for transition logging)

    @property
    def commanded_on(self) -> bool:
        return self.commanded_setpoint > 0

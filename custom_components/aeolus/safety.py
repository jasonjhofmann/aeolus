"""Safety + IAQ guardrails (FR-G*). These GATE every actuation.

For the reference (MCAS/allergy, leaky envelope) home the binding constraint is
allergen infiltration, not backdraft (§0.4). v0.1 implements: stale-sensor
safe-state, per-pathway filter-aware outdoor-AQ veto, and per-actuator
max-runtime. Radon-on-depressurization veto (FR-G2) is v1.1.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .const import DEFAULT_STALE_AFTER_SEC, Mechanism
from .engine import ActuatorRuntime, SpaceRuntime
from .models import Actuator, Space

# Mechanisms that move OUTDOOR air in (or depressurize → infiltration) and so
# are subject to the outdoor-AQ veto (FR-G3 / §0.4).
OUTDOOR_AIR_MECHANISMS = frozenset(
    {Mechanism.BALANCED, Mechanism.SUPPLY, Mechanism.EXHAUST, Mechanism.WINDOW}
)


def is_stale(
    member_seen: dict[str, datetime], now: datetime, *, stale_after_sec: float = DEFAULT_STALE_AFTER_SEC
) -> bool:
    """True if EVERY member is stale — don't trust the aggregate timestamp (FR-M1/G5)."""
    if not member_seen:
        return True
    cutoff = now - timedelta(seconds=stale_after_sec)
    return all(seen < cutoff for seen in member_seen.values())


def is_space_stale(
    rt: SpaceRuntime, now: datetime, *, stale_after_sec: float = DEFAULT_STALE_AFTER_SEC
) -> bool:
    """Per-space staleness via the primary metric's members (FR-M1/G5)."""
    return is_stale(rt.member_seen, now, stale_after_sec=stale_after_sec)


def outdoor_aq_blocks(outdoor_pm: float, filter_efficiency: float, threshold_pm: float) -> bool:
    """Filter-aware outdoor-AQ veto (FR-G3): estimated indoor PM contribution."""
    indoor_contribution = outdoor_pm * (1.0 - filter_efficiency)
    return indoor_contribution > threshold_pm


def outdoor_air_vetoed(
    hass: HomeAssistant, actuator: Actuator, space: Space
) -> bool:
    """Should this outdoor-air actuator be blocked for this space right now?

    Reads the per-pathway outdoor-AQ sensor (actuator's own intake sensor, else
    the space's). Fail-safe: if configured but unreadable, do NOT block on a
    missing reading (avoid stranding a space) — but a present over-threshold
    reading blocks. Non-outdoor-air mechanisms are never AQ-vetoed.
    """
    if actuator.mechanism not in OUTDOOR_AIR_MECHANISMS:
        return False
    aq_entity = actuator.outdoor_aq_entity or space.outdoor_aq_entity
    threshold = space.outdoor_aq_threshold
    if aq_entity is None or threshold is None:
        return False
    state = hass.states.get(aq_entity)
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return False
    try:
        outdoor_pm = float(state.state)
    except (TypeError, ValueError):
        return False
    return outdoor_aq_blocks(outdoor_pm, actuator.filter_efficiency, threshold)


def max_runtime_exceeded(rt: ActuatorRuntime, actuator: Actuator, now: datetime) -> bool:
    """Per-actuator max-runtime cap (FR-G1 baseline safety)."""
    if rt.on_since is None:
        return False
    return (now - rt.on_since) >= timedelta(minutes=actuator.max_runtime_min)

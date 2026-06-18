"""Mitigation control + arbitration (FR-L*, FR-T) — v3 graduated staircase.

Each Space metric runs a tier ladder with engage/release hysteresis (FR-T2/T3).
The active tier's per-actuator setpoints are arbitrated by `max` across all
metrics (FR-T / decision #5), gated by capability (a recirculating filter can't
reduce CO₂, FR-P5) and the outdoor-AQ veto (FR-G3). Min on/off, the override
yield (FR-L7/b), and re-arm are applied by the engine's `command_actuator`.

The CO₂ control shipped in v1 is the 2-tier special case (high → target).

Deferred / not yet wired into the staircase: induced/pressure edges (FR-X3) —
the `_induced_applicable` helper is retained (and unit-tested) for re-integration.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .const import (
    CONVERGENCE_SLOPE_PPM_PER_MIN,
    MECHANISM_REDUCES,
    SpaceMode,
)
from .safety import is_stale, max_runtime_exceeded, outdoor_air_vetoed

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .engine import AeolusEngine
    from .models import Actuator, Influence, Metric, Space
    from .runtime import MetricRuntime


def evaluate(engine: AeolusEngine, now: datetime) -> None:
    """Decide every actuator's setpoint from the metric tier ladders and command it."""
    if engine.paused:
        return  # master switch off → stop managing (leaves devices as-is)

    desired: dict[str, int] = {act_id: 0 for act_id in engine.actuators}
    for space_id, space in engine.spaces.items():
        srt = engine.space_runtime(space_id)
        if srt is None:
            continue
        if space.mode is not SpaceMode.MANAGE:
            srt.mitigating = False  # FR-L6: monitor/off → never actuate
            continue
        active = False
        for midx, metric in enumerate(space.metrics):
            if midx >= len(srt.metrics):
                continue
            mrt = srt.metrics[midx]
            if is_stale(mrt.member_seen, now):
                mrt.active_tier = -1  # FR-G5: never actuate blind; clear the latch
                continue
            value = mrt.value
            if value is None:
                continue
            # Update the tier latch for ALL fresh metrics so the value/status surface
            # is correct (FR-E5/E6) — but only a *managed* metric contributes demand.
            tier_idx = _active_tier(metric, mrt, value)
            if tier_idx is None or not mrt.manage:  # FR-E9 per-metric gate
                continue
            active = True
            for act_id, setpoint in metric.tiers[tier_idx].setpoints.items():
                act = engine.actuators.get(act_id)
                if act is None or not _actuator_eligible(engine, act, space, metric):
                    continue
                desired[act_id] = max(desired[act_id], int(setpoint))
        srt.mitigating = active

    for act_id, act in engine.actuators.items():
        art = engine.actuator_runtime(act_id)
        # Log outdoor-AQ veto engage/clear once per transition — the key
        # "why didn't it ventilate" signal, otherwise silent.
        if art is not None:
            vetoed = any(
                inf.space_id in engine.spaces
                and outdoor_air_vetoed(engine.hass, act, engine.spaces[inf.space_id])
                for inf in act.influences
            )
            if vetoed != art.aq_vetoed:
                art.aq_vetoed = vetoed
                if vetoed:
                    _LOGGER.warning(
                        "Aeolus: %s outdoor-AQ veto engaged — outdoor PM over "
                        "threshold; ventilation via this pathway suspended",
                        act.name,
                    )
                else:
                    _LOGGER.info("Aeolus: %s outdoor-AQ veto cleared", act.name)
        if engine.actuator_is_overridden(act_id, now):
            continue  # yield to the human/automation (FR-L7)
        setpoint = desired[act_id]
        if (
            setpoint > 0
            and art is not None
            and art.commanded_on
            and max_runtime_exceeded(art, act, now)
        ):
            # FR-G1 per-actuator runtime cap. Log the transition (still-demanded but
            # force-off) once — command_actuator is idempotent so subsequent ticks
            # won't re-log a no-op.
            _LOGGER.warning(
                "Aeolus: %s hit max runtime (%.0f min) — forcing off "
                "despite active demand",
                act.name,
                act.max_runtime_min,
            )
            setpoint = 0
        engine.command_actuator(act_id, setpoint, now)


def _active_tier(metric: Metric, mrt: MetricRuntime, value: float) -> int | None:
    """Highest engaged tier with per-tier hysteresis (FR-T2/T3); updates the latch.

    Escalates while the next tier's engage threshold is exceeded; de-escalates
    while the current tier's release threshold is not. Handles multi-tier jumps.
    """
    tiers = metric.tiers
    cur = mrt.active_tier
    while cur + 1 < len(tiers) and value > tiers[cur + 1].engage_at:
        cur += 1
    while cur >= 0 and value <= tiers[cur].release_at:
        cur -= 1
    mrt.active_tier = cur
    return cur if cur >= 0 else None


def _actuator_eligible(
    engine: AeolusEngine, act: Actuator, space: Space, metric: Metric
) -> bool:
    """Can this actuator reduce this metric, and is it not AQ-vetoed? (FR-P5/G3).

    A recirculating filter (air purifier) is rejected for CO₂; outdoor-air
    mechanisms are blocked when the outdoor-AQ veto trips.
    """
    if metric.kind not in MECHANISM_REDUCES.get(act.mechanism, frozenset()):
        return False
    return not outdoor_air_vetoed(engine.hass, act, space)


# --- Induced edges (FR-X3) — retained for re-integration into the staircase ----
def _space_not_converging(engine: AeolusEngine, space_id: str) -> bool:
    """A space whose smoothed slope isn't falling fast enough (FR-L3 trigger)."""
    rt = engine.space_runtime(space_id)
    if rt is None or rt.slope_ppm_per_min is None:
        return True
    return rt.slope_ppm_per_min >= -CONVERGENCE_SLOPE_PPM_PER_MIN


def _induced_applicable(engine: AeolusEngine, inf: Influence) -> bool:
    """Induced edge valid only when the target isn't converging (FR-L3) AND a named
    source space is meaningfully lower than the target (FR-X3)."""
    if not _space_not_converging(engine, inf.space_id):
        return False
    if inf.source_space_id is None:
        return False
    src = engine.space_runtime(inf.source_space_id)
    tgt = engine.space_runtime(inf.space_id)
    if src is None or tgt is None:
        return False
    src_ppm = src.ema_ppm
    tgt_ppm = tgt.ema_ppm
    if src_ppm is None or tgt_ppm is None:
        return False
    return src_ppm + inf.gap_margin_ppm < tgt_ppm

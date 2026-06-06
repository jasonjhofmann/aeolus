"""Mitigation control + arbitration (FR-L*) — v0.1.

Scope: per-space threshold/hysteresis, coverage arbitration over `direct` AND
`induced` actuators, min on/off cycling, per-actuator max-runtime, manual-
override yield, stale-sensor safe-state, per-pathway outdoor-AQ veto, and
direct→induced escalation (FR-L3/X3 — the canonical Primary-Bedroom case).

Deferred: PI control, variable-speed drive (FR-L4), cost-weighted arbitration,
occupancy feedforward, diffusive air-share propagation.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from .const import (
    CONVERGENCE_SLOPE_PPM_PER_MIN,
    GAIN_ACH_PRIOR,
    InfluenceType,
    SpaceMode,
)
from .safety import is_space_stale, max_runtime_exceeded, outdoor_air_vetoed

if TYPE_CHECKING:
    from .engine import AeolusEngine


def evaluate(engine: AeolusEngine, now: datetime) -> None:
    """Decide every actuator's on/off state and command it."""
    if engine.paused:
        return  # master switch off → stop managing (FR-L6, leaves devices as-is)
    demand = _space_demand(engine, now)

    for act_id, act in engine.actuators.items():
        if engine.actuator_is_overridden(act_id, now):
            continue  # yield to the human/automation (FR-L7)

        art = engine.actuator_runtime(act_id)
        if art is not None and art.commanded_on and max_runtime_exceeded(art, act, now):
            engine.command_actuator(act_id, False, now)  # FR-G1
            continue

        engine.command_actuator(act_id, _actuator_wanted(engine, act, demand), now)


def _space_demand(engine: AeolusEngine, now: datetime) -> dict[str, bool]:
    """Per-space mitigation demand, with hysteresis + stale safe-state."""
    demand: dict[str, bool] = {}
    for space_id, space in engine.spaces.items():
        rt = engine.space_runtime(space_id)
        if rt is None:
            demand[space_id] = False
            continue
        if space.mode is not SpaceMode.MANAGE or is_space_stale(rt, now):
            rt.mitigating = False  # FR-G5: never actuate blind / when not managing
            demand[space_id] = False
            continue
        ema = rt.ema_ppm
        if ema is not None:
            if ema > space.high_ppm:
                rt.mitigating = True  # start (FR-L1)
            elif ema <= space.target_ppm:
                rt.mitigating = False  # stop — deadband between target and high
        demand[space_id] = rt.mitigating
    return demand


def _actuator_wanted(engine: AeolusEngine, act, demand: dict[str, bool]) -> bool:
    """True if any space this actuator should serve needs it now."""
    for inf in act.influences:
        if GAIN_ACH_PRIOR.get(inf.gain, 0.0) <= 0.0:
            continue  # non-reducing edge
        if not demand.get(inf.space_id, False):
            continue
        space = engine.spaces.get(inf.space_id)
        if space is None or outdoor_air_vetoed(engine.hass, act, space):
            continue  # FR-G3 per-pathway veto
        if inf.influence_type is InfluenceType.DIRECT:
            return True
        if inf.influence_type is InfluenceType.INDUCED and _induced_applicable(engine, inf):
            return True
        # DIFFUSIVE is a space↔space link, not an actuator edge — skip.
    return False


def _space_not_converging(engine: AeolusEngine, space_id: str) -> bool:
    """A space whose smoothed slope isn't falling fast enough (FR-L3 trigger)."""
    rt = engine.space_runtime(space_id)
    if rt is None or rt.slope_ppm_per_min is None:
        return True  # no evidence it's improving → eligible to escalate
    return rt.slope_ppm_per_min >= -CONVERGENCE_SLOPE_PPM_PER_MIN


def _induced_applicable(engine: AeolusEngine, inf) -> bool:
    """Induced edge is valid only when (a) the target isn't converging on its
    own (escalation, FR-L3) and (b) the source space is meaningfully lower than
    the target, so depressurization actually pulls cleaner air in (FR-X3)."""
    if not _space_not_converging(engine, inf.space_id):
        return False
    if inf.source_space_id is None:
        return False
    src = engine.space_runtime(inf.source_space_id)
    tgt = engine.space_runtime(inf.space_id)
    if src is None or tgt is None or src.ema_ppm is None or tgt.ema_ppm is None:
        return False
    return src.ema_ppm + inf.gap_margin_ppm < tgt.ema_ppm

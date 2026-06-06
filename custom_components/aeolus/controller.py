"""Mitigation control + arbitration (FR-L*) — v0.1.

v0.1 scope (resolved MVP): per-space threshold/hysteresis on `direct` on/off
actuators, simple coverage arbitration (an actuator runs if ANY managed space
it directly serves needs mitigation and safety allows), min on/off cycling,
per-actuator max-runtime, manual-override yield, stale-sensor safe-state, and
the per-pathway outdoor-AQ veto.

Deferred to v1.1: induced/diffusive edges + escalation (FR-L3/X3), PI control,
variable-speed drive (FR-L4), cost-weighted arbitration, occupancy feedforward.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from .const import GAIN_ACH_PRIOR, InfluenceType, SpaceMode
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
    """True if any managed space this actuator DIRECTLY reduces needs it now."""
    for inf in act.influences:
        if inf.influence_type is not InfluenceType.DIRECT:
            continue  # v0.1: direct only
        if GAIN_ACH_PRIOR.get(inf.gain, 0.0) <= 0.0:
            continue  # non-reducing edge
        if not demand.get(inf.space_id, False):
            continue
        space = engine.spaces.get(inf.space_id)
        if space is None or outdoor_air_vetoed(engine.hass, act, space):
            continue  # FR-G3 per-pathway veto
        return True
    return False

"""Diagnostics for Aeolus (Gold `diagnostics`).

A dump of the influence graph, EVERY metric's full tier ladder, and the live
EMA/slope/status/veto state — so the configuration (incl. ladders) and runtime
can be viewed/shared without re-authoring (the §8.7 deferred editor). Nothing is
redacted: Aeolus owns no secrets (no tokens/credentials, NFR-3) and the source
sensor / actuator entity_ids are needed to make the dump useful for inspection —
and are no more revealing than the actuator names already shown in the ladders.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .engine import OVERRIDE_WINDOW
from .models import AeolusConfigEntry
from .runtime import ActuatorRuntime
from .safety import is_stale, max_runtime_exceeded, outdoor_air_vetoed


def _dt(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _td(value: timedelta | None) -> float | None:
    return None if value is None else value.total_seconds()


def _actuator_runtime(rt: ActuatorRuntime | None) -> dict[str, Any]:
    if rt is None:
        return {}
    return {
        "commanded_setpoint": rt.commanded_setpoint,
        "commanded_on": rt.commanded_on,
        "on_since": _dt(rt.on_since),
        "last_change": _dt(rt.last_change),
        "last_command_sent": _dt(rt.last_command_sent),
        "overridden_until": _dt(rt.overridden_until),
        "divergence_since": _dt(rt.divergence_since),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AeolusConfigEntry
) -> dict[str, Any]:
    """The whole Aeolus picture: spaces+metrics+ladders and actuators+runtime."""
    engine = entry.runtime_data.engine
    now = dt_util.utcnow()

    spaces: list[dict[str, Any]] = []
    for sid, space in engine.spaces.items():
        metrics: list[dict[str, Any]] = []
        for midx, metric in enumerate(space.metrics):
            mrt = engine.metric_runtime(sid, midx)
            seen = mrt.member_seen if mrt is not None else {}
            metrics.append(
                {
                    "kind": metric.kind.value,
                    "sensors": list(metric.sensors),
                    "aggregation": metric.aggregation.value,
                    "value": engine.metric_value(sid, midx),
                    "last_raw": mrt.last_raw if mrt is not None else None,
                    "slope_per_min": engine.metric_slope_per_min(sid, midx),
                    "active_tier": mrt.active_tier if mrt is not None else None,
                    "managed": engine.metric_manage(sid, midx),
                    "available": engine.metric_available(sid, midx),
                    # Why "stale"? — the freshness signal the safety check uses.
                    "stale": is_stale(seen, now),
                    "last_member_seen": _dt(max(seen.values())) if seen else None,
                    "tiers": engine.metric_tiers_view(sid, midx),
                }
            )
        spaces.append(
            {
                "subentry_id": sid,
                "name": space.name,
                "mode": space.mode.value,
                "target_ppm": space.target_ppm,
                "high_ppm": space.high_ppm,
                "outdoor_aq_entity": space.outdoor_aq_entity,
                "outdoor_aq_threshold": space.outdoor_aq_threshold,
                "status": engine.space_status(sid, now),
                "reason": engine.space_reason(sid, now),
                "mitigating": engine.space_mitigating(sid),
                "attention": engine.space_attention(sid, now),
                "available": engine.space_available(sid),
                "effective_ach": engine.space_effective_ach(sid),
                "time_to_target_min": engine.space_time_to_target_min(sid),
                "active_actuators": engine.space_active_actuator_names(sid),
                "driving_metrics": [k.value for k in engine.space_driving_metrics(sid)],
                "metrics": metrics,
            }
        )

    actuators = [
        {
            "subentry_id": aid,
            "name": act.name,
            "mechanism": act.mechanism.value,
            "entities": list(act.entities or [act.entity_id]),
            "filter_efficiency": act.filter_efficiency,
            "outdoor_aq_entity": act.outdoor_aq_entity,
            "max_runtime_min": act.max_runtime_min,
            "on_speed_pct": act.on_speed_pct,
            "rearm_interval_sec": _td(act.rearm_interval),
            "override_grace_sec": _td(act.override_grace),
            "is_overridden": engine.actuator_is_overridden(aid, now),
            # Blocking causes, evaluated now — answers "why isn't it running?".
            "outdoor_air_vetoed": any(
                inf.space_id in engine.spaces
                and outdoor_air_vetoed(hass, act, engine.spaces[inf.space_id])
                for inf in act.influences
            ),
            "max_runtime_exceeded": (
                max_runtime_exceeded(rt, act, now)
                if (rt := engine.actuator_runtime(aid)) is not None
                else False
            ),
            "influences": [
                {
                    "space_id": inf.space_id,
                    "gain": inf.gain.value,
                    "type": inf.influence_type.value,
                    "source_space_id": inf.source_space_id,
                    "gap_margin_ppm": inf.gap_margin_ppm,
                    "lag_sec": inf.lag_sec,
                }
                for inf in act.influences
            ],
            "runtime": _actuator_runtime(engine.actuator_runtime(aid)),
        }
        for aid, act in engine.actuators.items()
    ]

    return {
        "c_out_ppm": engine.c_out_ppm,
        "paused": engine.paused,
        # Control thresholds in effect, so a log reader can interpret min on/off
        # holds and the override yield window.
        "min_on_sec": engine.min_on.total_seconds(),
        "min_off_sec": engine.min_off.total_seconds(),
        "override_window_sec": OVERRIDE_WINDOW.total_seconds(),
        "spaces": spaces,
        "actuators": actuators,
        # Bounded what/when/why decision log (newest first) — the durable history
        # also fired as `aeolus_action` events and persisted to .storage (FR-U2).
        "recent_actions": [a.to_dict() for a in engine.recent_actions],
    }

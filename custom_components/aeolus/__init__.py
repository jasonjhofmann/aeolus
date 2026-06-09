"""The Aeolus integration — adaptive, multi-zone CO2 & ventilation manager.

Calculated/local-push helper. Lifecycle per the verified HA pattern: no
DataUpdateCoordinator; a push engine on `entry.runtime_data`; actions
registered in `async_setup` (action-setup rule).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from .const import (
    CONF_ACTUATOR_ENTITIES,
    CONF_ACTUATOR_ENTITY,
    CONF_AGGREGATION,
    CONF_CO2_SENSORS,
    CONF_FILTER_EFFICIENCY,
    CONF_HIGH_PPM,
    CONF_MECHANISM,
    CONF_METRIC_KIND,
    CONF_METRIC_SENSORS,
    CONF_METRICS,
    CONF_ON_SPEED_PCT,
    CONF_OUTDOOR_AQ_ENTITY,
    CONF_OUTDOOR_AQ_THRESHOLD,
    CONF_OVERRIDE_GRACE_MIN,
    CONF_REARM_INTERVAL,
    CONF_SERVED_SPACES,
    CONF_TARGET_PPM,
    CONF_TIER_ENGAGE,
    CONF_TIER_RELEASE,
    CONF_TIER_SETPOINTS,
    CONF_TIERS,
    CONF_VOLUME_FT3,
    DEFAULT_HIGH_PPM,
    DEFAULT_RELEASE_FRACTION,
    DEFAULT_TARGET_PPM,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_SPACE,
    Aggregation,
    Gain,
    InfluenceType,
    Mechanism,
    MetricKind,
)
from .engine import AeolusEngine
from .models import Actuator, AeolusConfigEntry, AeolusData, Influence, Metric, Space, Tier
from .services import async_register_services

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-level actions (independent of any loaded entry)."""
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AeolusConfigEntry) -> bool:
    """Set up Aeolus from its config entry + subentries."""
    spaces, actuators = _parse_subentries(entry)
    _migrate_entity_ids(hass, entry, spaces)
    engine = AeolusEngine(hass, entry.entry_id, spaces, actuators)
    entry.runtime_data = AeolusData(engine=engine)
    engine.async_start()
    entry.async_on_unload(engine.async_stop)
    # Reload when a Space/Actuator subentry is added or reconfigured, so threshold/
    # actuator edits take effect immediately instead of only at the next restart.
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload_on_update(hass: HomeAssistant, entry: AeolusConfigEntry) -> None:
    """Re-parse subentries by reloading the entry (config/subentry changed)."""
    await hass.config_entries.async_reload(entry.entry_id)


# The Aeolus *measurement* sensors (a metric value, its slope, the CO₂ ACH) are
# named "Managed <metric>" so their entity_ids carry a `managed_` marker — this
# distinguishes Aeolus's smoothed/managed output from the user's raw source sensors
# (whose convention is `<room>_<metric>`, e.g. the Aranet `sensor.primary_bedroom_co2`)
# and so never collides with them. Status/control entities keep descriptive names.
_VALUE_KINDS: frozenset[str] = frozenset({"co2", "pm1", "pm2_5", "pm10", "aqi", "generic"})
_TAIL_OVERRIDES: dict[str, str] = {"reason": "status_reason", "target": "target_co2"}


def _canonical_tail(suffix: str) -> str:
    """The object_id tail a fresh install generates for a given unique_id suffix."""
    if suffix in _VALUE_KINDS or suffix.endswith("_slope") or suffix == "air_change_rate":
        return f"managed_{suffix}"
    return _TAIL_OVERRIDES.get(suffix, suffix)


def _migrate_entity_ids(
    hass: HomeAssistant, entry: AeolusConfigEntry, spaces: dict[str, Space]
) -> None:
    """One-time, idempotent cleanup of legacy per-Space entity_ids:

    * strip the **double device-name prefix** some derived sensors acquired on older
      builds (e.g. `sensor.primary_bedroom_primary_bedroom_pm2_5`), and
    * give the **measurement sensors a `managed_` marker** (`sensor.<space>` →
      `sensor.<space>_managed_co2`) so no single metric reads as the space's unnamed
      default and they don't collide with the raw source sensors (FR-E8).

    Renames to the canonical `<domain>.<space-slug>_<tail>` a fresh install produces;
    a no-op once ids are canonical. Skips any rename whose target id is already taken
    (never clobbers another entity).
    """
    registry = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        space = spaces.get(ent.unique_id[:26])  # subentry_id is a 26-char ULID
        if space is None:
            continue  # not a Space entity (e.g. the manager master switch)
        suffix = ent.unique_id[27:]
        if not suffix:
            continue
        desired = f"{ent.domain}.{slugify(space.name)}_{_canonical_tail(suffix)}"
        if ent.entity_id == desired or registry.async_get(desired) is not None:
            continue
        registry.async_update_entity(ent.entity_id, new_entity_id=desired)


async def async_unload_entry(hass: HomeAssistant, entry: AeolusConfigEntry) -> bool:
    """Unload a config entry (config-entry-unloading rule)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _parse_subentries(
    entry: AeolusConfigEntry,
) -> tuple[dict[str, Space], dict[str, Actuator]]:
    """Turn config subentries into the engine's domain model.

    Two passes: actuators first (spaces' synthesized CO₂ tiers reference them).
    """
    actuators: dict[str, Actuator] = {
        sub_id: _parse_actuator(sub_id, sub.title, sub.data)
        for sub_id, sub in entry.subentries.items()
        if sub.subentry_type == SUBENTRY_TYPE_ACTUATOR
    }
    spaces: dict[str, Space] = {
        sub_id: _parse_space(sub_id, sub.title, sub.data, actuators)
        for sub_id, sub in entry.subentries.items()
        if sub.subentry_type == SUBENTRY_TYPE_SPACE
    }
    return spaces, actuators


def _parse_actuator(sub_id: str, title: str, data: Mapping[str, Any]) -> Actuator:
    entities = [str(e) for e in (data.get(CONF_ACTUATOR_ENTITIES) or [])]
    if not entities and data.get(CONF_ACTUATOR_ENTITY):
        entities = [str(data[CONF_ACTUATOR_ENTITY])]
    rearm_min = data.get(CONF_REARM_INTERVAL)
    on_speed = data.get(CONF_ON_SPEED_PCT)
    grace_min = data.get(CONF_OVERRIDE_GRACE_MIN)
    return Actuator(
        subentry_id=sub_id,
        name=title,
        entity_id=entities[0] if entities else "",
        entities=entities,
        mechanism=Mechanism(data.get(CONF_MECHANISM, Mechanism.BALANCED)),
        filter_efficiency=float(data.get(CONF_FILTER_EFFICIENCY, 0.0)),
        outdoor_aq_entity=data.get(CONF_OUTDOOR_AQ_ENTITY),
        on_speed_pct=int(on_speed) if on_speed else None,
        override_grace=timedelta(minutes=float(grace_min)) if grace_min else timedelta(0),
        rearm_interval=timedelta(minutes=float(rearm_min)) if rearm_min else None,
        influences=[
            Influence(space_id=s, gain=Gain.MEDIUM, influence_type=InfluenceType.DIRECT)
            for s in data.get(CONF_SERVED_SPACES, [])
        ],
    )


def _parse_space(
    sub_id: str, title: str, data: Mapping[str, Any], actuators: dict[str, Actuator]
) -> Space:
    co2_sensors = [str(s) for s in data.get(CONF_CO2_SENSORS, [])]
    aggregation = Aggregation(data.get(CONF_AGGREGATION, Aggregation.MEAN))
    target = float(data.get(CONF_TARGET_PPM, DEFAULT_TARGET_PPM))
    high = float(data.get(CONF_HIGH_PPM, DEFAULT_HIGH_PPM))
    return Space(
        subentry_id=sub_id,
        name=title,
        co2_sensors=co2_sensors,
        aggregation=aggregation,
        target_ppm=target,
        high_ppm=high,
        volume_ft3=data.get(CONF_VOLUME_FT3),
        outdoor_aq_entity=data.get(CONF_OUTDOOR_AQ_ENTITY),
        outdoor_aq_threshold=data.get(CONF_OUTDOOR_AQ_THRESHOLD),
        metrics=_build_metrics(data, sub_id, co2_sensors, aggregation, target, high, actuators),
    )


def _build_metrics(
    data: Mapping[str, Any],
    space_id: str,
    co2_sensors: list[str],
    aggregation: Aggregation,
    target: float,
    high: float,
    actuators: dict[str, Actuator],
) -> list[Metric]:
    """Synthesized CO₂ metric (from the simple fields) MERGED with any explicit
    PM/AQI metrics (CONF_METRICS). Keeps the simple CO₂ path while letting a Space
    also carry graduated particulate ladders authored in the config flow."""
    metrics: list[Metric] = []
    if co2_sensors:
        # 2-tier CO₂ ladder: off ≤ target; serving actuators on > high (at their
        # on-speed, else 100). Mirrors the v1 high/target hysteresis.
        setpoints = {
            aid: (act.on_speed_pct or 100)
            for aid, act in actuators.items()
            if any(inf.space_id == space_id for inf in act.influences)
        }
        metrics.append(
            Metric(
                kind=MetricKind.CO2,
                sensors=co2_sensors,
                aggregation=aggregation,
                tiers=[Tier(engage_at=high, release_at=target, setpoints=setpoints)],
            )
        )
    for m in data.get(CONF_METRICS) or []:
        metrics.append(_parse_metric(m))
    return metrics


def _parse_metric(m: Mapping[str, Any]) -> Metric:
    tiers: list[Tier] = []
    for t in m.get(CONF_TIERS, []):
        engage = float(t[CONF_TIER_ENGAGE])
        release = float(t.get(CONF_TIER_RELEASE) or engage * DEFAULT_RELEASE_FRACTION)
        setpoints = {str(k): int(v) for k, v in (t.get(CONF_TIER_SETPOINTS) or {}).items()}
        tiers.append(Tier(engage_at=engage, release_at=release, setpoints=setpoints))
    tiers.sort(key=lambda tier: tier.engage_at)
    return Metric(
        kind=MetricKind(m.get(CONF_METRIC_KIND, MetricKind.GENERIC)),
        sensors=[str(s) for s in m.get(CONF_METRIC_SENSORS, [])],
        aggregation=Aggregation(m.get(CONF_AGGREGATION, Aggregation.MEAN)),
        tiers=tiers,
    )

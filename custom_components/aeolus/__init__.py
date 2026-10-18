"""The Aeolus integration — adaptive, multi-zone CO2 & ventilation manager.

Calculated/local-push helper. Lifecycle per the verified HA pattern: no
DataUpdateCoordinator; a push engine on `entry.runtime_data`; actions
registered in `async_setup` (action-setup rule).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

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
    DOMAIN,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_SPACE,
    Aggregation,
    Gain,
    InfluenceType,
    Mechanism,
    MetricKind,
)
from .engine import AeolusEngine, signal_space_added
from .models import (
    Actuator,
    AeolusConfigEntry,
    AeolusData,
    Influence,
    Metric,
    Space,
    Tier,
)
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

# Config-entry-only integration: `async_setup` exists solely to register the
# integration-level actions; there is no YAML configuration for the `aeolus:` key.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

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
    engine = AeolusEngine(hass, entry.entry_id, spaces, actuators)
    entry.runtime_data = AeolusData(engine=engine)
    # Restore the persisted action ring (FR-U2) before the engine starts ticking,
    # so the history survives restarts; flush it back on unload.
    await engine.async_load_actions()
    engine.async_start()
    entry.async_on_unload(engine.async_stop)
    entry.async_on_unload(engine.async_save_actions)
    # Handle subentry changes live: a newly-added Space/Actuator is brought online
    # without a reload (dynamic-devices), a removed one is dropped (stale-devices),
    # and a reconfigure of an existing subentry reloads so its edited data re-parses.
    entry.async_on_unload(entry.add_update_listener(_async_handle_subentry_change))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # repair-issues: once HA has finished starting (so a not-yet-loaded source
    # isn't mistaken for a deleted one), surface any configured source/actuator
    # entity that no longer exists — a user-fixable misconfiguration.
    @callback
    def _on_started(_hass: HomeAssistant) -> None:
        _async_sync_missing_entity_issues(hass, entry, spaces, actuators)

    entry.async_on_unload(async_at_started(hass, _on_started))
    return True


ISSUE_MISSING_PREFIX = "missing_entity_"


def _referenced_entities(
    spaces: dict[str, Space], actuators: dict[str, Actuator]
) -> list[tuple[str, str, str]]:
    """(entity_id, owner_name, kind) for every entity the config references."""
    refs: list[tuple[str, str, str]] = []
    for space in spaces.values():
        for metric in space.metrics:
            refs.extend((sid, space.name, "sensor") for sid in metric.sensors)
        if space.outdoor_aq_entity:
            refs.append((space.outdoor_aq_entity, space.name, "sensor"))
    for act in actuators.values():
        refs.extend(
            (eid, act.name, "actuator")
            for eid in (act.entities or [act.entity_id])
            if eid
        )
        if act.outdoor_aq_entity:
            refs.append((act.outdoor_aq_entity, act.name, "sensor"))
    return refs


@callback
def _async_sync_missing_entity_issues(
    hass: HomeAssistant,
    entry: AeolusConfigEntry,
    spaces: dict[str, Space],
    actuators: dict[str, Actuator],
) -> None:
    """Create a repair issue per missing configured entity and clear resolved ones.

    An entity counts as missing only when it is absent from BOTH the state machine
    and the entity registry — i.e. genuinely deleted/renamed, not merely unavailable
    or provided by an integration that hasn't loaded yet (entity-unavailable covers
    those)."""
    registry = er.async_get(hass)
    issue_reg = ir.async_get(hass)
    wanted: set[str] = set()
    for entity_id, owner, kind in _referenced_entities(spaces, actuators):
        present = (
            hass.states.get(entity_id) is not None
            or registry.async_get(entity_id) is not None
        )
        if present:
            continue
        issue_id = f"{ISSUE_MISSING_PREFIX}{entry.entry_id}_{entity_id}"
        wanted.add(issue_id)
        if (
            issue_reg.async_get_issue(DOMAIN, issue_id) is None
        ):  # newly missing → log once
            _LOGGER.warning(
                "Aeolus: configured %s '%s' for '%s' no longer exists "
                "— raising a repair issue",
                kind,
                entity_id,
                owner,
            )
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing_entity",
            translation_placeholders={
                "entity_id": entity_id,
                "name": owner,
                "kind": kind,
            },
        )
    prefix = f"{ISSUE_MISSING_PREFIX}{entry.entry_id}_"
    for domain, issue_id in list(issue_reg.issues):
        if domain == DOMAIN and issue_id.startswith(prefix) and issue_id not in wanted:
            _LOGGER.info(
                "Aeolus: missing-entity repair issue resolved — clearing %s", issue_id
            )
            ir.async_delete_issue(hass, DOMAIN, issue_id)


async def _async_handle_subentry_change(
    hass: HomeAssistant, entry: AeolusConfigEntry
) -> None:
    """Route a subentry change: add/remove are applied live; a reconfigure reloads.

    HA fires the entry update listener for subentry add, update, AND remove. We diff
    the parsed subentries against what the engine already knows: a structural change
    (added/removed ids) is applied to the running engine without a reload
    (dynamic-devices / stale-devices); a pure reconfigure (same id set, changed data)
    reloads so the edited data re-parses (reconfiguration-flow)."""
    engine = entry.runtime_data.engine
    spaces, actuators = _parse_subentries(entry)

    added_space_ids = spaces.keys() - engine.spaces.keys()
    removed_space_ids = engine.spaces.keys() - spaces.keys()
    added_act_ids = actuators.keys() - engine.actuators.keys()
    removed_act_ids = engine.actuators.keys() - actuators.keys()

    if not (added_space_ids or removed_space_ids or added_act_ids or removed_act_ids):
        # Pure reconfigure of existing subentries → reload to re-parse the new data.
        await hass.config_entries.async_reload(entry.entry_id)
        return

    # Removals first (so a re-add can't collide), then additions.
    for act_id in removed_act_ids:
        engine.remove_actuator(act_id)
    for space_id in removed_space_ids:
        engine.remove_space(space_id)
    for act_id in added_act_ids:
        engine.add_actuator(actuators[act_id])
    for space_id in added_space_ids:
        engine.add_space(spaces[space_id])
        async_dispatcher_send(hass, signal_space_added(entry.entry_id), space_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: AeolusConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow deleting an orphaned Aeolus device from the UI (stale-devices).

    The manager device and any live Space device (whose subentry still exists) are
    protected; only a device whose backing subentry is gone may be removed."""
    own_ids = {ident for domain, ident in device.identifiers if domain == DOMAIN}
    if entry.entry_id in own_ids:  # the manager device
        return False
    return not any(sub_id in entry.subentries for sub_id in own_ids)


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
        override_grace=timedelta(minutes=float(grace_min))
        if grace_min
        else timedelta(0),
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
        metrics=_build_metrics(
            data, sub_id, co2_sensors, aggregation, target, high, actuators
        ),
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
        setpoints = {
            str(k): int(v) for k, v in (t.get(CONF_TIER_SETPOINTS) or {}).items()
        }
        tiers.append(Tier(engage_at=engage, release_at=release, setpoints=setpoints))
    tiers.sort(key=lambda tier: tier.engage_at)
    return Metric(
        kind=MetricKind(m.get(CONF_METRIC_KIND, MetricKind.GENERIC)),
        sensors=[str(s) for s in m.get(CONF_METRIC_SENSORS, [])],
        aggregation=Aggregation(m.get(CONF_AGGREGATION, Aggregation.MEAN)),
        tiers=tiers,
    )

"""Per-metric entity/control/status parity + explainability (FR-E5–E9, FR-U2).

The §8.8 gap: a CO₂ **and** PM managed Space must surface PM as a first-class
citizen — its own sensors, its own threshold control, a metric-attributed
status/attention, a Manage gate, and a plain-language `reason` — not just CO₂.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    CONF_MECHANISM,
    CONF_METRIC_KIND,
    CONF_METRIC_SENSORS,
    CONF_METRICS,
    CONF_TIER_ENGAGE,
    CONF_TIERS,
    DOMAIN,
)
from custom_components.aeolus.engine import signal_space_update


async def _setup_co2_and_pm(
    hass: HomeAssistant,
) -> tuple[MockConfigEntry, str, str, int]:
    """A Zone with CO₂ (700, calm) + a PM2.5 metric (tier-1 engage 30) and a hood."""
    hass.states.async_set("sensor.z_co2", "700")
    hass.states.async_set("sensor.z_pm", "5")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="Zone",
                unique_id=None,
                data={
                    CONF_CO2_SENSORS: ["sensor.z_co2"],
                    "target_ppm": 800,
                    "high_ppm": 1000,
                    CONF_METRICS: [
                        {
                            CONF_METRIC_KIND: "pm2_5",
                            CONF_METRIC_SENSORS: ["sensor.z_pm"],
                            CONF_TIERS: [{CONF_TIER_ENGAGE: 30}],
                        }
                    ],
                },
            ),
            ConfigSubentryData(
                subentry_type="actuator",
                title="Hood",
                unique_id=None,
                data={CONF_ACTUATOR_ENTITY: "fan.hood", CONF_MECHANISM: "exhaust"},
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    eng = entry.runtime_data.engine
    eng.min_on = eng.min_off = timedelta(0)
    for svc in ("turn_on", "turn_off"):
        async_mock_service(hass, "fan", svc)
    sid = next(iter(eng.spaces))
    hood = next(iter(eng.actuators))
    pm_idx = next(
        i for i, m in enumerate(eng.spaces[sid].metrics) if m.kind.value == "pm2_5"
    )
    return entry, sid, hood, pm_idx


def _eid(hass: HomeAssistant, domain: str, unique: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique)


def _drive_pm(
    hass: HomeAssistant, entry: MockConfigEntry, sid: str, pm_idx: int, value: float
):
    """Force the PM EMA and re-evaluate + refresh entities (no time advance)."""
    eng = entry.runtime_data.engine
    mrt = eng.metric_runtime(sid, pm_idx)
    mrt.member_seen["sensor.z_pm"] = dt_util.utcnow()
    mrt.ema._ema = float(value)
    eng.request_evaluation()
    async_dispatcher_send(hass, signal_space_update(eng.entry_id, sid))


async def test_per_metric_sensors_symmetric_naming(hass: HomeAssistant) -> None:
    """FR-E5/E8: every metric gets value + slope sensors; ACH is CO₂-only; and NO
    metric is the unnamed default — CO₂ is named "<Space> CO₂", symmetric with PM."""
    _, sid, _, _ = await _setup_co2_and_pm(hass)
    assert _eid(hass, "sensor", f"{sid}_co2") is not None  # unique_id preserved
    assert _eid(hass, "sensor", f"{sid}_co2_slope") is not None
    assert _eid(hass, "sensor", f"{sid}_air_change_rate") is not None
    assert _eid(hass, "sensor", f"{sid}_pm2_5") is not None  # NEW — was invisible
    assert _eid(hass, "sensor", f"{sid}_pm2_5_slope") is not None
    assert (
        _eid(hass, "sensor", f"{sid}_pm2_5_air_change_rate") is None
    )  # ACH is CO₂-only
    co2 = hass.states.get(_eid(hass, "sensor", f"{sid}_co2"))
    pm = hass.states.get(_eid(hass, "sensor", f"{sid}_pm2_5"))
    # "Managed <metric>" — not the bare "Zone", and never collides with a raw
    # `<room>_<metric>` source sensor (entity_id → sensor.zone_managed_co2).
    assert co2.attributes["friendly_name"] == "Zone Managed CO₂"
    assert pm.attributes["friendly_name"] == "Zone Managed PM2.5"
    assert co2.entity_id == "sensor.zone_managed_co2"
    assert co2.attributes["device_class"] == "carbon_dioxide"
    assert pm.attributes["device_class"] == "pm25"


async def test_migrate_legacy_entity_ids(hass: HomeAssistant) -> None:
    """Cleanup migration: a legacy double-prefixed PM sensor and a bare CO₂ sensor
    (`sensor.zone`) are renamed to the canonical `sensor.zone_pm2_5` / `_co2`."""
    hass.states.async_set("sensor.z_co2", "700")
    hass.states.async_set("sensor.z_pm", "5")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="Zone",
                unique_id=None,
                data={
                    CONF_CO2_SENSORS: ["sensor.z_co2"],
                    "target_ppm": 800,
                    "high_ppm": 1000,
                    CONF_METRICS: [
                        {
                            CONF_METRIC_KIND: "pm2_5",
                            CONF_METRIC_SENSORS: ["sensor.z_pm"],
                            CONF_TIERS: [{CONF_TIER_ENGAGE: 30}],
                        }
                    ],
                },
            ),
        ],
    )
    entry.add_to_hass(hass)
    sid = next(
        s.subentry_id for s in entry.subentries.values() if s.subentry_type == "space"
    )
    reg = er.async_get(hass)
    # Pre-seed the legacy (broken) entity_ids older builds left behind.
    reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{sid}_pm2_5",
        suggested_object_id="zone_zone_pm2_5",
        config_entry=entry,
    )
    reg.async_get_or_create(
        "sensor", DOMAIN, f"{sid}_co2", suggested_object_id="zone", config_entry=entry
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{sid}_pm2_5")
        == "sensor.zone_managed_pm2_5"
    )
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{sid}_co2")
        == "sensor.zone_managed_co2"
    )


async def test_pm_value_surfaced(hass: HomeAssistant) -> None:
    """FR-E5: the PM sensor reports the PM value (not CO₂)."""
    entry, sid, _, pm_idx = await _setup_co2_and_pm(hass)
    _drive_pm(hass, entry, sid, pm_idx, 47)
    await hass.async_block_till_done()
    assert float(hass.states.get(_eid(hass, "sensor", f"{sid}_pm2_5")).state) == 47.0


async def test_attention_and_mitigation_see_pm(hass: HomeAssistant) -> None:
    """FR-E6 correctness: a PM exceedance (CO₂ calm) raises attention + mitigation
    and names PM — the gap where CO₂-only logic stayed silent."""
    entry, sid, hood, pm_idx = await _setup_co2_and_pm(hass)
    eng = entry.runtime_data.engine
    eng.spaces[sid].metrics[pm_idx].tiers[0].setpoints[hood] = 100
    _drive_pm(hass, entry, sid, pm_idx, 60)  # > engage 30, > top tier → attention
    await hass.async_block_till_done()
    assert eng.space_attention(sid) is True
    assert eng.space_mitigating(sid) is True
    assert "pm2_5" in [k.value for k in eng.space_driving_metrics(sid)]
    assert eng.actuator_runtime(hood).commanded_setpoint == 100
    mit = hass.states.get(_eid(hass, "binary_sensor", f"{sid}_mitigation_active"))
    assert mit.state == "on"
    assert "pm2_5" in mit.attributes["driving_metrics"]
    att = hass.states.get(_eid(hass, "binary_sensor", f"{sid}_attention"))
    assert att.state == "on"


async def test_reason_explains_mitigation_and_veto(hass: HomeAssistant) -> None:
    """FR-U2: the reason sensor names the driving metric + actuator, and the veto."""
    entry, sid, hood, pm_idx = await _setup_co2_and_pm(hass)
    eng = entry.runtime_data.engine
    eng.spaces[sid].metrics[pm_idx].tiers[0].setpoints[hood] = 100
    _drive_pm(hass, entry, sid, pm_idx, 60)
    await hass.async_block_till_done()
    reason = hass.states.get(_eid(hass, "sensor", f"{sid}_reason")).state
    assert "PM2.5" in reason and "Hood" in reason and reason.startswith("Mitigating")

    # Add an outdoor-AQ veto on the hood's pathway → reason flips to the veto cause.
    hass.states.async_set("sensor.outdoor_pm", "200")
    eng.spaces[sid].outdoor_aq_entity = "sensor.outdoor_pm"
    eng.spaces[sid].outdoor_aq_threshold = 20.0
    _drive_pm(hass, entry, sid, pm_idx, 60)
    await hass.async_block_till_done()
    reason = hass.states.get(_eid(hass, "sensor", f"{sid}_reason")).state
    assert "veto" in reason.lower()


async def test_pm_threshold_number(hass: HomeAssistant) -> None:
    """FR-E7: a PM engage-threshold number exists and adjusts the tier live."""
    entry, sid, _, pm_idx = await _setup_co2_and_pm(hass)
    eid = _eid(hass, "number", f"{sid}_pm2_5_threshold")
    assert eid is not None
    await hass.services.async_call(
        "number", "set_value", {"entity_id": eid, "value": 45}, blocking=True
    )
    assert (
        entry.runtime_data.engine.spaces[sid].metrics[pm_idx].tiers[0].engage_at == 45
    )


async def test_manage_gate_monitor_only(hass: HomeAssistant) -> None:
    """FR-E9: a Manage switch exists (disabled by default); gating PM to monitor-only
    removes its demand but still surfaces the value + a 'monitoring only' reason."""
    entry, sid, hood, pm_idx = await _setup_co2_and_pm(hass)
    eng = entry.runtime_data.engine
    eng.spaces[sid].metrics[pm_idx].tiers[0].setpoints[hood] = 100
    # The switch is registered even though disabled-by-default.
    assert _eid(hass, "switch", f"{sid}_manage_pm2_5") is not None

    eng.set_metric_manage(sid, pm_idx, False)  # what the switch's turn_off does
    _drive_pm(hass, entry, sid, pm_idx, 60)
    await hass.async_block_till_done()
    assert eng.actuator_runtime(hood).commanded_setpoint == 0  # no demand
    assert (
        float(hass.states.get(_eid(hass, "sensor", f"{sid}_pm2_5")).state) == 60.0
    )  # still shown
    assert (
        "monitoring only"
        in hass.states.get(_eid(hass, "sensor", f"{sid}_reason")).state
    )

    eng.set_metric_manage(sid, pm_idx, True)  # re-enable → demand returns
    _drive_pm(hass, entry, sid, pm_idx, 60)
    await hass.async_block_till_done()
    assert eng.actuator_runtime(hood).commanded_setpoint == 100


async def test_reason_modes(hass: HomeAssistant) -> None:
    """FR-U2: reason reflects monitor/off/paused without a pollutant problem."""
    entry, sid, _, _ = await _setup_co2_and_pm(hass)
    eng = entry.runtime_data.engine
    from custom_components.aeolus.const import SpaceMode

    eng.spaces[sid].mode = SpaceMode.MONITOR
    assert "Monitor only" in eng.space_reason(sid)
    eng.spaces[sid].mode = SpaceMode.OFF
    assert "off" in eng.space_reason(sid).lower()
    eng.spaces[sid].mode = SpaceMode.MANAGE
    eng.paused = True
    assert "management off" in eng.space_reason(sid).lower()


async def test_reason_stale_and_unavailable(hass: HomeAssistant) -> None:
    """FR-U2: stale + unavailable safe-states are explained, and status follows."""
    entry, sid, _, _ = await _setup_co2_and_pm(hass)
    eng = entry.runtime_data.engine
    old = dt_util.utcnow() - timedelta(hours=2)
    for mrt in eng.space_runtime(sid).metrics:  # every member of every metric stale
        for k in list(mrt.member_seen):
            mrt.member_seen[k] = old
    assert "stale" in eng.space_reason(sid).lower()
    assert eng.space_status(sid) == "stale"

    hass.states.async_set("sensor.z_co2", "unavailable")
    hass.states.async_set("sensor.z_pm", "unavailable")
    await hass.async_block_till_done()
    assert "unavailable" in eng.space_reason(sid).lower()
    assert eng.space_status(sid) == "unavailable"


async def test_reason_override_block(hass: HomeAssistant) -> None:
    """FR-U2: a held override is named as the reason mitigation isn't running."""
    entry, sid, hood, pm_idx = await _setup_co2_and_pm(hass)
    eng = entry.runtime_data.engine
    eng.spaces[sid].metrics[pm_idx].tiers[0].setpoints[hood] = 100
    eng.actuator_runtime(hood).overridden_until = dt_util.utcnow() + timedelta(
        minutes=30
    )
    _drive_pm(hass, entry, sid, pm_idx, 60)
    await hass.async_block_till_done()
    reason = hass.states.get(_eid(hass, "sensor", f"{sid}_reason")).state
    assert "override" in reason.lower() and "PM2.5" in reason
    assert eng.actuator_runtime(hood).commanded_setpoint == 0


async def test_ladder_viewable_as_tiers_attribute(hass: HomeAssistant) -> None:
    """View ladders without re-authoring (#1): the full tier ladder rides as a
    `tiers` attribute on the metric sensor, with setpoints keyed by actuator name."""
    entry, sid, hood, pm_idx = await _setup_co2_and_pm(hass)
    eng = entry.runtime_data.engine
    eng.spaces[sid].metrics[pm_idx].tiers[0].setpoints[hood] = 40
    eng.spaces[sid].metrics[pm_idx].tiers[0].release_at = 25
    _drive_pm(hass, entry, sid, pm_idx, 10)  # refresh the entity
    await hass.async_block_till_done()
    tiers = hass.states.get(_eid(hass, "sensor", f"{sid}_pm2_5")).attributes["tiers"]
    assert tiers == [{"engage_at": 30.0, "release_at": 25.0, "setpoints": {"Hood": 40}}]
    # CO₂'s synthesized 2-tier ladder is visible on the primary sensor too.
    assert "tiers" in hass.states.get(_eid(hass, "sensor", f"{sid}_co2")).attributes


async def test_diagnostics_dump(hass: HomeAssistant) -> None:
    """View ladders without re-authoring (#2): the diagnostics dump carries every
    ladder + runtime with real entity_ids (nothing redacted — no secrets, NFR-3)."""
    from custom_components.aeolus.diagnostics import async_get_config_entry_diagnostics

    entry, sid, hood, pm_idx = await _setup_co2_and_pm(hass)
    eng = entry.runtime_data.engine
    eng.spaces[sid].metrics[pm_idx].tiers[0].setpoints[hood] = 40

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["paused"] is False and diag["c_out_ppm"] == 420.0
    space = next(s for s in diag["spaces"] if s["subentry_id"] == sid)
    pm = next(m for m in space["metrics"] if m["kind"] == "pm2_5")
    assert pm["tiers"] == [
        {"engage_at": 30.0, "release_at": 25.5, "setpoints": {"Hood": 40}}
    ]
    assert pm["sensors"] == ["sensor.z_pm"]  # real entity_ids, not redacted
    assert space["status"] in ("ok", "monitor", "mitigating", "attention")
    hood_d = next(a for a in diag["actuators"] if a["name"] == "Hood")
    assert hood_d["mechanism"] == "exhaust" and hood_d["entities"] == ["fan.hood"]


async def test_manage_switch_entity_toggles(hass: HomeAssistant) -> None:
    """FR-E9: enabling the Manage switch entity and toggling it gates the metric."""
    entry, sid, _hood, pm_idx = await _setup_co2_and_pm(hass)
    registry = er.async_get(hass)
    uid = f"{sid}_manage_pm2_5"
    disabled_eid = registry.async_get_entity_id("switch", DOMAIN, uid)
    assert registry.async_get(disabled_eid).disabled_by is not None  # off by default
    registry.async_update_entity(disabled_eid, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    eng = entry.runtime_data.engine
    eid = registry.async_get_entity_id("switch", DOMAIN, uid)
    assert hass.states.get(eid).state == "on"  # default: managed
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": eid}, blocking=True
    )
    assert eng.metric_manage(sid, pm_idx) is False
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": eid}, blocking=True
    )
    assert eng.metric_manage(sid, pm_idx) is True

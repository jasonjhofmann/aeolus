"""Action history (FR-U2): the decision ring, the aeolus_action event, diagnostics."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import Event, HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import (
    ACTION_LOG_MAXLEN,
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    DOMAIN,
    EVENT_AEOLUS_ACTION,
)
from custom_components.aeolus.diagnostics import async_get_config_entry_diagnostics

FAN = "input_boolean.fan"


async def _setup(hass: HomeAssistant):
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"fan": {}}})
    hass.states.async_set("sensor.z_co2", "600")
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
                },
            ),
            ConfigSubentryData(
                subentry_type="actuator",
                title="Fan",
                unique_id=None,
                data={CONF_ACTUATOR_ENTITY: FAN, "mechanism": "transfer"},
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_command_records_action_and_fires_event(hass: HomeAssistant) -> None:
    """An on/off command appends to the ring AND fires the aeolus_action event."""
    entry = await _setup(hass)
    engine = entry.runtime_data.engine
    act_id = next(iter(engine.actuators))

    events: list[Event] = []
    hass.bus.async_listen(EVENT_AEOLUS_ACTION, events.append)

    now = dt_util.utcnow()
    engine.command_actuator(act_id, True, now)
    await hass.async_block_till_done()

    actions = engine.recent_actions
    assert actions, "expected a recorded action"
    assert actions[0].action == "actuator_on"
    assert actions[0].actuator_name == "Fan"
    assert actions[0].setpoint and actions[0].setpoint > 0
    assert "Fan on" in actions[0].message

    assert [e.data["action"] for e in events] == ["actuator_on"]
    assert events[0].data["entry_id"] == entry.entry_id


async def test_off_after_min_on_records_actuator_off(hass: HomeAssistant) -> None:
    """The off transition (past min-on) is recorded as a distinct action."""
    from datetime import timedelta

    entry = await _setup(hass)
    engine = entry.runtime_data.engine
    act_id = next(iter(engine.actuators))

    now = dt_util.utcnow()
    engine.command_actuator(act_id, True, now)
    await hass.async_block_till_done()  # let the on-state settle before commanding off
    engine.command_actuator(act_id, False, now + timedelta(seconds=601))
    await hass.async_block_till_done()

    kinds = [a.action for a in engine.recent_actions]
    assert kinds[0] == "actuator_off"  # newest first
    assert "actuator_on" in kinds


async def test_action_log_is_bounded(hass: HomeAssistant) -> None:
    """The ring never grows past ACTION_LOG_MAXLEN."""
    entry = await _setup(hass)
    engine = entry.runtime_data.engine
    act = next(iter(engine.actuators.values()))
    for _ in range(ACTION_LOG_MAXLEN + 25):
        engine.record_action("actuator_on", actuator=act, setpoint=100)
    assert len(engine.recent_actions) == ACTION_LOG_MAXLEN


async def test_diagnostics_includes_recent_actions(hass: HomeAssistant) -> None:
    """The decision ring is surfaced in the diagnostics dump."""
    entry = await _setup(hass)
    engine = entry.runtime_data.engine
    engine.command_actuator(next(iter(engine.actuators)), True, dt_util.utcnow())
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert "recent_actions" in diag
    assert diag["recent_actions"], "expected at least one action in diagnostics"
    first = diag["recent_actions"][0]
    assert first["action"] == "actuator_on"
    assert first["ts"] is not None
    assert "Fan on" in first["message"]

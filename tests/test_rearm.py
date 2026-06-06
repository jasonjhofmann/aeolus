"""FR-L5b re-arm: re-send ON while wanted for a load that self-auto-offs."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    CONF_REARM_INTERVAL,
    CONF_SERVED_SPACES,
    DOMAIN,
)

ACTUATOR = "input_boolean.fan"


async def _engine_with_rearm(hass: HomeAssistant, rearm_min: float):
    hass.states.async_set("sensor.z_co2", "650")
    hass.states.async_set(ACTUATOR, "off")
    data = {CONF_ACTUATOR_ENTITY: ACTUATOR, "mechanism": "exhaust"}
    if rearm_min:
        data[CONF_REARM_INTERVAL] = rearm_min
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space", title="Zone", unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.z_co2"], "target_ppm": 800, "high_ppm": 1000},
            ),
            ConfigSubentryData(
                subentry_type="actuator", title="Fan", unique_id=None,
                data={**data, CONF_SERVED_SPACES: []},
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    engine = entry.runtime_data.engine
    return engine, next(iter(engine.actuators))


async def test_rearm_resends_on_while_wanted(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "input_boolean", "turn_on")
    engine, aid = await _engine_with_rearm(hass, 14)
    t0 = dt_util.utcnow()

    engine.command_actuator(aid, True, t0)  # initial ON
    await hass.async_block_till_done()
    assert len(calls) == 1

    engine.command_actuator(aid, True, t0 + timedelta(minutes=5))  # too soon — no re-send
    await hass.async_block_till_done()
    assert len(calls) == 1

    engine.command_actuator(aid, True, t0 + timedelta(minutes=15))  # past interval — re-arm
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert engine.actuator_runtime(aid).commanded_on is True  # still "on", not toggled


async def test_no_rearm_without_interval(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "input_boolean", "turn_on")
    engine, aid = await _engine_with_rearm(hass, 0)  # disabled
    t0 = dt_util.utcnow()
    engine.command_actuator(aid, True, t0)
    engine.command_actuator(aid, True, t0 + timedelta(minutes=30))
    await hass.async_block_till_done()
    assert len(calls) == 1  # idempotent, never re-sent


async def test_override_suppresses_rearm(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "input_boolean", "turn_on")
    engine, aid = await _engine_with_rearm(hass, 14)
    t0 = dt_util.utcnow()
    engine.command_actuator(aid, True, t0)
    await hass.async_block_till_done()
    assert len(calls) == 1
    engine.actuator_runtime(aid).overridden_until = t0 + timedelta(minutes=30)
    engine.command_actuator(aid, True, t0 + timedelta(minutes=15))  # would re-arm, but overridden
    await hass.async_block_till_done()
    assert len(calls) == 1

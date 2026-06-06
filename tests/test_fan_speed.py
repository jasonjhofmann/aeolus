"""FR-L4b fan on-speed: turning a fan actuator on sets a chosen percentage."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    CONF_ON_SPEED_PCT,
    CONF_SERVED_SPACES,
    DOMAIN,
)

FAN = "fan.test_hood"


async def _engine(hass: HomeAssistant, on_speed: int):
    hass.states.async_set("sensor.z_co2", "650")
    hass.states.async_set(FAN, "off", {"percentage": 0, "percentage_step": 20, "supported_features": 49})
    data = {CONF_ACTUATOR_ENTITY: FAN, "mechanism": "exhaust"}
    if on_speed:
        data[CONF_ON_SPEED_PCT] = on_speed
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space", title="Zone", unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.z_co2"], "target_ppm": 800, "high_ppm": 1000},
            ),
            ConfigSubentryData(
                subentry_type="actuator", title="Hood", unique_id=None,
                data={**data, CONF_SERVED_SPACES: []},
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    engine = entry.runtime_data.engine
    return engine, next(iter(engine.actuators))


async def test_fan_on_speed_sets_percentage(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "fan", "turn_on")
    engine, aid = await _engine(hass, 60)
    engine.command_actuator(aid, True, dt_util.utcnow())
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data.get("percentage") == 60


async def test_fan_without_on_speed_omits_percentage(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "fan", "turn_on")
    engine, aid = await _engine(hass, 0)  # 0 → leave at fan default
    engine.command_actuator(aid, True, dt_util.utcnow())
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert "percentage" not in calls[0].data

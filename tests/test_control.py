"""Control-loop tests: engine → controller → safety → real actuation.

Uses a real `input_boolean` as the actuator (so the service call actually
lands and we can assert the resulting state), not a bare mock state.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    CONF_MECHANISM,
    DOMAIN,
    Gain,
    InfluenceType,
    Mechanism,
)
from custom_components.aeolus.models import Influence

ACTUATOR = "input_boolean.fan"


async def _setup(hass: HomeAssistant, co2: str) -> MockConfigEntry:
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"fan": {}}})
    hass.states.async_set("sensor.z_co2", co2)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Aeolus",
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
                data={
                    CONF_ACTUATOR_ENTITY: ACTUATOR,
                    CONF_MECHANISM: Mechanism.TRANSFER.value,  # not outdoor-air → no AQ veto
                },
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _wire(entry: MockConfigEntry) -> None:
    """v0.1 served-spaces UI isn't exercised here; wire the influence directly."""
    engine = entry.runtime_data.engine
    space_id = next(iter(engine.spaces))
    act_id = next(iter(engine.actuators))
    engine.actuators[act_id].influences = [
        Influence(space_id=space_id, gain=Gain.MEDIUM, influence_type=InfluenceType.DIRECT)
    ]


async def test_high_co2_turns_actuator_on(hass: HomeAssistant) -> None:
    entry = await _setup(hass, "1200")  # seeds EMA at 1200 > high(1000)
    _wire(entry)
    entry.runtime_data.engine.request_evaluation()
    await hass.async_block_till_done()
    assert hass.states.get(ACTUATOR).state == "on"


async def test_low_co2_keeps_actuator_off(hass: HomeAssistant) -> None:
    entry = await _setup(hass, "600")  # below target → no demand
    _wire(entry)
    entry.runtime_data.engine.request_evaluation()
    await hass.async_block_till_done()
    assert hass.states.get(ACTUATOR).state == "off"


async def test_paused_engine_does_not_actuate(hass: HomeAssistant) -> None:
    entry = await _setup(hass, "1200")
    _wire(entry)
    entry.runtime_data.engine.paused = True
    entry.runtime_data.engine.request_evaluation()
    await hass.async_block_till_done()
    assert hass.states.get(ACTUATOR).state == "off"

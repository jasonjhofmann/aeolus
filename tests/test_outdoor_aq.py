"""Outdoor-AQ veto (FR-G3): an outdoor-air actuator is blocked when the
estimated indoor PM contribution exceeds the threshold."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    CONF_FILTER_EFFICIENCY,
    CONF_MECHANISM,
    CONF_OUTDOOR_AQ_ENTITY,
    CONF_OUTDOOR_AQ_THRESHOLD,
    DOMAIN,
    Gain,
    InfluenceType,
    Mechanism,
)
from custom_components.aeolus.models import Influence

ERV = "input_boolean.erv"


async def _setup(hass: HomeAssistant, outdoor_pm: str, filter_eff: float) -> MockConfigEntry:
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"erv": {}}})
    hass.states.async_set("sensor.z_co2", "1200")  # high → wants mitigation
    hass.states.async_set("sensor.outdoor_pm", outdoor_pm)
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
                    CONF_OUTDOOR_AQ_ENTITY: "sensor.outdoor_pm",
                    CONF_OUTDOOR_AQ_THRESHOLD: 35.0,
                },
            ),
            ConfigSubentryData(
                subentry_type="actuator",
                title="ERV",
                unique_id=None,
                data={
                    CONF_ACTUATOR_ENTITY: ERV,
                    CONF_MECHANISM: Mechanism.BALANCED.value,  # outdoor air → AQ-gated
                    CONF_FILTER_EFFICIENCY: filter_eff,
                },
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    engine = entry.runtime_data.engine
    space_id = next(iter(engine.spaces))
    act_id = next(iter(engine.actuators))
    engine.actuators[act_id].influences = [
        Influence(space_id=space_id, gain=Gain.MEDIUM, influence_type=InfluenceType.DIRECT)
    ]
    engine.request_evaluation()
    await hass.async_block_till_done()
    return entry


async def test_bad_outdoor_aq_vetoes_unfiltered_erv(hass: HomeAssistant) -> None:
    await _setup(hass, outdoor_pm="100", filter_eff=0.0)  # 100 > 35 → blocked
    assert hass.states.get(ERV).state == "off"


async def test_clean_outdoor_aq_allows(hass: HomeAssistant) -> None:
    await _setup(hass, outdoor_pm="10", filter_eff=0.0)  # 10 < 35 → allowed
    assert hass.states.get(ERV).state == "on"


async def test_filtered_erv_tolerates_higher_pm(hass: HomeAssistant) -> None:
    # 100 outdoor × (1 − 0.9) = 10 indoor contribution < 35 → allowed
    await _setup(hass, outdoor_pm="100", filter_eff=0.9)
    assert hass.states.get(ERV).state == "on"

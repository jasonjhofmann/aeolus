"""Induced/pressure-edge + escalation tests (FR-L3/X3) — the canonical case:
a depressurizing exhaust helps a stuck space ONLY while a source space is lower.
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

EXHAUST = "input_boolean.exhaust"


async def _setup(hass: HomeAssistant, primary_co2: str, great_co2: str) -> MockConfigEntry:
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"exhaust": {}}})
    hass.states.async_set("sensor.p_co2", primary_co2)
    hass.states.async_set("sensor.g_co2", great_co2)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space", title="Primary", unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.p_co2"], "target_ppm": 800, "high_ppm": 1000},
            ),
            ConfigSubentryData(
                subentry_type="space", title="Great", unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.g_co2"], "target_ppm": 800, "high_ppm": 1000},
            ),
            ConfigSubentryData(
                subentry_type="actuator", title="Bath Exhaust", unique_id=None,
                data={CONF_ACTUATOR_ENTITY: EXHAUST, CONF_MECHANISM: Mechanism.EXHAUST.value},
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    engine = entry.runtime_data.engine
    by_name = {s.name: sid for sid, s in engine.spaces.items()}
    act_id = next(iter(engine.actuators))
    engine.actuators[act_id].influences = [
        Influence(
            space_id=by_name["Primary"],
            gain=Gain.MEDIUM,
            influence_type=InfluenceType.INDUCED,
            source_space_id=by_name["Great"],
            gap_margin_ppm=50.0,
        )
    ]
    engine.request_evaluation()
    await hass.async_block_till_done()
    return entry


async def test_induced_escalates_when_source_lower(hass: HomeAssistant) -> None:
    # Primary stuck high (1200), Great low (600) → exhaust pulls Great air in.
    await _setup(hass, "1200", "600")
    assert hass.states.get(EXHAUST).state == "on"


async def test_induced_blocked_when_source_not_lower(hass: HomeAssistant) -> None:
    # Both high → no clean source to draw from (FR-X3) → don't run the exhaust.
    await _setup(hass, "1200", "1200")
    assert hass.states.get(EXHAUST).state == "off"


async def test_induced_off_when_target_not_in_demand(hass: HomeAssistant) -> None:
    # Primary below its high threshold → no mitigation demand → exhaust off.
    await _setup(hass, "700", "500")
    assert hass.states.get(EXHAUST).state == "off"

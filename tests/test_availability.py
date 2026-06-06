"""entity-unavailable / log-when-unavailable: Space entities follow their
CO2 sources' availability."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import CONF_CO2_SENSORS, DOMAIN


async def test_sensor_follows_source_availability(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.z_co2", "700")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="Zone",
                unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.z_co2"], "target_ppm": 800, "high_ppm": 1000},
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    sid = next(iter(entry.runtime_data.engine.spaces))
    eid = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{sid}_co2")
    assert eid is not None
    assert float(hass.states.get(eid).state) == 700.0

    # source drops → entity unavailable (logs a warning once)
    hass.states.async_set("sensor.z_co2", STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == STATE_UNAVAILABLE

    # source recovers → entity available again (logs info once)
    hass.states.async_set("sensor.z_co2", "720")
    await hass.async_block_till_done()
    assert hass.states.get(eid).state != STATE_UNAVAILABLE

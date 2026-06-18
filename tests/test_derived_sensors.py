"""Slope + effective-ACH exposed as first-class per-Space sensors (FR-E1/E2)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import CONF_CO2_SENSORS, DOMAIN


async def test_slope_and_ach_sensors_exist(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.z_co2", "700")
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space", title="Zone", unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.z_co2"], "target_ppm": 600, "high_ppm": 700},
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    reg = er.async_get(hass)
    sid = next(iter(entry.runtime_data.engine.spaces))
    slope = reg.async_get_entity_id("sensor", DOMAIN, f"{sid}_co2_slope")
    ach = reg.async_get_entity_id("sensor", DOMAIN, f"{sid}_air_change_rate")
    assert slope is not None
    assert ach is not None
    # Slope is registered but disabled by default (also a value-sensor attribute).
    assert reg.async_get(slope).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(slope) is None
    # ACH stays enabled — it's a headline metric, not redundant with an attribute.
    assert reg.async_get(ach).disabled_by is None
    assert hass.states.get(ach) is not None

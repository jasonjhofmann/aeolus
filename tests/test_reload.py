"""Reconfiguring a subentry reloads the engine (thresholds take effect live)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus import _async_reload_on_update
from custom_components.aeolus.const import CONF_CO2_SENSORS, DOMAIN


async def test_update_listener_reloads_engine(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.z_co2", "650")
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
    engine_before = entry.runtime_data.engine

    await _async_reload_on_update(hass, entry)
    await hass.async_block_till_done()

    # Reload replaces the engine instance → fresh re-parse of subentries.
    assert entry.runtime_data.engine is not engine_before

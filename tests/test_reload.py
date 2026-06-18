"""Reconfiguring an existing subentry (same id set) reloads the engine, so its
edited data re-parses and takes effect live."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus import _async_handle_subentry_change
from custom_components.aeolus.const import CONF_CO2_SENSORS, DOMAIN


async def test_reconfigure_reloads_engine(hass: HomeAssistant) -> None:
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

    # Same subentry id set as the engine knows → a pure reconfigure → reload.
    await _async_handle_subentry_change(hass, entry)
    await hass.async_block_till_done()

    # Reload replaces the engine instance → fresh re-parse of subentries.
    assert entry.runtime_data.engine is not engine_before

"""Diagnostics dump builds and surfaces the runtime debug fields (Gold)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentry, ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    CONF_SERVED_SPACES,
    DOMAIN,
)
from custom_components.aeolus.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_dump_has_debug_fields(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.z_co2", "900")
    hass.states.async_set("switch.fan", "off")
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
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sid = next(iter(entry.runtime_data.engine.spaces))
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={
                CONF_ACTUATOR_ENTITY: "switch.fan",
                "mechanism": "exhaust",
                CONF_SERVED_SPACES: [sid],
            },
            subentry_type="actuator",
            title="Fan",
            unique_id=None,
        ),
    )
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert {
        "min_on_sec",
        "min_off_sec",
        "override_window_sec",
        "spaces",
        "actuators",
    } <= diag.keys()
    space = diag["spaces"][0]
    assert {"effective_ach", "time_to_target_min", "status", "reason"} <= space.keys()
    metric = space["metrics"][0]
    assert {"stale", "last_member_seen", "last_raw", "value"} <= metric.keys()
    actuator = diag["actuators"][0]
    assert {
        "outdoor_air_vetoed",
        "max_runtime_exceeded",
        "is_overridden",
    } <= actuator.keys()

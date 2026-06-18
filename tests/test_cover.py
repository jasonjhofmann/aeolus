"""Cover/window actuator branch: command_actuator selects open/close_cover."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    DOMAIN,
)

COVER = "cover.window"


async def test_cover_actuator_command_branch(hass: HomeAssistant) -> None:
    # Register the cover services the engine dispatches; otherwise HA raises
    # ServiceNotFound eagerly when command_actuator opens the cover.
    async_mock_service(hass, "cover", SERVICE_OPEN_COVER)
    async_mock_service(hass, "cover", SERVICE_CLOSE_COVER)
    hass.states.async_set("sensor.z_co2", "1200")
    hass.states.async_set(COVER, "closed")
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
            ConfigSubentryData(
                subentry_type="actuator",
                title="Window",
                unique_id=None,
                data={CONF_ACTUATOR_ENTITY: COVER, "mechanism": "window"},
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    engine = entry.runtime_data.engine
    sid = next(iter(engine.spaces))
    aid = next(iter(engine.actuators))
    engine.spaces[sid].metrics[0].tiers[0].setpoints[aid] = 100
    engine.request_evaluation()
    await hass.async_block_till_done()
    # cover branch of command_actuator executed (open_cover dispatched)
    assert engine.actuator_runtime(aid).commanded_on is True

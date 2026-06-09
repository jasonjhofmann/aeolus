"""Config-flow + end-to-end setup tests (Bronze: config-flow-test-coverage).

Runs against a real HA test `hass`, so it also catches import/API mismatches
that compile-checking can't.
"""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER, ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import CONF_CO2_SENSORS, DOMAIN


async def test_user_flow_creates_single_entry(hass: HomeAssistant) -> None:
    """The parent flow creates one 'Aeolus' manager entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Aeolus"


async def test_single_instance_only(hass: HomeAssistant) -> None:
    """A second manager entry aborts (unique-config-entry)."""
    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_setup_with_space_creates_co2_sensor(hass: HomeAssistant) -> None:
    """A Space subentry yields a Space CO2 sensor that reflects the source EMA."""
    hass.states.async_set("sensor.office_co2", "650")

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Aeolus",
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="Office",
                unique_id=None,
                data={
                    CONF_CO2_SENSORS: ["sensor.office_co2"],
                    "target_ppm": 800,
                    "high_ppm": 1000,
                },
            )
        ],
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.office_managed_co2")  # managed value (no bare default)
    assert state is not None
    assert float(state.state) == 650.0  # seeded EMA == first sample

"""Subentry-flow tests (Bronze config-flow-test-coverage): Space + Actuator."""

from __future__ import annotations

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigSubentryData,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import CONF_CO2_SENSORS, DOMAIN


async def _manager(hass: HomeAssistant, **kw) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={}, **kw)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_add_space_subentry(hass: HomeAssistant) -> None:
    entry = await _manager(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "space"), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Office",
            CONF_CO2_SENSORS: ["sensor.office_co2"],
            "aggregation": "mean",
            "target_ppm": 800,
            "high_ppm": 1000,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert any(
        s.subentry_type == "space" and s.title == "Office"
        for s in entry.subentries.values()
    )


async def test_add_actuator_subentry(hass: HomeAssistant) -> None:
    entry = await _manager(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "actuator"), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "ERV", "actuator_entity": "switch.erv", "mechanism": "balanced"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert any(s.subentry_type == "actuator" for s in entry.subentries.values())


async def test_reconfigure_space_subentry(hass: HomeAssistant) -> None:
    entry = await _manager(
        hass,
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="Office",
                unique_id=None,
                data={
                    CONF_CO2_SENSORS: ["sensor.o"],
                    "target_ppm": 800,
                    "high_ppm": 1000,
                },
            )
        ],
    )
    sub_id = next(
        s.subentry_id for s in entry.subentries.values() if s.subentry_type == "space"
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "space"),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": sub_id},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Office",
            CONF_CO2_SENSORS: ["sensor.o"],
            "aggregation": "mean",
            "target_ppm": 750,
            "high_ppm": 950,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries[sub_id].data["target_ppm"] == 750


async def test_add_space_rejects_high_not_above_target(hass: HomeAssistant) -> None:
    """FR-C3: High must be above Target (non-empty deadband) — rejected in-flow."""
    entry = await _manager(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "space"), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Bad",
            CONF_CO2_SENSORS: ["sensor.x"],
            "aggregation": "mean",
            "target_ppm": 1000,
            "high_ppm": 800,  # <= target → invalid
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"high_ppm": "high_not_above_target"}
    assert not any(s.subentry_type == "space" for s in entry.subentries.values())


async def test_add_actuator_rejects_filter_serving_co2(hass: HomeAssistant) -> None:
    """FR-C8/P5: a Filter (recirculating purifier) can't be assigned CO₂ duty."""
    entry = await _manager(
        hass,
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="Zone",
                unique_id=None,
                data={
                    CONF_CO2_SENSORS: ["sensor.z"],
                    "target_ppm": 800,
                    "high_ppm": 1000,
                },
            )
        ],
    )
    sid = next(
        s.subentry_id for s in entry.subentries.values() if s.subentry_type == "space"
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "actuator"), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Purifier",
            "actuator_entity": "fan.purifier",
            "mechanism": "filter",
            "served_spaces": [sid],  # filter + CO₂ duty → invalid
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"served_spaces": "filter_cannot_serve_co2"}

    # A filter with NO served_spaces (PM-only) is accepted.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Purifier",
            "actuator_entity": "fan.purifier",
            "mechanism": "filter",
            "served_spaces": [],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_reconfigure_actuator_subentry(hass: HomeAssistant) -> None:
    entry = await _manager(
        hass,
        subentries_data=[
            ConfigSubentryData(
                subentry_type="actuator",
                title="ERV",
                unique_id=None,
                data={"actuator_entity": "switch.erv", "mechanism": "balanced"},
            )
        ],
    )
    sub_id = next(
        s.subentry_id
        for s in entry.subentries.values()
        if s.subentry_type == "actuator"
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "actuator"),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": sub_id},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "ERV",
            "actuator_entity": "switch.erv",
            "mechanism": "supply",
            "filter_efficiency": 0.5,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries[sub_id].data["mechanism"] == "supply"

"""repair-issues: a missing configured entity raises an actionable issue (Gold)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus import _async_sync_missing_entity_issues
from custom_components.aeolus.const import CONF_CO2_SENSORS, DOMAIN


def _space_entry(sensor: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space", title="Zone", unique_id=None,
                data={CONF_CO2_SENSORS: [sensor], "target_ppm": 600, "high_ppm": 700},
            )
        ],
    )


async def test_missing_source_raises_issue(hass: HomeAssistant) -> None:
    # The configured CO2 sensor was never created (deleted/renamed).
    entry = _space_entry("sensor.gone")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    reg = ir.async_get(hass)
    issue_id = f"missing_entity_{entry.entry_id}_sensor.gone"
    issue = reg.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "missing_entity"
    assert issue.translation_placeholders == {
        "entity_id": "sensor.gone",
        "name": "Zone",
        "kind": "sensor",
    }


async def test_present_source_raises_no_issue(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.here", "650")
    entry = _space_entry("sensor.here")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    reg = ir.async_get(hass)
    issue_id = f"missing_entity_{entry.entry_id}_sensor.here"
    assert reg.async_get_issue(DOMAIN, issue_id) is None


async def test_issue_cleared_when_entity_returns(hass: HomeAssistant) -> None:
    entry = _space_entry("sensor.gone")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    reg = ir.async_get(hass)
    issue_id = f"missing_entity_{entry.entry_id}_sensor.gone"
    assert reg.async_get_issue(DOMAIN, issue_id) is not None

    # The user recreates the entity; a re-check clears the stale issue.
    hass.states.async_set("sensor.gone", "600")
    engine = entry.runtime_data.engine
    _async_sync_missing_entity_issues(hass, entry, engine.spaces, engine.actuators)
    assert reg.async_get_issue(DOMAIN, issue_id) is None

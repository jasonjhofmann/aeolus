"""Entity IDs belong to the user once registered.

Setup, reload, and Space rename must never rewrite an Aeolus entity_id: not one
the user chose, not one HA generated on a fresh install.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import (
    CONF_CO2_SENSORS,
    CONF_METRIC_KIND,
    CONF_METRIC_SENSORS,
    CONF_METRICS,
    CONF_TIER_ENGAGE,
    CONF_TIERS,
    DOMAIN,
)


async def _setup_zone(
    hass: HomeAssistant, metrics: list[dict] | None = None
) -> tuple[MockConfigEntry, str]:
    """A CO₂ Space "Zone" (plus any extra metrics), set up and settled."""
    hass.states.async_set("sensor.z_co2", "700")
    hass.states.async_set("sensor.z_aqi", "40")
    hass.states.async_set("sensor.z_level", "3")
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
                    CONF_METRICS: metrics or [],
                },
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sid = next(
        s.subentry_id for s in entry.subentries.values() if s.subentry_type == "space"
    )
    return entry, sid


def _entity_ids(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, str]:
    """unique_id → entity_id for every registry row the entry owns."""
    reg = er.async_get(hass)
    return {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(reg, entry.entry_id)
    }


async def test_user_chosen_entity_id_survives_reload(hass: HomeAssistant) -> None:
    """A user rename of an Aeolus entity sticks across reload (and so restart)."""
    entry, sid = await _setup_zone(hass)
    reg = er.async_get(hass)
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{sid}_co2")
        == "sensor.zone_managed_co2"
    )
    reg.async_update_entity("sensor.zone_managed_co2", new_entity_id="sensor.my_co2")

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert reg.async_get_entity_id("sensor", DOMAIN, f"{sid}_co2") == "sensor.my_co2"
    assert hass.states.get("sensor.my_co2") is not None


async def test_space_rename_keeps_entity_ids(hass: HomeAssistant) -> None:
    """Renaming a Space (subentry title) reloads but leaves every entity_id alone."""
    entry, _ = await _setup_zone(hass)
    before = _entity_ids(hass, entry)
    subentry = next(s for s in entry.subentries.values() if s.subentry_type == "space")

    assert hass.config_entries.async_update_subentry(entry, subentry, title="Den")
    await hass.async_block_till_done()

    assert _entity_ids(hass, entry) == before


async def test_fresh_entity_ids_stable_across_reload(hass: HomeAssistant) -> None:
    """IDs a fresh install generates from the translated names are the final IDs.

    Covers the names whose slug differs from the unique_id suffix ("Managed AQI
    trend" for `aqi_slope`, "Level" for `generic`)."""
    entry, sid = await _setup_zone(
        hass,
        metrics=[
            {
                CONF_METRIC_KIND: "aqi",
                CONF_METRIC_SENSORS: ["sensor.z_aqi"],
                CONF_TIERS: [{CONF_TIER_ENGAGE: 100}],
            },
            {
                CONF_METRIC_KIND: "generic",
                CONF_METRIC_SENSORS: ["sensor.z_level"],
                CONF_TIERS: [{CONF_TIER_ENGAGE: 10}],
            },
        ],
    )
    before = _entity_ids(hass, entry)
    assert before[f"{sid}_aqi_slope"] == "sensor.zone_managed_aqi_trend"
    assert before[f"{sid}_generic"] == "sensor.zone_managed_level"
    assert before[f"{sid}_generic_slope"] == "sensor.zone_managed_level_slope"
    assert before[f"{sid}_generic_threshold"] == "number.zone_level_threshold"
    assert before[f"{sid}_manage_generic"] == "switch.zone_manage_level"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert _entity_ids(hass, entry) == before

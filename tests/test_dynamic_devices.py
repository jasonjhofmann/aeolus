"""dynamic-devices + stale-devices: Space/Actuator subentries are added and
removed live, without reloading the entry."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.config_entries import ConfigSubentry, ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus import async_remove_config_entry_device
from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    CONF_SERVED_SPACES,
    DOMAIN,
)


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set("sensor.a_co2", "650")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="Room A",
                unique_id=None,
                data={
                    CONF_CO2_SENSORS: ["sensor.a_co2"],
                    "target_ppm": 800,
                    "high_ppm": 1000,
                },
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_add_space_subentry_live(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine_before = entry.runtime_data.engine
    hass.states.async_set("sensor.b_co2", "700")

    sub = ConfigSubentry(
        data={CONF_CO2_SENSORS: ["sensor.b_co2"], "target_ppm": 800, "high_ppm": 1000},
        subentry_type="space",
        title="Room B",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(entry, sub)
    await hass.async_block_till_done()

    # No reload: the same engine instance now knows the new Space.
    assert entry.runtime_data.engine is engine_before
    assert sub.subentry_id in entry.runtime_data.engine.spaces

    # Its device and entities exist.
    assert (
        dr.async_get(hass).async_get_device(identifiers={(DOMAIN, sub.subentry_id)})
        is not None
    )
    reg = er.async_get(hass)
    assert (
        reg.async_get_entity_id("sensor", DOMAIN, f"{sub.subentry_id}_co2") is not None
    )
    assert (
        reg.async_get_entity_id("select", DOMAIN, f"{sub.subentry_id}_mode") is not None
    )


async def test_remove_space_subentry_live(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine_before = entry.runtime_data.engine
    sid = next(iter(engine_before.spaces))
    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, sid)}) is not None

    hass.config_entries.async_remove_subentry(entry, sid)
    await hass.async_block_till_done()

    # No reload; engine dropped the Space; HA cleared its device + entities.
    assert entry.runtime_data.engine is engine_before
    assert sid not in entry.runtime_data.engine.spaces
    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, sid)}) is None


async def test_add_actuator_wires_co2_setpoint_live(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine = entry.runtime_data.engine
    sid = next(iter(engine.spaces))
    hass.states.async_set("switch.fan", "off")

    sub = ConfigSubentry(
        data={
            CONF_ACTUATOR_ENTITY: "switch.fan",
            "mechanism": "exhaust",
            CONF_SERVED_SPACES: [sid],
        },
        subentry_type="actuator",
        title="Fan",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(entry, sub)
    await hass.async_block_till_done()

    assert entry.runtime_data.engine is engine  # no reload
    assert sub.subentry_id in engine.actuators
    # The actuator is wired into Room A's synthesized CO2 tier (default speed 100).
    assert engine.spaces[sid].metrics[0].tiers[0].setpoints.get(sub.subentry_id) == 100


async def test_remove_actuator_purges_setpoint_live(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    engine = entry.runtime_data.engine
    sid = next(iter(engine.spaces))
    hass.states.async_set("switch.fan", "off")
    sub = ConfigSubentry(
        data={
            CONF_ACTUATOR_ENTITY: "switch.fan",
            "mechanism": "exhaust",
            CONF_SERVED_SPACES: [sid],
        },
        subentry_type="actuator",
        title="Fan",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(entry, sub)
    await hass.async_block_till_done()
    assert sub.subentry_id in engine.spaces[sid].metrics[0].tiers[0].setpoints

    hass.config_entries.async_remove_subentry(entry, sub.subentry_id)
    await hass.async_block_till_done()
    assert sub.subentry_id not in engine.actuators
    assert sub.subentry_id not in engine.spaces[sid].metrics[0].tiers[0].setpoints


async def test_async_remove_config_entry_device(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    sid = next(iter(entry.runtime_data.engine.spaces))
    dev_reg = dr.async_get(hass)
    space_dev = dev_reg.async_get_device(identifiers={(DOMAIN, sid)})
    manager_dev = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert space_dev is not None and manager_dev is not None

    # Live Space device + manager device are protected from manual deletion.
    assert await async_remove_config_entry_device(hass, entry, space_dev) is False
    assert await async_remove_config_entry_device(hass, entry, manager_dev) is False
    # An orphan device (subentry no longer present) is removable.
    orphan = SimpleNamespace(identifiers={(DOMAIN, "ORPHAN00000000000000000000")})
    assert await async_remove_config_entry_device(hass, entry, orphan) is True  # type: ignore[arg-type]

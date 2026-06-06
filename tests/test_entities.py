"""Control/status entity tests + unload."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.aeolus.const import CONF_CO2_SENSORS, DOMAIN, SpaceMode


async def _setup_space(hass: HomeAssistant) -> tuple[MockConfigEntry, str]:
    hass.states.async_set("sensor.z_co2", "700")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="Zone",
                unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.z_co2"], "target_ppm": 800, "high_ppm": 1000},
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    space_id = next(iter(entry.runtime_data.engine.spaces))
    return entry, space_id


def _eid(hass: HomeAssistant, domain: str, unique: str) -> str:
    eid = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique)
    assert eid is not None, f"no entity for {domain} {unique}"
    return eid


async def test_target_number_updates_space(hass: HomeAssistant) -> None:
    entry, sid = await _setup_space(hass)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": _eid(hass, "number", f"{sid}_target"), "value": 760},
        blocking=True,
    )
    assert entry.runtime_data.engine.spaces[sid].target_ppm == 760


async def test_mode_select_off(hass: HomeAssistant) -> None:
    entry, sid = await _setup_space(hass)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": _eid(hass, "select", f"{sid}_mode"), "option": "off"},
        blocking=True,
    )
    assert entry.runtime_data.engine.spaces[sid].mode is SpaceMode.OFF


async def test_master_switch_pauses(hass: HomeAssistant) -> None:
    entry, _ = await _setup_space(hass)
    eid = _eid(hass, "switch", f"{entry.entry_id}_management")
    await hass.services.async_call("switch", "turn_off", {"entity_id": eid}, blocking=True)
    assert entry.runtime_data.engine.paused is True
    await hass.services.async_call("switch", "turn_on", {"entity_id": eid}, blocking=True)
    assert entry.runtime_data.engine.paused is False


async def test_space_sensor_attributes(hass: HomeAssistant) -> None:
    _, sid = await _setup_space(hass)
    state = hass.states.get(_eid(hass, "sensor", f"{sid}_co2"))
    assert state is not None
    assert float(state.state) == 700.0
    assert "co2_slope_per_min" in state.attributes
    assert "effective_ach" in state.attributes
    assert state.attributes["target_ppm"] == 800


async def test_unload_entry(hass: HomeAssistant) -> None:
    entry, _ = await _setup_space(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensor_restores_ema_across_restart(hass: HomeAssistant) -> None:
    # Pre-seed the restore cache for the Space CO2 sensor, then set up with NO
    # live source state — the sensor should seed its EMA from the restored value.
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State("sensor.zone", "760"),
                {"native_value": 760.0, "native_unit_of_measurement": "ppm"},
            ),
        ),
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="Zone",
                unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.z_co2"], "target_ppm": 800, "high_ppm": 1000},
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.zone").state) == 760.0

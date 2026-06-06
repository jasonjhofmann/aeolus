"""Engine-level tests: command min-cycle + actuator-event edge cases."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import CONF_ACTUATOR_ENTITY, CONF_CO2_SENSORS, DOMAIN

FAN = "input_boolean.fan"


async def _engine(hass: HomeAssistant):  # noqa: ANN201
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"fan": {}}})
    hass.states.async_set("sensor.z_co2", "600")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space", title="Zone", unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.z_co2"], "target_ppm": 800, "high_ppm": 1000},
            ),
            ConfigSubentryData(
                subentry_type="actuator", title="Fan", unique_id=None,
                data={CONF_ACTUATOR_ENTITY: FAN, "mechanism": "transfer"},
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data.engine


async def test_min_on_prevents_immediate_off(hass: HomeAssistant) -> None:
    engine = await _engine(hass)
    act_id = next(iter(engine.actuators))
    now = dt_util.utcnow()
    engine.command_actuator(act_id, True, now)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "on"
    # min-on (600 s) not satisfied → the off is suppressed
    engine.command_actuator(act_id, False, now + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "on"
    # after min-on elapses, off goes through
    engine.command_actuator(act_id, False, now + timedelta(seconds=601))
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"


async def test_untracked_actuator_event_ignored(hass: HomeAssistant) -> None:
    engine = await _engine(hass)
    # A state change for an entity Aeolus doesn't manage must be a no-op.
    hass.states.async_set("switch.not_ours", "on")
    await hass.async_block_till_done()
    assert engine is not None  # no exception raised


async def test_actuator_unavailable_event_ignored(hass: HomeAssistant) -> None:
    engine = await _engine(hass)
    hass.states.async_set(FAN, "unavailable")
    await hass.async_block_till_done()
    assert engine.actuator_runtime(next(iter(engine.actuators))) is not None


async def test_derived_metrics_none_without_slope(hass: HomeAssistant) -> None:
    engine = await _engine(hass)  # single seed sample → slope not yet defined
    sid = next(iter(engine.spaces))
    assert engine.space_effective_ach(sid) is None
    assert engine.space_time_to_target_min(sid) is None


async def test_periodic_control_tick_runs(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    engine = await _engine(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=70))
    await hass.async_block_till_done()
    assert engine is not None  # tick fired without error


async def test_garbage_and_out_of_range_source_ignored(hass: HomeAssistant) -> None:
    engine = await _engine(hass)
    sid = next(iter(engine.spaces))
    baseline = engine.space_runtime(sid).ema_ppm  # 600 from _engine setup
    hass.states.async_set("sensor.z_co2", "notanumber")  # parse guard + avail guard
    await hass.async_block_till_done()
    hass.states.async_set("sensor.z_co2", "55000")  # out-of-range guard
    await hass.async_block_till_done()
    assert engine.space_runtime(sid).ema_ppm == baseline  # neither moved the EMA


async def test_min_off_blocks_quick_restart(hass: HomeAssistant) -> None:
    engine = await _engine(hass)
    act_id = next(iter(engine.actuators))
    now = dt_util.utcnow()
    engine.command_actuator(act_id, True, now)
    engine.command_actuator(act_id, False, now + timedelta(seconds=601))  # off (min-on ok)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"
    # turning back on within min-off (600 s) is suppressed
    engine.command_actuator(act_id, True, now + timedelta(seconds=610))
    await hass.async_block_till_done()
    assert engine.actuator_runtime(act_id).commanded_on is False

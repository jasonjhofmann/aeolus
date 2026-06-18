"""FR-L7b override confirmation window — ignore transient cloud-actuator flaps."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    CONF_OVERRIDE_GRACE_MIN,
    CONF_SERVED_SPACES,
    DOMAIN,
)

ACT = "switch.cloud_fan"


async def _engine(hass: HomeAssistant, grace_min: float):
    hass.states.async_set("sensor.z_co2", "650")
    hass.states.async_set(ACT, "off")
    data = {CONF_ACTUATOR_ENTITY: ACT, "mechanism": "exhaust", CONF_SERVED_SPACES: []}
    if grace_min:
        data[CONF_OVERRIDE_GRACE_MIN] = grace_min
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
                    "target_ppm": 600,
                    "high_ppm": 700,
                },
            ),
            ConfigSubentryData(
                subentry_type="actuator", title="CloudFan", unique_id=None, data=data
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    engine = entry.runtime_data.engine
    aid = next(iter(engine.actuators))
    engine.command_actuator(aid, True, dt_util.utcnow())  # commanded on
    hass.states.async_set(ACT, "on")
    await hass.async_block_till_done()
    return engine, aid


async def test_grace_ignores_transient_flap(hass: HomeAssistant) -> None:
    engine, aid = await _engine(hass, 2)
    hass.states.async_set(ACT, "off")  # cloud flap → divergence
    await hass.async_block_till_done()
    assert engine.actuator_runtime(aid).divergence_since is not None
    assert engine.actuator_is_overridden(aid, dt_util.utcnow()) is False  # not yet
    hass.states.async_set(ACT, "on")  # flap clears within grace
    await hass.async_block_till_done()
    assert engine.actuator_runtime(aid).divergence_since is None
    assert engine.actuator_is_overridden(aid, dt_util.utcnow()) is False  # ignored


async def test_grace_confirms_persistent_override(hass: HomeAssistant) -> None:
    engine, aid = await _engine(hass, 2)
    hass.states.async_set(ACT, "off")  # real manual change, persists
    await hass.async_block_till_done()
    since = engine.actuator_runtime(aid).divergence_since
    assert since is not None
    later = since + timedelta(minutes=3)
    engine._promote_pending_overrides(later)
    assert engine.actuator_is_overridden(aid, later) is True


async def test_grace_zero_is_immediate(hass: HomeAssistant) -> None:
    engine, aid = await _engine(hass, 0)  # default behavior
    hass.states.async_set(ACT, "off")
    await hass.async_block_till_done()
    assert engine.actuator_is_overridden(aid, dt_util.utcnow()) is True

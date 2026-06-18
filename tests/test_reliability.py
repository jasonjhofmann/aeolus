"""Reliability regressions found in the 2026-06-17 sweep.

- A cover's transient `opening`/`closing` state must NOT be read as a manual
  override of Aeolus's own open/close command.
- An out-of-range-only source must NOT stamp freshness, so the stale-sensor
  safety check still trips.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import SERVICE_CLOSE_COVER, SERVICE_OPEN_COVER
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
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


async def test_cover_transient_state_no_false_override(hass: HomeAssistant) -> None:
    async_mock_service(hass, "cover", SERVICE_OPEN_COVER)
    async_mock_service(hass, "cover", SERVICE_CLOSE_COVER)
    hass.states.async_set("sensor.z_co2", "1200")
    hass.states.async_set(COVER, "closed")
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space", title="Zone", unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.z_co2"], "target_ppm": 800, "high_ppm": 1000},
            ),
            ConfigSubentryData(
                subentry_type="actuator", title="Window", unique_id=None,
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
    assert engine.actuator_runtime(aid).commanded_on is True

    # The cover passes through `opening` while executing Aeolus's own open command:
    # this must NOT be mistaken for a manual override.
    hass.states.async_set(COVER, "opening")
    await hass.async_block_till_done()
    assert engine.actuator_is_overridden(aid, dt_util.utcnow()) is False

    # Reaching the terminal `open` (== commanded) likewise leaves it un-overridden.
    hass.states.async_set(COVER, "open")
    await hass.async_block_till_done()
    assert engine.actuator_is_overridden(aid, dt_util.utcnow()) is False


async def test_out_of_range_only_source_is_not_marked_fresh(hass: HomeAssistant) -> None:
    # A CO2 sensor that only ever reports an out-of-range value (garbage) must not
    # stamp member_seen — otherwise is_stale() would treat the metric as fresh.
    hass.states.async_set("sensor.z_co2", "999999")  # > the 40000 ppm CO2 ceiling
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space", title="Zone", unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.z_co2"], "target_ppm": 800, "high_ppm": 1000},
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    engine = entry.runtime_data.engine
    sid = next(iter(engine.spaces))
    mrt = engine.metric_runtime(sid, 0)
    assert mrt is not None
    assert mrt.member_seen == {}  # never stamped from a garbage reading
    assert engine.space_available(sid) is False

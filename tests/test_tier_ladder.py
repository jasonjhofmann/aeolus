"""v3 acceptance — graduated PM ladder (FR-T) + the filter-can't-reduce-CO₂ gate (FR-P5).

Drives the metric EMA directly (deterministic, no time-advance) and asserts the
controller's per-actuator setpoints. Min on/off are zeroed so the ramp-down to
off isn't blocked by the cycle gate (which has its own tests).
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    CONF_MECHANISM,
    CONF_METRIC_KIND,
    CONF_METRIC_SENSORS,
    CONF_METRICS,
    DOMAIN,
)
from custom_components.aeolus.models import Tier


async def test_kitchen_pm_ladder(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.kpm", "5")
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space", title="Kitchen", unique_id=None,
                data={CONF_METRICS: [{CONF_METRIC_KIND: "pm2_5", CONF_METRIC_SENSORS: ["sensor.kpm"]}]},
            ),
            ConfigSubentryData(subentry_type="actuator", title="Hood", unique_id=None,
                data={CONF_ACTUATOR_ENTITY: "fan.hood", CONF_MECHANISM: "exhaust"}),
            ConfigSubentryData(subentry_type="actuator", title="Purifiers", unique_id=None,
                data={CONF_ACTUATOR_ENTITY: "fan.purifier", CONF_MECHANISM: "filter"}),
            ConfigSubentryData(subentry_type="actuator", title="Mud exhaust", unique_id=None,
                data={CONF_ACTUATOR_ENTITY: "input_boolean.mud", CONF_MECHANISM: "exhaust"}),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    eng = entry.runtime_data.engine
    eng.min_on = eng.min_off = timedelta(0)  # isolate the ladder from the cycle gates
    for domain in ("fan", "input_boolean"):  # absorb the fire-and-forget commands
        async_mock_service(hass, domain, "turn_on")
        async_mock_service(hass, domain, "turn_off")

    sid = next(iter(eng.spaces))
    hood = next(a for a in eng.actuators if eng.actuators[a].name == "Hood")
    pur = next(a for a in eng.actuators if eng.actuators[a].name == "Purifiers")
    mud = next(a for a in eng.actuators if eng.actuators[a].name == "Mud exhaust")
    eng.spaces[sid].metrics[0].tiers = [
        Tier(engage_at=30, release_at=25, setpoints={hood: 20, pur: 33}),
        Tier(engage_at=50, release_at=42, setpoints={hood: 40, pur: 66}),
        Tier(engage_at=80, release_at=68, setpoints={hood: 100, pur: 100, mud: 100}),
    ]
    mrt = eng.space_runtime(sid).metrics[0]

    def drive(value: float) -> dict[str, int]:
        mrt.member_seen["sensor.kpm"] = dt_util.utcnow()
        mrt.ema._ema = float(value)  # noqa: SLF001 — force the smoothed value
        eng.request_evaluation()
        return {a: eng.actuator_runtime(a).commanded_setpoint for a in (hood, pur, mud)}

    assert drive(35) == {hood: 20, pur: 33, mud: 0}     # tier 1
    assert drive(90) == {hood: 100, pur: 100, mud: 100}  # jump to tier 3 — all on, max speed
    assert drive(70) == {hood: 100, pur: 100, mud: 100}  # 70 > release 68 → holds (hysteresis)
    assert drive(40) == {hood: 20, pur: 33, mud: 0}      # ramp down to tier 1; mud off
    assert drive(5) == {hood: 0, pur: 0, mud: 0}         # below tier-1 release → all off


async def test_filter_rejected_for_co2(hass: HomeAssistant) -> None:
    """A recirculating purifier must NOT be driven for a CO₂ metric (FR-P5)."""
    hass.states.async_set("sensor.z_co2", "1200")
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={},
        subentries_data=[
            ConfigSubentryData(subentry_type="space", title="Zone", unique_id=None,
                data={CONF_CO2_SENSORS: ["sensor.z_co2"], "target_ppm": 800, "high_ppm": 1000}),
            ConfigSubentryData(subentry_type="actuator", title="Purifier", unique_id=None,
                data={CONF_ACTUATOR_ENTITY: "fan.purifier", CONF_MECHANISM: "filter"}),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    eng = entry.runtime_data.engine
    sid = next(iter(eng.spaces))
    pur = next(iter(eng.actuators))
    eng.spaces[sid].metrics[0].tiers[0].setpoints[pur] = 100  # try to drive it for CO₂
    eng.request_evaluation()
    await hass.async_block_till_done()
    assert eng.actuator_runtime(pur).commanded_setpoint == 0  # filter can't reduce CO₂

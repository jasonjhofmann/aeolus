"""Tests for the safety guardrails (FR-G*)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant

from custom_components.aeolus.const import Mechanism
from custom_components.aeolus.ema import SlopeTracker, TimeAwareEMA
from custom_components.aeolus.engine import ActuatorRuntime, SpaceRuntime
from custom_components.aeolus.models import Actuator, Space
from custom_components.aeolus.safety import (
    is_space_stale,
    max_runtime_exceeded,
    outdoor_air_vetoed,
    outdoor_aq_blocks,
)

T = datetime(2026, 1, 1, 12, tzinfo=UTC)


def _rt() -> SpaceRuntime:
    return SpaceRuntime(
        ema=TimeAwareEMA(300), slope=SlopeTracker(smoothing_halflife_sec=300)
    )


def test_stale_when_no_members():
    assert is_space_stale(_rt(), T) is True


def test_not_stale_when_recent():
    rt = _rt()
    rt.member_seen["s"] = T
    assert is_space_stale(rt, T + timedelta(seconds=60)) is False


def test_stale_after_window():
    rt = _rt()
    rt.member_seen["s"] = T
    assert is_space_stale(rt, T + timedelta(seconds=2000)) is True


def test_outdoor_aq_blocks_is_filter_aware():
    assert outdoor_aq_blocks(100.0, 0.0, 35.0) is True  # unfiltered over threshold
    assert outdoor_aq_blocks(100.0, 0.9, 35.0) is False  # 90%-filtered → 10 < 35


def test_max_runtime():
    art = ActuatorRuntime(commanded_on=True, on_since=T)
    act = Actuator(
        subentry_id="a", name="A", entity_id="switch.x",
        mechanism=Mechanism.EXHAUST, max_runtime_min=10.0,
    )
    assert max_runtime_exceeded(art, act, T + timedelta(minutes=11)) is True
    assert max_runtime_exceeded(art, act, T + timedelta(minutes=5)) is False


async def test_outdoor_air_vetoed_per_pathway(hass: HomeAssistant) -> None:
    space = Space(
        subentry_id="s", name="S", co2_sensors=[],
        outdoor_aq_entity="sensor.pm", outdoor_aq_threshold=35.0,
    )
    erv = Actuator(
        subentry_id="a", name="ERV", entity_id="switch.erv",
        mechanism=Mechanism.BALANCED, filter_efficiency=0.0,
    )
    hass.states.async_set("sensor.pm", "100")
    assert outdoor_air_vetoed(hass, erv, space) is True  # unfiltered, over

    erv.filter_efficiency = 0.9  # filtered intake tolerates it
    assert outdoor_air_vetoed(hass, erv, space) is False

    transfer = Actuator(
        subentry_id="a2", name="T", entity_id="fan.t", mechanism=Mechanism.TRANSFER,
    )
    assert outdoor_air_vetoed(hass, transfer, space) is False  # not outdoor air


async def test_outdoor_air_not_vetoed_without_config(hass: HomeAssistant) -> None:
    space = Space(subentry_id="s", name="S", co2_sensors=[])  # no AQ entity/threshold
    erv = Actuator(
        subentry_id="a", name="E", entity_id="switch.e", mechanism=Mechanism.SUPPLY
    )
    assert outdoor_air_vetoed(hass, erv, space) is False


async def test_outdoor_air_fail_safe_on_unreadable_sensor(hass: HomeAssistant) -> None:
    space = Space(
        subentry_id="s", name="S", co2_sensors=[],
        outdoor_aq_entity="sensor.pm", outdoor_aq_threshold=35.0,
    )
    erv = Actuator(
        subentry_id="a", name="E", entity_id="switch.e", mechanism=Mechanism.SUPPLY
    )
    assert outdoor_air_vetoed(hass, erv, space) is False  # missing state → don't strand
    hass.states.async_set("sensor.pm", "unknown")
    assert outdoor_air_vetoed(hass, erv, space) is False
    hass.states.async_set("sensor.pm", "notanumber")
    assert outdoor_air_vetoed(hass, erv, space) is False

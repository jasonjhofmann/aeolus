"""Attention-status correctness (FR-E6): no flapping, no status/reason contradiction.

Regression guard for the bug where a metric resting in its hysteresis band
(between release and engage) reported status "attention" while the reason said
"OK — all metrics within range," flapping on every slope sign-flip.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    DOMAIN,
)

FAN = "input_boolean.fan"
CO2 = "sensor.z_co2"


async def _engine(hass: HomeAssistant):
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"fan": {}}})
    hass.states.async_set(CO2, "600")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="Zone",
                unique_id=None,
                data={CONF_CO2_SENSORS: [CO2], "target_ppm": 800, "high_ppm": 1000},
            ),
            ConfigSubentryData(
                subentry_type="actuator",
                title="Fan",
                unique_id=None,
                data={CONF_ACTUATOR_ENTITY: FAN, "mechanism": "transfer"},
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data.engine


def _drive(engine, value: float) -> None:
    """Pin the metric EMA to `value` (fresh) and run one control evaluation.

    Tiers for this space are engage 1000 / release 800, so 800 < value < 1000 is
    the hysteresis band that used to false-trigger attention.
    """
    sid = next(iter(engine.spaces))
    mrt = engine.space_runtime(sid).metrics[0]
    mrt.member_seen[CO2] = dt_util.utcnow()
    mrt.ema._ema = float(value)
    engine.request_evaluation()


async def test_band_resting_is_ok_not_attention(hass: HomeAssistant) -> None:
    """A value in the hysteresis band (never engaged) is OK, not attention."""
    engine = await _engine(hass)
    sid = next(iter(engine.spaces))
    _drive(engine, 900)  # 800 < 900 < 1000 → no tier engaged

    assert engine.space_runtime(sid).metrics[0].active_tier == -1
    assert engine.space_attention(sid) is False
    assert engine.space_status(sid) == "ok"
    assert engine.space_reason(sid) == "OK — all metrics within range"


async def test_band_noise_does_not_flap_attention(hass: HomeAssistant) -> None:
    """Sensor noise around a band value must not toggle attention (the 167×/day bug)."""
    engine = await _engine(hass)
    sid = next(iter(engine.spaces))
    for value in (899, 901, 900, 902, 898, 900):
        _drive(engine, value)
        assert engine.space_attention(sid) is False
        assert engine.space_status(sid) == "ok"


async def test_status_reason_never_contradict(hass: HomeAssistant) -> None:
    """Across the value range, "attention" status never pairs with an OK reason."""
    engine = await _engine(hass)
    sid = next(iter(engine.spaces))
    for value in (500, 750, 850, 900, 999, 1001, 1500):
        _drive(engine, value)
        status = engine.space_status(sid)
        reason = engine.space_reason(sid)
        if status == "attention":
            assert not reason.startswith("OK"), f"@{value}: {reason!r}"


async def test_engaged_metric_is_mitigating_with_matching_reason(
    hass: HomeAssistant,
) -> None:
    """Over the engage threshold → status mitigating, reason explains it (not OK)."""
    engine = await _engine(hass)
    sid = next(iter(engine.spaces))
    _drive(engine, 1200)  # > engage 1000 → tier engaged

    assert engine.space_runtime(sid).metrics[0].active_tier >= 0
    assert engine.space_status(sid) == "mitigating"
    assert not engine.space_reason(sid).startswith("OK")

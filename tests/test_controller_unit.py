"""Unit tests for controller decision helpers (pure, fake engine)."""

from __future__ import annotations

from custom_components.aeolus.const import MetricKind
from custom_components.aeolus.controller import (
    _active_tier,
    _induced_applicable,
    _space_not_converging,
)
from custom_components.aeolus.ema import SlopeTracker, TimeAwareEMA
from custom_components.aeolus.engine import MetricRuntime, SpaceRuntime
from custom_components.aeolus.models import Influence, Metric, Tier


def _mrt(ema: float | None = None, slope_per_min: float | None = None) -> MetricRuntime:
    m = MetricRuntime(
        kind=MetricKind.CO2,
        ema=TimeAwareEMA(300),
        slope=SlopeTracker(smoothing_halflife_sec=300),
        floor=420.0,
    )
    if ema is not None:
        m.ema.seed(ema, None)
    if slope_per_min is not None:
        m.slope._smoother.seed(slope_per_min / 60.0, None)  # noqa: SLF001
    return m


def _rt(ema: float | None = None, slope_per_min: float | None = None) -> SpaceRuntime:
    return SpaceRuntime(metrics=[_mrt(ema, slope_per_min)])


class _FakeEngine:
    def __init__(self, runtimes: dict[str, SpaceRuntime]) -> None:
        self._r = runtimes

    def space_runtime(self, space_id: str):  # noqa: ANN201
        return self._r.get(space_id)


# --- staircase hysteresis (FR-T2/T3) ------------------------------------------
def _ladder() -> Metric:
    return Metric(
        kind=MetricKind.PM2_5,
        sensors=["x"],
        tiers=[
            Tier(engage_at=30, release_at=25),
            Tier(engage_at=50, release_at=42),
            Tier(engage_at=80, release_at=68),
        ],
    )


def test_active_tier_escalates_holds_and_releases() -> None:
    metric = _ladder()
    mrt = _mrt()
    assert _active_tier(metric, mrt, 90) == 2  # jumps straight to the top tier
    assert _active_tier(metric, mrt, 70) == 2  # 70 > release 68 → holds (hysteresis)
    assert _active_tier(metric, mrt, 65) == 1  # 65 ≤ 68 → steps down one
    assert _active_tier(metric, mrt, 26) == 0  # above tier-1 release → tier 1
    assert _active_tier(metric, mrt, 20) is None  # below tier-1 release → all off
    assert _active_tier(metric, mrt, 35) == 0  # re-engages from off


# --- induced helper (retained for re-integration) -----------------------------
def test_not_converging_when_no_slope() -> None:
    assert _space_not_converging(_FakeEngine({"p": _rt(1200)}), "p") is True


def test_converging_when_falling_fast() -> None:
    assert _space_not_converging(_FakeEngine({"p": _rt(1200, -5.0)}), "p") is False


def test_induced_applicable_when_source_lower() -> None:
    eng = _FakeEngine({"p": _rt(1200), "s": _rt(600)})
    inf = Influence(space_id="p", source_space_id="s", gap_margin_ppm=50.0)
    assert _induced_applicable(eng, inf) is True


def test_induced_not_applicable_when_source_not_lower() -> None:
    eng = _FakeEngine({"p": _rt(1200), "s": _rt(1200)})
    inf = Influence(space_id="p", source_space_id="s", gap_margin_ppm=50.0)
    assert _induced_applicable(eng, inf) is False


def test_induced_not_applicable_without_source() -> None:
    eng = _FakeEngine({"p": _rt(1200)})
    assert _induced_applicable(eng, Influence(space_id="p", source_space_id=None)) is False

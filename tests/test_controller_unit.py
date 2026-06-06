"""Unit tests for controller decision helpers (pure, fake engine)."""

from __future__ import annotations

from custom_components.aeolus.controller import _induced_applicable, _space_not_converging
from custom_components.aeolus.ema import SlopeTracker, TimeAwareEMA
from custom_components.aeolus.engine import SpaceRuntime
from custom_components.aeolus.models import Influence


def _rt(ema: float | None = None, slope_per_min: float | None = None) -> SpaceRuntime:
    rt = SpaceRuntime(ema=TimeAwareEMA(300), slope=SlopeTracker(smoothing_halflife_sec=300))
    if ema is not None:
        rt.ema.seed(ema, None)
    if slope_per_min is not None:
        rt.slope._smoother.seed(slope_per_min / 60.0, None)  # noqa: SLF001
    return rt


class _FakeEngine:
    def __init__(self, runtimes: dict[str, SpaceRuntime]) -> None:
        self._r = runtimes

    def space_runtime(self, space_id: str):  # noqa: ANN201
        return self._r.get(space_id)


def test_not_converging_when_no_slope():
    assert _space_not_converging(_FakeEngine({"p": _rt(1200)}), "p") is True


def test_not_converging_when_flat():
    assert _space_not_converging(_FakeEngine({"p": _rt(1200, 0.0)}), "p") is True


def test_converging_when_falling_fast():
    assert _space_not_converging(_FakeEngine({"p": _rt(1200, -5.0)}), "p") is False


def test_induced_applicable_when_source_lower():
    eng = _FakeEngine({"p": _rt(1200), "s": _rt(600)})
    inf = Influence(space_id="p", source_space_id="s", gap_margin_ppm=50.0)
    assert _induced_applicable(eng, inf) is True


def test_induced_not_applicable_when_source_not_lower():
    eng = _FakeEngine({"p": _rt(1200), "s": _rt(1200)})
    inf = Influence(space_id="p", source_space_id="s", gap_margin_ppm=50.0)
    assert _induced_applicable(eng, inf) is False


def test_induced_not_applicable_without_source():
    eng = _FakeEngine({"p": _rt(1200)})
    inf = Influence(space_id="p", source_space_id=None)
    assert _induced_applicable(eng, inf) is False


def test_induced_not_applicable_when_converging():
    eng = _FakeEngine({"p": _rt(1200, -5.0), "s": _rt(600)})
    inf = Influence(space_id="p", source_space_id="s", gap_margin_ppm=50.0)
    assert _induced_applicable(eng, inf) is False  # target already improving


def test_induced_not_applicable_missing_source_runtime():
    eng = _FakeEngine({"p": _rt(1200)})
    inf = Influence(space_id="p", source_space_id="missing", gap_margin_ppm=50.0)
    assert _induced_applicable(eng, inf) is False

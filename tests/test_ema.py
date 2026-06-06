"""Unit tests for the pure EMA/slope math (no Home Assistant needed).

`ema.py` is std-lib-only, so we import it directly and run these standalone:
    python -m pytest tests/test_ema.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "custom_components" / "aeolus")
)

from ema import SlopeTracker, TimeAwareEMA  # noqa: E402

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_first_sample_seeds():
    e = TimeAwareEMA(300)
    assert e.value is None
    assert e.add(1000.0, T0) == 1000.0
    assert e.value == 1000.0


def test_one_halflife_gives_half_weight():
    # dt == halflife → alpha ≈ 0.5 → ema = 0.5*new + 0.5*old
    e = TimeAwareEMA(300, max_alpha=1.0, precision=4)
    e.add(1000.0, T0)
    out = e.add(0.0, T0 + timedelta(seconds=300))
    assert out == pytest.approx(500.0, abs=0.5)


def test_max_alpha_caps_long_gap():
    # A huge gap would push alpha→1; max_alpha must cap the new-sample weight.
    e = TimeAwareEMA(300, max_alpha=0.5, precision=4)
    e.add(1000.0, T0)
    out = e.add(0.0, T0 + timedelta(seconds=36000))  # 100 half-lives
    assert out == pytest.approx(500.0, abs=0.5)  # capped at 0.5, not ~0


def test_nonpositive_dt_ignored():
    e = TimeAwareEMA(300)
    e.add(1000.0, T0)
    assert e.add(0.0, T0) == 1000.0  # same timestamp → ignored
    assert e.add(0.0, T0 - timedelta(seconds=10)) == 1000.0  # backwards → ignored


def test_invalid_params():
    with pytest.raises(ValueError):
        TimeAwareEMA(0)
    with pytest.raises(ValueError):
        TimeAwareEMA(300, max_alpha=0.0)
    with pytest.raises(ValueError):
        TimeAwareEMA(300, max_alpha=1.5)


def test_seed_restores_state():
    e = TimeAwareEMA(300)
    e.seed(750.0, None)
    # next sample folds against the seeded value
    out = e.add(750.0, T0)
    assert out == 750.0


def test_slope_sign_negative_when_falling():
    s = SlopeTracker(smoothing_halflife_sec=60)
    s.update(1000.0, T0)
    s.update(940.0, T0 + timedelta(seconds=60))  # -60 ppm/min = -1 ppm/s
    assert s.per_second is not None
    assert s.per_second < 0

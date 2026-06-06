"""Tests for the first-order estimators (gap-normalized ACH, exponential ETA)."""

from __future__ import annotations

import pytest

from custom_components.aeolus.estimator import effective_ach, time_to_target_min


def test_effective_ach_gap_normalized():
    # slope -116 ppm/hr at gap (1000-420)=580 → ACH = 116/580 ≈ 0.2 /hr
    assert effective_ach(-116.0, 1000.0, 420.0) == pytest.approx(0.2, abs=0.01)


def test_effective_ach_none_within_floor_epsilon():
    assert effective_ach(-10.0, 423.0, 420.0) is None  # gap 3 < epsilon(5)


def test_effective_ach_negative_when_rising():
    # rising CO2 → negative "ach" (not decaying)
    assert effective_ach(58.0, 1000.0, 420.0) < 0


def test_time_to_target_reachable_positive():
    t = time_to_target_min(1000.0, 800.0, -116.0, 420.0)
    assert t is not None and t > 0


def test_time_to_target_already_met_is_zero():
    assert time_to_target_min(700.0, 800.0, -10.0, 420.0) == 0.0


def test_time_to_target_none_when_diverging():
    assert time_to_target_min(1000.0, 800.0, 50.0, 420.0) is None  # rising


def test_time_to_target_none_when_target_below_floor():
    assert time_to_target_min(1000.0, 410.0, -116.0, 420.0) is None

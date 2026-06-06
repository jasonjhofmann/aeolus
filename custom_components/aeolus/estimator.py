"""Concentration-aware estimators derived from the first-order CO2 model (§1).

Pure functions. The single-zone mass balance is
    dC/dt = G/V - lambda*(C - C_out)
so the comparable, concentration-independent effectiveness is the air-change
rate lambda, recovered by normalizing slope by the driving gap (R-PHYS-3):
    effective_ach ~= -slope / (C - C_out)
Time-to-target is the EXPONENTIAL form (R-PHYS-1), not linear extrapolation.
"""

from __future__ import annotations

import math

from .const import C_OUT_GAP_EPSILON_PPM


def effective_ach(slope_ppm_per_hour: float, co2_ppm: float, c_out_ppm: float) -> float | None:
    """Gap-normalized air-change rate (1/hour). None if the gap is too small.

    Only meaningful during low-generation decay; the caller decides when to
    trust it (FR-S2). Returns >0 when CO2 is falling toward the floor.
    """
    gap = co2_ppm - c_out_ppm
    if gap <= C_OUT_GAP_EPSILON_PPM:
        return None
    return -(slope_ppm_per_hour / 3600.0) / gap * 3600.0  # == -slope_per_hour / gap


def equilibrium_ppm(co2_ppm: float, slope_ppm_per_hour: float, c_out_ppm: float) -> float | None:
    """Where the current first-order trajectory is heading (C_out + G/Q estimate)."""
    ach = effective_ach(slope_ppm_per_hour, co2_ppm, c_out_ppm)
    if ach is None or ach <= 0:
        return None
    # At equilibrium dC/dt=0 → C_eq = C_out + (generation term)/lambda.
    # With lambda from decay and the current slope, C_eq = C - slope/lambda.
    return co2_ppm - (slope_ppm_per_hour / ach)


def time_to_target_min(
    co2_ppm: float, target_ppm: float, slope_ppm_per_hour: float, c_out_ppm: float
) -> float | None:
    """Exponential ETA to the target in minutes (R-PHYS-1).

    Returns None if not converging or the target is unreachable (R-PHYS-2):
    a target at/below the floor, or below the trajectory's equilibrium, can't
    be reached by the current ventilation.
    """
    if co2_ppm <= target_ppm:
        return 0.0
    ach = effective_ach(slope_ppm_per_hour, co2_ppm, c_out_ppm)
    if ach is None or ach <= 0:
        return None  # not decaying → diverging / not converging
    gap_now = co2_ppm - c_out_ppm
    gap_target = target_ppm - c_out_ppm
    if gap_target <= 0:
        return None  # target at/below outdoor floor → unreachable
    eq = equilibrium_ppm(co2_ppm, slope_ppm_per_hour, c_out_ppm)
    if eq is not None and target_ppm <= eq:
        return None  # below where it will settle → unreachable at this ventilation
    # t = (1/lambda) * ln(gap_now / gap_target); lambda in 1/hour → minutes
    return (math.log(gap_now / gap_target) / ach) * 60.0

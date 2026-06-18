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


def effective_ach(
    slope_ppm_per_hour: float, co2_ppm: float, c_out_ppm: float
) -> float | None:
    """Gap-normalized air-change rate (1/hour). None if the gap is too small.

    Only meaningful during low-generation decay; the caller decides when to
    trust it (FR-S2). Returns >0 when CO2 is falling toward the floor.
    """
    gap = co2_ppm - c_out_ppm
    if gap <= C_OUT_GAP_EPSILON_PPM:
        return None
    return -(slope_ppm_per_hour / 3600.0) / gap * 3600.0  # == -slope_per_hour / gap


# NOTE: equilibrium_co2 (FR-S3) is deferred to v1.1 — it needs an independent
# generation/occupancy estimate (G, FR-S5). It is NOT derivable from
# effective_ach alone, because effective_ach is gap-normalized assuming decay
# (G≈0), which would make every "equilibrium" collapse to the outdoor floor.


def time_to_target_min(
    co2_ppm: float, target_ppm: float, slope_ppm_per_hour: float, c_out_ppm: float
) -> float | None:
    """Exponential ETA to the target in minutes (R-PHYS-1).

    Returns None if the space isn't converging (slope not falling) or the target
    is unreachable (at/below the outdoor floor, R-PHYS-2).
    """
    if co2_ppm <= target_ppm:
        return 0.0
    ach = effective_ach(slope_ppm_per_hour, co2_ppm, c_out_ppm)
    if ach is None or ach <= 0:
        return None  # not decaying → diverging / not converging
    gap_target = target_ppm - c_out_ppm
    if gap_target <= 0:
        return None  # target at/below outdoor floor → unreachable
    gap_now = co2_ppm - c_out_ppm
    # t = (1/lambda) * ln(gap_now / gap_target); lambda in 1/hour → minutes
    return (math.log(gap_now / gap_target) / ach) * 60.0

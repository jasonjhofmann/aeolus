"""Constants and enums for the Aeolus integration.

See REQUIREMENTS.md (§1 physical model, §2 domain model, §3 functional reqs)
in the repo root for the meaning behind these.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final = "aeolus"

# --- Config subentry types (FR-C2) ---
SUBENTRY_TYPE_SPACE: Final = "space"
SUBENTRY_TYPE_ACTUATOR: Final = "actuator"

# --- Space subentry config keys (FR-C3) ---
CONF_CO2_SENSORS: Final = "co2_sensors"
CONF_AGGREGATION: Final = "aggregation"
CONF_TARGET_PPM: Final = "target_ppm"
CONF_HIGH_PPM: Final = "high_ppm"
CONF_VOLUME_FT3: Final = "volume_ft3"
CONF_AREA_ID: Final = "area_id"
CONF_OCCUPANCY_ENTITY: Final = "occupancy_entity"
CONF_OUTDOOR_AQ_ENTITY: Final = "outdoor_aq_entity"
CONF_OUTDOOR_AQ_THRESHOLD: Final = "outdoor_aq_threshold"
CONF_RADON_ENTITY: Final = "radon_entity"

# --- Actuator subentry config keys (FR-C4) ---
CONF_NAME: Final = "name"
CONF_ACTUATOR_ENTITY: Final = "actuator_entity"
CONF_MECHANISM: Final = "mechanism"
CONF_INFLUENCES: Final = "influences"  # list of per-space influence rows
CONF_SERVED_SPACES: Final = "served_spaces"  # v0.1: direct-reducing space ids
CONF_FILTER_EFFICIENCY: Final = "filter_efficiency"  # 0..1, PM2.5 capture of this pathway
CONF_REARM_INTERVAL: Final = "rearm_interval"  # minutes; re-send ON for self-auto-off loads (FR-L5b)
CONF_MAX_RUNTIME_MIN: Final = "max_runtime_min"
CONF_RATED_CFM: Final = "rated_cfm"
# influence row keys
CONF_SPACE: Final = "space"
CONF_GAIN: Final = "gain"
CONF_INFLUENCE_TYPE: Final = "influence_type"
CONF_SOURCE_SPACE: Final = "source_space"  # induced edges (FR-X3)
CONF_GAP_MARGIN_PPM: Final = "gap_margin_ppm"
CONF_LAG_SEC: Final = "lag_sec"

# --- Defaults (FR-M2, FR-S, §1.1) ---
DEFAULT_HALFLIFE_SEC: Final = 300.0
DEFAULT_MAX_ALPHA: Final = 0.5
DEFAULT_PRECISION: Final = 1
# Outdoor CO2 floor / asymptotic limit (R-PHYS-1/2). Reference home has no outdoor
# CO2 sensor (AirVisual Outdoor reports PM/AQI, not CO2) → use the constant.
DEFAULT_C_OUT_PPM: Final = 420.0
DEFAULT_TARGET_PPM: Final = 800
DEFAULT_HIGH_PPM: Final = 1000
# Control loop / safety (FR-L5, FR-G1)
DEFAULT_CONTROL_TICK_SEC: Final = 60
DEFAULT_MIN_ON_SEC: Final = 600
DEFAULT_MIN_OFF_SEC: Final = 600
DEFAULT_MAX_RUNTIME_MIN: Final = 120
# Staleness safe-state (FR-G5/FR-M1): per-member freshness window.
DEFAULT_STALE_AFTER_SEC: Final = 1800
# Clamp for effective_ach denominator (R-PHYS-3): avoid div-by-zero/negative.
C_OUT_GAP_EPSILON_PPM: Final = 5.0
# Escalation (FR-L3): a space is "not converging" if its smoothed slope isn't
# falling faster than this (ppm/min) — i.e. its direct actuators aren't winning.
CONVERGENCE_SLOPE_PPM_PER_MIN: Final = 1.0


class Aggregation(StrEnum):
    """How a Space's member CO2 sensors are combined (FR-M1)."""

    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"  # "worst-case"


class Mechanism(StrEnum):
    """How an actuator moves air (FR-C4). Drives pressure + veto reasoning."""

    BALANCED = "balanced"  # ERV/HRV — neutral pressure
    SUPPLY = "supply"  # pressurizes
    EXHAUST = "exhaust"  # depressurizes → infiltration (FR-G1/§0.4)
    TRANSFER = "transfer"  # inter-zone fan
    WINDOW = "window"  # cover/opener


class InfluenceType(StrEnum):
    """Actuator→Space coupling kind (§2.1, FR-X)."""

    DIRECT = "direct"
    DIFFUSIVE = "diffusive"
    INDUCED = "induced"  # pressure-mediated; conditional on a source space (FR-X3)


class Gain(StrEnum):
    """Qualitative influence strength → internal ΔACH prior (FR-X5, decision #3)."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SpaceMode(StrEnum):
    """Per-space control mode (FR-L6)."""

    MANAGE = "manage"
    MONITOR = "monitor"
    OFF = "off"


# Qualitative gain → ΔACH prior (air changes per hour). Tunable; measured ACH
# (FR-S2/S4) stays observe-only until the Gold auto-calibration opt-in (FR-X5).
GAIN_ACH_PRIOR: Final[dict[Gain, float]] = {
    Gain.NONE: 0.0,
    Gain.LOW: 0.3,
    Gain.MEDIUM: 0.8,
    Gain.HIGH: 1.5,
}

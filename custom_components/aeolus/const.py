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

# --- Manager (parent entry) options (FR-C10) ---
# Opt-in flag that reveals the graduated PM/AQI tier-ladder wizard in the Space
# flow. Off by default so the common case (simple CO₂ space) stays uncluttered;
# the ladder UI is powerful but confusing. Disabling it never deletes already
# authored ladders — they keep running, they just can't be re-authored until
# the flag is turned back on.
CONF_ENABLE_LADDERS: Final = "enable_ladders"

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
# --- v3 multi-pollutant metrics + tier ladders (FR-P/FR-T) ---
CONF_METRICS: Final = "metrics"  # list of metric dicts on a Space
CONF_METRIC_KIND: Final = "kind"  # MetricKind value
CONF_METRIC_SENSORS: Final = "sensors"
CONF_TIERS: Final = "tiers"  # ordered list of tier dicts on a metric
CONF_TIER_ENGAGE: Final = "engage_at"
CONF_TIER_RELEASE: Final = "release_at"
CONF_TIER_SETPOINTS: Final = "setpoints"  # {actuator_subentry_id: pct 0..100}

# --- Actuator subentry config keys (FR-C4) ---
CONF_NAME: Final = "name"
CONF_ACTUATOR_ENTITY: Final = "actuator_entity"
CONF_ACTUATOR_ENTITIES: Final = "actuator_entities"  # v3: multi-entity group (FR-P8)
CONF_MECHANISM: Final = "mechanism"
CONF_INFLUENCES: Final = "influences"  # list of per-space influence rows
CONF_SERVED_SPACES: Final = "served_spaces"  # v0.1: direct-reducing space ids
CONF_FILTER_EFFICIENCY: Final = "filter_efficiency"  # 0..1, PM2.5 capture of this pathway
CONF_REARM_INTERVAL: Final = "rearm_interval"  # minutes; re-send ON for self-auto-off loads (FR-L5b)
CONF_ON_SPEED_PCT: Final = "on_speed_pct"  # fans only: % speed to set when turned on (FR-L4b)
CONF_OVERRIDE_GRACE_MIN: Final = "override_grace_min"  # min a divergence must persist → override (FR-L7b)
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
# Tier hysteresis (FR-T3): default release threshold = engage × this fraction.
DEFAULT_RELEASE_FRACTION: Final = 0.85
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
    FILTER = "filter"  # recirculating HEPA/purifier — removes PM, NOT CO2 (FR-P4)


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


class MetricKind(StrEnum):
    """What a Space metric measures (FR-P1). CO2 is the original; the rest are v3."""

    CO2 = "co2"
    PM1 = "pm1"
    PM2_5 = "pm2_5"
    PM10 = "pm10"
    AQI = "aqi"
    GENERIC = "generic"


# Asymptotic floor per metric (R-PHYS). CO2 → outdoor ~420; PM/AQI/generic → 0
# (PM's true floor is the live outdoor PM, applied in safety, not here).
METRIC_FLOOR: Final[dict[MetricKind, float]] = {
    MetricKind.CO2: DEFAULT_C_OUT_PPM,
    MetricKind.PM1: 0.0,
    MetricKind.PM2_5: 0.0,
    MetricKind.PM10: 0.0,
    MetricKind.AQI: 0.0,
    MetricKind.GENERIC: 0.0,
}

# --- Per-metric display metadata (FR-E5/E8/U5) -----------------------------
# Label, unit, display precision, icon, and a sensible threshold range per kind.
# device_class enums are applied in the entity modules (const stays HA-import-free).
METRIC_LABEL: Final[dict[MetricKind, str]] = {
    MetricKind.CO2: "CO₂",
    MetricKind.PM1: "PM1",
    MetricKind.PM2_5: "PM2.5",
    MetricKind.PM10: "PM10",
    MetricKind.AQI: "AQI",
    MetricKind.GENERIC: "Level",
}
METRIC_UNIT: Final[dict[MetricKind, str | None]] = {
    MetricKind.CO2: "ppm",
    MetricKind.PM1: "µg/m³",
    MetricKind.PM2_5: "µg/m³",
    MetricKind.PM10: "µg/m³",
    MetricKind.AQI: None,
    MetricKind.GENERIC: None,
}
METRIC_PRECISION: Final[dict[MetricKind, int]] = {
    MetricKind.CO2: 1,
    MetricKind.PM1: 1,
    MetricKind.PM2_5: 1,
    MetricKind.PM10: 1,
    MetricKind.AQI: 0,
    MetricKind.GENERIC: 1,
}
# Per-metric icons live in icons.json (icon-translations rule), keyed by each
# entity's translation_key — not set on the entity objects.
# Upper bound for the per-metric engage-threshold `number` (FR-E7). CO₂ uses the
# dedicated Target number, so it is absent here.
METRIC_THRESHOLD_MAX: Final[dict[MetricKind, float]] = {
    MetricKind.PM1: 500.0,
    MetricKind.PM2_5: 500.0,
    MetricKind.PM10: 600.0,
    MetricKind.AQI: 500.0,
    MetricKind.GENERIC: 1000.0,
}

_PM_KINDS: Final = frozenset(
    {MetricKind.PM1, MetricKind.PM2_5, MetricKind.PM10, MetricKind.AQI, MetricKind.GENERIC}
)
_ALL_KINDS: Final = frozenset(MetricKind)

# Which metric kinds each mechanism can actually reduce (FR-P4/P5). A recirculating
# FILTER (air purifier) removes PM/odor but NEVER CO2; air-moving mechanisms reduce
# everything (outdoor-PM import for supply/balanced is handled by the safety veto).
MECHANISM_REDUCES: Final[dict[Mechanism, frozenset[MetricKind]]] = {
    Mechanism.FILTER: _PM_KINDS,
    Mechanism.EXHAUST: _ALL_KINDS,
    Mechanism.SUPPLY: _ALL_KINDS,
    Mechanism.BALANCED: _ALL_KINDS,
    Mechanism.TRANSFER: _ALL_KINDS,
    Mechanism.WINDOW: _ALL_KINDS,
}

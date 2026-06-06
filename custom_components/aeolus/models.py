"""Runtime data models for Aeolus — the software image of the §1.3 graph.

These are the shared contracts the whole integration is built around, so they
live in one module by design (not fanned out). Parsed from config subentries
at setup; the live EMA/slope state lives on the engine, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .const import (
    Aggregation,
    Gain,
    InfluenceType,
    Mechanism,
    SpaceMode,
)

if TYPE_CHECKING:
    from .engine import AeolusEngine


@dataclass(slots=True)
class Space:
    """A managed zone (FR-C3). `subentry_id` is the HA config_subentry id."""

    subentry_id: str
    name: str
    co2_sensors: list[str]
    aggregation: Aggregation = Aggregation.MEAN
    target_ppm: float = 800.0
    high_ppm: float = 1000.0
    volume_ft3: float | None = None
    area_id: str | None = None
    occupancy_entity: str | None = None
    outdoor_aq_entity: str | None = None
    outdoor_aq_threshold: float | None = None
    radon_entity: str | None = None
    mode: SpaceMode = SpaceMode.MANAGE


@dataclass(slots=True)
class Influence:
    """One Actuator→Space edge (§2.1, FR-C4/FR-X)."""

    space_id: str
    gain: Gain = Gain.MEDIUM
    influence_type: InfluenceType = InfluenceType.DIRECT
    lag_sec: float = 0.0
    # induced edges only (FR-X3):
    source_space_id: str | None = None
    gap_margin_ppm: float = 50.0


@dataclass(slots=True)
class Actuator:
    """A ventilation entity Aeolus can drive (FR-C4)."""

    subentry_id: str
    name: str
    entity_id: str
    mechanism: Mechanism
    influences: list[Influence] = field(default_factory=list)
    # outdoor-air pathways carry their own AQ source + filtration (FR-G3, v2.3/2.5):
    outdoor_aq_entity: str | None = None
    filter_efficiency: float = 0.0  # PM2.5 capture, 0=foam/none … 0.99=HEPA
    max_runtime_min: float = 120.0
    rated_cfm: float | None = None
    # Re-arm (FR-L5b): for a load that auto-offs internally while its switch keeps
    # reporting `on` (e.g. the Primary-Bath toilet fan). When set, the engine
    # re-sends ON this often while still demanded. None = normal idempotent control.
    rearm_interval: timedelta | None = None


@dataclass(slots=True)
class AeolusData:
    """Stored on `entry.runtime_data` (FR-NFR runtime-data)."""

    engine: AeolusEngine


type AeolusConfigEntry = ConfigEntry[AeolusData]

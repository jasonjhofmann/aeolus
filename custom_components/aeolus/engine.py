"""The Aeolus engine — push-based, NOT a DataUpdateCoordinator.

Per the verified HA helper pattern (REQUIREMENTS NFR-1): a calculated helper
that reacts to the HA state machine subscribes to source-entity events rather
than polling. The engine owns the influence graph + per-space EMA/slope state
and a bounded control tick; entities read its state and re-render via dispatcher.

SCOPE (v0.1 scaffold): ingest + EMA/slope/ACH per space are wired here.
The arbitration/control loop (FR-L*) + safety vetoes (FR-G*) are stubbed —
see controller.py / safety.py. Build those next, coherently, in this module's
context (they share the graph + runtime state).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
)

from .const import (
    DEFAULT_C_OUT_PPM,
    DEFAULT_HALFLIFE_SEC,
    DEFAULT_MAX_ALPHA,
    DOMAIN,
)
from .ema import SlopeTracker, TimeAwareEMA
from .estimator import effective_ach, time_to_target_min
from .models import Actuator, Space

_LOGGER = logging.getLogger(__name__)


def signal_space_update(entry_id: str, space_id: str) -> str:
    """Dispatcher signal a Space entity listens on."""
    return f"{DOMAIN}_{entry_id}_space_{space_id}"


@dataclass(slots=True)
class SpaceRuntime:
    """Live derived state for one Space."""

    ema: TimeAwareEMA
    slope: SlopeTracker
    last_raw_ppm: float | None = None
    # newest last_updated across this space's members (per-member freshness, FR-M1):
    member_seen: dict[str, datetime] = field(default_factory=dict)

    @property
    def ema_ppm(self) -> float | None:
        return self.ema.value

    @property
    def slope_ppm_per_min(self) -> float | None:
        per_sec = self.slope.per_second
        return None if per_sec is None else round(per_sec * 60.0, 2)


class AeolusEngine:
    """Owns the graph + runtime; subscribes to sources; drives actuators."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        spaces: dict[str, Space],
        actuators: dict[str, Actuator],
        *,
        c_out_ppm: float = DEFAULT_C_OUT_PPM,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.spaces = spaces
        self.actuators = actuators
        self.c_out_ppm = c_out_ppm
        self._runtime: dict[str, SpaceRuntime] = {}
        self._sensor_to_spaces: dict[str, list[str]] = {}
        self._unsubs: list[callable] = []

    # --- lifecycle -------------------------------------------------------
    @callback
    def async_start(self) -> None:
        """Build runtime state + subscribe to all source CO2 sensors."""
        for space_id, space in self.spaces.items():
            self._runtime[space_id] = SpaceRuntime(
                ema=TimeAwareEMA(DEFAULT_HALFLIFE_SEC, max_alpha=DEFAULT_MAX_ALPHA),
                slope=SlopeTracker(smoothing_halflife_sec=DEFAULT_HALFLIFE_SEC),
            )
            for sensor_id in space.co2_sensors:
                self._sensor_to_spaces.setdefault(sensor_id, []).append(space_id)

        source_ids = list(self._sensor_to_spaces)
        if source_ids:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, source_ids, self._on_source_event
                )
            )
            # CO2 sensors re-report the same value without a *change* event; a
            # time-aware EMA needs those ticks too (verified HA pattern).
            self._unsubs.append(
                async_track_state_report_event(
                    self.hass, source_ids, self._on_source_event
                )
            )
            # Seed from current states.
            for sensor_id in source_ids:
                if (state := self.hass.states.get(sensor_id)) is not None:
                    self._ingest(sensor_id, state.state, state.last_updated)

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    # --- ingest ----------------------------------------------------------
    @callback
    def _on_source_event(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        self._ingest(new_state.entity_id, new_state.state, new_state.last_updated)

    @callback
    def _ingest(self, sensor_id: str, raw: str, when: datetime) -> None:
        if raw in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        try:
            ppm = float(raw)
        except (TypeError, ValueError):
            return
        if not 300.0 <= ppm <= 40000.0:  # implausible reading guard (FR-M2c)
            return
        for space_id in self._sensor_to_spaces.get(sensor_id, ()):
            self._recompute_space(space_id, sensor_id, ppm, when)

    @callback
    def _recompute_space(
        self, space_id: str, sensor_id: str, ppm: float, when: datetime
    ) -> None:
        rt = self._runtime[space_id]
        rt.member_seen[sensor_id] = when
        # TODO(v0.1): aggregate across members per Space.aggregation instead of
        # folding each member directly. Single-sensor spaces are correct already.
        rt.last_raw_ppm = ppm
        ema_val = rt.ema.add(ppm, when)
        if ema_val is not None:
            rt.slope.update(rt.ema.raw, when)  # type: ignore[arg-type]
        async_dispatcher_send(
            self.hass, signal_space_update(self.entry_id, space_id)
        )
        # TODO(v0.1): self._control_tick(space_id) — threshold/hysteresis +
        # arbitration (controller.py) gated by safety vetoes (safety.py).

    # --- read API (entities) --------------------------------------------
    def space_runtime(self, space_id: str) -> SpaceRuntime | None:
        return self._runtime.get(space_id)

    def space_effective_ach(self, space_id: str) -> float | None:
        rt = self._runtime.get(space_id)
        if rt is None or rt.ema_ppm is None or rt.slope_ppm_per_min is None:
            return None
        return effective_ach(rt.slope_ppm_per_min * 60.0, rt.ema_ppm, self.c_out_ppm)

    def space_time_to_target_min(self, space_id: str) -> float | None:
        rt = self._runtime.get(space_id)
        space = self.spaces.get(space_id)
        if rt is None or space is None or rt.ema_ppm is None or rt.slope_ppm_per_min is None:
            return None
        return time_to_target_min(
            rt.ema_ppm, space.target_ppm, rt.slope_ppm_per_min * 60.0, self.c_out_ppm
        )

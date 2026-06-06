"""The Aeolus engine — push-based, NOT a DataUpdateCoordinator.

Owns the influence graph + per-space EMA/slope state + per-actuator command
state, subscribes to source CO2 sensors AND actuator entities, and runs a
bounded control tick. The control *algorithm* lives in controller.py (imported
lazily to avoid a cycle); the safety vetoes live in safety.py.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_OPEN,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_C_OUT_PPM,
    DEFAULT_CONTROL_TICK_SEC,
    DEFAULT_HALFLIFE_SEC,
    DEFAULT_MAX_ALPHA,
    DEFAULT_MIN_OFF_SEC,
    DEFAULT_MIN_ON_SEC,
    DOMAIN,
)
from .ema import SlopeTracker, TimeAwareEMA
from .estimator import effective_ach, time_to_target_min
from .models import Actuator, Space

_LOGGER = logging.getLogger(__name__)

# How long to yield control after a detected manual override (FR-L7).
OVERRIDE_WINDOW = timedelta(minutes=30)


def signal_space_update(entry_id: str, space_id: str) -> str:
    """Dispatcher signal a Space entity listens on."""
    return f"{DOMAIN}_{entry_id}_space_{space_id}"


@dataclass(slots=True)
class SpaceRuntime:
    """Live derived state for one Space."""

    ema: TimeAwareEMA
    slope: SlopeTracker
    last_raw_ppm: float | None = None
    mitigating: bool = False  # hysteresis latch (FR-L1)
    member_seen: dict[str, datetime] = field(default_factory=dict)

    @property
    def ema_ppm(self) -> float | None:
        return self.ema.value

    @property
    def slope_ppm_per_min(self) -> float | None:
        per_sec = self.slope.per_second
        return None if per_sec is None else round(per_sec * 60.0, 2)


@dataclass(slots=True)
class ActuatorRuntime:
    """Aeolus's command state for one actuator."""

    commanded_on: bool = False
    on_since: datetime | None = None
    last_change: datetime | None = None
    overridden_until: datetime | None = None


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
        self.min_on = timedelta(seconds=DEFAULT_MIN_ON_SEC)
        self.min_off = timedelta(seconds=DEFAULT_MIN_OFF_SEC)
        self.paused = False  # master enable (switch); paused → controller no-ops
        self._runtime: dict[str, SpaceRuntime] = {}
        self._act_runtime: dict[str, ActuatorRuntime] = {}
        self._sensor_to_spaces: dict[str, list[str]] = {}
        self._actuator_by_entity: dict[str, str] = {}
        self._unsubs: list[Callable[[], None]] = []

    # --- lifecycle -------------------------------------------------------
    @callback
    def async_start(self) -> None:
        for space_id, space in self.spaces.items():
            self._runtime[space_id] = SpaceRuntime(
                ema=TimeAwareEMA(DEFAULT_HALFLIFE_SEC, max_alpha=DEFAULT_MAX_ALPHA),
                slope=SlopeTracker(smoothing_halflife_sec=DEFAULT_HALFLIFE_SEC),
            )
            for sensor_id in space.co2_sensors:
                self._sensor_to_spaces.setdefault(sensor_id, []).append(space_id)

        for act_id, act in self.actuators.items():
            self._act_runtime[act_id] = ActuatorRuntime()
            self._actuator_by_entity[act.entity_id] = act_id

        if source_ids := list(self._sensor_to_spaces):
            self._unsubs.append(
                async_track_state_change_event(self.hass, source_ids, self._on_source_event)
            )
            self._unsubs.append(
                async_track_state_report_event(self.hass, source_ids, self._on_source_event)
            )
            for sensor_id in source_ids:
                if (state := self.hass.states.get(sensor_id)) is not None:
                    self._ingest(sensor_id, state.state, state.last_updated)

        if actuator_ids := list(self._actuator_by_entity):
            self._unsubs.append(
                async_track_state_change_event(self.hass, actuator_ids, self._on_actuator_event)
            )

        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._async_tick, timedelta(seconds=DEFAULT_CONTROL_TICK_SEC)
            )
        )

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    # --- source ingest ---------------------------------------------------
    @callback
    def _on_source_event(self, event: Event[EventStateChangedData]) -> None:
        if (new_state := event.data.get("new_state")) is None:
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
        if not 300.0 <= ppm <= 40000.0:
            return
        for space_id in self._sensor_to_spaces.get(sensor_id, ()):
            self._recompute_space(space_id, sensor_id, ppm, when)
        self._evaluate(dt_util.utcnow())

    @callback
    def _recompute_space(self, space_id: str, sensor_id: str, ppm: float, when: datetime) -> None:
        rt = self._runtime[space_id]
        rt.member_seen[sensor_id] = when
        # TODO(v0.1): aggregate per Space.aggregation; single-sensor is correct now.
        rt.last_raw_ppm = ppm
        if rt.ema.add(ppm, when) is not None:
            rt.slope.update(rt.ema.raw, when)  # type: ignore[arg-type]
        async_dispatcher_send(self.hass, signal_space_update(self.entry_id, space_id))

    # --- actuator command + override detection ---------------------------
    @callback
    def _on_actuator_event(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        act_id = self._actuator_by_entity.get(new_state.entity_id)
        if act_id is None:
            return
        rt = self._act_runtime[act_id]
        if new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        actual_on = new_state.state in (STATE_ON, STATE_OPEN)
        # If reality diverges from what Aeolus commanded, a human/automation did
        # it → yield control for a window (FR-L7). Our own commands converge.
        if actual_on != rt.commanded_on:
            rt.overridden_until = dt_util.utcnow() + OVERRIDE_WINDOW
            _LOGGER.debug("Actuator %s externally overridden", new_state.entity_id)

    def actuator_is_overridden(self, act_id: str, now: datetime) -> bool:
        until = self._act_runtime[act_id].overridden_until
        return until is not None and now < until

    def command_actuator(self, act_id: str, turn_on: bool, now: datetime) -> None:
        """Drive an actuator on/off, honoring min on/off (FR-L5). Idempotent."""
        act = self.actuators[act_id]
        rt = self._act_runtime[act_id]
        if turn_on == rt.commanded_on:
            return
        if rt.last_change is not None:
            elapsed = now - rt.last_change
            if turn_on and elapsed < self.min_off:
                return
            if not turn_on and elapsed < self.min_on:
                return
        domain = act.entity_id.split(".", 1)[0]
        if domain == "cover":
            service = SERVICE_OPEN_COVER if turn_on else SERVICE_CLOSE_COVER
            service_domain = "cover"
        else:  # fan / switch / input_boolean
            service = SERVICE_TURN_ON if turn_on else SERVICE_TURN_OFF
            service_domain = domain
        rt.commanded_on = turn_on
        rt.last_change = now
        rt.on_since = now if turn_on else None
        self.hass.async_create_task(
            self.hass.services.async_call(
                service_domain, service, {"entity_id": act.entity_id}, blocking=False
            )
        )

    # --- control tick ----------------------------------------------------
    @callback
    def _async_tick(self, now: datetime) -> None:
        self._evaluate(now)

    @callback
    def request_evaluation(self) -> None:
        """Run the control loop now (e.g. after a target/mode/enable change)."""
        self._evaluate(dt_util.utcnow())

    def _evaluate(self, now: datetime) -> None:
        from . import controller  # lazy import to avoid a cycle

        controller.evaluate(self, now)

    # --- read API (entities + controller) --------------------------------
    def space_runtime(self, space_id: str) -> SpaceRuntime | None:
        return self._runtime.get(space_id)

    def actuator_runtime(self, act_id: str) -> ActuatorRuntime | None:
        return self._act_runtime.get(act_id)

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

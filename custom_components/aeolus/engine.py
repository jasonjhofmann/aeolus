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
    STATE_CLOSING,
    STATE_ON,
    STATE_OPEN,
    STATE_OPENING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    EventStateReportedData,
    HomeAssistant,
    State,
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
    METRIC_FLOOR,
    METRIC_LABEL,
    Aggregation,
    MetricKind,
    SpaceMode,
)
from .ema import SlopeTracker, TimeAwareEMA
from .estimator import effective_ach, time_to_target_min
from .models import Actuator, Metric, Space


def _aggregate(values: list[float], aggregation: Aggregation) -> float:
    """Combine a metric's member-sensor values (FR-M1). MAX = 'if ANY exceeds'."""
    if aggregation is Aggregation.MAX:
        return max(values)
    if aggregation is Aggregation.MIN:
        return min(values)
    if aggregation is Aggregation.MEDIAN:
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2.0
    return sum(values) / len(values)  # MEAN

_LOGGER = logging.getLogger(__name__)

# How long to yield control after a detected manual override (FR-L7).
OVERRIDE_WINDOW = timedelta(minutes=30)


def signal_space_update(entry_id: str, space_id: str) -> str:
    """Dispatcher signal a Space entity listens on."""
    return f"{DOMAIN}_{entry_id}_space_{space_id}"


def signal_space_added(entry_id: str) -> str:
    """Dispatcher signal carrying a newly-added Space subentry_id, so each platform
    can create that Space's entities live — without reloading the entry
    (dynamic-devices)."""
    return f"{DOMAIN}_{entry_id}_space_added"


@dataclass(slots=True)
class MetricRuntime:
    """Live derived state for ONE metric of a Space (FR-P/FR-T)."""

    kind: MetricKind
    ema: TimeAwareEMA
    slope: SlopeTracker
    floor: float
    last_raw: float | None = None
    active_tier: int = -1  # staircase hysteresis (FR-T3); -1 = no tier engaged
    # Per-metric management gate (FR-E9): True → contributes actuator demand;
    # False → monitor-only (value/status still surfaced, no demand). Toggled by
    # the advanced "Manage <metric>" switch; the space Mode is the master (FR-L6).
    manage: bool = True
    member_seen: dict[str, datetime] = field(default_factory=dict)

    @property
    def value(self) -> float | None:
        return self.ema.value

    @property
    def slope_per_min(self) -> float | None:
        per_sec = self.slope.per_second
        return None if per_sec is None else round(per_sec * 60.0, 2)


@dataclass(slots=True)
class SpaceRuntime:
    """Per-space runtime: one MetricRuntime per metric + the mitigation latch.

    The space-level read API (ema_ppm/slope/member_seen) proxies the *primary*
    metric (the CO₂ one if present, else the first) so the existing Space CO₂
    sensor + slope/ACH entities keep working unchanged.
    """

    metrics: list[MetricRuntime]
    primary: int = 0
    mitigating: bool = False  # any metric tier engaged (FR-L1)

    @property
    def primary_metric(self) -> MetricRuntime | None:
        return self.metrics[self.primary] if self.metrics else None

    @property
    def ema_ppm(self) -> float | None:
        m = self.primary_metric
        return None if m is None else m.value

    @property
    def slope_ppm_per_min(self) -> float | None:
        m = self.primary_metric
        return None if m is None else m.slope_per_min

    @property
    def last_raw_ppm(self) -> float | None:
        m = self.primary_metric
        return None if m is None else m.last_raw

    @property
    def member_seen(self) -> dict[str, datetime]:
        m = self.primary_metric
        return m.member_seen if m is not None else {}


@dataclass(slots=True)
class ActuatorRuntime:
    """Aeolus's command state for one actuator. `commanded_setpoint` is 0..100
    (0 = off; a fan %, or just on/off for switches/covers) — v3 variable drive."""

    commanded_setpoint: int = 0
    on_since: datetime | None = None
    last_change: datetime | None = None
    last_command_sent: datetime | None = None  # last time a service fired (rearm cadence)
    overridden_until: datetime | None = None
    divergence_since: datetime | None = None  # state≠command since (override confirmation, FR-L7b)
    aq_vetoed: bool = False  # last-seen outdoor-AQ veto state (for transition logging)

    @property
    def commanded_on(self) -> bool:
        return self.commanded_setpoint > 0


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
        self._space_available: dict[str, bool] = {}
        self._act_runtime: dict[str, ActuatorRuntime] = {}
        # sensor_id → [(space_id, metric_index)] it feeds (FR-P).
        self._sensor_to_metric: dict[str, list[tuple[str, int]]] = {}
        self._actuator_by_entity: dict[str, str] = {}
        # Source/actuator state-tracking subscriptions are re-established whenever a
        # Space/Actuator is added or removed at runtime (dynamic-devices); the control
        # tick lives in _unsubs and is set up once.
        self._unsubs: list[Callable[[], None]] = []
        self._source_unsubs: list[Callable[[], None]] = []
        self._actuator_unsub: Callable[[], None] | None = None

    # --- lifecycle -------------------------------------------------------
    def _init_space_runtime(self, space_id: str, space: Space) -> None:
        """Build the per-Space derived-state runtime and index its source sensors."""
        mruns: list[MetricRuntime] = []
        primary = 0
        for midx, metric in enumerate(space.metrics):
            mruns.append(
                MetricRuntime(
                    kind=metric.kind,
                    ema=TimeAwareEMA(DEFAULT_HALFLIFE_SEC, max_alpha=DEFAULT_MAX_ALPHA),
                    slope=SlopeTracker(smoothing_halflife_sec=DEFAULT_HALFLIFE_SEC),
                    floor=METRIC_FLOOR.get(metric.kind, 0.0),
                )
            )
            if metric.kind is MetricKind.CO2:
                primary = midx
            for sensor_id in metric.sensors:
                self._sensor_to_metric.setdefault(sensor_id, []).append((space_id, midx))
        self._runtime[space_id] = SpaceRuntime(metrics=mruns, primary=primary)

    def _init_actuator_runtime(self, act_id: str, act: Actuator) -> None:
        self._act_runtime[act_id] = ActuatorRuntime()
        for entity_id in (act.entities or [act.entity_id]):
            self._actuator_by_entity[entity_id] = act_id  # multi-entity (FR-P8)

    @callback
    def _resubscribe_sources(self) -> None:
        """(Re)subscribe to the current set of source sensors (dynamic-devices)."""
        for unsub in self._source_unsubs:
            unsub()
        self._source_unsubs.clear()
        if source_ids := list(self._sensor_to_metric):
            self._source_unsubs.append(
                async_track_state_change_event(self.hass, source_ids, self._on_source_changed)
            )
            self._source_unsubs.append(
                async_track_state_report_event(self.hass, source_ids, self._on_source_reported)
            )

    @callback
    def _resubscribe_actuators(self) -> None:
        """(Re)subscribe to the current set of actuator entities (dynamic-devices)."""
        if self._actuator_unsub is not None:
            self._actuator_unsub()
            self._actuator_unsub = None
        if actuator_ids := list(self._actuator_by_entity):
            self._actuator_unsub = async_track_state_change_event(
                self.hass, actuator_ids, self._on_actuator_event
            )

    @callback
    def _seed_sources(self, sensor_ids: list[str]) -> None:
        """Ingest the current state of the given source sensors (initial seed)."""
        for sensor_id in sensor_ids:
            if (state := self.hass.states.get(sensor_id)) is not None:
                self._ingest(sensor_id, state.state, state.last_updated)

    @callback
    def async_start(self) -> None:
        for space_id, space in self.spaces.items():
            self._init_space_runtime(space_id, space)
        for act_id, act in self.actuators.items():
            self._init_actuator_runtime(act_id, act)

        self._resubscribe_sources()
        self._seed_sources(list(self._sensor_to_metric))

        for space_id in self.spaces:
            self._space_available[space_id] = self.space_available(space_id)

        self._resubscribe_actuators()

        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._async_tick, timedelta(seconds=DEFAULT_CONTROL_TICK_SEC)
            )
        )

    # --- dynamic add/remove (dynamic-devices, stale-devices) -------------
    @callback
    def add_space(self, space: Space) -> None:
        """Bring a newly-added Space subentry online without reloading the entry."""
        space_id = space.subentry_id
        self.spaces[space_id] = space
        self._init_space_runtime(space_id, space)
        self._resubscribe_sources()
        self._seed_sources([s for m in space.metrics for s in m.sensors])
        self._space_available[space_id] = self.space_available(space_id)
        _LOGGER.info("Aeolus: Space '%s' added live (%d metric(s))", space.name, len(space.metrics))
        self.request_evaluation()

    @callback
    def remove_space(self, space_id: str) -> None:
        """Drop a removed Space subentry (its device/entities are cleared by HA)."""
        gone = self.spaces.pop(space_id, None)
        self._runtime.pop(space_id, None)
        self._space_available.pop(space_id, None)
        for sensor_id in list(self._sensor_to_metric):
            kept = [pair for pair in self._sensor_to_metric[sensor_id] if pair[0] != space_id]
            if kept:
                self._sensor_to_metric[sensor_id] = kept
            else:
                del self._sensor_to_metric[sensor_id]
        self._resubscribe_sources()
        if gone is not None:
            _LOGGER.info("Aeolus: Space '%s' removed live", gone.name)
        self.request_evaluation()

    @callback
    def add_actuator(self, act: Actuator) -> None:
        """Bring a newly-added Actuator subentry online; wire it into the CO₂ tiers
        of the Spaces it serves (the synthesized-setpoint cross-coupling)."""
        self.actuators[act.subentry_id] = act
        self._init_actuator_runtime(act.subentry_id, act)
        self._resubscribe_actuators()
        self._resync_co2_setpoints()
        _LOGGER.info("Aeolus: Actuator '%s' added live, wired into CO2 tiers", act.name)
        self.request_evaluation()

    @callback
    def remove_actuator(self, act_id: str) -> None:
        """Drop a removed Actuator subentry and purge it from every tier setpoint."""
        act = self.actuators.pop(act_id, None)
        self._act_runtime.pop(act_id, None)
        if act is not None:
            for entity_id in (act.entities or [act.entity_id]):
                self._actuator_by_entity.pop(entity_id, None)
        for space in self.spaces.values():
            for metric in space.metrics:
                for tier in metric.tiers:
                    tier.setpoints.pop(act_id, None)
        self._resync_co2_setpoints()
        self._resubscribe_actuators()
        if act is not None:
            _LOGGER.info("Aeolus: Actuator '%s' removed live and purged from all tiers", act.name)
        self.request_evaluation()

    @callback
    def _resync_co2_setpoints(self) -> None:
        """Rebuild every Space's synthesized CO₂-tier setpoints from the actuators
        currently serving it. Mirrors __init__._build_metrics; the CO₂ ladder is
        synthesized (not user-authored), so it is safe to rewrite wholesale."""
        for space in self.spaces.values():
            setpoints = {
                aid: (act.on_speed_pct or 100)
                for aid, act in self.actuators.items()
                if any(inf.space_id == space.subentry_id for inf in act.influences)
            }
            for metric in space.metrics:
                if metric.kind is MetricKind.CO2:
                    for tier in metric.tiers:
                        tier.setpoints = dict(setpoints)

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for unsub in self._source_unsubs:
            unsub()
        self._source_unsubs.clear()
        if self._actuator_unsub is not None:
            self._actuator_unsub()
            self._actuator_unsub = None

    # --- source ingest ---------------------------------------------------
    @callback
    def _on_source_changed(self, event: Event[EventStateChangedData]) -> None:
        self._handle_source(event.data["new_state"])

    @callback
    def _on_source_reported(self, event: Event[EventStateReportedData]) -> None:
        # State-report events fire when a sensor re-emits the same value with a
        # fresh timestamp — needed so a time-aware EMA keeps aging.
        self._handle_source(event.data["new_state"])

    @callback
    def _handle_source(self, new_state: State | None) -> None:
        if new_state is None:
            return
        self._ingest(new_state.entity_id, new_state.state, new_state.last_updated)
        # Availability fires on EVERY source change (incl. → unavailable), not
        # just numeric ones, so entities reflect source dropouts (entity-unavailable).
        for space_id in {sid for sid, _ in self._sensor_to_metric.get(new_state.entity_id, ())}:
            self._refresh_availability(space_id)

    @callback
    def _ingest(self, sensor_id: str, raw: str, when: datetime) -> None:
        if raw in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        for space_id, midx in self._sensor_to_metric.get(sensor_id, ()):
            self._recompute_metric(space_id, midx, sensor_id, when)
        if sensor_id in self._sensor_to_metric:
            self._evaluate(dt_util.utcnow())

    @callback
    def _recompute_metric(self, space_id: str, midx: int, sensor_id: str, when: datetime) -> None:
        srt = self._runtime[space_id]
        if midx >= len(srt.metrics):
            return
        mrt = srt.metrics[midx]
        metric = self.spaces[space_id].metrics[midx]
        values = self._read_metric_values(metric)
        if not values:
            return  # no usable member reading → leave freshness + EMA untouched, so
            # a sensor emitting only out-of-range garbage correctly ages to stale.
        # Stamp freshness only once a usable value exists (the stale-sensor safety
        # check keys off member_seen — see safety.is_stale).
        mrt.member_seen[sensor_id] = when
        mrt.last_raw = _aggregate(values, metric.aggregation)
        if mrt.ema.add(mrt.last_raw, when) is not None:
            mrt.slope.update(mrt.ema.raw, when)  # type: ignore[arg-type]
        async_dispatcher_send(self.hass, signal_space_update(self.entry_id, space_id))

    def _read_metric_values(self, metric: Metric) -> list[float]:
        """Current usable values of a metric's member sensors (range-guarded by kind)."""
        lo, hi = (300.0, 40000.0) if metric.kind is MetricKind.CO2 else (0.0, 100000.0)
        out: list[float] = []
        for sensor_id in metric.sensors:
            state = self.hass.states.get(sensor_id)
            if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                continue
            try:
                value = float(state.state)
            except (TypeError, ValueError):
                continue
            if lo <= value <= hi:
                out.append(value)
        return out

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
        # Ignore non-terminal states: UNKNOWN/UNAVAILABLE, and a cover's transient
        # OPENING/CLOSING — which occur DURING Aeolus's own open/close command and
        # would otherwise read as "off" and self-trigger a false manual override.
        if new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, STATE_OPENING, STATE_CLOSING):
            return
        actual_on = new_state.state in (STATE_ON, STATE_OPEN)
        act = self.actuators[act_id]
        now = dt_util.utcnow()
        # If reality diverges from what Aeolus commanded, a human/automation did it
        # → yield control for a window (FR-L7). With an override grace (FR-L7b), the
        # divergence must PERSIST that long before it counts — so a cloud actuator's
        # transient flap (e.g. LG ThinQ unavailable→off→on) doesn't false-trigger.
        if actual_on != rt.commanded_on:
            if act.override_grace <= timedelta(0):
                rt.overridden_until = now + OVERRIDE_WINDOW  # immediate (default)
                _LOGGER.info(
                    "Aeolus: %s manually overridden — yielding control for %d min",
                    act.name, OVERRIDE_WINDOW.total_seconds() // 60,
                )
            elif rt.divergence_since is None:
                rt.divergence_since = now  # start the clock; confirmed in _evaluate
        elif rt.divergence_since is not None:
            rt.divergence_since = None  # re-converged within grace → ignore the flap
            _LOGGER.debug("Aeolus: %s re-converged within grace (flap ignored)", act.name)

    def actuator_is_overridden(self, act_id: str, now: datetime) -> bool:
        until = self._act_runtime[act_id].overridden_until
        return until is not None and now < until

    def command_actuator(self, act_id: str, level: int | bool, now: datetime) -> None:
        """Drive an actuator to a setpoint (0..100; 0 = off), honoring min on/off
        on the on↔off boundary (FR-L5). `level` may be a bool for on/off callers
        (True → the fan's on-speed or full on; False → off).

        Idempotent, except: an actuator with `rearm_interval` re-sends its current
        setpoint periodically while on (FR-L5b) — defeats a load that auto-offs
        internally while its switch keeps reporting `on` (the Primary-Bath fan).
        """
        act = self.actuators[act_id]
        rt = self._act_runtime[act_id]
        setpoint = self._resolve_setpoint(act, level)
        if setpoint == rt.commanded_setpoint:
            if (
                setpoint > 0
                and act.rearm_interval is not None
                and not self.actuator_is_overridden(act_id, now)
                and rt.last_command_sent is not None
                and now - rt.last_command_sent >= act.rearm_interval
            ):
                self._send_command(act, setpoint, now)
            return
        crossing_on = rt.commanded_setpoint == 0 and setpoint > 0
        crossing_off = rt.commanded_setpoint > 0 and setpoint == 0
        if rt.last_change is not None:
            elapsed = now - rt.last_change
            if crossing_on and elapsed < self.min_off:
                _LOGGER.debug(
                    "Aeolus: %s on held by min-off (%ds of %ds elapsed)",
                    act.name, elapsed.total_seconds(), self.min_off.total_seconds(),
                )
                return
            if crossing_off and elapsed < self.min_on:
                _LOGGER.debug(
                    "Aeolus: %s off held by min-on (%ds of %ds elapsed)",
                    act.name, elapsed.total_seconds(), self.min_on.total_seconds(),
                )
                return
        rt.commanded_setpoint = setpoint
        if crossing_on or crossing_off:  # speed changes don't reset the cycle clock
            rt.last_change = now
            rt.on_since = now if setpoint > 0 else None
            # The on/off transition is the operator-relevant event (we drive real
            # hardware); speed-only changes and rearm re-sends stay at DEBUG.
            _LOGGER.info(
                "Aeolus: commanding %s %s%s",
                act.name,
                "on" if setpoint > 0 else "off",
                f" ({setpoint}%)" if 0 < setpoint < 100 else "",
            )
        self._send_command(act, setpoint, now)

    def _resolve_setpoint(self, act: Actuator, level: int | bool) -> int:
        """bool → setpoint (True: a fan's on-speed, else full on; False: off);
        int → clamped 0..100."""
        if isinstance(level, bool):
            if not level:
                return 0
            if act.entity_id.split(".", 1)[0] == "fan" and act.on_speed_pct is not None:
                return act.on_speed_pct
            return 100
        return max(0, min(100, int(level)))

    def _send_command(self, act: Actuator, setpoint: int, now: datetime) -> None:
        """Drive every entity of the actuator to `setpoint` and stamp the send time
        (FR-P7 variable drive, FR-P8 multi-entity group)."""
        self._act_runtime[act.subentry_id].last_command_sent = now
        for entity_id in (act.entities or [act.entity_id]):
            domain = entity_id.split(".", 1)[0]
            data: dict[str, int | str] = {"entity_id": entity_id}
            if domain == "cover":
                service = SERVICE_OPEN_COVER if setpoint > 0 else SERVICE_CLOSE_COVER
                service_domain = "cover"
            elif setpoint <= 0:
                service, service_domain = SERVICE_TURN_OFF, domain
            else:  # fan / switch / input_boolean — on
                service, service_domain = SERVICE_TURN_ON, domain
                # Variable fan speed: send a percentage only for a partial speed;
                # a full-on (100) or a switch is a plain turn_on.
                if domain == "fan" and 0 < setpoint < 100:
                    data["percentage"] = setpoint
            self.hass.async_create_task(self._async_call_service(service_domain, service, data))

    async def _async_call_service(
        self, domain: str, service: str, data: dict[str, int | str]
    ) -> None:
        """Fire one actuator service call, logging (not swallowing) any failure —
        otherwise a failed command leaves the engine believing the device moved."""
        try:
            await self.hass.services.async_call(domain, service, data, blocking=True)
        except Exception as err:  # never let a failed command crash the control loop
            _LOGGER.warning(
                "Aeolus: command %s.%s for %s failed: %s",
                domain, service, data.get("entity_id"), err,
            )

    # --- control tick ----------------------------------------------------
    @callback
    def _async_tick(self, now: datetime) -> None:
        self._evaluate(now)
        # Refresh status/reason/mitigation entities each tick even absent a source
        # change, so explainability (FR-U2) and mitigation state track the controller.
        for space_id in self.spaces:
            async_dispatcher_send(self.hass, signal_space_update(self.entry_id, space_id))

    @callback
    def request_evaluation(self) -> None:
        """Run the control loop now (e.g. after a target/mode/enable change)."""
        self._evaluate(dt_util.utcnow())

    def _evaluate(self, now: datetime) -> None:
        from . import controller  # lazy import to avoid a cycle

        self._promote_pending_overrides(now)
        controller.evaluate(self, now)

    @callback
    def _promote_pending_overrides(self, now: datetime) -> None:
        """Confirm a divergence that has outlasted its grace window (FR-L7b)."""
        for act_id, rt in self._act_runtime.items():
            if rt.divergence_since is None:
                continue
            grace = self.actuators[act_id].override_grace
            if grace > timedelta(0) and now - rt.divergence_since >= grace:
                rt.overridden_until = now + OVERRIDE_WINDOW
                rt.divergence_since = None
                _LOGGER.info(
                    "Aeolus: %s override confirmed (divergence outlasted %s) — "
                    "yielding control for %d min",
                    self.actuators[act_id].name, grace, OVERRIDE_WINDOW.total_seconds() // 60,
                )

    # --- availability (entity-unavailable / log-when-unavailable) --------
    def space_available(self, space_id: str) -> bool:
        """True if at least one of the space's primary-metric sensors is usable."""
        srt = self._runtime.get(space_id)
        space = self.spaces.get(space_id)
        if srt is None or space is None or not space.metrics:
            return False
        return bool(self._read_metric_values(space.metrics[srt.primary]))

    @callback
    def _refresh_availability(self, space_id: str) -> None:
        """Recompute availability; log + notify entities only on transitions."""
        available = self.space_available(space_id)
        if available == self._space_available.get(space_id):
            return
        self._space_available[space_id] = available
        name = self.spaces[space_id].name
        if available:
            _LOGGER.info("Aeolus: CO2 source(s) for %s are available again", name)
        else:
            _LOGGER.warning(
                "Aeolus: all CO2 sources for %s are unavailable — "
                "entity unavailable, mitigation suspended",
                name,
            )
        async_dispatcher_send(self.hass, signal_space_update(self.entry_id, space_id))

    # --- read API (entities + controller) --------------------------------
    def space_runtime(self, space_id: str) -> SpaceRuntime | None:
        return self._runtime.get(space_id)

    def actuator_runtime(self, act_id: str) -> ActuatorRuntime | None:
        return self._act_runtime.get(act_id)

    def space_effective_ach(self, space_id: str) -> float | None:
        srt = self._runtime.get(space_id)
        m = srt.primary_metric if srt is not None else None
        if m is None or m.value is None or m.slope_per_min is None:
            return None
        return effective_ach(m.slope_per_min * 60.0, m.value, m.floor)

    def space_time_to_target_min(self, space_id: str) -> float | None:
        srt = self._runtime.get(space_id)
        space = self.spaces.get(space_id)
        m = srt.primary_metric if srt is not None else None
        if m is None or space is None or m.value is None or m.slope_per_min is None:
            return None
        return time_to_target_min(m.value, space.target_ppm, m.slope_per_min * 60.0, m.floor)

    # --- per-metric read API (FR-E5–E9 parity) ---------------------------
    def metric_runtime(self, space_id: str, midx: int) -> MetricRuntime | None:
        srt = self._runtime.get(space_id)
        if srt is None or not (0 <= midx < len(srt.metrics)):
            return None
        return srt.metrics[midx]

    def metric_value(self, space_id: str, midx: int) -> float | None:
        mrt = self.metric_runtime(space_id, midx)
        return None if mrt is None else mrt.value

    def metric_slope_per_min(self, space_id: str, midx: int) -> float | None:
        mrt = self.metric_runtime(space_id, midx)
        return None if mrt is None else mrt.slope_per_min

    def metric_available(self, space_id: str, midx: int) -> bool:
        """A metric is available if any of its member sensors is currently usable."""
        space = self.spaces.get(space_id)
        if space is None or not (0 <= midx < len(space.metrics)):
            return False
        return bool(self._read_metric_values(space.metrics[midx]))

    def metric_manage(self, space_id: str, midx: int) -> bool:
        mrt = self.metric_runtime(space_id, midx)
        return True if mrt is None else mrt.manage

    def set_metric_manage(self, space_id: str, midx: int, manage: bool) -> None:
        """FR-E9 gate: include/exclude a metric's actuator demand, then re-evaluate."""
        mrt = self.metric_runtime(space_id, midx)
        if mrt is not None and mrt.manage != manage:
            mrt.manage = manage
            self.request_evaluation()

    def metric_threshold(self, space_id: str, midx: int) -> float | None:
        """The metric's tier-1 engage threshold (FR-E7), or None if no ladder."""
        space = self.spaces.get(space_id)
        if space is None or not (0 <= midx < len(space.metrics)):
            return None
        tiers = space.metrics[midx].tiers
        return tiers[0].engage_at if tiers else None

    def set_metric_threshold(self, space_id: str, midx: int, value: float) -> None:
        """Adjust the tier-1 engage threshold live (FR-E7), keeping its release
        below it for hysteresis; then re-evaluate."""
        from .const import DEFAULT_RELEASE_FRACTION

        space = self.spaces.get(space_id)
        if space is None or not (0 <= midx < len(space.metrics)):
            return
        tiers = space.metrics[midx].tiers
        if not tiers:
            return
        tiers[0].engage_at = value
        if tiers[0].release_at >= value:
            tiers[0].release_at = value * DEFAULT_RELEASE_FRACTION
        self.request_evaluation()

    def metric_tiers_view(self, space_id: str, midx: int) -> list[dict[str, object]]:
        """Read-only render of a metric's full ladder — engage/release + per-actuator
        setpoints keyed by actuator NAME — so it's viewable without re-authoring."""
        space = self.spaces.get(space_id)
        if space is None or not (0 <= midx < len(space.metrics)):
            return []
        view: list[dict[str, object]] = []
        for tier in space.metrics[midx].tiers:
            view.append(
                {
                    "engage_at": tier.engage_at,
                    "release_at": tier.release_at,
                    "setpoints": {
                        (self.actuators[aid].name if aid in self.actuators else aid): level
                        for aid, level in tier.setpoints.items()
                    },
                }
            )
        return view

    def _space_actuator_ids(self, space_id: str) -> set[str]:
        """Every actuator referenced by any tier of any of the space's metrics."""
        ids: set[str] = set()
        space = self.spaces.get(space_id)
        if space is not None:
            for metric in space.metrics:
                for tier in metric.tiers:
                    ids.update(tier.setpoints)
        return ids

    def space_active_actuator_names(self, space_id: str) -> list[str]:
        """Names of this space's actuators Aeolus currently has commanded on (FR-E2)."""
        names = [
            self.actuators[aid].name
            for aid in self._space_actuator_ids(space_id)
            if (art := self._act_runtime.get(aid)) is not None and art.commanded_on
        ]
        return sorted(names)

    def space_mitigating(self, space_id: str) -> bool:
        srt = self._runtime.get(space_id)
        return bool(srt is not None and srt.mitigating)

    def space_driving_metrics(self, space_id: str) -> list[MetricKind]:
        """Kinds whose ladder is currently engaged AND managed (FR-E6 attribution)."""
        srt = self._runtime.get(space_id)
        space = self.spaces.get(space_id)
        if srt is None or space is None or space.mode is not SpaceMode.MANAGE:
            return []
        return [m.kind for m in srt.metrics if m.manage and m.active_tier >= 0]

    def _all_stale(self, srt: SpaceRuntime, now: datetime) -> bool:
        from .safety import is_stale

        return bool(srt.metrics) and all(is_stale(m.member_seen, now) for m in srt.metrics)

    def space_attention(self, space_id: str, now: datetime | None = None) -> bool:
        """True if ANY driven metric is stale, maxed-and-still-high, or elevated &
        not improving — not CO₂ alone (FR-E6 correctness)."""
        from .safety import is_stale

        now = now or dt_util.utcnow()
        srt = self._runtime.get(space_id)
        space = self.spaces.get(space_id)
        if srt is None or space is None:
            return False
        for midx, metric in enumerate(space.metrics):
            mrt = srt.metrics[midx]
            if is_stale(mrt.member_seen, now):
                return True
            value = mrt.value
            if value is None or not metric.tiers:
                continue
            if value > metric.tiers[-1].engage_at:  # at/over the top tier
                return True
            slope = mrt.slope_per_min
            if value > metric.tiers[0].release_at and slope is not None and slope >= 0:
                return True
        return False

    def space_status(self, space_id: str, now: datetime | None = None) -> str:
        """One-word status across all metrics (FR-E2)."""
        now = now or dt_util.utcnow()
        srt = self._runtime.get(space_id)
        space = self.spaces.get(space_id)
        if srt is None or space is None or not self.space_available(space_id):
            return "unavailable"
        if self._all_stale(srt, now):
            return "stale"
        if self.paused:
            return "paused"
        if space.mode is SpaceMode.OFF:
            return "off"
        if space.mode is SpaceMode.MONITOR:
            return "monitor"
        if self.space_mitigating(space_id):
            return "mitigating"
        if self.space_attention(space_id, now):
            return "attention"
        return "ok"

    def space_reason(self, space_id: str, now: datetime | None = None) -> str:
        """Plain-language *why* the current action (FR-U2 explainability)."""
        now = now or dt_util.utcnow()
        srt = self._runtime.get(space_id)
        space = self.spaces.get(space_id)
        if srt is None or space is None:
            return "Not configured"
        if not self.space_available(space_id):
            return "Sensor unavailable — mitigation suspended"
        if self._all_stale(srt, now):
            return "Sensor stale — mitigation suspended"
        if self.paused:
            return "Aeolus management off (master switch)"
        if space.mode is SpaceMode.OFF:
            return "Mode off — not managing"
        if space.mode is SpaceMode.MONITOR:
            return "Monitor only — observing, not acting"
        # MANAGE: name the metrics whose ladder is engaged and managed.
        driving = [
            (metric, mrt)
            for midx, metric in enumerate(space.metrics)
            if (mrt := srt.metrics[midx]).manage and mrt.active_tier >= 0
        ]
        if driving:
            parts = [f"{METRIC_LABEL[m.kind]} tier {mrt.active_tier + 1}" for m, mrt in driving]
            acts = self.space_active_actuator_names(space_id)
            if acts:
                return f"Mitigating {', '.join(parts)} → {', '.join(acts)}"
            cause = self._blocking_cause(space_id, now)
            tail = f" — {cause}" if cause else " — no eligible actuator"
            return f"{', '.join(parts)} demanded{tail}"
        # Not driving: surface an elevated-but-not-acting metric (gated or blocked).
        for midx, metric in enumerate(space.metrics):
            mrt = srt.metrics[midx]
            value = mrt.value
            if value is None or not metric.tiers or value <= metric.tiers[0].engage_at:
                continue
            label = METRIC_LABEL[metric.kind]
            if not mrt.manage:
                return f"{label} elevated — monitoring only (Manage {label} off)"
            cause = self._blocking_cause(space_id, now)
            return f"{label} elevated — {cause}" if cause else f"{label} elevated"
        return "OK — all metrics within range"

    def _blocking_cause(self, space_id: str, now: datetime) -> str | None:
        """Why eligible actuators for an elevated metric aren't running (FR-U2)."""
        from .safety import max_runtime_exceeded, outdoor_air_vetoed

        space = self.spaces.get(space_id)
        if space is None:
            return None
        act_ids = self._space_actuator_ids(space_id)
        for aid in act_ids:
            if self.actuator_is_overridden(aid, now):
                until = self._act_runtime[aid].overridden_until
                mins = int((until - now).total_seconds() // 60) + 1 if until else 0
                return f"manual override — yielding {mins} min"
        for aid in act_ids:
            act = self.actuators.get(aid)
            if act is not None and outdoor_air_vetoed(self.hass, act, space):
                return "outdoor-air quality veto"
        for aid in act_ids:
            act = self.actuators.get(aid)
            art = self._act_runtime.get(aid)
            if act is not None and art is not None and max_runtime_exceeded(art, act, now):
                return "runtime cap reached"
        return None

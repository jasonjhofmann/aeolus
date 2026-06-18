"""Per-Space, per-metric sensors (FR-E2/E5/E8 + FR-U2 explainability).

For EVERY metric a Space is configured with (CO₂/PM/AQI/generic), Aeolus exposes
a smoothed value sensor and a slope sensor — not just the primary/CO₂ one (the
§8.8 parity gap). The CO₂ metric keeps its original unique_ids (`<sid>_co2`,
`<sid>_co2_slope`, `<sid>_air_change_rate`) and the unsuffixed device name, so a
live CO₂ space is unchanged. `effective_ach` is a CO₂/decay concept (§8.3 FR-P3)
and is emitted ONLY for the CO₂ metric. A per-Space `reason` diagnostic sensor
surfaces *why* Aeolus is (or isn't) acting (FR-U2).
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    METRIC_PRECISION,
    METRIC_UNIT,
    SUBENTRY_TYPE_SPACE,
    MetricKind,
)
from .engine import AeolusEngine, signal_space_update
from .entity import AeolusSpaceEntity
from .models import AeolusConfigEntry, Space

# Read-only derived entities (parallel-updates rule, Silver).
PARALLEL_UPDATES = 0

# Per-kind value device-class (kept here so const stays HA-import-free).
_METRIC_DEVICE_CLASS: dict[MetricKind, SensorDeviceClass | None] = {
    MetricKind.CO2: SensorDeviceClass.CO2,
    MetricKind.PM1: SensorDeviceClass.PM1,
    MetricKind.PM2_5: SensorDeviceClass.PM25,
    MetricKind.PM10: SensorDeviceClass.PM10,
    MetricKind.AQI: SensorDeviceClass.AQI,
    MetricKind.GENERIC: None,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AeolusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create per-metric value + slope sensors (+ ACH for CO₂) per Space, plus a
    per-Space reason sensor."""
    engine = entry.runtime_data.engine
    for sub_id, sub in entry.subentries.items():
        if sub.subentry_type != SUBENTRY_TYPE_SPACE:
            continue
        space = engine.spaces[sub_id]
        primary = engine.space_runtime(sub_id)
        primary_idx = primary.primary if primary is not None else 0
        entities: list[SensorEntity] = []
        for midx, metric in enumerate(space.metrics):
            is_primary = midx == primary_idx
            entities.append(AeolusMetricValueSensor(engine, space, midx, metric.kind, is_primary))
            entities.append(AeolusMetricSlopeSensor(engine, space, midx, metric.kind))
            if metric.kind is MetricKind.CO2:
                entities.append(AeolusAchSensor(engine, space, midx))
        entities.append(AeolusReasonSensor(engine, space))
        async_add_entities(entities, config_subentry_id=sub_id)


class _SpaceUpdateSensor(AeolusSpaceEntity, SensorEntity):
    """Base: subscribe to the Space dispatcher signal and rewrite state."""

    _attr_should_poll = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_space_update(self._engine.entry_id, self._space.subentry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class AeolusMetricValueSensor(_SpaceUpdateSensor, RestoreSensor):
    """Smoothed (EMA) value of one Space metric. The primary metric is unsuffixed
    (device name); others are suffixed by kind (FR-E8)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        engine: AeolusEngine,
        space: Space,
        midx: int,
        kind: MetricKind,
        is_primary: bool,
    ) -> None:
        super().__init__(engine, space)
        self._midx = midx
        self._kind = kind
        self._is_primary = is_primary
        self._attr_device_class = _METRIC_DEVICE_CLASS.get(kind)
        self._attr_native_unit_of_measurement = METRIC_UNIT.get(kind)
        self._attr_suggested_display_precision = METRIC_PRECISION.get(kind, 1)
        # Preserve the original CO₂ unique_id so a live deployment is unchanged.
        self._attr_unique_id = f"{space.subentry_id}_co2" if kind is MetricKind.CO2 else (
            f"{space.subentry_id}_{kind.value}"
        )
        # Named "Managed <metric>" via the per-kind translation key, so (a) no single
        # metric is the space's unnamed "default" (CO₂ used to be name=None → the bare
        # "<Space>" sensor), and (b) the entity_id gets a `managed_` marker that never
        # collides with the user's raw `<room>_<metric>` source sensors (FR-E8).
        self._attr_translation_key = kind.value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Seed this metric's EMA across restarts (NFR-2).
        if (last := await self.async_get_last_sensor_data()) is not None:
            mrt = self._engine.metric_runtime(self._space.subentry_id, self._midx)
            value = last.native_value
            if mrt is not None and isinstance(value, (int, float)):
                mrt.ema.seed(float(value), dt_util.utcnow())

    @property
    def available(self) -> bool:
        return self._engine.metric_available(self._space.subentry_id, self._midx)

    @property
    def native_value(self) -> float | None:
        return self._engine.metric_value(self._space.subentry_id, self._midx)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        sid = self._space.subentry_id
        mrt = self._engine.metric_runtime(sid, self._midx)
        raw = mrt.last_raw if mrt is not None else None
        attrs: dict[str, object] = {}
        if self._kind is MetricKind.CO2:
            # Preserve the v1 CO₂ attribute names exactly.
            attrs.update(
                {
                    "raw_co2": raw,
                    "co2_slope_per_min": self._engine.metric_slope_per_min(sid, self._midx),
                    "effective_ach": self._engine.space_effective_ach(sid),
                    "time_to_target_min": self._engine.space_time_to_target_min(sid),
                    "target_ppm": self._space.target_ppm,
                    "c_out_ppm": self._engine.c_out_ppm,
                }
            )
        else:
            attrs.update(
                {
                    "raw": raw,
                    "slope_per_min": self._engine.metric_slope_per_min(sid, self._midx),
                    "threshold": self._engine.metric_threshold(sid, self._midx),
                    "managed": self._engine.metric_manage(sid, self._midx),
                }
            )
        # The full ladder, viewable without re-authoring (engage/release + per-actuator
        # setpoints by name). Empty for a metric with no tiers.
        attrs["tiers"] = self._engine.metric_tiers_view(sid, self._midx)
        if self._is_primary:
            # The space-level summary rides on the primary metric's sensor (FR-E2/U2).
            attrs["status"] = self._engine.space_status(sid)
            attrs["reason"] = self._engine.space_reason(sid)
            attrs["active_actuators"] = self._engine.space_active_actuator_names(sid)
            attrs["driving_metrics"] = [k.value for k in self._engine.space_driving_metrics(sid)]
            attrs["mode"] = self._space.mode.value
        return attrs


class AeolusMetricSlopeSensor(_SpaceUpdateSensor):
    """Signed rate of change of a metric's EMA (à la VTherm's temp slope)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, engine: AeolusEngine, space: Space, midx: int, kind: MetricKind) -> None:
        super().__init__(engine, space)
        self._midx = midx
        self._kind = kind
        unit = METRIC_UNIT.get(kind)
        self._attr_native_unit_of_measurement = f"{unit}/min" if unit else None
        if kind is MetricKind.CO2:
            self._attr_translation_key = "co2_slope"
            self._attr_unique_id = f"{space.subentry_id}_co2_slope"
        else:
            self._attr_translation_key = f"{kind.value}_slope"
            self._attr_unique_id = f"{space.subentry_id}_{kind.value}_slope"

    @property
    def available(self) -> bool:
        return self._engine.metric_available(self._space.subentry_id, self._midx)

    @property
    def native_value(self) -> float | None:
        return self._engine.metric_slope_per_min(self._space.subentry_id, self._midx)


class AeolusAchSensor(_SpaceUpdateSensor):
    """Gap-normalized effective air-change rate (1/h) — CO₂ only (§8.3 FR-P3)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_translation_key = "air_change_rate"
    _attr_native_unit_of_measurement = "/h"

    def __init__(self, engine: AeolusEngine, space: Space, midx: int) -> None:
        super().__init__(engine, space)
        self._midx = midx
        self._attr_unique_id = f"{space.subentry_id}_air_change_rate"

    @property
    def available(self) -> bool:
        return self._engine.metric_available(self._space.subentry_id, self._midx)

    @property
    def native_value(self) -> float | None:
        return self._engine.space_effective_ach(self._space.subentry_id)


class AeolusReasonSensor(_SpaceUpdateSensor):
    """Plain-language explanation of the current action/inaction (FR-U2)."""

    _attr_translation_key = "reason"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, engine: AeolusEngine, space: Space) -> None:
        super().__init__(engine, space)
        self._attr_unique_id = f"{space.subentry_id}_reason"

    @property
    def native_value(self) -> str:
        return self._engine.space_reason(self._space.subentry_id)

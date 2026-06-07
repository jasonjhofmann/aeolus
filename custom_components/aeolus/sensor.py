"""Space CO2 sensor — the v0.1 read/observe slice (FR-E1/E2, FR-S).

One sensor per Space subentry. Native value = the smoothed (EMA) CO2; the
slope, gap-normalized effective ACH, time-to-target and status ride as
attributes. Push-based (no coordinator); seeds its EMA from RestoreSensor.
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import SUBENTRY_TYPE_SPACE
from .engine import AeolusEngine, signal_space_update
from .entity import AeolusSpaceEntity
from .models import AeolusConfigEntry, Space

# Read-only derived entities (parallel-updates rule, Silver).
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AeolusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one Space CO2 sensor per Space subentry."""
    engine = entry.runtime_data.engine
    for sub_id, sub in entry.subentries.items():
        if sub.subentry_type != SUBENTRY_TYPE_SPACE:
            continue
        space = engine.spaces[sub_id]
        async_add_entities(
            [
                AeolusSpaceCO2Sensor(engine, space),
                AeolusSlopeSensor(engine, space),
                AeolusAchSensor(engine, space),
            ],
            config_subentry_id=sub_id,  # links entity+device to the subentry
        )


class AeolusSpaceCO2Sensor(AeolusSpaceEntity, RestoreSensor):
    """Smoothed Space CO2 + derived attributes."""

    _attr_device_class = SensorDeviceClass.CO2
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
    _attr_name = None  # the device (Space) name is the entity name
    _attr_should_poll = False

    def __init__(self, engine: AeolusEngine, space: Space) -> None:
        super().__init__(engine, space)
        self._attr_unique_id = f"{space.subentry_id}_co2"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Seed the EMA across restarts (NFR-2).
        if (last := await self.async_get_last_sensor_data()) is not None:
            rt = self._engine.space_runtime(self._space.subentry_id)
            metric = rt.primary_metric if rt is not None else None
            value = last.native_value
            if metric is not None and isinstance(value, (int, float)):
                metric.ema.seed(float(value), dt_util.utcnow())
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

    @property
    def available(self) -> bool:
        return self._engine.space_available(self._space.subentry_id)

    @property
    def native_value(self) -> float | None:
        rt = self._engine.space_runtime(self._space.subentry_id)
        return None if rt is None else rt.ema_ppm

    @property
    def extra_state_attributes(self) -> dict[str, float | str | None]:
        sid = self._space.subentry_id
        rt = self._engine.space_runtime(sid)
        return {
            "raw_co2": None if rt is None else rt.last_raw_ppm,
            "co2_slope_per_min": None if rt is None else rt.slope_ppm_per_min,
            "effective_ach": self._engine.space_effective_ach(sid),
            "time_to_target_min": self._engine.space_time_to_target_min(sid),
            "target_ppm": self._space.target_ppm,
            "c_out_ppm": self._engine.c_out_ppm,
        }


class _DerivedSpaceSensor(AeolusSpaceEntity, SensorEntity):
    """Base for the per-Space derived diagnostic sensors (slope, ACH)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False
    _attr_suggested_display_precision = 2

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

    @property
    def available(self) -> bool:
        return self._engine.space_available(self._space.subentry_id)


class AeolusSlopeSensor(_DerivedSpaceSensor):
    """Signed CO2 slope (ppm/min) — the rate of change, à la VTherm's temp slope."""

    _attr_translation_key = "co2_slope"
    _attr_native_unit_of_measurement = "ppm/min"
    _attr_icon = "mdi:slope-downhill"

    def __init__(self, engine: AeolusEngine, space: Space) -> None:
        super().__init__(engine, space)
        self._attr_unique_id = f"{space.subentry_id}_co2_slope"

    @property
    def native_value(self) -> float | None:
        rt = self._engine.space_runtime(self._space.subentry_id)
        return None if rt is None else rt.slope_ppm_per_min


class AeolusAchSensor(_DerivedSpaceSensor):
    """Gap-normalized effective air-change rate (1/h). Meaningful during decay."""

    _attr_translation_key = "air_change_rate"
    _attr_native_unit_of_measurement = "/h"
    _attr_icon = "mdi:air-filter"

    def __init__(self, engine: AeolusEngine, space: Space) -> None:
        super().__init__(engine, space)
        self._attr_unique_id = f"{space.subentry_id}_air_change_rate"

    @property
    def native_value(self) -> float | None:
        return self._engine.space_effective_ach(self._space.subentry_id)

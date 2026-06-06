"""Space CO2 sensor — the v0.1 read/observe slice (FR-E1/E2, FR-S).

One sensor per Space subentry. Native value = the smoothed (EMA) CO2; the
slope, gap-normalized effective ACH, time-to-target and status ride as
attributes. Push-based (no coordinator); seeds its EMA from RestoreSensor.
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUBENTRY_TYPE_SPACE
from .engine import signal_space_update
from .entity import AeolusSpaceEntity
from .models import AeolusConfigEntry

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
            [AeolusSpaceCO2Sensor(engine, space)],
            config_subentry_id=sub_id,  # links entity+device to the subentry
        )


class AeolusSpaceCO2Sensor(AeolusSpaceEntity, RestoreSensor):
    """Smoothed Space CO2 + derived attributes."""

    _attr_device_class = SensorDeviceClass.CO2
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
    _attr_name = None  # the device (Space) name is the entity name
    _attr_should_poll = False

    def __init__(self, engine, space) -> None:
        super().__init__(engine, space)
        self._attr_unique_id = f"{space.subentry_id}_co2"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Seed the EMA across restarts (NFR-2).
        if (last := await self.async_get_last_sensor_data()) is not None:
            rt = self._engine.space_runtime(self._space.subentry_id)
            if rt is not None and last.native_value is not None:
                rt.ema.seed(float(last.native_value), None)
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

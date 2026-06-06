"""Per-Space target-CO2 number (FR-E3).

The configured subentry `target_ppm` is the source of truth: it's parsed into
`space.target_ppm` at setup and re-applied whenever the subentry is reconfigured
(via the reload-on-update listener). This number is a *live, in-session* knob —
it reads and nudges `space.target_ppm` but does NOT persist across reload, so a
reconfigure of the subentry always wins. (It used to be a RestoreNumber that
restored a stale value and clobbered the freshly-configured target — that's the
bug this design avoids.)
"""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUBENTRY_TYPE_SPACE
from .engine import AeolusEngine
from .entity import AeolusSpaceEntity
from .models import AeolusConfigEntry, Space

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AeolusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    engine = entry.runtime_data.engine
    for sub_id, sub in entry.subentries.items():
        if sub.subentry_type != SUBENTRY_TYPE_SPACE:
            continue
        async_add_entities(
            [AeolusTargetNumber(engine, engine.spaces[sub_id])],
            config_subentry_id=sub_id,
        )


class AeolusTargetNumber(AeolusSpaceEntity, NumberEntity):
    """The CO2 target the controller drives toward (FR-L1). Subentry-canonical."""

    _attr_translation_key = "target"
    _attr_device_class = NumberDeviceClass.CO2
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
    _attr_native_min_value = 420
    _attr_native_max_value = 2000
    _attr_native_step = 10
    _attr_mode = NumberMode.BOX

    def __init__(self, engine: AeolusEngine, space: Space) -> None:
        super().__init__(engine, space)
        self._attr_unique_id = f"{space.subentry_id}_target"

    @property
    def native_value(self) -> float:
        return self._space.target_ppm

    async def async_set_native_value(self, value: float) -> None:
        self._space.target_ppm = value
        self.async_write_ha_state()
        self._engine.request_evaluation()

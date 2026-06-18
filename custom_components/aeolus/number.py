"""Per-Space control numbers (FR-E3/E7).

The CO₂ Target number is unchanged (subentry-canonical; see note below). For
parity (FR-E7), every *other* driven metric (PM/AQI/generic) also gets a control
number — its tier-1 **engage threshold** — so its setpoint is adjustable from the
device card, not buried in the config-flow tier ladder.
"""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    METRIC_THRESHOLD_MAX,
    METRIC_UNIT,
    SUBENTRY_TYPE_SPACE,
    MetricKind,
)
from .engine import AeolusEngine, signal_space_added
from .entity import AeolusSpaceEntity
from .models import AeolusConfigEntry, Space

PARALLEL_UPDATES = 0

_METRIC_DEVICE_CLASS: dict[MetricKind, NumberDeviceClass | None] = {
    MetricKind.PM1: NumberDeviceClass.PM1,
    MetricKind.PM2_5: NumberDeviceClass.PM25,
    MetricKind.PM10: NumberDeviceClass.PM10,
    MetricKind.AQI: NumberDeviceClass.AQI,
    MetricKind.GENERIC: None,
}


def _build_space_numbers(engine: AeolusEngine, space: Space) -> list[NumberEntity]:
    """The CO₂ Target number plus a tier-1 threshold number per non-CO₂ metric."""
    numbers: list[NumberEntity] = []
    for midx, metric in enumerate(space.metrics):
        if metric.kind is MetricKind.CO2:
            numbers.append(AeolusTargetNumber(engine, space))
        elif metric.tiers:  # FR-E7: a threshold control per other driven metric
            numbers.append(
                AeolusMetricThresholdNumber(engine, space, midx, metric.kind)
            )
    return numbers


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AeolusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    engine = entry.runtime_data.engine

    @callback
    def _add_for_space(sub_id: str) -> None:
        space = engine.spaces.get(sub_id)
        if space is not None:
            async_add_entities(
                _build_space_numbers(engine, space), config_subentry_id=sub_id
            )

    for sub_id, sub in entry.subentries.items():
        if sub.subentry_type == SUBENTRY_TYPE_SPACE:
            _add_for_space(sub_id)
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, signal_space_added(entry.entry_id), _add_for_space
        )
    )


class AeolusTargetNumber(AeolusSpaceEntity, NumberEntity):
    """The CO2 target the controller drives toward (FR-L1). Subentry-canonical.

    The configured subentry `target_ppm` is the source of truth; this number is a
    live, in-session knob that reads/nudges it but does NOT persist across reload,
    so a reconfigure of the subentry always wins.
    """

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


class AeolusMetricThresholdNumber(AeolusSpaceEntity, NumberEntity):
    """Tier-1 engage threshold for a non-CO₂ metric (FR-E7). Live, in-session knob
    over the metric's ladder; a reconfigure re-authors the ladder and wins."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_step = 1

    def __init__(
        self, engine: AeolusEngine, space: Space, midx: int, kind: MetricKind
    ) -> None:
        super().__init__(engine, space)
        self._midx = midx
        self._kind = kind
        self._attr_translation_key = f"{kind.value}_threshold"
        self._attr_unique_id = f"{space.subentry_id}_{kind.value}_threshold"
        self._attr_device_class = _METRIC_DEVICE_CLASS.get(kind)
        self._attr_native_unit_of_measurement = METRIC_UNIT.get(kind)
        self._attr_native_max_value = METRIC_THRESHOLD_MAX.get(kind, 1000.0)

    @property
    def native_value(self) -> float | None:
        return self._engine.metric_threshold(self._space.subentry_id, self._midx)

    async def async_set_native_value(self, value: float) -> None:
        self._engine.set_metric_threshold(self._space.subentry_id, self._midx, value)
        self.async_write_ha_state()

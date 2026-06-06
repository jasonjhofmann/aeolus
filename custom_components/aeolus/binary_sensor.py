"""Per-Space status binary sensors (FR-E2): mitigation-active + attention."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import SUBENTRY_TYPE_SPACE
from .engine import AeolusEngine, signal_space_update
from .entity import AeolusSpaceEntity
from .models import AeolusConfigEntry, Space
from .safety import is_space_stale

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
        space = engine.spaces[sub_id]
        async_add_entities(
            [
                AeolusMitigationActiveBinarySensor(engine, space),
                AeolusAttentionBinarySensor(engine, space),
            ],
            config_subentry_id=sub_id,
        )


class _SpaceBinarySensor(AeolusSpaceEntity, BinarySensorEntity):
    _key: str

    def __init__(self, engine: AeolusEngine, space: Space) -> None:
        super().__init__(engine, space)
        self._attr_unique_id = f"{space.subentry_id}_{self._key}"

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


class AeolusMitigationActiveBinarySensor(_SpaceBinarySensor):
    """True while Aeolus is actively mitigating this space."""

    _key = "mitigation_active"
    _attr_translation_key = "mitigation_active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def is_on(self) -> bool:
        rt = self._engine.space_runtime(self._space.subentry_id)
        return bool(rt and rt.mitigating)


class AeolusAttentionBinarySensor(_SpaceBinarySensor):
    """True when the space needs attention: over-high, diverging, or stale."""

    _key = "attention"
    _attr_translation_key = "attention"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        rt = self._engine.space_runtime(self._space.subentry_id)
        if rt is None:
            return False
        if is_space_stale(rt, dt_util.utcnow()):
            return True
        ema = rt.ema_ppm
        if ema is None:
            return False
        # over the high threshold, or above target but not converging (slope >= 0)
        if ema > self._space.high_ppm:
            return True
        slope = rt.slope_ppm_per_min
        return ema > self._space.target_ppm and slope is not None and slope >= 0

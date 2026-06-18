"""Per-Space status binary sensors (FR-E2): mitigation-active + attention."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUBENTRY_TYPE_SPACE
from .engine import AeolusEngine, signal_space_added, signal_space_update
from .entity import AeolusSpaceEntity
from .models import AeolusConfigEntry, Space

PARALLEL_UPDATES = 0


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
                [
                    AeolusMitigationActiveBinarySensor(engine, space),
                    AeolusAttentionBinarySensor(engine, space),
                ],
                config_subentry_id=sub_id,
            )

    for sub_id, sub in entry.subentries.items():
        if sub.subentry_type == SUBENTRY_TYPE_SPACE:
            _add_for_space(sub_id)
    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_space_added(entry.entry_id), _add_for_space)
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
    """True while Aeolus is actively mitigating this space — for ANY metric (FR-E6)."""

    _key = "mitigation_active"
    _attr_translation_key = "mitigation_active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def is_on(self) -> bool:
        return self._engine.space_mitigating(self._space.subentry_id)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        sid = self._space.subentry_id
        return {
            "driving_metrics": [k.value for k in self._engine.space_driving_metrics(sid)],
            "active_actuators": self._engine.space_active_actuator_names(sid),
            "reason": self._engine.space_reason(sid),
        }


class AeolusAttentionBinarySensor(_SpaceBinarySensor):
    """True when ANY driven metric needs attention: over-high, not-improving, or
    stale — not CO₂ alone (FR-E6 correctness)."""

    _key = "attention"
    _attr_translation_key = "attention"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return self._engine.space_attention(self._space.subentry_id)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        sid = self._space.subentry_id
        return {
            "status": self._engine.space_status(sid),
            "reason": self._engine.space_reason(sid),
        }

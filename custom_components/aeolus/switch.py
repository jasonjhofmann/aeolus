"""Master enable switch (FR-E3): pause/resume all Aeolus management."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .engine import AeolusEngine
from .models import AeolusConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AeolusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    # One master switch, attached to the Aeolus manager device (parent entry).
    async_add_entities([AeolusMasterSwitch(entry.runtime_data.engine, entry.entry_id)])


class AeolusMasterSwitch(SwitchEntity, RestoreEntity):
    """When off, the controller stops commanding actuators (devices left as-is)."""

    _attr_has_entity_name = True
    _attr_translation_key = "management"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, engine: AeolusEngine, entry_id: str) -> None:
        self._engine = engine
        self._attr_unique_id = f"{entry_id}_management"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Aeolus",
            manufacturer="Aeolus",
            model="Manager",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._engine.paused = last.state == STATE_OFF

    @property
    def is_on(self) -> bool:
        return not self._engine.paused

    async def async_turn_on(self, **kwargs: object) -> None:
        self._engine.paused = False
        self.async_write_ha_state()
        self._engine.request_evaluation()

    async def async_turn_off(self, **kwargs: object) -> None:
        self._engine.paused = True
        self.async_write_ha_state()

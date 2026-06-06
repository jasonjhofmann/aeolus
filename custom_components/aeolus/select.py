"""Per-Space mode select (FR-E3/L6): manage / monitor / off."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import SUBENTRY_TYPE_SPACE, SpaceMode
from .entity import AeolusSpaceEntity
from .models import AeolusConfigEntry

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
            [AeolusModeSelect(engine, engine.spaces[sub_id])],
            config_subentry_id=sub_id,
        )


class AeolusModeSelect(AeolusSpaceEntity, SelectEntity, RestoreEntity):
    """How Aeolus treats this space."""

    _attr_translation_key = "mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = [m.value for m in SpaceMode]

    def __init__(self, engine, space) -> None:
        super().__init__(engine, space)
        self._attr_unique_id = f"{space.subentry_id}_mode"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None and (
            last.state in self._attr_options
        ):
            self._space.mode = SpaceMode(last.state)

    @property
    def current_option(self) -> str:
        return self._space.mode.value

    async def async_select_option(self, option: str) -> None:
        self._space.mode = SpaceMode(option)
        self.async_write_ha_state()
        self._engine.request_evaluation()

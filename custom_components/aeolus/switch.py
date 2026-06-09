"""Switches: the master enable (FR-E3) + per-metric Manage gates (FR-E9)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, METRIC_LABEL, SUBENTRY_TYPE_SPACE, MetricKind
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
    # One master switch, attached to the Aeolus manager device (parent entry).
    async_add_entities([AeolusMasterSwitch(engine, entry.entry_id)])
    # Per-metric Manage gates — only when a Space drives >1 metric (FR-E9); the
    # single-metric common case keeps just the master Mode select.
    for sub_id, sub in entry.subentries.items():
        if sub.subentry_type != SUBENTRY_TYPE_SPACE:
            continue
        space = engine.spaces[sub_id]
        if len(space.metrics) < 2:
            continue
        async_add_entities(
            [
                AeolusMetricManageSwitch(engine, space, midx, metric.kind)
                for midx, metric in enumerate(space.metrics)
            ],
            config_subentry_id=sub_id,
        )


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


class AeolusMetricManageSwitch(AeolusSpaceEntity, SwitchEntity, RestoreEntity):
    """FR-E9 per-metric gate: when off, this metric is monitor-only (its value +
    status still show, but it contributes no actuator demand). Advanced / off the
    common path → disabled by default; only created when a Space has >1 metric."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, engine: AeolusEngine, space: Space, midx: int, kind: MetricKind) -> None:
        super().__init__(engine, space)
        self._midx = midx
        self._attr_translation_key = f"manage_{kind.value}"
        self._attr_unique_id = f"{space.subentry_id}_manage_{kind.value}"
        # English fallback name; translations carry the localized form.
        self._attr_name = f"Manage {METRIC_LABEL.get(kind, kind.value)}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._engine.set_metric_manage(
                self._space.subentry_id, self._midx, last.state != STATE_OFF
            )

    @property
    def is_on(self) -> bool:
        return self._engine.metric_manage(self._space.subentry_id, self._midx)

    async def async_turn_on(self, **kwargs: object) -> None:
        self._engine.set_metric_manage(self._space.subentry_id, self._midx, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self._engine.set_metric_manage(self._space.subentry_id, self._midx, False)
        self.async_write_ha_state()

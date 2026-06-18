"""Shared entity base for Aeolus (has-entity-name; device-per-Space)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .engine import AeolusEngine
from .models import Space


class AeolusSpaceEntity(Entity):
    """Base for entities scoped to a Space subentry."""

    _attr_has_entity_name = True
    # Fully push/command-driven: state arrives via the engine's dispatcher signal
    # or in response to a command — never by polling, so no scan-interval timer.
    _attr_should_poll = False

    def __init__(self, engine: AeolusEngine, space: Space) -> None:
        self._engine = engine
        self._space = space
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, space.subentry_id)},
            name=space.name,
            manufacturer="Aeolus",
            model="Managed Space",
        )

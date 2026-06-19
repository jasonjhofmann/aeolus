"""Logbook humanizer for Aeolus action events (FR-U2).

Auto-discovered by Home Assistant: turns each ``aeolus_action`` event into a
readable Logbook line, e.g. "Kitchen Range Hood on — Kitchen: CO₂ tier 1".
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook.const import (
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.components.logbook.models import LazyEventPartialState
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, EVENT_AEOLUS_ACTION


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[
        [str, str, Callable[[LazyEventPartialState], dict[str, str]]], None
    ],
) -> None:
    """Register the describer for the aeolus_action event."""

    @callback
    def describe(event: LazyEventPartialState) -> dict[str, str]:
        data = event.data
        return {
            LOGBOOK_ENTRY_NAME: data.get("actuator_name") or "Aeolus",
            LOGBOOK_ENTRY_MESSAGE: data.get("message") or data.get("action", ""),
        }

    async_describe_event(DOMAIN, EVENT_AEOLUS_ACTION, describe)

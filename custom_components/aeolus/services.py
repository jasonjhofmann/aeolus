"""Aeolus actions, registered in async_setup (action-setup rule).

v0.1 ships `recalibrate` (clears observed/learned gains). set_target / set_mode
/ force_strategy land with the controller (FR-A1).
"""

from __future__ import annotations

from typing import cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .models import AeolusConfigEntry

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
SERVICE_RECALIBRATE = "recalibrate"

_RECALIBRATE_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register integration-level services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_RECALIBRATE):
        return

    async def _recalibrate(call: ServiceCall) -> None:
        entry = hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY_ID])
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_not_found"
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_not_loaded"
            )
        # TODO(FR-A1/S4): engine.reset_observed_gains()
        _ = cast(AeolusConfigEntry, entry).runtime_data.engine

    hass.services.async_register(
        DOMAIN, SERVICE_RECALIBRATE, _recalibrate, schema=_RECALIBRATE_SCHEMA
    )

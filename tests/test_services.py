"""Action tests (action-setup / action-exceptions)."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import DOMAIN
from custom_components.aeolus.services import SERVICE_RECALIBRATE


async def _loaded_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_recalibrate_loaded_entry(hass: HomeAssistant) -> None:
    entry = await _loaded_entry(hass)
    await hass.services.async_call(
        DOMAIN, SERVICE_RECALIBRATE, {"config_entry_id": entry.entry_id}, blocking=True
    )


async def test_recalibrate_unknown_entry_raises(hass: HomeAssistant) -> None:
    await _loaded_entry(hass)  # ensures the service is registered
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, SERVICE_RECALIBRATE, {"config_entry_id": "nope"}, blocking=True
        )
    # exception-translations: raised with a translation key, not a literal string.
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "entry_not_found"


async def test_recalibrate_unloaded_entry_raises(hass: HomeAssistant) -> None:
    entry = await _loaded_entry(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, SERVICE_RECALIBRATE, {"config_entry_id": entry.entry_id}, blocking=True
        )
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "entry_not_loaded"

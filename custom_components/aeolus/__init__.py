"""The Aeolus integration — adaptive, multi-zone CO2 & ventilation manager.

Calculated/local-push helper. Lifecycle per the verified HA pattern: no
DataUpdateCoordinator; a push engine on `entry.runtime_data`; actions
registered in `async_setup` (action-setup rule).
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_ACTUATOR_ENTITY,
    CONF_AGGREGATION,
    CONF_CO2_SENSORS,
    CONF_FILTER_EFFICIENCY,
    CONF_HIGH_PPM,
    CONF_MECHANISM,
    CONF_SERVED_SPACES,
    CONF_TARGET_PPM,
    CONF_VOLUME_FT3,
    DEFAULT_HIGH_PPM,
    DEFAULT_TARGET_PPM,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_SPACE,
    Aggregation,
    Gain,
    InfluenceType,
    Mechanism,
)
from .engine import AeolusEngine
from .models import Actuator, AeolusConfigEntry, AeolusData, Influence, Space
from .services import async_register_services

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-level actions (independent of any loaded entry)."""
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AeolusConfigEntry) -> bool:
    """Set up Aeolus from its config entry + subentries."""
    spaces, actuators = _parse_subentries(entry)
    engine = AeolusEngine(hass, entry.entry_id, spaces, actuators)
    entry.runtime_data = AeolusData(engine=engine)
    engine.async_start()
    entry.async_on_unload(engine.async_stop)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AeolusConfigEntry) -> bool:
    """Unload a config entry (config-entry-unloading rule)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _parse_subentries(
    entry: AeolusConfigEntry,
) -> tuple[dict[str, Space], dict[str, Actuator]]:
    """Turn config subentries into the engine's domain model."""
    spaces: dict[str, Space] = {}
    actuators: dict[str, Actuator] = {}
    for sub_id, sub in entry.subentries.items():
        data = sub.data
        if sub.subentry_type == SUBENTRY_TYPE_SPACE:
            spaces[sub_id] = Space(
                subentry_id=sub_id,
                name=sub.title,
                co2_sensors=list(data.get(CONF_CO2_SENSORS, [])),
                aggregation=Aggregation(data.get(CONF_AGGREGATION, Aggregation.MEAN)),
                target_ppm=float(data.get(CONF_TARGET_PPM, DEFAULT_TARGET_PPM)),
                high_ppm=float(data.get(CONF_HIGH_PPM, DEFAULT_HIGH_PPM)),
                volume_ft3=data.get(CONF_VOLUME_FT3),
            )
        elif sub.subentry_type == SUBENTRY_TYPE_ACTUATOR:
            actuators[sub_id] = Actuator(
                subentry_id=sub_id,
                name=sub.title,
                entity_id=data[CONF_ACTUATOR_ENTITY],
                mechanism=Mechanism(data.get(CONF_MECHANISM, Mechanism.BALANCED)),
                filter_efficiency=float(data.get(CONF_FILTER_EFFICIENCY, 0.0)),
                influences=[
                    Influence(
                        space_id=space_id,
                        gain=Gain.MEDIUM,
                        influence_type=InfluenceType.DIRECT,
                    )
                    for space_id in data.get(CONF_SERVED_SPACES, [])
                ],
            )
    return spaces, actuators

"""Config + subentry flows for Aeolus (FR-C1/C2).

One parent config entry (the "manager"); Spaces and Actuators are config
subentries (HA 2025.4+). API verified against core `dev`:
`async_get_supported_subentry_types` + `ConfigSubentryFlow` subclasses with
`async_step_user` / `async_step_reconfigure`.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACTUATOR_ENTITY,
    CONF_AGGREGATION,
    CONF_CO2_SENSORS,
    CONF_FILTER_EFFICIENCY,
    CONF_HIGH_PPM,
    CONF_MECHANISM,
    CONF_ON_SPEED_PCT,
    CONF_OUTDOOR_AQ_ENTITY,
    CONF_OUTDOOR_AQ_THRESHOLD,
    CONF_REARM_INTERVAL,
    CONF_SERVED_SPACES,
    CONF_TARGET_PPM,
    CONF_VOLUME_FT3,
    DEFAULT_HIGH_PPM,
    DEFAULT_TARGET_PPM,
    DOMAIN,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_SPACE,
    Aggregation,
    Mechanism,
)

_CO2_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        domain="sensor", device_class="carbon_dioxide", multiple=True
    )
)
_ACTUATOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["fan", "switch", "input_boolean", "cover"])
)


class AeolusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single parent entry; the real configuration lives in subentries."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # Single manager instance (unique-config-entry rule).
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Aeolus", data={})
        return self.async_show_form(step_id="user")

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            SUBENTRY_TYPE_SPACE: SpaceSubentryFlow,
            SUBENTRY_TYPE_ACTUATOR: ActuatorSubentryFlow,
        }


def _space_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=d.get(CONF_NAME, "")): str,
            vol.Required(CONF_CO2_SENSORS, default=d.get(CONF_CO2_SENSORS, [])): _CO2_SENSOR_SELECTOR,
            vol.Optional(
                CONF_AGGREGATION, default=d.get(CONF_AGGREGATION, Aggregation.MEAN.value)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[a.value for a in Aggregation],
                    translation_key="aggregation",
                )
            ),
            vol.Optional(CONF_TARGET_PPM, default=d.get(CONF_TARGET_PPM, DEFAULT_TARGET_PPM)): vol.All(
                vol.Coerce(int), vol.Range(min=420, max=2000)
            ),
            vol.Optional(CONF_HIGH_PPM, default=d.get(CONF_HIGH_PPM, DEFAULT_HIGH_PPM)): vol.All(
                vol.Coerce(int), vol.Range(min=420, max=5000)
            ),
            vol.Optional(CONF_VOLUME_FT3, default=d.get(CONF_VOLUME_FT3)): vol.Any(
                None, vol.Coerce(float)
            ),
            # Outdoor-AQ veto (FR-G3): the PM sensor for this space's outdoor air
            # + the indoor-contribution threshold above which outdoor-air
            # strategies are blocked. Per-actuator intake sensor (below) overrides.
            vol.Optional(
                CONF_OUTDOOR_AQ_ENTITY, default=d.get(CONF_OUTDOOR_AQ_ENTITY)
            ): vol.Any(None, selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )),
            vol.Optional(
                CONF_OUTDOOR_AQ_THRESHOLD, default=d.get(CONF_OUTDOOR_AQ_THRESHOLD)
            ): vol.Any(None, vol.Coerce(float)),
        }
    )


class SpaceSubentryFlow(ConfigSubentryFlow):
    """Add / reconfigure a managed Space (FR-C3)."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(step_id="user", data_schema=_space_schema())

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, title=user_input[CONF_NAME], data=user_input
            )
        return self.async_show_form(
            step_id="reconfigure", data_schema=_space_schema(dict(subentry.data))
        )


def _actuator_schema(
    space_options: list[selector.SelectOptionDict],
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=d.get(CONF_NAME, "")): str,
            vol.Required(
                CONF_ACTUATOR_ENTITY, default=d.get(CONF_ACTUATOR_ENTITY)
            ): _ACTUATOR_SELECTOR,
            vol.Required(
                CONF_MECHANISM, default=d.get(CONF_MECHANISM, Mechanism.BALANCED.value)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[m.value for m in Mechanism], translation_key="mechanism"
                )
            ),
            # v0.1: which Spaces this actuator DIRECTLY reduces (FR-C4 simplified).
            # Induced/diffusive influence rows + per-pathway AQ source come in v1.1.
            vol.Optional(
                CONF_SERVED_SPACES, default=d.get(CONF_SERVED_SPACES, [])
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=space_options, multiple=True)
            ),
            vol.Optional(
                CONF_FILTER_EFFICIENCY, default=d.get(CONF_FILTER_EFFICIENCY, 0.0)
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
            # Re-arm (FR-L5b): minutes between ON re-sends for a load that
            # auto-offs internally (switch keeps reporting `on`). 0 = off.
            vol.Optional(
                CONF_REARM_INTERVAL, default=d.get(CONF_REARM_INTERVAL, 0)
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=120)),
            # Fan on-speed (FR-L4b): fans only. % speed to set on turn-on. 0 = default.
            vol.Optional(
                CONF_ON_SPEED_PCT, default=d.get(CONF_ON_SPEED_PCT, 0)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=5, mode=selector.NumberSelectorMode.SLIDER,
                    unit_of_measurement="%",
                )
            ),
            # Per-pathway outdoor-AQ source (FR-G3, v2.3): the PM sensor at THIS
            # actuator's intake (e.g. the AirVisual at the ERV intake). Falls back
            # to the space's sensor when unset.
            vol.Optional(
                CONF_OUTDOOR_AQ_ENTITY, default=d.get(CONF_OUTDOOR_AQ_ENTITY)
            ): vol.Any(None, selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )),
        }
    )


class ActuatorSubentryFlow(ConfigSubentryFlow):
    """Add / reconfigure a ventilation Actuator (FR-C4)."""

    def _space_options(self) -> list[selector.SelectOptionDict]:
        """Spaces currently defined on the parent entry (subentry_id → title)."""
        return [
            selector.SelectOptionDict(value=sub_id, label=sub.title)
            for sub_id, sub in self._get_entry().subentries.items()
            if sub.subentry_type == SUBENTRY_TYPE_SPACE
        ]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            # TODO(FR-C8): reject recirculating air purifiers here.
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=_actuator_schema(self._space_options())
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, title=user_input[CONF_NAME], data=user_input
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_actuator_schema(self._space_options(), dict(subentry.data)),
        )

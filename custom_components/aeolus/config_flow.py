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
    ConfigSubentry,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACTUATOR_ENTITY,
    CONF_AGGREGATION,
    CONF_CO2_SENSORS,
    CONF_ENABLE_LADDERS,
    CONF_FILTER_EFFICIENCY,
    CONF_HIGH_PPM,
    CONF_MECHANISM,
    CONF_METRIC_KIND,
    CONF_METRIC_SENSORS,
    CONF_METRICS,
    CONF_ON_SPEED_PCT,
    CONF_OVERRIDE_GRACE_MIN,
    CONF_OUTDOOR_AQ_ENTITY,
    CONF_OUTDOOR_AQ_THRESHOLD,
    CONF_REARM_INTERVAL,
    CONF_SERVED_SPACES,
    CONF_TARGET_PPM,
    CONF_TIER_ENGAGE,
    CONF_TIER_SETPOINTS,
    CONF_TIERS,
    CONF_VOLUME_FT3,
    DEFAULT_HIGH_PPM,
    DEFAULT_TARGET_PPM,
    DOMAIN,
    SUBENTRY_TYPE_ACTUATOR,
    SUBENTRY_TYPE_SPACE,
    Aggregation,
    Mechanism,
    MetricKind,
)

# Step-local key: "also configure a graduated PM/AQI response" (not stored).
CONF_ADD_GRADUATED = "add_graduated"
CONF_ADD_ANOTHER_TIER = "add_another_tier"

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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AeolusOptionsFlow:
        return AeolusOptionsFlow()


class AeolusOptionsFlow(OptionsFlow):
    """Manager-level options — advanced-feature toggles (FR-C10).

    No reload is triggered: the only option (graduated-ladder visibility) affects
    how the Space form renders next time, nothing in the running engine.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ENABLE_LADDERS,
                        default=self.config_entry.options.get(
                            CONF_ENABLE_LADDERS, False
                        ),
                    ): selector.BooleanSelector(),
                }
            ),
        )


def _space_schema(
    defaults: dict[str, Any] | None = None, *, show_graduated: bool = True
) -> vol.Schema:
    d = defaults or {}
    fields: dict[Any, Any] = {
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
    # v3: branch into the metric/tier wizard to add a graduated PM/AQI response
    # (FR-P/FR-T). Gated behind the manager's "enable ladders" option (FR-C10) so
    # the common simple-CO₂ case isn't cluttered by it. When hidden, the toggle
    # simply isn't offered and the flow stays on the simple path.
    if show_graduated:
        fields[vol.Optional(CONF_ADD_GRADUATED, default=False)] = selector.BooleanSelector()
    return vol.Schema(fields)


def _metric_schema() -> vol.Schema:
    """Pick the pollutant + its sensors for one graduated metric (FR-P1)."""
    return vol.Schema(
        {
            vol.Required(CONF_METRIC_KIND, default=MetricKind.PM2_5.value): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[k.value for k in MetricKind if k is not MetricKind.CO2],
                    translation_key="metric_kind",
                )
            ),
            vol.Required(CONF_METRIC_SENSORS): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            ),
            vol.Optional(
                CONF_AGGREGATION, default=Aggregation.MAX.value
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[a.value for a in Aggregation], translation_key="aggregation"
                )
            ),
        }
    )


def _tier_schema(actuators: list[tuple[str, str]]) -> vol.Schema:
    """One tier: its engage threshold + a setpoint (0 = inactive) per actuator.

    Actuator fields are keyed by the actuator's title so the form labels them
    legibly (dynamic keys can't be translated)."""
    fields: dict[Any, Any] = {
        vol.Required(CONF_TIER_ENGAGE): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=2000, step=1, mode=selector.NumberSelectorMode.BOX
            )
        )
    }
    for title, _ in actuators:
        fields[vol.Optional(title, default=0)] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=100, step=5, mode=selector.NumberSelectorMode.SLIDER,
                unit_of_measurement="%",
            )
        )
    fields[vol.Optional(CONF_ADD_ANOTHER_TIER, default=False)] = selector.BooleanSelector()
    return vol.Schema(fields)


class SpaceSubentryFlow(ConfigSubentryFlow):
    """Add / reconfigure a managed Space (FR-C3), optionally with graduated
    PM/AQI metric ladders (FR-P/FR-T) authored via a metric → tier wizard."""

    _basics: dict[str, Any]
    _metrics: list[dict[str, Any]]
    _tiers: list[dict[str, Any]]
    _metric_kind: str
    _metric_sensors: list[str]
    _metric_agg: str
    _reconfigure: bool
    _title: str
    _subentry: ConfigSubentry

    def _actuators(self) -> list[tuple[str, str]]:
        """(title, subentry_id) for each actuator on the parent entry."""
        return [
            (sub.title, sub_id)
            for sub_id, sub in self._get_entry().subentries.items()
            if sub.subentry_type == SUBENTRY_TYPE_ACTUATOR
        ]

    def _ladders_enabled(self) -> bool:
        """Whether the manager opted into the graduated tier wizard (FR-C10)."""
        return bool(self._get_entry().options.get(CONF_ENABLE_LADDERS, False))

    def _begin(self, user_input: dict[str, Any]) -> bool:
        """Stash the basics; return whether to enter the graduated wizard."""
        add = bool(user_input.pop(CONF_ADD_GRADUATED, False))
        self._basics = user_input
        self._title = user_input[CONF_NAME]
        return add

    def _finish(self) -> SubentryFlowResult:
        data = dict(self._basics)
        if self._metrics:
            data[CONF_METRICS] = self._metrics
        if self._reconfigure:
            return self.async_update_and_abort(
                self._get_entry(), self._subentry, title=self._title, data=data
            )
        return self.async_create_entry(title=self._title, data=data)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._reconfigure = False
        if user_input is not None:
            enter_wizard = self._begin(user_input)
            self._metrics = []
            return await self.async_step_metric() if enter_wizard else self._finish()
        return self.async_show_form(
            step_id="user",
            data_schema=_space_schema(show_graduated=self._ladders_enabled()),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._reconfigure = True
        self._subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            enter_wizard = self._begin(user_input)
            # Re-authoring replaces the metrics; otherwise carry them forward.
            self._metrics = [] if enter_wizard else list(self._subentry.data.get(CONF_METRICS, []))
            return await self.async_step_metric() if enter_wizard else self._finish()
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_space_schema(
                dict(self._subentry.data), show_graduated=self._ladders_enabled()
            ),
        )

    async def async_step_metric(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._metric_kind = user_input[CONF_METRIC_KIND]
            self._metric_sensors = list(user_input[CONF_METRIC_SENSORS])
            self._metric_agg = user_input.get(CONF_AGGREGATION, Aggregation.MAX.value)
            self._tiers = []
            return await self.async_step_tier()
        return self.async_show_form(step_id="metric", data_schema=_metric_schema())

    async def async_step_tier(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        actuators = self._actuators()
        if user_input is not None:
            setpoints = {
                aid: int(user_input.get(title) or 0)
                for title, aid in actuators
                if int(user_input.get(title) or 0) > 0
            }
            self._tiers.append(
                {CONF_TIER_ENGAGE: float(user_input[CONF_TIER_ENGAGE]), CONF_TIER_SETPOINTS: setpoints}
            )
            if user_input.get(CONF_ADD_ANOTHER_TIER):
                return await self.async_step_tier()
            self._metrics.append(
                {
                    CONF_METRIC_KIND: self._metric_kind,
                    CONF_METRIC_SENSORS: self._metric_sensors,
                    CONF_AGGREGATION: self._metric_agg,
                    CONF_TIERS: self._tiers,
                }
            )
            return self._finish()
        return self.async_show_form(
            step_id="tier",
            data_schema=_tier_schema(actuators),
            description_placeholders={"tier": str(len(self._tiers) + 1)},
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
            # Override confirmation delay (FR-L7b): minutes a divergence must persist
            # before Aeolus yields. 0 = immediate. ~2 for cloud actuators (LG ThinQ).
            vol.Optional(
                CONF_OVERRIDE_GRACE_MIN, default=d.get(CONF_OVERRIDE_GRACE_MIN, 0)
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=30)),
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

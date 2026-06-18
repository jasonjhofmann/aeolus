"""Manager options flow (FR-C10) — the graduated tier wizard is opt-in.

The PM/AQI ladder UI is powerful but confusing, so the per-Space `add_graduated`
toggle (and therefore the whole metric→tier wizard) only appears when the
manager's "enable ladders" option is on. Turning it off must never destroy
ladders already authored on a Space.
"""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.config_flow import CONF_ADD_GRADUATED
from custom_components.aeolus.const import (
    CONF_CO2_SENSORS,
    CONF_ENABLE_LADDERS,
    CONF_METRIC_KIND,
    CONF_METRIC_SENSORS,
    CONF_METRICS,
    CONF_TIERS,
    DOMAIN,
    SUBENTRY_TYPE_SPACE,
)


def _space_form_keys(result: dict) -> set[str]:
    """The field names offered by a Space form's schema."""
    return {getattr(k, "schema", k) for k in result["data_schema"].schema}


async def _manager(hass: HomeAssistant, **kw) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={}, **kw)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_space_form_hides_ladder_toggle_by_default(hass: HomeAssistant) -> None:
    """With no option set, the Space form has no graduated-response toggle."""
    entry = await _manager(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_SPACE), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert CONF_ADD_GRADUATED not in _space_form_keys(result)


async def test_options_flow_enables_ladder_toggle(hass: HomeAssistant) -> None:
    """Turning the option on makes the toggle appear on the Space form."""
    entry = await _manager(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ENABLE_LADDERS: True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_ENABLE_LADDERS] is True

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_SPACE), context={"source": SOURCE_USER}
    )
    assert CONF_ADD_GRADUATED in _space_form_keys(result)


async def test_disabling_ladders_preserves_existing_metrics(
    hass: HomeAssistant,
) -> None:
    """A Space that already has a ladder keeps it when reconfigured with the
    feature turned off (the toggle is hidden, metrics carry forward)."""
    metric = {
        CONF_METRIC_KIND: "pm2_5",
        CONF_METRIC_SENSORS: ["sensor.pm"],
        CONF_TIERS: [{"engage_at": 30.0, "setpoints": {}}],
    }
    from homeassistant.config_entries import ConfigSubentryData

    entry = await _manager(
        hass,
        options={CONF_ENABLE_LADDERS: False},
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_SPACE,
                title="Kitchen",
                unique_id=None,
                data={
                    CONF_NAME: "Kitchen",
                    CONF_CO2_SENSORS: ["sensor.k"],
                    "target_ppm": 800,
                    "high_ppm": 1000,
                    CONF_METRICS: [metric],
                },
            )
        ],
    )
    sub_id = next(
        s.subentry_id
        for s in entry.subentries.values()
        if s.subentry_type == SUBENTRY_TYPE_SPACE
    )

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_SPACE),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": sub_id},
    )
    assert CONF_ADD_GRADUATED not in _space_form_keys(result)

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Kitchen",
            CONF_CO2_SENSORS: ["sensor.k"],
            "aggregation": "mean",
            "target_ppm": 750,
            "high_ppm": 950,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    # CO₂ edit applied, ladder untouched.
    assert entry.subentries[sub_id].data["target_ppm"] == 750
    assert entry.subentries[sub_id].data[CONF_METRICS] == [metric]

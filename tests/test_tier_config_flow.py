"""v3 config-flow tier editor — the Space metric→tier wizard authors CONF_METRICS."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.config_flow import (
    CONF_ADD_ANOTHER_TIER,
    CONF_ADD_GRADUATED,
)
from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITY,
    CONF_CO2_SENSORS,
    CONF_ENABLE_LADDERS,
    CONF_METRIC_KIND,
    CONF_METRIC_SENSORS,
    CONF_METRICS,
    CONF_TIER_ENGAGE,
    CONF_TIER_SETPOINTS,
    CONF_TIERS,
    DOMAIN,
    SUBENTRY_TYPE_SPACE,
)


async def test_space_wizard_creates_pm_ladder(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.kpm", "12")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        options={CONF_ENABLE_LADDERS: True},  # FR-C9: wizard is opt-in
        subentries_data=[
            ConfigSubentryData(
                subentry_type="actuator",
                title="Hood",
                unique_id=None,
                data={CONF_ACTUATOR_ENTITY: "fan.hood", "mechanism": "exhaust"},
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hood_id = next(sid for sid, s in entry.subentries.items() if s.title == "Hood")

    subs = hass.config_entries.subentries
    r = await subs.async_init(
        (entry.entry_id, SUBENTRY_TYPE_SPACE), context={"source": "user"}
    )
    assert r["type"] is FlowResultType.FORM and r["step_id"] == "user"

    r = await subs.async_configure(
        r["flow_id"],
        {CONF_NAME: "Kitchen", CONF_CO2_SENSORS: [], CONF_ADD_GRADUATED: True},
    )
    assert r["step_id"] == "metric"

    r = await subs.async_configure(
        r["flow_id"],
        {CONF_METRIC_KIND: "pm2_5", CONF_METRIC_SENSORS: ["sensor.kpm"]},
    )
    assert r["step_id"] == "tier"

    # Two tiers: 30 → Hood 20%, then 80 → Hood 100%.
    r = await subs.async_configure(
        r["flow_id"], {CONF_TIER_ENGAGE: 30, "Hood": 20, CONF_ADD_ANOTHER_TIER: True}
    )
    assert r["step_id"] == "tier"
    r = await subs.async_configure(
        r["flow_id"], {CONF_TIER_ENGAGE: 80, "Hood": 100, CONF_ADD_ANOTHER_TIER: False}
    )
    assert r["type"] is FlowResultType.CREATE_ENTRY

    space = next(
        s for s in entry.subentries.values() if s.subentry_type == SUBENTRY_TYPE_SPACE
    )
    metrics = space.data[CONF_METRICS]
    assert metrics[0][CONF_METRIC_KIND] == "pm2_5"
    assert metrics[0][CONF_METRIC_SENSORS] == ["sensor.kpm"]
    tiers = metrics[0][CONF_TIERS]
    assert [t[CONF_TIER_ENGAGE] for t in tiers] == [30, 80]
    assert tiers[0][CONF_TIER_SETPOINTS] == {hood_id: 20}
    assert tiers[1][CONF_TIER_SETPOINTS] == {hood_id: 100}

    # And the engine parses it into a live PM metric with a 2-tier ladder.
    eng = entry.runtime_data.engine
    sid = next(s for s in eng.spaces if eng.spaces[s].name == "Kitchen")
    pm = eng.spaces[sid].metrics[0]
    assert pm.kind.value == "pm2_5"
    assert [t.engage_at for t in pm.tiers] == [30, 80]
    assert pm.tiers[1].setpoints == {hood_id: 100}

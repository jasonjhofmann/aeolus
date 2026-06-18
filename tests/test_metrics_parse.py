"""v3 phase α — metric synthesis (legacy CO₂), explicit metrics, multi-entity."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aeolus.const import (
    CONF_ACTUATOR_ENTITIES,
    CONF_CO2_SENSORS,
    CONF_METRIC_KIND,
    CONF_METRIC_SENSORS,
    CONF_METRICS,
    CONF_TIER_ENGAGE,
    CONF_TIERS,
    DOMAIN,
    Mechanism,
    MetricKind,
)


async def test_phase_alpha_parsing(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.z_co2", "650")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="space",
                title="CO2 Zone",
                unique_id=None,
                data={
                    CONF_CO2_SENSORS: ["sensor.z_co2"],
                    "target_ppm": 800,
                    "high_ppm": 1000,
                },
            ),
            ConfigSubentryData(
                subentry_type="space",
                title="PM Zone",
                unique_id=None,
                data={
                    CONF_METRICS: [
                        {
                            CONF_METRIC_KIND: "pm2_5",
                            CONF_METRIC_SENSORS: ["sensor.kitchen_pm2_5"],
                            CONF_TIERS: [
                                {CONF_TIER_ENGAGE: 80},
                                {CONF_TIER_ENGAGE: 30},
                            ],
                        }
                    ]
                },
            ),
            ConfigSubentryData(
                subentry_type="actuator",
                title="Purifier group",
                unique_id=None,
                data={
                    CONF_ACTUATOR_ENTITIES: ["fan.p1", "fan.p2"],
                    "mechanism": "filter",
                },
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    eng = entry.runtime_data.engine

    # Legacy CO₂ space → synthesized one CO₂ metric with a 2-tier ladder (high→target).
    co2 = next(s for s in eng.spaces.values() if s.name == "CO2 Zone")
    assert len(co2.metrics) == 1
    assert co2.metrics[0].kind is MetricKind.CO2
    assert co2.metrics[0].sensors == ["sensor.z_co2"]
    assert co2.metrics[0].tiers[0].engage_at == 1000
    assert co2.metrics[0].tiers[0].release_at == 800

    # Explicit PM metric → tiers sorted ascending by engage_at; default release applied.
    pm = next(s for s in eng.spaces.values() if s.name == "PM Zone")
    assert pm.metrics[0].kind is MetricKind.PM2_5
    assert [t.engage_at for t in pm.metrics[0].tiers] == [30, 80]
    assert pm.metrics[0].tiers[0].release_at == 30 * 0.85  # DEFAULT_RELEASE_FRACTION

    # Multi-entity (group) actuator + filter mechanism.
    grp = next(a for a in eng.actuators.values() if a.name == "Purifier group")
    assert grp.entities == ["fan.p1", "fan.p2"]
    assert grp.entity_id == "fan.p1"
    assert grp.mechanism is Mechanism.FILTER

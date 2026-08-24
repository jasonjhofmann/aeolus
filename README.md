<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/custom_components/aeolus/brand/dark_logo@2x.png">
    <img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/custom_components/aeolus/brand/logo@2x.png" alt="Aeolus" width="380">
  </picture>
</p>

<p align="center"><strong>Multi-zone, multi-pollutant ventilation control for Home Assistant. Aeolus models rooms that share air, applies hard safety vetoes, and states the reason for every action it takes.</strong></p>

<p align="center">
  <a href="https://github.com/jasonjhofmann/aeolus/releases"><img src="https://img.shields.io/github/v/release/jasonjhofmann/aeolus" alt="Release"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-custom-41BDF5.svg" alt="HACS"></a>
  <a href="https://github.com/jasonjhofmann/aeolus/actions/workflows/ci.yml"><img src="https://github.com/jasonjhofmann/aeolus/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://developers.home-assistant.io/docs/core/integration-quality-scale/"><img src="https://img.shields.io/badge/quality%20scale-platinum-e5e4e2.svg" alt="Quality scale: Platinum"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.7%2B-41BDF5.svg" alt="Home Assistant 2026.7+">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/jasonjhofmann/aeolus" alt="License"></a>
</p>

---

> In Greek myth, Aeolus is the keeper of the winds: he holds many and releases each on demand. This integration does that job for a house. It decides which ERV, exhaust fan, range hood, purifier, or window opener to run, and it tells you why.

<p align="center">
  <img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/dashboard-managed-co2.png" alt="A managed space's CO₂ falling from 964 to 655 ppm, with slope, air-change rate, target, and the active control ladder" width="850">
</p>
<p align="center"><em>A managed bedroom overnight: smoothed CO₂, slope, air-change rate, and the control ladder that brought the level down. Built from Aeolus entities on a standard dashboard.</em></p>

## Why Aeolus

A template automation can turn on a fan when CO₂ passes 1000 ppm. Aeolus handles the harder parts of the problem:

- Rooms share air, and one actuator affects many rooms. An ERV can serve four bedrooms, and a bath exhaust depressurizes the whole envelope. Aeolus models these couplings and arbitrates demand across zones.
- More ventilation sometimes makes the air worse. During a wildfire smoke event, with a weak intake filter, or on a stale sensor, running fans pulls in a new hazard while removing the old one. Aeolus vetoes ventilation in those conditions.
- A recirculating purifier removes particulates. It does nothing for CO₂, so Aeolus rejects a purifier for CO₂ duty at configuration time.
- Raw ppm/min depends on how high CO₂ currently is, because CO₂ decays exponentially toward the outdoor level. The same fan looks fast at 2000 ppm and slow at 800. Aeolus reports the concentration-normalized air-change rate (ACH), which you can compare across rooms, fans, and days.

## Features

- Spaces group sensors and actuators into zones. One actuator can serve several spaces, with hysteresis control in each space and arbitration across them.
- A space can be driven by CO₂, PM1, PM2.5, PM10, AQI, or a generic level. Each metric gets its own tier ladder, for example a range hood at 20% above 30 µg/m³ and everything at 100% above 80, with separate engage and release thresholds so nothing short-cycles.
- Every space reports a time-aware smoothed value, a signed slope per minute, the effective air-change rate, and a time-to-target estimate.
- Safety vetoes cover outdoor air quality (filter-aware, per intake pathway), stale sensors, and per-actuator runtime caps.
- A manual change to an actuator wins. Aeolus yields control for 30 minutes, and a configurable confirmation delay keeps flappy cloud devices such as LG ThinQ from triggering false overrides.
- The **Status reason** sensor states in plain language why Aeolus is acting or holding. Every decision also appears in the Logbook and in a durable action history in diagnostics.
- Configuration is entirely in the UI. You can add and remove spaces and actuators live, without a reload.
- The integration is event-driven, has no external dependencies, passes `mypy --strict`, and declares Platinum on the Home Assistant integration quality scale.

Planned next: humidity and moisture management (shower-steam exhaust, an over-dry veto), pressure-induced coupling, radon and combustion-safety budgets, and auto-calibration of actuator effectiveness. The full design is in [REQUIREMENTS.md](REQUIREMENTS.md).

## Installation

Aeolus requires Home Assistant 2026.7 or later (config subentries, `UnitOfDensity`/`UnitOfRatio`). On older versions, install [v0.6.1](https://github.com/jasonjhofmann/aeolus/releases/tag/v0.6.1) instead.

### HACS (recommended)

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jasonjhofmann&repository=aeolus&category=integration)

1. Click the badge above, or add `https://github.com/jasonjhofmann/aeolus` in HACS as a custom repository of type **Integration**.
2. Install **Aeolus**.
3. Restart Home Assistant.
4. Go to **Settings > Devices & Services > Add integration** and select **Aeolus**, or click:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=aeolus)

### Manual installation

Copy `custom_components/aeolus/` into your Home Assistant `config/custom_components/` directory, restart, and add the integration as in step 4 above.

## Configuration

All configuration happens in the UI. The single Aeolus entry holds two kinds of subentries:

- **Space**: a managed zone. Choose its CO₂ sensors and how to combine them, a target and a high threshold in ppm, an optional room volume, and an optional outdoor air-quality sensor with a veto threshold. With graduated ladders enabled in the options flow, a space can also be driven by PM, AQI, or generic metrics, each with its own tier ladder.
- **Actuator**: a device that moves or filters air. Choose the entity to control (a fan, switch, input_boolean, or cover, or a group from one domain), its air mechanism (balanced ERV, supply, exhaust, transfer, window, or filter), the spaces it serves, its intake filter efficiency, an optional intake air-quality sensor, a fan on-speed, a re-arm interval, and a manual-override confirmation delay.

<table>
  <tr>
    <td align="center"><img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/flow-add-space.png" alt="The Add a space dialog: name, CO₂ sensors, aggregation, and target" width="430"></td>
    <td align="center"><img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/flow-add-actuator.png" alt="The Add an actuator dialog: entity, air mechanism, served spaces, filter efficiency" width="430"></td>
  </tr>
  <tr>
    <td align="center"><em>Adding a space: sensors, aggregation, and targets.</em></td>
    <td align="center"><em>Adding an actuator: mechanism, served spaces, and filtration.</em></td>
  </tr>
</table>

<p align="center">
  <img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/flow-options.png" alt="The options dialog explaining control precedence, with the graduated-ladders toggle" width="560">
</p>
<p align="center"><em>The options flow documents the control precedence and enables the tier-ladder wizard.</em></p>

Adding or removing a space or actuator takes effect live, without reloading the entry, and edits to an existing one apply as soon as you save. No restart needed.

## Supported devices

Aeolus is a calculated integration. It talks to no hardware and needs no cloud account. It reads and controls entities that already exist in your Home Assistant instance, so any device that surfaces a standard entity works.

Sources it reads, per space:

- **CO₂ sensors**: any `sensor` with `device_class: carbon_dioxide` (ppm). Tested with Aranet4, AirGradient, Airthings, and SCD4x-based ESPHome sensors.
- **Particulate and AQI sensors** (optional, for graduated ladders): any numeric `sensor` reporting PM1, PM2.5, or PM10 in µg/m³, an AQI, or a generic value. Tested with AirVisual/IQAir, PurpleAir, AirGradient, and Aranet Radon+.
- **Outdoor air-quality sensor** (optional): any PM `sensor` measuring the air a ventilation pathway would pull in. Used by the outdoor-air veto.

Actuators it controls:

- `fan` (on/off and percentage), `switch`, `input_boolean`, and `cover` for windows and openers. One actuator can drive a group of same-domain entities. Mechanisms: balanced (ERV/HRV), supply, exhaust, transfer, window, and filter (a recirculating purifier, used for PM only).

Aeolus never modifies or reconfigures the entities it uses. It reads their state and calls their standard `turn_on`, `turn_off`, `set_percentage`, `open_cover`, and `close_cover` services.

## Entities

Per space (a device named after the zone):

| Platform | Entity | Purpose |
| --- | --- | --- |
| `sensor` | **Managed `<metric>`** (one per configured metric) | Time-smoothed (EMA) value of the zone's CO₂, PM, or AQI. Carries `slope`, `effective_ach`, `time_to_target`, `status`, `reason`, and the live tier ladder as attributes. |
| `sensor` | **Managed `<metric>` slope** | Signed rate of change per minute. *(diagnostic, disabled by default)* |
| `sensor` | **Managed air change rate** (CO₂ only) | Concentration-normalized effective ACH (1/h). *(diagnostic)* |
| `sensor` | **Status reason** | Plain-language explanation of why Aeolus is or isn't acting. *(diagnostic)* |
| `binary_sensor` | **Mitigation active** | On while Aeolus is actively ventilating the zone. |
| `binary_sensor` | **Attention** | On when a driven metric is over its high threshold, not improving, or stale. *(diagnostic)* |
| `number` | **Target CO₂** | Live setpoint the controller drives toward. |
| `number` | **`<metric>` threshold** | Tier-1 engage level for each non-CO₂ driven metric. |
| `select` | **Mode** | `Manage`, `Monitor`, or `Off` for the zone. *(config)* |
| `switch` | **Manage `<pollutant>`** | Per-metric gate, created when a space drives more than one metric. *(config, disabled by default)* |

Per manager (the single Aeolus device):

| Platform | Entity | Purpose |
| --- | --- | --- |
| `switch` | **Management** | Master on/off for all Aeolus control. *(config)* |

Every operator-relevant decision fires an `aeolus_action` event, appears in the Logbook in plain language, and is kept in an action history that survives restarts and ships in the diagnostics download. That covers actuator on and off with the driving space and tier, override yields, veto engage and clear, and runtime caps.

<p align="center">
  <img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/device-page.png" alt="A space's device page: controls, sensors, per-metric manage switches, diagnostics, and an activity log of Aeolus decisions" width="850">
</p>
<p align="center"><em>A space's device page. The Activity log records each decision, such as "Mitigating CO₂ tier 1 → Kitchen Range Hood", and the blocking cause when Aeolus holds.</em></p>

<table>
  <tr>
    <td align="center"><img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/details-attributes.png" alt="The managed CO₂ sensor's attributes: raw value, slope, effective ACH, time to target, the tier ladder, status, and reason" width="430"></td>
    <td align="center"><img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/moreinfo-managed-co2.png" alt="The managed CO₂ sensor's more-info dialog with 24 hours of history falling toward target" width="430"></td>
  </tr>
  <tr>
    <td align="center"><em>The sensor's attributes: slope, effective ACH, the live tier ladder, status, and reason.</em></td>
    <td align="center"><em>Managed CO₂ is a normal sensor, so history, statistics, and dashboard cards work as usual.</em></td>
  </tr>
</table>

## How data updates

Aeolus doesn't poll. It subscribes to `state_changed` and `state_reported` events for every configured source sensor and recomputes the affected space's smoothed value, slope, and ACH when a reading arrives. A bounded control tick runs every 60 seconds to re-evaluate ventilation demand and refresh status even when no source has changed. Aeolus also watches actuator state, so a manual or automation-driven override is detected immediately, or after the configurable confirmation delay for cloud devices.

## Actions

- `aeolus.recalibrate` clears observed actuator effectiveness for an entry. Field: `config_entry_id`. The action is currently a registered stub; the reset ships with the auto-calibration feature.

## Use cases

- Hold a bedroom or office below a CO₂ target by cycling an exhaust fan, ERV, or window opener, with a deadband to prevent short-cycling.
- Let one ERV serve several rooms. Aeolus models the shared actuator and arbitrates demand across the spaces.
- Keep wildfire smoke out. The outdoor air-quality veto blocks ventilation while the outdoor PM sensor is above your threshold, and depressurizing mechanisms are penalized where they would cause radon or combustion-safety problems.
- Drive a range hood at 20% when PM2.5 passes 30 and everything at 100% when it passes 80, then ramp back down as the air clears.
- Re-arm a fan whose internal timer turns it off while its switch keeps reporting `on`.

## Examples

Notify when a zone needs attention:

```yaml
automation:
  - alias: "Aeolus - Primary Bedroom needs attention"
    triggers:
      - trigger: state
        entity_id: binary_sensor.primary_bedroom_attention
        to: "on"
        for: "00:10:00"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: >-
            {{ state_attr('binary_sensor.primary_bedroom_attention', 'reason') }}
```

Pause all Aeolus control while guests are over, then resume:

```yaml
automation:
  - alias: "Aeolus - pause during party scene"
    triggers:
      - trigger: state
        entity_id: input_boolean.party_mode
    actions:
      - action: switch.turn_{{ 'off' if trigger.to_state.state == 'on' else 'on' }}
        target:
          entity_id: switch.aeolus_management
```

Chart the air-change rate a ventilation run is achieving:

```yaml
type: history-graph
entities:
  - sensor.primary_bedroom_managed_air_change_rate
  - sensor.primary_bedroom_managed_co2
```

## Known limitations

- **Single manager instance.** One Aeolus config entry per Home Assistant instance. All spaces and actuators live under it as subentries.
- **Room volume is currently unused.** The field is reserved for the planned occupancy and equilibrium-CO₂ estimate. The air-change-rate readout is gap-normalized and doesn't need volume.
- **`aeolus.recalibrate` is a stub.** The action is registered but doesn't clear learned gains yet. It ships with the auto-calibration feature.
- **Pressure-induced coupling is not yet wired in.** The control loop arbitrates over direct actuators only. Induced coupling and escalation, plus occupancy and radon/combustion (CAZ) vetoes, are planned.
- **The continuous-run cap is a fixed 120 minutes.** An actuator that runs continuously for 120 minutes is force-stopped as a baseline safety cap, then re-engages on the next cycle if still demanded. The cap isn't user-configurable yet.
- **Filtration removes particulates only.** A filter-mechanism actuator is rejected for CO₂ duty by design.

## Troubleshooting

- **A fan or vent isn't turning on.** Check these in order: the **Management** switch is on, the space's **Mode** is `Manage`, and for multi-metric spaces the relevant **Manage** switch is on. The **Status reason** sensor states the exact cause.
- **Reason says the sensor is unavailable or stale.** The space's CO₂ sources are unavailable, or haven't reported a usable value within the freshness window, so Aeolus suspends control until they return. Confirm the source entity exists and is updating.
- **Reason says manual override.** Aeolus saw the actuator change to a state it didn't command, so it yields for 30 minutes. For cloud devices that briefly flap through unavailable and off (for example, LG ThinQ), set the actuator's **Manual-override confirmation delay** to about 2 minutes.
- **Reason says outdoor-air quality veto.** The configured outdoor PM sensor is above the veto threshold, so outdoor-air ventilation is blocked. You can assign a filtered intake (raise the actuator's filter efficiency) or relax the threshold.
- **A configured sensor or actuator was deleted or renamed.** Aeolus raises a repair issue under **Settings > Repairs** naming the missing entity. Reconfigure the affected space or actuator to point at the new entity.
- **The fan turns off on its own.** If the load has an internal auto-off timer while its switch keeps reporting `on`, set the actuator's **Re-arm interval** so Aeolus re-sends the on command periodically.
- **Why did it do that?** Open the Logbook, where every Aeolus decision is logged with its cause, or download diagnostics for the full action history and per-space state.

## Uninstall

Delete the Aeolus entry from **Settings > Devices & Services**. This removes its subentries, devices, and entities. For a manual install, also delete `custom_components/aeolus/` and restart. Aeolus never modifies the entities it reads or controls, so removing it only stops the automatic ventilation control.

## Development

The repository carries the full engineering spec and history:

- [REQUIREMENTS.md](REQUIREMENTS.md): the versioned requirements specification, from the building-physics model to per-requirement acceptance criteria.
- [docs/SCAFFOLD.md](docs/SCAFFOLD.md): repository structure, module responsibilities, and quality-scale traceability.
- [CHANGELOG.md](CHANGELOG.md): every release and the reasoning behind it.

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.14+
pip install -r requirements_test.txt
python -m pytest                                     # from the repo root
```

CI runs `ruff`, `mypy --strict`, and the full test suite (30 suites, 90% coverage gate) on Python 3.14, plus a syntax-floor compile and hassfest and HACS validation, on every push and pull request.

The integration declares Platinum on the [integration quality scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/). Every Bronze, Silver, Gold, and Platinum rule is either complete or formally exempt in `quality_scale.yaml`. Brand assets ship in the package at `custom_components/aeolus/brand/` and are served by the Brands Proxy.

## Credits

The time-aware EMA and slope approach comes from [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat)'s `ema.py`.

## License

[Apache-2.0](LICENSE).

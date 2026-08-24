<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/custom_components/aeolus/brand/dark_logo@2x.png">
    <img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/custom_components/aeolus/brand/logo@2x.png" alt="Aeolus" width="380">
  </picture>
</p>

<p align="center"><strong>Multi-zone, multi-pollutant ventilation control for Home Assistant — physics-grounded, safety-vetoed, and able to explain every move it makes.</strong></p>

<p align="center">
  <a href="https://github.com/jasonjhofmann/aeolus/releases"><img src="https://img.shields.io/github/v/release/jasonjhofmann/aeolus" alt="Release"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-custom-41BDF5.svg" alt="HACS"></a>
  <a href="https://github.com/jasonjhofmann/aeolus/actions/workflows/ci.yml"><img src="https://github.com/jasonjhofmann/aeolus/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://developers.home-assistant.io/docs/core/integration-quality-scale/"><img src="https://img.shields.io/badge/quality%20scale-platinum-e5e4e2.svg" alt="Quality scale: Platinum"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2026.7%2B-41BDF5.svg" alt="Home Assistant 2026.7+">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/jasonjhofmann/aeolus" alt="License"></a>
</p>

---

> In Greek myth, **Aeolus** is the keeper of the winds — he holds many separate winds and releases each on demand. That is what this integration does for your house: it orchestrates ERVs, exhaust fans, range hoods, supply and transfer fans, purifiers, and window openers across rooms that *share air*, releasing the right one at the right time — and telling you exactly why.

<p align="center">
  <img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/dashboard-managed-co2.png" alt="A managed Space's CO₂ falling from 964 to 655 ppm, with slope, air-change rate, target, and the active control ladder" width="850">
</p>
<p align="center"><em>A managed bedroom converging on its target overnight — smoothed CO₂, slope, gap-normalized air changes, and the control ladder that did it. (Dashboard cards built from Aeolus entities.)</em></p>

## Your thermostat has a brain. Your ventilation deserves one too.

Home Assistant will happily run *"if CO₂ > 1000, turn on the fan."* Aeolus exists because real houses are harder than that:

- **One actuator affects many rooms, and rooms share air.** An ERV serves four bedrooms; a bath exhaust depressurizes the whole envelope. Aeolus models these couplings explicitly and arbitrates demand across zones instead of fighting itself.
- **"Ventilate more" is sometimes the wrong answer.** When it's smoky outside, when the intake filter can't cope, or when a sensor has gone stale, blindly running fans trades one hazard for another. Aeolus vetoes those moves.
- **A recirculating purifier does nothing for CO₂** — filtration removes particulates, never CO₂. Aeolus enforces this at config time, not just in the docs.
- **Raw ppm/min is not a performance metric.** CO₂ decays exponentially toward the outdoor floor, so the same fan looks "fast" at 2000 ppm and "slow" at 800. Aeolus reports the concentration-normalized **air-change rate (ACH)** — a number you can actually compare across rooms, fans, and days.

### What you get

- 🌀 **Multi-zone, shared-air control** — group sensors and actuators into *Spaces*; one actuator can serve many spaces, with per-space hysteresis control and cross-space arbitration.
- 🪜 **Graduated multi-pollutant response** — drive a space by **CO₂, PM1, PM2.5, PM10, AQI, or a generic level**, each with its own tier ladder: hood at 20 % when PM2.5 > 30, everything at 100 % when it clears 80, ramping back down with engage/release hysteresis so nothing short-cycles.
- 📉 **Physics-grounded telemetry** — time-aware EMA smoothing, a signed **slope** (per minute), **effective ACH**, and time-to-target for every space.
- 🛡️ **Safety vetoes** — a filter-aware outdoor-air-quality veto, stale-sensor safe state, per-actuator runtime caps, and the purifier-can't-do-CO₂ capability gate.
- ✋ **Plays well with humans** — a manual override yields control for 30 minutes, with a configurable confirmation delay so flappy cloud devices (looking at you, LG ThinQ) don't false-trigger it.
- 🧾 **Explains itself** — a plain-language **Status reason** sensor, every decision humanized in the **Logbook**, and a durable action history in diagnostics that survives restarts.
- 🖱️ **100 % UI-configured** — config flow with subentries; no YAML, live add/remove of spaces and actuators without a reload.
- ⚡ **Push, not poll** — event-driven recompute the moment a reading arrives, zero external dependencies, `mypy --strict` clean, **Platinum** on the Integration Quality Scale.

**On the roadmap:** humidity and moisture management (shower-steam exhaust, over-dry veto), pressure-induced coupling and escalation, radon/combustion-safety budgets, and auto-calibration of actuator effectiveness. The full design lives in [REQUIREMENTS.md](REQUIREMENTS.md).

## Installation

Requires Home Assistant **2026.7 or newer** (config subentries; `UnitOfDensity`/`UnitOfRatio`). Installations on older HA can use [v0.6.1](https://github.com/jasonjhofmann/aeolus/releases/tag/v0.6.1).

**HACS (recommended):**

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jasonjhofmann&repository=aeolus&category=integration)

Or manually: HACS → custom repositories → add `https://github.com/jasonjhofmann/aeolus` (type: Integration) → install **Aeolus** → restart Home Assistant.

**Manual:** copy `custom_components/aeolus/` into your HA `config/custom_components/` and restart.

Then add the integration:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=aeolus)

(**Settings → Devices & Services → Add Integration → Aeolus**.)

## Configuration

All configuration is in the UI. The single **Aeolus** entry holds two kinds of subentries:

- **Space** — a managed zone. Pick its CO₂ sensor(s) and aggregation, a target and high threshold (ppm), optional volume, and an optional outdoor air-quality (PM) sensor + veto threshold. With graduated ladders enabled (an option-flow toggle), a Space can also be driven by PM/AQI/generic metrics with a full tier ladder each.
- **Actuator** — a ventilation device that reduces a pollutant (fan / switch / input_boolean / cover, or a same-domain group of them). Set its air *mechanism* (balanced ERV / supply / exhaust / transfer / window / filter), the Spaces it directly serves, its intake filter efficiency (0–1), an optional per-pathway intake AQ sensor, a fan on-speed, a re-arm interval, and a manual-override confirmation delay.

<table>
  <tr>
    <td align="center"><img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/flow-add-space.png" alt="The Add-a-space dialog: name, CO₂ sensors, aggregation, and target" width="430"></td>
    <td align="center"><img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/flow-add-actuator.png" alt="The Add-an-actuator dialog: entity, air mechanism, served spaces, filter efficiency" width="430"></td>
  </tr>
  <tr>
    <td align="center"><em>Add a Space: sensors, aggregation, targets.</em></td>
    <td align="center"><em>Add an Actuator: mechanism, served spaces, filtration.</em></td>
  </tr>
</table>

<p align="center">
  <img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/flow-options.png" alt="The options dialog explaining control precedence, with the graduated-ladders toggle" width="560">
</p>
<p align="center"><em>The options flow spells out the control precedence and gates the advanced tier-ladder wizard.</em></p>

Adding or removing a Space or Actuator takes effect live, without reloading the entry; edits to an existing one are re-parsed and applied immediately. No restarts.

## Supported devices

Aeolus is a **calculated** integration: it talks to no hardware directly and needs no cloud. It composes entities that already exist in your Home Assistant instance, so it works with **any** device exposed as a standard HA entity.

**Sources it reads (per Space):**

- **CO₂ sensors** — any `sensor` with `device_class: carbon_dioxide` (ppm). Tested with Aranet4, AirGradient, Airthings, SCD4x-based ESPHome sensors.
- **Particulate / AQI sensors (optional, graduated ladders)** — any numeric `sensor` reporting PM1 / PM2.5 / PM10 (μg/m³), an AQI, or a generic value. Tested with AirVisual/IQAir, PurpleAir, AirGradient, Aranet Radon+.
- **Outdoor air-quality sensor (optional veto)** — any PM `sensor` measuring the air a ventilation pathway would pull in.

**Actuators it controls (per Actuator):**

- `fan` (on/off and variable `percentage`), `switch`, `input_boolean`, and `cover` (windows/openers). One Actuator can drive a group of same-domain entities. Mechanisms: balanced (ERV/HRV), supply, exhaust, transfer, window, and filter (recirculating purifier — PM only, never CO₂).

Aeolus never modifies or reconfigures the entities it reads or controls; it only reads their state and calls their standard `turn_on` / `turn_off` / `set_percentage` / `open_cover` / `close_cover` services.

## Entities

Per **Space** (a device named after the zone):

| Platform | Entity | Purpose |
| --- | --- | --- |
| `sensor` | **Managed `<metric>`** (one per configured metric) | Time-smoothed (EMA) value of the zone's CO₂/PM/AQI. Carries `slope`, `effective_ach`, `time_to_target`, `status`, `reason`, and the live tier ladder as attributes. |
| `sensor` | **Managed `<metric>` slope** | Signed rate of change (per minute). *(diagnostic, disabled by default)* |
| `sensor` | **Managed air change rate** (CO₂ only) | Concentration-normalized effective ACH (1/h). *(diagnostic)* |
| `sensor` | **Status reason** | Plain-language explanation of why Aeolus is (or isn't) acting. *(diagnostic)* |
| `binary_sensor` | **Mitigation active** | On while Aeolus is actively ventilating the zone. |
| `binary_sensor` | **Attention** | On when a driven metric is over-high, not improving, or stale. *(diagnostic)* |
| `number` | **Target CO₂** | Live setpoint the controller drives toward. |
| `number` | **`<metric>` threshold** | Tier-1 engage level for each non-CO₂ driven metric. |
| `select` | **Mode** | `Manage` / `Monitor` / `Off` for the zone. *(config)* |
| `switch` | **Manage `<pollutant>`** | Per-metric gate (only when a Space drives >1 metric). *(config, disabled by default)* |

Per **manager** (the single Aeolus device):

| Platform | Entity | Purpose |
| --- | --- | --- |
| `switch` | **Management** | Master on/off for all Aeolus control. *(config)* |

Every operator-relevant decision — actuator on/off with the driving space and tier, override yields, veto engage/clear, runtime caps — also fires an `aeolus_action` event, appears humanized in the **Logbook**, and is retained in a restart-surviving action history included in the diagnostics download.

<p align="center">
  <img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/device-page.png" alt="A Space's device page: controls, sensors, per-metric manage switches, diagnostics, and an activity log of Aeolus decisions" width="850">
</p>
<p align="center"><em>A Space's device page. The Activity log reads like a flight recorder: "Mitigating CO₂ tier 1 → Kitchen Range Hood", "CO₂ tier 1 demanded — no eligible actuator".</em></p>

<table>
  <tr>
    <td align="center"><img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/details-attributes.png" alt="The managed CO₂ sensor's attributes: raw value, slope, effective ACH, time to target, the tier ladder, status, and reason" width="430"></td>
    <td align="center"><img src="https://raw.githubusercontent.com/jasonjhofmann/aeolus/main/docs/images/moreinfo-managed-co2.png" alt="The managed CO₂ sensor's more-info dialog with 24 hours of history falling toward target" width="430"></td>
  </tr>
  <tr>
    <td align="center"><em>Every answer as attributes: slope, effective ACH, the live tier ladder, and the reason.</em></td>
    <td align="center"><em>Managed CO₂ is a normal sensor — history, statistics, and dashboards all just work.</em></td>
  </tr>
</table>

## How data updates

Aeolus is **push / event-driven — it does not poll**. It subscribes to `state_changed` and `state_reported` events for every configured source sensor and recomputes the affected Space's smoothed value, slope, and ACH the moment a reading arrives. A bounded **control tick runs every 60 s** to re-evaluate ventilation demand and refresh status/explainability even when no source has changed. Actuator state is likewise watched via `state_changed` so a manual/automation override is detected and yielded to immediately (or after a configurable confirmation delay for flappy cloud devices).

## Actions

- **`aeolus.recalibrate`** — clears observed/learned actuator effectiveness for an entry. Field: `config_entry_id`. *(Currently a registered stub — the reset lands with the auto-calibration feature.)*

## Use cases

- **Single-room CO₂ control** — hold a bedroom or office below a target by cycling an exhaust fan, ERV, or window opener, with a deadband to prevent short-cycling.
- **Multi-zone shared air** — one ERV serving several rooms; Aeolus models that one actuator affects many spaces and arbitrates demand across them.
- **Don't trade one hazard for another** — an outdoor-AQ veto blocks pulling in dirty outdoor air; depressurizing mechanisms are penalized where they'd cause radon/combustion-safety problems; a recirculating purifier can never be selected for CO₂.
- **Graduated particulate response** — drive a hood at 20 % when PM2.5 > 30 and everything at 100 % when PM2.5 > 80, ramping back down automatically as it clears.
- **Self-auto-off loads** — re-arm a fan whose internal timer switches it off while its switch keeps reporting `on`.

## Examples

Notify when a zone needs attention:

```yaml
automation:
  - alias: "Aeolus — Primary Bedroom needs attention"
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
  - alias: "Aeolus — pause during party scene"
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

- **Single manager instance.** One Aeolus config entry per Home Assistant; all Spaces and Actuators live under it as subentries.
- **`Room volume (ft³)` is currently unused.** It is reserved for the planned occupancy/generation (equilibrium-CO₂) estimate. The air-change-rate readout is gap-normalized and does not need volume.
- **`aeolus.recalibrate` is a stub.** Observed/learned-gain reset lands with the auto-calibration feature; the action is registered but does not yet clear gains.
- **Induced/pressure edges + escalation are not yet wired in.** The control loop arbitrates over `direct` actuators only; pressure-mediated (induced) coupling and direct→induced escalation, plus occupancy and radon/combustion (CAZ) vetoes, are planned.
- **Continuous-run cap is a fixed 120 minutes.** An actuator running continuously for 120 minutes is force-stopped as a baseline safety cap (it then re-engages on the next cycle if still demanded). This cap is not yet user-configurable.
- **Filtration removes particulates, never CO₂.** A `filter`-mechanism actuator is rejected for CO₂ duty by design — see *Your thermostat has a brain* above.

## Troubleshooting

- **A fan/vent isn't turning on.** Check, in precedence order: the **Management** switch (master on/off) is on → the Space's **Mode** is `Manage` → for multi-metric Spaces, the relevant **Manage `<pollutant>`** switch is on. The **Status reason** sensor states the exact cause.
- **Reason reads *"Sensor unavailable — mitigation suspended"* or *"Sensor stale — mitigation suspended"*.** The Space's CO₂ source(s) are unavailable, or haven't reported a usable value within the freshness window; Aeolus suspends control until they return. Confirm the source entity exists and is updating.
- **Reason reads *"manual override — yielding N min"*.** Aeolus saw the actuator change to a state it didn't command (a person or another automation), so it yields for 30 minutes. For cloud devices (e.g. LG ThinQ) that briefly flap `unavailable → off → on`, set the actuator's **Manual-override confirmation delay** to ~2 minutes.
- **Reason reads *"outdoor-air quality veto"*.** The configured outdoor PM sensor is above the veto threshold, so outdoor-air ventilation is blocked. Lower-risk options: assign a filtered intake (raise the actuator's filter efficiency) or relax the threshold.
- **A configured sensor/actuator was deleted or renamed.** Aeolus raises a **repair issue** ("Settings → Repairs") naming the missing entity; reconfigure the affected Space/Actuator to point at the new entity.
- **The fan turns off on its own.** If the load has an internal auto-off timer while its switch keeps reporting `on`, set the actuator's **Re-arm interval** so Aeolus re-sends the ON command periodically.
- **Why did it do that?** Open the **Logbook** — every Aeolus decision is logged with its cause — or download diagnostics for the full action history and per-space state.

## Removal

Delete the **Aeolus** integration entry from Settings → Devices & Services (this removes its subentries, devices, and entities). For a manual install, also delete `custom_components/aeolus/` and restart. Aeolus never modifies the entities it reads or controls, so removing it simply stops the automatic ventilation control.

## Development

The repo carries the full engineering spec and history:

- **[REQUIREMENTS.md](REQUIREMENTS.md)** — the versioned requirements specification, from building-physics backbone to per-requirement acceptance criteria.
- **[docs/SCAFFOLD.md](docs/SCAFFOLD.md)** — repository structure, module responsibilities, and the Quality-Scale traceability.
- **[CHANGELOG.md](CHANGELOG.md)** — every release, with the reasoning.

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.14+
pip install -r requirements_test.txt
python -m pytest                                     # from the repo root
```

CI runs `ruff`, `mypy --strict`, and the full test suite (30 suites, 90 % coverage gate) on Python 3.14, plus a syntax-floor compile and hassfest + HACS validation, on every push and PR.

**Quality scale: Platinum** — every Bronze/Silver/Gold/Platinum rule is complete or formally exempt (`quality_scale.yaml`): fully async, push-driven, dependency-free local compute, strict typing. Brand assets ship in-package at `custom_components/aeolus/brand/` and are served by HA's Brands Proxy.

## Credits

The smoothing/slope approach is grounded in [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat)'s time-aware EMA — Aeolus aims to do for air what it does for heat.

## License

[Apache-2.0](LICENSE).

# Aeolus

**Adaptive, multi-zone CO₂ & ventilation manager for Home Assistant.**

> In Greek myth, **Aeolus** is the keeper of the winds — he holds many separate winds and releases each on demand. That is exactly what this integration does: it orchestrates multiple, cross-coupled air streams (ERV/HRV, exhausts, supply/transfer fans, windows) across rooms that *share air*, releasing the right one at the right time to manage CO₂ — while reporting the rate of change (slope) and the underlying air-change rate (ACH), in the spirit of [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat).

---

## Status: ✅ Platinum quality scale

The spec is settled and the v0.1 MVP is implemented end-to-end: data model +
verified config-subentry flows, the push engine (no coordinator), time-aware
EMA + slope + gap-normalized ACH (unit-tested), per-space **hysteresis control**
with coverage arbitration over `direct` actuators, **safety vetoes** (stale
safe-state, filter-aware outdoor-AQ veto, per-actuator max-runtime), manual-
override yield, and all five entity platforms (sensor / binary_sensor / number /
select / switch). It loads on current Home Assistant with the integration test
harness and the **full test suite passes** (EMA math, config + subentry flows,
end-to-end setup, the control loop actuating a real entity, live dynamic add/
remove of Spaces and Actuators, and repair-issue handling). Deferred to v1.1:
induced/pressure edges + escalation, variable drive, full CAZ + radon veto,
auto-calibration.

### Testing

```bash
python3 -m venv ~/venvs/aeolus
~/venvs/aeolus/bin/pip install pytest-homeassistant-custom-component
~/venvs/aeolus/bin/python -m pytest        # from the repo root
```

**Quality scale: Platinum** — every Bronze + Silver + Gold + Platinum rule is complete: `mypy --strict` clean, fully async/non-blocking, and dependency-free local compute (`async-dependency`/`inject-websession` are N/A — no external library, no HTTP). The `brands` rule is satisfied by the in-package assets at `custom_components/aeolus/brand/` (icon/logo + dark variants), served locally via HA's Brands Proxy — `home-assistant/brands` no longer accepts custom-integration submissions, so the local folder is the supported path. **Next:** v1.1 polish (per-actuator influence-row config UI, variable-speed drive).

- **[REQUIREMENTS.md](REQUIREMENTS.md)** — the full, versioned requirements specification (v3.1; §8 multi-pollutant built, §9 humidity planned).
- **[docs/SCAFFOLD.md](docs/SCAFFOLD.md)** — repository structure, module responsibilities, build status, and the Quality-Scale roadmap.
- **[CHANGELOG.md](CHANGELOG.md)** — spec history.
- **`custom_components/aeolus/`** — the integration; **`tests/`** — pure-math unit tests.

## What it will do (one paragraph)

Aeolus lets you select CO₂ sensors and ventilation actuators (fans, switches, ERV, windows) entirely through the UI, group them into **spaces**, and then keeps each space under a CO₂ target by activating actuators — explicitly modeling that **one actuator affects many rooms** and that **rooms share air** (direct, diffusive, and pressure-*induced* couplings). It reports a smoothed CO₂ value, a signed **slope** (ppm/min), and a concentration-normalized **effective air-change rate (ACH)** per space, and it refuses to trade one hazard for another (it won't ventilate into bad outdoor air, won't depressurize into a radon or combustion-safety problem, and won't let you pick a recirculating air purifier — which does nothing for CO₂).

## Design targets

- **Quality scale:** Home Assistant Integration **Quality Scale — Platinum**.
- **Distribution:** HACS (custom integration).

## Why this isn't "just a CO₂ automation"

Two correctness points drive the whole design (see REQUIREMENTS §1, §0.3):

1. **CO₂ is removed only by air exchange**, never by filtration — HEPA/carbon/PCO/ionizers do nothing for CO₂. Aeolus enforces this at config time.
2. **CO₂ decay is exponential toward an outdoor floor (~420 ppm)**, so the comparable effectiveness metric is the **air-change rate (ACH)**, not raw ppm/min (which scales with how high CO₂ currently is). Aeolus reports both.

## Installation

**HACS (recommended):** add `https://github.com/jasonjhofmann/aeolus` as a *custom repository* (type: Integration), install **Aeolus**, then restart Home Assistant. **Manual:** copy `custom_components/aeolus/` into your HA `config/custom_components/` and restart. Requires Home Assistant **2025.4 or newer** (config subentries).

Then **Settings → Devices & Services → Add Integration → Aeolus** to create the manager.

## Configuration

All configuration is in the UI. The single **Aeolus** entry holds two kinds of subentries:

- **Space** — a managed zone. Pick its CO₂ sensor(s) and aggregation, a target and high threshold (ppm), optional volume, and an optional outdoor air-quality (PM) sensor + veto threshold.
- **Actuator** — a ventilation device that reduces CO₂ (fan / switch / input_boolean / cover). Set its air *mechanism* (balanced ERV / supply / exhaust / transfer / window), the Spaces it directly serves, its intake filter efficiency (0–1), and an optional per-pathway intake AQ sensor.

Per Space you get a CO₂ sensor (with slope + effective-ACH + time-to-target attributes), a mitigation/attention binary sensor, a target number, and a mode select (manage / monitor / off). A master **Management** switch pauses all control.

## Actions

- **`aeolus.recalibrate`** — clears observed/learned actuator effectiveness for an entry. Field: `config_entry_id`.

## Supported devices

Aeolus is a **calculated** integration: it does not talk to any hardware directly. Instead it composes entities that already exist in your Home Assistant instance, so it works with **any** device whose data is exposed through a standard HA entity.

**Sources it reads (per Space):**

- **CO₂ sensors** — any `sensor` with `device_class: carbon_dioxide` (ppm). Tested with Aranet4, AirGradient, Airthings, SCD4x-based ESPHome sensors.
- **Particulate / AQI sensors (optional, graduated ladders)** — any numeric `sensor` reporting PM1 / PM2.5 / PM10 (µg/m³), an AQI, or a generic value. Tested with AirVisual/IQAir, PurpleAir, AirGradient, Aranet Radon+.
- **Outdoor air-quality sensor (optional veto)** — any PM `sensor` measuring the air a ventilation pathway would pull in.

**Actuators it controls (per Actuator):**

- `fan` (on/off and variable `percentage`), `switch`, `input_boolean`, and `cover` (windows/openers). One Actuator can drive a group of same-domain entities. Mechanisms: balanced (ERV/HRV), supply, exhaust, transfer, window, and filter (recirculating purifier — PM only, never CO₂).

Aeolus never modifies or reconfigures the entities it reads or controls; it only reads their state and calls their standard `turn_on` / `turn_off` / `set_percentage` / `open_cover` / `close_cover` services.

## Supported functions

Per **Space** (a device named after the zone), Aeolus creates:

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

## How data updates

Aeolus is **push / event-driven — it does not poll**. It subscribes to `state_changed` and `state_reported` events for every configured source sensor and recomputes the affected Space's smoothed value, slope, and ACH the moment a reading arrives. A bounded **control tick runs every 60 s** to re-evaluate ventilation demand and refresh status/explainability even when no source has changed. Actuator state is likewise watched via `state_changed` so a manual/automation override is detected and yielded to immediately (or after a configurable confirmation delay for flappy cloud devices).

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
- **Induced/pressure edges + escalation are deferred to v1.1.** The current control loop arbitrates over `direct` actuators only; pressure-mediated (induced) coupling and direct→induced escalation, plus occupancy and radon/combustion (CAZ) vetoes, are planned.
- **Continuous-run cap is a fixed 120 minutes.** An actuator running continuously for 120 minutes is force-stopped as a baseline safety cap (it then re-engages on the next cycle if still demanded). This cap is not yet user-configurable.
- **Filtration removes particulates, never CO₂.** A `filter`-mechanism actuator is rejected for CO₂ duty by design.
- **CO₂ is removed only by air exchange.** Aeolus reports ACH precisely because filtration does nothing for CO₂ — see *Why this isn't "just a CO₂ automation"* above.

## Troubleshooting

- **A fan/vent isn't turning on.** Check, in precedence order: the **Management** switch (master on/off) is on → the Space's **Mode** is `Manage` → for multi-metric Spaces, the relevant **Manage `<pollutant>`** switch is on. The **Status reason** sensor states the exact cause.
- **Reason reads *"Sensor unavailable — mitigation suspended"* or *"Sensor stale — mitigation suspended"*.** The Space's CO₂ source(s) are unavailable, or haven't reported a usable value within the freshness window; Aeolus suspends control until they return. Confirm the source entity exists and is updating.
- **Reason reads *"manual override — yielding N min"*.** Aeolus saw the actuator change to a state it didn't command (a person or another automation), so it yields for 30 minutes. For cloud devices (e.g. LG ThinQ) that briefly flap `unavailable → off → on`, set the actuator's **Manual-override confirmation delay** to ~2 minutes.
- **Reason reads *"outdoor-air quality veto"*.** The configured outdoor PM sensor is above the veto threshold, so outdoor-air ventilation is blocked. Lower-risk options: assign a filtered intake (raise the actuator's filter efficiency) or relax the threshold.
- **A configured sensor/actuator was deleted or renamed.** Aeolus raises a **repair issue** ("Settings → Repairs") naming the missing entity; reconfigure the affected Space/Actuator to point at the new entity.
- **The fan turns off on its own.** If the load has an internal auto-off timer while its switch keeps reporting `on`, set the actuator's **Re-arm interval** so Aeolus re-sends the ON command periodically.

## Removal

Delete the **Aeolus** integration entry from Settings → Devices & Services (this removes its subentries, devices, and entities). For a manual install, also delete `custom_components/aeolus/` and restart. Aeolus never modifies the entities it reads or controls, so removing it simply stops the automatic ventilation control.

## License

[Apache-2.0](LICENSE).

# Aeolus

**Adaptive, multi-zone CO₂ & ventilation manager for Home Assistant.**

> In Greek myth, **Aeolus** is the keeper of the winds — he holds many separate winds and releases each on demand. That is exactly what this integration does: it orchestrates multiple, cross-coupled air streams (ERV/HRV, exhausts, supply/transfer fans, windows) across rooms that *share air*, releasing the right one at the right time to manage CO₂ — while reporting the rate of change (slope) and the underlying air-change rate (ACH), in the spirit of [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat).

---

## Status: 🚧 v0.1 — control loop closed + loads/tests green on HA 2026.2.3

The spec is settled and the v0.1 MVP is implemented end-to-end: data model +
verified config-subentry flows, the push engine (no coordinator), time-aware
EMA + slope + gap-normalized ACH (unit-tested), per-space **hysteresis control**
with coverage arbitration over `direct` actuators, **safety vetoes** (stale
safe-state, filter-aware outdoor-AQ veto, per-actuator max-runtime), manual-
override yield, and all five entity platforms (sensor / binary_sensor / number /
select / switch). It loads in HA 2026.2.3 with the integration test harness and
**13 tests pass** (EMA math, config flow, end-to-end setup, and the control loop
actuating a real entity). Deferred to v1.1: induced/pressure edges + escalation,
variable drive, full CAZ + radon veto, auto-calibration.

### Testing

```bash
python3 -m venv ~/venvs/aeolus
~/venvs/aeolus/bin/pip install pytest-homeassistant-custom-component
~/venvs/aeolus/bin/python -m pytest        # from the repo root
```

**Next: expand to 100% config-flow coverage (Bronze) → >95% overall (Silver); brands PR + docs.**

- **[REQUIREMENTS.md](REQUIREMENTS.md)** — the full, versioned requirements specification (v2.5).
- **[docs/SCAFFOLD.md](docs/SCAFFOLD.md)** — repository structure, module responsibilities, build status, and the Quality-Scale roadmap.
- **[CHANGELOG.md](CHANGELOG.md)** — spec history.
- **`custom_components/aeolus/`** — the integration; **`tests/`** — pure-math unit tests.

## What it will do (one paragraph)

Aeolus lets you select CO₂ sensors and ventilation actuators (fans, switches, ERV, windows) entirely through the UI, group them into **spaces**, and then keeps each space under a CO₂ target by activating actuators — explicitly modeling that **one actuator affects many rooms** and that **rooms share air** (direct, diffusive, and pressure-*induced* couplings). It reports a smoothed CO₂ value, a signed **slope** (ppm/min), and a concentration-normalized **effective air-change rate (ACH)** per space, and it refuses to trade one hazard for another (it won't ventilate into bad outdoor air, won't depressurize into a radon or combustion-safety problem, and won't let you pick a recirculating air purifier — which does nothing for CO₂).

## Design targets

- **Build target:** Home Assistant Integration **Quality Scale — Silver**.
- **Architected for:** **Platinum** (strict typing + provably non-blocking, dependency-free local compute).
- **Distribution:** HACS (custom integration).

## Why this isn't "just a CO₂ automation"

Two correctness points drive the whole design (see REQUIREMENTS §1, §0.3):

1. **CO₂ is removed only by air exchange**, never by filtration — HEPA/carbon/PCO/ionizers do nothing for CO₂. Aeolus enforces this at config time.
2. **CO₂ decay is exponential toward an outdoor floor (~420 ppm)**, so the comparable effectiveness metric is the **air-change rate (ACH)**, not raw ppm/min (which scales with how high CO₂ currently is). Aeolus reports both.

## License

[Apache-2.0](LICENSE).

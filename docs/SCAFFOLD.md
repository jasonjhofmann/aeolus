# Aeolus — Repository Scaffold Plan

> Repository structure + module responsibilities. The v0.1 core scaffold is now built; this maps [REQUIREMENTS](../REQUIREMENTS.md) onto the layout and the Quality-Scale rules.

## v0.1 scaffold status (built 2026-06-05)

**Built (real) — the v0.1 control loop is closed:** `manifest.json`, `hacs.json`, `const.py`, `models.py` (Space/Actuator/Influence + typed `AeolusConfigEntry`), `ema.py` (`TimeAwareEMA` + `SlopeTracker` — **unit-tested**), `estimator.py` (gap-normalized `effective_ach`, exponential time-to-target, reachability), `engine.py` (push engine: source + actuator subscriptions, per-space EMA/slope, actuator command with min on/off, **manual-override detection**, control tick), `controller.py` (per-space **hysteresis** + coverage arbitration over `direct` actuators, safety-gated), `safety.py` (stale safe-state, filter-aware per-pathway outdoor-AQ veto, per-actuator max-runtime), `__init__.py` (lifecycle + subentry→model parsing incl. served-spaces→influences), `config_flow.py` (parent + Space/Actuator subentry flows, actuator served-spaces multi-select), `entity.py`, and all five platforms: `sensor.py` (Space CO₂ + slope/ACH/ETA attrs), `binary_sensor.py` (mitigation-active + attention), `number.py` (target, RestoreNumber), `select.py` (mode), `switch.py` (master enable). Plus `services.py`, `strings.json` (+ entity translations), `services.yaml`, `quality_scale.yaml`, `py.typed`, `pyproject.toml`, `tests/test_ema.py`. **`PLATFORMS` = sensor + binary_sensor + number + select + switch.**

**Quality scale (2026-06-17): Gold ✅** — all Bronze + Silver + Gold rules complete; Platinum rules also met (`mypy --strict` clean; `async-dependency`/`inject-websession` N/A). Gold work: 7 docs sections, `icons.json` (icon-translations), translation-key entity names, diagnostic/disabled-by-default categories, exception-translations, repair-issues for missing configured entities, and live `dynamic-devices`/`stale-devices` subentry add/remove. `brands` satisfied by the in-package `brand/` folder (NOT a home-assistant/brands PR — that repo auto-closes custom integrations). `test-before-configure`/`-setup` exempt (calculated helper; absent sources handled per-entity).

**Tests (`~/venvs/aeolus`, current HA):** **102 passing** — EMA/slope, estimator, config + subentry flows (add + reconfigure), end-to-end setup, control loop (high→on / low→off / paused), outdoor-AQ veto (block / clean / filtered-tolerates), manual-override yield, max-runtime force-off, safety vetoes, entities, services, unload, icon/translation consistency, repair-issues, and live dynamic add/remove of Spaces + Actuators. (`equilibrium_co2` remains deferred to v1.1 — needs an occupancy/generation estimate, FR-S5.)

**Deferred to v1.1 (not stubs — out of v0.1 scope):** induced/diffusive edges + direct→induced escalation (FR-L3/X3), PI control, variable-speed drive (FR-L4), cost-weighted arbitration, occupancy feedforward + `equilibrium_co2` (FR-S5), full CAZ net-exhaust budget + radon veto (FR-G2), auto-calibration (FR-X5), per-actuator influence-row UI (v0.1 uses a served-spaces multi-select → all `direct`, gain `medium`).

**Decisions reflected:** min HA **2025.4** (config subentries); **no DataUpdateCoordinator** → `engine.py` (not `coordinator.py`); `models.py` (not `model.py`); `services.py` for the action-setup rule.

---

## Target directory tree

```
aeolus/
├── README.md
├── REQUIREMENTS.md
├── CHANGELOG.md
├── LICENSE                         # Apache-2.0
├── hacs.json                       # HACS manifest (name, HA min version, render_readme)
├── pyproject.toml                  # ruff + mypy(strict) + pytest config; py.typed
├── .github/
│   └── workflows/
│       ├── validate.yml            # hassfest + HACS validation
│       └── test.yml                # ruff, mypy --strict, pytest --cov (gate >95%)
├── custom_components/
│   └── aeolus/
│       ├── __init__.py             # async_setup (action-setup), async_setup_entry,
│       │                           #   async_unload_entry (config-entry-unloading),
│       │                           #   runtime_data wiring, subentry handlers
│       ├── manifest.json           # domain, iot_class=calculated, quality_scale, codeowners
│       ├── const.py                # DOMAIN, defaults (HALFLIFE_SEC=300, MAX_ALPHA=0.5,
│       │                           #   C_OUT_DEFAULT=420), enums (Mechanism, InfluenceType, Status)
│       ├── config_flow.py          # config + options + reconfigure flow; Space & Actuator
│       │                           #   SUBENTRY flows; test-before-configure; FR-C8 purifier guard
│       ├── coordinator.py          # the Engine: source-entity subscriptions, tick loop,
│       │                           #   orchestrates estimator + controller + safety
│       ├── model.py                # dataclasses: Space, Actuator, Influence, AirShareLink,
│       │                           #   InfluenceGraph (the software image of M(u))
│       ├── ema.py                  # time-aware EMA (VT scheme) — pure, unit-tested
│       ├── estimator.py            # slope, effective_ach (gap-normalized), equilibrium,
│       │                           #   exponential time-to-target, occupancy/disturbance est.,
│       │                           #   per-(actuator,space) gain identification (decay system-ID)
│       ├── controller.py           # PI + hysteresis per space; multi-space arbitration
│       │                           #   (coverage×gain − cost); induced-edge conditional logic;
│       │                           #   strategy escalation; min on/off + settle windows
│       ├── safety.py               # CAZ depressurization caps, radon veto, outdoor-AQ veto,
│       │                           #   stale-sensor safe-state, manual-override yield
│       ├── entity.py               # AeolusEntity base (has-entity-name, device-per-space)
│       ├── sensor.py               # Space CO₂ + rich attributes; diagnostics sensors
│       ├── binary_sensor.py        # mitigation_active, attention
│       ├── number.py               # target ppm
│       ├── select.py               # space mode (manage/monitor/off)
│       ├── switch.py               # master enable
│       ├── diagnostics.py          # redacted dump (graph, gains, EMA/slope, active vetoes)
│       ├── repairs.py              # ir issues (HEPA-selected, sensor-stale, unreachable, AQ/radon veto)
│       ├── services.yaml           # set_target, set_mode, force_strategy, recalibrate
│       ├── strings.json            # config/options/subentry text, entity names, exceptions
│       ├── icons.json              # icon-translations
│       ├── quality_scale.yaml      # rule-by-rule status (done/todo/exempt)
│       ├── py.typed                # PEP-561 marker (Platinum strict-typing)
│       ├── brand/                  # icon/logo (light+dark) — served by HA's Brands Proxy
│       │                           #   (custom_components/<domain>/brand/, 2026.3+); ships via HACS
│       └── translations/
│           └── en.json
└── tests/
    ├── conftest.py
    ├── test_config_flow.py         # Bronze: config-flow-test-coverage
    ├── test_ema.py                 # exactness vs VT formula; irregular Δt; max_alpha cap
    ├── test_estimator.py           # slope sign, gap-normalized ACH, exponential ETA, reachability
    ├── test_controller.py          # hysteresis, arbitration, induced gating, escalation, anti-hunt
    ├── test_safety.py              # each veto + stale safe-state + override yield
    └── test_scenario_canonical.py  # §4 ERV + bath-exhaust acceptance scenario end-to-end
```

## Module → requirement → quality-rule traceability

| Module | Implements | Key Quality-Scale rules |
|---|---|---|
| `config_flow.py` | FR-C1..C9 | config-flow, config-flow-test-coverage, test-before-configure, unique-config-entry, reconfiguration-flow |
| `__init__.py` | FR-A2, lifecycle | action-setup, runtime-data, config-entry-unloading, test-before-setup |
| `ema.py` | FR-M2 | (pure; underpins appropriate-polling cadence) |
| `estimator.py` | FR-S1..S5, R-PHYS-1..3 | data-update docs, diagnostics |
| `controller.py` | FR-L1..L7, FR-X1..X6 | parallel-updates (declared), appropriate-polling |
| `safety.py` | FR-G1..G6 | entity-unavailable, log-when-unavailable, repair-issues |
| `model.py` | §2, §1.3 graph | strict-typing (Platinum) |
| `sensor/binary_sensor/number/select/switch` | FR-E1..E4 | entity-unique-id, has-entity-name, entity-category, entity-device-class, entity-disabled-by-default, entity-translations, icon-translations |
| `diagnostics.py` / `repairs.py` | observability | diagnostics, repair-issues (Gold) |
| `tests/` | all | test-coverage >95% (Silver), config-flow-test-coverage (Bronze) |

## Roadmap

- **v0.1 (MVP — RESOLVED, §7):** spaces + sensors (per-member freshness) + `ema.py` + slope + `effective_ach` + on/off **direct** actuators + threshold/hysteresis control + outdoor-AQ veto + stale-sensor safety + **per-actuator max-runtime**. Lands **Bronze**, most of **Silver**.
- **v1.0 (Silver complete):** full test coverage, config-entry-unloading, unavailable handling, docs params, integration-owner.
- **v1.1:** induced/pressure edges + escalation (FR-L3), door-gating, radon & CAZ caps (FR-G1/G2), variable-speed drive (FR-L4).
- **v1.2 (Gold):** diagnostics, repairs, devices/dynamic-devices, full translations, reconfiguration-flow, docs-* set.
- **v2.0 (Platinum):** strict typing end-to-end, provably non-blocking engine; opt-in measured gain auto-calibration (FR-S4/X5).

## Dependencies & constraints
- **Std-lib only.** No numpy/scipy — the math (EMA, first-order decay, gap-normalization, greedy arbitration) is light and must stay non-blocking for Platinum `async-dependency`. Keeps `dependency-transparency` trivial and avoids the wheel-rebuild/PyPI fragility seen in other custom integrations.
- **No network egress.** Outdoor CO₂/AQ/radon all arrive as user-selected HA entities.
- **HA minimum version:** TBD at scaffold time (must support config subentries comfortably).

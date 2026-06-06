# Aeolus — Repository Scaffold Plan

> Planned structure and module responsibilities for the eventual integration. **This is a plan, not code** — nothing here is implemented yet. It maps the [REQUIREMENTS](../REQUIREMENTS.md) onto a concrete HA-integration layout and the Quality-Scale rules each piece satisfies.

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
│       └── translations/
│           └── en.json
├── brand/                          # local brand assets (icon/logo) until home-assistant/brands PR
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

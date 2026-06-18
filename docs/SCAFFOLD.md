# Aeolus — Repository Scaffold Plan

> Repository structure + module responsibilities. The v0.1 core scaffold is now built; this maps [REQUIREMENTS](../REQUIREMENTS.md) onto the layout and the Quality-Scale rules.

## v0.1 scaffold status (built 2026-06-05)

**Built (real) — the v0.1 control loop is closed:** `manifest.json`, `hacs.json`, `const.py`, `models.py` (Space/Actuator/Influence + typed `AeolusConfigEntry`), `ema.py` (`TimeAwareEMA` + `SlopeTracker` — **unit-tested**), `estimator.py` (gap-normalized `effective_ach`, exponential time-to-target, reachability), `engine.py` (push engine: source + actuator subscriptions, per-space EMA/slope, actuator command with min on/off, **manual-override detection**, control tick), `controller.py` (per-space **hysteresis** + coverage arbitration over `direct` actuators, safety-gated), `safety.py` (stale safe-state, filter-aware per-pathway outdoor-AQ veto, per-actuator max-runtime), `__init__.py` (lifecycle + subentry→model parsing incl. served-spaces→influences), `config_flow.py` (parent + Space/Actuator subentry flows, actuator served-spaces multi-select), `entity.py`, and all five platforms: `sensor.py` (Space CO₂ + slope/ACH/ETA attrs), `binary_sensor.py` (mitigation-active + attention), `number.py` (target, RestoreNumber), `select.py` (mode), `switch.py` (master enable). Plus `services.py`, `strings.json` (+ entity translations), `services.yaml`, `quality_scale.yaml`, `py.typed`, `pyproject.toml`, `tests/test_ema.py`. **`PLATFORMS` = sensor + binary_sensor + number + select + switch.**

**Quality scale (2026-06-17): Platinum ✅** — every Bronze + Silver + Gold + Platinum rule done or exempt (`mypy --strict` clean; `async-dependency`/`inject-websession` N/A). Gold work: 7 docs sections, `icons.json` (icon-translations), translation-key entity names, diagnostic/disabled-by-default categories, exception-translations, repair-issues for missing configured entities, and live `dynamic-devices`/`stale-devices` subentry add/remove. `brands` satisfied by the in-package `brand/` folder (NOT a home-assistant/brands PR — that repo auto-closes custom integrations). `test-before-configure`/`-setup` exempt (calculated helper; absent sources handled per-entity).

**Tests (`~/venvs/aeolus`, current HA):** **102 passing** — EMA/slope, estimator, config + subentry flows (add + reconfigure), end-to-end setup, control loop (high→on / low→off / paused), outdoor-AQ veto (block / clean / filtered-tolerates), manual-override yield, max-runtime force-off, safety vetoes, entities, services, unload, icon/translation consistency, repair-issues, and live dynamic add/remove of Spaces + Actuators. (`equilibrium_co2` remains deferred to v1.1 — needs an occupancy/generation estimate, FR-S5.)

**Deferred to v1.1 (not stubs — out of v0.1 scope):** induced/diffusive edges + direct→induced escalation (FR-L3/X3), PI control, variable-speed drive (FR-L4), cost-weighted arbitration, occupancy feedforward + `equilibrium_co2` (FR-S5), full CAZ net-exhaust budget + radon veto (FR-G2), auto-calibration (FR-X5), per-actuator influence-row UI (v0.1 uses a served-spaces multi-select → all `direct`, gain `medium`).

**Decisions reflected:** min HA **2025.4** (config subentries); **no DataUpdateCoordinator** → `engine.py` (not `coordinator.py`); `models.py` (not `model.py`); `services.py` for the action-setup rule.

---

## Directory layout (as built)

```
aeolus/
├── README.md
├── REQUIREMENTS.md
├── CHANGELOG.md
├── LICENSE                         # Apache-2.0
├── hacs.json                       # HACS manifest (name, HA min version, render_readme)
├── pyproject.toml                  # ruff + mypy(strict) + pytest config
├── conftest.py                     # pytest fixtures (enable_custom_integrations)
├── .github/workflows/              # claude-code-review.yml, claude.yml
│                                   #   (CI: hassfest + HACS validate + pytest still TODO)
├── custom_components/
│   └── aeolus/
│       ├── __init__.py             # async_setup (action-setup), async_setup_entry/unload,
│       │                           #   runtime_data wiring, live subentry add/remove
│       │                           #   (_async_handle_subentry_change), repair-issue sync,
│       │                           #   async_remove_config_entry_device
│       ├── manifest.json           # domain, iot_class=calculated, quality_scale=platinum
│       ├── const.py                # DOMAIN, defaults (HALFLIFE_SEC=300, MAX_ALPHA=0.5,
│       │                           #   C_OUT=420), enums (Mechanism, InfluenceType, MetricKind…)
│       ├── config_flow.py          # config + options flow; Space & Actuator SUBENTRY flows
│       │                           #   (add + reconfigure); graduated PM/AQI tier wizard
│       ├── engine.py               # the push Engine: source + actuator state subscriptions,
│       │                           #   per-space EMA/slope, command_actuator (min on/off, rearm,
│       │                           #   override detection), control tick, live add/remove
│       ├── models.py               # dataclasses: Space, Actuator, Influence, Metric, Tier,
│       │                           #   AeolusData, typed AeolusConfigEntry
│       ├── ema.py                  # time-aware EMA + slope tracker — pure, unit-tested
│       ├── estimator.py            # gap-normalized effective_ach + exponential time-to-target
│       ├── controller.py           # per-space hysteresis staircase + coverage arbitration over
│       │                           #   `direct` actuators, safety-gated (induced edges deferred)
│       ├── safety.py               # stale-sensor safe-state, filter-aware outdoor-AQ veto,
│       │                           #   per-actuator max-runtime (CAZ/radon vetoes deferred)
│       ├── entity.py               # AeolusSpaceEntity base (has-entity-name, device-per-space)
│       ├── sensor.py               # per-metric value + slope + ACH + reason (push)
│       ├── binary_sensor.py        # mitigation_active, attention
│       ├── number.py               # CO₂ target + per-metric thresholds
│       ├── select.py               # space mode (manage/monitor/off)
│       ├── switch.py               # master enable + per-metric manage gates
│       ├── diagnostics.py          # full dump (graph, EMA/slope, staleness, vetoes, runtime;
│       │                           #   no redaction needed — no secrets)
│       ├── services.py/.yaml       # recalibrate action (gain-reset is a reserved stub)
│       ├── strings.json            # config/options/subentry text, entity names, exceptions, issues
│       ├── icons.json              # icon-translations
│       ├── quality_scale.yaml      # rule-by-rule status (done/exempt)
│       ├── py.typed                # PEP-561 marker (Platinum strict-typing)
│       ├── brand/                  # icon/logo (light+dark) — served by HA's Brands Proxy
│       │                           #   (custom_components/<domain>/brand/, 2026.3+); ships via HACS
│       └── translations/en.json
└── tests/                          # 25+ files: test_ema, test_estimator, test_control,
                                    #   test_controller_unit, test_config_flow, test_subentry_flow,
                                    #   test_safety, test_outdoor_aq, test_parity, test_reload,
                                    #   test_dynamic_devices, test_repairs, test_diagnostics,
                                    #   test_reliability, test_icons, …
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

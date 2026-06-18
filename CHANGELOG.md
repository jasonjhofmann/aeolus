# Changelog

All notable changes to the Aeolus integration are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.5.5] - 2026-06-18

### Changed (internal refactor — no behavior or API change)
- Extracted the runtime-state dataclasses (`MetricRuntime`, `SpaceRuntime`,
  `ActuatorRuntime`) into a new leaf module `runtime.py`, fixing an inverted
  dependency: `safety.py` previously imported these from `engine.py`, which forced
  `engine.py` to import `safety`/`controller` lazily inside methods to dodge a
  circular import. Those lazy imports are now top-level, and `safety`/`controller`
  no longer depend on `engine` at runtime. The types remain re-exported from
  `engine` for backward compatibility. (Audit P3, M3-1.)

## [0.5.4] - 2026-06-17

### Added — config-time validation (enforce what the docs promise)
- **Space:** the High threshold must be above the Target; an invalid combination is now
  rejected in the config flow (both add and reconfigure) with a clear error, instead of
  silently producing a degenerate CO₂ tier with no deadband.
- **Actuator (FR-C8):** a recirculating air purifier (the `filter` mechanism) can no longer
  be assigned to a Space's CO₂ ventilation (`served_spaces`) — the flow rejects it, since a
  filter removes particulates, not CO₂. (The controller already gated this at runtime; now it
  is caught at config time, as the documentation states.)

### Changed
- Docs: README "Testing" section uses `requirements_test.txt` and documents the CI matrix;
  `docs/SCAFFOLD.md` directory tree updated for the CI workflows.

## [0.5.3] - 2026-06-17

### Added
- **Continuous Integration** (`.github/workflows/ci.yml` + `validate.yml`) — the release
  safety net that was missing when v0.5.1 shipped an import break. On every push/PR:
  - **lint** — `ruff check` + `ruff format --check` + `mypy --strict` (Python 3.14);
  - **syntax-floor** — compiles the package on **Python 3.13** (the support floor), so a
    3.14-only construct (the v0.5.1 `except A, B:` regression) fails in CI instead of on a
    user's HA 2025.4 install;
  - **test** — the full suite on a **Python 3.13 + 3.14 matrix** with a 90% coverage gate
    (currently 96%);
  - **hassfest** + **HACS** validation.
- `requirements_test.txt` for local test/dev parity.

### Fixed
- The new CI surfaced pre-existing **hassfest** errors (nothing validated them before):
  - Removed the invalid `homeassistant` key from `manifest.json` (it is not a valid manifest
    key — the minimum-HA-version floor is declared in `hacs.json`; this corrects the v0.5.2
    addition that hassfest rejects).
  - Replaced the HTML-like `<pollutant>` placeholder with `[pollutant]` in the config-flow
    description strings (hassfest forbids HTML in translations).
  - Added `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` (config-entry-only
    integration), clearing the hassfest config-schema warning.
- Set the GitHub repository topics so HACS validation passes.

No change to control behavior.

## [0.5.2] - 2026-06-17

### Fixed
- **Critical: the integration failed to import on Home Assistant < 2026.x (Python < 3.14).**
  v0.5.1's `target-version=py314` let ruff/pyupgrade rewrite `except (TypeError, ValueError):`
  into the bare 3.14-only form `except TypeError, ValueError:` (PEP 758) in `engine.py` and
  `safety.py` — a hard `SyntaxError` on Python 3.13, which is what Home Assistant 2025.4–2025.12
  run. Restored the parenthesized form, verified all source parses under Python 3.13.

### Changed
- **Corrected the supported floor to Home Assistant 2025.4 / Python 3.13** (what `hacs.json` and
  the README already declared, and the minimum that supports config subentries): `requires-python>=3.13`,
  ruff `target-version=py313` (pinned to the floor so the bare-except rewrite can never recur),
  and added the `homeassistant: "2025.4.0"` key to `manifest.json` (previously absent). `mypy`
  stays at `python_version=3.14` to type-check against the installed HA core; this is intentional —
  ruff targets the support floor, mypy targets the analysis runtime.

## [0.5.1] - 2026-06-17

### Changed
- Tooling: declare Python **3.14** as the supported floor (`requires-python>=3.14`,
  ruff `target-version=py314`, mypy `python_version=3.14`) to match Home Assistant's
  minimum runtime; allow intentional domain glyphs (`×`, `–`, `−`, `α`) via ruff
  `allowed-confusables`; ran `ruff format` and cleared all `ruff check` findings.
  No runtime behavior change.

## [0.5.0] - 2026-06-17

### Added — Platinum quality scale (2026-06-17)
- Aeolus now satisfies the full Integration Quality Scale through **Platinum** (manifest
  `quality_scale: platinum`): the Platinum rules were already met (`strict-typing` via `mypy --strict`;
  `async-dependency`/`inject-websession` are N/A for a dependency-free, HTTP-free integration), so
  completing the **Gold** rules below raised the declared tier to Platinum:
  - **Docs**: added README sections for supported devices, supported functions, data-update model,
    use cases, examples, known limitations, and troubleshooting.
  - **icon-translations**: icons moved to `icons.json` (no `_attr_icon` in code).
  - **entity-translations**: the per-metric Manage switch now uses its translation key (no `_attr_name`).
  - **entity-category** / **entity-disabled-by-default**: slope sensors are diagnostic + disabled by
    default (their value is also a value-sensor attribute); ACH/reason/attention diagnostic.
  - **exception-translations**: the `recalibrate` action raises with `translation_key`s.
  - **repair-issues**: a missing configured source/actuator entity (deleted or renamed) raises an
    actionable repair issue pointing to reconfigure.
  - **dynamic-devices** / **stale-devices**: adding or removing a Space/Actuator subentry now takes
    effect live, without reloading the entry; an actuator added later is wired into the CO₂ tiers of
    the Spaces it serves. `async_remove_config_entry_device` allows deleting orphaned devices.

### Fixed (reliability sweep)
- **Cover actuators no longer self-trigger a false manual override** during their transient
  `opening`/`closing` state (previously read as "off" → 30-minute control yield on Aeolus's own command).
- **Out-of-range source readings no longer refresh freshness** (`member_seen`), so the stale-sensor
  safety check trips correctly on a sensor emitting only garbage.
- **Actuator service calls are awaited and log failures** instead of fire-and-forget swallowing them
  (the engine no longer believes a device moved when the command failed).
- All entities are now `should_poll = False` (push/command-driven), removing a pointless 30-second
  platform polling timer.

### Changed
- **Diagnostic logging**: Aeolus now logs (transition-gated) when it commands an actuator on/off, hits
  a max-runtime force-off, engages/clears an outdoor-AQ veto, detects a manual override, adds/removes a
  Space or Actuator live, or raises/clears a repair issue.
- **Diagnostics dump** adds per-metric staleness + `last_raw`, per-space `effective_ach` +
  `time_to_target_min`, per-actuator blocking causes (veto / runtime cap), and the control thresholds.
- Documentation corrections: `recalibrate` is documented as a reserved no-op stub; the fixed 120-minute
  continuous-run cap is documented; induced/pressure edges are correctly listed as deferred.

## [0.4.0] - 2026-06-09

First versioned release (the package shipped as `0.0.1` since the v0.1 MVP; the
manifest version was never bumped, so HA kept reporting `0.0.1` through the
multi-pollutant, parity, diagnostics, and entity-id-cleanup work below). `0.4.0`
reflects the milestones past the MVP: core CO₂ loop → §8 multi-pollutant graduated
ventilation → per-metric parity + explainability (FR-E5–E9 / FR-U2) → diagnostics,
ladder view, `managed_*` entity-id cleanup, and control-precedence help text.

### Added — control-precedence help text on the setup/options flows (2026-06-09)
- Every flow screen that supports help text now explains the control hierarchy, **strongest first**:
  the **Management** switch (global on/off) → each Space's **Mode** (Manage/Monitor/Off) → the advanced
  per-metric **Manage <pollutant>** switches (apply *only* when Mode = Manage; each level overrides the
  ones below). Added to the manager setup step, the **Options** flow, and the Space **add** + **edit**
  forms. (HA renders free-form help only in flow dialogs — the runtime entity more-info cards have no
  description field — so the flows + self-describing entity labels are the supported coverage.)

### Changed — clean up per-Space entity_ids: `managed_*` measurement sensors + migration (2026-06-09)
- The per-metric **measurement sensors** (value, slope, CO₂ ACH) are now named **"Managed
  <metric>"** → entity_ids `sensor.<space>_managed_co2`, `_managed_pm2_5`, `_managed_co2_slope`, …
  Two problems fixed: (1) the CO₂ value sensor was the **bare `sensor.<space>`**, reading as if CO₂
  were the space's default metric (pre-dates PM/humidity); (2) the `managed_` marker keeps Aeolus's
  smoothed output from **colliding with the user's raw source sensors** (convention `<room>_<metric>`,
  e.g. the Aranet `sensor.primary_bedroom_co2`). Status/control entities (mode, mitigation, attention,
  target, threshold, manage switches, status reason) keep their descriptive ids.
- **One-time idempotent migration** (`_migrate_entity_ids`, runs on setup): renames legacy ids to the
  canonical form — also stripping the **double device-name prefix** some derived sensors picked up on
  older builds (`sensor.primary_bedroom_primary_bedroom_pm2_5` → `…_managed_pm2_5`). Skips any rename
  whose target id is already taken (never clobbers another entity); a no-op once ids are canonical.
- Tests: `test_migrate_legacy_entity_ids` + updated naming assertions. 91 tests, `mypy --strict` clean.

### Added — view ladders without re-authoring: `tiers` attribute + diagnostics (2026-06-09)
You can now see a metric's full graduated ladder without walking the (replacing) config-flow
re-author path:
- **`tiers` attribute** on every metric value sensor — the ordered ladder as
  `{engage_at, release_at, setpoints: {<actuator name>: level}}`, viewable in Developer Tools →
  States or an attributes card. Includes the CO₂ metric's synthesized 2-tier (high→target) ladder.
- **`diagnostics` platform (Gold `diagnostics`)** — Download Diagnostics dumps the whole picture:
  spaces (mode/target/status/reason/mitigating/attention) + every metric (value/slope/active-tier/
  managed/**tiers**) + actuators (mechanism/runtime/influences), with **real entity_ids — nothing
  redacted** (Aeolus owns no secrets, NFR-3; entity_ids are needed for inspection and are no more
  revealing than the actuator names already in the ladders). `quality_scale.yaml diagnostics: done`.
  The field-by-field ladder *editor* stays deferred.
- Tests in `tests/test_parity.py` (now 12); 90 tests total, `mypy --strict` clean, 96% coverage.

### Added — per-metric parity (FR-E5–E9) + explainability (FR-U2): BUILT (§8.8) (2026-06-09)
Closes the §8.8 gap — the control engine was multi-metric but the entity/control/status
surface was CO₂-only (observed live on the Primary Bedroom: PM ran but was invisible, and
`attention` couldn't see a PM exceedance). Now built & tested (88 tests, `mypy --strict` clean):
- **Per-metric sensors (FR-E5/E8)** — every configured metric gets a value sensor + a slope
  sensor with the correct device-class/unit (`pm25`/`pm10`/`aqi`/…). `effective_ach` stays
  **CO₂-only** (§8.3 FR-P3). The CO₂ metric keeps its original unique_ids (`<sid>_co2`,
  `_co2_slope`, `_air_change_rate`) and the unsuffixed device name, so a live CO₂ space is
  unchanged; other metrics are suffixed by kind. **Fixes a latent bug**: a PM-only Space's
  primary sensor was previously emitted with a CO₂ device-class/ppm unit.
- **Metric-attributed status (FR-E6)** — `mitigation_active` / `attention` now reflect **any**
  driven metric and expose `driving_metrics` + `active_actuators`; attention is raised by a PM
  (or any) exceedance, not CO₂ alone. Centralized in the engine (`space_status/attention/
  mitigating/driving_metrics`).
- **Per-metric control (FR-E7)** — each non-CO₂ metric gets an engage-threshold `number`
  (tier-1 `engage_at`, live, hysteresis-preserving) alongside the CO₂ Target.
- **Per-metric Manage gate (FR-E9)** — an advanced, `entity-disabled-by-default` "Manage
  <metric>" switch; off → monitor-only (value/status still shown, **demand removed from the
  max-setpoint arbitration**, not a forced actuator-off). Only created when a Space drives >1
  metric. Master Mode select unchanged.
- **Explainability `reason` (FR-U2)** — a per-Space diagnostic sensor (+ `reason` attribute)
  stating *why* the current action: driving metric+tier → actuators, or the blocking cause when
  idle despite demand (outdoor-AQ veto, manual override w/ minutes remaining, runtime cap, stale/
  unavailable, monitoring-only, no-eligible-actuator). Replaces the cryptic activity-log text.
- Controller respects the per-metric gate; the tier latch updates for **all** fresh metrics
  (display correct) while only managed metrics contribute demand. Engine dispatches a per-Space
  refresh each control tick so status/reason track the controller. New `tests/test_parity.py`
  (10 tests); full strings/`en.json` for the new entities. Spec §8.8/§8.7/§3.9 marked built.

### Changed — Spec v3.2: usability pass (§3.9 FR-U + doc cleanup) (2026-06-09)
- **New §3.9 Usability / UX (FR-U1–U5)** consolidating UX intent that was scattered across FR-C10,
  FR-E6/E8, §9, and the Gold docs/repair rules — and adding the missing **explainability**
  requirement: **FR-U2** mandates a per-Space plain-language **`reason`** surfacing *why* the current
  action — driving metric+tier, active actuators, or the **blocking cause when idle despite demand**
  ("outdoor-AQ veto," "over-dry veto," "unreachable," "override — yielding 22 min," "stale," "below
  engage") — replacing today's cryptic "Mitigation active cleared (no running detected)." Plus FR-U1
  progressive disclosure / simple default path, FR-U3 coherent device page + recommended Lovelace
  example, FR-U4 user-facing alerting for blocking states, FR-U5 legible units/precision/icons.
- **Document-usability fixes:** numbered four **dangling `FR-H…` IDs → FR-H7–H10** (sign-gate, high
  ladder, condensation guard, cross-metric arbitration) and the `FR-H...` cross-ref; fixed a broken
  cross-ref (§0.4 "§7.5" → "§7 #5"); added a **Contents** block for navigation; broadened the title
  from "CO₂ & Ventilation Manager" → "**Air-Quality** & Ventilation Manager" (multi-pollutant since
  v3/v4); refreshed Last-updated → 2026-06-09; aligned two "FR-E5–E8" parity refs to **E5–E9**.
  Spec bumped **v3.1 → v3.2**. Spec-only; no code change.

### Decided — management control: one master Mode select, not a dropdown per pollutant (FR-E9) (2026-06-09)
- **Q:** should there be a Configuration/Mode dropdown per pollutant? **A:** no. The per-Space `select`
  Mode (`manage`/`monitor`/`off`) stays the **single master**; finer control is an **advanced,
  disabled-by-default `switch` "Manage <metric>"** per metric (the FR-L6 per-metric gate). A
  manage/monitor/off dropdown *per pollutant* would clutter the common single-CO₂ card and duplicate
  the master, and per-metric `off`-vs-`monitor` is redundant once a metric is configured — the real
  need is the binary "does this pollutant drive actuators."
- **Semantics (FR-L6 extended):** because actuators are **shared across a space's metrics** (bath
  exhaust = CO₂ + humidity; range hood = CO₂ + PM), gating a metric to monitor-only **removes its
  demand from the max-setpoint arbitration**, it does **not** force a specific actuator off (another
  metric may still want it). Space `off`/`monitor` overrides all per-metric gates. Spec-only.

### Changed — Spec: per-metric entity/control/status parity (§8.8, FR-E5–E8) (2026-06-09)
- Captured an **observed conformance gap**: the §8 control engine is fully multi-metric
  (`SpaceRuntime` holds a `MetricRuntime` per metric and the staircase drives PM + CO₂ together),
  but the **entity/control/status surface proxies only the primary (CO₂) metric** by design. Live on
  the **Primary Bedroom** (CO₂ **and** PM mitigation configured, PM has run ≥ once): the device shows
  only Air-change rate / "CO₂ slope" / CO₂ ppm / "Target CO₂"; **no PM sensor or control exists, and
  `attention` — computed purely from CO₂ thresholds — cannot flag a PM exceedance** (a silently-missed
  hazard for the MCAS household, not just a label gap).
- **New requirements FR-E5–E8** (§3.7) + **§8.8** (co-existence narrative + acceptance): per-metric
  value/slope **sensors** for every configured metric (correct device-class/unit; ACH stays CO₂-only);
  `mitigation_active`/`attention`/`status` that reflect **and name** *any* driving metric; a
  **threshold control per non-CO₂ metric**; and symmetric naming (no CO₂-privileged surface). FR-E2/E3
  generalized from CO₂-only to per-metric; the §8.7 "optional per-PM sensors" deferral reclassified as
  **required**. **§9 humidity inherits FR-E5–E8** — the bath-exhaust MVP ships with a humidity sensor +
  humidity-attributed status, not invisible actuation. Spec-only; not yet built.

### Changed — Spec v3.1 (draft): humidity & moisture management (§9, PLANNED) (2026-06-08)
- Major scope expansion captured in `REQUIREMENTS.md §9` (**design stage, NOT built**): humidity
  becomes a **first-class IAQ objective** alongside CO₂ and PM. **Primary, must-ship job: run a
  bathroom's exhaust fan when it gets very humid (shower steam)** — the humidity twin of the live
  CO₂→exhaust loop, reusing the same bath-fan actuator + re-arm (FR-L5b); the MVP is "humidity metric
  + high threshold + exhaust on/off." The rest of §9 is correctness scaffolding around that. Unlike
  §8's metrics humidity is **two-sided** (both high RH → mold/dust-mite/MCAS and low RH →
  eczema-cracking/irritation are harmful), its removal physics run on **absolute humidity / dewpoint**
  (not RH — ventilation moves vapor *mass*), and its floor is the **outdoor** absolute humidity, which
  is **weather-driven and changes sign** (desert dry season vs monsoon — the sign-flip that needs the
  `dehumidify` path).
- New **`humidity`** metric kind (FR-H1, requires a co-located temperature source) deriving
  absolute humidity, dewpoint, and `delta_w = W_indoor − W_out` (FR-H2); two-sided target **band**
  `[rh_low, rh_high]` ~30–55 % (FR-H3).
- New **`dehumidify`** actuator mechanism (FR-H4) — condensation, **no air exchange**, not gated on
  outdoor AH/AQ: the humidity analog of the recirculating `filter`, and the only path when outdoor
  air can't help (monsoon). **ERV latent-recovery attenuation** (FR-H5) — new per-actuator
  `latent_recovery_efficiency`, the moisture analog of PM `filter_efficiency` (Broan ERV110T enthalpy
  core ~0.5–0.6). `filter` (purifier) is capability-gated out for humidity, as for CO₂.
- **Over-dry veto (FR-H6)** — the key cross-metric coupling: below `rh_low`, drying ventilation is
  vetoed/penalized for **every** metric *including CO₂* (the already-shipped desert CO₂ ventilation
  over-dries the house). Plus a condensation/mold guard (dewpoint vs cold-surface temp) and a moisture
  term added to FR-L2 arbitration. Sign-gated outdoor-air mechanisms throughout (never assume outside
  is drier).
- §0.4 household profile, FR-P1 metric enum, and §6 out-of-scope updated; canonical scenarios
  (desert winter over-dry, shower spike + monsoon flip, cold-window condensation) and a 3-phase
  build plan (v4-α observe-only → β high-side → cross-metric+UX). Design under review.

### Added — graduated ladders are now opt-in (FR-C10) (2026-06-08)
- **Manager options flow** with an **`enable_ladders`** toggle (default **off**). The graduated
  PM/AQI tier-ladder wizard (the `add_graduated` step → metric → tiers) only appears on the Space
  form when this is turned on, so the common simple-CO₂ setup is no longer cluttered by it.
- **Non-destructive:** turning the flag off (or never turning it on) never deletes ladders already
  authored on a Space — they keep running and are preserved across reconfigure; they just can't be
  re-authored until the flag is on again. Flipping the flag does not reload the entry.
- **Tests:** `test_options_flow` (toggle hidden by default; options flow reveals it; disabling
  preserves existing metrics on reconfigure).

### Added — v3 multi-pollutant graduated ventilation: BUILT (§8) (2026-06-06)
Implements the §8 expansion (committed; migration-safe; **not yet deployed**):
- **Generalized metrics** — a Space can be driven by `pm1/pm2_5/pm10/aqi/generic` as well as
  `co2`, each with its own sensors, **multi-sensor aggregation** (mean/median/min/**max** =
  "if any exceeds"), and per-metric EMA/slope. New `MetricKind`; `Metric`/`Tier` models.
- **Graduated staircase controller** — per-metric tier ladder with **engage/release hysteresis**
  (`_active_tier`); per-actuator setpoint = **max** across all metrics. The shipped CO₂ control is
  now the 2-tier special case (high→target), synthesized for backward compatibility.
- **Pollutant-aware actuators** — new `filter` mechanism (recirculating purifier); `MECHANISM_REDUCES`
  capability gate rejects a filter for CO₂ (FR-P5) and only uses an actuator for metrics it can
  reduce. Exhaust/ERV stay gated on outdoor PM (FR-G3).
- **Variable drive + groups** — setpoint-based commands (0–100): fan %, switch, cover; one actuator
  can drive **multiple entities** (a purifier group) together (FR-P8).
- **Config-flow tier editor** — a Space wizard (metric → tiers, per-actuator setpoints) authors the
  ladder in the UI; reconfigure re-authors or preserves it. Full translations.
- **Migration** — existing CO₂ spaces parse unchanged (read-time synthesis; no `.storage` rewrite).
- **Tests**: `test_metrics_parse`, `test_tier_ladder` (Kitchen 30/50/80 acceptance + ramp-down +
  filter-rejected-for-CO₂), `test_tier_config_flow`. **75 tests, `mypy --strict` clean.**
- **Deferred**: induced edges (FR-X3) not yet wired into the staircase (helper retained + tested).

### Changed — Spec v3.0 (draft): multi-pollutant graduated ventilation (§8) (2026-06-06)
- Major scope expansion captured in `REQUIREMENTS.md §8` (not yet built): drive Spaces by
  **PM1/PM2.5/PM10/AQI** (not just CO₂) with a **graduated multi-tier response** (engage/release
  thresholds → per-actuator setpoints), **pollutant-aware actuators** (new `filter` mechanism —
  recirculating air purifiers become first-class **PM** actuators, still rejected for CO₂; FR-C8
  revised), **per-tier variable fan %** drive, **multi-entity actuator groups**, and PM-aware safety
  (prefer filtration; gate exhaust on outdoor PM). Canonical Kitchen-PM acceptance scenario
  (30/50/80 µg/m³ ladder → hood + purifier group + remote exhausts). Open design decisions + a
  3-phase build plan (FR-P*, FR-T*). Design under review.

### Added — override confirmation window for cloud actuators (FR-L7b) (2026-06-06)
- Per-actuator **"Manual-override confirmation delay (min)"**. A state divergence
  (actuator reads ≠ what Aeolus commanded) must now *persist* this long before it's
  treated as a manual override and triggers the 30-min yield. 0 = immediate (default,
  unchanged). This stops a **cloud actuator** (LG ThinQ: ~1 min poll lag +
  `unavailable→off→on` flaps) from false-triggering the yield — which had stranded the
  Kitchen Range Hood off for 30 min. Engine tracks `divergence_since`; `_evaluate`
  promotes it to a confirmed override once the grace elapses, and a re-converge within
  the window cancels it. `tests/test_override_grace.py`. Spec → **v2.8** (FR-L7b).
  Needs restart to take effect (new code + config field).

### Added — slope & ACH as first-class sensors (2026-06-06)
- Each Space now exposes **`sensor.<space>_co2_slope`** (ppm/min) and
  **`sensor.<space>_air_change_rate`** (1/h) as their own measurement sensors —
  graphable/recordable, like Versatile Thermostat's temperature slope — instead of
  only living as attributes on the CO₂ sensor (the attributes stay too). `tests/test_derived_sensors.py`.

### Fixed — configured target no longer clobbered by the Target number (2026-06-06)
- The Target `number` was a `RestoreNumber` that restored its last saved value and
  **overwrote `space.target_ppm` on every load** — so a reconfigured subentry target
  was reverted to the stale number value (a Space configured to 600 ran at a restored
  420). The Target number is now **subentry-canonical**: a plain `NumberEntity` that
  reads/nudges `space.target_ppm` live but never overrides the configured value, so a
  reconfigure always wins. (A live nudge is in-session; reconfigure for a persistent
  change.)

### Fixed — live reconfigure / reload-on-update (2026-06-06)
- Added a config-entry **update-listener** that reloads the entry when a Space or
  Actuator subentry is added/reconfigured. Previously the engine parsed thresholds
  only at `async_setup_entry`, so editing a Space's `target_ppm`/`high_ppm` (or any
  subentry field) saved to storage but the **running engine kept the stale values
  until a restart** — e.g. raising a high threshold left the actuator running on the
  old (low) value, which is exactly what stranded the Kitchen Range Hood on. Now any
  subentry edit takes effect immediately. `tests/test_reload.py`. (Needs one restart
  for the listener itself to start running.)

### Added — fan on-speed (FR-L4b) (2026-06-06)
- Per-actuator **fan speed when on** (0–100%, fans only). When Aeolus turns a `fan`
  actuator on, it issues `fan.turn_on` with `percentage=` so a multi-speed fan runs
  at a chosen speed instead of defaulting (e.g. a 5-speed range hood defaulting to
  20% / speed 1). The fan quantizes to its native step. Config-flow slider +
  help text; minutes-style parse (`int` or None); `_send_command` adds `percentage`
  to the `fan.turn_on` data. Tests in `tests/test_fan_speed.py`. Spec → **v2.7**
  (FR-L4b). **Needs an HA restart to take effect** (new Python + config-flow field).

### Fixed — brand icon/logo render locally (2026-06-05)
- Moved `brand/` from the repo root into **`custom_components/aeolus/brand/`** so HA's
  **Brands Proxy** (2026.3+) serves the integration's icon/logo (was "icon not
  available"), and so HACS ships the assets on install. Matches the working VisiblAir
  layout. Browser shows it after a hard refresh; the iOS Companion app (and first-time
  proxy registration) need a full HA restart.

### Added — actuator `rearm_interval` (FR-L5b) (2026-06-05)
- Per-actuator **re-arm interval** (minutes, optional). While a space still demands
  and the actuator is wanted, the engine re-sends the ON command every
  `rearm_interval` to defeat a load that **auto-offs internally while its switch
  keeps reporting `on`** — the Primary-Bath toilet fan (verified 14-min cycle in the
  baseline). Control stays idempotent otherwise; the re-arm is suppressed during a
  manual-override yield. New config-flow field + help text; minutes→`timedelta` in
  parsing; `command_actuator` gained a `_send_command` helper + `last_command_sent`
  cadence stamp. Covered by `tests/test_rearm.py` (re-send / too-soon / no-interval /
  override-suppressed) → **69 tests, mypy --strict clean**.
- **Spec:** `REQUIREMENTS.md` → **v2.6** (adds **FR-L5b** Re-arm interval; status line updated to reflect built/tested/deployed reality).

### Added/Changed — Silver + Platinum rules complete (2026-06-05)
- **entity-unavailable + log-when-unavailable:** the Space CO₂ sensor + status binary sensors report `unavailable` when all of a space's CO₂ sources drop; the engine logs once per availability transition (warning on loss, info on recovery). Fixed a latent EMA-restore bug surfaced by this (seed now applies only when not already live, with a real timestamp → restart continuity actually blends instead of re-initializing).
- **Coverage 98%, 66 tests** — every module ≥95% (engine closed via cover-branch, source garbage/out-of-range guards, min-off, and availability tests). Satisfies Silver `test-coverage`.
- **strict-typing (Platinum):** `mypy --strict` clean across all 16 modules — split the state-change vs state-report handlers by event type, annotated all params, moved `EntityCategory` import to `homeassistant.const`, typed the restore guard.
- **Quality scale: Silver 10/10 ✅, Platinum 3/3 ✅, Bronze 17/18** — only `brands` remains (needs icon artwork + a `home-assistant/brands` PR). `test-before-configure` / `test-before-setup` marked **exempt**: a calculated helper has no external service to verify, and absent source entities are handled per-entity (entity-unavailable) rather than by failing setup.

### Added — v1.1 induced/pressure edges + escalation (2026-06-05)
- **Induced-edge control** (FR-L3/X3): an actuator with an `induced` influence on a target space runs only when the target isn't converging on its own (`CONVERGENCE_SLOPE_PPM_PER_MIN`) AND a named source space is meaningfully lower (`source.ema + gap_margin < target.ema`) — the canonical "ERV can't clear the bedroom → bath exhaust pulls down low Great-Room air" case. Direct + induced now both arbitrate; diffusive remains space↔space (not an actuator edge).

### Changed — test + docs hardening (2026-06-05)
- **62 tests, 96% coverage** on HA 2026.2.3 (config-flow 100%, most modules ≥95%; engine 92% — cover-actuator + override edges — is the remaining gap). Added estimator, subentry-flow, entity, safety, services, engine, controller-unit, induced, and outdoor-AQ suites.
- **Bronze 15/18, Silver 7/10.** README docs sections added (Installation / Configuration / Actions / Removal) → docs-* rules done; `parallel-updates`, `action-exceptions`, `action-setup`, `config-flow-test-coverage` done. Remaining: `brands` (needs icon art + home-assistant/brands PR — see `brand/`), `test-before-configure`/`-setup`, `entity-unavailable`/`log-when-unavailable`, full per-module `test-coverage`, `strict-typing`.

### Changed — Specification v2.5 (2026-06-05)
- **Precise ERV filter facts** (it does have filters, just coarse ones): Broan ERV110T uses **2× washable 30-PPI foam pre-filters** (part `BRNS99010264`), ~MERV 1–4 — catches lint/large debris/some large pollen, negligible for fine PM2.5/smoke. Net conclusion from v2.4 unchanged (fine-PM `filter_efficiency` ≈ 0, gated as strictly as infiltration, MERV-13+ retrofit recommended), now with a marginal large-pollen credit + a maintenance-coupling note (dirty foam chokes airflow → don't assume rated CFM).

### Changed — Specification v2.4 (2026-06-05)
- **Corrected the ERV filtration assumption.** The installed **Broan ERV110T** (discontinued) ships with only a foam pre-filter (~MERV 1–2; optional MERV 8) → effectively no PM2.5/allergen filtration. So the ERV does **not** get a relaxed PM-veto threshold; it's a PM-import path gated as strictly as unfiltered infiltration. Its advantage over exhaust is being *balanced* (no forced infiltration), not filtration. To earn the relaxed threshold: add an external inline MERV-13+ filter box on the supply (mind static pressure), or lean on the room HEPA purifiers (model ERV PM import vs. purifier CADR headroom). `filter_efficiency` clarified as the actual per-path value (foam≈0 / MERV8≈0.2 / MERV13≈0.5 / HEPA≈0.99).

### Changed — Specification v2.3 (2026-06-05)
- **FR-G3 upgraded to a per-pathway, filter-aware veto.** The veto sensor is assignable per outdoor-air influence (ERV intake vs. infiltration point vs. regional), and the trip quantity is the *estimated indoor PM contribution* = `outdoor_PM × (1 − filter_efficiency)` — so a filtered ERV tolerates higher outdoor PM than unfiltered infiltration. FR-C4 gains a per-actuator AQ source + filter efficiency.
- Reference deployment: 3 particulate sensors — Western Trails AirVisual (regional, published→API→HA), a 2nd AirVisual at the ERV intake, a PurpleAir at the Primary Bedroom sliding door. (PurpleAir PMS5003 humidity-correction note.)

### Changed — Specification v2.2 (2026-06-05)
- **Resolved §7.5 with the appliance inventory:** no atmospheric/natural-draft combustion in the main envelope (sealed tankless WHs in a separate sealed garage, sealed/direct-vent fireplaces, unvented gas range with no flue) → **strict CAZ net-exhaust budget dropped**; per-actuator max-runtime + radon monitor retained.
- **Added §0.4 Household IAQ priority** (allergy/MCAS household, leaky envelope): allergen/PM protection is **co-primary** with CO₂; depressurizing/exhaust strategies are **health-penalized** (they pull unfiltered allergens through leaky doors) → prefer the filtered balanced ERV; outdoor-AQ veto elevated to a **low-threshold, multi-pollutant co-primary objective** (FR-G3); cooperate with the air purifiers, don't fight them.
- Gas range noted as a kitchen emission source (ducted range hood is the actuator; recirculating hoods don't help).

### Changed — Specification v2.1 (2026-06-05)
- **Resolved all 5 open decisions (§7):** (1) MVP slice = the core loop (spaces+sensors+EMA/slope/ACH+on/off direct actuators+threshold+outdoor-AQ veto+stale safety+per-actuator max-runtime), induced/diffusive/calibration/variable-drive/full-CAZ deferred to v1.1; (2) primary entity = sensor-centric (no domain abuse); (3) gains = buckets drive control, measured ACH observe-only until Gold; (4) C_out = single global value, entity-or-constant (default 420; this house has no outdoor CO₂ source); (5) combustion/radon = per-actuator max-runtime in v1, full CAZ budget + radon veto in v1.1, worst-case-safe defaults until the gas-appliance inventory is provided.
- Status moved from "draft for review" to "decisions resolved; ready to scaffold v0.1 MVP."

### Added — Specification v2.0 (2026-06-05)
- Initial repository: `README.md`, versioned `REQUIREMENTS.md` (v2.0), `docs/SCAFFOLD.md` (structure + Quality-Scale traceability + roadmap), Apache-2.0 `LICENSE`.
- Building-physics backbone: single-zone mass balance, exponential decay toward outdoor floor, reachability condition, gap-normalized **effective ACH** as the comparison metric, MIMO `M(u)` shared-air coupling (direct / diffusive / **induced**).
- EMA/slope grounded in Versatile Thermostat's `ema.py` (time-aware α from half-life + actual Δt, `max_alpha` cap, irregular-cadence handling).
- Hard guardrails: HEPA/recirculation rejection, outdoor-AQ veto, radon-on-depressurization veto, CAZ combustion-safety caps, per-member stale-sensor safe-state, manual-override yield.
- Quality-Scale plan: build for **Silver**, architected for **Platinum**.

### Open input still needed
- The gas/combustion appliance inventory (atmospheric vs sealed/direct-vent vs electric) — required before the v1.1 CAZ depressurization caps can be relaxed from their worst-case-safe defaults. Not blocking the v0.1 MVP.

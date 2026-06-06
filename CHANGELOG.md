# Changelog

All notable changes to the Aeolus specification are documented here. The project is in the **requirements stage** — no integration code exists yet.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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

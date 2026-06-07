# Aeolus — Adaptive CO₂ & Ventilation Manager for Home Assistant
**Requirements Specification — v3.0 (draft — multi-pollutant scope expansion under review)**

| | |
|---|---|
| **Status** | v1.1 **built, tested (76 tests, `mypy --strict`), deployed & live** on the author's HA (CO₂ control across 3 spaces, fan on-speed, override grace, reload-on-update). **§8 v3 expansion (multi-pollutant, graduated ventilation) is in requirements** — design under review, not yet built. |
| **Build target** | HA Integration Quality Scale — **Silver** |
| **Architected for** | **Platinum** |
| **Domain** | `aeolus` |
| **iot_class** | `calculated` (local push) |
| **Last updated** | 2026-06-05 |

> **The name.** **Aeolus** is the Greek keeper of the winds — the figure who holds many separate winds and *releases each on demand*. That is precisely this integration: a controller that orchestrates multiple, cross-coupled air streams (ERV, exhausts, fans, windows) across rooms that share air, releasing the right one at the right time to manage CO₂. (Verify the slug is free on `home-assistant/brands` and PyPI before first release.)

---

## 0. Nature, positioning, and a correctness warning that reshapes the design
- **0.1** Aeolus is a **calculated/local-push helper integration** (`iot_class: calculated`). It owns no hardware or cloud; it composes existing HA entities. Auth/reauth quality rules are therefore **exempt**.
- **0.2** It is the air-quality sibling of Versatile Thermostat, but with a real **building-physics model** and **multi-zone (MIMO) shared-air coupling**, which VT does not have.
- **0.3 — Critical domain correction (enforced in config, not just docs):** **CO₂ is a gas removed only by *air exchange* (ventilation/dilution), never by filtration.** HEPA, activated carbon (at room loadings), PCO, and ionizers do **not** reduce CO₂. The integration must **reject or hard-warn** when a recirculating air purifier is selected as a CO₂ actuator. Valid actuators move *outdoor* air in/out or move air *between zones of differing CO₂*. Encoded as FR-C8.
- **0.4 — Household IAQ priority (this deployment; see [[household-iaq-health-profile]]).** The reference home is an **allergy/MCAS household** (occupant with Mast Cell Activation Syndrome + eczema; both occupants severe allergies) with a **leaky envelope** (sliding glass doors). Consequences that override the generic design:
  - **Allergen/PM protection is co-primary with CO₂ — never trade one for the other.** Importing outdoor air to cut CO₂ must not raise the indoor PM/pollen/VOC load. The outdoor-AQ veto (FR-G3) is therefore a *first-class objective at a low threshold*, not a wildfire-only guardrail.
  - **Depressurizing (exhaust-dominant) strategies are health-penalized, not just energy-penalized:** with leaky doors, any net depressurization pulls **unfiltered** outdoor allergens straight through the envelope. So **prefer the balanced ERV over exhaust** — but for the *pressure* reason (it doesn't force infiltration), **NOT** because it filters (it barely does — see below). Down-weight exhaust/induced strategies (FR-L2 cost) even though there is *no* combustion-backdraft risk (see §7.5).
  - **The ERV is itself a PM-import path (corrected v2.4–2.5).** The installed unit is a **Broan ERV110T** (discontinued). It DOES have filters — **2× washable 30-PPI foam pre-filters** (part `BRNS99010264`, one per air stream) — but foam is a **coarse / core-protection** medium (~MERV 1–4): it catches lint/large dust/insects and *some* large pollen (10–100 µm), but is **negligible for fine PM2.5/smoke**. So for the fine-PM veto its `filter_efficiency` ≈ 0 and the ERV is gated at the **same strict outdoor-PM threshold as unfiltered infiltration** (marginal large-pollen credit only). To earn a relaxed threshold: (a) add an **external inline MERV-13+ filter box on the fresh-air supply** (mind static pressure — ERV blowers are low-static; HEPA likely needs a booster); or (b) rely on the room HEPA purifiers to clean up the imported PM (next bullet). *Maintenance coupling: a clogged foam filter chokes ERV airflow → rinse periodically; Aeolus should not assume rated CFM if the filter is dirty.*
  - **Cooperate with the air purifiers, don't fight them:** purifiers remove PM (not CO₂); Aeolus removes CO₂ (not PM). Model the ERV's net PM impact as *outdoor PM (at its intake sensor) minus the room purifiers' cleanup headroom (CADR)* — a moderate-PM day is acceptable only if the purifiers have capacity to absorb the imported load.

---

## 1. Physical model (the backbone — everything else derives from this)

### 1.1 Single-zone mass balance
A well-mixed zone of volume `V`:
```
V·dC/dt = G(t) + Q·C_out − Q·C
⇒ dC/dt = G/V − λ·(C − C_out),   λ ≡ Q/V  (air-change rate, ACH)
```
- `C_out` — outdoor CO₂, the **hard asymptotic floor** (~420 ppm today; unreachable below it). Configurable, ideally **measured**.
- `G` — generation (occupancy-driven; ~0.0046 L/s·person sedentary). The **disturbance**.
- `λ` — effective air-change rate — **what actuators change.**

### 1.2 Three consequences the software must respect
- **R-PHYS-1 (exponential, not linear).** `C(t) − C_out = (C₀ − C_out)·e^(−λt)`. Time-to-target uses the exponential form: `t = (1/λ)·ln[(C₀ − C_out)/(C_target − C_out)]`.
- **R-PHYS-2 (reachability).** Steady state `C_ss = C_out + G/Q`. A target is achievable only if `C_target > C_out + G/Q_max`; otherwise the space is **unreachable** — detect and report, don't run actuators forever.
- **R-PHYS-3 (the right effectiveness metric).** Instantaneous slope `dC/dt = −λ(C − C_out) + G/V` is **gap-dependent** — the same fan looks "stronger" at higher CO₂. The comparable, concentration-independent effectiveness is the **air-change rate λ**, recovered by normalizing slope by the driving gap: `λ_eff ≈ −slope/(C − C_out)` during low-generation decay. Aeolus reports **both** raw slope (VT-style UX) and `effective_ach` (the principled metric; basis for gain identification).

### 1.3 Multi-zone (MIMO) coupling — the heart of the problem
```
dC/dt = −M(u)·(C − C_out·𝟙) + g/V
```
`M(u)` = air-exchange matrix: diagonal = each zone's outdoor exchange; off-diagonal = inter-zone exchange. Actuators `u` modify `M`. **Induced/pressure couplings make `M(u)` bilinear** (an exhaust opens an inter-zone flow whose benefit depends on the *source* zone's concentration). Aeolus need not solve this matrix analytically, but its data model and controller must be a faithful explicit representation of it (FR-X*).

---

## 2. Domain model & terminology

| Term | Definition |
|---|---|
| **Space** | A managed zone. 1..N CO₂ sensors → one aggregated value. Has volume `V`, target/thresholds, optional HA area, occupancy hint, outdoor-AQ veto reference. |
| **Actuator** | A ventilation entity that changes `λ` or inter-zone flow: ERV/HRV (switch/fan/number/`select` boost), exhaust fan, supply fan, window opener (`cover`), transfer fan. On/off **or** variable. |
| **Influence (Actuator→Space)** | Edge: **mechanism** (supply/exhaust/balanced/transfer), **sign & gain** (ΔACH bucket or measured), **transport lag**, **type** (direct/induced). |
| **Air-share link (Space↔Space)** | Passive diffusive coupling; optionally **gated by a door/opening sensor**. |
| **Induced influence** | An exhaust whose benefit to space *P* is **conditional** on a named **source space** being lower (depressurization-draws-cleaner-air). |
| **Engine** | Central coordinator: sensor ingest, EMA/slope/λ estimator, occupancy/disturbance estimator, arbitration controller, safety supervisor. |

---

## 3. Functional requirements

### 3.1 Configuration (UI; config subentries)
- **FR-C1** All config via config flow + options/reconfigure flow. No YAML.
- **FR-C2** **Config subentries**: one config entry; **Space** and **Actuator** are subentry types (add/edit/remove independently). Also satisfies Gold `dynamic-devices`/`stale-devices`.
- **FR-C3 (Space)** name; HA area; CO₂ sensor selector (multi, `device_class: carbon_dioxide`); aggregation (mean/median/min/max/worst-case-max); **volume `V`** (manual or area×height); target ppm; elevated/high thresholds; optional **occupancy entity** for feedforward; optional **outdoor-AQ veto** entity + threshold; optional **radon entity** for the depressurization cross-check.
- **FR-C4 (Actuator)** entity; **mechanism** (supply/exhaust/balanced/transfer/window); "active" definition (on/off, %≥N, preset∈set); rated airflow (CFM, optional gain prior); per-affected-space **influence rows** (gain bucket None/Low/Med/High or measured ΔACH; lag; type). For **induced** rows: **source space** + minimum gap margin. For **window/cover**: couple to outdoor-AQ veto by default. For any **outdoor-air mechanism** (supply/balanced/window/depressurizing-exhaust): optional **co-located outdoor-AQ sensor** (the veto source for *this* pathway, FR-G3) + **filter efficiency** (0 = unfiltered infiltration … ~0.9+ = HEPA-filtered ERV intake) used for the filter-aware PM-import estimate.
- **FR-C5** Air-share links: Space↔Space, strength, optional gating door/opening sensor.
- **FR-C6 `test-before-configure`**: validate entities exist, correct domain/device_class, sensors emit numeric ppm in plausible range; reject with actionable text.
- **FR-C7 `unique-config-entry`** + guard against a sensor double-counted across overlapping spaces.
- **FR-C8 (§0.3 guard)** When an actuator suggests recirculating filtration (air_purifier device class / known purifier integrations), **block with an explanatory error / repair issue**.
- **FR-C9** Altitude/pressure note: NDIR ppm readings are pressure-sensitive (installation may be at elevation); expose optional per-sensor offset/scale; document ABC-calibration assumptions (self-zero to ~400 ppm on periodic fresh-air exposure).

### 3.2 Measurement & smoothing (EMA — Versatile Thermostat's `ema.py` scheme)
- **FR-M1** Aggregate member sensors per space on any member update; compute **per-member freshness** (do NOT trust the aggregate timestamp — a mean keeps reporting fresh while a member is dead).
- **FR-M2 Time-aware EMA**: `α = 1 − exp(ln(0.5)·Δt/halflife)`, `α = min(α, max_alpha)`, `ema = α·x + (1−α)·ema_prev`, init `ema = x₀`. Per-space `halflife_sec` (default 300), `max_alpha` (default 0.5; caps weight from long gaps — essential for irregular CO₂ cadence), `precision` (1 ppm). Reject Δt ≤ 0 and out-of-range readings.
- **FR-M3** Expose raw aggregate and `ema_co2`.

### 3.3 Slope, air-change estimation & prediction
- **FR-S1** `co2_slope` (ppm/min, signed; negative = improving) = rate of change of the **EMA series**, itself lightly slope-smoothed. Also `co2_slope_per_hour`.
- **FR-S2** `effective_ach` (R-PHYS-3): `−slope/(ema − C_out)` when generation is low/stable; cross-actuator-comparable effectiveness.
- **FR-S3** `equilibrium_co2` estimate + **exponential** `time_to_target` (R-PHYS-1). Emit `diverging`/`unreachable` (R-PHYS-2) when applicable.
- **FR-S4 Per-(actuator, space) identified gain**: from change in λ_eff when an actuator toggles (tracer-decay system-ID), gap-normalized. Diagnostic surface (e.g. "Primary Bath Exhaust → Primary Bedroom ≈ +0.4 ACH, induced, valid when Great Room < bedroom").
- **FR-S5 Occupancy/disturbance estimate**: infer `G` from rise rate when ventilation is low; if an occupancy entity is configured, use it as **feedforward** (pre-ventilate ahead of known occupancy).

### 3.4 Cross-space coupling
- **FR-X1** Maintain the explicit influence graph = software image of `M(u)`: actuators, spaces, Actuator→Space edges (mechanism/gain/lag/type), Space↔Space air-share edges (optionally door-gated).
- **FR-X2** Evaluate **all** spaces an actuator touches, including **negative/neutral** effects (a supply fan from a higher-CO₂ plenum can *raise* a zone — representable as a non-reducing/conditional edge).
- **FR-X3** **Induced edges are conditional**: benefit to *P* applies only while `source_space.ema + margin < P.ema`; otherwise the actuator offers *P* nothing and must not be chosen for *P*.
- **FR-X4** **Door/opening gating**: air-share and some induced paths suppressed when a gating sensor reads "closed."
- **FR-X5** Gains **declarative first** (buckets). **Measured auto-calibration** (FR-S4) is opt-in (Gold maturity) — shared air makes clean attribution hard.
- **FR-X6 Controllability check**: flag spaces not independently controllable by any direct actuator (e.g., reachable only via an induced path).

### 3.5 Control / arbitration
- **FR-L1** Per-space control on `(ema − target)` with **hysteresis/deadband**. A **PI** form (proportional + slow integral on the gap) preferred over pure bang-bang for variable actuators; derivative info from slope.
- **FR-L2 Arbitration** across spaces: choose the actuator set maximizing covered over-threshold demand (coverage × gain), tie-broken by **cost** (energy/enthalpy, depressurization, outdoor-AQ risk). A shared ERV satisfying many spaces outranks many small fans.
- **FR-L3 Strategy escalation (canonical use case)**: if a space is over target with its **direct** actuators active but **slope shows non-convergence** (FR-S3), escalate to **induced** actuators whose source space is currently low (FR-X3).
- **FR-L4** Variable drive: proportional speed/preset where supported; on/off otherwise.
- **FR-L4b Fixed fan on-speed**: per-actuator option to drive a multi-speed `fan` at a chosen percentage when turned on (the fan quantizes to its native step). Lets a range hood / ceiling fan run at a useful speed instead of whatever it defaults to. Precursor to full proportional drive (FR-L4).
- **FR-L5** Transport-lag aware: **min on/off**, post-actuation **settle window**, anti-windup — prevents hunting in a cross-coupled, dead-time system.
- **FR-L5b Re-arm interval (self-auto-off loads)**: for an actuator whose load auto-offs internally while its switch keeps reporting `on` (e.g. a bath fan with a built-in timer that the relay can't observe), re-send the ON command at a configurable per-actuator interval while the space still demands and no override is active. Default off (normal idempotent control). *Motivating case: the Primary-Bath toilet exhaust, whose Savant switch holds `on` through the fan's ~15–30 min hardware auto-off; the legacy automation re-armed it every 14 min.*
- **FR-L6** Per-space mode: `manage` / `monitor-only` / `off`.
- **FR-L7 Manual-override yield**: detect external changes to a managed actuator, mark `overridden`, yield for a configurable window, then resume.
- **FR-L7b Override confirmation window**: a per-actuator delay a state divergence must *persist* before it counts as a manual override (0 = immediate, default). Filters transient flaps from cloud actuators — e.g. LG ThinQ's ~1 min poll lag + `unavailable→off→on` blips — that would otherwise false-trigger the yield and strand the device.

### 3.6 Safety, IAQ trade-offs & guardrails (non-optional)
- **FR-G1 Combustion safety (CAZ depressurization).** Sustained net exhaust depressurizes the envelope → backdraft risk for *atmospheric/natural-draft* combustion appliances. Enforce **per-actuator max runtime** always; the **global max-simultaneous-net-exhaust (CAZ budget)** is required only when atmospheric appliances share the envelope. **Reference home (confirmed 2026-06-05): NO atmospheric appliances** — tankless water heaters are sealed and in a separately-sealed garage; propane fireplaces are sealed/direct-vent; the gas range is unvented but has no flue to backdraft (it is an *emission* source handled by ventilation, not a CAZ hazard). → **CAZ budget relaxed for this deployment; keep per-actuator max-runtime + the radon monitor.** ⚠️ But exhaust still carries an **allergen-infiltration** cost here (§0.4) — that penalty, not backdraft, is what limits exhaust strategies for this house.
- **FR-G2 Radon cross-effect.** Depressurization increases soil-gas radon entry. If a space has a radon entity, **monitor and veto/curb exhaust strategies** coinciding with rising radon.
- **FR-G3 Outdoor-AQ veto (co-primary objective — see §0.4).** Outdoor air imports PM2.5/PM10/ozone/smoke/pollen. **Block outdoor-air strategies when the relevant outdoor-AQ exceeds threshold.** Surface the CO₂-vs-PM trade-off explicitly; never silently swap hazards. For allergy/MCAS households the threshold is **low and multi-pollutant** (PM2.5 *and* pollen); an outdoor-air strategy that would raise indoor PM is rejected even if CO₂ is high.
  - **PER-PATHWAY veto sources (not one global number).** The outdoor air a strategy moves differs by pathway, so the veto sensor is assignable **per outdoor-air influence** (FR-C4): ERV → a sensor at its *intake*; a depressurizing/door-infiltrating strategy → a sensor at *that* infiltration point; a regional sensor as fallback/corroboration. Reference deployment: Western Trails AirVisual (regional, published→API→HA), a 2nd AirVisual at the **ERV intake**, a **PurpleAir at the Primary Bedroom sliding door** (the leaky-envelope infiltration point).
  - **FILTER-AWARE thresholds.** The quantity that matters is the *estimated indoor PM contribution* = `outdoor_PM × (1 − filter_efficiency)` of that pathway, where `filter_efficiency` is the **actual** filtration on *that* path (foam ≈ 0, MERV 8 ≈ 0.2, MERV 13 ≈ 0.5, HEPA ≈ 0.99). A genuinely filtered intake tolerates higher outdoor PM; an unfiltered one (efficiency = 0) gets the strictest threshold. **⚠️ Don't assume the ERV is filtered:** the installed Broan ERV110T ships ~unfiltered (foam only), so until an inline MERV-13+ box is added its `filter_efficiency` ≈ 0 and it is gated as strictly as infiltration (§0.4). (PurpleAir PMS5003 reads high at elevated RH → apply the EPA/LRAPA humidity correction.)
- **FR-G4 Energy/enthalpy awareness.** Prefer **balanced ERV** over exhaust; allow energy as an arbitration cost (FR-L2). Optional gate on HVAC/VT state.
- **FR-G5 Stale-sensor safety.** On per-member staleness/unavailability, **stop integration-initiated mitigation** for that space, set `status: stale`, log (`log-when-unavailable`, `entity-unavailable`).
- **FR-G6** Idempotent, rate-limited commands; never short-cycle fans.

### 3.7 Entities, attributes, devices
- **FR-E1** One **device per space** (Gold `devices`); actuators linked via `via_device` where sensible.
- **FR-E2** Per space: primary `sensor` (Space CO₂) with attributes `ema_co2`, `co2_slope`, `co2_slope_per_hour`, `effective_ach`, `equilibrium_co2`, `time_to_target`, `status` (ok/elevated/high/mitigating/diverging/unreachable/overridden/stale), `active_actuators`, `target`, `mode`, `estimated_occupancy`. Plus `binary_sensor` `mitigation_active` and `attention`.
- **FR-E3** Control entities: `number` (target), `select` (mode), `switch` (master enable). All `has-entity-name`, `entity-unique-id`, `entity-device-class`, `entity-category`, sensible `entity-disabled-by-default` for advanced diagnostics, full `entity-translations`/`icon-translations` (Gold).
- **FR-E4** Diagnostic entities: per-(actuator,space) identified gain, last decay-test results, per-sensor freshness, controllability flags.

### 3.8 Services / actions
- **FR-A1** `aeolus.set_target`, `set_mode`, `force_strategy` (manual actuator-set + duration; also runs a deliberate decay test for calibration), `recalibrate`/`reset_gains`.
- **FR-A2** Registered in `async_setup` (`action-setup`), documented (`docs-actions`), raising **translated** typed exceptions (`action-exceptions`, `exception-translations`).

---

## 4. Canonical acceptance scenario (reference home → model)

| Real element | Model representation |
|---|---|
| Whole-home **ERV** | Actuator, **balanced**; **direct** influences: Upper Level (High), most rooms (Med), Primary Bedroom (≈None). |
| **Primary Bath Exhaust** | Actuator, **exhaust**; **induced** influence on **Primary Bedroom**, **source = Great Room**, gated on `Great Room EMA + margin < bedroom EMA`; capped by FR-G1/G2. |
| Great Room ↔ Hallway ↔ Primary Bedroom | **Air-share links**; hallway link **door-gated**. |
| Behavior under test | ERV runs (covers many spaces, low cost). Primary Bedroom stays high with non-converging slope (≈0 ACH from ERV) → escalate to Bath Exhaust; induced benefit valid because ERV already pulled the Great Room down; runtime capped, radon-watched. |

Exercises direct + diffusive + induced + escalation + safety vetoes; the headline regression test.

---

## 5. Non-functional / Quality-Scale requirements

### 5.1 Silver (build target — complete)
`config-entry-unloading` (clean unsubscribe/teardown of all source listeners) · `entity-unavailable` + `log-when-unavailable` · `action-exceptions` · `parallel-updates` declared · `integration-owner` · `docs-configuration-parameters` + `docs-installation-parameters` · `test-coverage` >95% · (`reauthentication-flow` **N/A** — no auth). All **Bronze** rules are prerequisites (config-flow + tests, runtime-data, entity-event-setup, test-before-setup, brands, common-modules, dependency-transparency, docs set).

### 5.2 Gold (architect for from day one)
`devices` + `dynamic-devices` + `stale-devices` (spaces via subentries) · `diagnostics` (redacted: graph, gains, EMA/slope state, vetoes) · `repair-issues` (HEPA-selected, sensor-stale, unreachable target, outdoor-AQ blocking, radon-veto-active, uncontrollable space) · `reconfiguration-flow` · `entity-translations`/`icon-translations`/`exception-translations` · `entity-category`/`entity-device-class`/`entity-disabled-by-default` · full `docs-*` (use-cases, known-limitations, troubleshooting, data-update, examples). (`discovery*` **N/A**.)

### 5.3 Platinum (the plan)
`strict-typing` (fully typed, `mypy --strict`, `py.typed`) · `async-dependency` (all internal compute async/non-blocking; no blocking math libs — keep std-lib so trivially satisfied) · (`inject-websession` **N/A** — no HTTP). Platinum here ≈ strict typing + provably non-blocking engine, both achievable because the integration is dependency-free local compute.

### 5.4 Reliability / performance / security
- **NFR-1** Single push-based engine (coordinator), event-driven on source updates + a bounded periodic control tick (`appropriate-polling`); no per-entity HA polling.
- **NFR-2 Restore across restart**: `RestoreEntity` for EMA/slope seeds + persisted identified gains; cold-start degrades gracefully.
- **NFR-3** No secrets, no network egress (outdoor data via user-provided HA entities, not Aeolus calls).
- **NFR-4** O(spaces + edges) per tick; trivially within HA budget.

---

## 6. Out of scope
Temperature/HVAC control (pairs with Versatile Thermostat) · airflow/pressure *measurement* (inferred only) · code-compliance certification · CO (carbon-monoxide) life-safety detection · sorbent/biological CO₂ capture (negligible at room scale).

## 7. Resolved decisions (v2.1 — 2026-06-05)

1. **MVP slice — RESOLVED: ship the core loop (v0.1).** Spaces + CO₂ sensors (aggregation + per-member freshness) + time-aware EMA + slope + `effective_ach` + **on/off direct actuators** + threshold/hysteresis control + **outdoor-AQ veto** + **stale-sensor safe-state** + **per-actuator max-runtime cap**. Lands Bronze + most of Silver and already solves the whole-home-ERV case. **Deferred to v1.1:** induced/pressure edges + escalation (FR-L3, FR-X3), diffusive air-share links (FR-X4), door-gating, occupancy feedforward (FR-S5), variable-speed drive (FR-L4), auto-calibration (FR-X5/S4), full CAZ net-exhaust budget + radon veto (FR-G1 full / G2). *Rationale: prove the closed loop correct + useful standalone before the novel shared-air modeling; outdoor-AQ + stale + max-runtime are cheap correctness/safety, so they ship in v1.*
2. **Primary entity — RESOLVED: sensor-centric.** Per space: `sensor` (Space CO₂ + slope/ach/status attrs) + `binary_sensor` (mitigation/attention) + `number` (target) + `select` (mode) + `switch` (enable). No HA domain cleanly models a ventilation controller (`climate`=temp, `humidifier`=RH → domain abuse), so compose idiomatic standard entities. A bespoke single-card "manager" entity can be added later without breaking these.
3. **Gains — RESOLVED: buckets drive control; measured ACH observe-only until Gold.** Config uses qualitative buckets (None/Low/Medium/High → internal numeric ΔACH priors); these alone feed coverage×gain arbitration. `effective_ach` is measured continuously for display/comparison but is NOT fed back into control until opt-in auto-calibration (Gold) — clean per-actuator attribution in shared air is unreliable.
4. **C_out — RESOLVED: single global value, configurable entity with constant fallback (default 420 ppm).** Not per-space (outdoor CO₂ is ~uniform). It is the asymptotic floor and the denominator of `effective_ach`, so clamp `(C − C_out) ≥ ε` to avoid divide-by-zero / negative ACH on sensor noise. **This house:** no reliable outdoor CO₂ source exists (AirVisual Outdoor = PM/AQI, not CO₂) → use the 420 constant (seasonally ~420–430).
5. **Combustion/radon caps — RESOLVED (inventory confirmed 2026-06-05).** Appliance inventory: tankless gas water heaters (sealed, in a separately-sealed conditioned garage); propane decorative fireplaces (sealed/direct-vent); gas range (unvented, no flue); electric dryer; rest electric. ⇒ **NO atmospheric/natural-draft combustion in the main envelope → the strict CAZ net-exhaust budget is NOT needed.** Ship **per-actuator max-runtime** in v1; keep the **radon monitor** (Aranet Radon+, v1.1). **The constraint that actually limits exhaust strategies for this house is allergen infiltration through the leaky envelope (§0.4), not backdraft** — modeled as a health cost in arbitration (FR-L2) + the low-threshold outdoor-AQ veto (FR-G3), strongly favoring the filtered balanced ERV. *(The gas range is a kitchen emission source — CO₂/NO₂/CO/cooking-PM — best handled by a ducted range hood; flag if the hood is recirculating, since that removes neither the gases nor, fully, the PM.)*

---

## Appendix A — Two design decisions that make this correct (not just "VT-for-CO₂")
- **(a)** `effective_ach` (gap-normalized) is the comparison/learning metric, not raw slope. Raw ppm/min is fine for the dashboard but physically misleading for comparing actuators or learning gains, because it scales with current CO₂.
- **(b)** Outdoor-AQ and radon vetoes are **hard guardrails**, not niceties. "Reduce CO₂ by exhausting" can import PM2.5 and pull radon from the slab; an air-quality manager that silently trades one hazard for another is a defect, not a feature.

## Appendix B — Provenance
The EMA/slope approach is modeled on Versatile Thermostat's `custom_components/versatile_thermostat/ema.py` (time-aware exponential moving average; `alpha` derived from a half-life and the actual inter-sample interval, capped by `max_alpha`; handles irregular sensor cadence) and its `temperature_slope` reporting — adapted here to CO₂ with the gap-normalized ACH extension.

---

## 8. v3 Scope expansion — Multi-pollutant, graduated ventilation & filtration

**Status:** requirements (2026-06-06). Expands Aeolus from single-pollutant (CO₂), essentially on/off control to **multi-pollutant, multi-tier (graduated) ventilation + filtration**. The CO₂ control already shipped becomes the 2-tier special case of a general staircase controller.

### 8.1 Pollutants / metrics (FR-P)
- **FR-P1** A Space may be driven by one or more **metrics**, each `(kind, sensor(s), aggregation)` where kind ∈ `co2 | pm1 | pm2_5 | pm10 | aqi | generic` (any numeric sensor). Aggregation reuses mean/median/min/**max**; **max = "if ANY listed sensor exceeds"** (the canonical example uses max of two PM sensors).
- **FR-P2** Each metric carries its own response ladder (§8.2) and its own removal physics (§8.3). The existing CO₂ `target/high` is the degenerate 2-tier ladder.
- **FR-P3** Floors/units per kind: PM in µg/m³ (floor = the *outdoor* PM level, not a constant); AQI unitless; CO₂ ppm (floor ≈ 420). Gap-normalized effective-ACH is a CO₂/decay concept only; for PM, report raw level + slope/trend.

### 8.2 Graduated tiered response (FR-T)
- **FR-T1** A metric's response is an ordered **ladder of tiers**, each `{ engage_at, release_at (< engage_at, hysteresis), setpoints: {actuator → level} }`. A level is a **fan percentage**, a **switch on/off**, or a cover position.
- **FR-T2** The controller drives every actuator to the setpoint of the **highest tier whose `engage_at` the aggregated metric exceeds**; below tier-1's release → all referenced actuators off.
- **FR-T3 Ramp-down hysteresis:** a tier disengages only when the metric drops below its `release_at`; control then falls to the next-lower tier. Prevents flapping at boundaries (default `release_at` ≈ engage_at − 15%).
- **FR-T4** Min on/off + settle (FR-L5) and the override window (FR-L7/L7b) apply per actuator across tier transitions (no thrash on rapid PM swings).
- **FR-T5** Event-driven (sensor updates) + periodic re-evaluation, so the ladder tracks the pollutant **up and down** automatically.

### 8.3 Pollutant-aware actuators (revises FR-C8)
- **FR-P4** Each actuator declares the **mechanism(s)** it provides → which pollutants it reduces:
  - **filter** (recirculating HEPA / air purifier — NEW mechanism): removes **PM** (+ VOC/odor); **nothing for CO₂** (no air exchange).
  - **exhaust / range hood:** removes **PM and CO₂** (extraction + dilution); depressurizes (CAZ / infiltration caveats, FR-G).
  - **balanced (ERV) / supply:** removes **CO₂**; for **PM** it *imports* outdoor PM unless filtered (net = f(outdoor PM, `filter_efficiency`)).
  - **window:** dilutes both; fully gated on outdoor AQ.
- **FR-P5 (revises FR-C8):** the purifier guard is now **pollutant-aware** — a recirculating purifier is **rejected for a CO₂ metric** but **first-class for a PM metric**. An actuator is only offered/used for metrics its mechanism can actually reduce.
- **FR-P6 PM preference + safety:** for PM, prefer **filtration** (purifiers — no outdoor-air import) over **exhaust** (depressurizes → pulls unfiltered outdoor PM through the leaky envelope). Exhaust for PM is **gated on outdoor PM** (never exhaust into worse outdoor air). The MCAS/allergy household makes this a **health priority**, not just efficiency (see §0.4 / household IAQ profile). CAZ net-exhaust + radon caps (FR-G) still bound total exhaust.

### 8.4 Actuators: variable drive + groups
- **FR-P7 Variable drive (promotes FR-L4 to required):** a fan actuator is driven to a **percentage** per tier (quantized to the fan's `percentage_step`); switches on/off; covers to a position. Reuses the v1.1 `on_speed_pct` plumbing, generalized to per-tier setpoints.
- **FR-P8 Multi-entity actuators / groups:** one actuator may target **several entities of the same domain** (e.g. a group of air purifiers) driven to the tier setpoint together — or point at an HA fan-group/group helper.

### 8.5 Canonical acceptance scenario — Kitchen PM
Space "Kitchen", metric = **max(`sensor.kitchen_pm1`, `sensor.kitchen_pm2_5`)** (µg/m³). Ladder:

| Tier | Engage > | Release < | Kitchen Range Hood | Air-purifier group | Mud Room exhaust | Lower Powder exhaust |
|---|---|---|---|---|---|---|
| 1 | 30 | ~25 | 20% | 33% | — | — |
| 2 | 50 | ~42 | 40% | 66% | — | — |
| 3 | 80 | ~68 | 100% | 100% | ON | ON |

Below tier-1 release → all four off. As PM falls past each release threshold, Aeolus steps down automatically. (Release values illustrative; configurable.)

### 8.6 Open design decisions (to resolve before build)
1. **Tier ladder home:** per-Space metric (recommended) vs a reusable shared "Policy" object.
2. **Groups:** Aeolus multi-entity actuator (recommended) vs require an HA fan-group helper.
3. **Tier-config UX:** a real per-tier × per-actuator setpoint editor in the config flow (resurrects the deferred influence-row UI) vs a YAML/import path for complex ladders.
4. **CO₂ unification:** refactor the shipped CO₂ target/high onto the same staircase engine (recommended — one controller) vs keep CO₂ on its 2-level path and add tiers only for PM.
5. **Cross-metric arbitration:** when one actuator is wanted by two metrics (e.g. hood for both CO₂ and PM) at different levels, take the **max** setpoint (recommended).

### 8.7 Build phasing (proposed)
- **v3.0-α:** generalized metric (PM/AQI kinds + max aggregation); pollutant-aware `filter` mechanism + relaxed FR-C8; per-actuator variable % drive.
- **v3.0-β:** tier-ladder engine (staircase + hysteresis) + multi-entity actuators; the Kitchen scenario end-to-end.
- **v3.0:** tier config-flow UI; PM-aware safety (filtration preference, exhaust outdoor-PM gating); full tests + acceptance scenario; spec finalized (drop "draft").

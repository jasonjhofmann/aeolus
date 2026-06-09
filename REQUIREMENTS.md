# Aeolus — Adaptive Air-Quality & Ventilation Manager for Home Assistant
**Requirements Specification — v3.2**

| | |
|---|---|
| **Status** | v1.1 **deployed & live** on the author's HA (CO₂ control across 3 spaces). **v3 (§8 — multi-pollutant, graduated ventilation) is BUILT & tested (75 tests, `mypy --strict` clean): generalized metrics, the staircase tier engine, multi-entity actuators, PM-aware safety, and the config-flow tier editor — committed & migration-safe, NOT yet deployed. KNOWN GAP (§8.8): the *control engine* is multi-metric but the *entity/control/status surface* is still CO₂-only — a PM-managed Space exposes no PM sensor/control and `attention` can't even see a PM exceedance. Resolution specified as FR-E5–E9 (per-metric parity); not yet built.** **v4 (§9 — humidity & moisture management) is SPECIFIED at design stage — PLANNED, not built. Primary job: run bathroom exhaust fans when a bath gets very humid (shower steam), reusing the live CO₂→exhaust + re-arm path. Surrounding scaffolding: absolute-humidity physics, a `dehumidify` mechanism + monsoon sign-gate, ERV latent-recovery attenuation, and an over-dry cross-metric veto.** |
| **Build target** | HA Integration Quality Scale — **Silver** |
| **Architected for** | **Platinum** |
| **Domain** | `aeolus` |
| **iot_class** | `calculated` (local push) |
| **Last updated** | 2026-06-09 |

> **The name.** **Aeolus** is the Greek keeper of the winds — the figure who holds many separate winds and *releases each on demand*. That is precisely this integration: a controller that orchestrates multiple, cross-coupled air streams (ERV, exhausts, fans, windows) across rooms that share air, releasing the right one at the right time to manage **CO₂ — and, since v3/v4, particulates and humidity too**. (Verify the slug is free on `home-assistant/brands` and PyPI before first release.)

---

## Contents
- **§0** Nature & positioning (the CO₂-filtration correction · the household IAQ priority) · **§1** Physical model (mass balance, MIMO) · **§2** Domain model & terminology
- **§3** Functional requirements — 3.1 config · 3.2 measurement/EMA · 3.3 slope & estimation · 3.4 cross-space coupling · 3.5 control/arbitration · 3.6 safety & guardrails · 3.7 entities · 3.8 services · **3.9 usability/UX**
- **§4** Canonical scenario · **§5** Quality-scale (Silver/Gold/Platinum) · **§6** Out of scope · **§7** Resolved decisions · **Appendices A–B**
- **§8** v3 — multi-pollutant graduated ventilation (incl. **8.8** the per-metric parity gap) · **§9** v4 — humidity & moisture management (PLANNED)

---

## 0. Nature, positioning, and a correctness warning that reshapes the design
- **0.1** Aeolus is a **calculated/local-push helper integration** (`iot_class: calculated`). It owns no hardware or cloud; it composes existing HA entities. Auth/reauth quality rules are therefore **exempt**.
- **0.2** It is the air-quality sibling of Versatile Thermostat, but with a real **building-physics model** and **multi-zone (MIMO) shared-air coupling**, which VT does not have.
- **0.3 — Critical domain correction (enforced in config, not just docs):** **CO₂ is a gas removed only by *air exchange* (ventilation/dilution), never by filtration.** HEPA, activated carbon (at room loadings), PCO, and ionizers do **not** reduce CO₂. The integration must **reject or hard-warn** when a recirculating air purifier is selected as a CO₂ actuator. Valid actuators move *outdoor* air in/out or move air *between zones of differing CO₂*. Encoded as FR-C8.
- **0.4 — Household IAQ priority (this deployment; see [[household-iaq-health-profile]]).** The reference home is an **allergy/MCAS household** (occupant with Mast Cell Activation Syndrome + eczema; both occupants severe allergies) with a **leaky envelope** (sliding glass doors). Consequences that override the generic design:
  - **Allergen/PM protection is co-primary with CO₂ — never trade one for the other.** Importing outdoor air to cut CO₂ must not raise the indoor PM/pollen/VOC load. The outdoor-AQ veto (FR-G3) is therefore a *first-class objective at a low threshold*, not a wildfire-only guardrail.
  - **Depressurizing (exhaust-dominant) strategies are health-penalized, not just energy-penalized:** with leaky doors, any net depressurization pulls **unfiltered** outdoor allergens straight through the envelope. So **prefer the balanced ERV over exhaust** — but for the *pressure* reason (it doesn't force infiltration), **NOT** because it filters (it barely does — see below). Down-weight exhaust/induced strategies (FR-L2 cost) even though there is *no* combustion-backdraft risk (see §7 #5).
  - **The ERV is itself a PM-import path (corrected v2.4–2.5).** The installed unit is a **Broan ERV110T** (discontinued). It DOES have filters — **2× washable 30-PPI foam pre-filters** (part `BRNS99010264`, one per air stream) — but foam is a **coarse / core-protection** medium (~MERV 1–4): it catches lint/large dust/insects and *some* large pollen (10–100 µm), but is **negligible for fine PM2.5/smoke**. So for the fine-PM veto its `filter_efficiency` ≈ 0 and the ERV is gated at the **same strict outdoor-PM threshold as unfiltered infiltration** (marginal large-pollen credit only). To earn a relaxed threshold: (a) add an **external inline MERV-13+ filter box on the fresh-air supply** (mind static pressure — ERV blowers are low-static; HEPA likely needs a booster); or (b) rely on the room HEPA purifiers to clean up the imported PM (next bullet). *Maintenance coupling: a clogged foam filter chokes ERV airflow → rinse periodically; Aeolus should not assume rated CFM if the filter is dirty.*
  - **Cooperate with the air purifiers, don't fight them:** purifiers remove PM (not CO₂); Aeolus removes CO₂ (not PM). Model the ERV's net PM impact as *outdoor PM (at its intake sensor) minus the room purifiers' cleanup headroom (CADR)* — a moderate-PM day is acceptable only if the purifiers have capacity to absorb the imported load.
  - **Humidity (drives §9) — primary job = bathroom exhaust on shower steam.** The everyday case is concrete: a bathroom gets very humid during/after a shower → run its exhaust fan until it clears (the humidity twin of the live CO₂→exhaust loop). Around that, humidity is **two-sided and health-critical** here: *High* RH (>~60%) grows **mold and dust mites** — both direct MCAS/allergen triggers — so it is co-primary with PM/CO₂, not a comfort nicety; *Low* RH (<~30%) cracks the eczema occupant's skin and irritates mucosa, so over-drying is itself a **health** failure. The home is in a **desert (Las Vegas)**: outdoor air is dry most of the year, so bathroom exhaust reliably dehumidifies **and** whole-house ventilation is a strong over-drying hazard — the already-shipped CO₂ ventilation, run here, *dries the house*, so humidity also **retro-constrains existing ventilation** (the over-dry veto, FR-H6). The monsoon (Jul–Sep) flips the sign: outdoor air becomes humid and exhaust then *imports* moisture, so a non-ventilating `dehumidify` path (FR-H4) is required for those days.

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
- **FR-C10 (advanced-feature gating)** A manager **options flow** carries opt-in toggles for power-user features that would otherwise clutter the common path. First flag: **`enable_ladders`** (default **off**) — only when on does the Space flow expose the graduated PM/AQI tier-ladder wizard (`add_graduated` → metric → tier steps, FR-P/FR-T). Off keeps Space configuration to the simple CO₂ case. Toggling the flag is **non-destructive**: ladders already authored on a Space keep running and are carried forward on reconfigure; they simply can't be re-authored until the flag is on again. The flag changes only config-flow rendering, so flipping it does **not** reload the entry.

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
- **FR-L6** **Space mode (master):** `manage` / `monitor-only` / `off` — governs whether Aeolus may command this space's actuators at all (the single `select` in the Configuration card). **Per-metric gating (FR-E9):** within a `manage` space driving >1 metric, each metric may independently be **manage** (contributes actuator demand) or **monitor-only** (computed + surfaced, no demand). Because **actuators are shared across a space's metrics** (the bath exhaust serves CO₂ *and* humidity; the range hood serves CO₂ *and* PM), gating a metric to monitor-only **removes its demand from the max-setpoint arbitration** (§8 / FR-P open-decision 5) — it does **not** force a specific actuator off, since another metric may still want it. Space `off`/`monitor-only` overrides all per-metric gates.
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
- **FR-E2** Per space, **per metric** (CO₂/PM/AQI/humidity — see FR-E5): a primary `sensor` for that metric's smoothed value (correct `device-class`/unit per kind) carrying the metric-appropriate attributes — for CO₂: `ema_co2`, `co2_slope(_per_hour)`, `effective_ach`, `equilibrium_co2`, `time_to_target`; for PM/AQI: raw level + slope/trend (no ACH — §8.3 FR-P3); for humidity: absolute humidity/dewpoint (§9.2). Plus a per-space `status` (ok/elevated/high/mitigating/diverging/unreachable/overridden/stale) that **names the driving metric(s)**, `active_actuators`, `target`/band, `mode`, `estimated_occupancy`. Plus `binary_sensor` `mitigation_active` and `attention` (FR-E6). *(As-built v1/v3 surfaces only the **primary (CO₂)** metric — see the §8.8 parity gap; FR-E5–E9 bring the rest to parity.)*
- **FR-E3** Control entities: `number` (CO₂ target) + **a threshold/engage control per other driven metric** (FR-E7), `select` (mode), `switch` (master enable). All `has-entity-name`, `entity-unique-id`, `entity-device-class`, `entity-category`, sensible `entity-disabled-by-default` for advanced diagnostics, full `entity-translations`/`icon-translations` (Gold).
- **FR-E4** Diagnostic entities: per-(actuator,space) identified gain, last decay-test results, per-sensor freshness, controllability flags.
- **FR-E5 Per-metric sensor parity (co-existence).** A Space exposes a **value (and where meaningful, slope) sensor for *every* metric it is configured with**, not only the primary/CO₂ one — each with the correct `device_class`/unit (`pm25`/`pm10` µg/m³, `aqi`, `humidity` %). A PM- or humidity-managed Space whose only entities are CO₂ value/slope/ACH is **non-conformant** (the observed Primary Bedroom gap, §8.8). ACH/`effective_ach` is **CO₂-only** and must not be emitted for, or implied of, other metrics.
- **FR-E6 Metric-attributed status (co-existence + correctness).** `mitigation_active` reflects mitigation for **any** metric and exposes **which** metric(s) are driving (attribute and/or per-metric child sensors); `attention` is raised by an exceedance/divergence/staleness of **any** driven metric, not CO₂ alone. *(Correctness, not cosmetics: an `attention`/`status` computed solely from CO₂ thresholds cannot flag a PM or humidity problem — a silently-missed hazard for an MCAS household, §0.4.)* Activity-log/state-change text should name the pollutant ("PM2.5 mitigation active") rather than a bare "Mitigation active".
- **FR-E7 Per-metric control parity.** Each non-CO₂ driven metric gets a control surface symmetric to the CO₂ `target` number — at minimum its tier-1 `engage_at` threshold as a `number` (correct device-class/unit) — so PM/AQI/humidity setpoints are adjustable from the device card, not buried only in the config-flow tier ladder. `entity-disabled-by-default` is acceptable for advanced per-tier knobs.
- **FR-E8 Symmetric naming.** No metric is privileged in entity naming: a CO₂ Space's value sensor isn't generically "<Space>" while PM is absent — either all metric sensors are suffixed by kind ("<Space> CO₂", "<Space> PM2.5", "<Space> Humidity") or the unsuffixed primary is clearly the configured primary and all others are present and named. Translation keys are per-kind.
- **FR-E9 Management control: one master select, not a dropdown per pollutant.** The Space `select` Mode (`manage`/`monitor`/`off`, FR-E3) stays the **single master** in the Configuration card — there is **no** per-pollutant mode dropdown. For finer control, each non-trivial metric gets an **advanced, `entity-disabled-by-default` `switch` "Manage <metric>"** (e.g. *Manage PM2.5*, *Manage Humidity*) implementing the FR-L6 per-metric gate. *Rationale:* a full manage/monitor/off **dropdown per pollutant** would clutter the common single-CO₂ card and duplicate the master, and a per-metric `off`-vs-`monitor` distinction is redundant once a metric is configured — the actual need is the binary "does this pollutant drive actuators." Surface the per-metric toggle only when a space has >1 metric and is in `manage`; consistent with the FR-C10 advanced-gating philosophy (keep the common path clean).

### 3.8 Services / actions
- **FR-A1** `aeolus.set_target`, `set_mode`, `force_strategy` (manual actuator-set + duration; also runs a deliberate decay test for calibration), `recalibrate`/`reset_gains`.
- **FR-A2** Registered in `async_setup` (`action-setup`), documented (`docs-actions`), raising **translated** typed exceptions (`action-exceptions`, `exception-translations`).

### 3.9 Usability / UX (FR-U)
*Consolidates UX intent otherwise scattered across FR-C10 (advanced gating), FR-E6/E8 (attribution/naming), §9's "primary objective," and the Gold docs/repair rules — and adds the missing **explainability** requirement (FR-U2), the class of gap repeatedly surfaced by inspecting live device cards.*
- **FR-U1 Progressive disclosure (simple default path).** The default "add a Space" flow is the **simple CO₂ case** — pick CO₂ sensor(s), set a target, done — with **no** tiers, influence rows, or physics on screen. All power-user surface (graduated ladders FR-C10, per-tier setpoints, induced influence rows, per-metric *Manage* toggles FR-E9) is opt-in / `disabled-by-default` and appears only once enabled or once a Space has >1 metric. A first-timer must reach the live "ventilate on high CO₂" loop **without meeting** MIMO/tier/veto concepts. (§9's bath-exhaust "primary objective" is this same principle applied to humidity.)
- **FR-U2 Explainability — surface *why* the current action (NEW).** Aeolus makes non-obvious choices (which actuator, which metric, and especially **why a fan is _off_ while a pollutant reads high**), so it must explain itself. Expose a per-Space plain-language **`reason`** (attribute and/or diagnostic sensor): the driving metric + tier ("PM2.5 tier 2"), the active actuator(s) — or, when **idle despite demand**, the blocking cause: "outdoor-AQ veto," "over-dry veto," "unreachable target," "manual override — yielding 22 min," "stale sensor," "below engage threshold." This replaces today's cryptic "Mitigation active cleared (no running detected)" with an actionable statement. Cross-refs FR-E6 (metric attribution), FR-G2/G3/H6 (vetoes), FR-L7 (override).
- **FR-U3 Coherent device page + recommended dashboard.** The per-Space device page (FR-E1) reads coherently unaided — value · status · *why* · controls, grouped sensibly — and the docs ship a **recommended Lovelace example** (Gold `docs-examples`) giving an at-a-glance multi-metric view (every driven pollutant, its state, the active strategy) with **no metric hidden** (FR-E5/E8), so the user isn't left hand-building it.
- **FR-U4 User-facing alerting for blocking/abnormal states.** Conditions where Aeolus *wants* to act but **cannot**, or needs the human, surface as HA **repair issues / persistent notifications** (Gold `repair-issues`) naming **Space + cause + user action** — not just a buried attribute: outdoor-AQ veto blocking needed ventilation, unreachable target, uncontrollable space, stale-sensor-stranded Space, HEPA-selected-for-CO₂, and (humidity) over-dry-veto / condensation-risk.
- **FR-U5 Legible naming, units, precision, icons.** Per-metric entities carry correct device-class/unit (FR-E8) + sensible display precision per kind (CO₂ 1 ppm · PM 1 µg/m³ · RH 1 % · slope 2 dp) and **per-kind icons** so a glance separates CO₂/PM/humidity; all status/option strings are translated and human-readable ("Manage (control actuators)"), never raw enum values.

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
Temperature/HVAC control (pairs with Versatile Thermostat) · airflow/pressure *measurement* (inferred only) · code-compliance certification · CO (carbon-monoxide) life-safety detection · sorbent/biological CO₂ capture (negligible at room scale) · **active humidification** (adding moisture) — Aeolus *extracts/dilutes* moisture and *vetoes* over-drying but does not run a humidifier; HA's `humidifier` domain + `generic_hygrostat` already cover that and Aeolus complements rather than duplicates them (§9.6; one open decision is whether to *command* an existing humidifier as a low-RH actuator).

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

**Status:** BUILT & tested (2026-06-06) — in the repo, migration-safe, **not yet deployed**. Expands Aeolus from single-pollutant (CO₂), essentially on/off control to **multi-pollutant, multi-tier (graduated) ventilation + filtration**. The CO₂ control already shipped is now the 2-tier special case of the general staircase controller.

### 8.1 Pollutants / metrics (FR-P)
- **FR-P1** A Space may be driven by one or more **metrics**, each `(kind, sensor(s), aggregation)` where kind ∈ `co2 | pm1 | pm2_5 | pm10 | aqi | generic` (any numeric sensor) — plus **`humidity`** (§9, planned; the only **two-sided** kind, with its own physics). Aggregation reuses mean/median/min/**max**; **max = "if ANY listed sensor exceeds"** (the canonical example uses max of two PM sensors).
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

### 8.7 Build phasing — DONE
- ✅ **v3.0-α:** generalized metric (PM/AQI kinds + max aggregation); pollutant-aware `filter` mechanism; per-actuator variable % drive; backward-compat migration parser.
- ✅ **v3.0-β:** per-metric staircase engine (engage/release hysteresis) + multi-entity actuators; the Kitchen scenario end-to-end (`test_tier_ladder`).
- ✅ **v3.0:** config-flow metric→tier wizard (`test_tier_config_flow`); PM-aware safety = capability gate (filter ≠ CO₂, FR-P5) + outdoor-PM exhaust veto (FR-G3); 75 tests, `mypy --strict` clean; spec finalized.
- **Deferred:** induced/pressure edges (FR-X3) not yet wired into the staircase (helper retained + unit-tested); a tier-editor that round-trips *edits* of an existing ladder field-by-field (today: re-author replaces); **per-metric entity/control/status parity (§8.8 — now REQUIRED, was filed here as "optional per-PM sensors"; the live PM-on-Primary-Bedroom gap reclassifies it as a conformance defect, not a nicety).**

### 8.8 Per-metric entity, control & status parity (co-existence) — observed gap
**The engine is multi-metric; the entity/control/status surface is not.** `SpaceRuntime` holds one `MetricRuntime` per metric (own EMA/slope/tier), and the staircase already drives PM and CO₂ together — but `ema_ppm`/`slope`/`status`/`mitigating` are exposed only for the **primary (CO₂)** metric, by explicit design ("so the existing CO₂ sensor + slope/ACH entities keep working unchanged"). Consequences, **observed live on the Primary Bedroom** (CO₂ **and** PM mitigation configured; PM has run ≥ once):
- **Sensors are CO₂-only** — Air-change rate, "CO₂ slope", and "<Space>" (= CO₂ ppm). No PM value/slope sensor exists, so a PM mitigation that ran is **invisible** on the device.
- **Controls are CO₂-only** — just "Target CO₂"; the PM engage thresholds live solely in the config-flow tier ladder, unreachable from the device card.
- **Status doesn't attribute the metric and can't see PM** — "Mitigation active" / "Attention" are space-wide and `attention` is computed purely from CO₂ ppm/target/high/slope, so **a PM exceedance cannot raise attention** (a silently-missed hazard, not just a label gap). Activity-log text is a bare "Mitigation/Attention," never "PM2.5 …".

**Resolution = FR-E5–E9** (per-metric sensors, metric-attributed + all-metric status, per-metric controls, symmetric naming, and per-metric management gating via a master Mode select + advanced per-metric "Manage <metric>" toggles — *not* a mode dropdown per pollutant, FR-E9). This is the §8 **co-existence** requirement: when a Space manages CO₂ + PM (+ soon humidity, §9), each metric must be **first-class and co-equal** in entities, controls, status, and activity — no CO₂-privileged surface. **Acceptance:** configure the Primary Bedroom's PM metric → a `sensor.primary_bedroom_pm2_5` (+ slope) appears, a PM engage-threshold `number` appears, `attention` trips on a PM exceedance and names PM, and the activity log reads "PM2.5 mitigation active." **§9 humidity inherits FR-E5–E9 by construction** — the bath-exhaust feature must surface a humidity sensor + humidity-attributed status, not actuate invisibly the way PM does today.

---

## 9. v4 Scope expansion — Humidity & moisture management (PLANNED)

**Status:** SPECIFIED at design stage (2026-06-08) — **NOT built**.

> **Primary objective (the must-ship job).** **When a bathroom gets very humid — i.e. someone showers — run that bathroom's exhaust fan until the steam clears.** This is the everyday case and the reason §9 exists. It is the direct humidity twin of the CO₂→exhaust loop already live on the Primary Bedroom fan: a high-side threshold on a Space's humidity metric drives the **same bath-fan actuator**, held through the long dry-down by the **re-arm** plumbing (FR-L5b) that already solved the Savant hardware-auto-off problem. Everything else in §9 — absolute-humidity physics, the `dehumidify` path, the monsoon sign-flip, the over-dry veto — is **correctness scaffolding and later refinement around that one job**, and must not delay or complicate it. A first deployable slice is essentially "humidity metric + high threshold + exhaust on/off + re-arm," shippable in the same shape as today's CO₂ control.

The deeper model below makes that simple loop *correct* in the cases where naïve "RH high → exhaust" would be wrong (humid days, over-drying, RH-vs-temperature confusion). For the reference home humidity is also a **health** feature, not comfort (§0.4): high RH amplifies mold/dust-mite allergens (MCAS), low RH cracks eczema, and — second-order — the desert climate means the CO₂ ventilation already shipped *over-dries the house*, so §9 also retro-constrains §3.5/§8 control.

### 9.0 Where the simple loop needs guardrails (why humidity isn't *only* a §8 metric)
The bath-exhaust job is simple; three physics facts keep it honest, and only the first two touch the primary case:
1. **Ventilation moves *absolute* humidity, not RH.** RH is temperature-dependent; what air exchange transports is **water-vapor mass**. Triggering purely on RH can misfire (a zone can cross an RH threshold from a temperature change with no moisture change). Aeolus derives `(RH, T) → absolute humidity / dewpoint` indoor **and** outdoor and reasons on vapor mass. *For the everyday steamy-bathroom case this is mostly belt-and-suspenders — a post-shower bath is unambiguously humid on any metric — but it prevents false trips and is required to get the next point right.*
2. **The floor is the *outdoor* absolute humidity, which swings sign.** Exhausting a bathroom dehumidifies **only** when outdoor absolute humidity `W_out` < indoor `W`. In the **desert this is true nearly always**, so the simple loop just works — but the **monsoon (Jul–Sep) flips it**, and on those days raw exhaust would pull *more* humid air in. The sign gate (R-PHYS-H1) catches that and hands off to a non-ventilating **`dehumidify`** path (FR-H4). This is parallel to the CO₂-out floor and the PM-import veto.
3. **Two-sided objective (secondary).** Beyond bathrooms, both **high** RH (mold/dust-mites/MCAS) and **low** RH (eczema cracking, irritation, static) are harmful, so whole-house humidity has a **high mitigation ladder** *and* a **low constraint** (the over-dry veto, FR-H6). Ventilation can only push a zone *toward* outdoor moisture, so the low side is a **veto/penalty**, never an actuator demand (you can't ventilate moisture *in*). This matters for the desert over-drying problem but is **not** part of the bath-exhaust MVP.

### 9.1 Physics — moisture mass balance (extends §1)
Same single-zone form as §1.1 with **water vapor** as the transported species:
```
V·dW/dt = G_w(t) + Q·W_out − Q·W,   W ≡ absolute humidity (vapor mass / volume)
⇒ dW/dt = G_w/V − λ·(W − W_out),     λ ≡ Q/V (the same air-change rate)
```
- **`W`, `W_out`** — indoor / outdoor absolute humidity, derived from `(RH, T)` via Magnus/Tetens (dewpoint → saturation vapor pressure → g/m³). `W_out` is the asymptotic floor and, unlike CO₂'s ~constant `C_out`, is **time-varying** from the outdoor RH+T sensor.
- **`G_w`** — moisture generation: showers/baths (the dominant transient), cooking, occupant respiration+perspiration (~tens of g/h per person), unvented appliances, plants. The disturbance.
- **`λ`** — the **same** air-change rate actuators already modify for CO₂; one ventilation action moves CO₂, PM, *and* moisture simultaneously (the basis for cross-metric coupling, §9.4).
- **R-PHYS-H1 (sign gate).** The dehumidifying benefit of ventilation is `∝ (W − W_out)` and is **negative when outdoor is more humid** (ventilation then humidifies). Aeolus must gate ventilation-for-humidity on `sign(W − W_out)` and **never assume outside is drier** — the same class of guardrail as the outdoor-AQ veto (Appendix A-b).
- **R-PHYS-H2 (RH for UX, AH for control).** Thresholds are authored and displayed in **RH%** (what users and health guidance speak), but engage/release comparisons and the sign gate operate on **absolute humidity / dewpoint**. Surface both.

### 9.2 Humidity metric (FR-H1–FR-H3 — extends FR-P)
- **FR-H1** New metric kind **`humidity`** (RH %). It **requires a co-located temperature source** (per-sensor `T`, or a Space temperature sensor) so the engine can derive absolute humidity/dewpoint; reject configuration of a humidity metric without one (`test-before-configure`, FR-C6). Member aggregation reuses mean/median/min/**max** (max = "if any sensor reads high").
- **FR-H2 Derived surfaces.** Expose per Space: `absolute_humidity` (g/m³), `dewpoint`, the outdoor counterparts (`outdoor_absolute_humidity`, `outdoor_dewpoint`), and the control variable `delta_w = W_indoor − W_out` (sign = whether ventilation can help). Plus a humidity `status` (dry / ok / humid / mitigating / import-blocked).
- **FR-H3 Two-sided band.** A humidity metric carries a target **band** `[rh_low, rh_high]` (defaults **~30 %–55 %** for this MCAS/eczema household; configurable) plus optional escalation thresholds above `rh_high`. The **high** side drives mitigation ladders (§9.4); the **low** side is a **constraint/veto** on drying ventilation across *all* metrics (FR-H6), **not** an actuator demand.

### 9.3 Actuators & moisture mechanisms (extends FR-P4 / `MECHANISM_REDUCES`)
Each actuator's effect on humidity is declared by its mechanism:
- **FR-H4 `dehumidify` (NEW mechanism).** A standalone dehumidifier, or an AC/heat-pump operating in a dehumidify/dry mode: removes water by **condensation with no air exchange** → **no outdoor import, NOT gated on outdoor AH/AQ**, works regardless of the weather sign. It is the **humidity analog of the recirculating `filter`** mechanism for PM (and, like `filter`, does **nothing for CO₂**). First-class high-RH actuator and the **only** option when outdoor air can't help (humid climate / monsoon). Carries a compressor **energy cost** for arbitration (FR-L2), like exhaust enthalpy.
- **`exhaust` / range hood / bath fan.** Extracts humid indoor air; net dehumidification is **conditional on `W_out < W`** (the **FR-H7** sign gate, R-PHYS-H1) and still **depressurizes** (FR-G allergen/CAZ caveats). The **bath exhaust is the canonical shower-moisture actuator** and couples with the existing re-arm plumbing (FR-L5b) for the long post-shower runtime.
- **FR-H5 `balanced` ERV / `supply` — latent-recovery attenuation.** An **ERV recovers latent heat → partially recovers moisture**, so its humidity influence is **attenuated** by a new per-actuator **`latent_recovery_efficiency`** (0 = HRV / sensible-only, full moisture exchange … ~0.5–0.6 = the installed Broan **ERV110T** enthalpy core … →1 = no moisture exchange). Net moisture move = `(1 − latent_recovery_efficiency) × (W_out − W_indoor)`. This is the **direct moisture analog of PM `filter_efficiency`** (FR-C4): it *both* weakens the ERV's dehumidifying power on a dry day *and* limits how much moisture it imports on a humid one — physically correct and the reason an ERV is gentler on humidity than a bare exhaust+infiltration pair.
- **`window`.** Dilutes toward outdoor AH; **gated on outdoor AH (over-humidify) and outdoor AQ** (FR-G3) together.
- **`filter` (recirculating purifier).** **Nothing for humidity** — capability-gated out, exactly as it is for CO₂ (FR-P5). The `MECHANISM_REDUCES` table gains a `humidity` column: `dehumidify ✓`, `exhaust ✓ (sign-gated)`, `balanced/supply ✓ (latent-attenuated, sign-gated)`, `window ✓ (gated)`, `filter ✗`.
- **FR-H7 Capability + sign gate.** An outdoor-air mechanism is only **offered** for high-RH mitigation when `W_out < W` (R-PHYS-H1); when outside is more humid, only `dehumidify` actuators are eligible for the humidity metric, and ventilation wanted by *other* metrics inherits a moisture-import cost (§9.4).

### 9.4 Control — bidirectional & cross-metric (extends §3.5 / §8.2)
- **FR-H8 High ladder (the primary objective).** Reuse the §8 staircase on the humidity metric: as indoor RH (and AH) exceed `engage_at`, drive the **bathroom exhaust** — the headline shower-steam case — with ramp-down hysteresis per FR-T3 (default `release_at ≈ engage_at − 15 %`) and the re-arm (FR-L5b) holding it through dry-down. The **simplest valid ladder is a single high tier: RH > threshold → exhaust on** (the MVP, §9.9). Richer ladders may add `dehumidify` first and sign-gated `exhaust`/ERV behind it, but a bare bath-exhaust threshold is a complete, shippable degenerate case.
- **FR-H6 Over-dry veto (the key cross-metric coupling — health, §0.4).** When indoor RH ≤ `rh_low`, **veto or strongly down-weight drying ventilation for *every* metric — including CO₂ and PM-by-ventilation.** In a desert this is the constraint that actually governs winter operation: below the RH floor, Aeolus must prefer **non-drying** CO₂/PM strategies (transfer fans between zones, `filter` for PM, or simply accepting a higher CO₂ setpoint) over outdoor-air dilution, and must **surface the trade-off** rather than silently over-dry. Symmetric in spirit to the outdoor-AQ veto (FR-G3) and the radon veto (FR-G2): *never trade one health hazard for another* (Appendix A-b).
- **FR-H9 Condensation / mold guard.** If indoor **dewpoint ≥ (coldest tracked surface temperature − margin)** — cold window glass or an exterior wall in winter — bias toward **dehumidification even when bulk RH is mid-band**, because local condensation seeds mold. Surface temperature is an **optional** sensor; absent one, use **outdoor T as a winter proxy** for the worst cold surface. Emit a repair/attention signal when sustained.
- **FR-H10 Cross-metric arbitration (extends FR-L2).** Every ventilation action now carries a **moisture term** (benefit or cost) in the arbitration cost alongside energy/enthalpy, depressurization, and outdoor-AQ risk. When CO₂ wants ventilation but it would breach `rh_low` (over-dry) **or** import moisture on a humid day, arbitration weighs that explicitly. The §8 **max-setpoint** rule (open-decision 5) still applies when two metrics want the *same* actuator in the *same* direction; the **new case** is when they want it in *opposite* directions (CO₂ says ventilate, humidity says don't) — resolved by the veto/penalty, with the loser's unmet demand surfaced as `attention`.

### 9.5 Safety & household priority (extends §0.4 / §3.6)
- **High RH (>~60 % sustained)** = mold + dust-mite amplification = **direct MCAS/allergen trigger** → co-primary with PM/CO₂ for this home, not comfort.
- **Low RH (<~30 %)** = eczema cracking (the MCAS occupant) + mucosal/respiratory irritation + static → the **over-dry veto (FR-H6) is a health guardrail**, not an efficiency nicety.
- **Moisture-spike events** (shower, bath, cooking) are the most common high-RH transients → **fast exhaust response**, with the bath-fan re-arm (FR-L5b) covering the long dry-down.
- **Bounded by the same exhaust guardrails:** dehumidifying *by exhaust* still depressurizes → allergen infiltration (§0.4) + CAZ/radon caps (FR-G1/G2) still apply; this is another reason `dehumidify` (no air exchange) and the latent-attenuated ERV are preferred over raw exhaust here.

### 9.6 Out of scope (humidity)
- **Active humidification** (*adding* moisture). Aeolus is a ventilation/extraction manager: it can *veto* over-drying but will not run a humidifier. HA's `humidifier` domain + `generic_hygrostat` already own that; Aeolus **complements**, not duplicates (see §6). *(Open: optionally **command** an existing `humidifier` entity as a managed low-RH actuator — 9.7-2.)*
- Envelope/vapor-barrier remediation, crawlspace/attic moisture, and any structural moisture source control.

### 9.7 Open design decisions (resolve before build)
1. **Primary control variable:** RH vs **absolute humidity** vs **dewpoint**. *Recommend:* control on **absolute humidity/dewpoint** (correct physics + the sign gate), author/display thresholds in **RH%** (R-PHYS-H2).
2. **Low-RH actuator:** **pure veto** (recommend for v1 — keeps the "ventilation only" line clean) vs optionally **command an HA `humidifier`** as a managed actuator (richer, but crosses the scope boundary in §9.6).
3. **Condensation-guard surface temp:** dedicated surface/window sensor vs **outdoor-T proxy** vs skip the guard initially.
4. **ERV latent recovery:** a per-actuator **constant** `latent_recovery_efficiency` (recommend) vs a temperature-dependent latent-effectiveness curve (enthalpy cores vary with conditions).
5. **Controller reuse:** ride the **§8 staircase with a two-sided wrapper** (recommend — one engine, humidity high-ladder + a separate low-veto) vs a dedicated bidirectional humidity controller.

### 9.8 Canonical acceptance scenarios (reference home)
**(a) Shower moisture spike — THE headline (the primary objective).** Primary Bath RH spikes to 80 % after a shower; outdoor is dry (`W_out < W`, the desert norm). Expected: the high-RH threshold engages the **bath exhaust**, held through the long dry-down by the **re-arm** (FR-L5b), and steps off as RH falls back through `release`. This is the everyday job and the regression test §9 must pass first. **Monsoon variant:** the same spike on a humid day (`W_out > W`) — the exhaust is **sign-gated off** for dehumidification (it would import moisture) and a **`dehumidify`** actuator (FR-H4) is engaged instead. *(Until the `dehumidify`/sign-gate work lands, the MVP simply runs the exhaust on high RH — acceptable in the desert, where `W_out < W` nearly always; the monsoon refinement is a known, scheduled follow-up, not a silent gap.)*
**(b) Desert winter over-dry — the cross-metric guardrail.** Indoor CO₂ rises in a closed bedroom; outdoor air is dry (`W_out ≪ W`) so ventilation *would* cut CO₂ fast — but indoor RH is already 28 % (< `rh_low` 30 %). Expected: the **over-dry veto (FR-H6)** blocks/penalizes the ERV-for-CO₂ action, Aeolus prefers a non-drying path (zone transfer / accept a higher CO₂ band) and raises `attention` explaining the CO₂-vs-dryness trade-off — it does **not** silently dry the house to hit the CO₂ target.
**(c) Cold-window condensation.** Winter night, bulk RH a comfortable 45 % but indoor dewpoint meets the cold glass → condensation guard biases toward **dehumidify** despite the mid-band RH, averting window mold.

### 9.9 Build phasing (planned)
- **v4-MVP (the primary job — ship first):** `humidity` metric (FR-H1, `(RH,T)` derivation so triggering is moisture-correct) + a **high-RH threshold driving the bathroom `exhaust` on/off**, held by the existing **re-arm** (FR-L5b). This is the steamy-bathroom loop (9.8-a) and reuses the live CO₂→exhaust control path almost verbatim — the smallest deployable, useful slice. In the desert it is correct as-is (`W_out < W` nearly always); the sign gate is the *next* step, not a blocker. **Ships with its entity surface (FR-E5–E8): a Space humidity `sensor`, humidity-attributed `mitigation_active`/`attention`, and the RH engage-threshold `number`** — the bath-exhaust loop must be visible on the device, not invisibly actuating the way PM does today (§8.8).
- **v4-α surfaces:** outdoor `W_out` + `delta_w` + dewpoint as sensors/attributes (observe-only) to validate the physics against live sensors and prep the sign gate.
- **v4-β (sign gate + dehumidify):** wire R-PHYS-H1 so exhaust is sign-gated and the new **`dehumidify`** mechanism (FR-H4) covers humid/monsoon days; ERV **`latent_recovery_efficiency`** attenuation (FR-H5); monsoon-variant test (9.8-a).
- **v4 (cross-metric + UX):** **over-dry veto (FR-H6)** wired into the CO₂/PM ventilation arbitration (9.8-b); condensation/mold guard (9.8-c); config-flow humidity-metric wizard (band + per-sensor T + ERV latent recovery); translations, diagnostics, repair issues (over-dry-veto-active, humidity-import-blocked, condensation-risk). `mypy --strict` + tests as ever.

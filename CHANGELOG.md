# Changelog

All notable changes to the Aeolus specification are documented here. The project is in the **requirements stage** — no integration code exists yet.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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

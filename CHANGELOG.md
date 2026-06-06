# Changelog

All notable changes to the Aeolus specification are documented here. The project is in the **requirements stage** — no integration code exists yet.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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

# Changelog

All notable changes to the Aeolus specification are documented here. The project is in the **requirements stage** — no integration code exists yet.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added — Specification v2.0 (2026-06-05)
- Initial repository: `README.md`, versioned `REQUIREMENTS.md` (v2.0), `docs/SCAFFOLD.md` (structure + Quality-Scale traceability + roadmap), Apache-2.0 `LICENSE`.
- Building-physics backbone: single-zone mass balance, exponential decay toward outdoor floor, reachability condition, gap-normalized **effective ACH** as the comparison metric, MIMO `M(u)` shared-air coupling (direct / diffusive / **induced**).
- EMA/slope grounded in Versatile Thermostat's `ema.py` (time-aware α from half-life + actual Δt, `max_alpha` cap, irregular-cadence handling).
- Hard guardrails: HEPA/recirculation rejection, outdoor-AQ veto, radon-on-depressurization veto, CAZ combustion-safety caps, per-member stale-sensor safe-state, manual-override yield.
- Quality-Scale plan: build for **Silver**, architected for **Platinum**.

### Open
- Five open decisions tracked in `REQUIREMENTS.md` §7 (MVP slice, primary entity type, gain representation, `C_out` source, combustion/radon cap scope).

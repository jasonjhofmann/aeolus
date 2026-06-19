# Handoff — Aeolus: action-history enhancement + attention-status bug

**Prepared:** 2026-06-18 · **Repo:** `~/repos/aeolus` @ `62bbf81` (v0.5.5) · **For:** a follow-up session.

Two independent pieces of work surfaced while building the read-only **Aeolus
Viewer** webapp (`~/repos/aeolus-viewer`, served at `monkeyisland.local:8802`).
Both live in the **integration**, not the viewer.

1. **Issue 1 — Action history (ENHANCEMENT):** Aeolus keeps no durable record of
   the decisions it makes, so the viewer can only *reconstruct* a timeline from
   Home Assistant's recorded entity state-changes. Give Aeolus a real
   what/when/why log.
2. **Issue 2 — Attention status (BUG FIX):** every managed space reports
   `status: "attention"` while its `reason` says *"OK — all metrics within
   range,"* and the `binary_sensor.<space>_attention` flag flaps ~167×/day. The
   status logic and the reason logic disagree about what "elevated" means, and
   the attention test has no slope deadband.

Read the whole thing before starting; the two share the engine's
status/reason/explainability surface (`engine.py`), so coordinate the edits.

---

## Issue 2 — Attention-status bug (do this first; it's small and self-contained)

### Symptom (live, verified via the viewer's diagnostics feed)
All three spaces (`Primary Bedroom`, `Overall`, `Kitchen and Family Room`)
simultaneously report:
- `space_status()` → `"attention"`
- `space_reason()` → `"OK — all metrics within range"`
- `binary_sensor.<space>_attention` toggles on/off every few minutes
  (~167 transitions/24 h in HA history) even though no metric ever engages a tier.

A space whose status is "attention" while its reason says everything is fine is
self-contradictory, and the rapid flap is registry/recorder noise.

### Root cause — two coupled defects in `custom_components/aeolus/engine.py`

**Defect A — threshold mismatch between attention and reason.**
- `space_attention()` (`engine.py:741-761`) flags a metric as needing attention
  when `value > metric.tiers[0].release_at and slope >= 0` (`engine.py:759`) —
  i.e. anywhere **above the lower/release threshold** and not falling.
- `space_reason()` (`engine.py:818-829`) only calls a metric "elevated" when
  `value > metric.tiers[0].engage_at` (`engine.py:822`); otherwise it returns
  `"OK — all metrics within range"` (`engine.py:829`).

So for any value in the **hysteresis band** (`release_at < value ≤ engage_at`),
attention is True but reason says OK. This is the steady state here:
`Overall` CO₂ baseline ≈ 629 ppm sits permanently between its release (600) and
engage (700) thresholds, so it is *always* a candidate for attention.

**Defect B — no slope deadband → flapping.** The `slope >= 0` test
(`engine.py:759`) toggles on the *sign* of `slope_per_min`, which oscillates
around zero on real sensor noise. Each crossing flips attention → the 167
flaps/day. There is no deadband, no debounce, and no requirement that the metric
ever actually engaged a tier.

### Fix (recommended approach — confirm intent with Jason if unsure)
The docstring's intent (`engine.py:742-743`) is *"stale, maxed-and-still-high, or
elevated & not improving."* "Elevated" should mean the same thing everywhere, and
"not improving" shouldn't fire on noise. Concretely:

1. **Reconcile the "elevated" floor.** In `space_attention`, change the
   `release_at` comparison (`engine.py:759`) so the elevated-and-not-improving
   case keys off the **engage** threshold (consistent with `space_reason`), OR
   only applies once the metric has engaged a tier (`mrt.active_tier >= 0`) and is
   sitting in the band failing to clear. Pick one definition of "elevated" and use
   it in both methods.
2. **Add a slope deadband.** Replace `slope >= 0` with `slope > SLOPE_EPS` (e.g.
   a small positive ppm/min, define a `const.py` constant), so a flat/noisy metric
   doesn't flap. Consider also requiring the condition to persist (the engine
   already has per-metric runtime; a short debounce or "was engaged within N min"
   gate is cleaner than instantaneous slope sign).
3. **Make reason explain attention.** Add a branch to `space_reason` so that
   whenever `space_attention` is True, the reason states *why* (e.g. *"CO₂
   elevated and not clearing"*, *"sensor stale"*, *"at max tier"*) instead of
   *"OK — all metrics within range."* Status and reason must never contradict —
   that invariant is the real acceptance bar.

The two surfaces that consume these — `binary_sensor.py:101-111`
(`space_attention`) and `diagnostics.py:89` — need no change; fixing the engine
fixes them.

### Tests (add to the existing pytest suite; this repo gates 95%+)
- A metric resting in the hysteresis band with `slope ≈ 0` (and noisy ±) →
  `space_attention` is **stable False** (no flap) and `space_status` is `"ok"`,
  with `space_reason` == the OK string. (Reproduces today's bug.)
- A metric above the engage threshold and not improving → attention True **and**
  reason explains it (assert they agree).
- A stale metric → attention True + reason "stale" (regression-guard the existing
  branch).
- Boundary: exactly at `engage_at`, exactly at `release_at`.

### Acceptance criteria
- [ ] No space reports `status == "attention"` while `reason` is the OK string
      (invariant test).
- [ ] `binary_sensor.<space>_attention` is stable for a metric noisily resting in
      its band (no minute-scale flapping).
- [ ] CHANGELOG + quality_scale unchanged-or-updated; full suite green; ruff/mypy
      clean (this repo is Platinum, strict-typed — see `pyproject.toml`).

---

## Issue 1 — Action-history enhancement

### Goal
Give Aeolus a durable, queryable record of the decisions it takes — **what**
action, **when**, and **why** — so consumers (the viewer, the logbook, future
automations) show real history instead of reconstructing it. Today the viewer's
Activity tab infers a timeline from HA's recorded `binary_sensor.*_mitigation_active`
and the actuators' controlled-entity on/off history, and explicitly labels itself
as reconstructed.

### Current state (verified)
- **No events, no logbook, no decision log.** `grep` for
  `bus.async_fire` / `async_describe_event` / `logbook` across
  `custom_components/aeolus/*.py` → nothing.
- Reasoning exists only as **live entity attributes** (`sensor.<space>_status_reason`,
  `binary_sensor.<space>_mitigation_active.reason`, etc.) and **`_LOGGER.info`
  lines** that land in journald (not the recorder, not the logbook).
- The decision/command sites that should emit a history event:
  - **Actuator on/off command** — `engine.py:476-488`. The on/off transition is
    computed at `engine.py:477-487` (`crossing_on`/`crossing_off`) right before
    `self._send_command(act, setpoint, now)` (`engine.py:488`). This is the
    primary "action taken" hook; the surrounding context knows the actuator,
    setpoint, and (via `space_reason`/driving metric+tier) the why.
  - **Manual override detected** — `engine.py:417`.
  - **Override grace confirmed** — `engine.py:569`.
  - **Source available/unavailable** — `engine.py:595`.
  - **Outdoor-AQ veto engage/clear** — `controller.py:87` / `controller.py:92`.
  - **Max-runtime cap forcing off** — `controller.py:106`.

### Proposed design (recommend BOTH layers; discuss scope with Jason)
1. **Fire a structured HA event on each decision** —
   `hass.bus.async_fire("aeolus_action", {...})` at the sites above. Durable
   (lands in the recorder/logbook), standard, and consumable by automations and
   the viewer via `/api/logbook` or `/api/history`. Suggested payload:
   ```
   {
     "action": "actuator_on" | "actuator_off" | "veto_engaged" | "veto_cleared"
               | "override_started" | "runtime_capped" | "source_unavailable" | ...,
     "actuator_id": "<subentry_id>", "actuator_name": "...",
     "space_id": "<subentry_id>", "space_name": "...",
     "setpoint": 0..100,
     "metric": "co2" | "pm2_5" | ..., "tier": int | null,
     "reason": "<space_reason()-style string>",
     "ts": "<iso8601>"
   }
   ```
   Add an `async_describe_events` logbook hook so these render nicely in HA's
   own Logbook too (this is the FR-U2 explainability surface, extended).
2. **Keep a bounded in-memory decision ring buffer** (e.g. last 200 actions) on
   the engine, surfaced under a new `"recent_actions": [...]` key in
   `diagnostics.py` (`async_get_config_entry_diagnostics`, currently
   `diagnostics.py:47-149`). This gives the viewer a single rich read with no
   recorder dependency, and survives a recorder purge window. (Optional: persist
   across restarts via the existing RestoreEntity/runtime plumbing — only if Jason
   wants history to survive HA restarts.)

Layer 1 is the durable system-of-record; layer 2 is the convenient read. Both are
low-risk additive changes — no control-flow changes to the engine's actuation.

### Viewer integration (separate repo `~/repos/aeolus-viewer`)
Once the integration emits the above, update the viewer's history to consume the
real log instead of reconstructing:
- Backend `app.py` → `build_activity()` (currently reconstructs from
  `/api/history/period` over mitigation + actuator entities). Swap to read
  `diagnostics.data.recent_actions` (richest) and/or `/api/logbook` filtered to
  `aeolus_action` events. Drop the reconstruction note in `static/app.js`
  (`renderActivity`, the "Reconstructed from Home Assistant's recorded state
  changes" line).
- Keep the existing reconstruction as a fallback for pre-upgrade installs.

### Acceptance criteria
- [ ] Each actuator on/off, veto, override, and runtime-cap fires an
      `aeolus_action` event with the payload above; events appear in HA's Logbook
      with readable descriptions.
- [ ] `diagnostics` exposes `recent_actions` (bounded), with what/when/why.
- [ ] Viewer Activity tab shows real actions (with reasons) and the
      "reconstructed" disclaimer is removed when the new data is present.
- [ ] Tests cover event emission at each site; CHANGELOG + docs updated; suite
      green; ruff/mypy clean.

---

## Cross-cutting notes
- This repo is **Platinum, strict-typed, CI-gated** (ruff `target-version=py312`
  floor, mypy `--strict` on 3.14, pytest ≥95% on 3.13+3.14). Keep
  spec/code/tests/CHANGELOG moving together — a dangling FR-id is a bug here.
- HA-history gotchas learned while building the viewer (relevant if you touch the
  viewer's reconstruction fallback): `/api/history/period` only puts `entity_id`
  on the **first** entry of each series; a window older than the recorder's
  retention returns **empty**.
- Don't deploy/restart HA without Jason's gate (phone-approval hook). The viewer
  reads via the diagnostics + states + history REST endpoints; an integration
  change needs an HA restart to take effect.

**Live data for sanity-checking:** 3 spaces, 10 actuators (entry_id
`01KTDPAT4B7P4R549G7GRTFYAT`). Viewer diagnostics view shows current
status/reason per space if you want a quick before/after.

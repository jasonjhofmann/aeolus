"""Safety + IAQ guardrails (FR-G*). Mostly STUB; one pure helper is real.

These GATE every actuation. For the reference (MCAS/allergy, leaky envelope)
home the binding constraint is allergen infiltration, not backdraft (§0.4):

  * outdoor-AQ veto (per-pathway, filter-aware): indoor PM contribution
    = outdoor_PM x (1 - filter_efficiency); block if over the low threshold   FR-G3
  * stale-sensor safe-state: stop mitigation if a member is stale (PER-MEMBER) FR-G5
  * per-actuator max-runtime                                                   FR-G1
  * radon-on-depressurization veto (v1.1; Aranet Radon+)                       FR-G2
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .const import DEFAULT_STALE_AFTER_SEC
from .engine import SpaceRuntime


def is_space_stale(
    rt: SpaceRuntime, now: datetime, *, stale_after_sec: float = DEFAULT_STALE_AFTER_SEC
) -> bool:
    """True if EVERY member is stale (don't trust the aggregate timestamp; FR-M1)."""
    if not rt.member_seen:
        return True
    cutoff = now - timedelta(seconds=stale_after_sec)
    return all(seen < cutoff for seen in rt.member_seen.values())


def outdoor_aq_blocks(outdoor_pm: float, filter_efficiency: float, threshold_pm: float) -> bool:
    """Filter-aware outdoor-AQ veto (FR-G3). Estimated indoor PM contribution."""
    indoor_contribution = outdoor_pm * (1.0 - filter_efficiency)
    return indoor_contribution > threshold_pm

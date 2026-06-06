"""Mitigation control + multi-space arbitration (FR-L*).

STUB — not yet implemented. Build this coherently inside the engine's context
(it shares the influence graph + per-space runtime). The shape, per spec:

  * per-space threshold/hysteresis + PI on (ema - target)            FR-L1
  * arbitration: maximize covered demand (coverage x gain) - cost    FR-L2
  * strategy escalation: direct -> induced when not converging       FR-L3
  * min on/off + settle window + anti-windup                         FR-L5
  * manual-override yield                                            FR-L7

Every actuation must pass the safety vetoes in safety.py first.
"""

from __future__ import annotations

from .engine import AeolusEngine


def decide_and_actuate(engine: AeolusEngine, space_id: str) -> None:
    """Evaluate one space and drive actuators (gated by safety vetoes)."""
    raise NotImplementedError("controller: v1.x — see REQUIREMENTS FR-L*")

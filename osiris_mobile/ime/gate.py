"""Advance gate backed by osiris-cli's CapabilityGapAnalyzer (full tier).

``make_gap_gate`` returns a gate for ``IntentEngine`` when osiris-cli is importable and
``None`` when it is not, in which case the engine stages nothing. Each turn the engine is
about to stage becomes a ``ProposedStep`` for the capability ``ime.advance.stage`` on this
node, bound to the IME journal head as its workspace snapshot, and the gate answers with
the analyzer's disposition.

The bridge supplies only inputs it actually has, and this module adds no thresholds:

* The policy is the rule the protocol already states (SYS-021): staging text is allowed,
  bound to the turn's fingerprint, because the operator still taps to dispatch it. An
  irreversible turn needs the operator's separate approval, so the analyzer answers
  WAITING_APPROVAL and the sequence halts before it.
* The snapshot is the journal head, read again when the turn is judged; a capture
  journaled in between changes the head, and the analyzer answers NEEDS_CONTEXT.
* No context requirements or verifiers are declared, since none is registered for
  staging, and the template planner reports no confidence, so the step carries the
  analyzer's default.
"""

import hashlib
import time
from typing import Any, Callable, Dict, Optional

__all__ = ["CAPABILITY_ID", "make_gap_gate"]

CAPABILITY_ID = "ime.advance.stage"


def make_gap_gate(node_label: str, snapshot: Callable[[], str]) -> Optional[Callable[[Dict[str, Any]], str]]:
    """A gate for ``IntentEngine(advance_gate=...)``, or ``None`` without osiris-cli."""
    try:
        from osiris_cli import gap_analyzer as ga
    except ImportError:
        return None

    capability = ga.CapabilitySpec(
        capability_id=CAPABILITY_ID,
        required_inputs=("prompt_sha256",),
        supported_targets=(node_label,),
    )

    def gate(step: Dict[str, Any]) -> str:
        proposed = ga.ProposedStep(
            step_id="advance-%d" % step["iteration"],
            capability_id=CAPABILITY_ID,
            target_node=node_label,
            parameters={
                "iteration": step["iteration"],
                "prompt_sha256": hashlib.sha256(step["prompt"].encode("utf-8")).hexdigest(),
                "irreversible": step["irreversible"],
            },
            workspace_snapshot_id=snapshot(),
        )
        if step["irreversible"]:
            policy = ga.PolicyAssessment(
                state=ga.PolicyState.APPROVAL_REQUIRED,
                reason="irreversible turn: the operator approves it separately",
            )
        else:
            policy = ga.PolicyAssessment(
                state=ga.PolicyState.ALLOWED,
                bound_action_fingerprint=ga.compute_action_fingerprint(proposed),
            )
        report = ga.CapabilityGapAnalyzer.analyze(ga.AnalysisInput(
            step=proposed,
            current_epoch=time.time(),
            active_snapshot_id=snapshot(),
            registered_capabilities={CAPABILITY_ID: capability},
            available_targets=frozenset((node_label,)),
            available_verifiers=frozenset(),
            context_facts=(),
            policy=policy,
        ))
        return report.disposition.value

    return gate

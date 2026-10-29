"""Intent compiler behind the keyboard's ✨ Auto Enhance and ≫ Auto Advance chips.

The operator types rough intent into the keyboard's OSIRIS bar; this module turns it
into a delineated prompt for whatever app is focused (ChatGPT, Gemini, Claude, Termux,
GitHub). It is a deterministic template, not a model: it works with llama-server down,
it is testable without a device, and the response says ``planner: "template"`` so nobody
mistakes it for model output.

Authority boundary. Nothing here sends anything anywhere. ``compile`` returns text; the
keyboard commits that text into the host app only when the operator taps dispatch.
Auto Advance *stages* follow-up turns, every one marked
``requires_operator_dispatch``; it never submits them, and anything that would push,
merge, publish, deploy or delete is flagged ``irreversible`` so the client must ask for a
second, distinct confirmation. An agent loop is a proposal stream, never authorization.

Each turn is staged only after the engine's advance gate answers ``READY`` for it; the
first other answer halts the sequence there. With no gate, nothing is staged: Auto
Advance fails closed. The bridge supplies osiris-cli's CapabilityGapAnalyzer as the gate
when osiris-cli is installed (``gate.make_gap_gate``).
"""

import hashlib
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

__all__ = [
    "Mode", "HOST_PROFILES", "MAX_ADVANCE_DEPTH", "READY",
    "SensitiveField", "normalize", "profile_for", "is_irreversible", "IntentEngine",
]

#: Total turns in one advance sequence, the operator's first turn included.
MAX_ADVANCE_DEPTH = 5
MAX_INTENT_CHARS = 8 * 1024
#: The one advance-gate answer that lets a turn be staged.
READY = "READY"


class Mode(object):
    LLM_INTERCEPT = "LLM_INTERCEPT"
    CLI_DIRECT = "CLI_DIRECT"
    DEVOPS = "DEVOPS_BRIDGE"
    COMMUNICATION = "COMMUNICATION"
    STANDARD = "STANDARD_ASSIST"


# Shorthand and typo recoveries seen in real thumb-typed intents on the split keyboard.
# Whole-word, case-insensitive; extend by adding pairs, never by fuzzy matching.
LEXICON = (
    ("oilsiris", "OSIRIS"),
    ("clin", "CLI"),
    ("chat bits", "chatbots"),
    ("deliniation", "delineation"),
    ("defuce", "deduce"),
    ("recurwiely", "recursively"),
    ("oogle cloud", "Google Cloud"),
    ("sllit", "split"),
    ("9rvhestrations", "orchestrations"),
    ("ncllm", "NCLM"),
)

HOST_PROFILES: Dict[str, Dict[str, str]] = {
    "com.openai.chatgpt": {
        "name": "ChatGPT", "mode": Mode.LLM_INTERCEPT,
        "directive": "Return production-ready code or structured analysis only. No conversational filler.",
    },
    "com.google.android.apps.bard": {
        "name": "Gemini", "mode": Mode.LLM_INTERCEPT,
        "directive": "Ground the answer in the context block below. State assumptions explicitly.",
    },
    "com.google.android.googlequicksearchbox": {
        "name": "Google AI Mode", "mode": Mode.LLM_INTERCEPT,
        "directive": "Ground the answer in the context block below. Cite sources for factual claims.",
    },
    "com.anthropic.claude": {
        "name": "Claude", "mode": Mode.LLM_INTERCEPT,
        "directive": "Treat the context block as the system under change. Flag anything you cannot verify.",
    },
    "com.termux": {
        "name": "Termux", "mode": Mode.CLI_DIRECT,
        "directive": "Emit commands for the active substrate only. One command per line, no chaining.",
    },
    "com.github.android": {
        "name": "GitHub", "mode": Mode.DEVOPS,
        "directive": "Proposals only: branches and draft PRs. The operator merges.",
    },
    "com.google.android.apps.cloudconsole": {
        "name": "Google Cloud", "mode": Mode.DEVOPS,
        "directive": "Read-only inspection unless the operator confirms a named mutation.",
    },
    "com.google.android.apps.messaging": {
        "name": "Messages", "mode": Mode.COMMUNICATION,
        "directive": "Draft only. The operator sends.",
    },
    "com.google.android.gm": {
        "name": "Gmail", "mode": Mode.COMMUNICATION,
        "directive": "Draft only. The operator sends.",
    },
}

_DEFAULT_PROFILE = {"name": "", "mode": Mode.STANDARD,
                    "directive": "Answer the request directly and say what you could not verify."}

# The shape of the answer, per interception mode. The directive says what to do; the
# schema says how to lay it out so the operator can check it before acting on it.
_SCHEMAS = {
    Mode.LLM_INTERCEPT: "Answer, then Verified (what you checked and how), then Unverified (what you could not check).",
    Mode.CLI_DIRECT: "One fenced block of commands, then one line per command saying what it changes.",
    Mode.DEVOPS: "Branch name, PR title and PR body, as a draft for the operator to review.",
    Mode.COMMUNICATION: "The message text only, for the operator to review and send.",
    Mode.STANDARD: "Answer, then one line on anything you could not verify.",
}

_IRREVERSIBLE = re.compile(
    r"(?i)\b(push|merge|commit|tag|release|publish|deploy|delete|drop|destroy|"
    r"force[- ]?push|rm\s+-rf|revoke|transfer|send|pay|purchase|scale\s+down)\b")

# Follow-up turns 2..MAX_ADVANCE_DEPTH. The irreversible flag is set by hand, not by
# regex: step 4 prepares something pushable, so the client must confirm it separately.
_ADVANCE_STEPS = (
    ("Audit the previous answer against the context block: list each claim and whether the "
     "context supports it.", False),
    ("Turn the audited answer into the smallest change that can be tested offline, with the "
     "test that would fail without it.", False),
    ("Prepare the change as a proposal (branch + draft PR description) for the operator to "
     "review.", True),
    ("Summarise the state for the operator: done, unverified, and blocked, one line each.", False),
)


class SensitiveField(ValueError):
    """The focused field is a password or other sensitive input; nothing is compiled."""


def normalize(raw: str) -> str:
    out = raw
    for typo, fixed in LEXICON:
        out = re.sub(r"\b%s\b" % re.escape(typo), fixed, out, flags=re.IGNORECASE)
    return " ".join(out.split())


def profile_for(package: str) -> Dict[str, str]:
    profile = HOST_PROFILES.get(package)
    if profile is not None:
        return dict(profile)
    fallback = dict(_DEFAULT_PROFILE)
    fallback["name"] = package or "unknown host"
    return fallback


def is_irreversible(text: str) -> bool:
    return bool(_IRREVERSIBLE.search(text))


def _context_block(nodes: Sequence[Dict[str, Any]]) -> str:
    if not nodes:
        return "- (no captured context attached)"
    return "\n".join("- [%s] (%s, %s): %s" % (n["node_id"], n["payload_type"], n["provenance"],
                                              n["summary"]) for n in nodes)


class IntentEngine(object):
    def __init__(self, node_label: str = "NODE_ALPHA",
                 advance_gate: Optional[Callable[[Dict[str, Any]], str]] = None) -> None:
        self.node_label = node_label
        self.advance_gate = advance_gate

    def compile(
        self,
        intent: str,
        host_package: str,
        context: Sequence[Dict[str, Any]] = (),
        auto_enhance: bool = True,
        auto_advance: bool = False,
        iteration: int = 1,
        sensitive_field: bool = False,
    ) -> Dict[str, Any]:
        if sensitive_field:
            raise SensitiveField("focused field is sensitive; interception is suppressed")
        if len(intent) > MAX_INTENT_CHARS:
            raise ValueError("intent of %d chars exceeds %d" % (len(intent), MAX_INTENT_CHARS))
        deduced = normalize(intent)
        if not deduced:
            raise ValueError("empty intent")
        if iteration < 1:
            raise ValueError("iteration must be >= 1")
        profile = profile_for(host_package)

        if auto_enhance:
            prompt = (
                "[OSIRIS interception | target: %s]\n"
                "### Objective\n%s\n\n"
                "### Active Context (%s, explicit captures only)\n%s\n\n"
                "### Constraints\n- %s\n- Deterministic, verifiable output; say what you could not verify.\n\n"
                "### Schema\n- %s\n"
                % (profile["name"], deduced, self.node_label, _context_block(context), profile["directive"],
                   _SCHEMAS[profile["mode"]])
            )
        else:
            prompt = deduced

        staged: List[Dict[str, Any]] = []
        advance_state: Optional[str] = None
        advance_halt: Optional[Dict[str, Any]] = None
        if auto_advance:
            if iteration >= MAX_ADVANCE_DEPTH:
                advance_state = "ADVANCE_LIMIT"
            elif self.advance_gate is None:
                advance_state = "NO_GATE"
            else:
                advance_state = "STAGED"
                for nxt in range(iteration + 1, MAX_ADVANCE_DEPTH + 1):
                    text, irreversible = _ADVANCE_STEPS[nxt - 2]
                    step = {
                        "iteration": nxt,
                        "prompt": text,
                        "requires_operator_dispatch": True,
                        "irreversible": irreversible,
                    }
                    disposition = self._gate(step)
                    if disposition != READY:
                        advance_state = "HALTED"
                        advance_halt = {"iteration": nxt, "disposition": disposition}
                        break
                    staged.append(step)

        return {
            "planner": "template",
            "detected_app": profile["name"],
            "interception_mode": profile["mode"],
            "deduced_intent": deduced,
            "compiled_host_prompt": prompt,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "requires_operator_dispatch": True,
            "irreversible": is_irreversible(deduced),
            "auto_enhance_active": bool(auto_enhance),
            "auto_advance_active": bool(auto_advance),
            "advance_state": advance_state,
            "advance_halt": advance_halt,
            "staged_next": staged,
        }

    def _gate(self, step: Dict[str, Any]) -> str:
        """The gate's answer for one turn, as a string. A gate that raises or answers with
        anything but a string has not said READY, so the turn is not staged."""
        try:
            answer = self.advance_gate(dict(step))
        except Exception as exc:
            return "GATE_ERROR: %s" % type(exc).__name__
        answer = getattr(answer, "value", answer)  # the analyzer's Disposition is a str Enum
        return answer if isinstance(answer, str) else "GATE_ERROR: answer is not a string"

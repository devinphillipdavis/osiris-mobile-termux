"""Deterministic intent deduction and route selection.

Routing is regex-scored, not model-inferred. Three reasons: it must work before
llama-server is up, it must be unit-testable without a device or a model, and a
misrouted sentence on mobile can launch a four-hour tournament on battery -- that
decision should never be a sampling outcome.

Two independent dimensions are extracted:

* **domain** -- which subsystem the sentence is about (organism / NCLM / LivLM / ladder)
* **mode**   -- whether the user wants it *explained* or *executed*

The cross-product matters. "explain the mux benchmark" and "run the mux benchmark"
share every domain keyword and must route differently: the first to the coding agent,
the second to a power-gated execution route. Domain words alone never start a job.
"""

import re
from typing import Dict, List, Pattern, Sequence, Tuple

__all__ = ["Route", "Classification", "classify", "describe_routes"]


class Route(object):
    """Route identifiers. Plain constants -- 3.9 has no StrEnum."""

    BRAIN = "brain"
    ORGANISM = "organism"
    NCLM = "nclm"
    LIVLM = "livlm"
    LADDER = "ladder"
    SYSTEM = "system"

    ALL = (BRAIN, ORGANISM, NCLM, LIVLM, LADDER, SYSTEM)

    #: Routes that can start sustained compute and must pass the power governor.
    HEAVY = (ORGANISM, NCLM, LIVLM, LADDER)


def _compile(patterns: Sequence[str]) -> List[Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# Domain vocabulary. Weights separate unambiguous names (LivLM, ANNECS) from words that
# also occur in ordinary English (gene, bridge, swarm).
_DOMAIN: Dict[str, List[Tuple[Pattern, float]]] = {
    Route.ORGANISM: list(zip(_compile([
        r"\borganism(_sim)?\b", r"\bxcs\b", r"\blcs\b", r"\bclassifier system\b",
        r"\bmux\b", r"\bmultiplexer\b", r"\bgrn\b", r"\bregulatory gene",
        r"\bchat[_ -]?bridge\b", r"\bneuro-?symbolic\b", r"\brule ?engine\b",
        r"\bPARAMS16\b", r"\bdrift\b", r"\brelay\b", r"\btournament\b",
        r"\bgenome\b", r"\bgene\b", r"\bdna(::\}\{::)?lang\b", r"\bsubsumption\b",
    ]), [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 3, 2, 2, 2, 2, 1.5, 3, 3])),

    Route.NCLM: list(zip(_compile([
        r"\bnclm\b", r"\bsovereign ?transformer\b", r"\bphase-?conjugate attention\b",
        r"\bnon-?causal\b", r"\battention\b", r"\bautograd\b", r"\bsafetensors\b",
        r"\bconsciousness ?field\b", r"\bintent ?deducer\b", r"\bcode ?swarm\b",
    ]), [4, 4, 4, 3, 1.5, 2, 2, 3, 3, 3])),

    Route.LIVLM: list(zip(_compile([
        r"\blivlm\b", r"\bliving language model\b", r"\bperplexity\b",
        r"\bqbyte\b", r"\bq-?byte\b", r"\bnegentrop", r"\bgeneration circuit\b",
    ]), [4, 4, 3, 2.5, 2.5, 2, 3])),

    Route.LADDER: list(zip(_compile([
        r"\bauto[- ]?advance\b", r"\bnext rung\b", r"\bPROGRAM\.md\b", r"\bladder\b",
        r"\bpre-?regist", r"\bscorecard\b", r"\bANNECS\b", r"\bM[1-9][a-c]?\b",
        r"\bmilestone\b", r"\brung\b",
    ]), [6, 5, 4, 3, 3, 3, 3, 3, 2.5, 2.5])),
}

# Mode. Explanatory phrasing wins over execution phrasing when both appear, because the
# failure modes are asymmetric: explaining a run the user wanted costs a sentence,
# launching a run the user only asked about costs four hours of battery.
_EXPLAIN = _compile([
    r"\bexplain\b", r"\bwhat(?:'s| is| are| does)\b", r"\bhow (?:do(?:es)?|did|would|can)\b",
    r"\bwhy\b", r"\bdescribe\b", r"\bsummar(?:ise|ize)\b", r"\btell me\b",
    r"\bshow me the code\b", r"\bwhere (?:is|are|does)\b", r"\bwhich\b",
    r"\bread\b", r"\bdocument\b", r"\bmeaning\b", r"\bdifference between\b",
    r"\?\s*$",
])

_EXECUTE = _compile([
    r"\brun\b", r"\blaunch\b", r"\bstart\b", r"\bexecute\b", r"\bbenchmark\b",
    r"\bevolve\b", r"\btrain\b", r"\bbench\b", r"\badvance\b", r"\bresume\b",
    r"\bcontinue the\b", r"\bkick off\b", r"\bgo ahead and\b", r"\bsweep\b",
    r"\breplicate\b", r"\bevaluate\b",
])

# Slash commands bypass scoring entirely.
_COMMANDS: Dict[str, str] = {
    "help": Route.SYSTEM, "quit": Route.SYSTEM, "exit": Route.SYSTEM,
    "status": Route.SYSTEM, "power": Route.SYSTEM, "battery": Route.SYSTEM,
    "model": Route.SYSTEM, "clear": Route.SYSTEM, "panes": Route.SYSTEM,
    "brain": Route.BRAIN, "scan": Route.BRAIN, "ingest": Route.BRAIN,
    "audit": Route.BRAIN, "memory": Route.BRAIN, "sprint": Route.BRAIN,
    "organism": Route.ORGANISM, "bridge": Route.ORGANISM, "bench": Route.ORGANISM,
    "nclm": Route.NCLM, "livlm": Route.LIVLM,
    "advance": Route.LADDER, "ladder": Route.LADDER, "program": Route.LADDER,
}

#: Below this margin between the top two domains, the REPL should confirm before
#: committing to a heavy route rather than guess.
AMBIGUITY_MARGIN = 1.5


class Classification(object):
    """The routing decision for one utterance."""

    __slots__ = ("route", "mode", "score", "scores", "matched", "ambiguous", "text")

    def __init__(self, route: str, mode: str, score: float,
                 scores: Dict[str, float], matched: List[str],
                 ambiguous: bool, text: str) -> None:
        self.route = route
        self.mode = mode                  # "explain" | "execute" | "converse"
        self.score = score
        self.scores = scores
        self.matched = matched
        self.ambiguous = ambiguous
        self.text = text

    @property
    def heavy(self) -> bool:
        """Whether this route must clear the power governor before running."""
        return self.route in Route.HEAVY and self.mode == "execute"

    def __repr__(self) -> str:
        return "Classification(%s/%s, score=%.1f%s)" % (
            self.route, self.mode, self.score, ", ambiguous" if self.ambiguous else "")


def _score_domains(text: str) -> Tuple[Dict[str, float], List[str]]:
    scores: Dict[str, float] = {}
    matched: List[str] = []
    for route, entries in _DOMAIN.items():
        total = 0.0
        for pattern, weight in entries:
            found = pattern.search(text)
            if found:
                total += weight
                matched.append(found.group(0).strip())
        if total:
            scores[route] = total
    return scores, matched


def _mode(text: str) -> str:
    explain = any(p.search(text) for p in _EXPLAIN)
    execute = any(p.search(text) for p in _EXECUTE)
    if explain:
        return "explain"
    if execute:
        return "execute"
    return "converse"


def classify(text: str) -> Classification:
    """Route one utterance. Pure, deterministic, and free of side effects."""
    raw = (text or "").strip()
    if not raw:
        return Classification(Route.SYSTEM, "converse", 0.0, {}, [], False, raw)

    # 1. Explicit slash command.
    if raw.startswith("/"):
        word = re.split(r"[\s/]+", raw[1:], maxsplit=1)[0].lower()
        route = _COMMANDS.get(word)
        if route is not None:
            mode = "execute" if route in Route.HEAVY else "converse"
            return Classification(route, mode, 10.0, {route: 10.0}, ["/" + word], False, raw)
        return Classification(Route.SYSTEM, "converse", 0.0, {}, ["/" + word], False, raw)

    # 2. "auto advance" is the directive's reserved phrase -- never scored against others.
    if re.search(r"\bauto[- ]?advance\b", raw, re.IGNORECASE):
        return Classification(Route.LADDER, "execute", 10.0, {Route.LADDER: 10.0},
                              ["auto advance"], False, raw)

    scores, matched = _score_domains(raw)
    mode = _mode(raw)

    if not scores:
        # No domain signal: the coding agent is the catch-all.
        return Classification(Route.BRAIN, mode, 0.0, {}, matched, False, raw)

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_route, top_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    ambiguous = (top_score - runner_up) < AMBIGUITY_MARGIN and len(ranked) > 1

    # 3. Explanatory phrasing about a subsystem is a question for the agent, not a run.
    if mode == "explain":
        return Classification(Route.BRAIN, "explain", top_score, scores, matched, False, raw)

    return Classification(top_route, mode, top_score, scores, matched, ambiguous, raw)


def describe_routes() -> str:
    """Human-readable routing table, used by /help."""
    rows = [
        (Route.BRAIN, "osiris_brain.py", "code Q&A, file ops, scan/ingest/audit", "light"),
        (Route.ORGANISM, "organism_sim + chat_bridge", "ALife, LCS/XCS, GRN, benchmarks", "HEAVY"),
        (Route.NCLM, "bench/nclm_harness.py", "SovereignTransformer train/infer", "HEAVY"),
        (Route.LIVLM, "bench/livlm_perplexity.py", "LivLM evolve/generate/perplexity", "HEAVY"),
        (Route.LADDER, "osiris_mobile.ladder", "PROGRAM.md rungs, auto advance", "HEAVY"),
        (Route.SYSTEM, "built-in", "power, status, model, panes, quit", "light"),
    ]
    width = max(len(r[0]) for r in rows)
    out = []
    for name, target, what, cost in rows:
        out.append("  %-*s  %-28s  %-38s  %s" % (width, name, target, what, cost))
    return "\n".join(out)

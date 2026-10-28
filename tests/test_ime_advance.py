"""Auto Advance under a gate: a turn is staged only when the gate answers READY, the first
other answer halts the sequence, no gate means nothing is staged, the full-tier gate is
osiris-cli's CapabilityGapAnalyzer, and a staged sequence can be continued for
ADVANCE_TTL_MS and no longer."""

import enum
import sys

import pytest

from osiris_mobile.ime import server as srv
from osiris_mobile.ime.engine import _ADVANCE_STEPS, MAX_ADVANCE_DEPTH, READY, IntentEngine
from osiris_mobile.ime.gate import make_gap_gate
from osiris_mobile.ime.server import ADVANCE_TTL_MS, Bridge

KEY = bytes(range(32))
IRREVERSIBLE_AT = next(i for i, (_, flag) in enumerate(_ADVANCE_STEPS, start=2) if flag)


def _advance(engine, iteration=1):
    return engine.compile("refactor the parser", "com.openai.chatgpt", auto_advance=True, iteration=iteration)


# --- engine ------------------------------------------------------------------------

def test_without_a_gate_nothing_is_staged():
    out = _advance(IntentEngine())
    assert out["advance_state"] == "NO_GATE"
    assert out["staged_next"] == [] and out["advance_halt"] is None
    assert out["compiled_host_prompt"]  # enhance still works


def test_the_gate_sees_each_turn_before_it_is_staged():
    seen = []

    def gate(step):
        seen.append(step["iteration"])
        step["prompt"] = "tampered"  # the gate gets a copy
        return READY

    out = _advance(IntentEngine(advance_gate=gate))
    assert seen == list(range(2, MAX_ADVANCE_DEPTH + 1))
    assert out["advance_state"] == "STAGED" and out["advance_halt"] is None
    assert [s["prompt"] for s in out["staged_next"]] == [t for t, _ in _ADVANCE_STEPS]


def test_the_first_non_ready_answer_halts_the_sequence():
    def gate(step):
        return "WAITING_APPROVAL" if step["irreversible"] else READY

    out = _advance(IntentEngine(advance_gate=gate))
    assert out["advance_state"] == "HALTED"
    assert [s["iteration"] for s in out["staged_next"]] == list(range(2, IRREVERSIBLE_AT))
    assert out["advance_halt"] == {"iteration": IRREVERSIBLE_AT, "disposition": "WAITING_APPROVAL"}


class _Disposition(str, enum.Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@pytest.mark.parametrize("gate, disposition", [
    (lambda step: _Disposition.BLOCKED, "BLOCKED"),
    (lambda step: None, "GATE_ERROR: answer is not a string"),
    (lambda step: 1 / 0, "GATE_ERROR: ZeroDivisionError"),
])
def test_a_failing_or_refusing_gate_stages_nothing(gate, disposition):
    out = _advance(IntentEngine(advance_gate=gate))
    assert out["advance_state"] == "HALTED" and out["staged_next"] == []
    assert out["advance_halt"] == {"iteration": 2, "disposition": disposition}


def test_a_str_enum_ready_counts_as_ready():
    out = _advance(IntentEngine(advance_gate=lambda step: _Disposition.READY))
    assert out["advance_state"] == "STAGED" and len(out["staged_next"]) == MAX_ADVANCE_DEPTH - 1


# --- full-tier gate ------------------------------------------------------------------

def test_without_osiris_cli_there_is_no_gap_gate(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "osiris_cli", None)
    assert make_gap_gate("NODE_ALPHA", lambda: "head") is None
    bridge = Bridge(KEY, tmp_path / "journal.jsonl")
    assert bridge.advance_gate_name == "none" and bridge.engine.advance_gate is None


def test_gap_gate_halts_at_the_irreversible_turn():
    pytest.importorskip("osiris_cli.gap_analyzer")
    gate = make_gap_gate("NODE_ALPHA", lambda: "a" * 64)
    out = _advance(IntentEngine(advance_gate=gate))
    assert out["advance_state"] == "HALTED"
    assert [s["iteration"] for s in out["staged_next"]] == list(range(2, IRREVERSIBLE_AT))
    assert out["advance_halt"] == {"iteration": IRREVERSIBLE_AT, "disposition": "WAITING_APPROVAL"}


def test_gap_gate_halts_when_the_journal_moves_under_it():
    pytest.importorskip("osiris_cli.gap_analyzer")
    heads = iter(["a" * 64, "b" * 64] * MAX_ADVANCE_DEPTH)
    out = _advance(IntentEngine(advance_gate=make_gap_gate("NODE_ALPHA", lambda: next(heads))))
    assert out["staged_next"] == []
    assert out["advance_halt"] == {"iteration": 2, "disposition": "NEEDS_CONTEXT"}


def test_bridge_uses_the_gap_gate_when_osiris_cli_is_installed(tmp_path):
    pytest.importorskip("osiris_cli.gap_analyzer")
    bridge = Bridge(KEY, tmp_path / "journal.jsonl")
    assert bridge.advance_gate_name == "gap_analyzer"
    assert bridge.health()["advance_gate"] == "gap_analyzer"


# --- sequence expiry -------------------------------------------------------------------

@pytest.fixture
def clocked(tmp_path):
    now = [1_800_000_000_000]
    bridge = Bridge(KEY, tmp_path / "journal.jsonl", clock_ms=lambda: now[0], advance_gate=lambda s: READY)
    return bridge, now


def _intercept(bridge, **fields):
    body = {"intent": "refactor the parser", "host_package": "com.openai.chatgpt", "auto_advance": True}
    body.update(fields)
    return bridge.route("POST", "/v1/intent/intercept", body)


def test_a_first_turn_opens_a_sequence_that_lives_advance_ttl(clocked):
    bridge, now = clocked
    out = _intercept(bridge)
    sequence = out["advance_sequence"]
    assert len(sequence["id"]) == 32
    assert sequence["expires_at_ms"] == now[0] + ADVANCE_TTL_MS == now[0] + 120_000


def test_continuing_keeps_the_sequence_and_its_expiry(clocked):
    bridge, now = clocked
    first = _intercept(bridge)["advance_sequence"]
    now[0] += ADVANCE_TTL_MS - 1
    out = _intercept(bridge, iteration=3, advance_sequence_id=first["id"])
    assert [s["iteration"] for s in out["staged_next"]] == [4, 5]
    assert out["advance_sequence"] == first


@pytest.mark.parametrize("fields", [
    {"iteration": 2},                                   # no sequence id
    {"iteration": 2, "advance_sequence_id": "f" * 32},  # unknown sequence
])
def test_continuing_without_a_live_sequence_is_refused(clocked, fields):
    bridge, _ = clocked
    with pytest.raises(srv._BadRequest) as caught:
        _intercept(bridge, **fields)
    assert (caught.value.status, caught.value.code) == (409, "ADVANCE_EXPIRED")


def test_a_sequence_cannot_be_continued_after_it_expires(clocked):
    bridge, now = clocked
    first = _intercept(bridge)["advance_sequence"]
    now[0] += ADVANCE_TTL_MS
    with pytest.raises(srv._BadRequest) as caught:
        _intercept(bridge, iteration=2, advance_sequence_id=first["id"])
    assert (caught.value.status, caught.value.code) == (409, "ADVANCE_EXPIRED")
    assert _intercept(bridge)["advance_sequence"]["id"] != first["id"]  # a new first turn starts over


def test_nothing_staged_means_no_sequence(tmp_path):
    bridge = Bridge(KEY, tmp_path / "journal.jsonl", advance_gate=None)
    out = _intercept(bridge)
    assert out["advance_state"] == "NO_GATE" and out["advance_sequence"] is None
    assert bridge.health()["advance_gate"] == "none"
    assert '"advance_state":"NO_GATE"' in bridge.ledger.path.read_text(encoding="utf-8")

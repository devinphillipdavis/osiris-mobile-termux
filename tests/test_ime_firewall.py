"""SYS-025 AST firewall: captured code that calls an unconstrained execution primitive is
refused before it is journaled, in a bare snippet, in a fenced block inside model output,
and in text too long or too deep to parse; ordinary code and prose pass."""

import ast

import pytest

from osiris_mobile.ime import firewall
from osiris_mobile.ime.clipboard import ASTClipboard, FirewallRejected, IngestRejected, Provenance
from osiris_mobile.ime.firewall import MAX_PARSE_CHARS, firewall_violations
from osiris_mobile.ime.ledger import HashChainLedger

BANNED = [
    "eval(user_input)",
    "exec(compile(src, 'x', 'exec'))",
    "mod = __import__('os')",
    "import os\nos.system('rm -rf /tmp/x')",
    "os.popen('ls').read()",
    "os.execv('/bin/sh', ['sh'])",
    "import subprocess\nsubprocess.run('ls | wc', shell=True)",
    "import subprocess as sp\nsp.call(cmd, shell=True)",
]

CLEAN = [
    "def add(a, b):\n    return a + b",
    "import re\npattern = re.compile(r'\\d+')",   # an attribute call, as in osiris-cli
    "value = ast.literal_eval(text)",
    "model.eval()",
    "subprocess.run(['ls', '-l'], check=True)",
    "subprocess.run(cmd, shell=False)",
    "Please evaluate the plan and compile a summary.",  # prose: not Python
    "git push origin main",
]


@pytest.mark.parametrize("snippet", BANNED)
def test_banned_constructs_are_flagged(snippet):
    assert firewall_violations(snippet)


@pytest.mark.parametrize("snippet", CLEAN)
def test_clean_code_and_prose_pass(snippet):
    assert firewall_violations(snippet) == []


def test_a_fenced_block_inside_model_output_is_checked():
    reply = "Here is the fix:\n\n```python\nexec(payload)\n```\n\nIt runs the payload directly."
    assert firewall_violations(reply) == ["Forbidden call: 'exec' at line 1"]
    assert firewall_violations("Here is the fix:\n\n```python\nprint(payload)\n```\n") == []


def test_text_too_long_to_parse_is_checked_lexically():
    long_text = "x = 1\n" * (MAX_PARSE_CHARS // 6 + 1)
    assert len(long_text) > MAX_PARSE_CHARS
    assert firewall_violations(long_text) == []
    flagged = firewall_violations(long_text + "eval(x)\n")
    assert flagged and "unparsed" in flagged[0]
    # The lexical fallback bans what the AST rule bans: bare calls, not attribute calls.
    assert firewall_violations(long_text + "p = re.compile(r'x')\nmodel.eval()\n") == []


@pytest.mark.parametrize("error", [RecursionError, MemoryError])
def test_text_too_deep_to_parse_is_checked_lexically(monkeypatch, error):
    def too_deep(_text):
        raise error()

    monkeypatch.setattr(firewall.ast, "parse", too_deep)
    flagged = firewall_violations("eval(x)")
    assert flagged and "too deeply nested" in flagged[0]
    assert firewall_violations("print(x)") == []


def test_matches_osiris_cli_sys025_when_installed():
    controller = pytest.importorskip("osiris_cli.orchestration.controller")
    for snippet in BANNED + CLEAN:
        try:
            ast.parse(snippet)
        except SyntaxError:
            continue  # osiris-cli rejects unparseable proposals; captures of prose are not code
        clean, theirs = controller.GovernanceController.inspect_ast(snippet)
        assert firewall_violations(snippet) == theirs, snippet
        assert clean is (theirs == [])


def test_ingest_refuses_a_flagged_capture_and_journals_nothing(tmp_path):
    board = ASTClipboard(HashChainLedger(tmp_path / "journal.jsonl"))
    with pytest.raises(FirewallRejected) as caught:
        board.ingest("import os\nos.system('id')", "com.openai.chatgpt", Provenance.EXPLICIT_COPY)
    assert isinstance(caught.value, IngestRejected)
    assert caught.value.violations == ["Forbidden os call: 'os.system' at line 2"]
    assert len(board.ledger) == 0 and board.recent() == []

    node = board.ingest("def add(a, b):\n    return a + b", "x", Provenance.EXPLICIT_COPY)
    assert node["payload_type"] == "python_ast" and len(board.ledger) == 1

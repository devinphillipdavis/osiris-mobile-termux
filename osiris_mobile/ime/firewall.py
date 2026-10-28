"""SYS-025 AST firewall for captured code.

A capture whose Python calls an unconstrained execution primitive is refused before it
is journaled or offered as prompt context. The rules mirror osiris-cli's
``orchestration.controller.ASTFirewallVisitor``: ``exec``, ``eval``, ``compile`` and
``__import__``; ``os.system``, ``os.popen``, ``os.execv``, ``os.execve`` and ``os.spawnl``;
and ``subprocess`` called with ``shell=True``. ``tests/test_ime_firewall.py`` checks the two
agree whenever osiris-cli is importable; this repo cannot import it on the lite tier.

What is checked: the whole capture, and each fenced code block in it, since model output
usually arrives as prose around a code fence. Text that is not Python passes; there is
nothing to parse. Text the parser cannot take (too long, or nested too deep) is checked
lexically instead, so neither size nor depth gets code past the firewall.
"""

import ast
import re
from typing import List

__all__ = ["MAX_PARSE_CHARS", "BANNED_CALL_NAMES", "firewall_violations"]

#: Upper bound on characters handed to ``ast.parse``; deep or huge input can exhaust
#: the parser's stack long before it produces anything useful.
MAX_PARSE_CHARS = 64 * 1024

BANNED_CALL_NAMES = frozenset(("exec", "eval", "compile", "__import__"))
_BANNED_OS_CALLS = frozenset(("system", "popen", "execv", "execve", "spawnl"))
_SUBPROCESS_NAMES = frozenset(("subprocess", "sp"))

_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_LEXICAL = re.compile(
    r"(?<![\w.])(?:exec|eval|compile|__import__)\s*\("  # a bare call, as the AST rule: not re.compile(
    r"|\bos\s*\.\s*(?:system|popen|execve?|spawnl)\s*\("
    r"|\bshell\s*=\s*True\b")


def _ast_violations(tree: ast.AST) -> List[str]:
    found = []
    for node in ast.walk(tree):  # iterative, so a deep tree cannot overflow the stack here
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in BANNED_CALL_NAMES:
                found.append("Forbidden call: '%s' at line %d" % (func.id, node.lineno))
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "os":
                if func.attr in _BANNED_OS_CALLS:
                    found.append("Forbidden os call: 'os.%s' at line %d" % (func.attr, node.lineno))
            elif func.value.id in _SUBPROCESS_NAMES:
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        found.append("Forbidden subprocess with shell=True at line %d" % node.lineno)
    return found


def _lexical_violations(text: str, why: str) -> List[str]:
    return ["Forbidden construct (%s): %r" % (why, m.group(0)) for m in _LEXICAL.finditer(text)]


def _check(text: str) -> List[str]:
    if len(text) > MAX_PARSE_CHARS:
        return _lexical_violations(text, "unparsed, over %d chars" % MAX_PARSE_CHARS)
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []  # not Python
    except (RecursionError, MemoryError):
        return _lexical_violations(text, "unparsed, too deeply nested")
    return _ast_violations(tree)


def firewall_violations(text: str) -> List[str]:
    """SYS-025 violations in a capture: in the whole text, then in each fenced block."""
    found = _check(text)
    for block in _FENCE.findall(text):
        found.extend(v for v in _check(block) if v not in found)
    return found

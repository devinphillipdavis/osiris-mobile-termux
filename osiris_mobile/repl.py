"""The unified OSIRIS REPL -- one prompt, intent-routed, power-governed.

Design rules
------------
* Routing is deterministic (``osiris_mobile.intent``), so it works before llama-server
  is up and is unit-testable without a device.
* Heavy routes pass the power governor before spending battery, and say why when they
  do not.
* Research code is invoked as a subprocess through its own published CLI, never
  re-implemented here. ``organism_sim.cli ask`` already has a deterministic router with
  a ``--dry`` mode; the ORGANISM route delegates to it rather than building argv by hand.
* Routes whose harness is not yet written say so plainly instead of pretending.

Run:  osiris-mobile            |  python -m osiris_mobile.repl
      osiris-mobile --once "run the mux benchmark phase B"
      osiris-mobile --dry      # route and print the command, never execute
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .intent import Classification, Route, classify, describe_routes
from .power import Governor
from .store import ensure, env_flag, home
from .telemetry.stream import FrameStream

__all__ = ["OsirisREPL", "main"]

_BANNER = """\033[1mOSIRIS Mobile\033[0m -- unified research REPL
\033[2mintent-routed - power-governed - no cloud. /help for routes, /quit to exit.\033[0m"""

_PROMPT = "\033[36mosiris\033[0m> "

#: Every route now has a harness; the map is kept so a future route can declare itself
#: unwired rather than failing obscurely.
_PENDING = {}

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _src_root() -> Path:
    return Path(os.environ.get("OSIRIS_SRC", str(Path.home() / "osiris-src")))


def _venv_python() -> str:
    """The interpreter that has the research repos installed."""
    venv = os.environ.get("OSIRIS_VENV")
    if venv:
        candidate = Path(venv) / "bin" / "python"
        if candidate.exists():
            return str(candidate)
    return sys.executable


def find_brain() -> Optional[Path]:
    """Locate osiris_brain.py across the desktop and on-device layouts."""
    for candidate in (
        _src_root() / "osiris-cli" / "osiris_brain.py",
        _src_root() / "osiris_brain.py",
        Path.home() / "osiris_brain.py",
        Path(__file__).resolve().parent.parent.parent / "osiris_brain.py",
    ):
        if candidate.exists():
            return candidate
    return None


class OsirisREPL(object):
    """The loop. Holds the governor, the telemetry stream and the route dispatch."""

    def __init__(self, dry: bool = False, power_gate: bool = True,
                 governor: Optional[Governor] = None) -> None:
        self.dry = dry
        self.power_gate = power_gate
        self.governor = governor or Governor()
        self.stream = FrameStream(every=1)
        self.python = _venv_python()
        self.brain = find_brain()
        ensure()

    # -- process helpers ------------------------------------------------------
    def _run(self, argv: List[str], cwd: Optional[Path] = None) -> int:
        """Run a subprocess, streaming its output straight into the pane."""
        printable = " ".join(argv)
        if self.dry:
            print("\033[2mdry-run:\033[0m %s" % printable)
            return 0
        self.stream.note("exec", argv=printable)
        try:
            return subprocess.call(argv, cwd=str(cwd) if cwd else None)
        except OSError as exc:
            print("\033[31mcould not execute:\033[0m %s (%s)" % (printable, exc))
            return 127
        except KeyboardInterrupt:
            print("\n\033[2minterrupted\033[0m")
            return 130

    # -- power ----------------------------------------------------------------
    def _clear_to_run(self, decision_label: str) -> bool:
        """Gate a heavy route. Returns False when the user should not proceed."""
        if not self.power_gate:
            return True
        decision = self.governor.check()
        if decision.ok:
            if decision.action == "unknown":
                print("\033[33mpower unknown:\033[0m %s" % decision.reason)
            return True
        print("\033[33mpaused:\033[0m %s" % decision.reason)
        print("\033[2m%s needs sustained CPU. Plug in, or re-run with --no-power-gate.\033[0m"
              % decision_label)
        self.stream.note("pause", reason=decision.reason, route=decision_label)
        return False

    # -- routes ---------------------------------------------------------------
    def route_brain(self, text: str) -> int:
        if self.brain is None:
            print("\033[31mosiris_brain.py not found.\033[0m Looked under $OSIRIS_SRC "
                  "(%s) and $HOME." % _src_root())
            return 1
        argv = [self.python, str(self.brain), text]
        model = os.environ.get("OSIRIS_MODEL")
        if model:
            argv += ["--model", model]
        return self._run(argv)

    def route_organism(self, text: str) -> int:
        """Delegate to organism_sim's own deterministic router."""
        argv = [self.python, "-m", "organism_sim.cli", "ask"]
        if self.dry:
            argv.append("--dry")
        argv += text.split()
        return self._run(argv)

    def route_nclm(self, text: str) -> int:
        """Directive D. Bare mentions train; 'infer'/'sample'/'generate' sample."""
        script = str(_repo_root() / "bench" / "nclm_harness.py")
        lowered = text.lower()
        if any(word in lowered for word in ("infer", "sample", "generate", "complete")):
            return self._run([self.python, script, "infer", "--prompt", text])
        argv = [self.python, script, "train"]
        steps = self._first_int(text)
        if steps:
            argv += ["--steps", str(steps)]
        corpus = os.environ.get("OSIRIS_SRC")
        if corpus:
            argv += ["--corpus", corpus]
        return self._run(argv)

    def route_livlm(self, text: str) -> int:
        """Directive E. Judged runs need the pre-registered seeds; the benchmark enforces
        that itself, so the REPL does not second-guess it."""
        script = str(_repo_root() / "bench" / "livlm_perplexity.py")
        argv = [self.python, script]
        if "random" in text.lower() or "control" in text.lower():
            argv += ["--arm", "random"]
        if "tuning" in text.lower():
            argv += ["--tuning"]
        return self._run(argv)

    def route_ladder(self, text: str) -> int:
        """Directive F. `auto advance` stages or launches; it never invents a criterion."""
        argv = [self.python, "-m", "osiris_mobile.ladder.advance"]
        lowered = text.lower()
        if "status" in lowered or "ladder" in lowered and "advance" not in lowered:
            argv.append("status")
        else:
            argv.append("auto")
        if self.dry:
            argv.append("--dry")
        env_cwd = _repo_root()
        return self._run(argv, cwd=env_cwd)

    @staticmethod
    def _first_int(text: str) -> Optional[int]:
        import re as _re
        found = _re.search(r"\b(\d{2,6})\b", text)
        return int(found.group(1)) if found else None

    def route_pending(self, route: str) -> int:
        target, directive = _PENDING[route]
        print("\033[33m%s route is not wired yet.\033[0m" % route)
        print("\033[2mPlanned target: %s (%s). See docs/STRUCTURE.md.\033[0m"
              % (target, directive))
        return 2

    # -- system commands ------------------------------------------------------
    def route_system(self, text: str) -> int:
        word = text.lstrip("/").split()[0].lower() if text.strip() else "help"

        if word in ("quit", "exit"):
            return -1

        if word == "help":
            print(_BANNER)
            print("\n\033[1mroutes\033[0m")
            print(describe_routes())
            print("\n\033[1mcommands\033[0m")
            print("  /help /status /power /model /panes /clear /quit")
            print("  /brain /organism /nclm /livlm /advance  -- force a route")
            return 0

        if word in ("power", "battery"):
            decision = self.governor.check()
            print("%s\n\033[2m%s\033[0m" % (decision.reason, self.governor))
            return 0

        if word == "status":
            print("state root : %s" % home())
            print("sources    : %s" % _src_root())
            print("python     : %s" % self.python)
            print("brain      : %s" % (self.brain or "\033[31mnot found\033[0m"))
            print("telemetry  : %s (%d records)" % (self.stream.path, len(self.stream)))
            print("power      : %s" % self.governor.check().reason)
            size = shutil.get_terminal_size(fallback=(80, 24))
            print("terminal   : %dx%d %s" % (size.columns, size.lines,
                                             "(unfolded)" if size.columns >= 100 else "(narrow)"))
            return 0

        if word == "model":
            print("model  : %s" % os.environ.get("OSIRIS_MODEL", "(unset)"))
            print("weights: %s" % os.environ.get("OSIRIS_MODEL_PATH", "(unset)"))
            print("backend: %s" % os.environ.get("OSIRIS_OLLAMA", "(unset)"))
            return 0

        if word == "panes":
            print("Relayout the tmux lab for the current fold state:")
            print("  \033[36m./launch_fold.sh --relayout\033[0m   (or prefix + R inside tmux)")
            return 0

        if word == "clear":
            sys.stdout.write("\033[H\033[2J")
            sys.stdout.flush()
            return 0

        print("unknown command: /%s  (try /help)" % word)
        return 1

    # -- dispatch -------------------------------------------------------------
    def dispatch(self, cls: Classification) -> int:
        """Execute one classified utterance. Returns -1 to end the session."""
        if cls.route == Route.SYSTEM:
            return self.route_system(cls.text)

        if cls.ambiguous and cls.heavy:
            ranked = sorted(cls.scores.items(), key=lambda kv: -kv[1])[:2]
            print("\033[33mambiguous:\033[0m %s" %
                  " vs ".join("%s (%.1f)" % (r, s) for r, s in ranked))
            print("\033[2mforce one with /%s or /%s\033[0m" % (ranked[0][0], ranked[1][0]))
            return 1

        if cls.heavy and not self._clear_to_run(cls.route):
            return 1

        if cls.route == Route.BRAIN:
            return self.route_brain(cls.text)
        if cls.route == Route.ORGANISM:
            return self.route_organism(cls.text)
        if cls.route == Route.NCLM:
            return self.route_nclm(cls.text)
        if cls.route == Route.LIVLM:
            return self.route_livlm(cls.text)
        if cls.route == Route.LADDER:
            return self.route_ladder(cls.text)
        return self.route_pending(cls.route)

    def once(self, text: str) -> int:
        cls = classify(text)
        if os.environ.get("OSIRIS_TRACE_ROUTING"):
            print("\033[2m%r\033[0m" % cls)
        code = self.dispatch(cls)
        return 0 if code == -1 else code

    def loop(self) -> int:
        print(_BANNER)
        if self.brain is None:
            print("\033[33mnote:\033[0m osiris_brain.py not found -- the BRAIN route is unavailable.")
        while True:
            try:
                text = input(_PROMPT)
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not text.strip():
                continue
            cls = classify(text)
            if os.environ.get("OSIRIS_TRACE_ROUTING"):
                print("\033[2m%r\033[0m" % cls)
            if self.dispatch(cls) == -1:
                return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="osiris-mobile",
        description="Unified OSIRIS REPL: intent-routed, power-governed, on-device.")
    ap.add_argument("--once", metavar="TEXT", help="route one utterance and exit")
    ap.add_argument("--dry", action="store_true",
                    help="print the command each route would run, never execute")
    ap.add_argument("--no-power-gate", action="store_true",
                    help="skip the battery/thermal gate on heavy routes")
    ap.add_argument("--trace", action="store_true", help="print the routing decision")
    args = ap.parse_args(argv)

    if args.trace:
        os.environ["OSIRIS_TRACE_ROUTING"] = "1"

    repl = OsirisREPL(dry=args.dry or env_flag("OSIRIS_DRY_RUN", False),
                      power_gate=not args.no_power_gate)
    if args.once:
        return repl.once(args.once)
    return repl.loop()


if __name__ == "__main__":
    sys.exit(main())

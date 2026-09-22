"""Directive F -- stage and launch the next rung of the research ladder.

The governing rule, unchanged from the desktop: **the criterion is committed before the
run.** So this module distinguishes two verbs.

* **stage** -- a rung that is unresolved but has no pre-registration. Staging collects
  what a run would need, writes a *draft* criterion for a human to complete, and stops.
  It never launches.
* **launch** -- a rung that is unresolved, already pre-registered, and not in flight.
  Runs its driver under `setsid` so the Termux session can be swiped away, holds a wake
  lock, and notifies on completion.

Auto-advance will not invent a criterion, and will not write a verdict for one it had to
infer. Commit-on-PASS is allowed and is off by default; criterion-on-PASS is never allowed.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..power import Governor
from ..power.notify import NOTIFY_LADDER, notify
from ..store import atomic_write_json, ensure, sub
from .program import Program, Rung, load_program

__all__ = ["StagedRun", "Advancer", "main"]


def _src_root() -> Path:
    return Path(os.environ.get("OSIRIS_SRC", str(Path.home() / "osiris-src")))


def _organism_root() -> Path:
    for candidate in (_src_root() / "organism_sim", Path.home() / "organism_sim"):
        if candidate.exists():
            return candidate
    return _src_root() / "organism_sim"


class StagedRun(object):
    """What staging worked out about a rung, and what is still missing."""

    __slots__ = ("rung", "driver", "blockers", "draft_path", "notes")

    def __init__(self, rung: Rung, driver: Optional[Path], blockers: List[str],
                 draft_path: Optional[Path], notes: List[str]) -> None:
        self.rung = rung
        self.driver = driver
        self.blockers = blockers
        self.draft_path = draft_path
        self.notes = notes

    @property
    def ready(self) -> bool:
        return not self.blockers

    def to_dict(self) -> Dict[str, Any]:
        return {"rung": self.rung.rid, "status": self.rung.status,
                "driver": str(self.driver) if self.driver else None,
                "blockers": self.blockers, "notes": self.notes,
                "draft": str(self.draft_path) if self.draft_path else None}

    def __repr__(self) -> str:
        return "StagedRun(%s, %s)" % (self.rung.rid, "ready" if self.ready else "blocked")


class Advancer(object):
    """Reads the ladder, stages or launches, never invents a criterion."""

    def __init__(self, program: Optional[Program] = None,
                 governor: Optional[Governor] = None, power_gate: bool = True) -> None:
        self.program = program or load_program()
        self.governor = governor or Governor()
        self.power_gate = power_gate
        ensure()

    # -- discovery ------------------------------------------------------------
    def find_driver(self, rung: Rung) -> Optional[Path]:
        """Locate the experiment driver for a rung, if one has been written."""
        experiments = _organism_root() / "experiments"
        if not experiments.is_dir():
            return None
        number = rung.rid[1:].lower()               # M3c -> "3c", M4 -> "4"
        base = "".join(ch for ch in number if ch.isdigit())
        for path in sorted(experiments.glob("*.py")):
            stem = path.stem.lower()
            if stem in ("m%s" % number, "m%s_run" % number):
                return path
            if stem.startswith("m%s_" % number) or stem.startswith("m%s" % base + "_"):
                return path
        return None

    # -- staging --------------------------------------------------------------
    def stage(self, rung: Rung) -> StagedRun:
        """Work out what launching this rung would require. Never launches."""
        blockers: List[str] = []
        notes: List[str] = []

        if rung.in_flight:
            blockers.append("%s is already running (%s)" % (rung.rid, rung.driver or "driver unknown"))
        if rung.resolved:
            blockers.append("%s is already resolved: %s" % (rung.rid, "/".join(rung.verdicts)))

        driver = self.find_driver(rung)
        if driver is None:
            blockers.append("no driver script under %s for %s" % (_organism_root() / "experiments", rung.rid))
        else:
            notes.append("driver: %s" % driver)

        draft_path: Optional[Path] = None
        if not rung.pre_registered:
            blockers.append("%s has no pre-registration block in %s" % (rung.rid, self.program.path.name))
            draft_path = self._write_draft(rung)
            notes.append("draft criterion written to %s -- complete it, commit it to "
                         "PROGRAM.md, then launch" % draft_path)
        else:
            notes.append("pre-registered %s" % rung.prereg_date)

        staged = StagedRun(rung, driver, blockers, draft_path, notes)
        atomic_write_json(sub("results") / ("staged_%s.json" % rung.rid.lower()),
                          staged.to_dict(), indent=1)
        return staged

    def _write_draft(self, rung: Rung) -> Path:
        """A criterion *template*, deliberately full of blanks.

        It is a prompt for a human decision, not a generated criterion. Auto-advance
        must not be able to satisfy its own gate.
        """
        path = sub("results") / ("prereg_draft_%s.md" % rung.rid.lower())
        path.write_text(
            "### %s — %s (pre-registered TODO-DATE, not yet run)\n\n"
            "> DRAFT generated by osiris_mobile.ladder.advance on %s.\n"
            "> This is a template, not a criterion. Auto-advance cannot fill it in:\n"
            "> a criterion it wrote itself would not be a pre-registration.\n"
            "> Complete every TODO, paste the block into %s, commit it, then launch.\n\n"
            "**Ladder metric:** %s\n\n"
            "**Ladder kill criterion:** %s\n\n"
            "| criterion | statement |\n|---|---|\n"
            "| C1 | TODO |\n| C2 | TODO |\n\n"
            "PASS ⇔ TODO. Reported, not judged: TODO.\n\n"
            "**Seeds.** tuning TODO (never judged); evaluation TODO (frozen here).\n\n"
            "**Cost estimate.** TODO. **Driver.** %s\n"
            % (rung.rid, rung.title, time.strftime("%Y-%m-%d"), self.program.path,
               rung.metric or "TODO", rung.criterion or "TODO",
               self.find_driver(rung) or "TODO — not yet written"),
            encoding="utf-8")
        return path

    # -- launching ------------------------------------------------------------
    def launch(self, rung: Rung, seeds: int = 5, extra: Optional[List[str]] = None,
               dry: bool = False) -> Dict[str, Any]:
        """Run a pre-registered rung in the background, detached from the session."""
        staged = self.stage(rung)
        if not rung.launchable:
            return {"launched": False, "rung": rung.rid, "reason":
                    "not launchable (%s)" % rung.status, "blockers": staged.blockers}
        if staged.driver is None:
            return {"launched": False, "rung": rung.rid, "reason": "no driver",
                    "blockers": staged.blockers}

        if self.power_gate:
            decision = self.governor.check()
            if not decision.ok:
                return {"launched": False, "rung": rung.rid,
                        "reason": "power: %s" % decision.reason}

        python = os.environ.get("OSIRIS_VENV", "")
        interpreter = str(Path(python) / "bin" / "python") if python else sys.executable
        log = sub("logs") / ("%s_stdout.log" % rung.rid.lower())
        argv = [interpreter, str(staged.driver), str(seeds)] + list(extra or [])

        if dry:
            return {"launched": False, "rung": rung.rid, "dry": True,
                    "argv": " ".join(argv), "log": str(log)}

        # start_new_session=True is setsid: the run survives the Termux session being
        # swiped away. Plain nohup does not.
        from ..power.wakelock import acquire
        acquire()
        with open(str(log), "ab") as out, open(os.devnull, "rb") as devnull:
            proc = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT,
                                    stdin=devnull, cwd=str(_organism_root()),
                                    start_new_session=True)
        record = {"launched": True, "rung": rung.rid, "pid": proc.pid,
                  "argv": " ".join(argv), "log": str(log),
                  "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "pre_registered": rung.prereg_date}
        atomic_write_json(sub("results") / ("launched_%s.json" % rung.rid.lower()), record, indent=1)
        notify("%s launched" % rung.rid, "pid %d — tail %s" % (proc.pid, log.name),
               nid=NOTIFY_LADDER, ongoing=True)
        return record

    # -- the entry point ------------------------------------------------------
    def auto_advance(self, dry: bool = False) -> Dict[str, Any]:
        """`auto advance`: pick the next free rung, then stage or launch it."""
        running = self.program.in_flight()
        rung = self.program.next_free()
        if rung is None:
            return {"action": "none", "reason": "every rung is resolved or running",
                    "in_flight": [r.rid for r in running]}

        if rung.launchable:
            result = self.launch(rung, dry=dry)
            result["action"] = "launch"
            result["in_flight"] = [r.rid for r in running]
            return result

        staged = self.stage(rung)
        return {"action": "stage", "rung": rung.rid, "status": rung.status,
                "in_flight": [r.rid for r in running],
                "blockers": staged.blockers, "notes": staged.notes,
                "draft": str(staged.draft_path) if staged.draft_path else None}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="osiris-advance", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="auto",
                    choices=("auto", "status", "stage", "launch"))
    ap.add_argument("--rung", help="rung id for stage/launch (default: next free)")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--dry", action="store_true", help="show what would run, launch nothing")
    ap.add_argument("--no-power-gate", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    advancer = Advancer(power_gate=not args.no_power_gate)
    program = advancer.program

    if args.command == "status":
        if args.json:
            print(json.dumps([r.to_dict() for r in program.rungs], indent=1))
        else:
            print("ladder: %s\n" % program.path)
            print(program.summary())
            nxt = program.next_free()
            print("\nnext free rung : %s" % (nxt.rid if nxt else "none"))
            print("in flight      : %s" % (", ".join(r.rid for r in program.in_flight()) or "none"))
        return 0

    if args.command in ("stage", "launch"):
        rung = program.get(args.rung) if args.rung else program.next_free()
        if rung is None:
            print("no such rung: %s" % args.rung, file=sys.stderr)
            return 1
        result = (advancer.stage(rung).to_dict() if args.command == "stage"
                  else advancer.launch(rung, seeds=args.seeds, dry=args.dry))
    else:
        result = advancer.auto_advance(dry=args.dry)

    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

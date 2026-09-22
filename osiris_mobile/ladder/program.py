"""Parse `organism_sim/docs/PROGRAM.md` -- the milestone ladder and its pre-registrations.

The file is the source of truth for what has been decided, so this module reads it and
never writes it. Four facts are extracted per rung:

* whether the ladder cell already records a **PASS** or **FAIL** (the rung is resolved)
* whether a `### <rung> ... (pre-registered <date>)` block exists (a criterion is committed)
* whether that block says "not yet run"
* whether a driver for it is running right now (in flight)

A rung is launchable only when it is unresolved, pre-registered and not in flight.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = ["Rung", "Program", "load_program", "default_program_path"]

_ROW = re.compile(r"^\|\s*(M\d+[a-z]?)\s*\|(.+)\|\s*$")
# Heading ids may be hyphenated (`Substrate-Opt-1`), so the token runs up to the
# dash that separates id from prose, not up to the first hyphen inside the id.
_PREREG = re.compile(r"^###\s+(?P<token>[A-Za-z0-9][A-Za-z0-9\-]*)\s*[—–-]\s+(?P<rest>.*)$")
_RESULT = re.compile(r"\*\*Result\s*\([^)]*\)\s*:\s*\**\s*(PASS|FAIL|BOUNDED)", re.IGNORECASE)
_PREREG_DATE = re.compile(r"pre-registered\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_NOT_RUN = re.compile(r"not\s+(yet\s+)?run", re.IGNORECASE)
_VERDICT = re.compile(r"\*\*\s*(PASS|FAIL|BOUNDED)\b", re.IGNORECASE)
_TITLE = re.compile(r"\*\*(.+?)\*\*")


def default_program_path() -> Path:
    src = Path(os.environ.get("OSIRIS_SRC", str(Path.home() / "osiris-src")))
    for candidate in (src / "organism_sim" / "docs" / "PROGRAM.md",
                      Path.home() / "organism_sim" / "docs" / "PROGRAM.md"):
        if candidate.exists():
            return candidate
    return src / "organism_sim" / "docs" / "PROGRAM.md"


class Rung(object):
    """One milestone, plus everything the ladder file says about its state."""

    __slots__ = ("rid", "title", "metric", "criterion", "verdicts",
                 "prereg_date", "prereg_heading", "prereg_not_run", "in_flight", "driver")

    def __init__(self, rid: str, title: str = "", metric: str = "", criterion: str = "") -> None:
        self.rid = rid
        self.title = title
        self.metric = metric
        self.criterion = criterion
        self.verdicts: List[str] = []
        self.prereg_date: Optional[str] = None
        self.prereg_heading: Optional[str] = None
        self.prereg_not_run = False
        self.in_flight = False
        self.driver: Optional[str] = None

    @property
    def index(self) -> tuple:
        """Sort key: M3 before M3b before M4."""
        match = re.match(r"M(\d+)([a-z]?)", self.rid)
        return (int(match.group(1)), match.group(2) or "") if match else (99, "")

    @property
    def resolved(self) -> bool:
        """The ladder already records an outcome for this rung."""
        return bool(self.verdicts)

    @property
    def pre_registered(self) -> bool:
        return self.prereg_date is not None

    @property
    def status(self) -> str:
        if self.in_flight:
            return "in_flight"
        if self.resolved:
            return "resolved"
        if self.pre_registered:
            return "pre_registered"
        return "available"

    @property
    def launchable(self) -> bool:
        """Unresolved, criterion already committed, nothing running."""
        return self.status == "pre_registered"

    def to_dict(self) -> Dict[str, Any]:
        return {"rung": self.rid, "title": self.title, "status": self.status,
                "verdicts": self.verdicts, "pre_registered": self.pre_registered,
                "prereg_date": self.prereg_date, "in_flight": self.in_flight,
                "driver": self.driver, "criterion": self.criterion[:160]}

    def __repr__(self) -> str:
        return "Rung(%s, %s)" % (self.rid, self.status)


class Program(object):
    """The parsed ladder."""

    def __init__(self, path: Path, rungs: List[Rung], scorecard: List[str]) -> None:
        self.path = path
        self.rungs = sorted(rungs, key=lambda r: r.index)
        self.scorecard = scorecard

    def get(self, rid: str) -> Optional[Rung]:
        for rung in self.rungs:
            if rung.rid.lower() == rid.lower():
                return rung
        return None

    def in_flight(self) -> List[Rung]:
        return [r for r in self.rungs if r.in_flight]

    def next_free(self) -> Optional[Rung]:
        """The lowest rung that is neither resolved nor running.

        Note this is the next rung *to work on*, which is not necessarily launchable --
        it may still need a criterion committed. `Rung.launchable` decides that.
        """
        for rung in self.rungs:
            if rung.status in ("pre_registered", "available"):
                return rung
        return None

    def summary(self) -> str:
        width = max((len(r.rid) for r in self.rungs), default=2)
        lines = []
        for rung in self.rungs:
            mark = {"resolved": "✓", "in_flight": "▶",
                    "pre_registered": "○", "available": "·"}[rung.status]
            lines.append("  %s %-*s %-14s %s" % (mark, width, rung.rid, rung.status,
                                                 rung.title[:52]))
        return "\n".join(lines)


def _running_drivers() -> List[str]:
    """Command lines of experiment drivers running right now.

    This is how M3c is detected as in flight while its five workers are alive, so
    auto-advance steps over it instead of launching a competing run.
    """
    try:
        out = subprocess.run(["ps", "-eo", "args"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    lines = out.stdout.decode("utf-8", errors="replace").splitlines()
    return [ln for ln in lines if "experiments/" in ln and ".py" in ln]


def _rung_from_driver(command: str) -> Optional[str]:
    """Map a driver command line back to a rung id: experiments/m3_ablate.py -> M3c."""
    match = re.search(r"experiments/(m\d+[a-z]?)[_.]", command, re.IGNORECASE)
    if not match:
        return None
    stem = match.group(1).upper()
    # m3_ablate.py is the M3c ablation driver; the file is named for its family, not
    # the rung, so the mapping is explicit rather than guessed.
    if "ablate" in command.lower() and stem == "M3":
        return "M3c"
    return stem


def load_program(path: Optional[Path] = None, detect_running: bool = True) -> Program:
    """Read and parse the ladder."""
    path = Path(path) if path is not None else default_program_path()
    if not path.exists():
        raise FileNotFoundError("PROGRAM.md not found at %s -- set $OSIRIS_SRC" % path)
    text = path.read_text(encoding="utf-8", errors="replace")

    rungs: Dict[str, Rung] = {}
    for line in text.splitlines():
        match = _ROW.match(line.strip())
        if not match:
            continue
        rid = match.group(1)
        cells = [c.strip() for c in match.group(2).split("|")]
        if len(cells) < 4:
            continue
        title_match = _TITLE.search(cells[0])
        rung = Rung(rid,
                    title=(title_match.group(1) if title_match else cells[0])[:120],
                    metric=cells[2], criterion=cells[3])
        rung.verdicts = [v.upper() for v in _VERDICT.findall(cells[3])]
        rungs[rid] = rung

    lines = text.splitlines()

    # The scorecard is the most machine-readable record of outcomes: sub-rungs like M3b
    # and Substrate-Opt-1 have no ladder row of their own, and their verdict lives here.
    scorecard_verdicts: Dict[str, str] = {}
    grabbing = False
    for line in lines:
        if "scorecard:start" in line:
            grabbing = True
            continue
        if "scorecard:end" in line:
            grabbing = False
            continue
        if not grabbing or not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0].startswith("---") or cells[0] == "experiment":
            continue
        key = cells[0].split(":")[0].strip().lower()
        found = _VERDICT.search("**" + cells[1]) or re.match(r"(PASS|FAIL|BOUNDED)", cells[1], re.IGNORECASE)
        if key and found:
            scorecard_verdicts[key] = found.group(1).upper()

    # Pre-registration blocks name their rung in the heading; their body records the result.
    for i, line in enumerate(lines):
        if not line.startswith("### "):
            continue
        date = _PREREG_DATE.search(line)
        if not date:
            continue
        head = _PREREG.match(line.strip())
        token = (head.group("token") if head else line[4:].split()[0]).strip("*` ")
        rung = rungs.get(token)
        if rung is None:
            rung = Rung(token, title=(head.group("rest") if head else line[4:])[:120])
            rungs[token] = rung
        rung.prereg_date = date.group(1)
        rung.prereg_heading = line.strip()
        rung.prereg_not_run = bool(_NOT_RUN.search(line))

        # Body runs to the next heading; a recorded **Result (date): X** resolves the rung.
        body: List[str] = []
        for following in lines[i + 1:]:
            if following.startswith("## ") or following.startswith("### "):
                break
            body.append(following)
        outcome = _RESULT.search("\n".join(body))
        if outcome and outcome.group(1).upper() not in rung.verdicts:
            rung.verdicts.append(outcome.group(1).upper())

    # Finally fold in the scorecard, which outranks nothing but fills the gaps.
    for rid, rung in rungs.items():
        verdict = scorecard_verdicts.get(rid.lower())
        if verdict and verdict not in rung.verdicts:
            rung.verdicts.append(verdict)

    if detect_running:
        for command in _running_drivers():
            rid = _rung_from_driver(command)
            if rid is None:
                continue
            rung = rungs.get(rid) or Rung(rid)
            rung.in_flight = True
            rung.driver = command.strip()[:160]
            rungs[rid] = rung

    scorecard: List[str] = []
    grab = False
    for line in lines:
        if "scorecard:start" in line:
            grab = True
            continue
        if "scorecard:end" in line:
            break
        if grab and line.strip().startswith("|"):
            scorecard.append(line.strip())

    return Program(path, list(rungs.values()), scorecard)

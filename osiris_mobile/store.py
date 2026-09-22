"""osiris_mobile.store — on-device state layout and crash-safe, bounded persistence.

Android's lowmemorykiller reaps the largest-RSS background process without warning and
Doze suspends timers, so nothing durable may live in process memory and no write may be
left half-finished. Everything here is either atomic (``os.replace``) or append-only with
a bounded tail.

All paths live under ``$OSIRIS_HOME`` (default ``~/.osiris``), matching the desktop
layout so ``brain_memory.json`` and ``repo_index.json`` stay interchangeable.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

__all__ = [
    "home", "sub", "ensure", "env_int", "env_flag",
    "atomic_write_json", "read_json", "BoundedJSONL",
]

_SUBDIRS = ("bin", "models", "logs", "results", "checkpoints", "telemetry")


def home() -> Path:
    """Root of on-device OSIRIS state."""
    return Path(os.environ.get("OSIRIS_HOME", str(Path.home() / ".osiris")))


def sub(name: str) -> Path:
    """A known subdirectory of the state root, created on demand."""
    if name not in _SUBDIRS:
        raise KeyError("unknown state subdirectory: %r (expected one of %s)" % (name, ", ".join(_SUBDIRS)))
    p = home() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure() -> Path:
    """Create the full state tree. Idempotent."""
    root = home()
    root.mkdir(parents=True, exist_ok=True)
    for d in _SUBDIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    return root


def env_int(name: str, default: int) -> int:
    """Read an integer from the environment, falling back on anything unparseable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean from the environment. '1', 'true', 'yes', 'on' are true."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def atomic_write_json(path: Path, obj: Any, indent: Optional[int] = None) -> Path:
    """Write JSON so a kill mid-write cannot leave a truncated file.

    Writes a sibling temp file, fsyncs it, then ``os.replace``s it into position --
    atomic within a filesystem. The directory is fsynced too, so the rename survives
    a sudden power loss as well as a process kill.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=indent)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    dirfd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(dirfd)
    except OSError:
        pass                      # some Android filesystems refuse directory fsync
    finally:
        os.close(dirfd)
    return path


def read_json(path: Path, default: Any = None) -> Any:
    """Read JSON, returning `default` if the file is missing or corrupt."""
    try:
        with open(str(path), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


class BoundedJSONL:
    """Append-only JSONL with a hard bound on retained records.

    The bound is the OOM-killer defence named in the mobile survival rules: an unbounded
    AuditChain behind 16 live N=4000 agents exceeds 8 GB. Records are appended cheaply;
    once the file grows past ``limit * slack`` it is compacted down to the last ``limit``
    in one atomic rewrite, so the amortised cost of the bound is one rewrite per
    ``limit * (slack - 1)`` appends.

    ``fsync`` runs every ``sync_every`` appends rather than every append -- a compromise
    between flash wear and losing at most ``sync_every`` records to a kill.
    """

    def __init__(self, path: Path, limit: Optional[int] = None,
                 slack: float = 1.5, sync_every: int = 16) -> None:
        if slack <= 1.0:
            raise ValueError("slack must exceed 1.0, else every append compacts")
        if sync_every < 1:
            raise ValueError("sync_every must be >= 1")
        self.path = Path(path)
        self.limit = limit if limit is not None else env_int("OSIRIS_AUDIT_WINDOW", 512)
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        self.slack = slack
        self.sync_every = sync_every
        self._high_water = max(self.limit + 1, int(self.limit * slack))
        self._since_sync = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._count = self._count_lines()

    def _count_lines(self) -> int:
        try:
            with open(str(self.path), "rb") as fh:
                return sum(1 for line in fh if line.strip())
        except OSError:
            return 0

    def append(self, record: Any) -> None:
        """Append one record, compacting if the file has outgrown its bound."""
        line = json.dumps(record, separators=(",", ":"), default=str)
        with open(str(self.path), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            self._since_sync += 1
            if self._since_sync >= self.sync_every:
                os.fsync(fh.fileno())
                self._since_sync = 0
        self._count += 1
        if self._count > self._high_water:
            self.compact()

    def compact(self) -> int:
        """Rewrite the file keeping only the newest ``limit`` records. Returns the count."""
        kept = self.tail(self.limit)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent),
                                   prefix="." + self.path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for rec in kept:
                    fh.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, str(self.path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self._count = len(kept)
        self._since_sync = 0
        return self._count

    def tail(self, n: int) -> List[Dict[str, Any]]:
        """The newest `n` parseable records, oldest first. Corrupt lines are skipped.

        A torn final line is the normal signature of an OOM kill; it is dropped rather
        than raised, because the telemetry pane must keep rendering after a kill.
        """
        if n <= 0:
            return []
        out: List[Dict[str, Any]] = []
        try:
            with open(str(self.path), "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            return []
        for line in lines[-(n * 2):]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out[-n:]

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        return iter(self.tail(self.limit))

    def __len__(self) -> int:
        return self._count

    def __repr__(self) -> str:
        return "BoundedJSONL(%s, limit=%d, count=%d)" % (self.path.name, self.limit, self._count)

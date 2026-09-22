"""Capture organism / LCS / GRN frames to a bounded JSONL stream.

Wraps ``organism_sim.telemetry.capture_frame`` without modifying it -- the schema stays
whatever organism_sim says it is, so frames written on the phone validate against the
same ``schemas/`` contract as frames written on the desktop.

The stream is a ``BoundedJSONL``: capped by ``OSIRIS_AUDIT_WINDOW`` so a long run cannot
grow telemetry into the OOM killer's sights.
"""

import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..store import BoundedJSONL, sub

__all__ = ["FrameStream", "default_stream_path"]


def default_stream_path(name: str = "live") -> Path:
    """Where the monitor pane looks by default."""
    return sub("telemetry") / ("%s.jsonl" % name)


class FrameStream(object):
    """Append capture_frame() output to a bounded JSONL, with optional decimation.

    `every` decimates: on a Tensor chip a tick can be sub-millisecond, and writing every
    tick makes the stream pure I/O. Only every `every`-th capture is written.
    """

    def __init__(self, path: Optional[Path] = None, limit: Optional[int] = None,
                 every: int = 1) -> None:
        if every < 1:
            raise ValueError("every must be >= 1")
        self.path = Path(path) if path is not None else default_stream_path()
        self.every = every
        self.log = BoundedJSONL(self.path, limit=limit)
        self._seen = 0

    def capture(self, target: Any, tick: int) -> Optional[Dict[str, Any]]:
        """Capture and write one frame. Returns the frame, or None if decimated away."""
        self._seen += 1
        if (self._seen - 1) % self.every:
            return None
        from organism_sim.telemetry import capture_frame  # lazy: organism_sim is optional
        frame = capture_frame(target, tick)
        self.write(frame)
        return frame

    def write(self, frame: Dict[str, Any]) -> None:
        """Write a pre-built frame, stamping wall-clock time for the monitor pane."""
        record = dict(frame)
        record.setdefault("wall", time.time())
        self.log.append(record)

    def note(self, kind: str, **fields: Any) -> None:
        """Write a non-frame event (pause, resume, checkpoint, verdict) into the stream."""
        record = {"kind": kind, "wall": time.time()}
        record.update(fields)
        self.log.append(record)

    def __len__(self) -> int:
        return len(self.log)

    def __repr__(self) -> str:
        return "FrameStream(%s, every=%d)" % (self.path.name, self.every)

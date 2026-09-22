"""The right-hand monitor pane: live organism / LCS / GRN / power telemetry.

Rendered for a terminal whose width changes under you. The Pixel Fold's inner display
gives roughly 90-110 columns; the cover display gives 40-50. Every row here degrades by
dropping columns right-to-left rather than wrapping, because a wrapped table in a 44-column
pane is unreadable.

Run standalone:  python -m osiris_mobile.telemetry.tail [--source FILE] [--interval 2]
"""

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..store import BoundedJSONL, sub

__all__ = ["render", "watch", "newest_stream", "main"]

_CLEAR = "\033[H\033[2J"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"

#: Below this width we are on the cover display; drop to the narrow layout.
NARROW = 60


def newest_stream() -> Optional[Path]:
    """The most recently modified telemetry stream, or None."""
    try:
        candidates = sorted(sub("telemetry").glob("*.jsonl"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    return candidates[0] if candidates else None


def _fit(text: str, width: int) -> str:
    """Truncate to width with an ellipsis rather than wrapping."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[:width - 1] + "…"


def _num(value: Any, fmt: str = "%.3f") -> str:
    try:
        return fmt % float(value)
    except (TypeError, ValueError):
        return "-"


def _power_line(width: int) -> str:
    """One-line power summary. Never blocks the pane if termux-api is slow."""
    from ..power.battery import read_battery
    from ..power.thermal import read_temperature
    state = read_battery(timeout=3.0)
    temp = read_temperature()

    if state is None:
        bits = [_DIM + "power: termux-api unreachable" + _RESET]
    else:
        pct = state.percentage
        colour = _GREEN
        if pct is not None and pct < 20:
            colour = _RED
        elif pct is not None and pct < 40:
            colour = _YELLOW
        bits = ["%sbatt %s%%%s %s" % (colour, pct if pct is not None else "?", _RESET,
                                      "⚡" if not state.on_battery else "▓")]
    if temp is not None:
        tcolour = _RED if temp >= 45 else (_YELLOW if temp >= 40 else _GREEN)
        bits.append("%s%.1f°C%s" % (tcolour, temp, _RESET))
    bits.append(_DIM + time.strftime("%H:%M:%S") + _RESET)
    return _fit("  ".join(bits), width + 40)      # +40 slack for the ANSI escapes


def _frame_row(frame: Dict[str, Any], width: int) -> str:
    """One telemetry frame as a single line, degrading by dropping right-hand columns."""
    kind = frame.get("kind")
    if kind:                                      # a note(), not a capture_frame()
        return _fit("%s%-10s%s %s" % (_CYAN, kind, _RESET,
                                      " ".join("%s=%s" % (k, v) for k, v in sorted(frame.items())
                                               if k not in ("kind", "wall"))), width + 12)

    org = frame.get("organism") or {}
    learner = frame.get("learner") or {}
    reg = frame.get("regulation") or {}

    cols: List[str] = ["t%-5s" % frame.get("tick", "?")]
    if learner:
        cols.append("acc %s" % _num(learner.get("accuracy"), "%.2f"))
        cols.append("pop %-5s" % (learner.get("population") or learner.get("n") or "-"))
    if org:
        cols.append("Ξ %s" % _num(org.get("entropy") or org.get("xi")))
        cols.append("noise %s" % _num(org.get("noise"), "%.2f"))
    if reg:
        cols.append("grn %-3s" % (reg.get("n_genes") or reg.get("genes") or "-"))

    if width < NARROW:                            # cover display: first three columns only
        cols = cols[:3]
    line = "  ".join(cols)
    return _fit(line, width)


def render(source: Optional[Path] = None, width: Optional[int] = None,
           height: Optional[int] = None) -> str:
    """Build one full frame of the monitor pane as a string."""
    if width is None or height is None:
        size = shutil.get_terminal_size(fallback=(80, 24))
        width = width if width is not None else size.columns
        height = height if height is not None else size.lines

    out: List[str] = []
    title = "OSIRIS telemetry" if width >= NARROW else "OSIRIS"
    out.append(_BOLD + _fit(title, width) + _RESET)
    out.append(_power_line(width))
    out.append(_DIM + "─" * max(1, min(width, 120)) + _RESET)

    if source is None:
        source = newest_stream()
    if source is None or not Path(source).exists():
        out.append(_DIM + _fit("no telemetry stream in %s" % sub("telemetry"), width) + _RESET)
        out.append(_DIM + _fit("a run writes one via osiris_mobile.telemetry.FrameStream", width) + _RESET)
        return "\n".join(out)

    out.append(_DIM + _fit("source: %s" % Path(source).name, width) + _RESET)
    budget = max(1, height - len(out) - 1)
    log = BoundedJSONL(Path(source))
    frames = log.tail(budget)
    if not frames:
        out.append(_DIM + _fit("stream is empty", width) + _RESET)
    for frame in frames:
        out.append(_frame_row(frame, width))
    return "\n".join(out)


def watch(source: Optional[Path] = None, interval: float = 2.0,
          iterations: Optional[int] = None) -> int:
    """Redraw the pane every `interval` seconds until interrupted.

    `iterations` bounds the loop, which is what makes this testable.
    """
    count = 0
    try:
        while iterations is None or count < iterations:
            sys.stdout.write(_CLEAR)
            sys.stdout.write(render(source))
            sys.stdout.write("\n")
            sys.stdout.flush()
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        return 130
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="osiris_mobile.telemetry.tail",
                                 description="Live OSIRIS telemetry monitor pane.")
    ap.add_argument("--source", type=Path, default=None,
                    help="JSONL stream to follow (default: newest in $OSIRIS_TELEMETRY)")
    ap.add_argument("--interval", type=float, default=2.0, help="redraw seconds")
    ap.add_argument("--once", action="store_true", help="render one frame and exit")
    args = ap.parse_args(argv)

    if args.once:
        print(render(args.source))
        return 0
    return watch(args.source, args.interval)


if __name__ == "__main__":
    sys.exit(main())

"""termux-notification wrapper with stable, updatable notification ids.

Reusing an id updates the existing notification in place instead of stacking a new one,
which is what makes a long run's progress readable in the shade rather than a wall of
duplicates.
"""

import subprocess
from typing import Optional

__all__ = ["notify", "notify_remove", "NOTIFY_RUN", "NOTIFY_POWER", "NOTIFY_LADDER"]

NOTIFY_RUN = "osiris-run"
NOTIFY_POWER = "osiris-power"
NOTIFY_LADDER = "osiris-ladder"

_CMD = "termux-notification"
_CMD_REMOVE = "termux-notification-remove"


def notify(title: str, content: str = "", nid: str = NOTIFY_RUN,
           ongoing: bool = False, priority: str = "default",
           action: Optional[str] = None, timeout: float = 10.0) -> bool:
    """Post or update a notification. Returns False if the Termux:API bridge is absent.

    `ongoing` marks it non-dismissable, appropriate for a run in flight. `action` is a
    shell command Android runs when the notification is tapped -- used by the ladder
    runner to reopen the tmux session.
    """
    argv = [_CMD, "--id", nid, "--title", title, "--priority", priority]
    if content:
        argv += ["--content", content]
    if ongoing:
        argv += ["--ongoing"]
    if action:
        argv += ["--action", action]
    try:
        out = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0


def notify_remove(nid: str = NOTIFY_RUN, timeout: float = 10.0) -> bool:
    """Dismiss a notification by id."""
    try:
        out = subprocess.run([_CMD_REMOVE, "--id", nid],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0

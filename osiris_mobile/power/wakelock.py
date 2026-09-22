"""termux-wake-lock as a context manager.

Without a wake lock Android's Doze suspends the process' timers minutes after the screen
goes off, so a 4-hour run silently becomes a 40-hour one. The lock is released on exit
even when the body raises -- holding it forever is a battery bug.
"""

import subprocess
from contextlib import contextmanager
from typing import Iterator

__all__ = ["acquire", "release", "wake_lock"]


def _run(cmd: str, timeout: float = 10.0) -> bool:
    try:
        out = subprocess.run([cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0


def acquire(timeout: float = 10.0) -> bool:
    """Take the wake lock. False when termux-api is unavailable."""
    return _run("termux-wake-lock", timeout)


def release(timeout: float = 10.0) -> bool:
    """Drop the wake lock."""
    return _run("termux-wake-unlock", timeout)


@contextmanager
def wake_lock(required: bool = False) -> Iterator[bool]:
    """Hold a wake lock for the duration of the block.

    Yields whether the lock was actually taken. With `required=True` a failure raises,
    for callers that must not run unprotected; the default is to proceed and let the
    caller decide, since a foreground interactive session does not need one.
    """
    held = acquire()
    if not held and required:
        raise RuntimeError(
            "termux-wake-lock unavailable: install the Termux:API APK from F-Droid. "
            "Refusing to start a long run that Doze would suspend."
        )
    try:
        yield held
    finally:
        if held:
            release()

"""Power, thermal and notification governance for on-device research runs.

Android will suspend (Doze), throttle (thermal) or kill (lowmemorykiller) a long run
without asking. This package makes those forces explicit and testable so a heavy
workload pauses deliberately instead of dying halfway through a seed.
"""

from .battery import PowerState, read_battery
from .governor import Decision, Governor
from .notify import notify, notify_remove
from .thermal import read_temperature
from .wakelock import wake_lock

__all__ = [
    "PowerState", "read_battery",
    "read_temperature",
    "Governor", "Decision",
    "notify", "notify_remove",
    "wake_lock",
]

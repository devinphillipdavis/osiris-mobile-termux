"""termux-battery-status -> PowerState.

`pkg install termux-api` installs the CLI; it does nothing until the Termux:API APK is
installed from F-Droid (matching signature) and granted permissions. When the bridge is
absent every reader here returns None, and the caller decides the policy -- this module
never silently invents a battery level.
"""

import json
import subprocess
from typing import Any, Dict, Optional

__all__ = ["PowerState", "read_battery", "api_available"]

_CMD = "termux-battery-status"

# Values Android reports for BatteryManager.EXTRA_PLUGGED. "UNPLUGGED" means on battery.
_PLUGGED_ON_BATTERY = ("UNPLUGGED", "NONE", "")


class PowerState(object):
    """A single battery sample. Immutable by convention."""

    __slots__ = ("percentage", "plugged", "status", "temperature", "health", "raw")

    def __init__(self, percentage: Optional[int], plugged: str, status: str,
                 temperature: Optional[float] = None, health: str = "",
                 raw: Optional[Dict[str, Any]] = None) -> None:
        self.percentage = percentage
        self.plugged = plugged
        self.status = status
        self.temperature = temperature
        self.health = health
        self.raw = raw or {}

    @property
    def on_battery(self) -> bool:
        """True when running off the battery rather than an external supply."""
        return str(self.plugged).upper() in _PLUGGED_ON_BATTERY

    @property
    def charging(self) -> bool:
        return str(self.status).upper() in ("CHARGING", "FULL")

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> "PowerState":
        pct = payload.get("percentage")
        try:
            pct = int(pct) if pct is not None else None
        except (TypeError, ValueError):
            pct = None
        temp = payload.get("temperature")
        try:
            temp = float(temp) if temp is not None else None
        except (TypeError, ValueError):
            temp = None
        return cls(
            percentage=pct,
            plugged=str(payload.get("plugged", "")),
            status=str(payload.get("status", "")),
            temperature=temp,
            health=str(payload.get("health", "")),
            raw=payload,
        )

    def __repr__(self) -> str:
        return "PowerState(%s%%, %s, %s)" % (
            self.percentage if self.percentage is not None else "?",
            "battery" if self.on_battery else "plugged",
            self.status or "?",
        )


def api_available() -> bool:
    """Whether the termux-api CLI is on PATH. Does not prove the APK is responding."""
    try:
        subprocess.check_output(["command", "-v", _CMD], stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, OSError):
        pass
    import shutil
    return shutil.which(_CMD) is not None


def read_battery(timeout: float = 10.0) -> Optional[PowerState]:
    """Sample the battery, or None if the Termux:API bridge is unreachable.

    The timeout matters: when the APK is missing, the CLI can hang rather than exit,
    which would otherwise stall a governor check indefinitely.
    """
    try:
        out = subprocess.run(
            [_CMD],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout:
        return None
    try:
        payload = json.loads(out.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return PowerState.from_json(payload)

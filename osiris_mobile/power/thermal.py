"""CPU/SoC temperature sampling.

Sustained NumPy work on a Tensor chip throttles well before anything crashes, which
silently doubles wall-clock per seed. Reading the thermal zones lets a run pause and
record *why* it paused rather than producing an unexplained slow seed.
"""

import glob
import os
from typing import List, Optional, Tuple

__all__ = ["read_temperature", "zones"]

# Zone type substrings worth watching. Android exposes dozens; battery and skin zones
# lag the die badly, so prefer the CPU/SoC ones when present.
_PREFERRED = ("cpu", "soc", "tsens", "big", "mid", "little", "apc", "gpu")


def zones() -> List[Tuple[str, float]]:
    """Every readable thermal zone as (type, degrees C)."""
    out: List[Tuple[str, float]] = []
    for path in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        try:
            with open(os.path.join(path, "temp"), "r") as fh:
                raw = fh.read().strip()
            with open(os.path.join(path, "type"), "r") as fh:
                kind = fh.read().strip()
        except OSError:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        # Kernels report millidegrees; a few report degrees. 1000 C is not a temperature.
        if value > 1000.0:
            value /= 1000.0
        if -40.0 <= value <= 150.0:
            out.append((kind, value))
    return out


def read_temperature() -> Optional[float]:
    """Hottest preferred zone in degrees C, or the hottest of any zone, or None.

    Falls back to the battery sensor when sysfs is unreadable, which happens on some
    hardened Android builds where /sys/class/thermal is not world-readable.
    """
    found = zones()
    if found:
        preferred = [t for (k, t) in found if any(p in k.lower() for p in _PREFERRED)]
        if preferred:
            return max(preferred)
        return max(t for (_, t) in found)

    from .battery import read_battery
    state = read_battery(timeout=5.0)
    if state is not None and state.temperature is not None:
        return state.temperature
    return None

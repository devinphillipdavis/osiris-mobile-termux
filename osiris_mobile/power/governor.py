"""The power governor: decides whether a heavy workload may run right now.

Policy, and why it is what it is
--------------------------------
The mission directive says "if battery is < 20% or unplugged, pause". Read strictly,
`or` pauses every heavy run whenever the phone is not on a charger -- which is almost
always, and would make the mobile lab useless. The default here is therefore the
engineering reading: pause when **on battery AND below the floor**. Set
``OSIRIS_REQUIRE_PLUGGED=1`` to get the strict reading, where being unplugged alone is
enough to pause.

Hysteresis is not optional. Battery percentage jitters by a point or two under load, so
a bare threshold makes a run flap between paused and running many times a minute, and
each flap costs a tournament generation. Once paused for battery, the governor requires
``OSIRIS_BATTERY_RESUME`` (default 35%) before releasing.

When the Termux:API bridge is unreachable the governor **fails open** by default -- it
reports `unknown` and lets work proceed, because a missing APK should not silently
disable the lab. ``OSIRIS_POWER_FAIL_OPEN=0`` inverts that for unattended runs where
an ungoverned battery drain is worse than not running at all.
"""

import time
from typing import Callable, Optional

from ..store import env_flag, env_int
from .battery import PowerState, read_battery
from .notify import NOTIFY_POWER, notify, notify_remove
from .thermal import read_temperature

__all__ = ["Decision", "Governor"]

RUN = "run"
PAUSE = "pause"
UNKNOWN = "unknown"


class Decision(object):
    """The governor's verdict on one sample."""

    __slots__ = ("action", "reason", "state", "temperature")

    def __init__(self, action: str, reason: str,
                 state: Optional[PowerState] = None,
                 temperature: Optional[float] = None) -> None:
        self.action = action
        self.reason = reason
        self.state = state
        self.temperature = temperature

    @property
    def ok(self) -> bool:
        """True when heavy work may proceed. `unknown` counts as ok (fail-open)."""
        return self.action != PAUSE

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return "Decision(%s: %s)" % (self.action, self.reason)


class Governor(object):
    """Battery- and thermal-aware gate for heavy workers.

    Readers are injectable so the policy can be tested against recorded termux-api JSON
    without a device -- see tests/test_power.py.
    """

    def __init__(self,
                 floor: Optional[int] = None,
                 resume: Optional[int] = None,
                 thermal_ceiling: Optional[int] = None,
                 require_plugged: Optional[bool] = None,
                 fail_open: Optional[bool] = None,
                 battery_reader: Optional[Callable[[], Optional[PowerState]]] = None,
                 thermal_reader: Optional[Callable[[], Optional[float]]] = None) -> None:
        self.floor = floor if floor is not None else env_int("OSIRIS_BATTERY_FLOOR", 20)
        self.resume = resume if resume is not None else env_int("OSIRIS_BATTERY_RESUME", 35)
        self.thermal_ceiling = (thermal_ceiling if thermal_ceiling is not None
                                else env_int("OSIRIS_THERMAL_CEILING", 45))
        self.require_plugged = (require_plugged if require_plugged is not None
                                else env_flag("OSIRIS_REQUIRE_PLUGGED", False))
        self.fail_open = (fail_open if fail_open is not None
                          else env_flag("OSIRIS_POWER_FAIL_OPEN", True))
        self._battery_reader = battery_reader or read_battery
        self._thermal_reader = thermal_reader or read_temperature
        self._paused = False          # hysteresis latch

        if self.resume < self.floor:
            raise ValueError(
                "OSIRIS_BATTERY_RESUME (%d) must be >= OSIRIS_BATTERY_FLOOR (%d), "
                "else the governor cannot release a pause" % (self.resume, self.floor)
            )

    # -- policy ---------------------------------------------------------------
    def check(self) -> Decision:
        """Sample power and thermal state and decide. Updates the hysteresis latch."""
        state = self._battery_reader()
        temp = self._thermal_reader()

        if state is None:
            if self.fail_open:
                return Decision(
                    UNKNOWN,
                    "Termux:API unreachable; failing open (install the Termux:API APK)",
                    None, temp,
                )
            self._paused = True
            return Decision(
                PAUSE, "Termux:API unreachable and OSIRIS_POWER_FAIL_OPEN=0", None, temp)

        if temp is not None and temp >= self.thermal_ceiling:
            self._paused = True
            return Decision(PAUSE, "thermal %.1fC >= ceiling %dC" % (temp, self.thermal_ceiling),
                            state, temp)

        if self.require_plugged and state.on_battery:
            self._paused = True
            return Decision(PAUSE, "on battery and OSIRIS_REQUIRE_PLUGGED=1", state, temp)

        pct = state.percentage
        if pct is None:
            return Decision(UNKNOWN, "battery percentage unreported", state, temp)

        if not state.on_battery:
            # External supply: release any battery-driven pause immediately.
            self._paused = False
            return Decision(RUN, "plugged in (%d%%)" % pct, state, temp)

        # Hysteresis: a run already paused must climb to `resume`, not merely back to
        # `floor`, or percentage jitter under load flaps it many times a minute.
        label = "resume" if self._paused else "floor"
        threshold = self.resume if self._paused else self.floor
        if pct < threshold:
            self._paused = True
            return Decision(
                PAUSE, "on battery at %d%% < %s %d%%" % (pct, label, threshold), state, temp)

        self._paused = False
        return Decision(RUN, "on battery at %d%% (floor %d%%)" % (pct, self.floor), state, temp)

    # -- blocking gate --------------------------------------------------------
    def wait_until_ok(self, poll: float = 60.0, max_wait: Optional[float] = None,
                      announce: bool = True, sleep: Optional[Callable[[float], None]] = None) -> Decision:
        """Block until heavy work may proceed, notifying the user on each transition.

        Returns the releasing Decision. With `max_wait` exceeded, returns the last
        (still-paused) Decision so the caller can checkpoint and exit cleanly rather
        than be killed mid-seed.
        """
        _sleep = sleep or time.sleep
        waited = 0.0
        decision = self.check()
        if decision.ok:
            return decision

        if announce:
            notify("OSIRIS paused", decision.reason, nid=NOTIFY_POWER, ongoing=True,
                   priority="high")

        while not decision.ok:
            if max_wait is not None and waited >= max_wait:
                return decision
            _sleep(poll)
            waited += poll
            decision = self.check()

        if announce:
            notify_remove(NOTIFY_POWER)
            notify("OSIRIS resumed", decision.reason, nid=NOTIFY_POWER)
        return decision

    def __repr__(self) -> str:
        return ("Governor(floor=%d, resume=%d, thermal=%dC, require_plugged=%s, fail_open=%s)"
                % (self.floor, self.resume, self.thermal_ceiling,
                   self.require_plugged, self.fail_open))

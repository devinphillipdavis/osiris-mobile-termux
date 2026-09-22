"""The governor's policy, tested against recorded termux-api payloads -- no device."""

import pytest

from osiris_mobile.power.battery import PowerState
from osiris_mobile.power.governor import PAUSE, RUN, UNKNOWN, Governor


def state(pct, plugged="UNPLUGGED", status="DISCHARGING", temp=None):
    return PowerState.from_json({"percentage": pct, "plugged": plugged,
                                 "status": status, "temperature": temp})


def gov(pct, plugged="UNPLUGGED", temp=30.0, **kw):
    return Governor(battery_reader=lambda: state(pct, plugged),
                    thermal_reader=lambda: temp, **kw)


# -- real termux-battery-status output, for parsing ---------------------------
RECORDED = {
    "health": "GOOD", "percentage": 47, "plugged": "UNPLUGGED",
    "status": "DISCHARGING", "temperature": 29.200000762939453,
}


def test_parses_recorded_payload():
    s = PowerState.from_json(RECORDED)
    assert s.percentage == 47
    assert s.on_battery
    assert not s.charging
    assert s.temperature == pytest.approx(29.2, abs=0.01)


def test_string_percentage_is_coerced():
    assert PowerState.from_json({"percentage": "83", "plugged": "AC"}).percentage == 83


def test_garbage_percentage_does_not_raise():
    assert PowerState.from_json({"percentage": "n/a", "plugged": "AC"}).percentage is None


def test_plugged_in_always_runs_even_when_low():
    assert gov(5, plugged="AC").check().action == RUN


def test_on_battery_below_floor_pauses():
    assert gov(17).check().action == PAUSE


def test_on_battery_above_floor_runs():
    assert gov(64).check().action == RUN


def test_hysteresis_requires_resume_not_floor():
    """Percentage jitters under load; a bare threshold flaps many times a minute."""
    level = {"pct": 17}
    g = Governor(battery_reader=lambda: state(level["pct"]), thermal_reader=lambda: 30.0)
    assert g.check().action == PAUSE
    level["pct"] = 25                       # above floor(20), below resume(35)
    assert g.check().action == PAUSE, "released too early -- hysteresis is not latched"
    level["pct"] = 36
    assert g.check().action == RUN
    level["pct"] = 25                       # latch cleared: floor applies again
    assert g.check().action == RUN


def test_charger_clears_the_latch_immediately():
    s = {"pct": 10, "plug": "UNPLUGGED"}
    g = Governor(battery_reader=lambda: state(s["pct"], s["plug"]), thermal_reader=lambda: 30.0)
    assert g.check().action == PAUSE
    s["plug"] = "AC"
    assert g.check().action == RUN


def test_thermal_ceiling_pauses_regardless_of_charge():
    assert gov(100, plugged="AC", temp=52.0).check().action == PAUSE


def test_require_plugged_is_the_strict_reading():
    """OSIRIS_REQUIRE_PLUGGED=1 restores the directive's literal 'or unplugged'."""
    assert gov(90, require_plugged=True).check().action == PAUSE
    assert gov(90, plugged="AC", require_plugged=True).check().action == RUN


def test_missing_api_fails_open_by_default():
    g = Governor(battery_reader=lambda: None, thermal_reader=lambda: None)
    decision = g.check()
    assert decision.action == UNKNOWN
    assert decision.ok


def test_missing_api_can_fail_closed():
    g = Governor(battery_reader=lambda: None, thermal_reader=lambda: None, fail_open=False)
    assert g.check().action == PAUSE
    assert not g.check().ok


def test_unreadable_percentage_is_unknown_not_pause():
    g = Governor(battery_reader=lambda: state(None), thermal_reader=lambda: 30.0)
    assert g.check().action == UNKNOWN


def test_resume_below_floor_is_rejected():
    with pytest.raises(ValueError):
        Governor(floor=40, resume=10)


def test_wait_until_ok_releases_and_is_bounded():
    level = {"pct": 5}
    g = Governor(battery_reader=lambda: state(level["pct"]), thermal_reader=lambda: 30.0)
    ticks = {"n": 0}

    def fake_sleep(_seconds):
        ticks["n"] += 1
        if ticks["n"] >= 3:
            level["pct"] = 90

    decision = g.wait_until_ok(poll=1.0, announce=False, sleep=fake_sleep)
    assert decision.ok
    assert ticks["n"] == 3


def test_wait_until_ok_gives_up_at_max_wait():
    g = Governor(battery_reader=lambda: state(2), thermal_reader=lambda: 30.0)
    decision = g.wait_until_ok(poll=10.0, max_wait=30.0, announce=False, sleep=lambda _s: None)
    assert not decision.ok, "must return so the caller can checkpoint, not block forever"

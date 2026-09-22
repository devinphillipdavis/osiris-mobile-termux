"""The REPL must gate heavy routes on power and must never execute in dry mode."""

from osiris_mobile.intent import Route, classify
from osiris_mobile.power.battery import PowerState
from osiris_mobile.power.governor import Governor
from osiris_mobile.repl import OsirisREPL


def governor_at(pct, plugged="UNPLUGGED", temp=30.0):
    return Governor(
        battery_reader=lambda: PowerState.from_json(
            {"percentage": pct, "plugged": plugged, "status": "D"}),
        thermal_reader=lambda: temp)


def make(tmp_path, monkeypatch, governor):
    monkeypatch.setenv("OSIRIS_HOME", str(tmp_path))
    return OsirisREPL(dry=True, power_gate=True, governor=governor)


def test_heavy_route_is_blocked_on_low_battery(tmp_path, monkeypatch, capsys):
    repl = make(tmp_path, monkeypatch, governor_at(9))
    assert repl.dispatch(classify("run the mux benchmark phase B")) == 1
    assert "paused" in capsys.readouterr().out


def test_same_route_proceeds_when_plugged_in(tmp_path, monkeypatch, capsys):
    repl = make(tmp_path, monkeypatch, governor_at(9, plugged="AC"))
    assert repl.dispatch(classify("run the mux benchmark phase B")) == 0
    assert "dry-run" in capsys.readouterr().out


def test_light_route_is_never_gated(tmp_path, monkeypatch, capsys):
    repl = make(tmp_path, monkeypatch, governor_at(3))
    repl.dispatch(classify("explain PARAMS16"))
    out = capsys.readouterr().out
    assert "paused" not in out


def test_dry_mode_never_spawns_a_process(tmp_path, monkeypatch, capsys):
    repl = make(tmp_path, monkeypatch, governor_at(90))

    def explode(*_args, **_kwargs):
        raise AssertionError("dry mode executed a subprocess")

    monkeypatch.setattr("subprocess.call", explode)
    repl.dispatch(classify("run the mux benchmark phase B"))
    assert "dry-run" in capsys.readouterr().out


def test_every_route_now_dispatches_to_its_harness(tmp_path, monkeypatch, capsys):
    """Directives D, E and F are wired: each heavy route must reach a real command."""
    repl = make(tmp_path, monkeypatch, governor_at(90))
    for text, expected in [("evolve livlm 30 generations", "livlm_perplexity.py"),
                           ("train the sovereign transformer", "nclm_harness.py"),
                           ("auto advance", "osiris_mobile.ladder.advance"),
                           ("run the mux benchmark", "organism_sim.cli")]:
        assert repl.dispatch(classify(text)) == 0, text
        assert expected in capsys.readouterr().out, text


def test_livlm_control_arm_is_routed(tmp_path, monkeypatch, capsys):
    repl = make(tmp_path, monkeypatch, governor_at(90))
    repl.dispatch(classify("run the livlm perplexity random control"))
    assert "--arm random" in capsys.readouterr().out


def test_no_route_is_left_unwired():
    from osiris_mobile.repl import _PENDING
    assert _PENDING == {}


def test_quit_ends_the_session(tmp_path, monkeypatch):
    repl = make(tmp_path, monkeypatch, governor_at(90))
    assert repl.dispatch(classify("/quit")) == -1
    assert repl.dispatch(classify("/exit")) == -1


def test_status_and_help_do_not_raise(tmp_path, monkeypatch, capsys):
    repl = make(tmp_path, monkeypatch, governor_at(55))
    assert repl.dispatch(classify("/status")) == 0
    assert repl.dispatch(classify("/help")) == 0
    out = capsys.readouterr().out
    assert Route.ORGANISM in out


def test_telemetry_records_the_pause_reason(tmp_path, monkeypatch):
    repl = make(tmp_path, monkeypatch, governor_at(9))
    repl.dispatch(classify("run the mux benchmark phase B"))
    records = repl.stream.log.tail(10)
    assert any(r.get("kind") == "pause" for r in records)

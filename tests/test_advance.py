"""Auto-advance must never manufacture the criterion that authorises it to run."""


from conftest import FIXTURE
from osiris_mobile.ladder import program as prog
from osiris_mobile.ladder.advance import Advancer
from osiris_mobile.power.battery import PowerState
from osiris_mobile.power.governor import Governor


def build(tmp_path, monkeypatch, running=(), pct=90):
    monkeypatch.setenv("OSIRIS_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("OSIRIS_SRC", str(tmp_path / "src"))
    path = tmp_path / "PROGRAM.md"
    path.write_text(FIXTURE, encoding="utf-8")
    monkeypatch.setattr(prog, "_running_drivers", lambda: list(running))
    gov = Governor(
        battery_reader=lambda: PowerState.from_json(
            {"percentage": pct, "plugged": "AC", "status": "CHARGING"}),
        thermal_reader=lambda: 30.0)
    return Advancer(program=prog.load_program(path), governor=gov)


def test_auto_advance_targets_m4_while_m3c_runs(tmp_path, monkeypatch):
    adv = build(tmp_path, monkeypatch,
                running=["python experiments/m3_ablate.py 5"])
    result = adv.auto_advance(dry=True)
    assert result["rung"] == "M4"
    assert result["in_flight"] == ["M3c"]


def test_m4_is_staged_not_launched(tmp_path, monkeypatch):
    adv = build(tmp_path, monkeypatch, running=["python experiments/m3_ablate.py 5"])
    result = adv.auto_advance(dry=True)
    assert result["action"] == "stage"
    assert any("no pre-registration" in b for b in result["blockers"])


def test_launch_refuses_an_unregistered_rung(tmp_path, monkeypatch):
    adv = build(tmp_path, monkeypatch)
    result = adv.launch(adv.program.get("M4"), dry=True)
    assert result["launched"] is False
    assert any("pre-registration" in b for b in result["blockers"])


def test_launch_refuses_a_running_rung(tmp_path, monkeypatch):
    adv = build(tmp_path, monkeypatch, running=["python experiments/m3_ablate.py 5"])
    result = adv.launch(adv.program.get("M3c"), dry=True)
    assert result["launched"] is False


def test_launch_refuses_a_resolved_rung(tmp_path, monkeypatch):
    adv = build(tmp_path, monkeypatch)
    result = adv.launch(adv.program.get("M1"), dry=True)
    assert result["launched"] is False


def test_draft_criterion_is_a_template_not_a_criterion(tmp_path, monkeypatch):
    """If auto-advance could write a usable criterion it would be grading its own homework."""
    adv = build(tmp_path, monkeypatch)
    staged = adv.stage(adv.program.get("M4"))
    assert staged.draft_path is not None
    text = staged.draft_path.read_text()
    assert "TODO" in text
    assert "not a criterion" in text
    assert "PASS ⇔ TODO" in text


def test_low_battery_blocks_a_launch(tmp_path, monkeypatch):
    adv = build(tmp_path, monkeypatch, pct=5)
    adv.governor = Governor(
        battery_reader=lambda: PowerState.from_json(
            {"percentage": 5, "plugged": "UNPLUGGED", "status": "DISCHARGING"}),
        thermal_reader=lambda: 30.0)
    result = adv.launch(adv.program.get("M3c"), dry=True)
    assert result["launched"] is False


def test_stage_is_idempotent(tmp_path, monkeypatch):
    adv = build(tmp_path, monkeypatch)
    first = adv.stage(adv.program.get("M4")).to_dict()
    second = adv.stage(adv.program.get("M4")).to_dict()
    assert first == second

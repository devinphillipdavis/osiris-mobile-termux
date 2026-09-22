"""The ladder parser decides what auto-advance may touch, so it is tested on a fixture
with every shape the real PROGRAM.md uses, and then against the real file if present."""

import os
from pathlib import Path

import pytest

from conftest import FIXTURE
from osiris_mobile.ladder import program as prog


@pytest.fixture
def ladder(tmp_path, monkeypatch):
    path = tmp_path / "PROGRAM.md"
    path.write_text(FIXTURE, encoding="utf-8")
    monkeypatch.setattr(prog, "_running_drivers", lambda: [])
    return prog.load_program(path)


def test_ladder_rows_are_parsed(ladder):
    assert {r.rid for r in ladder.rungs} >= {"M1", "M3", "M4", "M5", "M3b", "M3c"}


def test_bold_verdicts_resolve_a_rung(ladder):
    assert ladder.get("M1").resolved
    assert ladder.get("M3").verdicts == ["FAIL", "PASS"]


def test_rung_without_a_verdict_is_unresolved(ladder):
    """M4's cell states a criterion, not an outcome -- it must not read as resolved."""
    assert not ladder.get("M4").resolved
    assert ladder.get("M4").status == "available"


def test_result_block_resolves_a_sub_rung_with_no_table_row(ladder):
    """M3b's outcome lives in its pre-registration body, not the ladder table."""
    m3b = ladder.get("M3b")
    assert m3b.pre_registered
    assert "PASS" in m3b.verdicts
    assert m3b.status == "resolved"


def test_scorecard_resolves_hyphenated_ids(ladder):
    rung = ladder.get("Substrate-Opt-1")
    assert rung is not None, "hyphenated heading id was truncated"
    assert "BOUNDED" in rung.verdicts


def test_pre_registered_but_unrun_rung_is_launchable(ladder):
    m3c = ladder.get("M3c")
    assert m3c.pre_registered and m3c.prereg_not_run
    assert m3c.status == "pre_registered"
    assert m3c.launchable


def test_next_free_skips_resolved_rungs(ladder):
    assert ladder.next_free().rid == "M3c"


def test_running_driver_marks_a_rung_in_flight(tmp_path, monkeypatch):
    """The M3c case: five workers alive means auto-advance must step over it."""
    path = tmp_path / "PROGRAM.md"
    path.write_text(FIXTURE, encoding="utf-8")
    monkeypatch.setattr(prog, "_running_drivers",
                        lambda: ["../osiris_env/bin/python experiments/m3_ablate.py 5"])
    parsed = prog.load_program(path)
    assert parsed.get("M3c").in_flight
    assert parsed.get("M3c").status == "in_flight"
    assert not parsed.get("M3c").launchable
    assert parsed.next_free().rid == "M4", "must advance past the running rung"


def test_driver_to_rung_mapping():
    assert prog._rung_from_driver("python experiments/m3_ablate.py 5") == "M3c"
    assert prog._rung_from_driver("python experiments/m3_wide.py") == "M3"
    assert prog._rung_from_driver("python something_else.py") is None


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        prog.load_program(tmp_path / "nope.md")


@pytest.mark.skipif(not (Path(os.environ.get("OSIRIS_SRC", "/home/enki"))
                         / "organism_sim" / "docs" / "PROGRAM.md").exists(),
                    reason="real PROGRAM.md not present")
def test_against_the_real_program_file():
    real = prog.load_program(Path(os.environ.get("OSIRIS_SRC", "/home/enki"))
                             / "organism_sim" / "docs" / "PROGRAM.md",
                             detect_running=False)
    assert real.get("M4") is not None and not real.get("M4").resolved
    assert real.get("M3b").resolved, "M3b PASSED and must not be offered as next"
    assert real.get("M3c").pre_registered

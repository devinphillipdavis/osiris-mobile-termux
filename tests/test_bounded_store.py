"""Bounded, crash-safe persistence -- the OOM-killer and mid-write-kill defences."""

import json

import pytest

from osiris_mobile.store import (
    BoundedJSONL,
    atomic_write_json,
    env_flag,
    env_int,
    read_json,
)


@pytest.fixture
def log(tmp_path):
    return BoundedJSONL(tmp_path / "t.jsonl", limit=10, slack=1.5, sync_every=4)


def test_bound_is_never_exceeded_on_disk(log):
    """The whole point: 16 live N=4000 agents with unbounded chains exceed 8 GB."""
    for i in range(500):
        log.append({"i": i})
        on_disk = sum(1 for line in open(str(log.path)) if line.strip())
        assert on_disk <= log._high_water, "file grew past the compaction trigger"
    assert len(log) <= log._high_water


def test_compaction_keeps_the_newest_records(log):
    for i in range(200):
        log.append({"i": i})
    kept = log.tail(10)
    assert [r["i"] for r in kept] == list(range(190, 200))


def test_tail_is_oldest_first(log):
    for i in range(5):
        log.append({"i": i})
    assert [r["i"] for r in log.tail(5)] == [0, 1, 2, 3, 4]


def test_tail_of_zero_or_negative_is_empty(log):
    log.append({"i": 1})
    assert log.tail(0) == []
    assert log.tail(-3) == []


def test_torn_final_line_is_skipped_not_raised(log):
    """A truncated last line is the normal signature of an OOM kill; the monitor pane
    must keep rendering after one."""
    for i in range(3):
        log.append({"i": i})
    with open(str(log.path), "a") as fh:
        fh.write('{"i": 3, "part')          # killed mid-write
    records = log.tail(10)
    assert [r["i"] for r in records] == [0, 1, 2]


def test_interior_corrupt_line_is_skipped(log):
    log.append({"i": 0})
    with open(str(log.path), "a") as fh:
        fh.write("not json at all\n")
    log.append({"i": 2})
    assert [r["i"] for r in log.tail(10)] == [0, 2]


def test_count_survives_reopen(tmp_path):
    first = BoundedJSONL(tmp_path / "r.jsonl", limit=50)
    for i in range(7):
        first.append({"i": i})
    second = BoundedJSONL(tmp_path / "r.jsonl", limit=50)
    assert len(second) == 7
    assert [r["i"] for r in second.tail(3)] == [4, 5, 6]


def test_missing_file_reads_as_empty(tmp_path):
    assert BoundedJSONL(tmp_path / "absent.jsonl", limit=5).tail(5) == []


def test_non_serialisable_values_do_not_crash_a_run(log):
    class Opaque:
        def __repr__(self):
            return "<opaque>"

    log.append({"obj": Opaque()})
    assert log.tail(1)[0]["obj"] == "<opaque>"


def test_rejects_degenerate_configuration(tmp_path):
    with pytest.raises(ValueError):
        BoundedJSONL(tmp_path / "a.jsonl", limit=10, slack=1.0)
    with pytest.raises(ValueError):
        BoundedJSONL(tmp_path / "b.jsonl", limit=0)
    with pytest.raises(ValueError):
        BoundedJSONL(tmp_path / "c.jsonl", limit=10, sync_every=0)


def test_atomic_write_leaves_no_partial_file(tmp_path):
    target = tmp_path / "check.json"
    atomic_write_json(target, {"seed": 70, "annecs": 34})
    assert json.loads(target.read_text()) == {"seed": 70, "annecs": 34}
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_atomic_write_replaces_in_place(tmp_path):
    target = tmp_path / "check.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})
    assert read_json(target) == {"v": 2}


def test_atomic_write_failure_cleans_up_its_temp(tmp_path):
    class Unserialisable:
        pass

    target = tmp_path / "bad.json"
    with pytest.raises(TypeError):
        atomic_write_json(target, {"x": Unserialisable()})
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_read_json_tolerates_corruption(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ truncated")
    assert read_json(bad, default={"fallback": True}) == {"fallback": True}
    assert read_json(tmp_path / "missing.json") is None


def test_env_helpers(monkeypatch):
    monkeypatch.setenv("OSIRIS_TEST_INT", "512")
    assert env_int("OSIRIS_TEST_INT", 1) == 512
    monkeypatch.setenv("OSIRIS_TEST_INT", "not-a-number")
    assert env_int("OSIRIS_TEST_INT", 7) == 7
    monkeypatch.delenv("OSIRIS_TEST_INT")
    assert env_int("OSIRIS_TEST_INT", 7) == 7

    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("OSIRIS_TEST_FLAG", truthy)
        assert env_flag("OSIRIS_TEST_FLAG") is True
    for falsy in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("OSIRIS_TEST_FLAG", falsy)
        assert env_flag("OSIRIS_TEST_FLAG") is False


def test_audit_window_env_is_the_default_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("OSIRIS_AUDIT_WINDOW", "32")
    assert BoundedJSONL(tmp_path / "w.jsonl").limit == 32

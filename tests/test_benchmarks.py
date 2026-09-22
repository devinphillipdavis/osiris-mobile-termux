"""Directive D and E harnesses. Heavy model imports are lazy, so these run without
`osiris` installed; the numerics that decide a verdict are tested directly."""


import numpy as np
import pytest

from bench import livlm_perplexity as lp
from bench import nclm_harness as nh


# ── LivLM: the distribution actually scored ──────────────────────────────────
def test_model_distribution_is_normalised():
    rng = np.random.RandomState(0)
    probs = rng.dirichlet(np.ones(256))
    out = lp.model_distribution(probs, "def evolve(", coherence=0.4)
    assert out.shape == (256,)
    assert float(out.sum()) == pytest.approx(1.0, abs=1e-9)
    assert (out >= 0).all()


def test_high_coherence_uses_the_raw_born_vector():
    """At Lambda >= 0.8 the decoder does not mix, so neither may the scorer."""
    probs = np.random.RandomState(1).dirichlet(np.ones(256))
    assert np.array_equal(lp.model_distribution(probs, "abc", 0.8), probs)
    assert np.array_equal(lp.model_distribution(probs, "", 0.1), probs)


def test_low_coherence_lifts_printable_bytes():
    """This is the confound LivLM-PPL-1 measured: the mix favours printable bytes."""
    probs = np.full(256, 1.0 / 256.0)
    mixed = lp.model_distribution(probs, "hello world", coherence=0.2)
    printable = float(sum(mixed[c] for c in lp.PRINTABLE))
    assert printable > (len(lp.PRINTABLE) / 256.0), "bias did not favour printable bytes"


# ── LivLM: baselines ─────────────────────────────────────────────────────────
def test_uniform_baseline_is_exactly_256():
    base = lp.baselines(b"the quick brown fox " * 20, b"the quick brown fox")
    assert base["uniform"] == 256.0


def test_order1_beats_order0_on_repetitive_text():
    train = b"abababababababab" * 40
    base = lp.baselines(train, b"abababab")
    assert base["order1"] < base["order0"] < 256.0


def test_split_is_eighty_twenty_and_disjoint():
    data = bytes(range(256)) * 10
    train, held = lp.split(data)
    assert len(train) == int(len(data) * lp.TRAIN_FRACTION)
    assert len(train) + len(held) == len(data)
    assert train + held == data


# ── LivLM: the pre-registered criterion ──────────────────────────────────────
def rows(ppls):
    return [{"seed": 300 + i, "livlm_ppl": p, "beats_uniform": p < 256.0,
             "baseline_order0": 32.5, "baseline_order1": 16.6}
            for i, p in enumerate(ppls)]


def test_verdict_pass_needs_median_and_four_of_five():
    assert lp.verdict(rows([120, 121, 122, 123, 124]))["verdict"] == "PASS"


def test_verdict_fails_when_too_few_seeds_beat_uniform():
    assert lp.verdict(rows([120, 121, 300, 301, 302]))["verdict"] == "FAIL"


def test_verdict_fails_on_median_even_with_four_below():
    """Four below uniform but a median at/above it must still fail."""
    result = lp.verdict(rows([10, 20, 300, 30, 40]))
    assert result["seeds_below_uniform"] == "4/5"
    assert result["verdict"] == "PASS"       # median 30 < 256: both clauses hold


def test_wrong_seed_count_is_unjudged_not_failed():
    """A 2-seed tuning run must not manufacture a FAIL from the seed count alone."""
    result = lp.verdict(rows([100, 110]))
    assert result["verdict"].startswith("UNJUDGED")


def test_evaluation_seeds_are_frozen():
    assert lp.EVAL_SEEDS == (300, 301, 302, 303, 304)
    assert lp.EXPECTED_PARAMS == 24 * lp.N_LAYERS == 72


def test_judged_run_refuses_unregistered_seeds():
    assert lp.main(["--seeds", "7", "--corpus", "."]) == 2


def test_random_control_genome_is_deterministic_and_sized():
    a, meta = lp.random_genome(300)
    b, _ = lp.random_genome(300)
    assert a.shape == (72,) and np.array_equal(a, b)
    assert not np.array_equal(a, lp.random_genome(301)[0])
    assert meta["arm"] == "random"


# ── NCLM harness ─────────────────────────────────────────────────────────────
def test_atomic_npz_round_trips(tmp_path):
    target = tmp_path / "ckpt.npz"
    payload = {"p0": np.arange(6.0).reshape(2, 3), "m0": np.ones((2, 3))}
    nh._atomic_npz(target, payload)
    with np.load(str(target)) as blob:
        assert np.array_equal(blob["p0"], payload["p0"])
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_atomic_npz_overwrites_in_place(tmp_path):
    target = tmp_path / "ckpt.npz"
    nh._atomic_npz(target, {"p0": np.zeros(4)})
    nh._atomic_npz(target, {"p0": np.ones(4)})
    with np.load(str(target)) as blob:
        assert np.array_equal(blob["p0"], np.ones(4))


def test_failed_write_leaves_the_previous_checkpoint_intact(tmp_path, monkeypatch):
    """The guarantee that matters on Android: a kill or error mid-save must not destroy
    the checkpoint that was already good."""
    target = tmp_path / "ckpt.npz"
    nh._atomic_npz(target, {"p0": np.ones(4)})

    def boom(*_args, **_kwargs):
        raise OSError("ENOSPC")

    monkeypatch.setattr(nh.np, "savez", boom)
    with pytest.raises(OSError):
        nh._atomic_npz(target, {"p0": np.zeros(4)})

    with np.load(str(target)) as blob:
        assert np.array_equal(blob["p0"], np.ones(4)), "a failed write damaged the good file"
    assert not [q for q in tmp_path.iterdir() if q.name.endswith(".tmp")], "temp file leaked"


def test_config_merges_overrides_and_ignores_none(tmp_path, monkeypatch):
    monkeypatch.setenv("OSIRIS_HOME", str(tmp_path))
    cfg = nh.MobileNCLMConfig(dim=None, n_layers=6, checkpoint_every=7)
    assert cfg.dim == nh.DEFAULTS["dim"]
    assert cfg.n_layers == 6
    assert cfg.checkpoint_every == 7


def test_rss_reader_returns_a_number_or_none():
    value = nh._rss_mb()
    assert value is None or value > 0

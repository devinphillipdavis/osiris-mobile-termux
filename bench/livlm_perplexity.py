#!/usr/bin/env python3
"""Directive E -- LivLM-PPL-1: held-out byte perplexity for 72 evolved gate angles.

Criterion is pre-registered in docs/PRE_REGISTRATION.md and was committed before this
file was written. Do not edit the criterion here; edit nothing after an evaluation run.

What is measured
----------------
LivLM's generation circuit at ``n_layers=3`` has exactly ``24 * 3 = 72`` learnable gate
rotation angles (``GenerationCircuit``, osiris_livlm.py:251). Executing it leaves an
8-qubit register whose Born-rule distribution over the 256 basis states *is* a normalized
categorical over the byte vocabulary -- verified to sum to 1.0 within 1e-9. So

    PPL = exp( mean_i( -ln P(b_i | context_i) ) )

is a real likelihood, not a metaphor. Contexts are teacher-forced with the true preceding
bytes, so this measures likelihood assignment and not generation quality.

This is a claim about a classical state-vector simulation. It is not a physical claim.

    python bench/livlm_perplexity.py --seeds 300 301 302 303 304      # evaluation
    python bench/livlm_perplexity.py --seeds 310 --tuning             # tuning only
    python bench/livlm_perplexity.py --verdict                        # score saved results
"""

import argparse
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from osiris_mobile.power import Governor  # noqa: E402
from osiris_mobile.store import BoundedJSONL, atomic_write_json, read_json, sub  # noqa: E402

__all__ = ["evaluate_seed", "baselines", "verdict", "main"]

# ── Pre-registered constants. Changing any of these invalidates the registration. ──
EVAL_SEEDS = (300, 301, 302, 303, 304)
TUNING_SEEDS = (310, 311, 312, 313, 314)
N_LAYERS = 3                  # -> 72 parameters
EXPECTED_PARAMS = 72
TRAIN_FRACTION = 0.8
UNIFORM_PPL = 256.0           # by construction: exp(-ln(1/256))
PASS_MIN_SEEDS = 4            # of 5
RESULTS_NAME = "livlm_ppl1_eval_seeds300-304.json"


def load_corpus_bytes(root: Path, extensions=(".py", ".md", ".txt"),
                      max_bytes: int = 600_000) -> bytes:
    """Deterministic byte corpus: sorted paths, bounded total."""
    chunks: List[bytes] = []
    total = 0
    for path in sorted(Path(root).rglob("*")):
        if total >= max_bytes:
            break
        if not path.is_file() or path.suffix not in extensions:
            continue
        if any(part.startswith(".") or part == "__pycache__" for part in path.parts):
            continue
        try:
            blob = path.read_bytes()[: max_bytes - total]
        except OSError:
            continue
        chunks.append(blob)
        total += len(blob)
    if total < 2000:
        raise ValueError("corpus under %s is too small (%d bytes)" % (root, total))
    return b"".join(chunks)


def split(data: bytes) -> Tuple[bytes, bytes]:
    """80/20 by byte offset. Held-out bytes are never seen by the GA or the baselines."""
    cut = int(len(data) * TRAIN_FRACTION)
    return data[:cut], data[cut:]


def baselines(train: bytes, held: bytes) -> Dict[str, float]:
    """Uniform, order-0 and order-1 byte models, add-1 smoothed, fitted on train only."""
    counts0 = np.ones(256, dtype=np.float64)                  # add-1
    for b in train:
        counts0[b] += 1.0
    p0 = counts0 / counts0.sum()

    counts1 = np.ones((256, 256), dtype=np.float64)           # add-1
    prev = None
    for b in train:
        if prev is not None:
            counts1[prev, b] += 1.0
        prev = b
    p1 = counts1 / counts1.sum(axis=1, keepdims=True)

    nll0 = 0.0
    nll1 = 0.0
    prev = None
    for b in held:
        nll0 += -math.log(p0[b])
        nll1 += -math.log(p1[prev, b]) if prev is not None else -math.log(p0[b])
        prev = b
    n = len(held)
    return {
        "uniform": UNIFORM_PPL,
        "order0": float(math.exp(nll0 / n)),
        "order1": float(math.exp(nll1 / n)),
    }


def evolve_genome(train: bytes, seed: int, population: int, generations: int,
                  sample_length: int, log: Optional[BoundedJSONL] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Evolve the 72 angles on the train split only.

    The train bytes are written to a scratch directory and LivLM's own ``load_corpus`` is
    pointed at it, so the split is enforced through the public API rather than by reaching
    into Corpus internals.
    """
    from osiris_livlm import LivLM, LivLMConfig

    np.random.seed(seed)
    config = LivLMConfig(n_layers=N_LAYERS, population_size=population,
                         max_generations=generations, sample_length=sample_length)
    model = LivLM(config)
    if model.gen_circuit.n_params != EXPECTED_PARAMS:
        raise AssertionError(
            "pre-registration names %d parameters; circuit reports %d"
            % (EXPECTED_PARAMS, model.gen_circuit.n_params))

    started = time.time()
    with tempfile.TemporaryDirectory(prefix="livlm-train-") as tmp:
        (Path(tmp) / "train.txt").write_bytes(train)
        model.load_corpus(tmp)

        def _cb(gen, best):
            if log is not None:
                log.append({"kind": "livlm_gen", "seed": seed, "gen": int(gen),
                            "fitness": float(best.fitness), "phi": float(best.phi)})

        model.evolve(callback=_cb, verbose=False)

    genome = np.asarray(model._genome, dtype=np.float64).copy()
    return genome, {"evolve_s": round(time.time() - started, 1),
                    "generations": generations, "population": population}


PRINTABLE = set(range(32, 127)) | {9, 10, 13}
_IDX = np.arange(256)


def model_distribution(probs: np.ndarray, prev_chars: str, coherence: float) -> np.ndarray:
    """The distribution LivLM actually generates from, as a normalized 256-vector.

    Faithful vectorised replica of ``TextDecoder.decode_with_coherence_bias``
    (osiris_livlm.py:186) with the terminal ``np.random.choice`` removed. When coherence
    Lambda >= 0.8 the raw Born distribution is used; below that the decoder mixes in a
    context bias, and *that mixture* is the model's real predictive distribution.
    Scoring the raw Born vector instead would understate the model.
    """
    if not prev_chars or coherence >= 0.8:
        return probs
    bias = np.zeros(256, dtype=np.float64)
    spread = 50.0 * (1.0 - coherence + 0.01)
    for ch in prev_chars[-8:]:
        b = ord(ch) if ord(ch) < 256 else 32
        delta = np.abs(_IDX - b)
        bias += np.exp(-np.minimum(delta, 256 - delta) ** 2 / spread)
    for code in PRINTABLE:
        bias[code] += 0.1
    bias /= (bias.sum() + 1e-30)
    mixed = coherence * probs + (1.0 - coherence) * bias
    return mixed / mixed.sum()


def heldout_nll(genome: np.ndarray, held: bytes, seed_text: str,
                healing_interval: int = 8) -> Tuple[float, int, float]:
    """Teacher-forced negative log-likelihood of the held-out bytes.

    Mirrors ``LivLM.generate``'s per-step construction exactly -- encode context, build
    the parameterised circuit, inject memory phases, execute -- but reads the full
    probability vector and scores the *true* byte instead of sampling one.
    """
    from osiris_livlm import GenerationCircuit, PhaseMemory, TextEncoder
    from qbyte_system.sovereign_executor import SovereignExecutor

    encoder = TextEncoder()
    circuit_tpl = GenerationCircuit(n_layers=N_LAYERS)
    executor = SovereignExecutor(n_qubits=8, enable_healing=True, enable_ccce=True)

    memory = PhaseMemory(capacity=128)
    for ch in seed_text:
        memory.record(ord(ch))

    total = 0.0
    total_raw = 0.0
    scored = 0
    for step, true_byte in enumerate(held):
        angles = encoder.encode_context(memory.context_str)
        circuit = circuit_tpl.build(angles, genome)
        memory.inject_into_circuit(circuit)
        result = executor.run(circuit, shots=0, return_statevector=True)

        probs = result.probabilities
        if probs is None:
            continue
        coherence = float((result.metrics or {}).get("\u039b", 1.0))
        dist = model_distribution(probs, memory.context_str, coherence)

        # Floor at the smallest positive double so a zero-probability byte contributes a
        # large finite penalty rather than an infinity that would void the whole seed.
        total += -math.log(max(float(dist[true_byte]), 1e-300))
        total_raw += -math.log(max(float(probs[true_byte]), 1e-300))
        scored += 1

        memory.record(true_byte)                       # teacher forcing
        if (step + 1) % healing_interval == 0:
            memory.heal()
    return total, scored, total_raw


def random_genome(seed: int) -> Tuple[np.ndarray, Dict[str, Any]]:
    """LivLM-PPL-2 control arm: 72 angles drawn uniformly, no GA.

    Holds the decoder fixed so its printable-byte bias appears in both arms and cancels.
    """
    rng = np.random.RandomState(seed)
    return rng.uniform(-np.pi, np.pi, EXPECTED_PARAMS), {
        "evolve_s": 0.0, "generations": 0, "population": 0, "arm": "random"}


def evaluate_seed(seed: int, corpus_root: Path, n_heldout: int, population: int,
                  generations: int, sample_length: int,
                  log: Optional[BoundedJSONL] = None, arm: str = "evolved") -> Dict[str, Any]:
    """One seed end to end: split, fit the genome, score held-out, compare baselines."""
    data = load_corpus_bytes(corpus_root)
    train, held_all = split(data)
    held = held_all[:n_heldout]

    if arm == "random":
        genome, meta = random_genome(seed)
    else:
        genome, meta = evolve_genome(train, seed, population, generations, sample_length, log)
        meta["arm"] = "evolved"
    started = time.time()
    nll, scored, nll_raw = heldout_nll(genome, held, seed_text="# ")
    if scored == 0:
        raise RuntimeError("no held-out byte was scored; the executor returned no probabilities")

    ppl = float(math.exp(nll / scored))
    ppl_raw = float(math.exp(nll_raw / scored))
    base = baselines(train, held)
    row = {
        "seed": seed, "arm": arm, "n_params": EXPECTED_PARAMS, "n_layers": N_LAYERS,
        "train_bytes": len(train), "heldout_bytes": scored,
        "livlm_ppl": round(ppl, 4),
        "livlm_ppl_raw_born": round(ppl_raw, 4),
        "baseline_uniform": round(base["uniform"], 4),
        "baseline_order0": round(base["order0"], 4),
        "baseline_order1": round(base["order1"], 4),
        "beats_uniform": bool(ppl < UNIFORM_PPL),
        "ratio_to_uniform": round(ppl / base["uniform"], 4),
        "ratio_to_order0": round(ppl / base["order0"], 4),
        "score_s": round(time.time() - started, 1),
    }
    row.update(meta)
    if log is not None:
        log.append({"kind": "livlm_seed", **row})
    return row


def verdict(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply the pre-registered criterion. No other rule may decide this."""
    ppls = sorted(float(r["livlm_ppl"]) for r in rows)
    median = ppls[len(ppls) // 2] if len(ppls) % 2 else (ppls[len(ppls) // 2 - 1] + ppls[len(ppls) // 2]) / 2.0
    n_beat = sum(1 for r in rows if r["beats_uniform"])
    # The criterion is defined over the five pre-registered evaluation seeds. Applying it
    # to a smaller tuning set would manufacture a FAIL purely from the seed count, so a
    # non-conforming run is reported UNJUDGED rather than given a verdict it cannot earn.
    if len(rows) != len(EVAL_SEEDS):
        label = "UNJUDGED (criterion needs %d seeds; got %d)" % (len(EVAL_SEEDS), len(rows))
    else:
        label = "PASS" if (median < UNIFORM_PPL and n_beat >= PASS_MIN_SEEDS) else "FAIL"
    return {
        "experiment": "LivLM-PPL-1",
        "verdict": label,
        "median_ppl": round(median, 4),
        "uniform": UNIFORM_PPL,
        "seeds_below_uniform": "%d/%d" % (n_beat, len(rows)),
        "criterion": "median < 256.0 AND >= %d/5 seeds < 256.0" % PASS_MIN_SEEDS,
        "median_order0": round(sorted(float(r["baseline_order0"]) for r in rows)[len(rows) // 2], 4),
        "median_order1": round(sorted(float(r["baseline_order1"]) for r in rows)[len(rows) // 2], 4),
        "seeds": [r["seed"] for r in rows],
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="livlm_perplexity", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=list(EVAL_SEEDS))
    ap.add_argument("--corpus", type=Path,
                    default=Path(os.environ.get("OSIRIS_SRC", str(Path.home() / "osiris-src"))))
    ap.add_argument("--heldout", type=int, default=384, help="held-out bytes scored per seed")
    ap.add_argument("--population", type=int, default=20)
    ap.add_argument("--generations", type=int, default=8)
    ap.add_argument("--sample-length", type=int, default=16)
    ap.add_argument("--tuning", action="store_true",
                    help="tuning run: results are NOT written to the judged results file")
    ap.add_argument("--verdict", action="store_true", help="score the saved results and exit")
    ap.add_argument("--arm", choices=("evolved", "random"), default="evolved",
                    help="random = the LivLM-PPL-2 control (no GA)")
    ap.add_argument("--no-power-gate", action="store_true")
    args = ap.parse_args(argv)

    out_path = sub("results") / RESULTS_NAME
    if getattr(args, "arm", "evolved") == "random":
        out_path = sub("results") / RESULTS_NAME.replace(".json", "_random.json")

    if args.verdict:
        saved = read_json(out_path)
        if not saved:
            print("no results at %s" % out_path, file=sys.stderr)
            return 1
        print(json.dumps(verdict(saved["rows"]), indent=1))
        return 0

    judged = not args.tuning
    if judged and sorted(args.seeds) != sorted(EVAL_SEEDS):
        print("refusing: %s are not the pre-registered evaluation seeds %s.\n"
              "Use --tuning for any other seed set."
              % (args.seeds, list(EVAL_SEEDS)), file=sys.stderr)
        return 2

    if not args.no_power_gate:
        decision = Governor().check()
        if not decision.ok:
            print("refusing to start: %s" % decision.reason, file=sys.stderr)
            return 3

    log = BoundedJSONL(sub("telemetry") / "livlm_ppl.jsonl")
    rows: List[Dict[str, Any]] = []
    started = time.time()
    print("LivLM-PPL-1 | %d params | seeds %s | %s"
          % (EXPECTED_PARAMS, args.seeds, "TUNING (not judged)" if args.tuning else "EVALUATION"))

    for seed in args.seeds:
        row = evaluate_seed(seed, args.corpus, args.heldout, args.population,
                            args.generations, args.sample_length, log, arm=args.arm)
        rows.append(row)
        # Per-seed checkpoint: a kill mid-sweep loses one seed, not the sweep.
        atomic_write_json(sub("checkpoints") / ("livlm_ppl1_%s_seed%d.json" % (args.arm, seed)), row, indent=1)
        print("  seed %d  PPL %9.2f  (uniform %.1f, order0 %7.2f, order1 %7.2f)  %s  %.0fs"
              % (seed, row["livlm_ppl"], row["baseline_uniform"], row["baseline_order0"],
                 row["baseline_order1"], "below" if row["beats_uniform"] else "ABOVE",
                 row["evolve_s"] + row["score_s"]))

    result = verdict(rows)
    payload = {"pre_registration": "docs/PRE_REGISTRATION.md#livlm-ppl-1",
               "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "judged": judged, "wall_s": round(time.time() - started, 1),
               "verdict": result, "rows": rows}
    if judged:
        atomic_write_json(out_path, payload, indent=1)
        for seed in args.seeds:
            (sub("checkpoints") / ("livlm_ppl1_%s_seed%d.json" % (args.arm, seed))).unlink(missing_ok=True)
        print("\nwrote %s" % out_path)
    else:
        print("\ntuning run -- not written to %s" % out_path)

    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

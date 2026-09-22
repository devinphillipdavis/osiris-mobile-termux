#!/usr/bin/env python3
"""Directive D -- SovereignTransformer training and inference on Termux.

NumPy, not PyTorch. ``osiris.nclm`` already carries its own reverse-mode autograd
(``autograd.Tensor``), layers, AdamW and byte-level dataset, so a torch dependency on
Termux would be ~250 MB of aarch64 wheels bought for nothing. This harness supplies
only what the desktop trainer does not: per-step telemetry into the fold pane, power
gating, an RSS ceiling, and exact-resume checkpoints written atomically.

``osiris.nclm.trainer.Trainer`` is not used because its ``train()`` is a closed blocking
loop with no per-step hook. The loop here is built from the same published primitives,
so nothing in the research package is modified or shadowed.

Phase-conjugate telemetry (the Directive's requirement) comes from the V2 model's own
instruments: ``NegentropicTracker`` (Xi, Phi, Gamma, Lambda_Phi per forward pass) and
``consciousness_phi``. Torsion-lock and phase-conjugate correction are on by default so
those instruments have something to read.

    python bench/nclm_harness.py train --steps 200 --corpus ~/osiris-src/organism_sim
    python bench/nclm_harness.py infer --prompt "def evolve(" --tokens 96
    python bench/nclm_harness.py config
"""

import argparse
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from zipfile import BadZipFile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from osiris_mobile.power import Governor  # noqa: E402
from osiris_mobile.power.notify import NOTIFY_RUN, notify  # noqa: E402
from osiris_mobile.store import atomic_write_json, env_int, read_json, sub  # noqa: E402
from osiris_mobile.telemetry.stream import FrameStream  # noqa: E402

__all__ = ["MobileNCLMConfig", "NCLMHarness", "main"]

#: Mobile default. ~1.2 M parameters: it fits in a few hundred MB of working set with
#: batch 4 x seq 128, which is what keeps Android's lowmemorykiller uninterested.
DEFAULTS = dict(dim=128, n_layers=4, n_heads=4, ff_dim=256, max_seq_len=128,
                batch_size=4, seq_len=128, lr=3e-4, weight_decay=0.01, grad_clip=1.0,
                warmup_steps=50)


def _rss_mb() -> Optional[float]:
    """Resident set size in MB from /proc, or None where /proc is unavailable."""
    try:
        with open("/proc/self/statm", "r") as fh:
            pages = int(fh.read().split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return pages * (os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096) / (1024 * 1024)


def _atomic_npz(path: Path, arrays: Dict[str, np.ndarray]) -> None:
    """Save an .npz so a kill mid-write cannot leave a truncated checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        # Write through the open handle. Passing np.savez a *path* would make it append
        # ".npz", leaving the real data beside the empty mkstemp file -- and renaming the
        # empty one over the checkpoint, which reads back as EOFError on resume.
        with os.fdopen(fd, "wb") as fh:
            np.savez(fh, **arrays)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class MobileNCLMConfig(object):
    """Harness-level knobs. Model hyper-parameters live in SovereignConfig."""

    def __init__(self, **kw: Any) -> None:
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in kw.items() if v is not None})
        for key, value in merged.items():
            setattr(self, key, value)
        self.checkpoint_every = int(kw.get("checkpoint_every") or 25)
        self.gate_every = int(kw.get("gate_every") or 25)
        self.telemetry_every = int(kw.get("telemetry_every") or 5)
        self.rss_ceiling_mb = int(kw.get("rss_ceiling_mb")
                                  or env_int("OSIRIS_RSS_CEILING_MB", 1500))

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in sorted(vars(self).items())}


class NCLMHarness(object):
    """Train and sample a SovereignTransformerV2 under mobile constraints."""

    def __init__(self, config: Optional[MobileNCLMConfig] = None,
                 run: str = "nclm", governor: Optional[Governor] = None,
                 power_gate: bool = True, seed: int = 0) -> None:
        self.cfg = config or MobileNCLMConfig()
        self.run = run
        self.seed = seed
        self.power_gate = power_gate
        self.governor = governor or Governor()
        self.stream = FrameStream(path=sub("telemetry") / ("%s.jsonl" % run))
        self.ckpt = sub("checkpoints") / ("%s.npz" % run)
        self.meta = sub("checkpoints") / ("%s.json" % run)
        self.model = None
        self.optimizer = None
        self._built = False

    # -- construction ---------------------------------------------------------
    def adopt_checkpoint_config(self) -> bool:
        """Rebuild `self.cfg` from the checkpoint's saved geometry.

        Without this, `infer` builds the *default* model (dim 128) against a checkpoint
        trained at another width, the weight load fails on shape, and generation runs
        from random weights -- producing confident-looking garbage. Geometry must come
        from the checkpoint, never from CLI defaults.
        """
        meta = read_json(self.meta)
        if not meta or "config" not in meta:
            return False
        saved = dict(meta["config"])
        self.cfg = MobileNCLMConfig(**saved)
        self.seed = int(meta.get("seed", self.seed))
        self._built = False
        return True

    def build(self):
        """Instantiate the model and optimizer. Imports are lazy: `osiris` is the
        `full` bootstrap tier, and `config`/`--help` must work without it."""
        from osiris.nclm import AdamW, LRSchedule, SovereignConfig, SovereignTransformerV2

        np.random.seed(self.seed)
        sovereign = SovereignConfig(
            vocab_size=256, dim=self.cfg.dim, n_layers=self.cfg.n_layers,
            n_heads=self.cfg.n_heads, ff_dim=self.cfg.ff_dim,
            max_seq_len=self.cfg.max_seq_len, dropout=0.0,
            torsion_lock=True, phase_conjugate=True, fractal_embedding=False,
        )
        self.model = SovereignTransformerV2(sovereign)
        params = self.model.parameters()
        self.optimizer = AdamW(
            params=params, lr=self.cfg.lr, weight_decay=self.cfg.weight_decay,
            schedule=LRSchedule(warmup_steps=self.cfg.warmup_steps, total_steps=10000),
        )
        self._built = True
        return self

    def n_parameters(self) -> int:
        return int(sum(np.prod(p.data.shape) for p in self.model.parameters()))

    # -- data -----------------------------------------------------------------
    def load_corpus(self, root: Path, extensions=(".py", ".md", ".txt"),
                    max_bytes: int = 2_000_000) -> bytes:
        """Concatenate a byte corpus, bounded so the phone never holds a huge buffer."""
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
        if total == 0:
            raise ValueError("no %s files under %s" % ("/".join(extensions), root))
        return b"".join(chunks)

    def _batch(self, data: np.ndarray, rng: np.random.RandomState):
        n = self.cfg.batch_size
        span = self.cfg.seq_len + 1
        starts = rng.randint(0, max(1, len(data) - span), size=n)
        block = np.stack([data[s:s + span] for s in starts])
        return block[:, :-1], block[:, 1:]

    # -- checkpointing --------------------------------------------------------
    def save_checkpoint(self, step: int, history: List[float]) -> None:
        """Model + optimizer moments, so a resume is exact rather than a warm restart."""
        arrays: Dict[str, np.ndarray] = {}
        for i, p in enumerate(self.model.parameters()):
            arrays["p%d" % i] = p.data
            arrays["m%d" % i] = self.optimizer._m[i]
            arrays["v%d" % i] = self.optimizer._v[i]
        _atomic_npz(self.ckpt, arrays)
        atomic_write_json(self.meta, {
            "step": step, "step_count": self.optimizer.step_count,
            "seed": self.seed, "config": self.cfg.to_dict(),
            "history": history[-200:], "saved": time.time(),
        }, indent=1)

    def load_checkpoint(self) -> int:
        """Restore and return the step to resume from. 0 when there is nothing to resume."""
        meta = read_json(self.meta)
        if not meta or not self.ckpt.exists():
            return 0
        try:
            with np.load(str(self.ckpt)) as blob:
                for i, p in enumerate(self.model.parameters()):
                    p.data[...] = blob["p%d" % i]
                    self.optimizer._m[i][...] = blob["m%d" % i]
                    self.optimizer._v[i][...] = blob["v%d" % i]
        except (OSError, ValueError, KeyError, EOFError, BadZipFile) as exc:
            print("checkpoint unreadable (%s); starting fresh" % exc, file=sys.stderr)
            return 0
        self.optimizer.step_count = int(meta.get("step_count", 0))
        return int(meta.get("step", 0))

    # -- telemetry ------------------------------------------------------------
    def _telemetry(self, step: int, loss: float, grad_norm: float,
                   ids: np.ndarray, started: float) -> Dict[str, Any]:
        """One frame. `negentropy.summary()` is the phase-conjugate instrument."""
        summary: Dict[str, Any] = {}
        tracker = getattr(self.model, "negentropy", None)
        if tracker is not None:
            try:
                summary = tracker.summary()
            except Exception:
                summary = {}
        frame = {
            "tick": step,
            "learner": {"accuracy": float(math.exp(-loss)), "population": self.n_parameters()},
            "organism": {"entropy": float(loss / math.log(2)), "noise": float(grad_norm)},
            "nclm": {
                "loss": round(float(loss), 5),
                "ppl": round(float(math.exp(min(loss, 20.0))), 3),
                "lr": round(float(self.optimizer.current_lr
                                  if hasattr(self.optimizer, "current_lr") else self.cfg.lr), 8),
                "grad_norm": round(float(grad_norm), 5),
                "xi": round(float(summary.get("mean_xi", 0.0)), 5),
                "phi": round(float(summary.get("mean_phi", 0.0)), 5),
                "gamma": round(float(summary.get("mean_gamma", 0.0)), 5),
                "negentropic_ratio": round(float(summary.get("negentropic_ratio", 0.0)), 5),
                "rss_mb": round(_rss_mb() or 0.0, 1),
                "elapsed_s": round(time.time() - started, 1),
            },
        }
        self.stream.write(frame)
        return frame

    # -- training -------------------------------------------------------------
    def train(self, corpus: Path, steps: int = 200, resume: bool = True,
              verbose: bool = True) -> Dict[str, Any]:
        from osiris.nclm import cross_entropy_loss
        from osiris.nclm.autograd import clip_grad_norm

        if resume:
            self.adopt_checkpoint_config()
        if not self._built:
            self.build()

        raw = self.load_corpus(Path(corpus))
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.int64)
        rng = np.random.RandomState(self.seed)

        start_step = self.load_checkpoint() if resume else 0
        history: List[float] = list((read_json(self.meta) or {}).get("history", [])) if resume else []
        started = time.time()

        self.stream.note("nclm_start", run=self.run, step=start_step, target=steps,
                         params=self.n_parameters(), corpus_bytes=len(data))
        if verbose:
            print("SovereignTransformerV2 | %s params | corpus %s bytes | steps %d->%d"
                  % ("{:,}".format(self.n_parameters()), "{:,}".format(len(data)),
                     start_step, steps))

        params = self.model.parameters()
        stop_reason = "completed"

        for step in range(start_step, steps):
            if self.power_gate and step and step % self.cfg.gate_every == 0:
                decision = self.governor.check()
                if not decision.ok:
                    self.save_checkpoint(step, history)
                    self.stream.note("pause", reason=decision.reason, step=step)
                    notify("NCLM paused", decision.reason, nid=NOTIFY_RUN)
                    stop_reason = "paused: %s" % decision.reason
                    break

            rss = _rss_mb()
            if rss is not None and rss > self.cfg.rss_ceiling_mb:
                self.save_checkpoint(step, history)
                self.stream.note("rss_ceiling", rss_mb=round(rss, 1), step=step)
                stop_reason = "rss %.0f MB over ceiling %d MB" % (rss, self.cfg.rss_ceiling_mb)
                break

            x, y = self._batch(data, rng)
            self.optimizer.zero_grad()
            logits = self.model.forward(x)
            loss = cross_entropy_loss(logits, y)
            loss.backward()
            grad_norm = float(clip_grad_norm(params, self.cfg.grad_clip))
            self.optimizer.step()

            value = float(loss.data)
            history.append(value)

            if step % self.cfg.telemetry_every == 0:
                frame = self._telemetry(step, value, grad_norm, x, started)
                if verbose and step % (self.cfg.telemetry_every * 4) == 0:
                    n = frame["nclm"]
                    print("  step %-5d loss %.4f  ppl %8.2f  |g| %.3f  Xi %.3f  rss %.0fMB"
                          % (step, n["loss"], n["ppl"], n["grad_norm"], n["xi"], n["rss_mb"]))

            if step and step % self.cfg.checkpoint_every == 0:
                self.save_checkpoint(step, history)
        else:
            self.save_checkpoint(steps, history)

        result = {
            "run": self.run, "stop_reason": stop_reason,
            "steps_done": len(history), "params": self.n_parameters(),
            "first_loss": round(history[0], 5) if history else None,
            "final_loss": round(history[-1], 5) if history else None,
            "final_ppl": round(math.exp(min(history[-1], 20.0)), 3) if history else None,
            "wall_s": round(time.time() - started, 1),
            "checkpoint": str(self.ckpt),
        }
        self.stream.note("nclm_done", **result)
        return result

    # -- inference ------------------------------------------------------------
    def infer(self, prompt: str, tokens: int = 96, temperature: float = 0.8,
              top_k: int = 40, allow_untrained: bool = False) -> str:
        """Sample from the run's checkpoint.

        Raises unless a checkpoint actually loaded: sampling from random weights returns
        plausible-looking bytes and is worse than an error, because it looks like output.
        """
        self.adopt_checkpoint_config()
        if not self._built:
            self.build()
        step = self.load_checkpoint()
        if step == 0 and not allow_untrained:
            raise RuntimeError(
                "no usable checkpoint for run %r at %s -- train first, or pass "
                "--allow-untrained to sample from random weights on purpose."
                % (self.run, self.ckpt))
        return self.model.generate(prompt, max_new_tokens=tokens,
                                   temperature=temperature, top_k=top_k)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="nclm_harness", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub_ap = ap.add_subparsers(dest="cmd", required=True)

    tr = sub_ap.add_parser("train", help="train on a byte corpus")
    tr.add_argument("--corpus", type=Path, default=Path.cwd())
    tr.add_argument("--steps", type=int, default=200)
    tr.add_argument("--run", default="nclm")
    tr.add_argument("--seed", type=int, default=0)
    tr.add_argument("--dim", type=int)
    tr.add_argument("--n-layers", type=int)
    tr.add_argument("--batch-size", type=int)
    tr.add_argument("--seq-len", type=int)
    tr.add_argument("--lr", type=float)
    tr.add_argument("--checkpoint-every", type=int)
    tr.add_argument("--no-resume", action="store_true")
    tr.add_argument("--no-power-gate", action="store_true")
    tr.add_argument("--json", action="store_true")

    inf = sub_ap.add_parser("infer", help="sample from a checkpoint")
    inf.add_argument("--prompt", default="def ")
    inf.add_argument("--tokens", type=int, default=96)
    inf.add_argument("--temperature", type=float, default=0.8)
    inf.add_argument("--top-k", type=int, default=40)
    inf.add_argument("--run", default="nclm")
    inf.add_argument("--allow-untrained", action="store_true",
                     help="sample from random weights on purpose")

    sub_ap.add_parser("config", help="print the mobile defaults and exit")
    args = ap.parse_args(argv)

    if args.cmd == "config":
        print(json.dumps(MobileNCLMConfig().to_dict(), indent=2, default=str))
        return 0

    if args.cmd == "infer":
        harness = NCLMHarness(run=args.run)
        try:
            print(harness.infer(args.prompt, args.tokens, args.temperature, args.top_k,
                                allow_untrained=args.allow_untrained))
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0

    harness = NCLMHarness(
        MobileNCLMConfig(dim=args.dim, n_layers=args.n_layers, batch_size=args.batch_size,
                         seq_len=args.seq_len, lr=args.lr,
                         checkpoint_every=args.checkpoint_every),
        run=args.run, seed=args.seed, power_gate=not args.no_power_gate)
    result = harness.train(args.corpus, steps=args.steps, resume=not args.no_resume,
                           verbose=not args.json)
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        print("\n%s: %s | loss %s -> %s (ppl %s) in %ss"
              % (result["run"], result["stop_reason"], result["first_loss"],
                 result["final_loss"], result["final_ppl"], result["wall_s"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

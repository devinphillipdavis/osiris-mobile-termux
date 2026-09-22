# An edge-deployed research harness, and a negative result for evolved parameterized quantum circuits as byte-level language models

**Devin Phillip Davis**
Agile Defense Systems LLC · `osiris.dnalang@gmail.com`
Version `v0.4.0-edge-beta` · 2026-09-22

---

## Abstract

We describe `osiris-mobile-termux`, an execution harness that runs the OSIRIS research
stack — an artificial-life substrate, a domain-specific quantum circuit compiler, and two
experimental language models — entirely on an Android device under Termux, with no cloud
compute and no external model API. The harness contributes a tiered dependency
installation that reduces the mobile-critical install to NumPy alone, a fold-aware
terminal layout that migrates running processes between panes as the device hinge opens,
a hysteretic battery and thermal governor for long unattended runs, and a research-ladder
runner that refuses to launch an experiment whose criterion has not been committed in
advance. Using this harness we then pre-registered and ran two experiments on LivLM, a
byte-level generative model whose parameters are 72 gate rotation angles of a simulated
8-qubit circuit. The first experiment met its pre-registered criterion and we report it as
PASS, but a diagnostic recorded alongside it shows the criterion was confounded: the
circuit's own Born-rule distribution is approximately 70× worse than uniform, and the
apparent result belongs to a smoothing term in the decoder. The second experiment, a
control that the first lacked, compares evolved against random gate angles under an
identical decoder and finds evolved parameters worse on 5 of 5 evaluation seeds, with a
median perplexity ratio of 1.401. We present this as evidence that, on this corpus and at
this circuit depth, genetic evolution of the gate angles does not improve held-out
likelihood and measurably degrades it. We offer a mechanism consistent with the
observation and close the branch.

---

## 1. Motivation

Research infrastructure usually assumes a workstation. The experiments in this program are
NumPy-bound, single-node and long-running, which makes them a poor fit for cloud rental and
a reasonable fit for a modern phone: a 2026 foldable has eight cores and 12 GB of RAM, and
it is already carried. The obstacles are not compute but environment — an operating system
that kills large background processes without warning, suspends timers when the screen
sleeps, throttles under sustained load, and offers a terminal whose width changes when the
device is unfolded.

The harness described here addresses those obstacles and nothing else. It contains no
science. The research packages (`dnalang`, `organism_sim`, `osiris`) are installed from
their own repositories in editable mode and are never patched for mobile, so a number
measured on the device is comparable to the same number measured on a desktop.

## 2. System

### 2.1 The dependency finding

The mobile-critical obstacle appeared to be Qiskit. `dnalang` declares `qiskit>=1.3`, and
Qiskit ≥ 1.0 carries a Rust core (`rustworkx`, `qiskit-accelerate`) with no aarch64-Android
wheels, so installing it on-device means a 30–60 minute compile.

Inspection showed the dependency is only nominal for the paths that matter. `dnalang`
imports Qiskit lazily, inside `Circuit.to_qiskit` (`dnalang/qc_ir.py:63`); only the `aer`
and `ibm` backend modules import it at module scope. We verified this by installing a
meta-path hook that raises on any `qiskit` import and then importing the full mobile path —
`dnalang`, `action_dsl`, `regulation`, `organism_sim.lcs`, `agent`, `grn`, `telemetry`,
`chat_bridge` and `benchmarks.mux` all import cleanly.

The installer therefore offers three tiers. The default, `lite`, compiles nothing but
NumPy (taken as a prebuilt Termux package) and still runs the entire artificial-life,
classifier-system and neuro-symbolic-bridge track. Qiskit is quarantined in the `quantum`
tier, needed only for Aer ground truth and hardware submission.

### 2.2 Fold-aware layout

Above 100 columns the session is a single window split side by side: the REPL on the left,
live telemetry on the right. Below that threshold — the cover display, or a split-screen
window — the monitor moves to its own window. A session-scoped `client-resized` hook
re-runs the layout pass, so folding and unfolding rearranges the workspace live.

The transition uses `join-pane` and `break-pane`, which **move** panes between windows
rather than respawning them. A four-hour run is therefore not interrupted by opening the
device. Three `tmux` behaviours had to be worked around, each of which fails silently:
`set-option -t` rejects the `=` exact-match target prefix that `has-session` accepts;
`set-hook -g` installs server-wide regardless of its `-t` argument; and key tables are
server-global, so per-session behaviour must be indirected through a `@user_option`
referenced inside the binding.

### 2.3 Power governance

Heavy routes pass a governor before consuming battery. The literal policy suggested by the
requirement — pause below 20 % **or** whenever unplugged — pauses nearly always on a phone,
so the implemented default pauses when *on battery and below the floor*, with the strict
reading available behind a flag.

The governor is hysteretic: once paused it requires 35 % to resume, not the 20 % floor.
Without hysteresis, the ±1 % jitter of a battery gauge under load causes the gate to flap
many times a minute, and each flap costs a tournament generation. Thermal state is sampled
from `/sys/class/thermal` and pauses at 45 °C. When the Termux:API bridge is absent the
governor fails open by default, because a missing companion APK should not silently disable
the laboratory; failing closed is available for unattended runs.

### 2.4 Intent routing

Routing is deterministic regex scoring, not model inference. It must work before a local
model server is running, must be testable without a device, and — decisively — a misroute
on a phone can start a four-hour job on battery, which should not be a sampling outcome.

Two dimensions are extracted independently: the *domain* (which subsystem) and the *mode*
(explain versus execute). The cross-product matters. "Explain the mux benchmark" and "run
the mux benchmark" share every domain keyword; the first routes to the coding agent, the
second to a power-gated execution route. Domain vocabulary alone never starts a job,
because the failure modes are asymmetric: explaining a run the user wanted costs a
sentence, while launching a run the user only asked about costs hours of battery.

### 2.5 The pre-registration gate

The ladder runner parses the program's milestone file and classifies each rung as
resolved, in flight, pre-registered or available. Verdicts are read from three places,
because sub-rungs frequently have no table row of their own: the ladder table, a
`**Result (date): …**` block inside a pre-registration section, and the generated
scorecard.

`auto advance` selects the lowest rung that is neither resolved nor running. It will
**stage** a rung that has no committed criterion — collecting the driver, the blockers and
a criterion *template* full of `TODO` — but it will not launch one, and it never writes a
verdict for a criterion it had to infer. Commit-on-pass is permitted; criterion-on-pass is
not. At the time of writing, one rung (M3c) was executing with five worker processes; the
runner correctly identified it as in flight, stepped over it, and staged M4 without
disturbing it.

## 3. Method: LivLM as a byte-level language model

LivLM generates text by executing a parameterized 8-qubit circuit and reading the
measurement outcome as a byte. Its learnable parameters are gate rotation angles,
`24 × n_layers`; at the default `n_layers = 3` there are exactly **72**. Parameters are
fitted by a genetic algorithm maximising `F = α·Ξ + β·ngram_coherence + γ·corpus_likelihood`,
where Ξ is a negentropy term over the measurement distribution.

Because the 8-qubit register's Born-rule probability vector has exactly 256 entries and
sums to one, it is a normalized categorical distribution over the byte vocabulary, and
held-out perplexity

&nbsp;&nbsp;&nbsp;&nbsp;`PPL = exp( (1/N) · Σᵢ −ln P(bᵢ | contextᵢ) )`

is well defined rather than metaphorical. We verified normalization to within 1e-9 before
pre-registering.

Contexts are teacher-forced with true preceding bytes, so the measurement is likelihood
assignment and not generation quality. The corpus is split 80/20 by byte offset; the
genetic algorithm sees only the training split, as do all baselines. Evaluation seeds
300–304 and tuning seeds 310–314 were fixed in advance and are disjoint from every seed
range spent elsewhere in the program.

One amendment was recorded **before any evaluation seed was run**. LivLM does not generate
from the raw Born vector: its decoder mixes in a context-derived bias whenever a coherence
statistic falls below 0.8. That mixture, not the Born vector, is the model's predictive
distribution, and scoring the Born vector alone would understate the model. The primary
metric was therefore defined on the mixture, with raw-Born perplexity retained as a
diagnostic.

## 4. Results

### 4.1 LivLM-PPL-1 — PASS on a criterion that did not test the claim

Criterion: median held-out perplexity below the uniform baseline of 256.0, with at least
4 of 5 seeds individually below.

| seed | PPL (as generated) | PPL (raw Born) | order-0 | order-1 |
|---|---|---|---|---|
| 300 | 127.00 | 16 508.89 | 32.54 | 16.59 |
| 301 | 122.78 | 22 965.91 | 32.54 | 16.59 |
| 302 | 125.39 | 31 884.11 | 32.54 | 16.59 |
| 303 | 123.44 | 15 112.37 | 32.54 | 16.59 |
| 304 | 125.26 | 17 855.29 | 32.54 | 16.59 |

Median 125.26, 5/5 below uniform: the criterion is met and the result is recorded as
**PASS**, because a criterion committed in advance is not rewritten afterwards.

The diagnostic column voids the interpretation. The circuit's own distribution scores a
median perplexity of 17 855 — roughly **70× worse than uniform**. The entire sub-uniform
result is produced by the decoder's mixing term, which raises the probability mass on
printable bytes; natural text is overwhelmingly printable, so that term beats uniform
regardless of the circuit. LivLM-PPL-1 measured the decoder.

We record this as a fault in our own pre-registration rather than repairing it quietly.
"Beats uniform" cannot separate an evolved circuit from a printable-byte prior. The
appropriate control is not against a fixed baseline but against the same architecture with
unfitted parameters.

### 4.2 LivLM-PPL-2 — the missing control

Criterion, committed after LivLM-PPL-1 reported and before the control arm was run:
evolved perplexity below random-genome perplexity on ≥ 4 of 5 seeds, with a median ratio
below 0.95. The 0.95 margin was specified so that a numerically indistinguishable tie
would be recorded as a failure rather than a narrow win. Both arms share corpus, split,
held-out bytes, teacher forcing, decoder and seeds; the only difference is whether the 72
angles were fitted or drawn uniformly from [−π, π].

| seed | evolved | random | ratio |
|---|---|---|---|
| 300 | 127.00 | 88.96 | 1.427 |
| 301 | 122.78 | 87.58 | 1.402 |
| 302 | 125.39 | 89.50 | 1.401 |
| 303 | 123.44 | 89.71 | 1.376 |
| 304 | 125.26 | 89.74 | 1.396 |

Evolved parameters are worse than random parameters on **5 of 5 seeds**, by a consistent
≈ 40 %. Observed: 0/5 and a median ratio of 1.401 against a threshold of 0.95. The kill
criterion fires: **FAIL**.

### 4.3 A mechanism consistent with the observation

The fitness function rewards Ξ, a negentropy term that favours peaked, low-entropy
measurement distributions. Log-loss punishes a confident wrong answer far more than an
uncertain one. A genetic algorithm that sharpens the output distribution without steering
*where* the mass lands therefore optimises directly against the metric by which a language
model is judged. Random angles leave the register nearer uniform, which log-loss treats
more gently. This account is consistent with both the direction and the uniformity of the
effect, but we did not test it directly — doing so would require an ablation over the α,
β, γ weights and is a separate pre-registration.

## 5. Scope and limitations

The LivLM result is specific to this corpus, this circuit depth (`n_layers = 3`, 72
parameters), this fitness function and this decoder. We did not test greater depth, a
different corpus, or an optimiser driven by held-out log-loss, and we make no claim about
them. A model with 72 parameters is not expected to compete with an order-0 unigram, which
fits roughly 255 free parameters directly to the data; that comparison was stated in the
pre-registration as context rather than as a criterion, precisely so that losing to it
could not later be presented as a surprise.

Nothing here bears on any physical claim. The 8-qubit register is a classical state-vector
simulation; no hardware was involved, and no assertion is made about τ-phase, 51.843°,
negentropy as a physical quantity, or phase-conjugate optics. `dnalang-core`'s own record
lists several such earlier claims as refuted on hardware, and this work does not revisit
them. The Ξ, Φ and Γ quantities reported by the transformer harness are instrument
readings from a tracker module, reported as such.

The NCLM harness (`bench/nclm_harness.py`) is instrumentation, not an experiment. Falling
training loss demonstrates that the NumPy autograd stack and optimizer function on-device;
it is not evidence about any property of the attention mechanism. Any such claim would
require its own pre-registration and a control.

Finally, the harness itself has been exercised on a desktop Linux host and in `tmux` 3.4;
the Termux-specific installation paths are written against documented Termux behaviour but
had not been executed on the target device at the time of this release.

## 6. Reproduction

```bash
git clone https://github.com/osiris-dnalang/osiris-mobile-termux
cd osiris-mobile-termux && bash bootstrap_termux.sh --tier full

# LivLM-PPL-1 (judged arm; the script refuses any other seed set)
python bench/livlm_perplexity.py --seeds 300 301 302 303 304 --corpus $OSIRIS_SRC/organism_sim

# LivLM-PPL-2 control arm
python bench/livlm_perplexity.py --seeds 300 301 302 303 304 --arm random --corpus $OSIRIS_SRC/organism_sim

# Ladder state
python -m osiris_mobile.ladder.advance status
```

Criteria, amendments and outcomes are in `docs/PRE_REGISTRATION.md`, written in that
order. The test suite (101 tests) covers the governor's hysteresis against recorded
battery payloads, the routing table, the bounded telemetry store, the ladder parser
against both a fixture and the live program file, and the numerics that decide each
verdict.

## 7. What this release claims, and what it does not

It claims: a working edge-compute harness, with the dependency analysis that makes the
default install NumPy-only; and two pre-registered experiments whose outcomes are
recorded as run, one of which is a clean negative result with its control.

It does not claim: that LivLM's architecture is refuted in general; that phase-conjugate
attention does or does not work; that any physical prediction has been tested; or that the
Termux installation has been validated on hardware.

---

*Licensed under the OSIRIS Source-Available Dual License v1.0. Negative results are part
of the record.*

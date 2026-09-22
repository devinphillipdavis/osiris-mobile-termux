# Pre-registrations — `osiris-mobile-termux`

Same discipline as `organism_sim/docs/PROGRAM.md`: **the criterion is committed before the
run.** Nothing is re-tuned on evaluation seeds. A result that fails is recorded as FAIL and
the branch closes. Tuning seeds and evaluation seeds are disjoint and named here in advance.

Seed ranges are fresh, chosen to avoid collision with every range already spent in
`organism_sim` (eval 0–4, 10–14, 20–24, 30–34, 40–44, 50–54, 60–64, 70–74; tuning 100–124).

---

## LivLM-PPL-1 — do 72 evolved gate angles carry corpus information?

*Pre-registered 2026-09-22, before the benchmark was written. Directive E.*

### Claim under test

LivLM at `n_layers=3` — **72 learnable parameters**, being `24 × n_layers` gate rotation
angles (`GenerationCircuit`, `osiris_livlm.py:251`) — assigns higher likelihood to
held-out bytes of the OSIRIS corpus than a uniform byte distribution does.

This is a claim about a classical 8-qubit state-vector simulation's likelihood
assignment. **It is not a physical claim.** No assertion is made here about τ-phase,
51.843°, negentropy or hardware behaviour; `dnalang-core`'s README records those as
refuted on hardware and nothing in this benchmark revisits them.

### Metric

Held-out byte-level perplexity

&nbsp;&nbsp;&nbsp;&nbsp;`PPL = exp( (1/N) · Σ_i −ln P(b_i | context_i) )`

where `P(· | context)` is the Born-rule distribution `Qbyte.probabilities()` over the 256
basis states of the 8-qubit register, after encoding `context_i` and applying the evolved
circuit. Verified before pre-registration: the vector has shape `(256,)` and sums to 1.0
to within 1e-9, so it is a normalized categorical over the byte vocabulary and perplexity
is well-defined rather than metaphorical.

### Design

- Corpus split **80 / 20** train / held-out by byte offset, deterministically.
- The genome is evolved on the **train split only**. The GA never sees a held-out byte.
- Baselines are estimated on the **train split only** and scored on the identical
  held-out bytes:
  - **uniform** — exactly 256.0 by construction
  - **order-0** byte unigram, add-1 smoothed
  - **order-1** byte bigram, add-1 smoothed
- Teacher forcing: context at position *i* is the true preceding bytes, not the model's
  own samples, so the measurement is likelihood and not generation quality.

### Seeds

| role | seeds | used for |
|---|---|---|
| tuning | 310–314 | population size, generations, sample length — never judged |
| evaluation | 300–304 | judged, frozen at pre-registration |

### Criteria

**Primary (judged).** PASS iff the **median held-out PPL over evaluation seeds 300–304 is
below 256.0**, *and* at least **4 of 5** individual seeds are below 256.0.

**Kill criterion.** If the median is ≥ 256.0, the 72 evolved parameters carry no usable
information about the corpus at this depth. The branch closes and is published as FAIL.

**Secondary (reported, not judged).** Ratio of LivLM PPL to the order-0 and order-1
baselines. A 72-parameter circuit is *not* expected to beat an order-0 unigram, which has
~255 free parameters fitted directly to the data. That comparison is context for the
reader, not a criterion, and it is stated here in advance precisely so that a loss to
order-0 cannot later be presented as a surprise or a success.

### Amendment recorded before the evaluation run (2026-09-22)

The measured distribution is the one LivLM **actually generates from**, not the raw Born
vector. `TextDecoder.decode_with_coherence_bias` (osiris_livlm.py:186) mixes the Born
distribution with a context bias whenever coherence Λ < 0.8:
`mixed = Λ·probs + (1−Λ)·bias`, normalized; at Λ ≥ 0.8 it uses the Born vector unchanged.
Only the terminal `np.random.choice` is stochastic, so the predictive distribution is
recoverable exactly.

Scoring the raw Born vector would **understate** the model, because the bias term is part
of the generative path and boosts printable bytes. The primary metric is therefore the
NLL of the mixed distribution. Raw-Born PPL is recorded alongside as a diagnostic.

This amendment is made **before any evaluation seed has been run** — only tuning seed 310
had been executed at the time, at a throwaway configuration. The criterion itself
(median < 256.0, ≥ 4/5 seeds) is unchanged.

### Outcome

<!-- livlm-ppl-1:start -->
**Result (2026-09-22): PASS on the letter of the criterion — and the criterion was wrong.**

| seed | LivLM PPL (as generated) | LivLM PPL (raw Born) | order-0 | order-1 |
|---|---|---|---|---|
| 300 | 127.00 | 16508.89 | 32.54 | 16.59 |
| 301 | 122.78 | 22965.91 | 32.54 | 16.59 |
| 302 | 125.39 | 31884.11 | 32.54 | 16.59 |
| 303 | 123.44 | 15112.37 | 32.54 | 16.59 |
| 304 | 125.26 | 17855.29 | 32.54 | 16.59 |

Median 125.26 < 256.0 and 5/5 seeds below uniform, so the pre-registered criterion is met:
**PASS**, recorded as such because the criterion was committed in advance and is not
rewritten after the fact.

**But the diagnostic voids the interpretation.** The circuit's own Born distribution
scores a median PPL of **17 855 — about 70× *worse* than uniform**. Every bit of the
sub-uniform result comes from the classical mixing term in
`TextDecoder.decode_with_coherence_bias`, which boosts printable bytes; text is mostly
printable, so that term alone beats uniform regardless of what the circuit does.

LivLM-PPL-1 therefore measured the **decoder**, not the 72 evolved gate angles. The
criterion was insufficiently controlled: "beats uniform" cannot separate the evolved
parameters from a printable-byte prior. That is a fault in the pre-registration, recorded
here rather than quietly repaired, and it is why LivLM-PPL-2 below exists.

Nothing about this result supports any claim regarding τ-phase, 51.843°, negentropy or
phase-conjugate physics. It is a statement about a decoder's smoothing term.
<!-- livlm-ppl-1:end -->

---

## LivLM-PPL-2 — does evolution contribute anything at all?

*Pre-registered 2026-09-22, after LivLM-PPL-1 reported and before this arm was run.
The control arm did not exist when this criterion was written.*

### Claim under test

The 72 evolved gate angles assign higher likelihood to held-out bytes than 72 **random**
gate angles do, under the identical decoder, identical held-out bytes and identical seeds.

This is the control LivLM-PPL-1 lacked. It holds the decoder fixed, so the printable-byte
bias appears in both arms and cancels; the only difference between arms is whether the
genome was evolved on the train split or drawn uniformly from [−π, π].

### Design

- Arms: `evolved` (GA on the train split, as in LivLM-PPL-1) and `random`
  (`RandomState(seed).uniform(−π, π, 72)`, no GA).
- Everything else is byte-identical: same corpus, same 80/20 split, same 384 held-out
  bytes, same teacher forcing, same decoder mixture, same evaluation seeds 300–304.
- Metric: held-out PPL of the distribution as generated, exactly as in LivLM-PPL-1.

### Criteria

**Primary (judged).** PASS iff `PPL(evolved) < PPL(random)` on **≥ 4 of 5** evaluation
seeds **and** the median ratio `PPL(evolved) / PPL(random) < 0.95`.

**Kill criterion.** If the median ratio is ≥ 0.95, genetic evolution of the 72 angles
contributes nothing measurable to held-out likelihood over random angles, and the
"evolved quantum circuit as a language model" branch closes. The 5 % margin exists so
that a numerically indistinguishable tie is recorded as FAIL rather than as a narrow win.

### Outcome

<!-- livlm-ppl-2:start -->
**Result (2026-09-22): FAIL — 0/5, median ratio 1.401.**

| seed | evolved PPL | random PPL | ratio evolved/random |
|---|---|---|---|
| 300 | 127.00 | 88.96 | 1.427 |
| 301 | 122.78 | 87.58 | 1.402 |
| 302 | 125.39 | 89.50 | 1.401 |
| 303 | 123.44 | 89.71 | 1.376 |
| 304 | 125.26 | 89.74 | 1.396 |

Evolved genomes are **worse than random genomes on every seed**, by a consistent ~40 %.
The criterion required ≥ 4/5 seeds with evolved < random and a median ratio < 0.95; the
observed values are 0/5 and 1.401. The kill criterion fires.

**What this means.** Genetic evolution of the 72 gate angles does not merely fail to
improve held-out likelihood — it actively degrades it. The GA maximises
`F = α·Ξ + β·ngram_coherence + γ·corpus_likelihood`, and the Ξ (negentropy) term rewards
peaked, low-entropy measurement distributions. A peaked distribution that is peaked on
the *wrong* bytes is penalised hard by log-loss, so the fitness function is optimising
against the metric a language model is judged on. Random angles leave the register closer
to uniform, which log-loss treats more kindly.

Combined with LivLM-PPL-1's raw-Born diagnostic (circuit-only PPL ≈ 70× worse than
uniform), the picture is consistent and unflattering: on this corpus and at this depth,
**the quantum generation circuit contributes nothing to byte-level prediction, and
evolving it makes matters worse.** The apparent sub-uniform performance belongs entirely
to the decoder's printable-byte smoothing.

**Branch closed.** Per the kill criterion, "evolved quantum circuit as a language model"
is closed on this evidence. Reviving it would require a different fitness function — one
that prices held-out log-loss rather than Ξ — and a fresh pre-registration.

Not tested here, and not claimed either way: whether a different corpus, greater circuit
depth, or a log-loss-driven optimiser would change this. Those are separate experiments.
<!-- livlm-ppl-2:end -->

---

## NCLM harness — instrumentation, not an experiment

*Directive D.* `bench/nclm_harness.py` trains `SovereignTransformerV2` on a byte corpus
with per-step telemetry, power gating, an RSS ceiling and exact-resume checkpoints.

It is **not** a pre-registered experiment and makes no claim. Falling training loss on a
corpus demonstrates that the autograd stack and optimizer function on-device; it is not
evidence for any property of phase-conjugate attention. The Ξ / Φ / Γ figures it streams
are instrument readings from `NegentropicTracker`, reported as such. Any claim about them
would need its own pre-registration here, with a control.

---

## Auto-advance and this file

`osiris_mobile/ladder/advance.py` refuses to launch a rung that has no pre-registration
block — in `organism_sim/docs/PROGRAM.md` for ladder rungs, or here for mobile-side
benchmarks. It will not write a verdict for a criterion it had to infer. Commit-on-PASS
is allowed; criterion-on-PASS is not.

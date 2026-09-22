# `osiris-mobile-termux` — repository structure

The authoritative layout. Every path below is either **written** (exists now) or
**planned** (named here so the directive's later stages have a fixed target).

This repo is an *execution harness only*. It contains no science. `dnalang`,
`organism_sim`, `osiris` and `bridge` are cloned as siblings under `$OSIRIS_SRC`
and installed editable; the research code is never forked, vendored or modified
for mobile. That is what keeps results on the phone comparable to results on the
desktop.

```
osiris-mobile-termux/
├── bootstrap_termux.sh            [WRITTEN]  Directive A — full device provisioning
├── launch_fold.sh                 [WRITTEN]  Directive B — fold-aware tmux lab
├── pyproject.toml                 [WRITTEN]  package `osiris-mobile`, numpy-only deps
├── README.md                      [WRITTEN]
├── LICENSE                        [planned]  OSIRIS Source-Available Dual License v1.0
├── .gitignore                     [WRITTEN]
│
├── docs/
│   ├── STRUCTURE.md               [WRITTEN]  this file
│   ├── MOBILE_CONSTRAINTS.md      [planned]  what runs on Termux, what cannot, measured
│   └── PRE_REGISTRATION.md        [WRITTEN]  LivLM-PPL-1 (PASS, confounded) and -2 (FAIL)
│
├── osiris_mobile/                 the harness package
│   ├── __init__.py                [WRITTEN]
│   ├── repl.py                    [WRITTEN]  Directive C — the unified REPL (entry point)
│   ├── intent.py                  [WRITTEN]  deterministic intent classifier + route table
│   │                                         (regex/keyword first, model only as tiebreak,
│   │                                          so routing is testable without an LLM)
│   ├── store.py                   [WRITTEN]  $OSIRIS_HOME paths; bounded JSONL ring buffers
│   │
│   ├── routes/
│   │   ├── brain.py               [planned]  -> osiris_brain.py  (standard agent / codebase Q&A)
│   │   ├── organism.py            [planned]  -> organism_sim.chat_bridge, cli bench, LCSAgent
│   │   ├── nclm.py                [WRITTEN]  in repl.py: route_nclm — SovereignTransformer harness
│   │   └── livlm.py               [WRITTEN]  in repl.py: route_livlm — LivLM evolve/generate
│   │
│   ├── power/                     Directive C, mobile constraint
│   │   ├── battery.py             [WRITTEN]  termux-battery-status -> PowerState
│   │   ├── governor.py            [WRITTEN]  the policy: floor/resume hysteresis, thermal, fail-open
│   │   ├── thermal.py             [WRITTEN]  /sys/class/thermal sampling
│   │   ├── notify.py              [WRITTEN]  termux-notification wrapper (id-stable, updatable)
│   │   └── wakelock.py            [WRITTEN]  termux-wake-lock as a context manager
│   │
│   ├── backends/
│   │   ├── llama_server.py        [planned]  supervise/POST to llama-server
│   │   └── ollama_shim.py         [planned]  /api/chat -> /v1/chat/completions, so
│   │                                         osiris_brain.py's OSIRIS_OLLAMA contract is
│   │                                         preserved byte-for-byte and needs no edit
│   │
│   ├── telemetry/
│   │   ├── stream.py              [WRITTEN]  organism_sim.telemetry.capture_frame -> JSONL
│   │   └── tail.py                [WRITTEN]  right-pane renderer (fold-width aware)
│   │
│   └── ladder/                    Directive F
│       ├── program.py             [WRITTEN]  parse organism_sim/docs/PROGRAM.md: ladder rows,
│       │                                     pre-registration blocks, scorecard state
│       └── advance.py             [WRITTEN]  setsid launcher, stage-vs-launch gate, notify
│
├── bench/
│   ├── livlm_perplexity.py        [WRITTEN]  Directive E — LivLM-PPL-1 and -2
│   └── nclm_harness.py            [WRITTEN]  Directive D — SovereignTransformer train/infer
│
├── scripts/
│   ├── install_llamacpp.sh        [planned]  standalone re-build (bootstrap stage 7 alone)
│   ├── fetch_model.sh             [planned]  standalone GGUF pull (bootstrap stage 8 alone)
│   └── termux_boot_osiris.sh      [planned]  ~/.termux/boot/ hook: wake-lock + resume runs
│
├── config/
│   ├── osiris-mobile.toml         [planned]  thresholds, model, pane layout
│   └── tmux.fold.conf             [WRITTEN]  fold/unfold keybinds, status line
│
└── tests/
    ├── test_intent.py             [WRITTEN]  routing table is exhaustive and deterministic
    ├── test_power.py              [WRITTEN]  governor against recorded termux-api JSON
    ├── test_program_parser.py     [WRITTEN]  fixture + the live PROGRAM.md
    ├── test_bounded_store.py      [WRITTEN]
    └── test_repl_routing.py        [WRITTEN]  power gate + dry mode  ring buffer never exceeds OSIRIS_AUDIT_WINDOW
```

## On-device state — everything under `$OSIRIS_HOME` (`~/.osiris`)

Android's `lowmemorykiller` reaps the largest-RSS background process first, and Doze
suspends timers. Nothing durable may live in process memory.

```
~/.osiris/
├── venv/              --system-site-packages, so pkg-installed numpy/scipy are visible
├── bin/               llama-server, llama-cli symlinks
├── models/            *.gguf
├── logs/              build + run logs
├── results/           experiment output (mirrors organism_sim/results/ layout)
├── checkpoints/       per-seed, flushed every OSIRIS_CHECKPOINT_EVERY seeds
├── telemetry/         JSONL frames, bounded ring
├── brain_memory.json  osiris_brain.py memory (unchanged path — desktop-compatible)
├── repo_index.json    osiris_brain.py scan index
└── env.sh             generated by bootstrap_termux.sh
```

## The dependency fact the whole design rests on

`dnalang/qc_ir.py:63` imports qiskit **lazily**, inside `Circuit.to_qiskit`. Only
`dnalang/backends/aer.py` and `dnalang/backends/ibm.py` import it at module scope.

Verified on 2026-09-22 by blocking `qiskit` in `sys.meta_path` and importing the full
mobile path — `dnalang`, `action_dsl`, `regulation`, `organism_sim.lcs` (`PARAMS16`),
`agent`, `grn`, `telemetry`, `chat_bridge`, `benchmarks.mux` all import clean.

So the `lite` tier ships **numpy and nothing else compiled**, and still runs the entire
ALife / LCS / GRN / neuro-symbolic-bridge research track. Qiskit — a 30–60 min on-device
Rust build — is needed only for `bridge/` and `dnalang run --backend aer`, and is
quarantined in the `quantum` tier.

| Track | Tier | Compiled deps |
|---|---|---|
| `organism_sim` LCS/XCS, 6-mux, drift, relay, M-rungs | lite | numpy |
| `dnalang` parse / check / lower / qasm3 export | lite | numpy |
| `chat_bridge` neuro-symbolic REPL | lite | numpy (+ llama-server) |
| `osiris_brain.py` agent | lite | numpy, requests (+ llama-server) |
| LivLM, qbyte, NCLM | full | numpy (+ scipy via tur-repo for parts of `osiris`) |
| `bridge/`, Aer ground truth, IBM submission | quantum | qiskit, qiskit-aer, Rust |

## Research-program discipline on mobile

`auto advance` (Directive F) is bound by the same rule as the desktop: **the criterion is
committed before the run.** `ladder/advance.py` will refuse to launch a rung that does not
already have a pre-registration block in `organism_sim/docs/PROGRAM.md`, and will never
write a verdict for a rung whose criterion it had to infer. Commit-on-PASS is fine;
criterion-on-PASS is not. Tuning seeds stay 100–124; evaluation seeds stay in the
pre-registered ranges. Mobile is a slower CPU, not a different protocol.

## Fold behaviour (Directive B, as implemented)

`launch_fold.sh` treats the hinge as a layout input, not a restart:

| Client width | Layout | Monitor lives in |
|---|---|---|
| `>= 100` cols (unfolded inner display) | one window, split side-by-side; REPL 60% / telemetry 40% | pane 1 of `lab` |
| `< 100` cols (cover display, split-screen) | single pane | its own `monitor` window, prefix+T |

A session-scoped `client-resized` hook re-runs `--relayout`, so folding and unfolding
rearranges the lab live. The transition uses `join-pane` / `break-pane`, so the running
processes are moved, never restarted — a four-hour run is not interrupted by opening the
phone.

Verified on tmux 3.4: launch → unfold → fold → toggle → double-relayout (idempotent),
with `@osiris_launcher` readable and the resize hook confined to the OSIRIS session.

Three tmux details that were wrong on the first pass and are worth not repeating:

* `set-option -t "=$SESSION"` **silently fails** — the `=` exact-match prefix that
  `has-session` accepts is rejected here, and `-q` hides it. The keybinds would have
  expanded `#{@osiris_launcher}` to the empty string and done nothing.
* `set-hook -g` installs server-wide **regardless of `-t`**, so every unrelated tmux
  session would have run a relayout against the OSIRIS session on every resize.
* Key tables in tmux are server-global; per-session behaviour has to come from a
  `@user_option` referenced inside the binding, which is why the binding is written as
  `run-shell -b "#{@osiris_launcher} --relayout --session #{session_name}"`.

## Running the shell scripts off-device

Both `.sh` files carry the canonical Termux shebang
(`/data/data/com.termux/files/usr/bin/bash`), which does not exist on a desktop Linux
host. Invoke them as `bash bootstrap_termux.sh …` / `bash launch_fold.sh …` there;
on the device `./script.sh` works directly.


## Directives D, E, F as implemented

**D — NCLM harness** (`bench/nclm_harness.py`). NumPy, not PyTorch: `osiris.nclm` already
carries reverse-mode autograd, layers, AdamW and a byte dataset, so torch would be ~250 MB
of aarch64 wheels bought for nothing. `osiris.nclm.trainer.Trainer` is not used — its
`train()` is a closed blocking loop with no per-step hook — so the loop is rebuilt from the
same published primitives, leaving the research package untouched. Adds per-step telemetry
into the fold pane, power gating, an RSS ceiling and exact-resume checkpoints (model *and*
AdamW moments) written atomically.

Two bugs were found and fixed while testing it, both of which would have corrupted results
silently: `np.savez` given a *path* appends `.npz`, so renaming the empty `mkstemp` file
over the checkpoint produced an `EOFError` on resume; and `infer` built the default model
geometry against a checkpoint trained at another width, failed the weight load, and
generated confident-looking noise from random weights. Geometry is now read from the
checkpoint, and sampling without a loaded checkpoint raises.

**E — LivLM perplexity** (`bench/livlm_perplexity.py`). Criterion committed in
`docs/PRE_REGISTRATION.md` before the file existed. LivLM-PPL-1 PASSED and its diagnostic
showed the criterion was confounded; LivLM-PPL-2 supplied the missing control and FAILED at
0/5. Both outcomes are recorded in full.

**F — auto advance** (`osiris_mobile/ladder/`). Parses the ladder, resolving verdicts from
the table, from `**Result (date): …**` blocks and from the generated scorecard — necessary
because sub-rungs like M3b and Substrate-Opt-1 have no table row. Detects in-flight runs
from the process table. `auto advance` **stages** a rung without a committed criterion
(writing a `TODO` template it cannot itself complete) and **launches** only a
pre-registered one, under `setsid` with a wake lock.

Verified against the live ladder while M3c was executing on five workers: the runner
identified M3c as in flight, stepped over it, and staged M4 — correctly refusing to launch
M4, which has neither a pre-registration nor a driver.

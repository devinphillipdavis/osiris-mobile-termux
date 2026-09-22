"""Shared fixtures. The ladder fixture carries every shape the real PROGRAM.md uses:
a table row with a bold verdict, one with only a criterion, a sub-rung whose outcome
lives in its pre-registration body, a hyphenated heading id, and a scorecard.
"""

FIXTURE = """\
## 3. The milestone ladder

| # | milestone | mechanism | metric | kill criterion |
|---|---|---|---|---|
| M1 | **Regulatory genes** — interpreter | GRNs | drift family | **FAIL (gaming).** Language built |
| M3 | **Open-ended tasks** — POET | POET | ANNECS | **FAIL at 6–10 bits**; **PASS at 12–16** |
| M4 | **Library learning** — abstraction | DreamCoder | held-out solve rate | no gain → abstraction adds nothing |
| M5 | **Division of labour** — bus | signalling | fraction solved | no rise over 18 % |

### M3b — wide spaces with `PARAMS16` (pre-registered 2026-09-21)

Body text.

**Result (2026-09-22): PASS.** Pooled ANNECS 35 vs 25.

### M3c — curriculum or inheritance? (pre-registered 2026-09-22, not yet run)

Body text with no result.

### Substrate-Opt-1 — the learner's knobs (pre-registered 2026-09-21)

Body.

## 6. Scorecard

<!-- scorecard:start -->
| experiment | verdict | number |
|---|---|---|
| m3b: open-ended, 12-16 bit | PASS | ratio 1.40 |
| substrate-opt-1: XCS grid | BOUNDED | winner 11500 |
| bridge step 3 | PASS (tie) | 0.9763 |
<!-- scorecard:end -->
"""

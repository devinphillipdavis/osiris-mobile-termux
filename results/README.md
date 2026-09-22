# Results

Data for the pre-registered experiments in [`../docs/PRE_REGISTRATION.md`](../docs/PRE_REGISTRATION.md).
Criteria were committed before each run; the one amendment was recorded before any
evaluation seed executed.

| file | experiment | verdict |
|---|---|---|
| `livlm_ppl1_eval_seeds300-304.json` | LivLM-PPL-1, evolved arm | PASS (criterion confounded — see the diagnostic column `livlm_ppl_raw_born`) |
| `livlm_ppl1_eval_seeds300-304_random.json` | LivLM-PPL-2, random-genome control | — |
| `livlm_ppl2_comparison.json` | LivLM-PPL-2, scored | **FAIL** — 0/5, median ratio 1.401 |

Regenerate:

```bash
python bench/livlm_perplexity.py --seeds 300 301 302 303 304 --corpus $OSIRIS_SRC/organism_sim
python bench/livlm_perplexity.py --seeds 300 301 302 303 304 --arm random --corpus $OSIRIS_SRC/organism_sim
```

Runs are seeded and deterministic. `livlm_ppl` is the perplexity of the distribution LivLM
actually generates from; `livlm_ppl_raw_born` is the circuit's own Born-rule distribution
before the decoder's mixing term, and is the diagnostic that voids LivLM-PPL-1's
interpretation.

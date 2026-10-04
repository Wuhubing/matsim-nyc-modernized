# Context-aware MATSim acceleration pilot

This pilot tests selected-plan transfer into the same launch-2025 pricing scenario.
It does not establish convergence, real-world validity, or policy ranking accuracy.

Three executable ablations share full population, pricing, capacity, scoring,
seed 4711, 16 threads, 16 GiB heap and a 12-iteration horizon:

- `cold`: original selected plan per person.
- `warm_early`: selected plans serialized before baseline iteration 1.
- `warm_latest`: selected plans in the completed baseline's final output.

All transferred scores and alternative plans are removed. Routes and activity times
are retained. This is a selected-plan warm start, not a full solver checkpoint:
link travel-time state and internal random state are not transferred. Initialization
may perform normal MATSim route preparation. It is not the fixed-plan diagnostic.

A one-shot GPT-4.1-mini selector sees only historical aggregate context and picks
one of those three IDs before any target results exist. It cannot change model
parameters or execute commands. Its selected arm is evaluated using the matching
ablation, not a duplicate simulation. A single selected arm cannot establish
LLM superiority over fixed or numerical selection rules. One source trajectory is
not a diverse scenario-retrieval benchmark.

## Budgets and provenance

User-authorized shared simulation cap: 4 hours; API cap: USD 20. The pilot uses
at most two API requests with at most 600 output tokens each and reserves USD 0.10 per request in advance;
unknown outcomes remain reserved and are not retried automatically. The initial
request is limited to 30 KB. Rates: USD 0.40/M input and 1.60/M output tokens,
checked 2026-10-04 against the official model page. Cost is an estimate, not an
account billing reconciliation. Only aggregate historical summaries are sent.
The secret is read from the user-specified file and never logged or copied.

Simulation monitoring reuses the existing diagnostic executor: sequential runs,
persistent wall-clock ledger including failed attempts, 30 GiB disk reserve,
sustained critical memory-pressure and swap-growth limits. Existing attempts
cannot be overwritten; failed attempts require inspection. The budget is not a
request to exhaust all available time. Source generation cost is reported separately
from marginal warm-start cost. A newly prepared campaign is a new budget ledger;
do not create extra campaigns to bypass this task's total cap.

## Evaluation

All arms use the same finite horizon and innovation fraction 0.8. This changes the
innovation shutoff relative to the old five-iteration run, which is historical
context only. It is also not a prefix of a 100-iteration run.

Replay a preregistered three-observation stability screen with maximum ranges:
score 0.25 utility, car/PT shares 0.005 each, unfinished population 1,500. These
are illustrative screening tolerances, not empirically validated error guarantees.
Compare first screen against the same run's final-three mean; this is an offline
false-stop diagnostic, not a prospective proof. The screen alone cannot authorize
a real early stop because detailed flow, waiting and pricing checks are additional
gates. Retain all event files for those checks. Report time and peak memory,
initialization sensitivity and final-state disagreements even if unfavorable.
No reference in this pilot is automatically ground truth.

## Commands

Run from repository root with its existing `.venv` and `.tools` installations:

```sh
.venv/bin/python -m unittest discover -s experiments/acceleration -p 'test_*.py'
.venv/bin/python experiments/acceleration/pilot.py prepare --iterations 12
.venv/bin/python experiments/acceleration/pilot.py select --run-dir outputs/acceleration-pilot-TIMESTAMP --key-file /absolute/path/to/token.txt
.venv/bin/python experiments/acceleration/pilot.py run --run-dir outputs/acceleration-pilot-TIMESTAMP
.venv/bin/python experiments/acceleration/pilot.py summarize --run-dir outputs/acceleration-pilot-TIMESTAMP
```

## Research branches after this pilot

1. Initialization: multiple independent source policies, context retrieval versus
   fixed and random source baselines, multiple seeds, source-cost amortization.
2. Stopping: prefix-only features, held-out scenarios, constraint-aware error
   gates, non-LLM versus LLM decisions, false-stop and regret evaluation.
3. Budget allocation: successive resource allocation and surrogate models only
   after a reliable reference set exists.
4. Systems: profile I/O and routing independently; do not conflate changed output
   settings or behavior with algorithmic convergence acceleration.

The current Git branch contains the harness; method branches are configuration
arms with shared implementation to minimize accidental semantic differences.

Official API references:
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/models/gpt-4.1-mini

### Additional analysis and checks

```sh
.venv/bin/python experiments/acceleration/event_metrics.py outputs/acceleration-pilot-TIMESTAMP --tail 3
.venv/bin/python experiments/acceleration/check_transfer.py outputs/acceleration-pilot-TIMESTAMP
.venv/bin/python experiments/acceleration/validate.py outputs/acceleration-pilot-TIMESTAMP
.venv/bin/python experiments/acceleration/report.py outputs/acceleration-pilot-TIMESTAMP
```

Warm routes originate in the old policy and can remain initially different from
fresh cold-start routes. That is part of the initialization treatment, not evidence
of changed pricing. The normal MATSim initialization/replanning pipeline remains
active. Both advantages and bias from this asymmetry must be reported.

## Related work checked for this pilot

- [Parallel Bayesian Optimization of Agent-based Transportation Simulation](https://arxiv.org/abs/2207.05041): BEAM/MATSim calibration using Bayesian optimization and extrapolation-based early stopping. This is precedent for outer-loop calibration/budget allocation, not evidence that the present selected-plan transfer is effective.
- [Warm Starting of CMA-ES for Contextual Optimization Problems](https://arxiv.org/abs/2502.12555): contextual Gaussian-process predictions initialize an evolutionary search distribution. It motivates a numerical context baseline; its optimization state differs from MATSim person plans.

These abstract-level checks are not a systematic novelty review. Neither general
warm starting nor adding early stopping alone is a new research claim. The proposed
contribution would need held-out evidence for selective reuse under capacity and
policy changes, with explicit error/constraint preservation.

### Exploratory context addition during execution

After inspecting the static strategy settings, a second selector request adds the
60,203-person `outside` group's lack of rerouting/mode/time innovation. It receives
no target outcomes. This is an exploratory addition, not a preregistered second
method. Both selectors chose `warm_early`; this does not demonstrate that context
is useless or that this choice is superior. `check_transfer.py` compares initial
and final car-route signatures to quantify persistent noninnovating-group transfer.

```sh
.venv/bin/python experiments/acceleration/pilot.py select --run-dir outputs/acceleration-pilot-TIMESTAMP --key-file /absolute/path/to/token.txt --context-constraints
.venv/bin/python experiments/acceleration/check_transfer.py outputs/acceleration-pilot-TIMESTAMP
.venv/bin/python experiments/acceleration/status.py outputs/acceleration-pilot-TIMESTAMP
```

### Conditional fixed-background follow-up

`guarded_transfer.py` adds `guarded_warm_latest` to the **same** campaign and
four-hour ledger only after all initial arms complete, a persistent outside-group
route difference is measured, input hashes match, and sufficient budget remains.
It keeps the target cold run's **pre-mobsim iteration-0 prepared** selected plans
for `outside`, while transferring the latest historical plans for other groups.
No target experienced plans or final target scores are used. This is a post-hoc
mechanism control; preparing target background routes has a real deployment cost
and the existing cold preparation artifact must not be considered free.

```sh
.venv/bin/python experiments/acceleration/guarded_transfer.py outputs/acceleration-pilot-TIMESTAMP
```

After it completes, rerun event metrics, route-transfer checks, validation and the
report. Heavy offline analysis must run after simulations to avoid timing noise.

## Recorded local pilot

Campaign `outputs/acceleration-pilot-20261004-032117` completed four full-input
arms (389,301 persons, 12 iterations each) in 139.96 simulation minutes. Two LLM
requests cost an estimated USD 0.0012232 and both selected `warm_early`.

MATSim startup-to-first-iteration time fell from 151 seconds to approximately
38 seconds with transferred plans, excluding extraction/source/controller costs.
No equal-quality total-runtime acceleration or independently validated early stop
was established. All arms first passed the three-observation stability screen at
the final iteration, after innovation was disabled. Guarded and ordinary latest
warm starts agree within the four aggregate tolerances, yet their mean pricing-zone
car entries differ by 6.54%, illustrating why policy-specific checks are needed.

See the local [Chinese report](../../outputs/acceleration-pilot-20261004-032117/report_zh.md)
and its adjacent manifests, raw outputs, validation records and trajectory figure.
Output data are local artifacts and are not committed with the harness.

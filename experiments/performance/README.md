# MATSim performance experiment

Sequential engineering benchmark on the full launch-2025 historical-demand scenario.
This is not a convergence study, a 2025 validation, or a general speedup claim.

Run from the modernized repository root:

```sh
.venv/bin/python -m unittest discover -s experiments/performance -p 'test_*.py'
.venv/bin/python experiments/performance/benchmark.py prepare
.venv/bin/python experiments/performance/benchmark.py run --run-dir outputs/performance-TIMESTAMP
.venv/bin/python experiments/performance/benchmark.py analyze --run-dir outputs/performance-TIMESTAMP
```

Preparation snapshots the existing pilot JAR and scripts, hashes all input files,
and records the pre-existing work inventory. It does not modify the historical
pilot manifest. The default source is `outputs/acceleration-pilot-20261004-032117`.
The executor locks that campaign's `executor.lock` and charges its `budget.json`.
Creating another result directory does not create another simulation allowance.

Four iteration-0 runs, in fixed order: JFR baseline, unprofiled baseline, QSim 10
threads, and output reduction. All use GC logging. The output treatment sets
`controller.createGraphsInterval=0`, `controller.writePlansInterval=0`, and
`scoring.writeExperiencedPlans=false`. Full event files remain available every
iteration. The baseline retains the pilot's plans interval 11. No behavior,
capacity, population, event threads, or global threads are altered.

Short runs share 1,200 seconds, full validation shares 4,800 seconds, and both
obey the original remaining simulation budget. Monitoring includes startup and
termination. Failures and interruptions consume budget and are never retried
automatically. If an executor died without clearing the ledger, a subsequent
run refuses a still-existing PID; otherwise it conservatively charges all time
since the ledger checkpoint, marks the run interrupted, and stops for inspection.

A candidate must pass the effective-config whitelist, event conservation,
engine histogram/revenue reconciliation, and exact discrete/cent metrics plus
floating comparisons at rtol=1e-9, atol=1e-8. It must be at least 5% faster than
the current unprofiled short baseline. Of qualifying candidates, select the
faster one, preferring output reduction when times differ by less than 2% of
the faster time. JFR results are never ranked as a speed baseline.

Full validation runs a fresh baseline and the selected candidate for iterations
0–11, with the same innovation schedule. Order is seeded and stored before
screening. Admission estimates paired cost from historical cold duration and
the short-run ratio, with 15% margin. No candidate or insufficient budget ends
the campaign without expanding the search. Full recommendation requires all
per-iteration checks and at least 5% lower wall time. This remains a single pair.

Outputs: manifest, per-attempt config/log/resources/GC, JFR and derived views,
raw events, per-iteration event metrics, timing and difference CSVs, analysis
JSON and Chinese report. Stopwatch stages overlap: do not sum nested callbacks.
Analysis runs outside timed simulations; preparation/analysis costs are separate.

Current unit tests include realistic event fixtures; actual scenario acceptance
is enforced by the executor and complete offline analysis. Original raw data and
existing uncommitted work are preserved. No API calls, model training or PSim
integration are performed.

## Recorded local run

`outputs/performance-20261004-engineering` used 1,198.06 simulation seconds,
including a retained 0.59-second configuration-reader failure. That failure was
inspected and fixed (missing MATSim DTD); the reviewed continuation used the same
ledger, not a reset. The final preparer runs a real Java config-parser preflight.

The three completed iteration-0 runs took 317.11 seconds (JFR), 316.18 seconds
(baseline), and 352.04 seconds (QSim 10). Their required metrics matched, but the
thread candidate did not meet the 5% speed gate. The output candidate was stopped
after 212.14 seconds by the shared short-stage limit, before completing its first
iteration. No 12-iteration validation pair was launched and no fast configuration
is recommended. The 20-minute screening allocation was too tight for four full
cold starts on this machine; it was not expanded after seeing results.

The recorded run used `code/benchmark-revision2.py`; later code revisions add
preflight/reporting hardening without altering measured runs. The manifest records
these revisions. First preparation and event-analysis costs were not independently
metered in this run; future campaigns record preparation and fresh scan durations.
Cached analysis runtime must not be reported as first-time scan cost.

JFR attribution can also be reproduced with `profile_analysis.py RECORDING
--jfr-tool /absolute/path/to/jdk/bin/jfr`. Call-stack categories are inclusive and
may overlap. The local report identifies the pricing routing-cost function as a
follow-up profiling target, not an implemented or measured optimization.

## Architecture exploration without additional simulations

`architecture_profile.py outputs/performance-20261004-engineering` partitions the
existing iteration-0 JFR by the recorded stopwatch boundaries and writes
`architecture-profile.json`. This local recording uses America/New_York log time;
boundaries have one-second precision. The script does not launch MATSim or charge
the simulation ledger. Startup, pre-mobsim, mobsim, and finishing are separate.
The recording has no replanning iteration, so later-iteration cost must be read
from historical stopwatch data, and later-iteration method hotspots remain unknown.

The phase partition puts 3,952 of 3,954 sampled pricing route-cost stacks in
startup. During mobsim, the single event-processing thread contributes 6,926 of
15,662 execution samples (44.22%); this is not wall time, does not include all
blocked/native activity, and does not by itself prove a critical-path bottleneck.
Scoring is partly event-driven, so a near-zero `scoring` stopwatch row must not be
interpreted as no scoring cost. Historical cold 12-iteration data spend 1,602
seconds in mobsim and 194 seconds in replanning; nested stopwatch rows cannot be
summed indiscriminately.

# Redundancy inside the simulation: per-iteration offline measurement

Branch `perf/simulation-redundancy`. Reads the per-iteration events of completed runs only; **no new simulations**.
Data: `outputs/acceleration-pilot-20261004-032117/cold-attempt-1` (2025 pricing, full population of 389,301,
seed 4711, 12 iterations; innovation in iterations 0–8, plan selection only afterwards).
Results: `outputs/redundancy-20261004/cold/`.

## Question

MATSim re-simulates the whole population in every iteration. How much of what the previous iteration
already computed is recomputed again, exactly or approximately? Which kinds of redundancy are there, and
which acceleration approach suits each? This turns the acceleration problem into measurable quantities,
as a prerequisite for method research.

## Definitions

For every iteration i and every person, extracted from the event stream:

- **Choice signature**: leg modes plus the realized road route (link sequence), decided by replanning.
  Departure-time-only changes (TimeAllocationMutator) do not count as a choice change.
- **Outcome signature**: timestamps of all of the person's events (departures, arrivals, activities,
  boarding/alighting, link entries, ...), determined by the interaction in the traffic simulation.
- **Link-hour state**: number of vehicle entries and mean traversal time per (link, hour).

Comparing consecutive iterations, each person falls into one of three classes: exact replay (same choice
and outcome), same choice but different outcome, or changed choice.

## Results (cold run, consecutive iterations)

| Iteration | Exact replay | Same choice, outcome changed | Choice changed | Changed choices returning to an earlier plan | Same choice, \|ΔT\| ≤ 60 s | Same choice, \|ΔT\| > 15 min | Entries on link-hours changing ≤ 5%* |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 13.0% | 75.1% | 11.9% | 0% | 52.8% | 23.5% | 34.4% |
| 4 | 10.7% | 69.9% | 19.4% | 44.2% | 54.3% | 16.9% | 34.3% |
| 8 | 9.0% | 65.5% | 25.5% | 59.4% | 53.1% | 16.4% | 31.9% |
| 9 | 10.8% | 72.0% | 17.2% | 98.0% | 53.0% | 17.3% | 30.3% |
| 11 | 12.9% | 77.0% | 10.0% | 98.8% | 57.3% | 9.2% | 45.0% |

ΔT is the change in a person's total travel time over completed legs. Each iteration has about 76–96 million events.
Full per-iteration data: `redundancy.json`, `magnitude.json`, `revisits.json` (column \* from `outputs/redundancy-20261005-fixed/cold/`).

\* **Recomputed (2026-10-05).** The extractor used to pair a vehicle's arrival link with its next departure from
the same link, so parked durations could be counted as link traversal times. Only the link-hour column marked \*
depends on traversal times; it was recomputed with the fixed extractor (`iteration_redundancy.py` drops the pending
link entry on `vehicle leaves traffic` / `vehicle aborts`) and moved by at most 0.5 percentage points. Person-level
columns use departure/arrival times and are unchanged.

## Four kinds of redundancy observed

1. **Exact replay (R1, about 9–13%)**: choice and outcome identical to the previous iteration, event for
   event, yet fully re-simulated. The share is small, so exact incremental simulation ("only re-simulate
   people who changed") is not viable.
2. **Approximate replay (R2, about 40% of the population, including R1)**: same choice, total travel time
   changes by at most one minute. Suited to approximate reuse, but only with error bounds.
3. **Re-evaluating earlier plans (R3)**: among people whose choice changed, the share returning to a plan
   they already simulated rises each iteration, to 59% by iteration 8 and about 99% once innovation is
   switched off. Those plans already have scores; re-simulating them mainly updates the scores to reflect
   other people's changed behaviour.
4. **Fixed per-iteration overhead (R4)**: about 1.1 GB of event XML written every iteration, and 151 s of route
   preparation at a cold start. The first is removed by E1 below; the second already has a warm-start option.

## Implications for method design

- **Interaction-driven change is global, not local.** Even with innovation off (iterations 10–11), about 9% of
  people with an unchanged choice see their travel time change by more than 15 minutes. So simulating only
  the people who changed their plans is not enough; learned or approximate components should target
  **link-hour / transit-run level traffic state** rather than individual trajectories.
- **(Corrected 2026-10-05) Iteration-to-iteration change is mostly signal, not noise.** An earlier version of
  this document assumed that outcome changes under an unchanged plan were inherent noise usable as an
  approximation tolerance. Fixed-plan runs refute that: with identical plans and only the random seed changed,
  QSim shows 1.3% volume WAPE, about 4% link-time error and a 31 s median person travel-time difference
  (93 s mean), far below the change between consecutive iterations (8.2% volume WAPE, 107 s median, 328 s mean).
  Outcome changes under an unchanged plan are therefore mostly **real effects of other people's plan changes,
  transmitted through the interaction**. Approximation tolerances should use this stricter fixed-plan noise
  floor; see `experiments/surrogate/`.
- **R3 points to a decision problem**: does an already evaluated plan need another full simulation, or is a
  surrogate estimate of its score enough? It can be framed as budget allocation: the decision is a full
  simulation or a surrogate iteration; available features are link loads, saturation and the plan-change rate;
  the feedback arrives only several iterations later — a decision problem with delayed feedback that is hard
  to handle with hand-written rules.

## Limitations

Single scenario and seed, 12 iterations only; the choice signature excludes departure times and transit lines;
ΔT covers completed legs only; consecutive-iteration comparison is not a convergence test. The measurements
should be repeated on warm-start runs and other policies before drawing general conclusions.

## Reproduction

```sh
.venv/bin/python experiments/redundancy/iteration_redundancy.py RUN/simulation --out OUT --workers 4   # ~150-190 s per iteration
.venv/bin/python experiments/redundancy/magnitude.py OUT      # needs PYTHONHASHSEED=0 (the main script sets it itself)
.venv/bin/python experiments/redundancy/revisits.py OUT
```

## Engineering items on this branch: timed and validated

Campaign `outputs/performance-20261004-171012-redundancy` (independent ledger, 6,124 / 14,400 s used; report `report_zh.md` there).

- **E1 + E2, 12-iteration pair: wall time 2,139.9 → 1,574.0 s (−26.4%), mobsim 1,611 → 1,063 s (−34%),
  output 15.1 → 2.9 GB.** Zero per-iteration metric differences over 12 iterations: counts and cents exactly
  equal, other values within rtol 1e-9.
- Almost all of the gain comes from **E1** (online metrics instead of per-iteration event XML).
  E2 (index-based pricing lookups) is bit-identical at full scale, but its timing change is within noise (−2.9% in screening).
- JFR: of the events thread's execution samples, XML writing is 37–39%; dispatch, scoring and travel-time
  statistics are 14–21% each; the custom pricing handlers only 3–4%.
- This addresses R4 above. Afterwards mobsim still takes 74–108 s per iteration and grows over iterations.
  What remains comes mainly from R1–R3 (the interacting simulation itself) and calls for approximate or learned
  methods; exact-result engineering alone will not remove it.
- Single scenario, seed and pair. E1 writes no event files by default; set `writeEventsInterval` to the last
  iteration when events are needed.

Reproduction:

```sh
.venv/bin/python experiments/performance/redundancy_campaign.py prepare --baseline-jar PRE_E2_JAR --limit-seconds 14400
.venv/bin/python experiments/performance/redundancy_campaign.py run --run-dir outputs/performance-TIMESTAMP-redundancy
.venv/bin/python experiments/performance/critical_path.py outputs/performance-TIMESTAMP-redundancy/short-profile JDK/bin/jfr
```

Offline equivalence checks (no simulation needed):

```sh
java -cp target/matsim-nyc-modernized-1.0.0.jar:target/regression-classes org.c2smart.matsimnyc.VerifyPricingReplay CONFIG EVENTS
java -cp target/matsim-nyc-modernized-1.0.0.jar:target/regression-classes org.c2smart.matsimnyc.ReplayIterationMetrics CONFIG EVENTS ITERATION OUTDIR
```

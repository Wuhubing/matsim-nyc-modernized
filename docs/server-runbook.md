# ORCD reference and research-data runbook

This workflow separates historical reproducibility, observational instrumentation checks, baseline calibration diagnostics,
and policy experiments. A completed job is not evidence of convergence, calibration, or paper reproduction.

## Current validation and restart policy

Keep the original job 25110162 and its files as the unmodified 75abcdd reference. Do not overwrite its JAR or output.
New builds use `target-research/`; prepared snapshots copy the JAR, source and scenario inputs into a unique directory.
Each Java process also loads its own private `runner.jar`. New experiments start at iteration 0 in new output directories.
No automatic cancellation, deletion, or reuse of a partial run is performed.

Run from an ordinary ORCD SSH terminal:

```sh
cd ~/matsim-work/matsim-nyc-modernized
bash experiments/reference/prepare_research.sh
```

This compiles offline with the cached Maven dependencies, runs synthetic regressions and Python checks, prepares inputs,
freezes a snapshot, and submits a three-task validation array to `mit_normal`. With `--prepare-only`, it creates the snapshot
without contacting Slurm. The latest snapshot path is saved in `~/matsim-work/latest-research-snapshot.txt`.

The three checks use 16 CPUs, 32 GiB requested memory, and a 24 GiB Java heap per task:

| Task | Scenario | Iterations | Additional recording |
|---|---|---|---|
| 0 | actual2025 | 12 | legacy metrics only, events off, JFR off |
| 1 | actual2025 | 12 | research metrics, events every 10, JFR |
| 2 | historical baseline | 2 | research metrics, events every iteration, JFR |

Tasks 0/1 retain the historical innovation fraction of 0.8 and seed 4711. Their legacy metrics and score tables must match
the archived Mac results exactly. Added research data lives in separate files. Verification failure is propagated to Slurm;
there is no `|| true`. The gate also compares tasks 0 and 1 directly, checks mode shares, and checks research/legacy totals.
A cross-platform difference blocks automatic continuation and must be investigated; never replace the expected answers to
make a failed run pass. Timing ratios from these concurrent jobs are screening measurements, not controlled benchmarks.

Each validation has one hour **after allocation**, independently of any interactive `salloc`. Builds in an interactive shell
use that shell's allocation time. Batch jobs persist after disconnecting. Query with `squeue -u "$USER"`; if absent, inspect
`sacct -j JOBID --format=JobID,State,ExitCode,Elapsed,MaxRSS` and logs. The agent's sandbox may lack network access even when SSH works.

## Filesystem and provenance

Code/snapshots stay under shared `~/matsim-work`. Large results go under the unique snapshot directory beneath
`~/orcd/scratch/matsim-work`, which resolves to `/orcd/scratch/orcd/006/weibingw/matsim-work` in this account.
Slurm stdout files are in the snapshot directory; detailed simulation logs are in each result directory.

`df` reports filesystem-wide space, not the user's quota. The submission helper displays `df` and tries `quota -s` when
available, but a missing or empty quota report does not prove unlimited quota. Confirm the applicable scratch quota and
retention policy with ORCD before retaining large campaigns; copy important results to durable storage.

The runner records SHA-256 hashes of the JAR, resolved config, loaded file inputs, capacity factors and cohort polygon;
the snapshot manifest records the copied code and inputs, including uncommitted edits. It also records seed, host, job ID,
Java heap, threads, recording settings, input plans and innovation schedule. Do not pool differently configured runs merely
because they have the same seed. `.venv` is shared with the workspace; avoid changing dependencies during a campaign.

Free filesystem space is sampled during execution, with a default 5 GiB floor that stops the run. This cannot predict
quota exhaustion or rapid writes between samples. I/O failures are errors. Audit reports measure actual output sizes and
provide a rough 100-iteration extrapolation; there is no guaranteed 1.1 GB/event-file size or negligible-overhead promise.

## What is recorded

| Data | Frequency | Interpretation |
|---|---|---|
| Legacy `iteration-metrics-N.json` | Every iteration | Original aggregates, unchanged schema and summation order |
| scorestats, modestats, stopwatch | Every iteration | Score, mode shares and simulation stages |
| countscompare | Every iteration (`writeCountsInterval=1`) | Supplied count stations and MATSim's configured scaling |
| `research/persons-N.csv.gz` | Every iteration | Person ID, fixed cohorts, score/delta, plan memory size, SHA-256 plan/choice signatures, realized diagnostic hashes, trip-leg/wait/toll totals |
| `research/groups-N.csv.gz` | Every iteration | All, subpopulation, charging cohort, and joint-group totals; includes score sums/denominators and plan-change counts |
| `research/group-modes-N.csv.gz` | Every iteration | Departures/completions/stuck legs and completed travel time by group/mode |
| `research/link-hours-N.csv.gz` | Every iteration | Every observed network link/hour/mode: entry count, matched traversal count and total traversal seconds |
| `research/cohorts.csv.gz`, `schema.json` | Once per run | Group membership and exact definitions/limitations |
| Plans | Every 10 iterations plus MATSim final output | Full plan sets for warm starts; inspect actual final artifacts before policy submission |
| Full events | Every 10 iterations by default | Detailed offline analysis at saved iterations; set `EVENTS_INTERVAL=1` for all iterations |
| `resources.jsonl`, `gc.log`, `profile.jfr` | Samples / JVM events | CPU time, RSS, threads, process I/O, disk free space, GC and bounded flight recording |
| `research/diagnostics-N.json` | Every iteration | Invariant errors, fingerprint time and research-output time |

Full events are sampled, so they cannot reconstruct every intervening iteration. Compact diagnostics support adjacent-iteration
analysis but are not a replacement for all event-level research: planned signatures exclude simulated travel estimates; realized
64-bit hashes are diagnostics with collision risk and do not cover every MATSim event type. Exact replay claims require the
full relevant event streams. For model training, split by seed/run/scenario and time as appropriate; avoid leakage across adjacent
iterations. Resource traces and optional JFR support bottleneck analysis, not a causal attribution of every slowdown.

Link traversal statistics pair LinkEnter/LinkLeave only, assigned to entry hour. Initial partial links are omitted, and exit/abort
clears pending entries to avoid counting parking as travel. Sparse missing cells mean zero observations. `completed_traversals`
is the denominator for mean travel time, not entry count. These raw vehicle counts have no population expansion applied.

Group modes count **legs**, not whole origin-destination trips (transit journeys have several legs). Car-duration means cover
completed legs; waiting includes unfinished waiting until the configured simulation cutoff. Keep censored outcomes separate
from completed ones. `private_car_entry_crossings` retains the old 2025-geofence definition across all scenarios for compatibility;
it is not the number of Schema-1 toll payments.

## Stable cohort definition

`subpopulation` comes from the archived person attribute (`man`, `nonman`, `outside`, with explicit unknown handling).
Charging-related means at least one non-stage activity location in the **loaded selected plan** is inside the repository's
reconstructed Schema-1 charging polygon. This includes trips wholly inside the area and all modes. Polygon boundary points
are included; missing coordinates produce `unknown` unless another activity establishes membership.

Membership is fixed before replanning and saved explicitly, not inferred from whether the person paid a toll. When comparing
baseline and warm-start policy runs, join cohort manifests by person ID and check equality; use the baseline manifest if an
activity-location-changing strategy is later introduced. The boundary is an exploratory reconstruction, not the original paper's
authoritative cordon, and must be validated before claiming identical population segments.

## Baseline campaign and convergence

After all validation tasks finish:

```sh
snapshot=$(cat ~/matsim-work/latest-research-snapshot.txt)
bash "$snapshot/experiments/reference/submit_research.sh" baseline
```

The helper reruns the validation gate and submits three baseline seeds (4711–4713), 100 iterations, at most eight hours per task.
Read the measured validation durations first: eight hours is a resource limit, not a completion estimate. If needed, adjust the
submission limit using a new reviewed snapshot/helper invocation; never silently shorten the scientific iteration horizon.

Research runs explicitly set innovation strategies' `disableAfter=79`; they do not infer a new cutoff from the requested horizon.
For 100 iterations (0–99), this separates the innovation and selection-only phases. A 50-iteration experiment with this schedule
is a truncated innovative run, not a 50-iteration run that disables innovation at 40. Extension experiments must state whether they
extend innovation or only selection. Legacy 12-iteration verification intentionally retains the old fractional schedule.

```sh
.venv/bin/python experiments/reference/analyze_reference.py RUN1 RUN2 RUN3 --window 10 --out analysis.json
```

The analysis reports sliding adjacent-window changes, tail means/SDs, seed spread, measured iteration times, and supplied-count
errors. Its default 1% window flag is explicitly exploratory, **not a scientific acceptance criterion**. Predefine per-metric absolute
and relative quality margins, group-level margins, and the required persistence window before judging acceleration. Three seeds
provide only a preliminary variance estimate. A stable total can hide unstable groups/links; use their saved series too. A flat
selection-only tail is not proof that the model converged while innovation was active. Shorter stopping rules require independent
validation across seeds and policies. Do not call an empirical reference trajectory a unique ground truth.

## Paper reproduction versus policy extension

Source: https://arxiv.org/abs/2008.04762 (v2, sections 4–5). The paper uses historical baseline calibration and starts policy runs
from the baseline final plan set. Its charging-related definition uses trip origins/destinations in the charging area. We implement
that definition on the available reconstructed boundary, and expose `--plans` for the full baseline plan set.

Run the historical baseline first. For each seed, after successful completion and convergence review, locate
`simulation/BUILT.output_plans.xml.*` and use that full plan set for matched policy runs:

```sh
# From the prepared snapshot, with JAVA_HOME and OUTPUT_ROOT set:
SCENARIO=schema1 PLANS=/absolute/baseline/simulation/BUILT.output_plans.xml.zst \
SEED=4711 ITERS=100 RESEARCH=1 INNOVATION_UNTIL=79 EVENTS_INTERVAL=10 \
sbatch -p mit_normal --export=ALL experiments/reference/reference.sbatch
```

Repeat with corresponding baseline seed/plan files; use a new OUTPUT_ROOT for each campaign to keep records clear.
`actual2025` is a separate extension, not evidence of historical calibration. `--factors` accepts a capacity vector for future
calibration experiments and records its hash. No optimizer is run automatically, and the old “20 hours” calibration estimate is
not a measured budget on this cluster.

Counts comparisons must match observed stations, direction, time bins, modes and scale (currently countsScaleFactor=25).
The analysis's all-station error is not automatically the paper's East River screenline error. The paper reports different error
measures for screenlines, road links, speed and transit; a universal “within 5%” rule is not justified. Resolve the station mapping
and original observation datasets before making a reproduction claim.

Remaining reproduction prerequisites: authoritative/validated cordon geometry, availability and provenance of the final calibrated
parameters and historical observations, the paper's second pricing schema if reproducing both policies, and travel-utility component
accounting. Total selected-plan score is **not** the paper's travel consumer surplus and must not be converted directly to dollars.
The current changes provide measurement and experiment controls; they do not certify paper reproduction.

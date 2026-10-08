# Plan: learning which agents and trips to replan in MATSim-NYC (an L2Seg analogue)

Branch `research/l2seg-replanning`, started from `main` on 2026-10-07. It is the working plan; results are added in
place as each stage finishes.

**Status 2026-10-07.** W0–W3 are implemented and the detailed recorder (ResearchMetrics) is ported (Section 9.1);
12-iteration acceptance runs are listed there. No study run (RQ1–RQ6) has started. The RQ0 references now running
on ORCD are **not** the configuration this plan assumes (Section 4.1); this needs a decision before σ_x is used.

Evidence cited below comes from branch `perf/simulation-redundancy` (head `75abcdd`), referred to as *perf*.
The method being adapted is Ouyang, Li, Ma, Wu, *Learning to Segment for Vehicle Routing Problems*,
arXiv:2507.01037v2 (2025), referred to as *L2Seg*.

## 1. Claim and structure

A policy study costs *runs × iterations per run × cost per iteration*. Exact engineering has brought the last
factor close to its floor, and replacing the traffic simulation by an approximation (PSim) is biased because
agents interact through congestion and transit crowding. We therefore always simulate every agent exactly and
apply L2Seg's idea, "predict what is still unstable and re-optimize only that", to **replanning**, at three levels:

| Level | What is held fixed | What is re-optimized | Role in the study |
|---|---|---|---|
| **Policy** (main line, Section 5) | agents a new policy does not affect, warm-started from the baseline equilibrium | agents predicted to be affected | main contribution: fewer iterations per policy, fewer policy runs |
| **Agent** (Section 6) | agents predicted to be resolved within one run | agents predicted to be unresolved | method building block; measures the oracle ceiling |
| **Trip** (Section 7) | stable trips inside a replanned plan, kept as fixed segments | trips whose route is predicted to change | the one level where the problem itself gets smaller, as in FSTA |

The policy level is the main line because (a) within a single run innovation only happens in the first 80% of
iterations, which caps any saving, and (b) after a policy change most agents are unaffected, so the signal
"who needs re-optimization" is stronger. This is also the setting L2Seg cites as its predecessor: Morabit,
Desaulniers and Lodi (2024), *Learning to repeatedly solve routing problems*, which studies segment stability
when re-solving a changed routing instance.

At the policy and agent levels the saving comes **only from fewer iterations and fewer runs**; an iteration
costs the same. Only the trip level reduces the size of a replanning step, and replanning is a small share of
an iteration (Section 2). Targets, not results: 2–4× fewer iterations per policy compared with a cold start, and
2–3× fewer policy runs through adaptive sampling. How warm starts and targeting combine is measured, not
multiplied in advance.

## 2. What is already known (perf branch)

| Item | Result | Source on perf |
|---|---|---|
| Iteration cost (workstation) | ≈118 s (replanning ≈15, mobsim ≈88.6, scoring/stats ≈14.1) on 16 threads, 389,301 persons + ≈51,000 transit drivers | **Source found only for mobsim:** 88.6 = 1,063 s / 12 iterations, the E1+E2 run of the perf campaign (`experiments/redundancy/README.md`, workstation). The 15 and 14.1 s have no recorded breakdown on perf and are superseded by the ORCD rows below |
| Iteration cost (ORCD, launch-2025, E1+E2) | **223 s** mean over iterations 0–11: replanning 26.7 s in innovation iterations 1–8 and < 1 s afterwards, mobsim 179.6 s, before-mobsim listeners 5.8 s, iteration-end listeners 11.0 s; wall 2,919 s incl. ≈240 s start-up | `BUILT.stopwatch.csv` of job 25110162 (perf 75abcdd, seed 4711, 12 iterations, AMD EPYC 9474F, 16 threads; its online metrics equal `expected-seed4711-12it.json`). ORCD is ≈1.9× slower per iteration than the workstation; **the share of replanning (≈12% of an innovation iteration) is unchanged** |
| Iteration cost (ORCD, 100-iteration baseline references, interim) | mean 268–303 s over iterations 0–40/46; iterations 31–46: replanning 32–38 s, mobsim 227–270 s; mobsim grows within the run (seed 4711: 164 s in iterations 1–10 → 227 s in 31–46) | jobs 25151308_0–2 at iterations 41–47 (2026-10-07 12:09). These runs also record ResearchMetrics and JFR (Section 4.1), so absolute times include that overhead; final numbers after the runs end |
| Replanning | 194 s over a cold 12-iteration run (≈16 s per iteration), vs 1,602 s mobsim | `experiments/performance/README.md` |
| Mobsim growth | 74 → 108 s per iteration within a run (after E1) | `experiments/redundancy/README.md` |
| E1 + E2 (online metrics instead of per-iteration event XML; index-based pricing lookups) | 12-iteration wall time 2,139.9 → 1,574.0 s (−26.4%), all metrics identical; almost all of it from E1 | same, "Engineering items" |
| Choice changes | 10–25% of agents change choice per iteration | same |
| Approximate replay (R2) | ≈40% of agents keep **the same choice** and their travel time moves by ≤ 60 s | same |
| Revisits (R3) | among choice changes, the share returning to an already simulated plan reaches 59% by iteration 8 and ≈99% once innovation is off | same |
| Interaction | with innovation off, ≈9% of agents with an unchanged choice still see travel time change by > 15 min | same |
| Noise floor | same plans, different seed: 93 s mean person travel-time difference, vs 328 s between consecutive iterations | `experiments/surrogate/README.md` |
| L1 learned travel-time correction | error on changed plans 579 → 535 s (≈8%) | same |
| L2 PSim for most iterations | iteration cost 1/1.6–1/2.2; final-score bias −20% to −74%, mostly underestimated transit crowding | same |
| L3 charge interpolation | ≤ 1% above the current charge; +11–16% at half charge (kink in cordon entries near zero) | same |

Configuration facts that constrain the design (`scenarios/nyc-zip-aligned/config-actual2025.xml`, identical on
`main`): subpopulations `man` and `nonman` use SelectExpBeta 0.7 and TimeAllocationMutator, ReRoute,
SubtourModeChoice at 0.1 each; `outside` only selects; `maxAgentPlanMemorySize = 5`;
`fractionOfIterationsToDisableInnovation = 0.8`. **Innovation stops at 80% of the run**; shortening a run moves
the switch-off point with it.

Routing inside these strategies (MATSim 2026.0 source, `org.matsim.core.replanning.strategies`):
`ReRoute` re-routes every trip of the plan; `SubtourModeChoice` changes the modes of one subtour and then runs
the same full-plan `ReRoute` module, so trips outside the changed subtour are re-routed too;
`TimeAllocationMutator` (without `ReRoute`) shifts times and keeps routes.

## 3. Mapping to L2Seg, and what does not transfer

| L2Seg (VRP) | MATSim-NYC |
|---|---|
| Solution: set of routes | the selected plan of each of the 389,301 agents |
| Route = sequence of customers joined by edges | plan = sequence of activities joined by trips (Section 7) |
| Stable edge: unchanged over the next *k* search steps (labels use *k* = 1, App. A.1) | resolved agent / stable trip / policy-unaffected agent (Section 4) |
| Search step (LKH-3, LNS) | replanning: innovation (time, route, mode) plus selection among stored plans |
| Hypernode: aggregated stable segment, kept fixed while the rest is re-optimized | stable trip kept with its current route while other trips are re-routed (Section 7) |
| No decomposition: every edge may be re-optimized | every agent may innovate; every trip of a replanned plan is re-routed |
| Random FSTA (40%/60% of edges marked unstable, Table 3) is **worse than no decomposition** | **today's default**: 30% random innovators per iteration |
| Repeatedly solving a changed instance (Morabit et al. 2024) | warm-starting a new charge level from the baseline equilibrium (Section 5) |
| Labels: one-step look-ahead with the backbone solver | labels L-H, L-U, L-P, L-T (Section 4); look-ahead is not possible after trajectories diverge |
| NAR (global, one shot) and AR (local, sequential) decoders | per-agent / per-trip gradient-boosted model first; graph model over agents sharing links or transit runs only if needed |
| Metric: objective vs wall time | distance to the reference steady state vs iterations (and wall time) |

What does not transfer:

1. **The mechanism of the speedup.** FSTA aggregates stable segments into hypernodes, so each search step solves
   a smaller problem (L2Seg, Section 3.2, Fig. 5 plots objective against wall time). Here every agent is still
   simulated every iteration. Only the trip level (Section 7) makes replanning smaller, and replanning is
   ≈16 of ≈118 s on the workstation and ≈27 of ≈223 s on ORCD (Section 2), about 12% of an innovation iteration
   and ≈0 once innovation stops.
2. **The guarantee.** FSTA's feasibility and monotonicity theorem relies on route costs being additive over
   edges, so fixed segments do not affect the rest. Agents frozen in MATSim still occupy roads and vehicles; this
   is why freezing them in the simulation (L2) was biased. We segment *replanning*, never *simulation*. The trip
   level keeps a weaker analogue (Section 7.3).
3. **Oracle → model loss.** L2Seg's Table 5 (CVRP2k, time to reach the learned model's quality): perfect oracle
   39 s, 95% recall/TNR 62 s, 90% 119 s, 70% 324 s, learned L2Seg-SYN 241 s. A learned predictor keeps only a
   fraction of the oracle's gain; the gates below are set with this in mind.
4. **Drift of the unstable set.** L2Seg App. E.6: overlap of predicted unstable edges between adjacent steps
   rises only from 28% to 54%. Targets are re-predicted every iteration and a random share ε of the budget is
   kept (W3).

## 4. Definitions

**Run schedule.** Unless stated otherwise: 100 iterations (0–99), innovation until iteration 79, seeds
4711/4712/4713, launch-2025 configuration with `assumptions/archive-capacity-factors.csv`, as in
`experiments/reference/run_reference.py` on perf. *Charge scale* τ multiplies all congestion charges
(τ = 1 is launch-2025), using the pricing-scale lever already on perf.

### 4.1 The RQ0 references running on ORCD (checked 2026-10-07)

Jobs 25151308_0–2 (seeds 4711–4713, 100 iterations, started 08:35) were submitted from a snapshot of branch
`research/reference-instrumentation` (runner commit 996faa0 plus the cutoff fix 7e06a3d), **not** with perf's
`reference.sbatch`. Compared with the configuration perf's runner writes for launch-2025:

- **Scenario `baseline`, not launch-2025.** `pricing2025Links` is removed and road pricing reads
  `scenarios/nyc-schema1/control-zero-tolls.xml`: there is no 2025 congestion charge. Cordon entries are still
  counted (on the 2025 entry links), revenue from the charge is zero. This is also not τ = 0 of the
  `nyc.pricing.scale` lever, which leaves taxi/FHV trip fees in place.
- Innovation cutoff set as `disableAfterIteration = 79` with fraction 1.0; for 100 iterations this is the same
  schedule as fraction 0.8 (innovation in iterations 0–79).
- ResearchMetrics (per-person, group and link-hour records), JFR, events every 10 iterations, 24 GB heap.

Consequences: when they finish, they give T\* and σ_x **for the no-charge baseline**, not for τ = 1 as the
definitions below assume. The instrumentation branch's design is to warm-start policy runs from the baseline's
final plans, i.e. τ0 = baseline and τ1 = launch-2025, which is a different main-line setting from Section 5
(τ0 = 1). **Decision needed:** either (a) adopt baseline → launch-2025 as the first policy change and take σ_x
from the baseline references, checking it at τ = 1 with one extra seed set; or (b) run three launch-2025
references as originally planned (3 more full runs, Section 10). Until decided, the tolerance table below is
not filled in.

### 4.2 RQ0 results for the baseline references (finished 2026-10-07, wall 8.7–9.5 h)

All three runs completed (8 h 41 min, 9 h 30 min, 8 h 48 min with ResearchMetrics and JFR on; within the 12 h limit),
and all three research audits passed. Tolerance table (`experiments/l2seg/tolerance.py`, window 90–99,
`outputs/rq0/tolerance-baseline.json`):

| Indicator | x̄ | σ | σ / \|x̄\| |
|---|---:|---:|---:|
| Mean executed score | 6.769 | 0.0065 | 0.1% |
| Car share | 0.4261 | 0.00074 | 0.17% |
| PT share | 0.2116 | 0.00005 | 0.02% |
| Walk / taxi / FHV / ride / bike share | 0.1350 / 0.1107 / 0.0787 / 0.0203 / 0.0166 | 0.00008 / 0.00057 / 0.00011 / 0.00003 / 0.00008 | ≤ 0.5% |
| Car departures / completions | 522,804 / 514,621 | 920 / 917 | 0.18% |
| Unfinished persons | 16,486 | 45 | 0.27% |
| Cordon entries (2025 entry links) | 34,846 | 134 | 0.39% |
| Transit waiting, person-hours | 229,770 | 579 | 0.25% |
| Bridge/tunnel count total, simulated | 2,544,100 | 3,790 | 0.15% |
| Net charge revenue | 0 | 0 | (no charge) |

**Finding 1: the T\* rule in this section is degenerate and must be restated (overturns the rule as written).**
σ is the spread across seeds of 10-iteration *means*, but T\* compares *single* iterations with 2σ. Within
iterations 90–99 a single run fluctuates more than that: the within-run standard deviation is 2.0–2.1 σ for the
score and 3.1–4.4 σ for the PT share, so only 40–60% of the references' own last iterations fall inside 2σ and
**T\* is undefined for all three references**. The rule was fixed before seeing results, but it cannot be satisfied
even by the runs that define it, so it is a definition error, not a threshold to tune. Proposed restatement with
the same 2σ: T\* is the first t such that the mean over t..t+9 is within 2σ of x̄ for every indicator (the same
quantity σ is computed from). With it, **T\* = 88, 89, 89**. Not yet adopted; needs agreement.

**Finding 2: the runs do not settle while innovation is on (answers RQ0's main question; overturns the
expectation in the runbook that runs settle before iteration 80).** 10-iteration means of seed 4711:

| Iterations | Score | Car share | PT share | Unfinished | Count error (total) |
|---|---:|---:|---:|---:|---:|
| 0–9 | −11.25 | 0.261 | 0.341 | 43,692 | −16% |
| 20–29 | −0.65 | 0.313 | 0.262 | 22,372 | +18% |
| 40–49 | 2.14 | 0.352 | 0.236 | 18,944 | +26% |
| 60–69 | 3.50 | 0.379 | 0.221 | 17,862 | +29% |
| 70–79 | 4.00 | 0.391 | 0.215 | 17,724 | +30% |
| 80–89 | 6.67 | 0.426 | 0.212 | 16,536 | +36% |
| 90–99 | 6.77 | 0.426 | 0.212 | 16,460 | +37% |

Score and car share still rise steadily at iteration 79; the step at 80 is the innovation switch-off (random
innovators stop executing non-best plans), after which everything is flat. So the "steady state" of this schedule is
produced by switching innovation off, and its level depends on how long innovation ran. Consequences: (i) a shorter
schedule would end at a different state (lower car share), so "fewer iterations" cannot be judged against T\*
alone but only by matching the 100-iteration end state; (ii) per the runbook, a longer horizon (150–200 iterations)
is needed to see whether the drift itself stops; (iii) the oracle and warm-start comparisons (RQ2, RQ5) remain
well defined, because they compare end states.

**Finding 3: the East River screenline is far outside the paper's 5% (calibration risk in Section 12 has
materialised).** What the paper says (arXiv:2008.04762, Sections 3.2 and 4.2–4.3, read 2026-10-07): the network
was calibrated with SPSA on 12 capacity factors (2 road types × 6 periods) against 19 bridges/tunnels (Table 1),
50 MATSim iterations per SPSA step, 6 steps "until the simulated screenline volumes were observed to be within 5%
of the observed data"; the **5% applies to the East River screenline** (Queensboro, Williamsburg and Manhattan
bridges, Queens-Midtown and Hugh Carey tunnels, Brooklyn Bridge), whose total daily simulated volume ended
**+1.8%** from the counts (10.3% mean error per time period); arterial speeds were within 17.1% of INRIX and key
road-corridor counts had a 39.8% mean / 29% median difference in validation. A 44-station total, as first reported
here, is not the paper's measure; that number (+37%) is withdrawn as a calibration test.

Mapping the count links to facilities by their coordinates (`count.xml.gz` has no names): Queensboro = stations
5–8 and 44, Queens-Midtown = 1 and 21, Williamsburg = 16, 31, 32, Brooklyn = 19 and 20, Hugh Carey = 17 and 37;
**the Manhattan Bridge has no count station** in the file, so the screenline below has five facilities on both
sides (observed 509,173 vehicles per day). Baseline references, daily totals:

| | Iteration 0 | 20 | 49 | 79 | 90–99 mean |
|---|---:|---:|---:|---:|---:|
| Screenline error, seeds 4711 / 4712 / 4713 | −18% | +60 to +63% | +64 to +69% | +69 to +72% | **+74 to +76%** |

At iteration 99 by facility: Queens-Midtown **+222 to +224%**, Hugh Carey **+213 to +221%**, Brooklyn +43 to +48%,
Queensboro +30 to +32%, Williamsburg +2%. The excess is concentrated on the two MTA-tolled tunnels. Likely cause
(not yet tested): the facility tolls (`LegacyCosts`: $6.12 at MTA tunnels, PANYNJ tolls) are charged only as
score money events; the router's car disutility sees only the road-pricing scheme, which in the baseline is the
all-zero control file, so re-routing treats the tolled tunnels as free. The 50-iteration point (+64 to +69%) shows
the gap is not caused by running 100 instead of 50 iterations. Next steps, in order: check how the archived
C2SMART code routed with facility tolls; test toll-aware routing for `LegacyCosts` in a 12-iteration run (this
changes results, so it is a model decision); only then decide on SPSA recalibration (≈20 h).

**Toll-routing check (2026-10-07, 12 iterations, baseline, seed 4711, innovation to 79).** The archived C2SMART
code (Zenodo 7430184, MD5 as in PROVENANCE.md; `Run.java` emits `TollPersonEvent1/2`, scored in `NewScoring`)
also charges facility tolls only in scoring, so toll-blind routing is the original model's behaviour, not a
porting loss. Job 25218415 (unchanged code) reproduces the first 12 iterations of the seed-4711 reference exactly
(all IterationMetrics and scores), so the current branch and the RQ0 runs are interchangeable. Job 25218416 adds
the facility tolls to car routing (`--legacy-toll-routing`, diagnostic only, off by default):

| Iteration 11 | Screenline | Queens-Midtown | Hugh Carey | Queensboro | Williamsburg | Brooklyn | Car share | Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Toll-blind (control) | +51% | +185% | +157% | +13% | −10% | +23% | 0.2789 | −5.065 |
| Toll-aware routing | +48% | +76% | +72% | +49% | +11% | +52% | 0.2776 | −5.348 |

Toll-aware routing moves traffic from the two tunnels to the free bridges (at iteration 0 the tunnels are 70–86%
*below* their counts) but leaves the screenline total almost unchanged. **The screenline excess is a demand
effect, not a route-split effect:** the total crossing volume starts 18% below the counts and grows with the car
share over the iterations (Finding 2). Capacity recalibration (what SPSA adjusts) is therefore unlikely to remove
it alone; the drift of mode choice towards car needs to be understood first (scoring parameters, transit
crowding, the `outside` background traffic are candidates).

### 4.3 Why the car share drifts (diagnosis in progress, 2026-10-07)

From the RQ0 seed-4711 records (`research/group-modes-N`, IterationMetrics), no new runs. Leg departures, iteration
0 → 99:

| Subpopulation | Car | PT | Taxi | FHV |
|---|---|---|---|---|
| `outside` (background, selection only) | 61,604 → 62,208 (flat) | 112,770 → 119,803 | – | – |
| `nonman` | 207,484 → 388,612 (+87%) | 478,031 → 204,230 (**−57%**) | 10,281 → 60,340 | 1,886 → 17,827 |
| `man` | 36,429 → 71,696 (+97%) | 496,124 → 283,103 (**−43%**) | 12,254 → 76,812 | 8,179 → 79,521 |

The background traffic is ruled out. Residents leave transit for car, taxi and FHV. Transit service at the start
is very poor and improves as riders leave:

| Iteration | PT legs | PT legs unfinished at 30 h | Waiting per PT leg (incl. censored) | PT leg | Car leg |
|---:|---:|---:|---:|---:|---:|
| 0 | 1,086,925 | 4.6% | 58 min | 34 min | 78 min |
| 10 | 856,123 | 2.6% | 36 min | 27 min | 55 min |
| 40 | 688,401 | 1.5% | 25 min | 23 min | 52 min |
| 99 | 607,136 | 1.3% | 23 min | 22 min | 46 min |

Transit vehicle capacities are not under-scaled: buses carry 9–12 and subway trains 165–210 persons, about 2–3 times
a 4% scaling of real vehicles (70–110 per bus, 1,500–2,500 per train), consistent with the paper's choice of flow
capacity 0.15 instead of 0.04 for roads. The load comes from demand: 1.09 M PT legs at iteration 0 is 2.8 per
person; a rough 4% scaling of NYC's ≈8.5 M daily unlinked transit trips (2016, not yet verified) gives ≈0.34 M,
so the initial plans carry about 3× the real transit demand, and still ≈1.8× at iteration 99. Working hypothesis:
transit is overloaded by inflated initial demand, agents shed it to road modes over 80 iterations, which raises
cross-river car volumes (Section 4.2, Finding 3). Next checks: the real 2016 ridership figure; trips and PT legs per
person in the initial plans against the paper's population summary; subway station boardings (events of
iterations 0 and 99) against the paper's turnstile validation (e.g. Times Square 191,425 observed, 202,363
simulated in the paper); the mode constants and cost coefficients in the scoring configuration.

**Checks done (2026-10-07).** Outputs in `outputs/rq0/transit-check/` (scripts `experiments/l2seg/plans_stats.py`,
`experiments/l2seg/ridership.py`, Slurm jobs 25224295 and 25224705).

1. *Real ridership.* MTA reports 2016 average weekday ridership of 5,655,755 subway entries and 2,038,119 NYCT bus
   rides ([MTA](https://www.mta.info/agency/new-york-city-transit/subway-bus-ridership-2019),
   [Baruch NYC Data](https://www.baruch.cuny.edu/nycdata/travel/mta-subwayridership.html)). Turnstile entries do not
   count in-system transfers, so vehicle boardings are higher; ≈9–10 M boardings per day is the order of magnitude.
2. *Initial and final plans (selected plans; trips split at activities; main mode = first non-walk leg).*

   | Subpopulation | Trips/person | PT | Car | Taxi | FHV | Walk |
   |---|---:|---|---|---|---|---|
   | `man` (123,290) | 3.35 | 0.509 → 0.268 | 0.091 → 0.173 | 0.031 → 0.186 | 0.021 → 0.192 | 0.318 → 0.150 |
   | `nonman` (205,808) | 3.28 | 0.306 → 0.123 | 0.313 → **0.576** | 0.016 → 0.089 | 0.003 → 0.026 | 0.266 → 0.135 |
   | `outside` (60,203) | 2.45 | 0.460 → 0.458 | 0.447 → 0.447 | – | – | 0.093 → 0.095 |

   (initial = `cold.xml.gz`, final = seed-4711 reference `output_plans`). Trip rates are plausible. Linked PT trips
   are ≈485 k initially (≈12.1 M/day scaled by 25, about twice the ≈6–7 M linked transit trips implied by the
   ridership above) and ≈261 k at the end (≈6.5 M/day, close to reality). The initial plans' PT legs (1.71 per
   `man` resident) are not comparable with simulated legs, because routing splits trips into several PT legs.
3. *Subway boardings at the paper's ten validation stations* (all boardings incl. transfers, × 25; turnstile data
   exclude transfers, so transfer hubs are overstated):

   | Station | Real (turnstile) | Paper simulated | Iteration 0 | Iteration 99 |
   |---|---:|---:|---:|---:|
   | Times Square | 202,363 | 191,425 | 225,800 (+12%) | 183,525 (−9%) |
   | Grand Central | 158,580 | 170,025 | 226,775 (+43%) | 185,400 (+17%) |
   | 34 St – Penn Station | 173,108 | 256,825 | 237,700 (+37%) | 221,450 (+28%) |
   | 34 St – Herald Sq | 125,682 | 124,500 | 246,875 (+96%) | 214,050 (+70%) |
   | 14 St – Union Sq | 106,718 | 97,825 | 237,300 (+122%) | 176,625 (+66%) |
   | Fulton St | 85,440 | 83,025 | 102,200 (+20%) | 79,350 (−7%) |
   | Canal St | 70,806 | 78,250 | 151,175 (+114%) | 119,675 (+69%) |
   | 59 St – Columbus Circle | 73,836 | 75,050 | 287,950 (+290%) | 208,625 (+183%) |
   | Atlantic Av – Barclays Ctr | 42,711 | 59,350 | 161,700 (+279%) | 117,650 (+175%) |
   | Jackson Hts – Roosevelt Av | 52,296 | 41,200 | 210,900 (+303%) | 133,025 (+154%) |
   | **Ten stations** | 1,091,540 | 1,177,475 (+8%) | 2,088,375 (+91%) | 1,639,375 (+50%) |
   | All subway boardings | ≈5.7 M entries | – | 9.85 M | 6.51 M |

   Stations without large transfers (Times Square, Fulton St) end within 10%; the large overshoots are at transfer
   hubs, where this count includes transfers. Subway volume falls from ≈1.7× to ≈1.1–1.2× the entry count.
4. *Scoring.* In-vehicle time has zero marginal utility for car, taxi, FHV, ride and PT (only walk and bike have
   negative per-hour terms; PT has waiting −1.33/h and access/egress/transfer terms); time spent travelling costs
   only the forgone activity utility (performing 1.747/h). This follows the paper's normalisation (Section 4.1.1,
   Table 2: car travel time set to 0, other modes relative to it) and the PT constants match after the $2.75 fare
   (3.126 − 0.0622·2.75 = 2.955 vs 2.95). Differences from Table 2: taxi/FHV travel time (+1.75/h for `man` in the
   paper, 0 here), carpool travel time (+2.35 / +0.36 in the paper, 0 here), `nonman` cost coefficient (0 in the
   paper, 0.0544 here); none of them makes driving more attractive.

**Revised reading.** Transit is overloaded at the start (initial demand ≈2× real), so agents leave it, and by
iteration 99 subway volumes are roughly realistic. But the shift does not stop at transit: walk trips halve too,
and residents end with 58% car (`nonman`) and 55% car+taxi+FHV (`man`), far above NYC survey shares. With in-vehicle
time free for road modes and congestion felt only through lost activity time, road modes keep gaining as long as
innovation is on. The paper validated the base model with 50-iteration runs (and warm-started its policy runs from
that base for 100 iterations, which is the setting of option (a) in Section 4.1); our 100-iteration cold runs keep
drifting past that point. Candidate next steps: compare mode shares at iteration 49 with the paper's validation
period; check whether the paper's base used the same strategy weights and plan memory; treat the iteration count
of the base run as part of the calibration rather than as a free choice.

**Did the paper's model converge? Not shown (paper read 2026-10-08).** The paper describes MATSim generically as
iterating "until the agents' scores converge" (Section 2) and cites Djavadian and Chow (2017a) for stochastic user
equilibrium in sufficiently sampled agent-based models, but it reports no score-versus-iteration curve, no
convergence criterion and no iteration count for the base scenario. Its only stability evidence is a seed test
(Section 4.1.3, item 6): four baseline runs with a standard deviation of trips per mode of at most 3.6% of the mean,
which measures seed spread, not stability over iterations. Calibration used 50 iterations per SPSA step; the policy
runs started from "the final plan set obtained from the base MATSim-NYC scenario" and ran 100 iterations. Mode shares
were validated only for the synthetic population before simulation (against the 2017 Citywide Mobility Survey),
not after it. Our references still drift strongly at iteration 49, and our seed spread at iterations 90–99 (≈0.2%
of the mean for mode trips) is an order of magnitude below the paper's 3.6%, which would fit runs that were still
moving; the paper does not say which iteration its seed test used, so this is an inference, not a finding.

**Indicators** (produced online by `IterationMetrics` on perf, plus MATSim's own stats): mean executed score,
mode shares, car departures and completions, stuck agents, cordon entries, net charge revenue, transit waiting
time, bridge and tunnel counts.

**Tolerance.** For each indicator *x*, σ_x = standard deviation across the three reference seeds of the mean over
iterations 90–99; x̄ = mean across seeds over the same window.

**Steady state reached** at iteration T\* when every indicator stays within 2σ_x of x̄ for 5 consecutive
iterations. A run "matches the reference" if its last-10-iteration mean is within 2σ_x for every indicator.
These choices are fixed now and will not be tuned after seeing results. For other charge levels σ_x is taken from
τ = 1 and checked at one other level (Section 5.4).

**Labels.**

- **L-H, unresolved agent (hindsight).** Agent *i* is unresolved at iteration *t* if the plan selected at the end of
  the run was created after *t* (`Plan.getIterationCreated()`, MATSim 2026).
- **L-U, innovation uplift.** Innovation is randomized in the default setup, so for each agent and iteration the
  log records whether it innovated and what happened to the new plan. Outcome: the new plan is selected at least
  once in the next 10 iterations and its score exceeds the agent's best stored score by more than δ (δ from the
  noise floor, set in RQ0). Random assignment makes this an unbiased uplift label.
- **L-P, policy-affected agent.** For a policy change τ0 → τ1, agent *i* is affected if its selected plan at the
  end of the τ1 reference differs from its selected plan at the end of the τ0 reference in mode chain, cordon
  crossing, or departure time (15-minute bins). Variant L-P': its final τ1 plan was created after the policy
  switch in a warm-started run.
- **L-T, unstable trip.** A trip of a replanned plan is unstable if re-routing it with current travel times changes
  its route (road: link sequence; transit: lines and stops) or lowers the router's estimated cost by more than a
  threshold.
- **Plan change is not a label.** Up to 99% of choice changes return to a stored plan; they are SelectExpBeta
  re-evaluating plans, not evidence that an agent needs to innovate.

## 5. Main line: reuse across policies (Direction B)

### 5.1 Problem

Given the converged state S(τ0) (all agents' plan memories with scores) and a new charge level τ1, reach the
steady state of τ1 with as few iterations as possible, and choose which τ to run at all with as few runs as
possible. Today each τ is a cold 100-iteration run with 30% random innovation.

### 5.2 Who is affected

- **Direct:** any stored plan (or its car/taxi/FHV alternative) crosses a priced link in priced hours, or paid a
  charge in S(τ0). Computable from the plans and `scenarios/nyc-2025/links.csv` without simulation.
- **Indirect:** congestion or crowding on the agent's routes changes because others react. This is the ≈9% effect
  from Section 2 and is why a geometric rule alone is not expected to be enough.

Agents that are not targeted still select among their stored plans and are scored in the new state every
iteration, so their choices among known plans adapt. What they do not get is new plans.

### 5.3 Arms (warm-started runs are 40 iterations, innovation to 31)

| Arm | Start | Who innovates |
|---|---|---|
| B0 cold reference | cold | default (30% random), 100 iterations; ground truth and today's cost |
| B1 warm default | S(τ0) | default 30% random |
| B2 warm rule | S(τ0) | direct-affected set + ε random, same total budget cap |
| B3 warm learned | S(τ0) | model score on L-P (Section 5.2 features + one probe iteration) + ε random |
| B4 warm oracle | S(τ0) | L-P from B0 at the same τ1 (upper bound) |

Features for B3: everything in Section 6.2 plus policy-delta features — charge change × number of priced
crossings in stored plans, charge paid in S(τ0), score gap between the selected plan and the best stored
non-car plan, and experienced travel-time change in a single selection-only *probe iteration* under τ1.

### 5.4 Charge levels and adaptive sampling

τ0 = 1. Training levels τ1 ∈ {0.5, 0.75, 1.5, 2.0}; held-out levels {0.25, 1.25}. L3 showed a kink near zero,
so 0.25 is the hardest held-out case. Adaptive sampling: after each run, fit piecewise-linear and model-based
interpolations of each indicator over τ, and run next where they disagree most; stop when the leave-one-out
interpolation error is below 2% on all indicators. Report the number of runs needed vs a uniform grid.

### 5.5 Gate for the main line

B1 vs B0 shows how much a plain warm start already gives. B3 must reach the B0 steady state (within 2σ) at least
2× faster than B1 on held-out levels; otherwise the result is "warm start + rule (B2)", reported with B4 as the
ceiling.

## 6. Agent level within one run (method building block)

### 6.1 RQ2 arms (3 seeds × 100 iterations each)

| Arm | Who innovates each iteration (man/nonman) |
|---|---|
| A. Default (reuse RQ1 runs) | 30% at random (WeightedStrategyChooser) |
| B. Built-in, not learned | BalancedInnovationStrategyChooser (same expected share, fewer repeats) |
| C. Oracle, same budget | 30% budget: (1 − ε) to L-H-unresolved agents, ε = 0.1 at random |
| D. Oracle, budget = need | only L-H-unresolved agents (≤ 30%) plus ε random |
| E. Noisy oracle | as C, with labels flipped to 80% recall and TNR (cf. L2Seg Table 5) |

Arm C's labels come from the same seed's log run, so the oracle becomes approximate as soon as the run diverges;
it is a conservative oracle and reported as such.

**Gate:** best oracle reaches T\* ≥ 3× earlier than A and matches the reference → train a per-run model (RQ3);
otherwise the agent level is reported as an upper bound, and its features and chooser are used only in the
policy line (Section 5). The threshold is 3× because of the oracle-to-model loss (Section 3, item 3).

### 6.2 Features (end of iteration *t*, from W1 and online metrics)

Plan-memory size, spread of stored scores, age of selected plan, switches in the last 5 iterations, executed
minus best stored score, last-iteration travel-time change, mode chain, home and work zone, whether any plan
crosses the cordon, congestion on the links of the selected plan, crowding on its transit runs.

## 7. Trip level: stable trips as fixed segments (Direction A)

### 7.1 Analogy

A plan is a sequence of activities joined by trips, as a VRP route is a sequence of customers joined by edges.
FSTA keeps stable edges and re-optimizes only unstable ones; here a replanned plan keeps the routes of stable
trips and re-routes only unstable ones. This is the only level where the replanning problem itself gets smaller.

### 7.2 Variants

| Variant | Which trips are re-routed | Note |
|---|---|---|
| T0 default | all trips of the plan (ReRoute; SubtourModeChoice + ReRoute) | today |
| T1 changed subtour | for SubtourModeChoice, only trips of the subtour whose mode changed; ReRoute unchanged | rule, no learning |
| T2 predicted unstable | ReRoute and SubtourModeChoice re-route the changed subtour plus trips predicted unstable under L-T | learned |
| T3 policy-targeted | after τ0 → τ1, re-route only trips whose route or road alternative touches a priced link, plus T2 | feeds Section 5 |

T1 is not an exact speedup: trips outside the changed subtour lose a route refresh they would have received.
Its effect on convergence is measured, not assumed.

### 7.3 What survives of the FSTA theorem

With activity times and modes held fixed, re-routing any subset of trips yields a feasible plan, and each
re-routed trip gets the least-cost path under the same travel-time estimate, so the plan's *router-estimated*
cost cannot increase. The experienced score can, because of interaction. This is the trip-level analogue of
FSTA's feasibility and monotonicity, in the router's cost only.

### 7.4 Expected size of the gain

Replanning is ≈16 s of ≈118 s per iteration on the workstation and ≈27 s of ≈223 s on ORCD (Section 2), and
routing is a part of it (share to be profiled, W6). In a single run the ceiling is therefore about 10% of
iteration time during innovation, and nothing after the 80% switch-off. The larger value is in Section 5: under a new charge,
re-routing is how car users react, and T3 decides whom to re-route. It also matters at a cold start, where route
preparation took 151 s (perf, R4).

## 8. Research questions

| RQ | Question | Experiment | Decisive output | Depends on |
|---|---|---|---|---|
| RQ0 | When do runs reach steady state, how far apart are seeds? | 3 × 100-iteration references (running on ORCD, but as the no-charge baseline, Section 4.1) | T\*, σ_x; bridge/tunnel counts within 5% or not | — |
| RQ1 | How stable is each agent, is it predictable? | 3 log-enabled default runs (W1); stability curve (analogue of L2Seg Fig. 1); classifiers on L-H, L-U | unresolved share per iteration; AUC; recall at 30% budget | RQ0, W1 |
| RQ2 | Ceiling of agent-level targeting in one run | Section 6.1 | T\* per arm; gate | RQ1 |
| RQ3 | Can a model replace the oracle in one run? | model on L-U/L-H, train seeds 4711/4712, test 4713 | recall, TNR, T\* vs oracle | RQ2 gate |
| RQ4 | Does targeting change the final state? | 50-iteration schedule (innovation to 39) with the model vs the reference; ε ∈ {0.05, 0.2} | all indicators within 2σ_x | RQ3 |
| **RQ5** | **Can unaffected agents be reused across policies?** | Section 5.3–5.4 | iterations per policy (B1–B4 vs B0); runs needed for 2% interpolation error | RQ0, W5, W7 |
| RQ6 | Does trip-level aggregation shrink replanning without hurting convergence? | T1, T2 (3 seeds × 100 iterations); T3 inside RQ5 | replanning time per iteration, routed trips, T\*, final-state match | RQ1, W6 |

## 9. Engineering work (on this branch, before any run)

`main` does not contain the perf work, so W0 brings over only what this plan needs.

| ID | Work | Files | Acceptance |
|---|---|---|---|
| W0 | Port from perf: `IterationMetrics` (E1), E2 pricing lookups and the pricing-scale lever, the `nyc.onlineMetrics` switch in `RunNyc`, `experiments/reference/` and the `pilot.py` helpers it imports | `IterationMetrics.java`, `Pricing2025.java`, `RunNyc.java`, `experiments/reference/*` | `run_reference.py verify` on a 12-iteration seed-4711 run matches `expected-seed4711-12it.json` |
| W1 | Compact replanning log per iteration and resident agent: person index, strategy chosen, selected plan id, its iterationCreated, executed score, best stored score, number of stored plans; plus per re-routed trip: route changed or not, estimated cost before/after. `planInheritance` on for plan ids | new `ReplanningLog.java` | ≤ 10 MB/iteration; logging on vs off gives identical indicators over 12 iterations |
| W2 | Recording chooser delegating to the default WeightedStrategyChooser | `RecordingStrategyChooser.java` | same RNG draws as the default |
| W3 | Targeted chooser: in `beforeReplanning`, rank agents per subpopulation by priority (file or model), mark the top (1 − ε)·B plus ε·B random, B = innovation weight share × subpopulation size; marked agents choose among innovation strategies in configured proportions, others among selectors; reads the actual weights, so innovation still stops at 80% | `TargetedInnovationChooser.java` | realised share = B ± 1 agent; with ε = 1 the decision distribution equals the default |
| W4 | Analysis: stability curves, labels L-H/L-U/L-P/L-T, T\*, tolerance table, features | `experiments/l2seg/` | tests on a synthetic log |
| W5 | Warm start: start a run from another run's output plans with all stored plans and scores, at a new τ | runner option | with τ unchanged and innovation off, indicators stay within 2σ |
| W6 | Partial re-routing: a re-route module that takes the set of trips to route (changed subtour, model, priced-link rule) and keeps the others; profile routing share of replanning | `PartialReRoute.java`, strategy bindings for T1–T3 | with "route all trips" it reproduces `ReRoute` exactly over 12 iterations |
| W7 | Policy features and probe iteration: direct-affected rule from plans and priced links; one selection-only iteration under τ1 | `experiments/l2seg/policy_features.py`, runner option | rule matches a brute-force scan of plans on a sample |

Checks: confirm in the MATSim 2026 source that `chooseStrategy` is called sequentially per person
(`GenericStrategyManagerImpl`) before relying on unsynchronised state in W3; the `outside` subpopulation is never
targeted; W6 must leave access/egress legs of re-routed trips consistent.

### 9.1 Status and acceptance (2026-10-07)

All 12-iteration checks: seed 4711, launch-2025, historical innovation schedule (iterations 0–8), ORCD
`mit_normal`, 16 threads. "Identical" means `run_reference.py verify`: all 12 `iteration-metrics-N.json` and
average executed scores equal `expected-seed4711-12it.json`.

| Item | Result | Evidence |
|---|---|---|
| W0 | **Accepted.** Identical; wall 2,347 s, peak RSS 17.5 GB. The perf code itself (75abcdd) is also identical on ORCD (job 25110162, 2,919 s on another node: node speed varies by ≈20%) | job 25171033, commit 03004ff |
| W1 | **Accepted.** Log on: identical; wall 2,161 s, peak RSS 17.6 GB. Size 6.6–10.9 MB per iteration with double-precision scores (over the 10 MB target in innovation iterations 2–8); scores are now written at float precision (d4c8e0e), which re-encoding the run's files puts at ≈8 MB per innovation iteration (not re-run) | job 25171696, commit 29d6683 |
| W2 | **Accepted** (synthetic): same decisions and same `MatsimRandom` stream as `WeightedStrategyChooser` over 5 iterations × 1,200 agents | `scripts/VerifyReplanningChoosers.java` |
| W3 | **Accepted** (synthetic): exactly B = round(0.3 N) innovators (270 by priority + 30 random at ε = 0.1); `outside` never innovates; B = 0 when innovation weights are 0; at ε = 1 strategy shares within 0.005 of the default over 400 iterations and per-agent innovation rates 0.225–0.370 around 0.3 | same |
| W4 | **Implemented**, synthetic tests pass (`experiments/l2seg/test_l2seg.py`); runs on the real W1 log in 19 s / 0.5 GB | `experiments/l2seg/` |
| Detailed recorder (ResearchMetrics, ported from `research/reference-instrumentation`) | **Accepted.** Off/on pair with identical settings (heap 24 GB, events and plans every 10 iterations): both identical to the expected values, so the recorder leaves all indicators unchanged. Audit passed: full person coverage every iteration, every partition sums to the total, link-hour completions ≤ entries with nonnegative times, events/plans/counts files exactly where the parsed config puts them, deferred output initialization, config check by MATSim. Cost below | jobs 25172621 (off) / 25172622 (on), commit cb981aa; `research-audit.json` |

**Recorder cost (12 iterations; the two jobs ran on different nodes, which differ by up to ≈20%).** Mean iteration
170 s off vs 230 s on (+35%): mobsim +39 s (per-event handling on the events thread, mixed with node speed),
before-mobsim +8 s (plan fingerprints), iteration end +11 s (writing); the recorder's own timers give 19 s per
iteration for fingerprints and writing. Peak RSS unchanged (25.6 vs 25.5 GB; the 24 GB heap dominates). Disk per
iteration: persons 53 MB, link-hours 23 MB, groups < 0.01 MB, i.e. ≈75 MB per iteration; events 1.1 GB and plans
0.43 GB (+ experienced plans 0.28 GB) per snapshot.

**Where an iteration's time goes (RQ0 seed 4711, iterations 40–65, 16 cores, recorder and JFR on).** Mobsim
245 s (78%) using **3.8 of 16 cores**, replanning 35 s (11%) using 13.9 cores, before-mobsim 14 s, after-mobsim to
iteration end 19 s, GC pauses 1.5% of wall; over the whole run the process averages ≈5 cores. Events are handled
on one thread (`SimStepParallelEventsManagerImpl`, threads = 1), QSim synchronises with it every simulated second,
and the slowest simulated hours are the peaks (7–9 h and 15–17 h: 17–22 s of wall time per simulated hour). This
**overturns** the statement in Section 1 that exact engineering has brought the cost per iteration close to its
floor: most cores are idle during mobsim.

**More event threads (12-iteration checks, `--events-threads`).** With `eventsManager.numberOfThreads` = 4 and 8
the run stays **identical** to the expected values (jobs 25181738 and 25181739), but mobsim barely gets faster:

| Events threads | Node | Mobsim, iterations 1–9 | Cores during mobsim | Wall |
|---:|---|---:|---:|---:|
| 1 (W0, job 25171033) | node3105 | 133.6 s | — | 2,347 s |
| 1 (recorder off, job 25172621) | node3104 | 122.1 s | 4.6 | 2,242 s |
| 4 (job 25181738) | node1602 | 123.7 s | 6.2 | 2,128 s |
| 8 (job 25181739) | node3108 | 115.7 s | 8.1 | 2,008 s |

CPU use rises with the thread count, time falls by at most 5–13%, inside the ≈20% spread between nodes. The
limit is therefore not the number of event threads: a single heavy handler (each handler runs on one thread) or
QSim's per-second synchronisation remains. The JFR profiles of the RQ0 runs (written when they end) are the next
step to name it. The option stays available; it is safe but not worth relying on for speed.

**JFR of RQ0 seed 4711 (whole run, 3.06 M execution samples).** QSim network threads 39% of samples, the single
events thread 35%, routing during replanning 18%, main thread 6%. The events-thread share means it is busy for
roughly 70% of the run's wall time, i.e. most of mobsim: it is the critical path. Inside it: **ResearchMetrics
26%**, travel-time collection (`TravelTimeCalculator`) 17%, dispatch and queueing 16%, scoring 8%,
`VolumesAnalyzer` 7%, **road pricing with the all-zero control toll file 8%** (`RoadPricingTollCalculator` +
`CalcAverageTolledTripLength`), `EventsToLegs` 3%; the top frames are hash-map lookups. In QSim threads and the
router, time-variant link attributes (archive capacity factors) cost 15% and 36% respectively, mostly binary
searches. Exact speed-ups to test, in order: (1) a cheaper ResearchMetrics (index arrays instead of hash maps and
link-id strings per event) or leaving it off for runs that only need indicators; (2) not installing road pricing
when the toll file has no positive toll (baseline only); (3) caching time-variant capacities per time bin. Each
is checked with the 12-iteration identity test.

**Resources for 100-iteration runs with the recorder** (events and plans every 10 iterations): ≈7.5 GB records +
≈12 GB events (iterations 0, 10, …, 90, 99) + ≈7 GB plans ≈ **27–30 GB per run**, so outputs belong on scratch,
not home (200 GB quota). Wall time: if the +35% holds, a run that takes 7–9 h without the recorder takes 9.5–12 h,
at the 12 h `mit_normal` limit. The RQ0 references record with ResearchMetrics and JFR, so their final wall time is
the direct measurement; until then request `--mem=32G`, heap 24 GB, `--time=12:00:00`, and treat the recorder as
optional for runs that only need indicators. A cheaper recorder (index-based keys instead of link-id strings in
the per-event hashes) is the first thing to try if the limit is hit.

MATSim 2026.0 source checks: `chooseStrategy` is called sequentially per person in `GenericStrategyManagerImpl.run`
(lines 223–247), with `beforeReplanning` once per iteration, so W3's unsynchronised state is safe. Plan
inheritance is **off** by default and `Plan.getIterationCreated()` throws a `NullPointerException` for plans that
never had it set; the log enables inheritance and reads the attribute defensively. A strategy's selector first
picks any unscored plan (`RandomUnscoredPlanSelector`), so "selector" strategies can also switch plans. Plans are
dumped only at `it % N == 0` (and up to `writePlansUntilIteration` = 1), not in the last iteration; the final state
is `output_plans`. Events are also written in the last iteration.

First look at the stability curve (W1 log, 12 iterations, so not a result): exactly 30.0% of `man`/`nonman`
innovate per iteration; the share whose final plan is newer than t (L-H) falls linearly from 65% at t = 0 to 0 at
t = 8 (35% end on their initial plan); the selected plan changes for 30–59% per iteration during innovation and still
for 35–44% afterwards, all of it revisits of stored plans. This is higher than perf's 10–25% choice changes because
any change of the selected plan counts here, including plans that differ only in timing.

## 10. Compute

One full run: 16 cores, 24 GB, one ORCD `mit_normal` job (12 h limit). **Revised 2026-10-07:** the earlier
3.5–5 h estimate came from workstation speed; on ORCD a launch-2025 iteration takes ≈223 s at the start of a run
and the baseline references are at 270–340 s per iteration by iteration 40 because mobsim grows, so a
100-iteration run takes **≈7–9 h** (to be replaced by the measured wall time when RQ0 ends). A 40-iteration warm
run counts as 0.4 of a full run.

| Stage | Runs | Full-run equivalents |
|---|---|---|
| RQ0 references (running on perf) | 3 | 3 |
| RQ1 log-enabled default runs | 3 | 3 |
| RQ2 arms B–E | 12 | 12 |
| RQ3 model + ε variant | 6 | 6 |
| RQ4 50-iteration runs | 6 | 3 |
| RQ5 B0 cold references at 6 levels (+2 seeds at τ = 0.5 for σ) | 8 | 8 |
| RQ5 B1–B4 warm runs at 6 levels | 24 | 9.6 |
| RQ5 adaptive-sampling extra levels | ≈4 | ≈1.6 |
| RQ6 T1, T2 | 6 | 6 |
| **Total** | **≈72** | **≈52, i.e. ≈360–470 run-hours, ≈5,800–7,500 core-hours on ORCD** (revised from 180–260 run-hours / 2,900–4,200 core-hours, which assumed workstation speed) |

RQ1 runs repeat the RQ0 seeds with logging on; if W1 is passive their indicators equal RQ0's, which doubles as a
determinism check on ORCD. Runs within a stage are independent and go into one Slurm array.

## 11. Timeline (14 weeks from 2026-10-07)

| Weeks | Dates | Work | Exit |
|---|---|---|---|
| 1–2 | 10/07–10/20 | W0–W3, W5, unit tests, 12-iteration passive-log check locally | RQ0 finished; tolerance table |
| 3–4 | 10/21–11/03 | RQ1 runs; RQ5 B0 cold references at all levels; W4, W7 | stability curve, AUC; ground truth per τ |
| 5–6 | 11/04–11/17 | RQ2 arms; RQ5 B1, B2, B4 | agent-level gate; warm-start baseline |
| 7–9 | 11/18–12/08 | models (agent and policy, shared features); RQ5 B3; W6 | main-line gate (Section 5.5) |
| 10–11 | 12/09–12/22 | RQ3/RQ4 if the agent gate passed; RQ6 | final-state match; trip-level cost |
| 12–14 | 12/23–01/12 | adaptive sampling, write-up | policy-study cost table |

## 12. Risks

- **Warm start already does most of the work.** If B1 is close to B4, targeting adds little; the result is then
  the cost of a warm-started policy study and the B4 ceiling.
- **Indirect effects dominate.** If many affected agents are not directly priced, the rule (B2) fails and the probe
  iteration carries the model; if the probe is not informative either, report the recall ceiling.
- **Small oracle gain within one run.** Up to 99% of late choice changes are revisits; late iterations may settle
  anyway. RQ2 measures this before any per-run model exists.
- **Changed final state.** Fewer innovators may under-explore; RQ4 and RQ5 test against seed spread; ε keeps a
  random share.
- **Trip-level gain too small to see.** If routing is a small part of 16 s, RQ6 reports the measured ceiling and T3
  is kept only for its role in Section 5.
- **Labels are run-specific.** Train and test on different seeds (agent level) and different τ (policy level).
- **Reference not settled by iteration 80, or counts outside 5%.** Then schedule or calibration comes first (perf
  `docs/server-runbook.md`: SPSA, 6 steps × 2 runs × 50 iterations) and the timeline shifts.
- **Iteration cost not constant.** Mobsim grows during a run (74 → 108 s), and targeting may change that. Report
  wall time next to iteration counts.

## 13. Open questions for discussion

1. Is the policy line with the trip level as the FSTA-like component the right framing, or should the paper
   lead with the single-run agent level?
2. Per-agent model or graph model over agents sharing links and transit runs? Current preference: per-agent with
   aggregated congestion and crowding features; a graph model only if recall stays near 70%, where L2Seg's Table 5
   shows the steepest loss. Indirect policy effects (Section 5.2) are the most likely reason to need it.
3. Is L-U (uplift from the randomized default) acceptable as the primary within-run label, and L-P from cold
   references as the policy label, instead of a look-ahead label?
4. Which charge levels matter for the application, so that held-out levels reflect real use?

# Plan: learning which agents to replan in MATSim-NYC (an L2Seg analogue)

Branch `research/l2seg-replanning`, started from `main` on 2026-10-07. **Nothing in this document has been run yet.**
It is the working plan; results will be added in place as each stage finishes.

Evidence cited below comes from branch `perf/simulation-redundancy` (head `75abcdd`), referred to as *perf*.
The method being adapted is Ouyang, Li, Ma, Wu, *Learning to Segment for Vehicle Routing Problems*,
arXiv:2507.01037v2 (2025), referred to as *L2Seg*.

## 1. Claim in one paragraph

A policy study costs *runs × iterations per run × cost per iteration*. Exact engineering has brought the last
factor close to its floor, and replacing the traffic simulation by an approximation (PSim) is biased because
agents interact through congestion and transit crowding. We therefore leave the simulation exact and change
**who innovates**: today about 30% of resident agents, chosen at random, innovate each iteration; we propose to
spend that budget on the agents predicted to still be unresolved, and to reuse resolved agents across policy
scenarios. The saving comes **only from needing fewer iterations and fewer runs**; an iteration costs the same.
This is the main difference from L2Seg, whose gain comes from each search step operating on a smaller,
aggregated problem (Section 3).

Targets, not results: 2–4× fewer iterations per run, and 2–3× fewer policy runs through adaptive sampling.
How these combine with warm starts is itself a measurement (RQ5); we do not multiply them in advance.

## 2. What is already known (perf branch)

| Item | Result | Source on perf |
|---|---|---|
| Iteration cost | ≈118 s (replanning ≈15, mobsim ≈88.6, scoring/stats ≈14.1) on 16 threads, 389,301 persons + ≈51,000 transit drivers | 12-iteration seed-4711 run; **breakdown to be recomputed** from `stopwatch.csv` of the reference runs |
| Mobsim growth | 74 → 108 s per iteration within a run | `experiments/redundancy/README.md` |
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
`fractionOfIterationsToDisableInnovation = 0.8`. **Innovation stops at 80% of the run**, so focused innovation
can only save iterations in that first 80%. Shortening a run moves the switch-off point with it.

## 3. Mapping to L2Seg, and what does not transfer

| L2Seg (VRP) | MATSim-NYC |
|---|---|
| Solution: set of routes | the selected plan of each of the 389,301 agents |
| Stable edge: unchanged over the next *k* search steps (labels use *k* = 1, App. A.1) | agent whose final plan already exists in its plan memory (Section 4) |
| Search step (LKH-3, LNS) | replanning: innovation (time, route, mode) plus selection among stored plans |
| No decomposition: every edge may be re-optimized | every agent may innovate |
| Random FSTA (40%/60% of edges marked unstable, Table 3) is **worse than no decomposition** | **today's default**: 30% random innovators per iteration |
| FSTA: re-optimize only unstable parts | innovate only predicted-unresolved agents, others only select |
| Labels: one-step look-ahead with the backbone solver | look-ahead is not possible after trajectories diverge; see labels L-H and L-U (Section 4) |
| NAR (global, one shot) and AR (local, sequential) decoders | per-agent classifier first; graph model over agents sharing links or transit runs only if needed |
| Metric: objective vs wall time | distance to the reference steady state vs iterations |

What does not transfer:

1. **The mechanism of the speedup.** FSTA aggregates stable segments into hypernodes, so each search step solves
   a smaller problem (L2Seg, Section 3.2, Fig. 5 plots objective against wall time). Here every agent is still
   simulated every iteration, and replanning is ≈15 of ≈118 s. Iteration cost stays the same, so only the
   iteration count can fall.
2. **The guarantee.** FSTA's feasibility and monotonicity theorem relies on route costs being additive over
   edges, so fixed segments do not affect the rest. Agents frozen in MATSim still occupy roads and vehicles; this
   is why freezing them in the simulation (L2) was biased. We therefore segment *replanning*, never *simulation*.
3. **Oracle → model loss.** L2Seg's Table 5 (CVRP2k, time to reach the learned model's quality) shows how much the
   gain depends on classifier quality: perfect oracle 39 s, 95% recall/TNR 62 s, 90% 119 s, 70% 324 s, learned
   L2Seg-SYN 241 s. Expect a learned predictor to keep a fraction of the oracle's gain. The go/no-go threshold
   in RQ2 is set with this in mind.
4. **Drift of the unstable set.** L2Seg App. E.6: overlap of predicted unstable edges between adjacent steps
   rises only from 28% to 54%. A fixed or slowly updated target set would stall exploration, so the chooser keeps
   a random share ε of the budget (Section 6, W3) and re-predicts every iteration.

## 4. Definitions

**Run schedule.** Unless stated otherwise: 100 iterations (0–99), innovation until iteration 79, seed
4711/4712/4713, launch-2025 configuration with `assumptions/archive-capacity-factors.csv`, as in
`experiments/reference/run_reference.py` on perf.

**Indicators** (all already produced online by `IterationMetrics` on perf, plus MATSim's own stats): mean executed
score, mode shares, car departures and completions, stuck agents, cordon entries, net charge revenue, transit
waiting time, bridge and tunnel counts.

**Tolerance.** For each indicator *x*, the seed spread σ_x = standard deviation across the three reference seeds of
the mean over iterations 90–99. Reference value x̄ = mean across seeds over the same window.

**Steady state reached** at iteration T\* when every indicator stays within 2σ_x of x̄ for 5 consecutive
iterations. A run "matches the reference" if its iteration-90–99 mean is within 2σ_x for every indicator.
(The 2σ and 5-iteration choices are fixed now and will not be tuned after seeing results.)

**Labels for "unresolved agent at iteration t".**

- **L-H, hindsight.** Agent *i* is unresolved at *t* if the plan it has selected at iteration 99 was created after *t*
  (`Plan.getIterationCreated()`, MATSim 2026). That is, the agent still has to discover its final plan. Cheap,
  computed from a single logged run, but tied to that run's trajectory.
- **L-U, uplift.** Innovation is randomized in the default setup, so for each agent and iteration the log tells
  whether it innovated and what happened to the new plan. Define the outcome as "the innovated plan is
  selected at least once in the following 10 iterations and its score exceeds the agent's best stored score by
  more than δ" (δ = noise floor, to be set from RQ0). Because assignment is random, a model trained on agents
  that innovated estimates the benefit of innovating for every agent without bias (an uplift model).
- **Plan change is not a label.** Up to 99% of choice changes return to a stored plan; they are SelectExpBeta
  re-evaluating plans, not evidence that an agent needs to innovate.

## 5. Research questions

| RQ | Question | Experiment | Decisive output | Depends on |
|---|---|---|---|---|
| RQ0 | When do runs reach steady state, and how far apart are seeds? | 3 × 100-iteration reference runs (perf, running on ORCD) | T\*, σ_x per indicator; bridge/tunnel counts within 5% or not | — |
| RQ1 | How stable is each agent, and is it predictable? | 3 log-enabled default runs (W1); stability curve (share unresolved under L-H by iteration, analogue of L2Seg Fig. 1); simple classifiers on L-H and L-U | unresolved share per iteration; AUC; recall at the 30% budget | RQ0 tolerance, W1 |
| RQ2 | If we knew who is unresolved, how much faster is steady state? | arms in Section 5.1, 3 seeds each | T\* per arm; final-state match | RQ0, RQ1 |
| RQ3 | Can a model replace the oracle? | gradient-boosted model on L-U (and L-H), train seeds 4711/4712, test 4713; run with the model in the chooser | recall, TNR, T\* relative to the RQ2 oracle | RQ1, RQ2 gate |
| RQ4 | Does focused innovation change the final state? | shortened schedule (50 iterations, innovation to 39) with the model vs the 100-iteration reference, 3 seeds; ε ∈ {0.05, 0.2} | every indicator within 2σ_x | RQ3 |
| RQ5 | Can resolved agents be reused across policies? | warm start from the baseline run's final plan memories at new charge levels; innovate only agents the model flags; adaptive choice of charge levels (L3 kink) | iterations per policy; policy runs needed for a given L3 interpolation error | RQ3, L3 |

### 5.1 RQ2 arms (each 3 seeds × 100 iterations)

| Arm | Who innovates each iteration (man/nonman) |
|---|---|
| A. Default (reuse RQ1 runs) | 30% at random (WeightedStrategyChooser) |
| B. Built-in, not learned | BalancedInnovationStrategyChooser (same expected share, fewer repeats) |
| C. Oracle, same budget | 30% budget: (1 − ε) to L-H-unresolved agents, ε = 0.1 at random |
| D. Oracle, budget = need | only L-H-unresolved agents (≤ 30%) plus ε random |
| E. Noisy oracle | as C, with labels flipped to 80% recall and TNR (sensitivity, cf. L2Seg Table 5) |

Arm C's labels come from the same seed's log run, so the oracle becomes approximate as soon as the run diverges.
That makes it a conservative oracle; we report it as such.

### 5.2 Gate after RQ2

- Oracle (best of C, D) reaches T\* ≥ 3× earlier than A and matches the reference → build the model (RQ3).
- 1.5–3× → skip a dedicated per-run model; go to RQ5, where most agents are unaffected by a policy change and
  the signal is stronger.
- < 1.5× → stop; report the upper bound and the R3 revisit finding as the result.

The threshold is 3× rather than 2× because of the oracle-to-model loss in Section 3, item 3.

## 6. Engineering work (to do on this branch, before any run)

`main` does not contain the perf work, so W0 brings over only what this plan needs.

| ID | Work | Files | Acceptance |
|---|---|---|---|
| W0 | Port from perf: `IterationMetrics` (E1), E2 pricing lookups, the `nyc.onlineMetrics` switch in `RunNyc`, `experiments/reference/` (runner, sbatch, expected values, userspace setup), `experiments/acceleration/pilot.py` helpers it imports | `src/main/java/.../IterationMetrics.java`, `Pricing2025.java`, `RunNyc.java`, `experiments/reference/*` | `run_reference.py verify` on a 12-iteration seed-4711 run matches `expected-seed4711-12it.json` |
| W1 | Compact replanning log: per iteration and resident agent, `person index, strategy chosen (select / TAM / ReRoute / SMC), selected plan id, its iterationCreated, executed score, best stored score, number of stored plans`. Enable `planInheritance` for plan ids and lineage | new `ReplanningLog.java` (controller listener + chooser hook) | ≈ 389k rows/iteration, binary or gzip CSV, target ≤ 10 MB/iteration; logging on vs off gives identical indicators over 12 iterations (it must be passive) |
| W2 | Recording chooser: delegates to the default WeightedStrategyChooser and records the decision for W1 | `RecordingStrategyChooser.java` | same RNG draws as the default, so the W1 identity test holds |
| W3 | Targeted chooser: in `beforeReplanning`, rank agents of each subpopulation by a priority file or model score, mark the top (1 − ε)·B plus ε·B random, where B = innovation weight share × subpopulation size; marked agents choose among innovation strategies in their configured proportions, others among selectors. Reads the actual weights passed in, so innovation still switches off at 80% | `TargetedInnovationChooser.java`, priority input = per-iteration file (oracle) or model scores (RQ3) | unit test: realised share = B ± 1 agent; with ε = 1 the decision distribution equals the default |
| W4 | Analysis: stability curves, L-H and L-U labels, T\*, tolerance table, features | `experiments/l2seg/` (Python) | tests on a synthetic log |
| W5 | Warm start for RQ5: start a policy run from another run's output plans with all stored plans and scores | config + runner option | runs 1 iteration with no new innovation when the policy is unchanged |

Checks for W3: confirm in the MATSim 2026 source that `chooseStrategy` is called sequentially per person
(`GenericStrategyManagerImpl`) before relying on unsynchronised state; the `outside` subpopulation is never
targeted.

Features for RQ3 (all computable from W1 and existing online metrics at the end of iteration *t*): plan-memory
size, spread of stored scores, age of selected plan, switches in the last 5 iterations, executed minus best
stored score, last-iteration travel-time change, mode chain, home and work zone, whether any plan crosses the
cordon, congestion on the links of the selected plan, crowding on its transit runs.

## 7. Compute

One run: 16 cores, 24 GB, 3.5–5 h (estimate until RQ0 finishes), one ORCD `mit_normal` job.

| Stage | Runs |
|---|---|
| RQ0 reference (running on perf) | 3 |
| RQ1 log-enabled default runs | 3 |
| RQ2 arms B–E | 12 |
| RQ3 model runs (and one ε variant) | 12 |
| RQ4 shortened-schedule runs | 6 |
| RQ5 policy runs | ≈15 |
| **Total** | **≈51 runs, 180–255 run-hours, 2,900–4,100 core-hours** |

RQ1 runs repeat the RQ0 seeds with logging on; if W1 is passive their indicators equal RQ0's, which doubles as a
determinism check on ORCD. Runs within a stage are independent and go into one Slurm array.

## 8. Timeline (14 weeks from 2026-10-07)

| Weeks | Dates | Work | Exit |
|---|---|---|---|
| 1–2 | 10/07–10/20 | W0–W3, unit tests, 12-iteration passive-log check locally | RQ0 runs finished; tolerance table |
| 3–4 | 10/21–11/03 | RQ1 runs and analysis (W4) | stability curve, AUC |
| 5–6 | 11/04–11/17 | RQ2 arms | **gate** (Section 5.2) |
| 7–9 | 11/18–12/08 | RQ3 model, runs | recall/TNR, T\* vs oracle |
| 10–11 | 12/09–12/22 | RQ4 | final-state match |
| 12–14 | 12/23–01/12 | RQ5, write-up | policy-study cost table |

## 9. Risks

- **Small oracle gain.** With up to 99% of late choice changes being revisits, late iterations may settle anyway.
  RQ2 measures this before any model exists.
- **Changed final state.** Fewer innovators may under-explore (premature convergence in VRP terms). RQ4 tests
  against seed spread; ε keeps a random share.
- **Labels are run-specific.** An agent unresolved in one seed may not be in another. Train and test on different
  seeds, as in L1. L-U is less run-specific than L-H because it is a property of the agent and its context.
- **Reference not settled by iteration 80, or counts outside 5%.** Then the schedule or calibration comes first
  (perf `docs/server-runbook.md`: SPSA, 6 steps × 2 runs × 50 iterations) and the timeline shifts.
- **Iteration cost not constant.** Mobsim grows during a run (74 → 108 s), and focused innovation may change that.
  Report wall time next to iteration counts.

## 10. Open questions for discussion

1. Is focused replanning a sufficient contribution, or should RQ5 (reuse across policies) be the main line with
   RQ2–RQ4 as method? Current preference: RQ5 as the main line, because within a single run the saving is capped by
   the 80% innovation window, and under a policy change most agents are unaffected.
2. Per-agent model or graph model over agents sharing links and transit runs? Current preference: per-agent with
   aggregated congestion and crowding features; move to a graph model only if recall stays near 70%, where L2Seg's
   Table 5 shows the steepest loss.
3. Is L-U (uplift from the randomized default) acceptable as the primary label instead of a look-ahead label?

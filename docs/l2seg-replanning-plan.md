# Plan: learning which agents and trips to replan in MATSim-NYC (an L2Seg analogue)

Branch `research/l2seg-replanning`, started from `main` on 2026-10-07. **Nothing in this document has been run yet.**
It is the working plan; results will be added in place as each stage finishes.

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
| Iteration cost | ≈118 s (replanning ≈15, mobsim ≈88.6, scoring/stats ≈14.1) on 16 threads, 389,301 persons + ≈51,000 transit drivers | 12-iteration seed-4711 run; **breakdown to be recomputed** from `stopwatch.csv` of the reference runs |
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
   ≈16 of ≈118 s.
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

Replanning is ≈16 s of ≈118 s per iteration and routing is a part of it (share to be profiled, W6). In a single
run the ceiling is therefore about 10% of iteration time. The larger value is in Section 5: under a new charge,
re-routing is how car users react, and T3 decides whom to re-route. It also matters at a cold start, where route
preparation took 151 s (perf, R4).

## 8. Research questions

| RQ | Question | Experiment | Decisive output | Depends on |
|---|---|---|---|---|
| RQ0 | When do runs reach steady state, how far apart are seeds? | 3 × 100-iteration references (perf, running on ORCD) | T\*, σ_x; bridge/tunnel counts within 5% or not | — |
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

## 10. Compute

One full run: 16 cores, 24 GB, 3.5–5 h (estimate until RQ0 finishes), one ORCD `mit_normal` job. A 40-iteration
warm run counts as 0.4 of a full run.

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
| **Total** | **≈72** | **≈52, i.e. 180–260 run-hours, 2,900–4,200 core-hours** |

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

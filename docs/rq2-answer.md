# RQ2. Which conclusions must stay unchanged after acceleration?

**Answer.** What must stay unchanged is the change a policy causes, not absolute levels, because MATSim studies draw their conclusions as comparisons within the model. For MATSim-NYC these are nine checks:
- how many fewer car trips the charging-related population makes;
- how much the car share falls;
- how much the transit share rises;

each under $9.18 and under $14, plus how much stronger $14 is than $9.18 on each. Every check has an interval set in advance from three seeds of the original procedure. Revenue, welfare by group and the share of people made worse off are reported but not required, because they are not stable in the original runs. Each scenario's absolute values only need to stay within loose sanity bounds of the original (e.g., car and transit shares within 2 pp), because the original's end state is a convention, not a converged state. Earlier MATSim acceleration papers checked levels such as the mean score, mode shares or counts, mostly on one seed and often at the iteration where the original's mean score is first reached, without a threshold set in advance (Section 3); our checks are on policy effects, after innovation stops, with three seeds and pre-set intervals.

## 1. What MATSim policy studies conclude

| Paper | City · policy | Main conclusions | Form | Seeds · iterations |
|---|---|---|---|---|
| [He et al. 2021](https://arxiv.org/abs/2008.04762) | New York · cordon pricing, $9.18 vs $14 peak | 127K fewer car trips/day; both groups gain; $14 worse than $9.18 citywide | Absolute, difference, group, ranking | Baseline 4 runs (SD ≤ 3.6%), policies not reported · 100 from baseline plans |
| [Meyer de Freitas et al. 2016](https://www.strc.ch/2016/MeyerDeFreitas_EtAl.pdf) | Zurich · cordon pricing | Peak VKT −24%; middle-income outsiders lose most | Difference, group | 1 · until stable |
| [Grether et al. 2008](https://doi.org/10.14279/depositonce-10358) | Zurich · afternoon-only toll | Afternoon toll also shifts morning trips | Direction, difference | 1 · 500 + 300, branched from one state |
| [Kaddoura & Nagel 2018](https://svn.vsp.tu-berlin.de/repos/public-svn/publications/vspwp/2017/17-14/KaddouraNagel2017congestionPricing.pdf) | Berlin · congestion pricing rules | Simple rule (LP) beats QCP variants | Ranking, difference | Not reported · 400 + 100 |
| [Kaddoura & Nagel 2016](https://doi.org/10.1016/j.procs.2016.04.184) | Berlin · individual value of time | Welfare +27%; result depends on iteration count | Ranking, difference | Not reported · 80 + 20 (500) |
| [Kickhöfer & Kern 2015](https://doi.org/10.1016/j.trd.2015.04.019) | Munich · emission/exposure pricing, Zone 30 | Rankings of measures; effects < 0.5% | Ranking, group | 1, 1% sample · 500 |
| [Hörl et al. 2021](https://doi.org/10.1016/j.trc.2021.102974) | Zurich · automated taxis | Demand peaks at ~4,000 vehicles; mileage +85–100% | Absolute, shape, direction | **5 seeds** · convergence criterion (~200) |

## 2. What the seven have in common

| Observation | Evidence |
|---|---|
| Conclusions are changes, not levels | Difference from baseline 7/7; ranking 5/7; group direction 4/7; absolute headline 2/7, and those compared with outside figures |
| Uncertainty is rarely reported | Multiple seeds only in Hörl; He gives baseline spread only |
| Many conclusions rest on small differences | He's "$14 too high": $0.11 (≈1%); Meyer de Freitas groups: 0.1–0.3%; Kickhöfer: −0.5% to +0.1% |
| Iteration budgets are conventions | 100, 500, 400 + 100, judged by eye; Kaddoura 2016: budget changes how methods compare |
| Calibration is separate | Calibrated models still miss counts by tens of percent; conclusions are comparisons within the model |

## 3. How MATSim acceleration papers check that results are unchanged

The policy studies above say which conclusions matter. The papers that accelerate MATSim are the other half: what they compare to show that a faster run gives the same result. Reading notes in [literature/](literature/README.md).

| Paper | How it accelerates | Reference | When compared | What is compared (numbers from the paper) | Seeds | Not checked |
|---|---|---|---|---|---|---|
| [Fourie et al. 2013](https://doi.org/10.3141/2343-09) (PSim), Zurich, 67k agents | Cheap pseudo-simulation between real ones | Original, 101 iterations; mean executed score 175.4 at iteration 101 | **First iteration whose mean executed score reaches 175.4** | Real-simulation iterations to get there (101 → 13–20); RMSD of departure-time distribution (32.6 seed-to-seed vs 50.9–56.4); RMSD of daily link volumes (5.7 vs 24.5–30.0); share of agents within 5 min total travel time (77.1% vs 74.6–76.1%); car share (80.7% vs 76.2–80.0%) | 1, plus one original rerun with another seed as noise reference | No stationary state (authors: none had settled at that iteration); no pass rule for the 4–5× larger link differences |
| [Moukir et al. 2024](https://www.scitepress.org/Papers/2024/124526/124526.pdf) (multiMATSim), Los Angeles 0.1% and 1% | 4–8 parallel instances exchanging plans every 50 iterations | Original mean executed score curve; "converged score" 105 read off it | **Wall time when the mean executed score first reaches 105** | Mean executed score only: 6 h → 1.5 h (0.1%), 29 h → 6 h (1%); time for all 300 iterations not reduced (1%: 36 h → 50 h) | 1 | Mode shares, link volumes, departure times; part of the curve plots best stored scores, not executed ones |
| [Zhuge et al. 2021](https://doi.org/10.1007/s11116-019-10048-0), small car-only scenario | Only agents below their best stored plan replan; variable time step | Original, each calibrated with Cadyts | **Each run's own stopping iteration** (mean score change < 0.001 for 4 iterations) | Iterations (154 → 69) and time (1,187 s → 549 s); count error at 12 stations, 2-hour morning peak (MAPE 42.1% vs 42.5%) | 1 | Mode shares, score or departure distributions, other links; the stop rule is partly produced by the method (fewer replanners, flatter scores) |
| [Graur et al. 2021](https://www.dpss.inesc-id.pt/~rbruno/papers/dgraur-abmtrans21.pdf) (Hermes), Switzerland 10% | Faster mobsim | Original (QSim) | End of the run (301 iterations) | Mode shares (car 44.69% vs 45.15%); motorway volume differences; per-agent travel-time skew, mostly within 10% | 1 | Statistical test; authors call results "comparable, but not similar" and recalibrate |
| [Ben-Dor et al. 2021](https://doi.org/10.1016/j.simpat.2020.102233), Sioux Falls | Smaller population sample | **Mean and spread of 10 full-scale runs** | Each run's stationary state | Relative bias of each statistic, judged against the full-scale coefficient of variation; travel duration by period (t-tests); link volume-to-capacity bias; outlier runs by Tukey fence (3 of 100 in a different equilibrium) | **10 per sample size** | — (the most careful design; safe only at ≥ 20–25% sample) |
| [Natterer et al. 2025](https://doi.org/10.1016/j.trc.2025.105360), Paris 1% | Graph-neural-network surrogate replacing whole runs | One MATSim run per policy scenario; baseline averaged over 50 seeds | End state | **Policy-induced change** of daily link volumes on 416 unseen scenarios: R² 0.91 overall, 0.98 on policy roads, 0.77 off-policy; 98% of its error equals MATSim's own seed variance | 50 for the baseline, 1 per policy | Mode shift, hourly profiles |
| [Saprykin et al. 2019](https://doi.org/10.1016/j.simpat.2019.03.002) (GEMSim), [Laudan et al. 2025](https://doi.org/10.3390/info16020116) (distributed mobsim) | Faster mobsims | Counts (GEMSim); none (Laudan) | — | Swiss counts and iteration-to-iteration change (GEMSim); only that event output has the same format (Laudan) | — | **No item-by-item comparison with original MATSim on the same scenario** |

**What they have in common**

| Observation | Evidence |
|---|---|
| The reference is the original procedure, never a converged answer | All rows; the original itself stops after a fixed budget judged by eye |
| "Caught up" often means "reached the original's mean score" | PSim (175.4), multiMATSim (105). The same mean score can hide a different state: PSim reached it with car share 4.5 pp lower. The comparison happens during the search, and the mean includes untested trial plans |
| Levels are compared, rarely policy effects | Scores, mode shares, link volumes, counts; only Natterer compares the change a policy causes |
| One seed is the norm | Only Ben-Dor (10 runs) and Natterer (50-seed baseline) measure randomness; PSim adds one rerun |
| No pass criterion is set in advance | Differences are described ("very similar", "relatively small"), not tested against a threshold |

**Our design differs on each point:** we compare the nine policy effects, over the last 10 iterations after innovation stops (not at a score threshold), with three seeds, against intervals fixed before any accelerated run, and we require them to still hold 20 iterations later. Like all of these papers, our reference is still the original procedure; none of them, and not yet we, checks against a converged answer.

## 4. What we will follow on MATSim-NYC

**Rule.** We preserve the change a policy causes, not absolute levels:
- for each seed, run the baseline and the policy with that same seed;
- average over iterations 90–99;
- subtract.

For example, with seed 4711 the charging-related population makes 72,488 car trips without a toll and 63,773 with $9.18, so the toll removes **8,715**. That number must be preserved; matching the 72,488, screenline counts, or He's 127K is not required.

**Reference.** Three scenarios: no toll (baseline), $9.18 (Schema 1) and $14 (Schema 2), each run with three seeds (4711, 4712, 4713), so nine runs in total. Each run uses the original procedure: 100 iterations, innovation until iteration 79, selection only for iterations 80–99. Indicators are means over iterations 90–99, in model units (4% sample).

**Selection.** A conclusion of He et al. 2021 becomes a criterion only if all three seeds agree in direction and differ little relative to the effect.

**Interval.** Original mean ± max(2 × seed SD, practical margin), where the margin for shares is 0.05 pp. Set before any accelerated run is analysed.

### 4.1 Criteria (must hold, with the same direction)

| He et al. 2021 conclusion | Measured as | Original (3 seeds) | Required interval |
|---|---|---|---|
| Fewer car trips by the charging-related population | Trips removed, $9.18 | 8,715 / 9,073 / 8,361 | 8,005 – 9,429 |
| | Trips removed, $14 | 10,764 / 11,467 / 10,927 | 10,317 – 11,789 |
| Car → transit shift | Car share drop, $9.18 | 0.25 pp (0.23–0.27) | 0.20 – 0.30 pp |
| | Car share drop, $14 | 0.33 pp (0.32–0.35) | 0.28 – 0.38 pp |
| | Transit share rise, $9.18 | 0.057 pp (0.040–0.069) | 0.007 – 0.107 pp |
| | Transit share rise, $14 | 0.084 pp (0.077–0.097) | 0.034 – 0.134 pp |
| $14 stronger than $9.18 | Extra trips removed | 2,049 / 2,394 / 2,566 | 1,810 – 2,862 |
| | Extra car share drop | 0.081 pp (0.074–0.090) | 0.031 – 0.131 pp |
| | Extra transit share rise | 0.027 pp (0.007–0.039) | 0 – 0.077 pp ($14 still higher) |

Direction matches He et al. 2021 in all cases. Size differs: our 8,717 × 25 ≈ 218K trips vs their 127K; size is not required.

### 4.2 Reported only

| He et al. 2021 conclusion | Original | Why not a criterion |
|---|---|---|
| Revenue ($1.09B/year) | ≈ $434K / $525K per day | Sensitive to how fully a run is optimised |
| Both groups gain | Welfare per person changes by −$0.18 to −$0.81 | Different definition (He: travel-only surplus; ours: total utility incl. tolls); sign varies across seeds |
| 37–40% worse off | ≈ 50% in every run | Per-person differences are random |
| $14 lowers citywide welfare | Direction varies across seeds | Not stable in the original |

### 4.3 Each scenario: a loose sanity check, not a reproduction

The absolute state of each scenario depends on how fully the procedure optimises, while the policy-induced changes above do not. The original stops at 100 iterations by convention, not at a converged state. Requiring each scenario to fall inside the original's narrow seed range would therefore reject any method that searches differently, even when every conclusion is unchanged.

Each scenario is instead checked loosely, to catch runs that drift as a whole while the differences happen to stay in range:

| Indicator | Original: no toll / $9.18 / $14 | Allowed deviation from the original's same scenario |
|---|---|---|
| Car share | 13.27% / 13.03% / 12.94% | ≤ 2 pp |
| Transit share | 15.44% / 15.50% / 15.53% | ≤ 2 pp |
| Car trips of the charging-related population | 72,622 / 63,906 / 61,570 | ≤ 10% |
| People not finished by the end of the day | 16,486 (no toll) | ≤ 1.5 × original |

Whether each scenario also falls inside the original's natural seed range (e.g., car share 13.23–13.32% without a toll) is reported, not required.

**Pass condition.** The accelerated method is run on the same three scenarios with the same three seeds, using its own number of iterations. Each indicator is averaged over its last 10 iterations, and the nine comparisons are computed the same way:
- each toll scenario minus the baseline with the same seed;
- $14 minus $9.18;
- then the mean over the three seeds.

It passes if:
1. all nine fall inside their intervals with the same direction;
2. every scenario passes the sanity check in 4.3;
3. both still hold 20 iterations after the stop;
4. they hold on a scenario not used for tuning.

# RQ1. How do other fields accelerate simulation, and what carries over to MATSim?

**Answer.** By RQ2 and RQ3, accelerating MATSim means reaching the same nine policy effects with less compute. The final evaluation is fixed; the search before it can be redesigned freely. Other fields with slow stochastic searches to a steady state save compute in five places, and all five act on that free part:
- **where the search starts:** reuse earlier solutions;
- **who searches, and how much:** explore less as the run goes on, or only where it is needed;
- **how new candidates are made:** start from good ones, or screen them with a cheap predictor;
- **what the search reacts to:** averages of past states, not the latest noisy one;
- **when to stop:** a measured criterion, not a fixed budget.

All the fields warn about the same thing: **a faster search can end somewhere else.** Most of their acceleration papers check this with one run and a curve that has stopped moving. For MATSim, which can have several equilibria, that check is not enough. The RQ2 policy effects over three seeds are the check.

## Summary table

Grouped by where the saving comes from. Gains are as reported in the papers; reading notes in [literature/](literature/README.md).

| Where it saves | Field | Method (how it works) | Key papers | Reported gain | Lesson for MATSim |
|---|---|---|---|---|---|
| **Fewer iterations: better start** | Climate spin-up | Treat one model year as a fixed-point map; extrapolate from past iterates (Anderson); start from a de-noised or learned steady state | [Khatiwala 2024](https://doi.org/10.1126/sciadv.adn2839); [Mahfuz & Slawig 2025](https://arxiv.org/abs/2506.10475) | 5–12× (Anderson); 50–95% fewer iterations (learned start) | Warm start helps, but the end can move when equilibria are not unique |
| | Activity-based platforms | Start each scenario from the previous converged travel times | [Nair et al. 2026](https://arxiv.org/abs/2608.24817) (POLARIS) | "Fewer iterations" (no number) | Same as above; compare against a baseline that started the same way |
| **Fewer iterations: smarter proposals** | MATSim mode choice | Estimate the utility of every feasible mode chain and propose by logit; the simulation still scores and selects | [Hörl et al. 2018](https://doi.org/10.1016/j.procs.2018.04.087), [2019](https://doi.org/10.3929/ethz-b-000303667); [Rakow & Nagel 2023](https://doi.org/10.1016/j.procs.2023.03.086) | 4–5× fewer iterations to a similar score (Rakow & Nagel) | Closest fit: targets random mode switching; default estimators ignore road tolls |
| | Evolutionary computation | A cheap surrogate screens candidates; some always get the true evaluation | [Jin 2005](https://doi.org/10.1007/s00500-003-0328-5); [Hansen & Ostermeier 2001](http://www.cmap.polytechnique.fr/~nikolaus.hansen/cmaartic.pdf) | Fewer expensive evaluations; 3–10× (CMA-ES) | A cheap model may propose, never decide |
| | Multi-fidelity | Low fidelity filters, high fidelity stays in the loop | [Peherstorfer et al. 2018](https://arxiv.org/abs/1806.10761) | Saving grows with the rejection rate | Same rule; PSim and Planomat broke it and shifted results |
| **Fewer iterations: search where needed** | Combinatorial optimisation | Learn which parts of a solution are unstable; re-optimise only those | [Ouyang et al. 2025](https://arxiv.org/abs/2507.01037) (L2Seg) | 2–7× | The NYC policy effect sits in 33% of agents; random selection is the worst case |
| | Traffic assignment | Move travellers with the largest experienced-minus-shortest time; 1/n step sizes | [Sbayti et al. 2007](https://doi.org/10.3141/2029-03); [Auld et al. 2019](https://www.osti.gov/servlets/purl/1528926) | 7 → 2 iterations to the same gap | Use measured gaps only; moving everyone at once oscillates |
| **Fewer iterations: damped reactions** | Learning in games; traffic assignment | React to averaged past states, not the latest one | [Hofbauer & Sandholm 2002](https://homepage.univie.ac.at/Josef.Hofbauer/sfp.htm); [Sheffi 1985](https://web.mit.edu/sheffi/www/urbanTransportation.html) | Convergence in congestion games | Smoothing travel times can damp collective rerouting |
| **Fewer iterations: adaptive exploration** | MCMC; evolutionary algorithms | Tune exploration online and let adaptation vanish | [Andrieu & Thoms 2008](https://people.eecs.berkeley.edu/~jordan/sail/readings/andrieu-thoms.pdf); [Eiben et al. 1999](https://cs.adelaide.edu.au/~zbyszek/Papers/self9.pdf) | Faster mixing, target preserved | Anneal exploration, but stop adapting before the final evaluation |
| **Fewer iterations: stop on time** | MCMC; MATSim | Stop by a measured criterion over several chains | [Vehtari et al. 2021](https://arxiv.org/abs/1903.08008); [Hörl et al. 2021](https://doi.org/10.1016/j.trc.2021.102974) | Catches false convergence | Flat curves are not a stopping rule |
| **Cheaper iterations** | GPU or distributed simulation | Rewrite the mobsim for GPUs, event-driven execution or message passing | [Saprykin 2022](https://doi.org/10.3929/ethz-b-000601899); [Graur et al. 2021](https://www.dpss.inesc-id.pt/~rbruno/papers/dgraur-abmtrans21.pdf); [Laudan et al. 2025](https://doi.org/10.3390/info16020116) | Mobsim 2.5–119×; whole loop ≤ 22.7× | Capped by Amdahl's law; results only "comparable" to MATSim |
| **Fewer runs** | Surrogates of whole runs | Learn the input-to-output map from many runs | [Natterer et al. 2025](https://doi.org/10.1016/j.trc.2025.105360); [Lamperti et al. 2018](https://www.lem.sssup.it/WPLem/2017-11.html) | ≈ 5,000× per prediction (after ~10k training runs) | Replaces the final evaluation; indirect effects poorly predicted |

**In one sentence:** steady-state simulations are sped up mainly by wasting fewer trials (a better start, better proposals, searching only where needed), not by making each trial faster; a cheap model may propose but must not decide, and almost no paper checks that the accelerated end state is unchanged.

## 1. What we are accelerating

**The problem (RQ2, RQ3).**
- **What must not change:** the change a policy causes. That is nine checks (car trips removed, car share drop, transit share rise; under $9.18, under $14, and $14 minus $9.18), each with an interval set in advance. Absolute levels only need to pass a loose per-scenario check.
- **What is fixed:** the final evaluation. That means MATSim's own simulation and scoring, selection only, means over the last 10 iterations, and the same network, population and policies.
- **What is free:** everything before the final evaluation. That covers the number of iterations, when innovation stops, who explores and how, and a cold or warm start.

**MATSim as an algorithm (RQ3).** Each iteration does two things at once, and both share one network loading:
- **Search:** about 30% of agents copy a randomly chosen plan of theirs, change it (time, route or mode) and execute it;
- **Selection:** the rest choose among at most 5 stored plans by a logit on their scores.

This has five consequences for borrowing methods:

| Trait of MATSim | Evidence | What a borrowed method must cope with |
|---|---|---|
| Stochastic: each new plan is scored by one noisy execution | NYC scores are overwritten every iteration (no averaging) | Methods that assume exact evaluations (Newton, plain extrapolation) need denoising |
| Co-evolving: an agent's score depends on everyone else's plans | A congestion (potential) game; tens of thousands rerouting together overshoot | Changes made by many agents at once interact; step size matters |
| No convergence while innovating | Plan sets keep changing; best scores still rising at iteration 79 | Search cannot be judged by flat curves; only the fixed final evaluation can |
| Several equilibria are possible | 3 of 100 runs in a different state ([Ben-Dor et al. 2021](https://doi.org/10.1016/j.simpat.2020.102233)) | A method that starts or searches differently may land elsewhere; check on several seeds |
| Time goes into search, not into settling | Policy effects stable ~3 iterations after innovation stops; ≈ 85% of innovated plans not kept; ≈ 78% of each iteration in the mobsim | The main lever is a search that finds good plans with fewer iterations |

## 2. Fields at a glance

One row per field: the representative papers, what they do, and a related idea for MATSim. These ideas are not yet screened and are not a work plan; the method direction is open (charter §4). All 61 papers in [literature/](literature/README.md), plus L2Seg, are listed by field in the appendix.

| # | Field | Representative papers | What they do | Related idea for MATSim (not screened) |
|---|---|---|---|---|
| 1 | MATSim and agent-based transport | [Fourie et al. 2013](https://doi.org/10.3141/2343-09) (PSim); [Zhuge et al. 2021](https://doi.org/10.1007/s11116-019-10048-0); [Moukir et al. 2024](https://www.scitepress.org/Papers/2024/124526/124526.pdf) (multiMATSim); [Horni et al. 2016](https://doi.org/10.5334/baw) | Cheap pseudo-simulation between real ones; only agents below their best plan replan; parallel instances with different strategy weights exchange plans | Re-search only affected agents; elite parent; shorten / stop on Δ. PSim itself is ruled out (the cheap model scores) |
| 2 | Traffic assignment (DTA) | [Sheffi 1985](https://web.mit.edu/sheffi/www/urbanTransportation.html); [Sbayti et al. 2007](https://doi.org/10.3141/2029-03); [Ameli et al. 2020](https://doi.org/10.1111/mice.12524); [Auld et al. 2019](https://www.osti.gov/servlets/purl/1528926) | 1/n step sizes; move travellers with the largest experienced-minus-shortest time; mix historical and current travel times; initial solution matters | Travel-time smoothing; replan by measured time difference; innovation annealing |
| 3 | Activity-based agent platforms (POLARIS) | [Auld et al. 2016](https://www.osti.gov/pages/servlets/purl/1392074); [Mori et al.](https://www.osti.gov/pages/servlets/purl/3794253); [Nair et al. 2026](https://arxiv.org/abs/2608.24817) | Every agent re-decides each day with choice models; mode is chosen by a logit on zone-to-zone travel times (skims), not by trial; skims are averaged across iterations; warm start from the previous year's skims | Informed mode proposals; travel-time smoothing; warm start |
| 4 | Combinatorial optimisation (L2Seg) | [Ouyang et al. 2025](https://arxiv.org/abs/2507.01037) | Learn which parts of a solution are still unstable and re-optimise only those; labels from a one-step look-ahead | Re-search only affected agents (decided at group level first); oracle-ceiling check before building any selector |
| 5 | Evolutionary algorithms | [Jin 2005](https://doi.org/10.1007/s00500-003-0328-5); [Eiben et al. 1999](https://cs.adelaide.edu.au/~zbyszek/Papers/self9.pdf); [Hansen & Ostermeier 2001](http://www.cmap.polytechnique.fr/~nikolaus.hansen/cmaartic.pdf) | Surrogate screening with some true evaluations kept; exploration strength changed during the run; new candidates built from past successes | Informed mode proposals; innovation annealing; elite parent |
| 6 | Learning in games | [Hofbauer & Sandholm 2002](https://homepage.univie.ac.at/Josef.Hofbauer/sfp.htm); [Mertikopoulos et al. 2018](https://arxiv.org/abs/1709.02738) | Respond to the average of past play; undamped learning can cycle | Travel-time smoothing; score averaging |
| 7 | MCMC | [Andrieu & Thoms 2008](https://people.eecs.berkeley.edu/~jordan/sail/readings/andrieu-thoms.pdf); [Vehtari et al. 2021](https://arxiv.org/abs/1903.08008) | Adapt proposals online but let adaptation vanish; judge convergence from several chains | Innovation annealing; acceptance design (several seeds, window means) |
| 8 | Molecular dynamics (enhanced sampling) | [Earl & Deem 2005](https://arxiv.org/abs/physics/0508111); [Hénin et al. 2022](https://arxiv.org/abs/2202.04164) | Bias only the exploration (replicas, history-dependent bias), keep the final statistics unbiased | The "free search, fixed final evaluation" rule; parallel replicas on idle cores (later work) |
| 9 | Climate spin-up | [Khatiwala 2024](https://doi.org/10.1126/sciadv.adn2839); [Mahfuz & Slawig 2025](https://arxiv.org/abs/2506.10475) | Anderson extrapolation of the yearly map; de-noised warm start; a learned steady state as the initial value | Warm start; Anderson on travel times kept for later |
| 10 | Economic agent-based models | [Lamperti et al. 2018](https://www.lem.sssup.it/WPLem/2017-11.html); [Grazzini et al. 2017](https://repository.essex.ac.uk/23189/) | A classifier trained on few runs decides which runs to execute; stationarity tests set burn-in | Informed mode proposals; stop on Δ |
| 11 | Multi-fidelity and surrogates | [Peherstorfer et al. 2018](https://arxiv.org/abs/1806.10761); [Giles 2008](https://doi.org/10.1287/opre.1070.0496) | Cheap models filter or correct, the expensive model stays in the loop; multilevel Monte Carlo | Informed mode proposals (predictor proposes, MATSim decides); coarse to fine (deferred) |
| 12 | Reduced-order and learned simulators | [Kochkov et al. 2021](https://doi.org/10.1073/pnas.2101784118); [Natterer et al. 2025](https://doi.org/10.1016/j.trc.2025.105360) | Coarse solver plus learned correction; GNN surrogate of whole MATSim runs | None directly: they replace the final evaluation. Natterer shows indirect effects matter (off-policy roads R² 0.77) |
| 13 | Faster simulation engines | [Saprykin 2022](https://doi.org/10.3929/ethz-b-000601899) (GEMSim); [Graur et al. 2021](https://www.dpss.inesc-id.pt/~rbruno/papers/dgraur-abmtrans21.pdf) (Hermes); [Laudan et al. 2025](https://doi.org/10.3390/info16020116) | GPU, event-driven or distributed mobsims | Outside our definition (cost per iteration); motivation: once the mobsim is fast, the search is the bottleneck |

## 3. How they accelerate, by stage of the search

The same literature grouped by the part of the search it acts on, for analysis. Numbers are from the papers; reading notes in [literature/](literature/README.md).

| Where it acts | Field · paper | What they do | Result | Fit for MATSim |
|---|---|---|---|---|
| **Where the search starts** | Climate spin-up · [Khatiwala 2024](https://doi.org/10.1126/sciadv.adn2839) | Under noisy forcing, extrapolate on a de-noised version first, then switch back to the normal model | Still 5× faster; plain extrapolation stalls under noise | Start point is free in our definition; the end must be re-checked |
| | Climate spin-up · [Mahfuz & Slawig 2025](https://arxiv.org/abs/2506.10475) | A network trained on earlier spin-ups predicts the steady state, used as the initial value | 50–95% fewer iterations | Their end point is unchanged only because their model has a unique steady state; MATSim's may not |
| | Traffic assignment · [Ameli et al. 2020](https://doi.org/10.1111/mice.12524) | Compare initial solutions and step sizes for simulation-based assignment | Both strongly affect speed and the final solution | Same warning: the start can move the end |
| | Activity-based platform · [Nair et al. 2026](https://arxiv.org/abs/2608.24817) (POLARIS) | Each forecast year starts from the previous year's converged skims | 14 iterations per year (≈ 43.5 h); "the prior year's skims warm-start the iterations, so fewer are needed", no cold-start comparison given | Warm start is routine practice elsewhere too, but its saving is rarely measured |
| | MATSim policy studies · [Grether et al. 2008](https://doi.org/10.14279/depositonce-10358); [He et al. 2021](https://arxiv.org/abs/2008.04762) | Run policy scenarios from the baseline's final plans | Common practice, not tested for bias | The MATSim book lists "if the resulting set of plans is unbiased by the fast initialization" as open ([Horni et al. 2016](https://doi.org/10.5334/baw), §97.2) |
| **Who searches, and how much** | Evolutionary algorithms · [Eiben et al. 1999](https://cs.adelaide.edu.au/~zbyszek/Papers/self9.pdf) | Change exploration during the run: by schedule, or from feedback such as the 1/5 success rule | Static parameters "seem to be inappropriate"; even simple schedules help | MATSim's innovation share is fixed at 30% until it drops to 0 |
| | MCMC · [Andrieu & Thoms 2008](https://people.eecs.berkeley.edu/~jordan/sail/readings/andrieu-thoms.pdf) | Tune proposals online; adaptation must diminish | Faster mixing without losing the target | Fits "free search, fixed end": adapt during search, stop adapting before the final evaluation |
| | Traffic assignment · [Sheffi 1985](https://web.mit.edu/sheffi/www/urbanTransportation.html); [Sbayti et al. 2007](https://doi.org/10.3141/2029-03) | Move only a shrinking share (1/n) of travellers, chosen by how much they would gain | Moving everyone at once oscillates; targeted choice gives a better solution, not fewer iterations | Choosing by "how much they would gain" needs a per-agent gap for full-day plans, which MATSim does not provide ([Nagel & Flötteröd 2009](https://infoscience.epfl.ch/record/152368/files/NagFlo09.pdf)) |
| | MATSim · [Zhuge et al. 2021](https://doi.org/10.1007/s11116-019-10048-0) | Only agents whose current plan is worse than their best stored plan replan | 154 → 69 iterations; one seed, 12 count stations | Their stop rule partly comes from the method: fewer replanners, flatter scores |
| | Combinatorial optimisation · [Ouyang et al. 2025](https://arxiv.org/abs/2507.01037) (L2Seg) | Predict which edges of a routing solution are still unstable (labels from a one-step look-ahead), fix the rest, re-optimise only the unstable part; a global model finds regions, a local model refines | 2–7× faster solvers. Marking a random 40–60% as unstable is worse than no decomposition; fixing too much causes premature convergence; with a perfect oracle the gain is far larger (39 s vs 241 s learned) | MATSim's default (30% random innovators) is the "random" case. Stability must be defined on plan search, not on the simulation (frozen agents still load the network), and per-agent labels "switches next iteration" were too noisy (AUC 0.58–0.67). Start at group level, report recall and true-negative rate, and measure the oracle ceiling first |
| | Activity-based platform · [Mori et al.](https://www.osti.gov/pages/servlets/purl/3794253); [Alam et al. 2026](https://arxiv.org/abs/2609.00327) (POLARIS) | Experienced-minus-routed travel time is the route-level convergence measure and triggers re-decisions ("if a trip takes significantly longer than expected") | No speed figure | A directly measured quantity, so allowed in our methods; covers routes only |
| **How new candidates are made** | Evolutionary algorithms · [Hansen & Ostermeier 2001](http://www.cmap.polytechnique.fr/~nikolaus.hansen/cmaartic.pdf) | CMA-ES builds new candidates from the steps that succeeded before | 3–10× fewer evaluations on moderately ill-scaled problems | MATSim mutates a uniformly random stored plan and picks a uniformly random new mode |
| | Evolutionary algorithms · [Jin 2005](https://doi.org/10.1007/s00500-003-0328-5) | A cheap approximate model screens candidates; some are always evaluated by the true function | Fewer expensive evaluations; without true evaluations, false optima | A predictor may propose; MATSim's simulation must still score |
| | Activity-based platform · [Auld et al. 2016](https://www.osti.gov/pages/servlets/purl/1392074) (POLARIS) | Mode is chosen by a logit (later nested logit, Gurumurthy et al. 2020) on skimmed or routed travel times by mode: all modes are evaluated at once, none is tried and executed first | No trial-and-error waste on mode; every agent re-decides every iteration | Directly addresses our largest gap (mode). Transfer as a proposal rule: estimate each mode's utility with MATSim's own scoring on (smoothed) travel times, propose by logit, keep some uniform proposals; MATSim still executes and scores |
| | Economic ABMs · [Lamperti et al. 2018](https://www.lem.sssup.it/WPLem/2017-11.html) | A classifier trained on a few runs picks which runs to execute, plus uncertainty sampling | Predictions 500–3,750× faster than the model | Same structure, applied to plans instead of parameter sets |
| | MATSim · [Horni et al. 2016](https://doi.org/10.5334/baw), Ch. 43 (Planomat); [Fourie et al. 2013](https://doi.org/10.3141/2343-09) (PSim) | Score new plans in a simplified mobsim or from last iteration's travel times | Planomat dropped when its cheap scores drifted from the core mobsim; PSim cut QSim iterations 101 → 13–20 but car share moved 80.7% → 76.2% | Both let the cheap model decide. That changes the final evaluation, which our definition fixes |
| **What the search reacts to** | Learning in games · [Hofbauer & Sandholm 2002](https://homepage.univie.ac.at/Josef.Hofbauer/sfp.htm) | Respond to the average of past play, step 1/t | Converges in congestion games, not necessarily to a unique point | MATSim agents route on the last iteration's travel times only |
| | Learning in games · [Mertikopoulos et al. 2018](https://arxiv.org/abs/1709.02738) | Analyse when learning cycles instead of settling | Undamped learning can cycle | Matches the overshoot when many agents reroute together |
| | Activity-based DTA · [Auld et al. 2019](https://www.osti.gov/servlets/purl/1528926) (POLARIS) | Route on a mix of historical and current link times; in one variant the weight also shrinks as 1/n and depends on each traveller's gap | Mixing alone (weight independent of the gap) cuts oscillation but still needs 7 iterations; the gap-dependent 1/n variant reaches the same gap in 2; one run, end distribution not checked | The gap-free mixing transfers directly to routing; the 7 → 2 gain needs a per-agent gap. Too much smoothing reacts slowly to a new toll |
| | Activity-based platform · [Mori et al.](https://www.osti.gov/pages/servlets/purl/3794253) (POLARIS) | "Across multiple 24-hour-day iterations of POLARIS, travel times are averaged to obtain a stable skim" that mode and destination choice use | Cordon, distance and delay pricing run to iteration 50 (1.25 h each); judged by flat revenue and delay curves, one run | Smoothing applies to the travel times used for mode proposals too, not only to routing |
| | MATSim · [Horni et al. 2016](https://doi.org/10.5334/baw), §47.3.2 | Average scores over executions (MSA) once innovation stops | Selection then converges to a unique logit distribution | NYC overwrites scores each iteration; averaging changes the final evaluation, so it belongs only in the search phase |
| **When to stop** | MATSim · [Hörl et al. 2021](https://doi.org/10.1016/j.trc.2021.102974) | Stop when a moving mean is close to itself and to a lagged mean | The only RQ2 paper with a numeric rule | Applicable; we apply it to the policy effects, not to levels |
| | MCMC · [Vehtari et al. 2021](https://arxiv.org/abs/1903.08008); ABM · [Grazzini et al. 2017](https://repository.essex.ac.uk/23189/) | Judge convergence from ≥ 4 chains; set burn-in by a stationarity test | Catches failures a single trace hides | Supports several seeds and window means |
| | Traffic assignment · [Sheffi 1985](https://web.mit.edu/sheffi/www/urbanTransportation.html) | Warns that "changes have become small" is a misleading stop rule | — | Flat curves after innovation stops say nothing about where the search ended |
| **Cost per iteration** (outside our definition) | GPU, distributed and event-driven mobsims: [Saprykin 2022](https://doi.org/10.3929/ethz-b-000601899) (GEMSim); [Graur et al. 2021](https://www.dpss.inesc-id.pt/~rbruno/papers/dgraur-abmtrans21.pdf) (Hermes) | Rewrite the network loading | GEMSim mobsim 100×, whole loop 22.7× because replanning then takes ≈ 47% of each iteration; Hermes 2.5× per iteration | Engineering, not this question; shows that once the mobsim is fast, the search is the bottleneck |
| | Population sampling · [Ben-Dor et al. 2021](https://doi.org/10.1016/j.simpat.2020.102233) | Simulate a smaller sample | Safe at ≥ 25%; below 10% statistics deviate | NYC is already a 4% sample |

## 4. What the fields have in common

| Observation | Evidence |
|---|---|
| Steady-state problems are sped up by wasting fewer trials, not by faster trials | Adaptive exploration, screening, targeted moves and warm starts all cut iterations; faster engines shrink at the loop level (22.7× of 100×) |
| A cheap model must not have the last word | Jin: false optima; Planomat: dropped; PSim: car share moved; multi-fidelity methods keep the expensive model in the loop ([Peherstorfer et al. 2018](https://arxiv.org/abs/1806.10761)) |
| Adaptation must end before the result is read | Adaptive MCMC requires diminishing adaptation; the MATSim book requires innovation off |
| Averaging damps noise and cycles; extrapolation struggles with noise | Fictitious play, MSA and POLARIS average; Khatiwala's plain extrapolation stalls under noise |
| Changing the start can change the end when equilibria are not unique | Mahfuz works because the steady state is unique; Ben-Dor and [Watling & Hazelton 2003](https://doi.org/10.1023/A:1025398302560) show MATSim-type processes need not be |
| Choosing at random what to re-optimise wastes effort; choosing well needs a measured ceiling first | L2Seg: random decomposition is worse than none, a perfect oracle is 6× better than the learned model; MATSim's default picks 30% of agents at random |
| Platforms that do not try options do not waste trials on them | POLARIS evaluates all modes with a choice model on averaged travel times; MATSim tries one random mode and executes it (71% clearly worse in NYC) |
| Acceleration papers rarely check the end state | PSim, Zhuge and POLARIS compare scores, gaps or a few counts on one seed; the MATSim book leaves bias as an open question |

## 5. What carries over to MATSim-NYC

**Rule (from RQ3).** A borrowed method may change anything before the final evaluation:
- where the search starts;
- who searches and how often;
- how new plans are made;
- what travel times and scores the search reacts to;
- when innovation stops.

It may not change the final evaluation:
- MATSim's own simulation and scoring;
- selection only;
- means over the last 10 iterations;
- the same network, population and policies.

**What this keeps and rules out.**
- **Kept:** warm starts, schedules that reduce exploration over time, informed proposals (including utility-based mode proposals), smoothed travel times during search, re-search limited to affected agents, replanning by a measured time difference, and stopping on the policy effects.
- **Ruled out:** methods where a cheap model scores plans that enter the final evaluation (PSim, Planomat), and methods that change how plans are scored at the end.

**Lessons from the reading.**
- A cheap model may propose but never decide (Jin; Planomat; PSim).
- Adaptation diminishes and ends with innovation off (Andrieu & Thoms; MATSim book).
- A different start is checked against a baseline that started the same way, on several seeds, because MATSim can have several equilibria (Ben-Dor; Watling & Hazelton).
- A flat curve is not a stopping rule (Sheffi).
- Before building a selector (who searches), measure its ceiling with oracle labels from finished runs, and report recall and true-negative rate (L2Seg).
- Evaluate options with a model instead of trying them where possible, but let MATSim execute and score (POLARIS mode choice; Jin).
- Any extra cost, such as training or running a predictor, counts toward total compute.

**Check.** Every borrowed method is judged by the RQ2 criteria: a faster run counts only if the nine policy effects stay inside their intervals.

## Appendix. All papers by field

Every paper read for RQ1 ([literature/](literature/README.md), numbered as there), grouped by field. "Approach to try" names a related idea for MATSim (not screened, not a plan) or says why the paper is background only.

### A1. MATSim and agent-based transport

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 03 | [Horni, Nagel & Axhausen 2016](https://doi.org/10.5334/baw), MATSim book | Configuration, innovation switch-off, PSim (Ch. 39), Markov-chain view (Ch. 48), Planomat (Ch. 43), open question on fast initialisation (§97.2) | Problem definition; "cheap model must not decide" (Planomat); score averaging only in the search phase |
| 04 | [Nagel & Flötteröd 2009](https://infoscience.epfl.ch/record/152368/files/NagFlo09.pdf) | Defines agent-based UE/SUE; MATSim as co-evolutionary population search; switching ∝ expected gain; no gap function for full-day plans | Problem definition; why we use measured time differences, not an estimated gap |
| 05 | [Ben-Dor et al. 2021](https://doi.org/10.1016/j.simpat.2020.102233) | Population downscaling in MATSim, 10 runs per sample size | Coarse to fine (deferred); validation template with several runs; evidence of several equilibria |
| 01 | [Zhuge et al. 2021](https://doi.org/10.1007/s11116-019-10048-0) | Only agents below their best stored plan replan; variable mobsim time step | Re-search only affected agents; warns about stop rules produced by the method |
| 46 | [Fourie et al. 2013](https://doi.org/10.3141/2343-09) | PSim: pseudo-simulation from last iteration's travel times between QSim runs; 101 → 13–20 QSim iterations, car share shifted | Ruled out as a method (the cheap model scores); idea kept: cheap evaluation may only propose |
| 48 | [Moukir et al. 2024](https://www.scitepress.org/Papers/2024/124526/124526.pdf) | Parallel MATSim instances with different strategy weights, exchanging plans every 50 iterations; 4.0–4.8× wall time | Parallel replicas on idle cores (later work); judged only by average score |
| 62 | [Hörl, Balac & Axhausen 2018](https://doi.org/10.1016/j.procs.2018.04.087), [2019](https://doi.org/10.3929/ethz-b-000303667); [Hörl 2021](https://doi.org/10.1016/j.procs.2021.03.088) | MATSim's Discrete Mode Choice extension: estimate the utility of every feasible mode chain and choose by logit instead of at random; as an "importance sampler" MATSim still executes, scores and selects | Informed mode proposals, already implemented in MATSim; its default estimator has no road tolls, and no speed-up has been published for this use |
| 58 | [Chhatre et al. 2022](https://arxiv.org/abs/2207.05041) | Parallel Bayesian optimisation with early stopping to calibrate BEAM (MATSim-based) | Background: calibration outer loop, shows repeated runs are the cost |

### A2. Traffic assignment and day-to-day dynamics

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 06 | [Sheffi 1985](https://web.mit.edu/sheffi/www/urbanTransportation.html) | MSA with step 1/n for stochastic equilibrium; "changes are small" is a misleading stop rule; one inner iteration per outer is fastest | Innovation annealing; travel-time smoothing; stop on Δ (not on flat curves) |
| 07 | [Peeta & Ziliaskopoulos 2001](https://doi.org/10.1023/A:1012827724856) | Review of dynamic traffic assignment; simulation-based methods give up uniqueness | Background |
| 08 | [Sbayti et al. 2007](https://doi.org/10.3141/2029-03) | Move travellers with the largest experienced-minus-shortest time first; better solution, not fewer iterations | Replan by measured time difference |
| 09 | [Lu et al. 2009](https://ideas.repec.org/a/eee/transb/v43y2009i3p345-364.html) | Gap-function DUE; path swapping ∝ relative cost difference; equilibrate the current path set before adding paths | Replan by measured time difference; background for gap as a diagnostic |
| 10 | [Cascetta 1989](https://ideas.repec.org/a/eee/transb/v23y1989i1p1-17.html) | Traffic as a Markov process; unique stationary distribution if every option keeps positive probability | Problem definition (convergence in distribution) |
| 11 | [Watling & Hazelton 2003](https://doi.org/10.1023/A:1025398302560) | Day-to-day models; equilibria can be multiple or unstable; one run may stay in one mode of a bimodal distribution | Acceptance design: several seeds; warm start needs a matching baseline |
| 50 | [Ameli et al. 2020](https://doi.org/10.1111/mice.12524) | Compares path-swapping rules and initialisations for simulation-based DTA | Warm start (initial solution matters); travel-time smoothing |
| 52 | [Li et al. 2024](https://arxiv.org/abs/2401.08013) | Cumulative-logit day-to-day dynamics converge to the maximum-entropy UE, which depends on the initial state | Warm start needs care: the start selects among equilibria |
| 56 | [Li, Chen & Jin 2026](https://arxiv.org/abs/2607.17344) | Anderson acceleration for logit SUE on GPU, much faster than MSA | Anderson on travel times kept for later (deterministic loading only) |

### A3. Activity-based agent platforms (POLARIS)

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 51 | [Verbas et al. 2024](https://arxiv.org/abs/2408.05176); [Auld et al. 2019](https://www.osti.gov/servlets/purl/1528926) | Gap-based route switching; mixing of historical and current link times (7 → 2 iterations with the gap-dependent variant); 765 scenario runs | Travel-time smoothing; replan by measured time difference |
| 61 | [Auld et al. 2016](https://www.osti.gov/pages/servlets/purl/1392074); [Mori et al.](https://www.osti.gov/pages/servlets/purl/3794253); [Nair et al. 2026](https://arxiv.org/abs/2608.24817); [Gurumurthy et al. 2025](https://matsim.org/conferences/mum2025/abstracts/MUM25_paper_24.pdf) | Mode chosen by (nested) logit on skims; skims averaged across iterations; warm start from previous year's skims; cordon pricing run to iteration 50 | Informed mode proposals; travel-time smoothing; warm start |

### A4. Combinatorial optimisation

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| — | [Ouyang, Li, Ma & Wu 2025](https://arxiv.org/abs/2507.01037) (L2Seg) | Learn unstable segments of a routing solution, fix stable ones, re-optimise the rest; 2–7× faster; random decomposition worse than none | Re-search only affected agents, decided at group level; oracle-ceiling check; recall / true-negative rate |

### A5. Evolutionary algorithms

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 12 | [Jin 2005](https://doi.org/10.1007/s00500-003-0328-5) | Fitness approximation with evolution control; without true evaluations, false optima | Informed mode proposals with a share of uniform proposals |
| 13 | [Jin 2011](https://pub.uni-bielefeld.de/record/2978603) | Survey of surrogate-assisted evolutionary computation (abstract only) | Background |
| 14 | [Eiben et al. 1999](https://cs.adelaide.edu.au/~zbyszek/Papers/self9.pdf) | Parameter control: deterministic, adaptive (1/5 success rule), self-adaptive | Innovation annealing; adaptive strategy weights |
| 15 | [Hansen & Ostermeier 2001](http://www.cmap.polytechnique.fr/~nikolaus.hansen/cmaartic.pdf) | CMA-ES: mutation distribution adapted from selected steps | Elite parent (start from what succeeded) |
| 16 | [Popovici et al. 2012](https://doi.org/10.1007/978-3-540-92910-9_31) | Co-evolutionary algorithms: fitness depends on other individuals; define the solution concept first | Problem definition (an agent's score depends on others) |

### A6. Learning in games

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 17 | [Fudenberg & Levine 1998](https://jmvidal.cse.sc.edu/lib/fudenberg98a.html) | Equilibrium as the long-run outcome of learning (table of contents only) | Background |
| 18 | [Hofbauer & Sandholm 2002](https://homepage.univie.ac.at/Josef.Hofbauer/sfp.htm) | Stochastic fictitious play converges in potential games, not necessarily to a unique point | Travel-time smoothing; score averaging |
| 19 | [Mertikopoulos et al. 2018](https://arxiv.org/abs/1709.02738) | Regularised learning cycles in zero-sum games | Background: why undamped reactions overshoot |
| 20 | [Daskalakis et al. 2018](https://arxiv.org/abs/1711.00141) | Optimistic mirror descent removes cycling in bilinear zero-sum games | Later work (extrapolated travel times) |
| 21 | [Syrgkanis et al. 2015](https://arxiv.org/abs/1507.00407) | Optimistic learning gives faster regret decay when all players use it | Background |
| 53 | [Anagnostides et al. 2022](https://arxiv.org/abs/2203.12056) | Last-iterate convergence in potential games within O(1/ε²) iterations | Background (needs full feedback) |

### A7. MCMC

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 22 | [Roberts et al. 1997](https://doi.org/10.1214/aoap/1034625254) | Optimal acceptance rate 0.234 for random-walk Metropolis | Background: many rejected proposals are not waste in themselves |
| 23 | [Andrieu & Thoms 2008](https://people.eecs.berkeley.edu/~jordan/sail/readings/andrieu-thoms.pdf) | Adaptive MCMC by stochastic approximation; adaptation must diminish | Innovation annealing; adaptive strategy weights ending before the final evaluation |
| 24 | [Gelman & Rubin 1992](https://doi.org/10.1214/ss/1177011136) | Convergence from several over-dispersed chains (R̂) | Acceptance design (several seeds) |
| 25 | [Vehtari et al. 2021](https://arxiv.org/abs/1903.08008) | Rank-normalised R̂, bulk and tail ESS, ≥ 4 chains | Acceptance design (several seeds, window means) |

### A8. Molecular dynamics (enhanced sampling)

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 26 | [Earl & Deem 2005](https://arxiv.org/abs/physics/0508111) | Parallel tempering: replicas at several temperatures exchange states | Parallel replicas on idle cores (later work) |
| 27 | [Laio & Parrinello 2002](https://arxiv.org/abs/cond-mat/0208352) | Metadynamics: history-dependent bias fills visited minima | Later work (avoid re-proposing plans already tried) |
| 28 | [Hénin et al. 2022](https://arxiv.org/abs/2202.04164) | Survey: bias the exploration, recover unbiased statistics | The "free search, fixed final evaluation" rule |
| 54 | [Zhu et al. 2025](https://doi.org/10.1021/acs.chemrev.5c00700) | Machine learning for collective variables and biasing | Background |

### A9. Climate spin-up

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 29 | [Khatiwala 2024](https://doi.org/10.1126/sciadv.adn2839) | Black-box Anderson acceleration of spin-up (5–12×); de-noised warm start under noisy forcing | Warm start; Anderson on travel times later |
| 30 | [Khatiwala 2008](https://ora.ox.ac.uk/objects/uuid:0bfee829-bf1d-4d3e-a4ca-aa6cb882e62c) | Newton–Krylov for periodic steady states (abstract only) | Not applicable (needs a deterministic model) |
| 55 | [Mahfuz & Slawig 2025](https://arxiv.org/abs/2506.10475) | A network trained on past spin-ups predicts the steady state as the initial value; 50–95% fewer iterations | Warm start learned from earlier runs (valid only with a matching baseline) |

### A10. Economic agent-based models

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 31 | [Lamperti et al. 2018](https://www.lem.sssup.it/WPLem/2017-11.html) | Classifier surrogate with active sampling chooses which ABM runs to execute | Informed mode proposals (predict which proposals are worth executing) |
| 32 | [Grazzini et al. 2017](https://repository.essex.ac.uk/23189/) | Bayesian ABM estimation; runs test for burn-in; ergodicity checks | Stop on Δ (test-based stopping) |
| 33 | [Platt 2020](https://arxiv.org/abs/1902.05938) | Benchmark of ABM calibration methods | Background (calibration) |
| 57 | [Platt 2022](https://doi.org/10.1007/s10614-021-10095-9) | Neural likelihood for Bayesian ABM estimation | Background (calibration) |

### A11. Multi-fidelity and uncertainty quantification

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 34 | [Peherstorfer et al. 2018](https://arxiv.org/abs/1806.10761) | Adaptation, fusion, filtering; high fidelity stays in the loop; delayed-acceptance MCMC | Informed mode proposals (predictor filters, MATSim decides) |
| 35 | [Kennedy & O'Hagan 2001](https://www.asc.ohio-state.edu/statistics/comp_exp/jour.club/kennedy01.pdf) | Bayesian calibration with model-discrepancy term | Background (calibration) |
| 36 | [Giles 2008](https://doi.org/10.1287/opre.1070.0496) | Multilevel Monte Carlo couples coarse and fine levels | Coarse to fine (deferred) |

### A12. Reduced-order and learned simulators

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 37 | [Benner et al. 2015](https://doi.org/10.1137/130932715) | Projection-based parametric model reduction | Not applicable (needs governing equations) |
| 38 | [Peherstorfer & Willcox 2016](https://doi.org/10.1016/j.cma.2016.03.025) | Operator inference from black-box state snapshots | Later work (low-dimensional map of travel-time fields) |
| 39 | [Sanchez-Gonzalez et al. 2020](https://arxiv.org/abs/2002.09405) | Graph network simulators; inference about as slow as the original | Not applicable |
| 40 | [Li et al. 2021](https://arxiv.org/abs/2010.08895) | Fourier neural operator for PDE families | Not applicable (regular grids) |
| 41 | [Kochkov et al. 2021](https://doi.org/10.1073/pnas.2101784118) | Coarse CFD with learned correction, 40–80× | Coarse to fine idea only (deferred) |
| 49 | [Natterer et al. 2025](https://doi.org/10.1016/j.trc.2025.105360) | GNN surrogate of MATSim policy runs (Paris), ≈ 5,000× per prediction | Not a method for us (replaces the final evaluation); evidence that indirect effects matter |
| 59 | [Liu & Meidani 2023](https://arxiv.org/abs/2310.13193) | Heterogeneous GNN surrogate of static traffic assignment | Not applicable |

### A13. Faster simulation engines and parallel simulation

| # | Paper | What they do | Approach to try |
|---|---|---|---|
| 02 | [Graur et al. 2021](https://www.dpss.inesc-id.pt/~rbruno/papers/dgraur-abmtrans21.pdf) | Hermes event-driven mobsim, 2.5× per iteration | Outside our definition |
| 42 | [Saprykin et al. 2019](https://doi.org/10.1016/j.simpat.2019.03.002); [thesis 2022](https://doi.org/10.3929/ethz-b-000601899) | GEMSim GPU mobsim: 100× mobsim, 22.7× loop | Outside our definition; motivation (search becomes the bottleneck) |
| 43 | [Jiang et al. 2024](https://arxiv.org/abs/2406.08496) | LPSim multi-GPU regional simulation | Outside our definition |
| 44 | [Zhang et al. 2024](https://arxiv.org/abs/2406.10661) | MOSS GPU microscopic simulator | Outside our definition |
| 45 | [Fujimoto 2000](https://catalogimages.wiley.com/images/db/pdf/0471183830.pdf) | Parallel discrete-event simulation (table of contents only) | Background (why the QSim uses few cores) |
| 47 | [Laudan et al. 2025](https://doi.org/10.3390/info16020116) | Distributed QSim in Rust, 119× at 1,024 processes | Outside our definition |
| 60 | [Yedavalli et al. 2020](https://arxiv.org/abs/2007.03614) | MANTA GPU microsimulation; only 43% faster than JDEQSim on the same case | Outside our definition |

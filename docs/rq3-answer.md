# RQ3. What does convergence mean for MATSim, and in what sense?

**Answer.** MATSim's iterations are a stochastic learning process, not simulated days. "Converged" can mean three things:

| Sense | Meaning | Original NYC run (100 iterations, innovation off at 80) |
|---|---|---|
| Flat curves | Scores and mode shares stop changing | Yes after iteration 80, but mainly because agents stop trying new plans; slow drift remains |
| Equilibrium | No agent can gain by changing its own plan | No: best scores were still rising when innovation stopped, and agents still have better options |
| Stable conclusions | Policy effects stop changing | Yes: within ~3 iterations after innovation stops, and they agree across seeds |

There is no strict convergence. What the procedure delivers reliably is stable policy conclusions, so that is our definition.

## Literature

| Source | Point |
|---|---|
| [MATSim book](https://ubiquitypress.com/site/books/10.5334/baw) | Convergence requires innovation off and score averaging; NYC uses no averaging |
| [Cascetta 1989](https://ideas.repec.org/a/eee/transb/v23y1989i1p1-17.html); [Watling & Hazelton 2003](https://doi.org/10.1023/A:1025398302560) | A stochastic process converges in distribution, not to a fixed point; several equilibria possible |
| [Ben-Dor et al. 2021](https://doi.org/10.1016/j.simpat.2020.102233) | MATSim runs can end in different equilibria |
| [Mertikopoulos et al. 2018](https://arxiv.org/abs/1709.02738) | Learning can cycle instead of converging (Yining's GAN question); in NYC, agents switching routes together overshoot and swing back while innovation is on |
| Policy studies (RQ2) | Six of seven stop after a fixed number of iterations, judged by eye |

## Our definition

**A run is converged when the nine RQ2 policy effects:**
- are inside their intervals;
- are computed over 10 iterations in which no agent tries new plans;
- show no trend over those iterations;
- are still inside 20 iterations later.

**This means the search before that final evaluation can be redesigned freely:** number of iterations, when innovation stops, who explores and how, cold or warm start. The final evaluation stays fixed: MATSim's own simulation and scoring, selection only, with the same network, population and policies. Two checks guard against landing somewhere different:
- a per-scenario sanity check;
- a re-check on a scenario not used for tuning.

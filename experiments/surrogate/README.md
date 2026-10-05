# Surrogate study: can approximate iterations replace full simulation?

Status: **in progress** (2026-10-05). Numbers below are from single runs of one scenario and are
reported with their failure modes; nothing here is a validated speedup claim yet.

## Framing

Multi-iteration MATSim cost = (policies) × (iterations) × (cost per iteration). Exact engineering
(E1/E2, `experiments/redundancy/`) cut wall time by 26%; what remains is the interacting traffic
simulation itself. A 20–30× gain cannot come from one level — an Amdahl bound with the measured
per-iteration structure caps a perfect mobsim surrogate at roughly 4–6× for a single run. The study
therefore tests three multiplicative levels, each against an explicit tolerance:

| Level | Idea | Tolerance |
|---|---|---|
| L1 within an iteration | approximate a plan's travel times without QSim | fixed-plan QSim noise floor |
| L2 across iterations | replace most QSim iterations by pseudo-simulation (PSim), refresh adaptively | QSim seed spread of final policy indicators |
| L3 across policies | predict policy indicators at untested settings from a few full runs | QSim seed spread |

## Data

`data_runs.py` (`outputs/surrogate-data-20261005`):
- **Fixed-plan noise floor**: iteration 0 only, identical plans (full-baseline iteration 11), seeds 4711/1001/1002.
- **Extra seeds**: 12-iteration runs with seeds 4712 and 4713 writing events *and* pre-mobsim plans every
  iteration, so inputs for iteration *i* use only information available before its mobsim (no leakage).

## Findings so far

### Noise floor (fixed plans, different seeds)

| Comparison | Volume WAPE | Link-time error | Person travel-time MAE / median |
|---|---:|---:|---:|
| Same plans, different seed | 1.3% | 4.0% | 93 s / 31 s |
| Consecutive iterations (persistence) | 8.2% | 10.1% | 328 s / 107 s |

QSim is nearly deterministic given plans; iteration-to-iteration change is mostly the effect of other
agents' plan changes (signal), not noise. Tolerances must be correspondingly strict.

### L1: plan travel-time estimates (person level, network legs)

Held-out iteration 6 of seed 4712 (trained on iterations 1–5):

| Estimator | Changed plans MAE / median | Unchanged plans MAE / median |
|---|---:|---:|
| PSim replay, mean link times (15-min bins) | 579 s / 203 s | 949 s / 249 s |
| PSim replay, geometric-mean link times | 658 s / 249 s | 1,126 s / 310 s |
| Previous QSim outcome (what PSim keeps for unchanged plans) | — | 490 s / 187 s |
| Gradient-boosted correction of the replay (features PSim can compute) | 535 s / 192 s | 862 s / — |

A learned correction improves the replay by only ~8%; most of the error comes from interaction effects
a frozen-time replay cannot represent, not from how link times are aggregated.

### L2: PSim hybrids, end to end (seed 4711, 12 iterations, final iteration is QSim)

Gate check: with PSim installed but every iteration QSim (`qsim-ref`), all 12 iterations' online metrics are
identical to the plain run.

Final-iteration indicators, relative to the all-QSim run with the same seed (QSim seed SD is tiny, e.g.
car share 0.0002, so every arm is far outside seed noise; |z| reported as max over nine indicators):

| Arm | QSim its | Score | PT share | Not boarded | Waiting | Unfinished | Car entries | Revenue | max\|z\| |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| psim3-mean (contrib-like) | 5 | −26.9% | +2.3% | +10.5% | +8.7% | +8.1% | −3.7% | −5.2% | 90 |
| psim6-mean | 3 | −74.1% | +4.7% | +30.6% | +23.7% | +23.1% | −5.2% | −7.6% | 185 |
| drift-mean (θ = 0.5) | 5 | −29.9% | +2.0% | +11.8% | +9.4% | +9.0% | −2.0% | −2.5% | 77 |
| psim3-learned (road correction) | 5 | −26.1% | +2.4% | +10.3% | +8.6% | +7.9% | −2.8% | −4.8% | 94 |
| **psim3-pt (observed transit times)** | 5 | **−20.3%** | **+0.8%** | **+7.3%** | +5.9% | +5.7% | −2.1% | −3.3% | **34** |
| psim6-pt (observed transit times) | 3 | −60.5% | +2.2% | +24.1% | +17.7% | +18.4% | −2.7% | −4.5% | 101 |

Diagnosis: the bias grows with the number of PSim iterations and always points the same way — more transit,
more people not boarded, lower executed score. Experienced transit legs in QSim take **1.6–2.8× their routed
time** (peak hours 2.3–2.8×) because capacity is tight, so a replay that uses routed transit times makes transit
look far better than it is. Correcting road times does not help; scaling transit times by the last QSim's
experienced/routed ratio per departure hour removes about two thirds of the transit-share bias. The remainder
(denied boarding as a discrete capacity event; hour-level rather than line/stop-level ratios) is still open.

Cost: wall times drifted by up to ~25% over the session because of other load on the machine (an all-QSim
reference took 1,574 s at one time and 1,955 s later), so speedups are computed within each run from its own
QSim and PSim iteration durations: a PSim iteration costs 0.28–0.35 of a QSim iteration (replanning/routing
dominates), giving **1.6× (QSim every 3rd iteration) to 2.2× (every 6th)** over the iterations, startup excluded
(psim3-pt 1.58×, psim6-pt 2.00×).
This matches the Amdahl bound above: PSim alone cannot approach 20–30×.

### L3: policy response (congestion-charge scale)

Pending (`policy_runs.py`).

## Corrections made during the study (kept for the record)

1. **Parked-duration pairing bug.** The Python link-time extractor paired a vehicle's arrival link with its
   next departure from the same link, counting parked hours as travel time. Early results (very large
   aggregation errors, an apparent advantage of geometric means, a "7.5×" learned improvement) were
   artifacts and were recomputed after the fix. The Java statistics never had this bug; a feature-parity
   check against Java on real data exposed it.
2. **Noise interpretation.** An early reading treated iteration-to-iteration variation as noise; the fixed-plan
   experiment showed it is mostly signal.
3. **Implementation failures caught before or at the first PSim iteration** (precondition on routed modes,
   chronological event order, handler-derived events on the parallel events manager) — see the campaign
   manifests' `note` fields. Each was fixed with a synthetic regression test (`scripts/VerifyPSim.java`).
4. **Timing contamination.** One reference run overlapped with offline analysis; its wall time is not used.

## Implementation

- `src/main/java/org/c2smart/matsimnyc/NycPSim.java` — PSim adapted to this scenario: car/taxi/FHV keep their
  vehicles (pricing and facility tolls are billed by the normal handlers), transit legs use routed times,
  router travel times are gated during PSim iterations, events are emitted in QSim-like whole-second steps.
  Options: `-Dnyc.psim=cycle:K|drift:THETA`, `-Dnyc.psim.linkTime=mean|geometric`, `-Dnyc.psim.model=FILE`.
- `scripts/VerifyPSim.java`, `VerifyPSimModel.java`, `VerifyPSimFeatures.java` — semantics, Java/scikit-learn
  model parity (exact), Java/Python feature parity on real data (1.6e-15).
- `-Dnyc.pricing.scale=X` (Pricing2025) scales car charges and credits for L3; 1.0 is bit-identical.
- Analysis: `dataset.py`, `metrics.py`, `noise_floor.py`, `oracle*.py`, `agent_surrogate.py`, `export_model.py`,
  `evaluate.py`. Runners: `data_runs.py`, `psim_runs.py`, `policy_runs.py` (sequential, chained with `--after`).

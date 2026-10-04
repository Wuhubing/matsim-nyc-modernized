# Controlled route-choice pilot

This is a **problem-screening experiment**, not a calibrated model of people or NYC.
It does not alter the MATSim runner or the initialization experiments.

## Running

From the repository root:

```sh
.venv/bin/python -m unittest discover -s experiments/collective_behavior -p 'test_*.py' -v
.venv/bin/python experiments/collective_behavior/runner.py --out outputs/collective-behavior-UNIQUE
.venv/bin/python experiments/collective_behavior/report.py outputs/collective-behavior-UNIQUE
.venv/bin/python experiments/collective_behavior/audit.py outputs/collective-behavior-UNIQUE
.venv/bin/python experiments/collective_behavior/inspect_results.py outputs/collective-behavior-UNIQUE
```

The runner is opt-in and makes paid calls after numerical checks pass. It reads the
previously authorized key file at the workspace root; never add that file to Git.
A run directory must be new. It never overwrites or automatically retries an old run.
The default shared ledger is the existing acceleration campaign. An active writer
blocks budget reservation: no simulation or paid call starts in that case.

## Registered design

- 24 agents, 30 days, simultaneous actions. Intervention begins day 11, lasts ten
  days, and ends before day 21 in **all** causal conditions. Agents do not receive
  the event schedule, duration, magnitude, or causal label.
- Route A costs `10 + 0.5 * (agent_flow + background) / capacity_multiplier`;
  route B costs `16 + 0.25 * agent_flow`. Time is in artificial minutes.
- Scenarios: unchanged, capacity, background, both. Capacity multipliers are 2/3
  and 1/2; background flows are 8 and 16. Both combines corresponding strengths.
  These magnitudes match the separate shocks at A flow 16; they do not match at
  every flow, which is precisely why mechanisms may have different action values.
- Only A changes. This assumption and the baseline equations are public to every
  policy, including the arithmetic baseline. The setting is intentionally simple.
- Observations contain the last five own choices and experienced times. The flow
  condition additionally exposes both routes' total traffic, including background.
  Environment truth is saved separately and never passed to the decision function.
- Random policy chooses each route with probability 1/2. Smooth policy reconstructs
  an EWMA (weight .35, initial means 18) from the visible window and uses a logistic
  choice with temperature 2 minutes. Estimate policy infers capacity from observed
  A cost/total flow and background from total flow minus 24, then randomizes around
  the stationary equal-cost allocation. With time-only information it uses smooth
  learning. None receives actual future conditions or future agent choices.
- Numeric screen: seven scenario/strength cells × two information conditions ×
  three methods × 30 seeds = 1,260 runs. There is no redundant second null strength.
- Frozen replay: 15 states per scenario, selected deterministically from smooth/flow
  trajectories (seeds 0–14, days 12–19). From the candidate pool select with fixed
  seed 20261004, without inspecting LLM outcomes. Two information conditions × two
  LLM methods × three samples = 720 independent calls.
- Replay action cost holds the **other 23 next-day actions fixed**, re-inserting
  the focal agent on each alternative route. It is conditional action regret, not
  closed-loop welfare and not regret against an unattainable individual oracle.
- Closed loop: high/low smooth/time excess-cost cells plus null; two LLM methods,
  three seeds, 30 days, flow information. The 18 worlds advance in round-robin days.
  Planned calls: 12,960, **subject to budget**. Incomplete worlds are not ranked as
  complete episodes. Calls from an incomplete joint-action batch remain recorded,
  but that batch does not change the environment.
- One fixed model: gpt-4.1-mini-2025-04-14, temperature .7, 180 output tokens.
  Direct chooses first and then provides diagnostic fields; diagnose assesses first
  and chooses last. Prompts share observations and budget. No claim about hidden
  reasoning follows from this intervention; output order is part of the treatment.
- Generation rationale is not requested or used as causal evidence. Predictions
  concern the coming day; diagnostic labels concern the last observed conditions.

## Identifiability gate

A 16-person A flow with half capacity has the same 26-minute cost as capacity 1
with 16 background vehicles. Time-only observations match exactly. Total-flow
observations distinguish them. If seven **other** travelers next choose A, choosing
A is better in the capacity world and B in the background world. This is a
controlled counterfactual proving possible decision relevance, not proof of
spontaneous emergence or a forecast of the others' choices.

## Resource accounting and failures

Shared caps remain 4 hours and $20; this campaign additionally caps at 30 minutes
and $5, bounded by available shared funds. It prepays simulation time under the
existing executor lock, so legacy experiments cannot spend the same time. API
funds are reserved under the existing API lock. Final settlement refunds unused
simulation time only when no other writer is active; until then the full reservation
remains conservatively charged. Completed work can be reported without settlement.

All simulation and API waiting wall time inside the campaign is charged; setup,
unit tests and report rendering are outside simulation time. Every API call reserves
an upper cost bound based on request bytes plus framing allowance and output cap.
Actual usage is charged without cached-input discounts; unknown billing retains
its reservation. There is no automatic network retry or response cache. Three
transport failures stop dispatch. Repeated sampling always issues distinct calls.

Malformed, refused or incomplete outputs are logged and fall back to the last
route, or seeded random choice if none exists. Fallback actions remain in cost
metrics; their diagnostic/prediction fields are excluded. A budget stop produces
missing coverage, not fabricated actions. API errors are sanitized; request headers
and credentials are never logged.

## Outputs and interpretation

`manifest.json` and `code/` capture execution provenance; `numerical.jsonl.gz`
contains full numerical observations/actions/truth; `calls/` records every actual
LLM input/output; `replay*.jsonl` and `closed-steps.jsonl` record evaluations.
`results.json`, `comparison.png`, and `report_zh.md` retain incomplete conditions.
After execution, the read-only audit checks observations, costs, flow, archived
source hashes, and API accounting. `inspect_results.py` adds closed-loop trajectory
plots and prediction diagnostics; solid lines are individual group runs, whereas
dashed numerical baselines are 30-run means and intentionally suppress their variance.
These post-processing tools can also inspect partial runs without dispatching calls.

Run-level uncertainty is reported for numeric experiments. Frozen-state repetitions
are averaged before comparison; these selected states are exploratory and do not
represent a random sample of cities. Do not treat agents within a world as independent
replications. At most three closed-loop seeds support screening, not broad claims.
The social optimum is only an enumerated system lower bound, not an equally informed
policy. No thresholds have been calibrated to real policy importance.

RouteChoiceEnv was inspected as a reference, but no source was copied. PettingZoo,
SUMO, RouteRL and additional orchestration dependencies are not needed here.

Official API references checked for this implementation:
- https://developers.openai.com/api/docs/models/gpt-4.1-mini
- https://developers.openai.com/api/docs/guides/structured-outputs

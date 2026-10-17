#!/usr/bin/env python3
"""O2: how stale are stored scores?

MATSim 2026.0 updates only the executed plan's score (NewScoreAssignerImpl); with learningRate = 1 (NYC) the stored
score is simply the score of the plan's last execution. When a stored plan is selected again after `age` iterations,
its new score minus its stored score measures how much the environment (other agents' choices) has moved since then,
plus simulation noise. If staleness matters, |new - stored| should grow with age.

  o2_staleness.py RUN --out FILE.json [--first 0] [--last 99]

Uses only the W1 replanning log (agents-IT.csv.gz): per iteration and person, selected plan id, iteration created and
executed score. Residents only. A re-execution is an iteration t at which the executed plan was not created at t and
was executed before (last at t0 < t); age = t - t0, diff = executed(t) - executed(t0).
Reported by phase (innovation phase t < first switched-off iteration, selection phase after) and age bins:
n, mean, median, mean absolute and standard deviation of diff; and the share of re-executions with age 1."""
import argparse, json, os, sys
from pathlib import Path
import numpy as np

_SIBLING = Path(__file__).resolve().parent.parent/'l2seg'
REPO = Path(os.environ.get('L2SEG_DIR', str(_SIBLING if _SIBLING.is_dir() else Path.home()/'matsim-work'/'matsim-nyc-modernized'/'experiments'/'l2seg')))
sys.path.insert(0, str(REPO))
from logs import ReplanningLog                    # noqa: E402

RESIDENTS = ('man', 'nonman')
AGE_BINS = [(1, 1, '1'), (2, 2, '2'), (3, 5, '3-5'), (6, 10, '6-10'), (11, 20, '11-20'), (21, 40, '21-40'), (41, 999, '41+')]


def stats(x):
    if len(x) == 0:
        return {'n': 0}
    return {'n': int(len(x)), 'mean': float(x.mean()), 'median': float(np.median(x)),
            'mean_abs': float(np.abs(x).mean()), 'sd': float(x.std())}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True)
    ap.add_argument('--first', type=int, default=0); ap.add_argument('--last', type=int)
    ap.add_argument('--switch-off', type=int, default=80, help='first iteration without innovation')
    a = ap.parse_args()
    log = ReplanningLog(a.run)
    last = a.last if a.last is not None else max(log.iterations)
    res = np.isin(log.subpopulation, RESIDENTS)
    n = len(log.index)
    memory = [dict() for _ in range(n)]            # per person: plan id -> (score, iteration)
    ages, diffs, phases = [], [], []
    for t in range(a.first, last + 1):
        ag = log.agents(t)
        plan, created, ex = ag['plan'], ag['created'], ag['executed']
        for i in np.nonzero(res & (plan >= 0) & np.isfinite(ex))[0]:
            p = int(plan[i]); prev = memory[i].get(p)
            if prev is not None and created[i] != t:
                ages.append(t - prev[1]); diffs.append(ex[i] - prev[0]); phases.append(t >= a.switch_off)
            memory[i][p] = (float(ex[i]), t)
        if t % 10 == 0:
            print(f'iteration {t}: {len(ages)} re-executions so far', flush=True)
    ages, diffs, phases = np.array(ages), np.array(diffs), np.array(phases)
    out = {'run': a.run, 'iterations': [a.first, last], 'switch_off': a.switch_off, 'phases': {}}
    for name, m in (('innovation', ~phases), ('selection', phases), ('all', np.ones(len(ages), bool))):
        d = {'all_ages': stats(diffs[m]), 'share_age1': float((ages[m] == 1).mean()) if m.any() else None, 'by_age': {}}
        for lo, hi, lab in AGE_BINS:
            mm = m & (ages >= lo) & (ages <= hi)
            d['by_age'][lab] = stats(diffs[mm])
        out['phases'][name] = d
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    print('\nphase       age    n         mean    median  mean|d|   sd')
    for name, d in out['phases'].items():
        for lab, s in d['by_age'].items():
            if s['n']:
                print(f"{name:11} {lab:6} {s['n']:9d} {s['mean']:+8.3f} {s['median']:+8.3f} {s['mean_abs']:8.3f} {s['sd']:8.3f}")


if __name__ == '__main__':
    main()

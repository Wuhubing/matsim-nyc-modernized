#!/usr/bin/env python3
"""Labels L-H and L-U and the stability curve from one run's replanning log (plan Section 4, RQ1).

L-H  agent i is unresolved at iteration t if the plan selected at the end of the run was created after t.
L-U  for each innovation (agent innovated at t, so a new plan was created and selected at t): the outcome is
     positive if the new plan is selected again in t+1..t+H and its executed score at its last selection in
     t..t+H exceeds the agent's best stored score at the end of t-1 by more than delta. Innovations with
     t+H beyond the last iteration are censored (not labelled). Default H = 10; delta comes from RQ0.
Stability curve per iteration: share unresolved (L-H), share innovating, share whose selected plan differs
from the previous iteration, share selecting an already stored plan (revisit), per subpopulation that innovates.

  labels.py RUN --out DIR [--horizon 10] [--delta 0]
writes DIR/stability.csv, DIR/labels.npz (lh[t, row], innovation events with L-U) and prints a summary.
"""
import argparse, csv, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from logs import ReplanningLog


def load(log):
    its = log.iterations
    if its != list(range(its[0], its[-1] + 1)): raise SystemExit(f'agent files missing: {its}')
    a = [log.agents(t) for t in its]
    stack = lambda k, dt=None: np.stack([x[k] for x in a]).astype(dt or a[0][k].dtype)
    return its, {k: stack(k, np.float32 if k in ('executed', 'best') else None) for k in ('plan', 'created', 'executed', 'best', 'innovated', 'plans')}


def label_lh(created):
    """lh[t, i] = final selected plan of i created after iteration t."""
    T = created.shape[0]
    return created[-1][None, :] > np.arange(T)[:, None]


def label_lu(d, horizon, delta):
    """Innovation events (t, row) with L-U label; censored events are dropped."""
    T = d['plan'].shape[0]; ts, rows, labels = [], [], []
    for t in range(1, T - horizon):
        new = d['innovated'][t] & (d['created'][t] == t)
        idx = np.nonzero(new)[0]
        if not len(idx): continue
        plan = d['plan'][t, idx]
        window = d['plan'][t:t + horizon + 1, idx] == plan[None, :]            # selections in t..t+H
        again = window[1:].any(axis=0)
        last = horizon - np.argmax(window[::-1], axis=0)                         # last selection offset
        score = d['executed'][t + last, idx]
        labels.append(again & (score > d['best'][t - 1, idx] + delta)); ts.append(np.full(len(idx), t)); rows.append(idx)
    cat = lambda x, dt: np.concatenate(x).astype(dt) if x else np.zeros(0, dt)
    return cat(ts, np.int32), cat(rows, np.int32), cat(labels, bool)


def stability(its, d, lh, groups):
    out = []
    for t_i, t in enumerate(its):
        for name, mask in groups.items():
            prev = d['plan'][t_i - 1] if t_i else None
            changed = (d['plan'][t_i] != prev) if prev is not None else np.zeros_like(mask)
            revisit = changed & (d['created'][t_i] < t)
            out.append({'iteration': t, 'group': name, 'persons': int(mask.sum()), 'unresolved_lh': lh[t_i, mask].mean(),
                        'innovated': d['innovated'][t_i, mask].mean(), 'selected_changed': changed[mask].mean(),
                        'revisit': revisit[mask].mean()})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True); ap.add_argument('--horizon', type=int, default=10)
    ap.add_argument('--delta', type=float, default=0.0)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    log = ReplanningLog(a.run); its, d = load(log)
    if its[0] != 0: raise SystemExit('expected the log to start at iteration 0')
    lh = label_lh(d['created'])
    ever = d['innovated'].any(axis=0)
    groups = {'innovating': np.isin(log.subpopulation, sorted(set(log.subpopulation[ever])))}
    groups.update({f'subpopulation:{s}': log.subpopulation == s for s in sorted(set(log.subpopulation[ever]))})
    rows = stability(its, d, lh, groups)
    with open(out/'stability.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    t, r, lu = label_lu(d, a.horizon, a.delta)
    np.savez_compressed(out/'labels.npz', lh=lh, person_index=log.index, lu_iteration=t, lu_row=r, lu=lu,
                        horizon=a.horizon, delta=a.delta)
    print(f'{len(its)} iterations, {len(log.index)} persons; L-U events {len(lu)} (positive {lu.mean() if len(lu) else float("nan"):.3f})')
    for row in rows:
        if row['group'] == 'innovating':
            print(f"it {row['iteration']:3d} unresolved {row['unresolved_lh']:.3f} innovated {row['innovated']:.3f} "
                  f"changed {row['selected_changed']:.3f} revisit {row['revisit']:.3f}")


if __name__ == '__main__':
    main()

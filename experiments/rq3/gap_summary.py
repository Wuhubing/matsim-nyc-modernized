#!/usr/bin/env python3
"""Summary and validation of GapEstimator output (QR3/06_G_estimator_design.md sections 1 and 4).

  gap_summary.py GAP.csv.gz RUN_DIR K --out FILE.json

G and its components (residents in the sample):
  g_route = max(0, est_route - est_current), g_mode = max(0, est_mode - est_current), g = max(g_route, g_mode);
  G = sum(g) / sum(|est_current|); also median, p90 and share of g < 0.1 per component, by subpopulation and by the
  main mode of the executed plan (first trip mode that is not walk).
V1  est_current against the executed score of iteration K (research/persons-K): Spearman, mean and median error.
V2  real switches in iteration K (selected plan created in K by ReRoute or SubtourModeChoice, parent estimated too):
    estimated gain est_current - est_parent against realised gain executed(K) - executed(K-1), for persons whose plan
    executed in K-1 was the parent (replanning-log/agents-(K-1)). Spearman and least-squares slope, per strategy type.
Pass marks (pre-registered): V1 Spearman >= 0.8; V2 Spearman >= 0.3 for ReRoute and for SubtourModeChoice separately.
"""
import argparse, csv, gzip, json
from pathlib import Path
import numpy as np


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3:
        return float('nan')
    rx, ry = x.argsort().argsort(), y.argsort().argsort()
    return float(np.corrcoef(rx, ry)[0, 1])


def read_csv(path):
    with gzip.open(path, 'rt', newline='') as f:
        return list(csv.DictReader(f))


def num(s):
    return float(s) if s not in ('', None) else float('nan')


def main_mode(modes):
    for m in modes.split('|'):
        if m and m != 'walk':
            return m
    return 'walk'


def dist(g):
    g = np.asarray(g, float)
    return {'n': int(len(g)), 'mean': float(g.mean()) if len(g) else None, 'median': float(np.median(g)) if len(g) else None,
            'p90': float(np.percentile(g, 90)) if len(g) else None, 'share_below_0.1': float((g < 0.1).mean()) if len(g) else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('gap'); ap.add_argument('run'); ap.add_argument('k', type=int); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    sim = Path(a.run)/'simulation'
    rows = read_csv(a.gap)
    ok = [r for r in rows if r['failures'] != '-1' and r['est_current'] != '']
    out = {'rows': len(rows), 'estimated': len(ok), 'person_errors': len(rows) - len(ok),
           'with_failures': sum(1 for r in ok if int(r['failures']) > 0)}
    cur = np.array([num(r['est_current']) for r in ok])
    route = np.array([num(r['est_route']) for r in ok])
    mode = np.array([num(r['est_mode']) for r in ok])
    g_route = np.maximum(0, np.nan_to_num(route - cur, nan=0.0))
    g_mode = np.maximum(0, np.nan_to_num(mode - cur, nan=0.0))
    g = np.maximum(g_route, g_mode)
    denom = np.abs(cur).sum()
    out['G'] = {'total': float(g.sum() / denom), 'route': float(g_route.sum() / denom), 'mode': float(g_mode.sum() / denom)}
    out['dist'] = {'total': dist(g), 'route': dist(g_route), 'mode': dist(g_mode)}
    groups = {}
    for i, r in enumerate(ok):
        for key in ('sub:' + r['subpopulation'], 'mode:' + main_mode(r['current_modes'])):
            groups.setdefault(key, []).append(i)
    out['by_group'] = {k: {'n': len(ix), 'G': float(g[ix].sum() / np.abs(cur[ix]).sum()), 'mean_g': float(g[ix].mean())}
                       for k, ix in sorted(groups.items())}
    choice = {}
    for i, r in enumerate(ok):
        if g_mode[i] > 0 and r['mode_choice']:
            m = r['mode_choice'].split(':')[0]; choice[m] = choice.get(m, 0) + 1
    out['best_mode_switch_counts'] = choice

    # V1
    executed = {r['person_id']: num(r['score']) for r in read_csv(sim/'research'/f'persons-{a.k}.csv.gz')}
    pairs = [(c, executed[r['person_id']]) for c, r in zip(cur, ok) if r['person_id'] in executed]
    e, x = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
    out['V1'] = {'n': len(pairs), 'spearman': spearman(e, x), 'mean_error': float((e - x).mean()),
                 'median_abs_error': float(np.median(np.abs(e - x))), 'pass': spearman(e, x) >= 0.8}

    # V2
    log = sim/'replanning-log'
    v2 = {}
    if (log/f'agents-{a.k - 1}.csv.gz').exists():
        idof = {r['person']: r['person_id'] for r in read_csv(log/'persons.csv.gz')}   # agents-K use the row index
        prev = {idof[r['person']]: (r['plan_id'], num(r['executed_score'])) for r in read_csv(log/f'agents-{a.k - 1}.csv.gz')}
        now = {idof[r['person']]: num(r['executed_score']) for r in read_csv(log/f'agents-{a.k}.csv.gz')}
        for kind in ('ReRoute', 'SubtourModeChoice', 'TimeAllocationMutator'):
            est_gain, real_gain = [], []
            for r in ok:
                if not r['est_parent'] or kind not in r['mutator']:
                    continue
                if kind == 'ReRoute' and 'SubtourModeChoice' in r['mutator']:
                    continue
                p = prev.get(r['person_id'])
                if p is None or p[0] != r['parent_id'] or r['person_id'] not in now:
                    continue
                est_gain.append(num(r['est_current']) - num(r['est_parent']))
                real_gain.append(now[r['person_id']] - p[1])
            eg, rg = np.array(est_gain), np.array(real_gain)
            slope = float(np.polyfit(eg, rg, 1)[0]) if len(eg) > 2 else float('nan')
            v2[kind] = {'n': len(eg), 'spearman': spearman(eg, rg), 'slope': slope,
                        'mean_est': float(eg.mean()) if len(eg) else None, 'mean_real': float(rg.mean()) if len(rg) else None,
                        'pass': (spearman(eg, rg) >= 0.3) if len(eg) > 2 else None}
    out['V2'] = v2
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps({k: out[k] for k in ('rows', 'estimated', 'person_errors', 'with_failures', 'G', 'V1', 'V2')}, indent=1))
    print('dist', json.dumps(out['dist']))
    print('best mode switches', out['best_mode_switch_counts'])
    for k, v in out['by_group'].items():
        print(f"  {k:16} n={v['n']:6d}  G={v['G']:.4f}  mean g={v['mean_g']:.3f}")


if __name__ == '__main__':
    main()

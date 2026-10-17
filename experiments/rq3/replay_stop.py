#!/usr/bin/env python3
"""Gate 1: replay candidate stopping rules on complete reference trajectories (offline, no simulation).

  replay_stop.py S=DIR [S=DIR ...] --out FILE.json [--ref-window 90-99] [--switch-off 80]

Per run and iteration, indicators from iteration-metrics-IT.json and research/groups-IT.csv.gz: mean executed score
(all persons), car share and pt share of departing legs, unfinished persons, cordon entries, waiting person-hours.
Reference values: mean over the reference window per run; sigma = sd across runs of those window means (as in the
repository's tolerance table). Rules, applied separately to each run:
- T*: first t whose mean over t..t+9 is within 2 sigma of the cross-run reference mean for every indicator;
- C1(H, L, K): Hoerl-type double window on every indicator, |x_t - mu_t| <= a and |mu_t - mu_(t-L)| <= b, where mu_t is
  the mean of the H iterations before t; passes after K consecutive iterations with all checks true. a = 3 x the
  within-run sd of single iterations in the reference window (pooled over runs), b = 2 sigma.
  Evaluated twice: from iteration 0 (would it stop during the innovation phase?) and only after the switch-off.
For each stop: iteration, and the error of the 10-iteration mean at the stop against the run's own reference mean, in
units of sigma. A stop before the switch-off with errors far above 2 sigma is a false stop."""
import argparse, csv, gzip, json
from pathlib import Path
import numpy as np

IND = ('score', 'car_share', 'pt_share', 'unfinished', 'cordon_entries', 'wait_person_hours')


def trajectory(run):
    sim = Path(run)/'simulation'; its = sorted(int(p.stem.split('-')[-1]) for p in sim.glob('iteration-metrics-*.json'))
    rows = []
    for it in its:
        m = json.loads((sim/f'iteration-metrics-{it}.json').read_text())
        dep = m['departures']; tot = sum(dep.values())
        with gzip.open(sim/'research'/f'groups-{it}.csv.gz', 'rt') as f:
            g = {r['group']: r for r in csv.DictReader(f)}['all']
        rows.append([float(g['score_sum']) / float(g['persons']), dep.get('car', 0) / tot, dep.get('pt', 0) / tot,
                     float(m['unfinished_all']), float(m['private_car_entry_crossings']), float(m['censored_wait_person_hours'])])
    return np.array(its), np.array(rows)


def first_double_window(X, its, a, b, H, L, K, start):
    ok_run = 0
    for j in range(len(its)):
        if its[j] < start or j < H + L:
            ok_run = 0; continue
        mu = X[j - H:j].mean(axis=0); lam = X[j - L - H:j - L].mean(axis=0)
        ok = np.all(np.abs(X[j] - mu) <= a) and np.all(np.abs(mu - lam) <= b)
        ok_run = ok_run + 1 if ok else 0
        if ok_run >= K:
            return int(its[j])
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('runs', nargs='+'); ap.add_argument('--out', required=True)
    ap.add_argument('--ref-window', default='90-99'); ap.add_argument('--switch-off', type=int, default=80)
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.ref_window.split('-'))
    runs = dict(x.split('=', 1) for x in a.runs)
    T = {s: trajectory(d) for s, d in runs.items()}
    ref = {s: X[(its >= lo) & (its <= hi)].mean(axis=0) for s, (its, X) in T.items()}
    R = np.array(list(ref.values())); ref_mean = R.mean(axis=0); sigma = R.std(axis=0, ddof=1)
    within = np.sqrt(np.mean([X[(its >= lo) & (its <= hi)].var(axis=0, ddof=1) for its, X in T.values()], axis=0))
    A = 3 * within
    # b for the drift check: the strict version uses 2 sigma (cross-run sd of window means, as in the tolerance table);
    # the within-run version uses 3 x the sd of a difference of two H-iteration means under independent noise,
    # 3 * within * sqrt(2 / H) (first replay showed that 2 sigma is far below within-run noise and never stops).
    def b_for(H, kind):
        return 2 * sigma if kind == 'strict' else 3 * within * np.sqrt(2.0 / H)
    out = {'indicators': IND, 'ref_mean': ref_mean.tolist(), 'sigma': sigma.tolist(), 'within_sd': within.tolist(),
           'a': A.tolist(), 'runs': {}}
    def err(X, its, t, s):
        j = int(np.nonzero(its == t)[0][0]); m = X[max(0, j - 9):j + 1].mean(axis=0)
        return ((m - ref[s]) / sigma).tolist()
    for s, (its, X) in T.items():
        r = {}
        tstar = None
        for j in range(len(its) - 9):
            if np.all(np.abs(X[j:j + 10].mean(axis=0) - ref_mean) <= 2 * sigma):
                tstar = int(its[j]); break
        r['T_star'] = tstar
        for kind in ('strict', 'within'):
            for H, L, K in ((10, 5, 3), (10, 5, 5), (20, 10, 5)):
                for start, tag in ((0, 'from0'), (a.switch_off, 'after_switch_off')):
                    t = first_double_window(X, its, A, b_for(H, kind), H, L, K, start)
                    r[f'C1_{kind}_H{H}_L{L}_K{K}_{tag}'] = {'stop': t, 'error_sigma': err(X, its, t, s) if t is not None else None,
                                                            'before_switch_off': (t is not None and t < a.switch_off)}
        out['runs'][s] = r
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    print('sigma:', dict(zip(IND, np.round(sigma, 6))))
    for s, r in out['runs'].items():
        print(f"\nrun {s}: T* = {r['T_star']}")
        for k, v in r.items():
            if k == 'T_star':
                continue
            e = v['error_sigma']; emax = max(abs(x) for x in e) if e else None
            print(f"  {k:34} stop={v['stop']}  max|error|={emax if emax is None else round(emax, 1)} sigma  before switch-off={v['before_switch_off']}")


if __name__ == '__main__':
    main()

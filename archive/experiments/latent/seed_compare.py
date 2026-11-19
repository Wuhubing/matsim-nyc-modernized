#!/usr/bin/env python3
"""How far each seeded MATSim run is from the stable state, iteration by iteration (docs/converged-plan-plan.md, 6b).

  seed_compare.py --stable RUN_DIR --cold-traj RUN_DIR --runs NAME=RUN_DIR ... [--final-pkl NAME=PKL ...]
                  --stable-pkl PKL --city city.npz --out FILE.json

RUN_DIR is a run's simulation directory with research/group-modes-k.csv.gz and persons-k.csv.gz. Stable state: the
mean over iterations 90-99 of --stable (the original baseline of the same seed). Per iteration of every run:
share_car and share_pt of departing legs (all persons), car legs of the related cohort, mean executed score,
unfinished legs; distances = |value - stable| (car legs as a share of the stable value). --cold-traj (the original
cold baseline) gives the cold trajectory; for each run and distance, 'equivalent cold iteration' is the first cold
iteration whose 3-iteration moving average is at most the run's iteration-12 distance (3-iteration average 10-12).
With --final-pkl (extract_plans.py of a run's output plans, sampled persons) and --stable-pkl: per origin cell car and
pt trip shares of the selected plans, root mean square difference from the stable run's output plans.
--upto N reads iterations 0..N-1 of every run and --window A B averages the distances over iterations A..B (default
13 and 10 12, the 12-iteration check). --stable-seeds NAME=RUN_DIR (other seeds of the original, iterations 90-99)
gives the seed difference U: the same distances of their stable state from --stable."""
import argparse, csv, gzip, json, math, pickle
from collections import defaultdict
from pathlib import Path
import numpy as np

KEYS = ['share_car', 'share_pt', 'car_related', 'score', 'unfinished']


def iteration(run, k):
    legs = defaultdict(float); rel = 0.0
    with gzip.open(Path(run) / f'research/group-modes-{k}.csv.gz', 'rt') as f:
        for r in csv.DictReader(f):
            if r['group'] == 'all': legs[r['leg_mode']] += float(r['departures'])
            if r['group'] == 'charging:related' and r['leg_mode'] == 'car': rel = float(r['departures'])
    tot = sum(legs.values()); sc = []; unf = 0
    with gzip.open(Path(run) / f'research/persons-{k}.csv.gz', 'rt') as f:
        for r in csv.DictReader(f):
            if r['score']: sc.append(float(r['score']))
            unf += int(r['unfinished'] or 0)
    return {'share_car': legs['car'] / tot, 'share_pt': legs['pt'] / tot, 'car_related': rel, 'score': float(np.mean(sc)), 'unfinished': unf}


def trajectory(run, its):
    out = {}
    for k in its:
        if (Path(run) / f'research/group-modes-{k}.csv.gz').exists(): out[k] = iteration(run, k)
    return out


def cell_rmse(pkl, stable, city):
    x0, y0, size, nx, ny = city['grid']; ny = int(ny)
    def shares(path):
        agents = pickle.load(open(path, 'rb')); n = defaultdict(float); car = defaultdict(float); pt = defaultdict(float)
        for ag in agents.values():
            sel = next((p for p in ag['plans'] if p['selected']), ag['plans'][0])
            for t in sel['trips']:
                c = int((t[2] - x0) // size) * ny + int((t[3] - y0) // size); n[c] += 1; car[c] += t[0] == 'car'; pt[c] += t[0] == 'pt'
        return {c: (car[c] / n[c], pt[c] / n[c]) for c in n if n[c] >= 50}
    A, B = shares(pkl), shares(stable); cs = A.keys() & B.keys()
    return {'car': float(np.sqrt(np.mean([(A[c][0] - B[c][0]) ** 2 for c in cs]))),
            'pt': float(np.sqrt(np.mean([(A[c][1] - B[c][1]) ** 2 for c in cs]))), 'cells': len(cs)}


def main():
    ap = argparse.ArgumentParser()
    for k in ('--stable', '--cold-traj', '--stable-pkl', '--city', '--out'): ap.add_argument(k, required=True)
    ap.add_argument('--runs', nargs='+', required=True); ap.add_argument('--final-pkl', nargs='*', default=[])
    ap.add_argument('--upto', type=int, default=13); ap.add_argument('--window', type=int, nargs=2, default=[10, 12])
    ap.add_argument('--stable-seeds', nargs='*', default=[])
    a = ap.parse_args()
    st = trajectory(a.stable, range(90, 100))
    stable = {k: float(np.mean([v[k] for v in st.values()])) for k in KEYS}
    def dist(v): return {'share_car': abs(v['share_car'] - stable['share_car']), 'share_pt': abs(v['share_pt'] - stable['share_pt']),
                         'car_related': abs(v['car_related'] - stable['car_related']) / stable['car_related'],
                         'score': abs(v['score'] - stable['score']), 'unfinished_ratio': v['unfinished'] / max(stable['unfinished'], 1)}
    cold = trajectory(a.cold_traj, range(0, 80))
    cd = {k: dist(v) for k, v in cold.items()}
    smooth = {m: {k: float(np.mean([cd[j][m] for j in (k - 1, k, k + 1) if j in cd])) for k in cd} for m in ('share_car', 'share_pt', 'car_related', 'score')}
    res = {'stable': stable, 'window': a.window, 'seed_difference': {}, 'cold_trajectory': {k: {**cold[k], **{f'd_{m}': v for m, v in cd[k].items()}} for k in cd}, 'runs': {}}
    for spec in a.runs:
        name, run = spec.split('=', 1)
        tr = trajectory(run, range(0, a.upto)); d = {k: dist(v) for k, v in tr.items()}
        r = {'per_iteration': {k: {**tr[k], **{f'd_{m}': v for m, v in d[k].items()}} for k in tr}}
        last = [k for k in range(a.window[0], a.window[1] + 1) if k in d]
        if last:
            at12 = {m: float(np.mean([d[k][m] for k in last])) for m in ('share_car', 'share_pt', 'car_related', 'score', 'unfinished_ratio')}
            r['at_12'] = at12
            r['equivalent_cold_iteration'] = {m: next((k for k in sorted(smooth[m]) if smooth[m][k] <= at12[m]), '>79') for m in ('share_car', 'share_pt', 'car_related', 'score')}
        res['runs'][name] = r
        print(name, json.dumps({k: r.get(k) for k in ('at_12', 'equivalent_cold_iteration')}), flush=True)
    for spec in a.stable_seeds:
        name, run = spec.split('=', 1); o = trajectory(run, range(90, 100))
        res['seed_difference'][name] = dist({k: float(np.mean([v[k] for v in o.values()])) for k in KEYS})
        print('seed difference', name, json.dumps(res['seed_difference'][name]), flush=True)
    if a.final_pkl:
        city = np.load(a.city); res['cell_rmse'] = {}
        for spec in a.final_pkl:
            name, pkl = spec.split('=', 1); res['cell_rmse'][name] = cell_rmse(pkl, a.stable_pkl, city)
            print('cell rmse', name, res['cell_rmse'][name], flush=True)
    print('stable', stable)
    with open(a.out, 'w') as f: json.dump(res, f, indent=1, default=str)


if __name__ == '__main__':
    main()

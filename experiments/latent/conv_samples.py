#!/usr/bin/env python3
"""Samples for predicting the stable-state plan from a person's day (docs/converged-plan-plan.md, step 2).

  conv_samples.py --final DIR --city city.npz --cohorts COHORTS.csv.gz --out FILE.npz

One sample per sampled person (crc32 % 1000 < 128). Inputs, from the initial plans (DIR/cold.pkl) only:
- trip tokens (int, [n, T, 5]): origin and destination activity type, departure hour (0..29), origin and
  destination cell (city.npz grid; C = outside the used cells), padded with -1;
- trip features (float, [n, T, 3]): departure hours / 24, log1p(straight-line km), trip index / 10;
- the initial plan's main mode per trip (int, [n, T], -1 padded); subpopulation (0 man, 1 nonman, 2 outside);
  number of trips; related cohort flag; person group crc32 % 10.
Labels, from the selected plan of DIR/s{seed}-out.pkl (iteration 100) for seeds 4711-4713: main mode per trip
(int, [n, T]) and departure shift against the initial plan in quarter hours, clipped to -8..8 and stored as
0..16 (int, [n, T]); -1 where padded, missing or when the person's trip count differs from the initial plan.
Soft label for seed 4711: main-mode counts over the selected plans of iterations 80, 90 and 100 ([n, T, 8])."""
import argparse, csv, gzip, math, pickle, zlib
import numpy as np

MODES = ['car', 'taxi', 'FHV', 'pt', 'ride', 'bike', 'cb', 'walk']
ACTS = ['Home', 'Work', 'Secondary', 'School', 'University']
SUBPOPS = ['man', 'nonman', 'outside']
SEEDS = [4711, 4712, 4713]
T = 10


def act_id(t): return ACTS.index(t) if t in ACTS else len(ACTS)


def selected(ag): return next((p for p in ag['plans'] if p['selected']), ag['plans'][0])


def main():
    ap = argparse.ArgumentParser()
    for k in ('--final', '--city', '--cohorts', '--out'): ap.add_argument(k, required=True)
    a = ap.parse_args()
    city = np.load(a.city)
    x0, y0, size, nx, ny = city['grid']; ny = int(ny)
    index = {int(c): i for i, c in enumerate(city['cells'])}; C = len(index)
    cell = lambda x, y: index.get(int((x - x0) // size) * ny + int((y - y0) // size), C)
    with gzip.open(a.cohorts, 'rt') as f:
        related = {r['person_id']: r['charging_cohort'] == 'related' for r in csv.DictReader(f)}
    load = lambda name: pickle.load(open(f'{a.final}/{name}.pkl', 'rb'))
    cold = load('cold'); pids = sorted(cold)
    n = len(pids)
    tok = np.full((n, T, 5), -1, np.int16); x = np.zeros((n, T, 3), np.float32); init = np.full((n, T), -1, np.int8)
    sub = np.zeros(n, np.int8); ntrips = np.zeros(n, np.int8); rel = np.zeros(n, bool); grp = np.zeros(n, np.int8)
    dep0 = np.full((n, T), np.nan)
    for i, p in enumerate(pids):
        trips = selected(cold[p])['trips'][:T]
        for j, t in enumerate(trips):
            h = 0 if math.isnan(t[1]) else min(int(t[1] // 3600), 29)
            tok[i, j] = (act_id(t[6]), act_id(t[7]), h, cell(t[2], t[3]), cell(t[4], t[5]))
            km = math.hypot(t[4] - t[2], t[5] - t[3]) * 0.3048 / 1000
            x[i, j] = (0 if math.isnan(t[1]) else t[1] / 3600 / 24, math.log1p(km), j / 10)
            init[i, j] = MODES.index(t[0]); dep0[i, j] = t[1]
        s = cold[p]['subpop']; sub[i] = SUBPOPS.index(s) if s in SUBPOPS else 0
        ntrips[i] = len(trips); rel[i] = related.get(p, False); grp[i] = zlib.crc32(p.encode()) % 10
    out = {'tok': tok, 'x': x, 'init': init, 'sub': sub, 'ntrips': ntrips, 'related': rel, 'grp': grp, 'n_cells': np.array(C + 1)}

    def labels(snap):
        mode = np.full((n, T), -1, np.int8); shift = np.full((n, T), -1, np.int8); bad = 0
        for i, p in enumerate(pids):
            if p not in snap: bad += 1; continue
            trips = selected(snap[p])['trips'][:T]
            if len(trips) != ntrips[i]: bad += 1; continue
            for j, t in enumerate(trips):
                mode[i, j] = MODES.index(t[0])
                if not (math.isnan(t[1]) or math.isnan(dep0[i, j])):
                    shift[i, j] = int(np.clip(round((t[1] - dep0[i, j]) / 900), -8, 8)) + 8
        return mode, shift, bad

    for s in SEEDS:
        m, sh, bad = labels(load(f's{s}-out'))
        out[f'mode_{s}'], out[f'shift_{s}'] = m, sh
        print(f'seed {s}: persons without usable label {bad}', flush=True)
    soft = np.zeros((n, T, len(MODES)), np.float32)
    for it in ('it80', 'it90', 'out'):
        m, _, _ = labels(load(f's4711-{it}'))
        for k in range(len(MODES)): soft[..., k] += m == k
    out['soft_4711'] = soft
    np.savez_compressed(a.out, **out)
    valid = tok[..., 0] >= 0
    print(f'{n} persons, {valid.sum()} trips; label agreement 4711 vs 4712 '
          f'{np.mean((out["mode_4711"] == out["mode_4712"])[valid & (out["mode_4711"] >= 0) & (out["mode_4712"] >= 0)]):.3f}', flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Smoke test of policy_predict.py on synthetic inputs: test_policy_predict.py DIR, then run policy_predict.py on DIR."""
import csv, gzip, pickle, sys, zlib
from pathlib import Path
import numpy as np

d = Path(sys.argv[1]); (d / 'plans').mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(0)
pids = [str(i) for i in range(4000) if zlib.crc32(str(i).encode()) % 1000 < 128]
C = 20


def plan(car, score, sel):
    legs = {'car': 2, 'walk': 0} if car else {'pt': 2, 'walk': 4}
    cars = [(8 * 3600.0, int(rng.integers(0, 2)), {int(rng.integers(0, C)): [5, 120.0]}), (17 * 3600.0, 0, {3: [4, 90.0]})] if car else []
    return {'score': score, 'selected': sel, 'created': 0, 'sig': int(rng.integers(0, 1 << 30)), 'legs': legs, 'car': cars}


for seed in (4711, 4712, 4713):
    for scen, shift in (('baseline', 0), ('schema1', 1), ('schema2', 2)):
        its = ['it40', 'it50', 'it60', 'it70', 'it80', 'it90', 'out'] if scen == 'baseline' else ['it90', 'out']
        for it in its:
            ag = {}
            for p in pids:
                car_sel = rng.random() < 0.5 - 0.1 * shift
                ag[p] = {'subpop': 'man', 'plans': [plan(car_sel, 100 + rng.normal(), True), plan(not car_sel, 99 + rng.normal(), False)]}
            with open(d / 'plans' / f'{scen}-s{seed}-{it}.pkl', 'wb') as f: pickle.dump(ag, f)
        its = list(range(20, 100, 5))
        X = np.zeros((len(its), C, 30, 3), np.float32)
        X[..., 0] = np.log1p(rng.integers(0, 500, (len(its), C, 30))); X[..., 1] = 1 + X[..., 0] / 10; X[..., 2] = 1
        np.savez(d / f'city-{scen}-s{seed}.npz', X=X, states=np.array([f'{scen}-{seed}-{i}' for i in its]))
with gzip.open(d / 'cohorts.csv.gz', 'wt') as f:
    w = csv.writer(f); w.writerow(['person_id', 'charging_cohort'])
    for p in pids: w.writerow([p, 'related' if int(p) % 2 else 'unrelated'])
print(len(pids), 'agents written to', d)

#!/usr/bin/env python3
"""Smoke test: project full-baseline iteration 11 from iteration-10 travel times and iteration-11 plans."""
import pickle, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import dataset as S
SIM = Path('outputs/performance-20261004-171012-redundancy/full-baseline/simulation'); OUT = Path('outputs/surrogate-analysis')
t = time.time(); net = S.network(SIM/'BUILT.output_network.xml.zst'); print('network', len(net), round(time.time()-t), flush=True)
for i in (10, 11):
    f = OUT/f'baseline-state-{i}.pkl'
    if not f.exists():
        t = time.time(); st = S.road_state(SIM/f'ITERS/it.{i}/BUILT.{i}.events.xml.zst'); pickle.dump(st, open(f, 'wb')); print('state', i, round(time.time()-t), flush=True)
y10, legs10 = pickle.load(open(OUT/'baseline-state-10.pkl', 'rb')); y11, legs11 = pickle.load(open(OUT/'baseline-state-11.pkl', 'rb'))
t = time.time(); demand, plegs = S.project(SIM/'ITERS/it.11/BUILT.11.plans.xml.zst', net, y10); print('project', round(time.time()-t), flush=True)
pickle.dump((demand, plegs), open(OUT/'baseline-projection-11.pkl', 'wb'))

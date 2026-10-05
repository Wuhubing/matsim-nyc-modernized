#!/usr/bin/env python3
"""Oracle projections of full-baseline iteration 11 from its own link states: aggregation error alone."""
import pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import dataset as S, metrics as M
SIM = Path('outputs/performance-20261004-171012-redundancy/full-baseline/simulation'); O = Path('outputs/surrogate-analysis')
net = S.network(SIM/'BUILT.output_network.xml.zst')
for i in (10, 11):
    st = S.road_state(SIM/f'ITERS/it.{i}/BUILT.{i}.events.xml.zst'); pickle.dump(st, open(O/f'baseline-state-{i}.pkl', 'wb'))
y11, l11 = pickle.load(open(O/'baseline-state-11.pkl', 'rb')); g = S.geometric(y11)
for name, kw in [('mean', {}), ('mean_skip_last', {'skip_last': True}), ('geo', {'times': g}), ('geo_skip_last', {'times': g, 'skip_last': True})]:
    D, pl = S.project(SIM/'ITERS/it.11/BUILT.11.plans.xml.zst', net, y11, **kw)
    print('ORACLE', name, '| agent', M.fmt(M.agent_errors(l11, pl)), '| volume', M.fmt(M.link_errors(y11, dict(D))), flush=True)

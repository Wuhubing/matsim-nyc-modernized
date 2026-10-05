#!/usr/bin/env python3
"""Oracle projection accuracy vs time-bin width (geometric mean, end link excluded)."""
import pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import dataset as S, metrics as M
SIM = Path('outputs/performance-20261004-171012-redundancy/full-baseline/simulation'); O = Path('outputs/surrogate-analysis')
net = S.network(SIM/'BUILT.output_network.xml.zst'); _, l11 = pickle.load(open(O/'baseline-state-11.pkl', 'rb'))
for b in map(int, sys.argv[1:]):
    y = S.road_state(SIM/'ITERS/it.11/BUILT.11.events.xml.zst', b)[0]; pickle.dump(y, open(O/f'baseline-state-11-bin{b}.pkl', 'wb'))
    D, pl = S.project(SIM/'ITERS/it.11/BUILT.11.plans.xml.zst', net, y, times=S.geometric(y), skip_last=True, bin_seconds=b)
    print('ORACLE bin', b, '| agent', M.fmt(M.agent_errors(l11, pl)), flush=True)

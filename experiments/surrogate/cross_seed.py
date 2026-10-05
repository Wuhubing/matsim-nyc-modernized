#!/usr/bin/env python3
"""Held-out-run test of the L1 correction: train on seed-4712-r2 rows (iterations 1-6), test on seed-4713 iteration 6."""
import json, sys
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
sys.path.insert(0, str(Path(__file__).parent)); import agent_surrogate as A, dataset as S
O = Path('outputs/surrogate-analysis'); FB = Path('outputs/performance-20261004-171012-redundancy/full-baseline/simulation')
net = S.network(FB/'BUILT.output_network.xml.zst'); index = A.link_index(net)
(O/'seed4713').mkdir(exist_ok=True)
test = A.build(Path('outputs/surrogate-data-20261005/seed-4713/simulation'), O/'seed4713', [6], net, index)[6]
train = A.build(Path('outputs/surrogate-data-20261005/seed-4712-r2/simulation'), O/'seed4712r2', [1, 2, 3, 4, 5, 6], net, index)
Xtr = np.vstack([train[i][0] for i in train])[:, :7]; ytr = np.concatenate([train[i][1] for i in train])
model = HistGradientBoostingRegressor(max_iter=300, learning_rate=.1, max_leaf_nodes=63, random_state=0).fit(Xtr, np.log1p(ytr) - np.log1p(Xtr[:, 0]))
X, y = test; ch = X[:, 9] == 1; res = {}
for name, pred in [('psim_mean', X[:, 0]), ('learned_mean_base', np.expm1(model.predict(X[:, :7]) + np.log1p(X[:, 0])))]:
    res[name] = {'changed': A.errors(pred, y, ch), 'unchanged': A.errors(pred, y, ~ch)}
    print(name, ' | '.join(f"{g}: mae={v['mae']:.0f} med={v['median']:.0f} n={v['n']}" for g, v in res[name].items()), flush=True)
(O/'cross-seed.json').write_text(json.dumps(res, indent=2) + '\n')

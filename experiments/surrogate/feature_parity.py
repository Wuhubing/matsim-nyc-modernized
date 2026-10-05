#!/usr/bin/env python3
"""Write Python features (agent_surrogate.features, columns 0-6) for the first N persons of a plans file,
as the reference for NycPSim.features. Usage: SIM_DIR ROWS_DIR ITERATION N NETWORK"""
import itertools, pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import agent_surrogate as A, dataset as S
sim, out, i, n, network = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), Path(sys.argv[5])
net = S.network(network); index = A.link_index(net)
prev_links, prev_legs = pickle.load(open(out/f'state-{i-1}.pkl', 'rb'))
plans = next((sim/f'ITERS/it.{i}').glob('*.plans.xml.zst'))
wanted = {p for p, _ in itertools.islice(S.selected_plans(plans), n)}
full = S.selected_plans
S.selected_plans = lambda path: (x for x in full(path) if x[0] in wanted)   # restrict features() to the sample
rows = A.features(plans, net, index, prev_links, prev_legs, {}, {})
with open(out/f'feature-parity-{i}.csv', 'w') as f:
    for p, r in rows.items():
        f.write(p.decode() + ',' + ','.join(repr(float(v)) for v in r[:7]) + '\n')
print(len(rows))

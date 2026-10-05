#!/usr/bin/env python3
"""Noise floor: identical plans (full-baseline it.11), different seeds -> pure QSim stochasticity."""
import itertools, json, pickle, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import dataset as S, metrics as M
RUNS = Path('outputs/surrogate-data-20261005'); O = Path('outputs/surrogate-analysis')

def extract(seed):
    f = O/f'fixed-s{seed}-state.pkl'
    if not f.exists():
        pickle.dump(S.road_state(next((RUNS/f'fixed-s{seed}/simulation/ITERS/it.0').glob('*.events.xml.zst'))), open(f, 'wb'))
    return seed

if __name__ == '__main__':
    seeds = [4711, 1001, 1002]
    with ProcessPoolExecutor(3) as pool: list(pool.map(extract, seeds))
    st = {s: pickle.load(open(O/f'fixed-s{s}-state.pkl', 'rb')) for s in seeds}
    st['it11'] = pickle.load(open(O/'baseline-state-11.pkl', 'rb'))
    rows = {}
    for a, b in itertools.combinations(list(st), 2):
        (ya, la), (yb, lb) = st[a], st[b]
        r = {'link': M.link_errors(yb, {k: v[0] for k, v in ya.items()}, M.mean_time(ya)), 'agent': M.agent_errors(lb, la)}
        rows[f'{a}-vs-{b}'] = r; print(a, 'vs', b, '| link', M.fmt(r['link']), '| agent', M.fmt(r['agent']), flush=True)
    json.dump(rows, open(O/'noise-floor.json', 'w'), indent=2)

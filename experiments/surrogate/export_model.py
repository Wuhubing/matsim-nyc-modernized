#!/usr/bin/env python3
"""Train the PSim travel-time correction on agent rows and export it for NycPSim (Java).

Features (columns 0-6 of agent_surrogate rows, all computable during a PSim replay):
  psim_mean, psim_geo, free_flow (seconds), n_legs, n_links, first_dep_h, congested_share
Target: log1p(actual) - log1p(base), base = psim_mean (0) or psim_geo (1). Export format (text):
  line 1: 'base B'; line 2: baseline;  then per tree: 'tree N' followed by N lines 'feature threshold left right leaf value missing_left'.
A parity file with sample rows and Python predictions lets the Java evaluator be checked exactly.
Usage: export_model.py ROWS_DIR OUT_MODEL --iterations 1 2 3 4
"""
import argparse, pickle
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

COLS = [0, 1, 2, 3, 4, 5, 6]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('rows', type=Path); ap.add_argument('out', type=Path)
    ap.add_argument('--iterations', type=int, nargs='+', required=True)
    ap.add_argument('--base', choices=['mean', 'geo'], default='mean', help='PSim estimate the correction is relative to')
    a = ap.parse_args()
    data = [pickle.load(open(a.rows/f'agent-rows-{i}.pkl', 'rb')) for i in a.iterations]
    X = np.vstack([d[0] for d in data])[:, COLS]; y = np.concatenate([d[1] for d in data])
    model = HistGradientBoostingRegressor(max_iter=300, learning_rate=.1, max_leaf_nodes=63, random_state=0)
    b = 0 if a.base == 'mean' else 1
    model.fit(X, np.log1p(y) - np.log1p(X[:, b]))
    lines = [f'base {b}', repr(float(np.ravel(model._baseline_prediction)[0]))]
    for predictors in model._predictors:
        nodes = predictors[0].nodes
        lines.append(f'tree {len(nodes)}')
        for n in nodes:
            lines.append(' '.join([str(int(n['feature_idx'])), repr(float(n['num_threshold'])), str(int(n['left'])), str(int(n['right'])),
                                   str(int(n['is_leaf'])), repr(float(n['value'])), str(int(n['missing_go_to_left']))]))
    a.out.write_text('\n'.join(lines) + '\n')
    rng = np.random.default_rng(0); idx = rng.choice(len(X), 2000, replace=False)
    raw = model.predict(X[idx])
    with open(a.out.with_suffix('.parity.csv'), 'w') as f:
        for row, p in zip(X[idx], raw):
            f.write(','.join(repr(float(v)) for v in row) + ',' + repr(float(p)) + '\n')
    print('trees', len(model._predictors), 'rows', len(y), 'base', b, 'baseline', lines[1])


if __name__ == '__main__':
    main()

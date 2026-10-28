#!/usr/bin/env python3
"""Gradient-boosting reference without any cell information (docs/converged-plan-plan.md, section 2).

  conv_gbt.py SAMPLES.npz --out DIR

Per trip: subpopulation, origin and destination activity, departure hour, log1p straight-line km, trip index,
number of trips; 'gbt+init' adds the initial plan's mode. Trained on seed 4711's labels of persons with
crc32 % 10 >= 2; writes the mode probabilities of every trip as DIR/gbt.npz and DIR/gbt_init.npz (P [n, T, 8]),
to be scored by train_conv.py --extern."""
import argparse
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

M = 8


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('samples'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    D = np.load(a.samples); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    tok, x, n, T = D['tok'], D['x'], *D['tok'].shape[:2]
    valid = tok[..., 0] >= 0
    base = np.stack([np.broadcast_to(D['sub'][:, None], (n, T)), tok[..., 0], tok[..., 1], tok[..., 2], x[..., 1],
                     x[..., 2] * 10, np.broadcast_to(D['ntrips'][:, None], (n, T))], -1).astype(np.float32)
    lab = D['mode_4711']; train = valid & (lab >= 0) & (D['grp'] >= 2)[:, None]
    for name, F, cat in (('gbt', base, [0, 1, 2]), ('gbt_init', np.concatenate([base, D['init'][..., None]], -1), [0, 1, 2, 7])):
        mask = np.zeros(F.shape[-1], bool); mask[cat] = True
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, categorical_features=mask, random_state=0)
        clf.fit(F[train], lab[train])
        P = np.full((n, T, M), 1 / M, np.float32)
        pr = np.zeros((valid.sum(), M), np.float32); pr[:, clf.classes_] = clf.predict_proba(F[valid])
        P[valid] = pr
        np.savez_compressed(out / f'{name}.npz', P=P)
        print(name, 'trained on', int(train.sum()), 'trips', flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""A2: if innovation were switched off at snapshot k and everyone played their best stored plan, how close would the
mode split be to the final state? (docs/aggregate-regularity-plan.md Section 5, method M2)

  best_state.py SNAPDIR [SNAPDIR ...] --out FILE.json [--final output] [--ks 0,10,...,90]

SNAPDIR: output of plan_snapshots.py for one run. Per run and snapshot k, overall and by subpopulation
(trip-weighted main-mode shares):
- tv_sel, tv_best: total variation distance (half the L1 distance, in percentage points) between the shares of the
  selected plans, resp. the best stored plans, at k and the selected plans of the final state;
- max_sel, max_best: largest single-mode difference (pp), and the mode;
- same_vector: persons whose best-plan trips-per-mode vector at k equals their final selected one;
- best_score: mean best stored score at k; final_score: mean stored score of the final selected plans.
Seed noise: tv between the final states of different runs (pairwise max), the scale below which a difference
cannot be told apart from seed noise. Gate (plan Section 5): tv_best <= 1 pp at some k well before 79."""
import argparse, itertools, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_snapshots import MODES


def load(d, k):
    z = np.load(Path(d)/f'snap-{k}.npz'); return {n: z[n] for n in z.files}


def shares(counts, mask):
    c = counts[mask].sum(axis=0).astype(float); return c / c.sum() if c.sum() else c


def compare(a, b):
    diff = (a - b) * 100; j = int(np.argmax(np.abs(diff)))
    return float(np.abs(diff).sum() / 2), float(diff[j]), MODES[j]


def align(snap, ids):
    """Reorder a snapshot's per-person arrays to the person order ids (snapshots normally share it)."""
    if len(snap['id']) == len(ids) and np.array_equal(snap['id'], ids): return snap
    pos = {p: i for i, p in enumerate(snap['id'])}; order = np.array([pos[p] for p in ids])
    return {n: (v[order] if n != 'id' else ids) for n, v in snap.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('snapdirs', nargs='+'); ap.add_argument('--out', required=True)
    ap.add_argument('--final', default='output'); ap.add_argument('--ks', default='0,10,20,30,40,50,60,70,80,90')
    a = ap.parse_args(); ks = a.ks.split(',')
    out = {'final': a.final, 'modes': MODES, 'runs': {}}; finals = []
    for d in a.snapdirs:
        persons = np.load(Path(d)/'persons.npz'); ids = persons['id']; sub = persons['subpopulation']
        groups = {'all': np.ones(len(ids), bool), **{s: sub == s for s in sorted(set(sub))}}
        fin = align(load(d, a.final), ids); finals.append({g: shares(fin['sel'], m) for g, m in groups.items()})
        run = {'final_shares': {g: v.tolist() for g, v in finals[-1].items()}, 'by_k': {}}
        for k in ks:
            s = align(load(d, k), ids); row = {}
            for g, m in groups.items():
                tv_s, max_s, mode_s = compare(shares(s['sel'], m), finals[-1][g])
                tv_b, max_b, mode_b = compare(shares(s['best'], m), finals[-1][g])
                row[g] = {'tv_sel': tv_s, 'max_sel': max_s, 'max_sel_mode': mode_s, 'tv_best': tv_b, 'max_best': max_b,
                          'max_best_mode': mode_b, 'best_shares': shares(s['best'], m).tolist(),
                          'same_vector': float(np.mean(np.all(s['best'][m] == fin['sel'][m], axis=1))),
                          'best_score': float(np.nanmean(s['best_score'][m])), 'final_score': float(np.nanmean(fin['sel_score'][m]))}
            run['by_k'][k] = row
        out['runs'][d] = run
    out['seed_noise_tv'] = {g: max((compare(x[g], y[g])[0] for x, y in itertools.combinations(finals, 2)), default=float('nan'))
                            for g in finals[0]}
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    print('seed noise (max pairwise tv of final states, pp): ' + ' '.join(f'{g} {v:.2f}' for g, v in out['seed_noise_tv'].items()))
    print(f"{'k':>6} {'group':8} {'tv_sel':>7} {'tv_best':>7} {'max_best':>16} {'same':>6} {'best_sc':>8} {'final_sc':>8}   (mean over runs)")
    for k in ks:
        for g in finals[0]:
            rs = [r['by_k'][k][g] for r in out['runs'].values()]
            mb = rs[0]['max_best_mode']
            print(f"{k:>6} {g:8} {np.mean([r['tv_sel'] for r in rs]):7.2f} {np.mean([r['tv_best'] for r in rs]):7.2f} "
                  f"{np.mean([r['max_best'] for r in rs]):+8.2f} ({mb:5}) {np.mean([r['same_vector'] for r in rs]):6.3f} "
                  f"{np.mean([r['best_score'] for r in rs]):8.2f} {np.mean([r['final_score'] for r in rs]):8.2f}")


if __name__ == '__main__':
    main()

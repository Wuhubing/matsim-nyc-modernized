#!/usr/bin/env python3
"""How well can each agent's final plan be predicted from the state at iteration k (0 = initial plans)?
Upper bound for a 'jump' that writes predicted plans into the plan memory at k and lets MATSim finish.

  final_from_early.py SNAPDIR_S4711 SNAPDIR_S4712 SNAPDIR_S4713 --cohorts COHORTS.csv.gz --out FILE.json
                      [--ks 0,10,20,30,40] [--limit N]

Inputs are the per-person snapshot summaries of experiments/l2seg/plan_snapshots.py (snap-K.npz, persons.npz):
trips per main mode (MODES order) of the selected and of the best-scored plan. Target: trips per main mode of the
selected plan in snap-output (state after the last iteration). Predictors at k:
- sel: the selected plan at k; best: the best-scored stored plan at k (A2's state, per person);
- learned: gradient boosting per mode on person attributes + state at k, trained on another seed of the same
  scenario (train s -> test s+1). Same-scenario transfer is an upper bound; transfer to a policy needs policy runs;
- other_seed: the other seed's final plan, i.e. what randomness alone leaves (no predictor beats this by much).
Metrics: share of persons whose whole mode vector is right ('exact'); trip-weighted overlap sum_m min(p_m, f_m) /
trips; car use right (p_car > 0 == f_car > 0); aggregate total-variation distance of mode shares in percentage points,
overall and per subpopulation and charging cohort."""
import argparse, json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'l2seg'))
from plan_snapshots import MODES  # noqa: E402

SUBPOPS = ('man', 'nonman', 'outside')


def load(snapdir, ks, limit=None):
    d = Path(snapdir)
    p = np.load(d / 'persons.npz', allow_pickle=True)
    order = np.argsort(p['id'], kind='stable')
    if limit:  # same positions in id order for every seed
        order = order[np.sort(np.random.default_rng(0).choice(len(order), limit, replace=False))]
    persons = {k: p[k][order] for k in p.files}
    snaps = {}
    for k in list(ks) + ['output']:
        s = np.load(d / f'snap-{k}.npz', allow_pickle=True)
        idx = np.argsort(s['id'], kind='stable')[:len(order)] if limit is None else None
        if limit:
            pos = {v: i for i, v in enumerate(s['id'])}; idx = np.array([pos[v] for v in persons['id']])
        snap = {f: s[f][idx] for f in s.files}
        if not np.array_equal(snap['id'], persons['id']): raise SystemExit(f'{d}: person order differs in snap-{k}')
        snaps[k] = snap
    return persons, snaps


def features(persons, snap):
    sub = np.stack([(persons['subpopulation'] == s).astype(float) for s in SUBPOPS], 1)
    num = np.stack([persons[c] for c in ('home_x', 'home_y', 'prim_x', 'prim_y', 'departure')] +
                   [persons['trips'].astype(float), snap['sel_score'], snap['best_score'], snap['plans'].astype(float)], 1)
    return np.hstack([sub, num, snap['sel'].astype(float), snap['best'].astype(float)])


def to_counts(pred, trips):
    """Continuous per-mode predictions -> integer trips per mode summing to the person's trips (largest remainder)."""
    x = np.clip(pred, 0, None)
    tot = x.sum(1, keepdims=True); tot[tot == 0] = 1
    x = x / tot * trips[:, None]
    base = np.floor(x).astype(int); rem = x - base
    short = trips - base.sum(1)
    order = np.argsort(-rem, 1)
    for i in np.nonzero(short > 0)[0]:
        base[i, order[i, :short[i]]] += 1
    return base


def learned(train_p, train_s, test_p, test_s, k):
    from sklearn.ensemble import HistGradientBoostingRegressor
    Xtr, Xte = features(train_p, train_s[k]), features(test_p, test_s[k])
    # Constant or all-missing columns (e.g. best_score at k = 0, before any execution) break the binning.
    keep = [j for j in range(Xtr.shape[1]) if len(np.unique(Xtr[np.isfinite(Xtr[:, j]), j])) > 1]
    Xtr, Xte = Xtr[:, keep], Xte[:, keep]
    Ytr = train_s['output']['sel'].astype(float)
    out = np.zeros((len(Xte), len(MODES)))
    for m in range(len(MODES)):
        reg = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, max_leaf_nodes=63, random_state=0)
        out[:, m] = reg.fit(Xtr, Ytr[:, m]).predict(Xte)
    return out


def tv(pred, final, mask):
    a, b = pred[mask].sum(0), final[mask].sum(0)
    if a.sum() == 0 or b.sum() == 0: return float('nan')
    return float(50 * np.abs(a / a.sum() - b / b.sum()).sum())


def metrics(pred_counts, pred_cont, final, groups):
    trips = final.sum(1); ok = trips > 0
    r = {'exact': float(np.mean(np.all(pred_counts[ok] == final[ok], 1))),
         'overlap': float(np.minimum(pred_counts[ok], final[ok]).sum() / final[ok].sum()),
         'car_use': float(np.mean((pred_counts[ok, 0] > 0) == (final[ok, 0] > 0)))}
    for name, mask in groups.items():
        r[f'tv_{name}'] = tv(pred_cont, final, mask & ok)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('snapdirs', nargs=3)
    ap.add_argument('--cohorts', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--ks', default='0,10,20,30,40')
    ap.add_argument('--limit', type=int)
    a = ap.parse_args()
    ks = [int(x) for x in a.ks.split(',')]
    runs = [load(d, ks, a.limit) for d in a.snapdirs]
    ids = runs[0][0]['id']
    for p, _ in runs[1:]:
        if not np.array_equal(p['id'], ids): raise SystemExit('person sets differ between seeds')
    import csv, gzip
    with gzip.open(a.cohorts, 'rt') as f:
        coh = {row['person_id']: row['charging_cohort'] for row in csv.DictReader(f)}
    cohort = np.array([coh.get(i, 'unknown') for i in ids])
    sub = runs[0][0]['subpopulation']
    groups = {'all': np.ones(len(ids), bool), **{s: sub == s for s in SUBPOPS},
              'related': cohort == 'related', 'unrelated': cohort == 'unrelated'}
    print(f'persons {len(ids)}; cohort sizes', {g: int(m.sum()) for g, m in groups.items()}, flush=True)

    res = {'n': len(ids), 'modes': MODES, 'ks': ks, 'results': []}
    n = len(runs)
    for t in range(n):
        test_p, test_s = runs[t]; train_p, train_s = runs[(t + 1) % n]
        final = test_s['output']['sel'].astype(int); trips = final.sum(1)
        other = runs[(t + 1) % n][1]['output']['sel'].astype(int)
        row = {'test_seed_index': t, 'train_seed_index': (t + 1) % n,
               'other_seed': metrics(other, other.astype(float), final, groups), 'by_k': {}}
        for k in ks:
            s = test_s[k]
            byk = {'sel': metrics(s['sel'].astype(int), s['sel'].astype(float), final, groups),
                   'best': metrics(s['best'].astype(int), s['best'].astype(float), final, groups)}
            cont = learned(train_p, train_s, test_p, test_s, k)
            byk['learned'] = metrics(to_counts(cont, trips), cont, final, groups)
            row['by_k'][k] = byk
            print(f'test {t} k={k}: ' + '; '.join(f"{m} exact {v['exact']:.3f} overlap {v['overlap']:.3f} "
                  f"tv {v['tv_all']:.2f}pp" for m, v in byk.items()), flush=True)
        print(f"test {t} other_seed: exact {row['other_seed']['exact']:.3f} overlap {row['other_seed']['overlap']:.3f} "
              f"tv {row['other_seed']['tv_all']:.2f}pp", flush=True)
        res['results'].append(row)
    Path(a.out).write_text(json.dumps(res, indent=1))
    print('wrote', a.out)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""RQ1: can unresolved agents (L-H) and useful innovations (L-U) be predicted from information available during the run?

  predict.py --train RUN [RUN ...] --test RUN --out DIR [--horizon 10] [--delta 0] [--iterations 2,5,10,...]

L-H sample: every agent of an innovating subpopulation at the end of iteration t (features at t), label = its final
plan was created after t. L-U sample: every innovation at iteration t (features at t-1, i.e. before it), label as in
labels.py. Model: scikit-learn HistGradientBoostingClassifier, trained on the train runs, evaluated on the test run.
Reported per test iteration: positive share, ROC AUC, and recall (L-H) or precision (L-U) when the top 30% of
agents by predicted probability are selected, against random selection and the rule "largest gap to the best
stored score". Writes DIR/rq1-predict.json and prints a summary."""
import argparse, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import labels, features
from logs import ReplanningLog
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

NUMERIC = ['plans', 'executed_minus_best', 'age', 'switches_last5', 'innovations_last5', 'score_change', 'executed',
           'travel_seconds', 'travel_change', 'choice_changed']
CATEGORICAL = ['subpopulation', 'cohort']
BUDGET = 0.3


def load_run(run, horizon, delta):
    log = ReplanningLog(run); its, d = labels.load(log)
    lh = labels.label_lh(d['created'])
    innovating = np.isin(log.subpopulation, sorted(set(log.subpopulation[d['innovated'].any(axis=0)])))
    lu_t, lu_row, lu = labels.label_lu(d, horizon, delta)
    return {'run': run, 'log': log, 'its': its, 'd': d, 'lh': lh, 'innovating': innovating, 'lu': (lu_t, lu_row, lu)}


def matrix(r, t_i, rows, codes):
    f = features.features(r['log'], r['d'], r['its'], t_i, r['run'])
    f['executed'] = r['d']['executed'][t_i]
    cols = []
    for k in NUMERIC: cols.append(np.asarray(f.get(k, np.full(len(r['log'].index), np.nan)), dtype=float)[rows])
    for k in CATEGORICAL:
        v = np.asarray(f.get(k, np.full(len(r['log'].index), '', dtype=object))).astype(str)[rows]
        m = codes.setdefault(k, {})
        uniq, inv = np.unique(v, return_inverse=True)
        cols.append(np.array([m.setdefault(u, len(m)) for u in uniq], dtype=float)[inv])
    return np.column_stack(cols)


def lh_data(r, t_values, codes):
    rows = np.nonzero(r['innovating'])[0]; X, y, it = [], [], []
    for t in t_values:
        X.append(matrix(r, t, rows, codes)); y.append(r['lh'][t, rows]); it.append(np.full(len(rows), t))
    return np.vstack(X), np.concatenate(y), np.concatenate(it), rows


def lu_data(r, t_values, codes):
    lu_t, lu_row, lu = r['lu']; X, y, it = [], [], []
    for t in t_values:
        sel = lu_t == t
        if not sel.any() or t == 0: continue
        X.append(matrix(r, t - 1, lu_row[sel], codes)); y.append(lu[sel]); it.append(np.full(sel.sum(), t))
    return np.vstack(X), np.concatenate(y), np.concatenate(it)


def top_share(score, k):
    order = np.argsort(-score, kind='stable'); top = np.zeros(len(score), bool); top[order[:k]] = True; return top


def evaluate(model, X, y, it, gap_col):
    out = {}
    p = model.predict_proba(X)[:, 1]
    for t in sorted(set(it.tolist())):
        s = it == t; yt = y[s]; n = s.sum(); k = int(round(BUDGET * n))
        if yt.all() or not yt.any(): out[int(t)] = {'n': int(n), 'positive_share': float(yt.mean())}; continue
        top_m = top_share(p[s], k); top_g = top_share(-X[s, gap_col], k)   # gap = executed - best <= 0; most negative first
        out[int(t)] = {'n': int(n), 'positive_share': float(yt.mean()), 'auc_model': float(roc_auc_score(yt, p[s])),
                       'auc_gap_rule': float(roc_auc_score(yt, -X[s, gap_col])),
                       'recall_top30_model': float(yt[top_m].sum() / yt.sum()), 'recall_top30_gap': float(yt[top_g].sum() / yt.sum()),
                       'recall_top30_random': BUDGET * 1.0,
                       'precision_top30_model': float(yt[top_m].mean()), 'precision_top30_gap': float(yt[top_g].mean())}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--train', nargs='+', required=True); ap.add_argument('--test', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--horizon', type=int, default=10); ap.add_argument('--delta', type=float, default=0.0)
    ap.add_argument('--iterations', default='2,5,10,15,20,30,40,50,60,70,78')
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    t_values = [int(x) for x in a.iterations.split(',')]
    codes = {}; gap_col = NUMERIC.index('executed_minus_best')
    result = {'train': a.train, 'test': a.test, 'iterations': t_values, 'horizon': a.horizon, 'delta': a.delta, 'budget': BUDGET,
              'features': NUMERIC + CATEGORICAL}
    for task in ('L-H', 'L-U'):
        Xs, ys = [], []
        for run in a.train:
            r = load_run(run, a.horizon, a.delta)
            X, y, _ = (lh_data(r, t_values, codes)[:3] if task == 'L-H' else lu_data(r, t_values, codes))
            Xs.append(X); ys.append(y); del r
        Xtr = np.vstack(Xs); ytr = np.concatenate(ys); del Xs, ys
        # Drop columns that carry no information in training (all NaN or constant, e.g. no ResearchMetrics in the run).
        keep = [j for j in range(Xtr.shape[1]) if np.isfinite(Xtr[:, j]).any() and np.unique(Xtr[np.isfinite(Xtr[:, j]), j]).size > 1]
        names = (NUMERIC + CATEGORICAL); cat = [i for i, j in enumerate(keep) if j >= len(NUMERIC)]
        result.setdefault('features_used', {})[task] = [names[j] for j in keep]
        model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, categorical_features=cat or None, random_state=0)
        model.fit(Xtr[:, keep], ytr); del Xtr, ytr
        r = load_run(a.test, a.horizon, a.delta)
        X, y, it = (lh_data(r, t_values, codes)[:3] if task == 'L-H' else lu_data(r, t_values, codes))
        result[task] = evaluate(model, X[:, keep], y, it, keep.index(gap_col))
        if task == 'L-H':
            result['stability'] = {int(t): {'unresolved': float(r['lh'][t, r['innovating']].mean()),
                                            'innovated': float(r['d']['innovated'][t, r['innovating']].mean())} for t in range(len(r['its']))}
            lu_t, _, lu = r['lu']
            result['lu_positive_rate_by_iteration'] = {int(t): float(lu[lu_t == t].mean()) for t in sorted(set(lu_t.tolist()))}
        del r
        print(task)
        for t, v in result[task].items():
            if 'auc_model' in v:
                print(f"  it {t:3d} n {v['n']:7d} pos {v['positive_share']:.3f} AUC model {v['auc_model']:.3f} gap {v['auc_gap_rule']:.3f} | "
                      f"top30% recall model {v['recall_top30_model']:.3f} gap {v['recall_top30_gap']:.3f} random 0.300 | precision model {v['precision_top30_model']:.3f}")
    (out/'rq1-predict.json').write_text(json.dumps(result, indent=1) + '\n')


if __name__ == '__main__':
    main()

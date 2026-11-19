#!/usr/bin/env python3
"""Can a cheap predictor tell, before the mobsim, whether an innovation will be worse than the agent's best plan?
Offline check for H1 of docs/research-charter.md (pre-evaluate proposals, execute only the promising ones).

  proposal_predictor.py RUN --persons SNAPDIR/persons.npz --out FILE.json [--ks 10,20,30,40,50,60,70] [--jobs 7]

Innovations at snapshot iteration k (new plan created at k; it is executed at k). Outcome, from the W1 log:
    delta = executed score at k - best stored score at k-1   (first evaluation relative to the agent's best).
Predictors of delta, all available before the mobsim of k:
- parent: score of the stored plan that was copied and mutated, minus best (RandomPlanSelector picks any stored plan);
- self: best stored score among the agent's plans with the same per-trip main modes as the new plan, minus best
  (nan when none: coverage reported);
- group: mean delta of earlier innovations (snapshots < k) with the same change key in the same group, with
  fallbacks; group = subpopulation x 6 km home cell x 6 km primary-activity cell; change key = strategy kind, and for
  mode innovations the first changed trip (from -> to main mode);
- combined: least squares on earlier snapshots of delta on [parent, group, self (0 if none), has self].
Reported per k and pooled over k >= 20 (group and combined need earlier data), per strategy kind: coverage,
Spearman(pred, delta), AUC for delta > 0, and filters that skip the lowest q of predictions (q = 0.3, 0.5, 0.7):
share of better-at-once innovations kept and share of clearly worse ones (delta < -3) skipped."""
import argparse, json, sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from logs import ReplanningLog
from innovation_outcomes import kinds
from plans_stats import stream
from plan_snapshots import snapshot_path
from proposal_success import trip_main_modes

CELL = 6 * 3280.84          # 6 km in EPSG:2263 feet
RESIDENTS = ('man', 'nonman')


def attr(p, name):
    a = p.find(f"attributes/attribute[@name='{name}']")
    return None if a is None else a.text


def parse(job):
    """{person_id: (parent score, best score among same-signature stored plans or nan, change key)} at k."""
    run, k, want = job; out = {}
    with stream(snapshot_path(run, k)) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            w = want.get(el.get('id'))
            if w is not None:
                parent_id, kind = w; new = par = None; stored = []
                for p in el.findall('plan'):
                    pid, cr, sc = attr(p, 'planId'), attr(p, 'iterationCreated'), p.get('score')
                    is_new = pid is not None and int(pid, 36) == parent_id and cr is not None and int(cr) == k
                    if is_new: new = p; continue
                    if sc is None: continue
                    modes = tuple(trip_main_modes(p)); stored.append((float(sc), modes))
                    if pid is not None and int(pid, 36) == parent_id: par = (float(sc), modes)
                if new is not None and par is not None:
                    nm = tuple(trip_main_modes(new)); same = [s for s, m in stored if m == nm]
                    key = kind
                    if kind == 'mode':
                        ch = [(a, b) for a, b in zip(par[1], nm) if a != b]
                        key = f'mode:{ch[0][0]}->{ch[0][1]}' if ch and len(nm) == len(par[1]) else 'mode:other'
                    out[el.get('id')] = (par[0], max(same) if same else np.nan, key)
            root.remove(el)
    return k, out


def auc(score, label):
    ok = np.isfinite(score); s, y = score[ok], label[ok]
    if y.all() or not y.any(): return float('nan')
    r = np.argsort(np.argsort(s)) + 1.0
    return float((r[y].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (~y).sum()))


def spearman(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3: return float('nan')
    return float(np.corrcoef(np.argsort(np.argsort(x[ok])), np.argsort(np.argsort(y[ok])))[0, 1])


def evaluate(pred, delta):
    ok = np.isfinite(pred); res = {'n': int(len(delta)), 'coverage': float(ok.mean()) if len(delta) else float('nan')}
    p, d = pred[ok], delta[ok]
    res.update({'spearman': spearman(p, d), 'auc_better': auc(p, d > 0)})
    better, worse = d > 0, d < -3
    for q in (0.3, 0.5, 0.7):
        keep = p > np.quantile(p, q) if len(p) else p.astype(bool)
        res[f'skip{int(q*100)}'] = {'better_kept': float(keep[better].mean()) if better.any() else float('nan'),
                                    'worse_skipped': float((~keep)[worse].mean()) if worse.any() else float('nan')}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--persons', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--ks', default='10,20,30,40,50,60,70'); ap.add_argument('--jobs', type=int, default=1)
    a = ap.parse_args(); ks = [int(x) for x in a.ks.split(',')]
    log = ReplanningLog(a.run); kind = kinds(log)
    P = dict(np.load(a.persons)); prow = {p: i for i, p in enumerate(P['id'])}
    def group(pid):
        i = prow[pid]; c = lambda v: -1 if not np.isfinite(v) else int(v // CELL)
        return (str(P['subpopulation'][i]), c(P['home_x'][i]), c(P['home_y'][i]), c(P['prim_x'][i]), c(P['prim_y'][i]))
    rows = {}; jobs = []
    for k in ks:
        ag, prev = log.agents(k), log.agents(k - 1)
        idx = np.nonzero(ag['innovated'] & (ag['created'] == k) & np.isin(log.subpopulation, RESIDENTS))[0]
        rows[k] = {log.person_id[i]: (float(ag['executed'][i]), float(prev['best'][i]), kind.get(int(ag['strategy'][i]), 'select')) for i in idx}
        jobs.append((a.run, k, {log.person_id[i]: (int(ag['parent'][i]), rows[k][log.person_id[i]][2]) for i in idx}))
    with Pool(a.jobs) as pool: parsed = dict(pool.map(parse, jobs))
    print('parsed: ' + ', '.join(f'k={k} {len(v)}/{len(rows[k])}' for k, v in parsed.items()), flush=True)

    # per k arrays
    D = {}
    for k in ks:
        ids = [p for p in parsed[k] if np.isfinite(rows[k][p][0]) and np.isfinite(rows[k][p][1])]
        ex = np.array([rows[k][p][0] for p in ids]); be = np.array([rows[k][p][1] for p in ids])
        D[k] = {'id': ids, 'kind': np.array([rows[k][p][2] for p in ids]), 'key': np.array([parsed[k][p][2] for p in ids]),
                'delta': ex - be, 'parent': np.array([parsed[k][p][0] for p in ids]) - be,
                'self': np.array([parsed[k][p][1] for p in ids]) - be, 'grp': [group(p) for p in ids]}
    # group predictor and combined model, trained on earlier snapshots only
    for j, k in enumerate(ks):
        tr = ks[:j]; g = np.full(len(D[k]['id']), np.nan); D[k]['group'] = g; D[k]['combined'] = np.full_like(g, np.nan)
        if not tr: continue
        fine, mid, top = defaultdict(list), defaultdict(list), defaultdict(list)
        for t in tr:
            for gr, key, d in zip(D[t]['grp'], D[t]['key'], D[t]['delta']):
                fine[(gr, key)].append(d); mid[(gr[0], key)].append(d); top[key].append(d)
        for i, (gr, key) in enumerate(zip(D[k]['grp'], D[k]['key'])):
            for tab, kk in ((fine, (gr, key)), (mid, (gr[0], key)), (top, key)):
                v = tab.get(kk)
                if v is not None and len(v) >= 20: g[i] = float(np.mean(v)); break
        def feats(t):
            s = D[t]['self']; has = np.isfinite(s)
            return np.column_stack([np.ones(len(s)), D[t]['parent'], D[t]['group'], np.where(has, s, 0.0), has])
        Xs, ys = [], []
        for t in tr:
            if np.isfinite(D[t]['group']).any():
                X = feats(t); ok = np.isfinite(X).all(axis=1); Xs.append(X[ok]); ys.append(D[t]['delta'][ok])
        if Xs:
            beta = np.linalg.lstsq(np.vstack(Xs), np.concatenate(ys), rcond=None)[0]
            X = feats(k); ok = np.isfinite(X).all(axis=1); D[k]['combined'][ok] = X[ok] @ beta; D[k]['beta'] = beta.tolist()

    preds = ('parent', 'self', 'group', 'combined'); out = {'run': a.run, 'by_k': {}, 'pooled_k20plus': {}}
    for k in ks:
        out['by_k'][k] = {kd: {'n': int((D[k]['kind'] == kd).sum()), 'better_share': float((D[k]['delta'][D[k]['kind'] == kd] > 0).mean()),
                               'worse3_share': float((D[k]['delta'][D[k]['kind'] == kd] < -3).mean()),
                               **{pr: evaluate(D[k][pr][D[k]['kind'] == kd], D[k]['delta'][D[k]['kind'] == kd]) for pr in preds}}
                          for kd in ('mode', 'route', 'time') if (D[k]['kind'] == kd).any()}
        if 'beta' in D[k]: out['by_k'][k]['combined_beta'] = D[k]['beta']
    late = [k for k in ks if k >= 20]
    for kd in ('mode', 'route', 'time', 'all'):
        sel = lambda k: np.ones(len(D[k]['id']), bool) if kd == 'all' else D[k]['kind'] == kd
        dl = np.concatenate([D[k]['delta'][sel(k)] for k in late])
        out['pooled_k20plus'][kd] = {'n': int(len(dl)), 'better_share': float((dl > 0).mean()), 'worse3_share': float((dl < -3).mean()),
                                     **{pr: evaluate(np.concatenate([D[k][pr][sel(k)] for k in late]), dl) for pr in preds}}
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    print('\npooled k>=20: kind  n  better  worse<-3 | predictor: coverage spearman AUC | skip 50%: better kept / worse skipped')
    for kd, r in out['pooled_k20plus'].items():
        print(f"{kd:6} {r['n']:7d} {r['better_share']:.3f} {r['worse3_share']:.3f}")
        for pr in preds:
            e = r[pr]; s = e['skip50']
            print(f"    {pr:9} {e['coverage']:.2f} {e['spearman']:+.3f} {e['auc_better']:.3f} | {s['better_kept']:.3f} / {s['worse_skipped']:.3f}")


if __name__ == '__main__':
    main()

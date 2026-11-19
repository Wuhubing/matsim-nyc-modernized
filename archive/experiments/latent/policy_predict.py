#!/usr/bin/env python3
"""Predict a held-out toll schema's effects from the baseline run (docs/policy-prediction-plan.md, step 3).

  policy_predict.py --dir POLICY_DIR --cohorts COHORTS.csv.gz --train schema1 --test schema2 --out FILE.json

Inputs in POLICY_DIR: plans/{scenario}-s{seed}-{it}.pkl (policy_extract.py) and city-{scenario}-s{seed}.npz
(city_tensor.py, iterations 20..95). Same sampled agents everywhere (crc32 % 1000 < 128).

Truth per agent and scenario: leg counts of the selected plan, mean of snapshot 90 and the output plans.
Effects: legs_car_charging:related (scaled by 1000/128 to the simulated population), share_car, share_pt (all
sampled agents); Delta = scenario - baseline of the same seed. Methods, each giving per agent the expected change
of car, pt and all legs:
- zero; linear: training Delta x peak price ratio;
- I-0: logit over the baseline final pool (output plans), score - money utility x toll, change = P_policy - P_base;
- I-0u: same over the union of the baseline pools of snapshots 40..90 and output (latest score per choice signature);
- I-1: I-0u plus congestion feedback: car link entries per cell and hour change with the expected plan change
  (x 1000/128), a gradient-boosted congestion model (trained on baseline and training-schema states only) gives
  the new congestion ratio, car legs gain or lose free-flow seconds x ratio change, scored at the performing rate;
  iterated with step 1/n to a fixed point;
- D: gradient-boosted regression per agent of the changes, trained on the training schema (3 seeds);
- D+I: D with the I-1 changes as features.
The I methods have one parameter, the logit scale beta (MATSim: 1), fitted on the training schema to its
related-car Delta (grid), and reported both fitted and at 1."""
import argparse, csv, gzip, json, math, pickle
from collections import defaultdict
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

SEEDS = [4711, 4712, 4713]
PEAK = {'baseline': 0.0, 'schema1': 9.18, 'schema2': 14.0}
LAMBDA = {'man': 0.062227, 'outside': 0.062227, 'nonman': 0.0543894}
PERFORMING = 1.74717
SCALE = 1000 / 128
EPS = {'schema1': {'legs_car_related': 712, 'share_car': 0.0005, 'share_pt': 0.0005},
       'schema2': {'legs_car_related': 736, 'share_car': 0.0005, 'share_pt': 0.0005}}
REF = {'schema1': {'legs_car_related': -8717, 'share_car': -0.00250, 'share_pt': 0.00057},
       'schema2': {'legs_car_related': -11053, 'share_car': -0.00332, 'share_pt': 0.00084}}


def amount(dep, peak):
    if peak == 0: return 0.0
    h = (dep if not math.isnan(dep) else 0) / 3600
    return peak if (6 <= h < 10 or 14 <= h < 20 or 30 <= h < 34) else 3.06


def toll(plan, peak): return sum(t * amount(d, peak) for d, t, _ in plan['car'])


def legs(plan):
    l = plan['legs']; return np.array([l.get('car', 0), l.get('pt', 0), sum(l.values())], float)


def load(d, name):
    with open(f'{d}/plans/{name}.pkl', 'rb') as f: return pickle.load(f)


def truth(d, scen, seed):
    """Per agent [car, pt, all] legs of the selected plan, mean of snapshot 90 and output."""
    out = {}
    for it in ('it90', 'out'):
        for pid, ag in load(d, f'{scen}-s{seed}-{it}').items():
            sel = next((p for p in ag['plans'] if p['selected']), ag['plans'][0])
            out[pid] = out.get(pid, 0) + legs(sel) / 2
    return out


def pools(d, seed):
    """Final pool (output) and union pool (snapshots 40..90 + output, latest score per signature)."""
    final = load(d, f'baseline-s{seed}-out')
    union = defaultdict(dict)
    for it in ('it40', 'it50', 'it60', 'it70', 'it80', 'it90', 'out'):
        snap = final if it == 'out' else load(d, f'baseline-s{seed}-{it}')
        for pid, ag in snap.items():
            for p in ag['plans']:
                if not math.isnan(p['score']): union[pid][p['sig']] = p
    return final, {pid: list(v.values()) for pid, v in union.items()}


def effects(delta, base, related, pids):
    """delta, base: per agent [car, pt, all]; returns the three main effects (legs scaled)."""
    B = np.array([base[p] for p in pids]); Dl = np.array([delta[p] for p in pids]); r = np.array([related.get(p, False) for p in pids])
    P = B + Dl
    return {'legs_car_related': float(Dl[r, 0].sum() * SCALE),
            'share_car': float(P[:, 0].sum() / P[:, 2].sum() - B[:, 0].sum() / B[:, 2].sum()),
            'share_pt': float(P[:, 1].sum() / P[:, 2].sum() - B[:, 1].sum() / B[:, 2].sum())}


class Pool:
    """All plans of all agents of one seed as flat arrays: score, money utility x toll, legs, and sparse
    (plan x cell-hour) matrices of car link entries and free-flow seconds."""
    def __init__(self, pools, subpop, peak, n_cells):
        from scipy.sparse import csr_matrix
        s, m, lg, ag, rows, cols, k, ff, self.pids, starts = [], [], [], [], [], [], [], [], [], []
        for pid, plans in pools.items():
            if not plans: continue
            starts.append(len(s)); self.pids.append(pid); lam = LAMBDA.get(subpop.get(pid), 0.062227)
            for p in plans:
                j = len(s); s.append(p['score']); m.append(lam * toll(p, peak)); lg.append(legs(p))
                for dep, _, cells in p['car']:
                    h = 0 if math.isnan(dep) else min(int(dep // 3600), 29)
                    for c, v in cells.items():
                        if c >= 0: rows.append(j); cols.append(c * 30 + h); k.append(v[0]); ff.append(v[1])
        self.s, self.m, self.legs = np.array(s), np.array(m), np.array(lg)
        self.starts = np.array(starts); self.agent = np.repeat(np.arange(len(starts)), np.diff(np.append(self.starts, len(s))))
        shape = (len(s), n_cells * 30)
        self.K = csr_matrix((k, (rows, cols)), shape=shape); self.F = csr_matrix((ff, (rows, cols)), shape=shape)

    def probs(self, beta, u):
        u = beta * u; mx = np.maximum.reduceat(u, self.starts)
        e = np.exp(u - mx[self.agent]); return e / np.add.reduceat(e, self.starts)[self.agent]

    def per_agent(self, w):
        """Expected change of [car, pt, all] legs per agent for plan weight changes w."""
        d = np.add.reduceat(w[:, None] * self.legs, self.starts)
        return dict(zip(self.pids, d))


def logit_delta(pool, beta, congestion=None, iters=30):
    """Expected change of legs per agent; with congestion = (model, base entries, base congestion) iterate the
    feedback with step 1/n. Returns the per-agent changes and the largest congestion change."""
    pb = pool.probs(beta, pool.s)
    pp = pool.probs(beta, pool.s - pool.m)
    if congestion is None: return pool.per_agent(pp - pb), 0.0
    model, E0, C0 = congestion
    G0 = model(E0); dC = np.zeros_like(C0)
    for n in range(1, iters + 1):
        dE = (pool.K.T @ (pp - pb)).reshape(E0.shape) * SCALE
        dC = np.clip(C0 + model(np.maximum(E0 + dE, 0)) - G0, 0.5, None) - C0
        x = -(pool.F @ dC.ravel()) / 3600 * PERFORMING
        pp = pp + (pool.probs(beta, pool.s - pool.m + x) - pp) / n
    return pool.per_agent(pp - pb), float(np.abs(dC).max())


def congestion_model(states):
    """states: list of (entries [C, 30], congestion [C, 30], observed). Gradient boosting on the cell-hour's typical
    log entries and congestion, the hour and its log entries (monotone increasing). Returns E -> congestion."""
    LE = np.mean([np.log1p(e) for e, c, o in states], 0); CM = np.mean([np.where(o, c, 1) for e, c, o in states], 0)
    H = np.broadcast_to(np.arange(30), LE.shape)
    def f(E): return np.stack([LE.ravel(), CM.ravel(), H.ravel(), np.log1p(E).ravel()], 1)
    X = np.concatenate([f(e)[o.ravel()] for e, c, o in states]); y = np.concatenate([c.ravel()[o.ravel()] for e, c, o in states])
    m = HistGradientBoostingRegressor(max_iter=300, max_leaf_nodes=63, monotonic_cst=[0, 0, 0, 1]).fit(X, np.clip(y, 0.5, 5))
    print(f'congestion model: {len(y)} cell-hours', flush=True)
    return lambda E: m.predict(f(E)).reshape(E.shape)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--dir', required=True); ap.add_argument('--cohorts', required=True)
    ap.add_argument('--train', required=True); ap.add_argument('--test', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    with gzip.open(a.cohorts, 'rt') as f:
        related = {r['person_id']: r['charging_cohort'] == 'related' for r in csv.DictReader(f)}

    # congestion model: baseline and training-schema states
    states, base_state = [], {}
    for scen in ('baseline', a.train):
        for seed in SEEDS:
            Z = np.load(f'{a.dir}/city-{scen}-s{seed}.npz'); X = Z['X']
            states += [(np.expm1(X[i, :, :, 0]), X[i, :, :, 1], X[i, :, :, 2] > 0) for i in range(len(X))]
            if scen == 'baseline':
                last = [i for i, st in enumerate(Z['states']) if int(st.rsplit('-', 1)[1]) >= 90]
                base_state[seed] = (np.expm1(X[last, :, :, 0]).mean(0), X[last, :, :, 1].mean(0))
    model = congestion_model(states); n_cells = states[0][0].shape[0]

    data = {}
    for seed in SEEDS:
        tb = truth(a.dir, 'baseline', seed)
        final, union = pools(a.dir, seed)
        subpop = {pid: ag['subpop'] for pid, ag in final.items()}
        pids = sorted(set(tb) & set(final))
        data[seed] = {'pids': pids, 'base': tb, 'final': final, 'union': union, 'subpop': subpop}
        for scen in (a.train, a.test):
            t = truth(a.dir, scen, seed)
            data[seed][scen] = {p: t[p] - tb[p] for p in pids if p in t}
        print(f'seed {seed}: {len(pids)} agents', flush=True)

    res = {'train': a.train, 'test': a.test, 'methods': {}}

    def score(method, per_seed):
        """per_seed: seed -> per-agent delta for the test schema."""
        eff = [effects(per_seed[s], data[s]['base'], related, [p for p in data[s]['pids'] if p in per_seed[s]]) for s in SEEDS]
        m = {k: float(np.mean([e[k] for e in eff])) for k in eff[0]}
        res['methods'][method] = {'effects': m, 'per_seed': eff,
                                  'err_over_eps': {k: abs(m[k] - truth_eff[k]) / EPS[a.test][k] for k in m}}
        print(method, json.dumps({k: round(v, 5) for k, v in m.items()}),
              {k: round(v, 2) for k, v in res['methods'][method]['err_over_eps'].items()}, flush=True)

    # truth in the sample (and how it compares with the reference)
    truth_eff = {}
    for scen in (a.train, a.test):
        eff = [effects(data[s][scen], data[s]['base'], related, [p for p in data[s]['pids'] if p in data[s][scen]]) for s in SEEDS]
        res[f'truth_{scen}'] = {k: float(np.mean([e[k] for e in eff])) for k in eff[0]}
        res[f'truth_{scen}_per_seed'] = eff
    truth_eff = res[f'truth_{a.test}']
    print('truth', a.train, res[f'truth_{a.train}'], a.test, truth_eff, 'reference', REF[a.test], flush=True)

    score('zero', {s: {p: np.zeros(3) for p in data[s]['pids']} for s in SEEDS})
    ratio = PEAK[a.test] / PEAK[a.train]
    score('linear', {s: {p: data[s][a.train][p] * ratio for p in data[s][a.train]} for s in SEEDS})

    def pool(s, kind, peak):
        src = data[s]['final'] if kind == 'final' else data[s]['union']
        src = {p: (v['plans'] if isinstance(v, dict) else v) for p, v in src.items() if p in data[s]['base']}
        src = {p: [x for x in v if not math.isnan(x['score'])] for p, v in src.items()}
        return Pool(src, data[s]['subpop'], peak, n_cells)

    pools_cache = {(s, kind, sc): pool(s, kind, PEAK[sc]) for s in SEEDS for kind in ('final', 'union') for sc in (a.train, a.test)}

    def run(kind, cong, beta, scen, iters=30):
        per, mx = {}, 0
        for s in SEEDS:
            per[s], d = logit_delta(pools_cache[(s, kind, scen)], beta, (model, *base_state[s]) if cong else None, iters)
            mx = max(mx, d)
        return per, mx

    ipred = {}
    for kind, cong, name in (('final', False, 'I-0'), ('union', False, 'I-0u'), ('union', True, 'I-1')):
        target = res[f'truth_{a.train}']['legs_car_related']; fits = {}
        for beta in (0.25, 0.5, 1.0, 2.0, 4.0, 8.0):
            per, _ = run(kind, cong, beta, a.train)
            fits[beta] = float(np.mean([effects(per[s], data[s]['base'], related, list(per[s]))['legs_car_related'] for s in SEEDS]))
        res.setdefault('beta_fit', {})[name] = {'target': target, 'train_related_car': fits}
        print(f'  {name}: training related-car by beta {fits} vs {target:.0f}', flush=True)
        fitted = min(fits, key=lambda b: abs(fits[b] - target))
        for beta_mode, beta in (('beta1', 1.0), ('fitted', fitted)):
            per, mx = run(kind, cong, beta, a.test)
            score(f'{name} ({beta_mode}, beta {beta})', per)
            if cong: res['methods'][f'{name} ({beta_mode}, beta {beta})']['max_congestion_change'] = mx
        if name == 'I-1':
            ipred['test'] = run(kind, cong, fitted, a.test)[0]; ipred['train'] = run(kind, cong, fitted, a.train)[0]

    def feats(s, peak, ipr):
        rows, keys = [], []
        for p in data[s]['pids']:
            ag = data[s]['final'].get(p)
            if ag is None: continue
            pl = ag['plans']; sel = next((x for x in pl if x['selected']), pl[0])
            sc = np.array([x['score'] for x in pl]); sc = np.where(np.isnan(sc), -1e3, sc)
            t = np.array([toll(x, peak) for x in pl]); lg = np.array([legs(x) for x in pl])
            lam = LAMBDA.get(ag['subpop'], 0.062227)
            free = t == 0; nocar = lg[:, 0] == 0
            sub = [ag['subpop'] == k for k in ('man', 'nonman', 'outside')]
            row = [*sub, related.get(p, False), peak, *legs(sel), toll(sel, peak), lam * toll(sel, peak),
                   sum(c[1] for c in sel['car']), len(pl), sc.max() - (sc[free].max() if free.any() else sc.min() - 50),
                   sc.max() - (sc[nocar].max() if nocar.any() else sc.min() - 50), lg[:, 0].mean(), lg[:, 1].mean(),
                   len(data[s]['union'].get(p, []))]
            if ipr is not None: row += list(ipr[s].get(p, np.zeros(3)))
            rows.append(row); keys.append(p)
        return np.array(rows, float), keys

    for name, use_i in (('D', False), ('D+I', True)):
        Xtr, ytr = [], []
        for s in SEEDS:
            X, keys = feats(s, PEAK[a.train], ipred['train'] if use_i else None)
            Xtr.append(X); ytr.append(np.array([data[s][a.train].get(p, np.zeros(3)) for p in keys]))
        Xtr, ytr = np.concatenate(Xtr), np.concatenate(ytr)
        models = [HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05).fit(Xtr, ytr[:, j]) for j in range(3)]
        per = {}
        for s in SEEDS:
            X, keys = feats(s, PEAK[a.test], ipred['test'] if use_i else None)
            pr = np.stack([m.predict(X) for m in models], 1)
            per[s] = dict(zip(keys, pr))
        score(name, per)

    with open(a.out, 'w') as f: json.dump(res, f, indent=1)
    print('wrote', a.out)


if __name__ == '__main__':
    main()

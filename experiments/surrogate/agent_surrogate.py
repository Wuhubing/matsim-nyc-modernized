#!/usr/bin/env python3
"""L1 at the agent level: can a learned model correct PSim's travel-time estimate for a plan?

For iteration i of a run that wrote pre-mobsim plans and events every iteration:
  inputs  (available before mobsim i): plans_i, link times measured in iteration i-1, the person's
           actual times in i-1, whether the selected plan changed since i-1
  target  : person's total network-leg seconds measured in iteration i (QSim)
Estimators compared on held-out iterations: PSim with mean link times (contrib), PSim with geometric
means, persistence (previous actual, unchanged plans only), and a gradient-boosted correction.
Usage: agent_surrogate.py RUN_SIMULATION_DIR OUT_DIR --iterations 1 2 3 4 --test 4
"""
import argparse, json, math, pickle, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import dataset as S

BIN = 900


def link_index(net):
    return {l: i for i, l in enumerate(net)}


def state(events, index, cache):
    """Compact (link_idx*200+bin) -> [n, sum, sumlog] plus per-person network-leg durations."""
    if cache.exists():
        return pickle.load(open(cache, 'rb'))
    links, legs = {}, {}
    full, legs = S.road_state(events, BIN)
    for (l, b), v in full.items():
        i = index.get(l)
        if i is not None:
            links[i * 200 + b] = (v[0], v[1] / v[0], math.expm1(v[2] / v[0]))
    del full
    pickle.dump((links, legs), open(cache, 'wb'), protocol=pickle.HIGHEST_PROTOCOL)
    return links, legs


def signatures(plans):
    return {p: hash(tuple((e[0], e[1], tuple(e[3]) if e[0] == 'leg' and e[3] else None) for e in el))
            for p, el in S.selected_plans(plans)}


def features(plans, net, index, prev_links, prev_legs, prev_sig, cur_sig):
    """One row per person with at least one network leg."""
    names = list(net)
    def times(l, t, last):
        i = index.get(l); b = int(t // BIN)
        if i is None:
            return 1.0, 1.0, 1.0
        ff = S.free_flow(net, l, int(t // 3600))
        if last:
            return ff, ff, ff
        v = prev_links.get(i * 200 + b)
        return (v[1], v[2], ff) if v else (ff, ff, ff)
    rows = {}
    for person, el in S.selected_plans(plans):
        t_mean = t_geo = 0.0; tot_mean = tot_geo = tot_ff = 0.0; n_legs = n_links = 0; first_dep = None; congested = 0
        t = 0.0
        for kind, *x in el:
            if kind == 'act':
                end, dur = x; t = max(t, end) if end is not None else t + (dur or 0)
            else:
                mode, trav, route = x
                if mode in S.NETWORK_MODES and route:
                    n_legs += 1; first_dep = t if first_dep is None else first_dep
                    a = b = t
                    for k, l in enumerate(route[1:]):
                        last = k == len(route) - 2
                        m, g, ff = times(l, b, last)
                        mm, _, _ = times(l, a, last)
                        a += max(1, mm); b += max(1, g); tot_ff += ff; n_links += 1; congested += g > 2 * ff
                    tot_mean += a - t; tot_geo += b - t; t = b
                else:
                    t += trav
        if n_legs:
            prev = prev_legs.get(person)
            rows[person] = [tot_mean, tot_geo, tot_ff, n_legs, n_links, first_dep / 3600, congested / max(n_links, 1),
                            sum(prev) if prev else np.nan, len(prev) if prev else 0, float(prev_sig.get(person) != cur_sig.get(person))]
    return rows


COLUMNS = ['psim_mean', 'psim_geo', 'free_flow', 'n_legs', 'n_links', 'first_dep_h', 'congested_share', 'prev_actual', 'prev_n_legs', 'changed']


def build(sim, out, iterations, net, index):
    data = {}
    for i in iterations:
        f = out/f'agent-rows-{i}.pkl'
        if f.exists():
            data[i] = pickle.load(open(f, 'rb')); continue
        prev_links, prev_legs = state(next((sim/f'ITERS/it.{i-1}').glob('*.events.xml.zst')), index, out/f'state-{i-1}.pkl')
        _, legs = state(next((sim/f'ITERS/it.{i}').glob('*.events.xml.zst')), index, out/f'state-{i}.pkl')
        prev_sig = signatures(next((sim/f'ITERS/it.{i-1}').glob('*.plans.xml.zst')))
        cur_sig = signatures(next((sim/f'ITERS/it.{i}').glob('*.plans.xml.zst')))
        rows = features(next((sim/f'ITERS/it.{i}').glob('*.plans.xml.zst')), net, index, prev_links, prev_legs, prev_sig, cur_sig)
        X, y = [], []
        for p, r in rows.items():
            actual = legs.get(p)
            if actual and len(actual) == r[3]:
                X.append(r); y.append(sum(actual))
        data[i] = (np.array(X, dtype=float), np.array(y, dtype=float))
        pickle.dump(data[i], open(f, 'wb'), protocol=pickle.HIGHEST_PROTOCOL)
        print('built', i, len(y), flush=True)
    return data


def errors(pred, y, mask=None):
    d = np.abs(pred - y) if mask is None else np.abs(pred[mask] - y[mask])
    if not len(d):
        return {}
    return {'n': int(len(d)), 'mae': float(d.mean()), 'median': float(np.median(d)), 'p90': float(np.quantile(d, .9)),
            'within_60s': float((d <= 60).mean()), 'within_300s': float((d <= 300).mean())}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('sim', type=Path); ap.add_argument('out', type=Path)
    ap.add_argument('--iterations', type=int, nargs='+', required=True); ap.add_argument('--test', type=int, nargs='+', required=True)
    ap.add_argument('--network', type=Path, required=True)
    a = ap.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    net = S.network(a.network); index = link_index(net)
    data = build(a.sim, a.out, a.iterations, net, index)
    from sklearn.ensemble import HistGradientBoostingRegressor
    train = [i for i in a.iterations if i not in a.test]
    Xtr = np.vstack([data[i][0] for i in train]); ytr = np.concatenate([data[i][1] for i in train])
    # Predict the log ratio of actual to the geometric PSim estimate: scale-free and robust to heavy tails.
    model = HistGradientBoostingRegressor(max_iter=300, learning_rate=.1, max_leaf_nodes=63, random_state=0)
    model.fit(Xtr, np.log1p(ytr) - np.log1p(Xtr[:, 1]))
    report = {'train_iterations': train, 'test_iterations': a.test, 'columns': COLUMNS, 'results': {}}
    for i in a.test:
        X, y = data[i]; changed = X[:, 9] == 1; unchanged = ~changed
        learned = np.expm1(model.predict(X) + np.log1p(X[:, 1]))
        # What PSim actually does: unchanged plans keep their last QSim outcome, changed plans are replayed.
        hybrid = np.where(unchanged & ~np.isnan(X[:, 7]) & (X[:, 8] == X[:, 3]), X[:, 7], X[:, 1])
        res = {}
        for name, pred in [('psim_mean', X[:, 0]), ('psim_geo', X[:, 1]), ('psim_hybrid', hybrid), ('learned', learned)]:
            res[name] = {'all': errors(pred, y), 'changed': errors(pred, y, changed), 'unchanged': errors(pred, y, unchanged)}
        report['results'][str(i)] = res
        for name, r in res.items():
            print(i, f'{name:22s}', ' | '.join(f"{g}: mae={v['mae']:.0f} med={v['median']:.0f} n={v['n']}" for g, v in r.items() if v), flush=True)
    (a.out/'agent-surrogate.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()

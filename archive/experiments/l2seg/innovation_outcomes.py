#!/usr/bin/env python3
"""What kind of waste is the 85% of innovations that do not become kept improvements? (RQ1 follow-up)

  innovation_outcomes.py RUN --out FILE.json [--horizon 10] [--last 79]

For every innovation at iteration t (new plan created and selected at t) by strategy type (ReRoute, time mutation,
subtour mode choice + reroute), from the replanning log:
- no-op: the new plan has the same trips, modes and routes as its parent (per trips-t; time mutation always keeps
  modes and routes, so it is reported separately);
- first evaluation: executed score at t minus the agent's best stored score at t-1 (positive = better at once);
- fate: selected again within t+1..t+H, and useful as in L-U (selected again and its last score in t..t+H above
  the best at t-1);
- noise scale: |score change| of agents who kept the same, older plan from t-1 to t (same plan, different
  simulation) - the size of score differences that one evaluation cannot distinguish from noise."""
import argparse, csv, gzip, json, re, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from logs import ReplanningLog
import labels


def kinds(log):
    with open(log.dir/'strategies.csv', newline='') as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        d = r['description']
        out[int(r['strategy'])] = 'mode' if 'SubtourModeChoice' in d else 'time' if 'TimeAllocation' in d else 'route' if 'ReRoute' in d else 'select'
    return out


def trip_changes(log, t):
    """Per person index with a new plan at t: (any mode changed, any route changed, trip count mismatch)."""
    res = {}
    with gzip.open(log.dir/f'trips-{t}.csv.gz', 'rt') as f:
        for r in csv.DictReader(f):
            p = int(r['person']); m, rt, mis = res.get(p, (False, False, False))
            if r['trip'] == '-1': res[p] = (True, True, True); continue
            res[p] = (m or r['mode_changed'] == '1', rt or r['route_changed'] == '1', mis)
    return res


def q(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if not len(x): return {}
    return {'n': int(len(x)), 'mean': float(x.mean()), 'p10': float(np.quantile(x, .1)), 'p50': float(np.quantile(x, .5)),
            'p90': float(np.quantile(x, .9)), 'share_positive': float((x > 0).mean())}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True); ap.add_argument('--horizon', type=int, default=10)
    ap.add_argument('--last', type=int, default=79); a = ap.parse_args()
    log = ReplanningLog(a.run); its, d = labels.load(log); kind = kinds(log)
    strat = np.stack([log.agents(t)['strategy'] for t in its])          # strategy code per iteration
    H = a.horizon; T = len(its)
    buckets = {'1-10': range(1, 11), '11-40': range(11, 41), '41-79': range(41, a.last + 1)}
    acc = {}
    noise = {b: [] for b in buckets}
    for b, rng in buckets.items():
        for t in rng:
            if t + H >= T: continue
            ch = trip_changes(log, t)
            new = d['innovated'][t] & (d['created'][t] == t)
            idx = np.nonzero(new)[0]
            first = d['executed'][t, idx] - d['best'][t - 1, idx]
            window = d['plan'][t:t + H + 1, idx] == d['plan'][t, idx][None, :]
            again = window[1:].any(axis=0)
            last = H - np.argmax(window[::-1], axis=0)
            useful = again & (d['executed'][t + last, idx] > d['best'][t - 1, idx])
            for j, k in enumerate(idx):
                ty = kind.get(int(strat[t, k]), '?')
                c = ch.get(int(log.index[k]), (False, False, False))
                key = (b, ty); s = acc.setdefault(key, {'n': 0, 'noop': 0, 'mode_changed': 0, 'route_changed': 0, 'again': 0, 'useful': 0, 'first': []})
                s['n'] += 1; s['noop'] += (not c[0] and not c[1] and ty != 'time'); s['mode_changed'] += c[0]; s['route_changed'] += c[1]
                s['again'] += bool(again[j]); s['useful'] += bool(useful[j]); s['first'].append(float(first[j]))
            same = (d['plan'][t] == d['plan'][t - 1]) & (d['created'][t] < t - 1)
            noise[b].extend(np.abs(d['executed'][t, same] - d['executed'][t - 1, same]).tolist()[::20])
    out = {'run': a.run, 'horizon': H, 'buckets': {}}
    for (b, ty), s in sorted(acc.items()):
        n = s['n']
        out['buckets'].setdefault(b, {})[ty] = {'innovations': n, 'noop_share': s['noop'] / n, 'mode_changed_share': s['mode_changed'] / n,
            'route_changed_share': s['route_changed'] / n, 'selected_again_share': s['again'] / n, 'useful_share': s['useful'] / n,
            'first_score_minus_best': q(s['first'])}
    out['noise_abs_score_change_same_old_plan'] = {b: q(x) for b, x in noise.items()}
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    for b, v in out['buckets'].items():
        print(f'== iterations {b}; noise |score change| of unchanged plans: median {out["noise_abs_score_change_same_old_plan"][b].get("p50", float("nan")):.3f}, p90 {out["noise_abs_score_change_same_old_plan"][b].get("p90", float("nan")):.3f}')
        for ty, s in v.items():
            f = s['first_score_minus_best']
            print(f"  {ty:6} n {s['innovations']:8d} no-op {s['noop_share']:.3f} mode-chg {s['mode_changed_share']:.3f} route-chg {s['route_changed_share']:.3f} "
                  f"again {s['selected_again_share']:.3f} useful {s['useful_share']:.3f} | first-best: p10 {f['p10']:.2f} p50 {f['p50']:.2f} p90 {f['p90']:.2f} better-at-once {f['share_positive']:.3f}")


if __name__ == '__main__':
    main()

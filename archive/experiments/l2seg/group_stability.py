#!/usr/bin/env python3
"""A3: do groups of similar travellers settle at clearly different times, can that be seen early, and what would
freezing a settled group lose? Compares groupings (docs/aggregate-regularity-plan.md Section 3.1, method M3).

  group_stability.py --runs RUN [RUN ...] --snaps SNAPDIR [SNAPDIR ...] --out FILE.json
                     [--cell-ft 10000] [--od-cell-ft 20000] [--min-size 300]

Persons of subpopulations man and nonman (outside never innovates). Groupings are fixed from iteration-0
attributes (persons.npz of plan_snapshots.py for the first run; the population is the same in every run):
- cohort: subpopulation x charging cohort (research/cohorts.csv.gz), the existing ResearchMetrics groups;
- home: subpopulation x home cell (square grid of --cell-ft, EPSG:2263 feet; 10000 ft = 3 km);
- od: subpopulation x home cell x primary-activity cell (--od-cell-ft) x departure period of the first trip
  (night <6, am 6-10, mid 10-15, pm 15-19, eve >=19 h).
A group smaller than --min-size falls back to the next coarser key (od -> home cell x period -> home cell ->
subpopulation 'other'; home -> subpopulation 'other').
Per group and run: mean executed score and share whose choice changed, every iteration (research/persons-N.csv.gz);
per snapshot the main-mode shares of the selected and the best stored plans and the mean best stored score.
Settling, looking back from the end (the truth an online rule should find):
- t_score: first iteration t >= 10 from which the 10-iteration rolling mean of the group score stays within
  eps x (change from iterations 1-10 to 70-79) of the 70-79 mean, up to 79 (at most 79 by construction);
- t_mode: first snapshot k from which the best-plan mode split stays within tau (total variation) of the selected
  split at snapshot 90 (after ten iterations without innovation), up to 70; 80 = not settled.
Reported per grouping: group count and sizes; person-weighted quantiles of t_score and t_mode; seed consistency
(Spearman correlation of a group's settling time between runs: a property of the group, or luck?); online rules at
t = 20..70 (score: change over the last 10 iterations <= eps x change since iteration 10, which cannot hold at
t = 20; mode: best split moved
<= tau/2 since the previous snapshot) with share of persons declared settled, precision (truly settled by t) and
recall; what freezing at k would forgo (mean best stored score at snapshot 80 minus at k) for settled and unsettled
groups; eta^2 of the final car and pt trip shares (person-level variation explained by the grouping); seed noise of
the group mode split (total variation between runs at snapshot 90)."""
import argparse, csv, gzip, itertools, json, sys, warnings
from pathlib import Path
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.stats import spearmanr
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_snapshots import MODES
from best_state import load

SUBPOPS = ('man', 'nonman')
PERIODS = [(6, 'night'), (10, 'am'), (15, 'mid'), (19, 'pm'), (float('inf'), 'eve')]
EPS = (0.05, 0.10); TAUS = (0.02, 0.05)
SNAPS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]; ITS = range(100); ONLINE = (20, 30, 40, 50, 60, 70)


def period(dep):
    if not np.isfinite(dep): return 'none'
    return next(n for b, n in PERIODS if dep / 3600 < b)


def cells(x, y, size):
    return np.array([f'{int(a // size)}_{int(b // size)}' if np.isfinite(a) and np.isfinite(b) else 'na' for a, b in zip(x, y)], dtype=object)


def assign(levels, min_size):
    """levels: key arrays, finest first. Each person gets the finest key whose group, among persons not yet assigned,
    has at least min_size members; the last level takes everyone left."""
    out = np.array(levels[-1], dtype=object); left = np.ones(len(out), bool)
    for keys in levels[:-1]:
        keys = np.asarray(keys, dtype=object)
        if not left.any(): break
        _, inv, cnt = np.unique(keys[left], return_inverse=True, return_counts=True)
        idx = np.flatnonzero(left)[cnt[inv] >= min_size]; out[idx] = keys[idx]; left[idx] = False
    return out


def groupings(persons, cohort, cell_ft, od_cell_ft, min_size):
    sub = persons['subpopulation'].astype(object)
    other = sub + '|other'
    home = sub + '|h|' + cells(persons['home_x'], persons['home_y'], cell_ft)
    oh = cells(persons['home_x'], persons['home_y'], od_cell_ft); op = cells(persons['prim_x'], persons['prim_y'], od_cell_ft)
    per = np.array([period(d) for d in persons['departure']], dtype=object)
    return {'cohort': sub + '|' + cohort,
            'home': assign([home, other], min_size),
            'od': assign([sub + '|od|' + oh + '|' + op + '|' + per, sub + '|hp|' + oh + '|' + per, sub + '|h|' + oh, other], min_size)}


def person_series(run, pos):
    """Executed score and choice-changed flag per person (rows aligned with pos) and iteration."""
    n = len(pos); score = np.full((n, len(ITS)), np.nan, np.float32); changed = np.full((n, len(ITS)), np.nan, np.float32)
    for t in ITS:
        with gzip.open(Path(run)/'simulation'/'research'/f'persons-{t}.csv.gz', 'rt') as f:
            r = csv.reader(f); h = next(r); ip, isc, ic = h.index('person_id'), h.index('score'), h.index('choice_changed')
            for row in r:
                k = pos.get(row[ip])
                if k is None: continue
                if row[isc]: score[k, t] = float(row[isc])
                if row[ic]: changed[k, t] = row[ic] == 'True'
    return score, changed


def gmean(x, g, ng):
    """Group means of x ([n] or [n, T]) ignoring nan."""
    if x.ndim == 1: x = x[:, None]
    out = np.full((ng, x.shape[1]), np.nan)
    for j in range(x.shape[1]):
        ok = np.isfinite(x[:, j]); n = np.bincount(g[ok], minlength=ng)
        s = np.bincount(g[ok], weights=x[ok, j], minlength=ng)
        with np.errstate(invalid='ignore', divide='ignore'): out[:, j] = s / n
    return out


def gshares(counts, g, ng):
    s = np.stack([np.bincount(g, weights=counts[:, m], minlength=ng) for m in range(counts.shape[1])], axis=1)
    with np.errstate(invalid='ignore', divide='ignore'): return s / s.sum(axis=1, keepdims=True)


def tv(a, b): return 0.5 * np.abs(a - b).sum(axis=-1)


def rolling(y):
    """10-iteration rolling mean, value at t = mean over t-9..t (nan for t < 9)."""
    out = np.full(y.shape, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        out[:, 9:] = np.nanmean(sliding_window_view(y, 10, axis=1), axis=2)
    return out


def settle_score(y, eps):
    """y [G, 100] group series -> t_score [G] (nan when the group did not change at all)."""
    roll = rolling(y); ref = roll[:, 79]; total = np.abs(ref - roll[:, 10])
    bad = np.abs(roll[:, 10:80] - ref[:, None]) > eps * total[:, None]
    t = np.where(bad.any(axis=1), 10 + (bad.shape[1] - np.argmax(bad[:, ::-1], axis=1)), 10).astype(float)
    t[~(total > 0)] = np.nan
    return t


def settle_mode(best, ref, tau):
    """best [G, K, M] best-plan shares at snapshots 10..70, ref [G, M] -> t_mode [G] in {10, ..., 80}."""
    bad = tv(best, ref[:, None, :]) > tau
    return np.where(bad.any(axis=1), 10 * (bad.shape[1] - np.argmax(bad[:, ::-1], axis=1)) + 10, 10).astype(float)


def wquantiles(x, w, qs=(0.1, 0.25, 0.5, 0.75, 0.9)):
    ok = np.isfinite(x) & (w > 0)
    if not ok.any(): return [float('nan')] * len(qs)
    o = np.argsort(x[ok]); xs, cw = x[ok][o], np.cumsum(w[ok][o]); cw = cw / cw[-1]
    return [float(xs[min(np.searchsorted(cw, q), len(xs) - 1)]) for q in qs]


def eta2(x, g, ng):
    ok = np.isfinite(x); x, g = x[ok], g[ok]
    n = np.bincount(g, minlength=ng); m = np.bincount(g, weights=x, minlength=ng)
    with np.errstate(invalid='ignore', divide='ignore'): gm = m / n
    tot = ((x - x.mean()) ** 2).sum()
    return float((n[n > 0] * (gm[n > 0] - x.mean()) ** 2).sum() / tot) if tot else float('nan')


def wmean(x, w):
    ok = np.isfinite(x) & (w > 0); return float(np.average(x[ok], weights=w[ok])) if ok.any() else float('nan')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--runs', nargs='+', required=True); ap.add_argument('--snaps', nargs='+', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--cell-ft', type=float, default=10000)
    ap.add_argument('--od-cell-ft', type=float, default=20000); ap.add_argument('--min-size', type=int, default=300)
    a = ap.parse_args(); assert len(a.runs) == len(a.snaps)
    persons = dict(np.load(Path(a.snaps[0])/'persons.npz'))
    keep = np.isin(persons['subpopulation'], SUBPOPS); persons = {k: v[keep] for k, v in persons.items()}
    ids = persons['id']; pos = {p: i for i, p in enumerate(ids)}
    with gzip.open(Path(a.runs[0])/'simulation'/'research'/'cohorts.csv.gz', 'rt') as f:
        coh = {r['person_id']: r['charging_cohort'] for r in csv.DictReader(f)}
    cohort = np.array([coh.get(p, 'unknown') for p in ids], dtype=object)
    G = groupings(persons, cohort, a.cell_ft, a.od_cell_ft, a.min_size)
    codes = {}
    for name, keys in G.items():
        u, inv = np.unique(keys, return_inverse=True); codes[name] = (u, inv)
    print('groupings: ' + ', '.join(f'{n} {len(u)} groups' for n, (u, _) in codes.items()), flush=True)

    per_run = []
    for run, sd in zip(a.runs, a.snaps):
        score, changed = person_series(run, pos)
        snaps = {}
        for k in SNAPS:
            s = load(sd, k); full = {p: i for i, p in enumerate(s['id'])}; order = np.array([full[p] for p in ids])
            snaps[k] = {n: v[order] for n, v in s.items()}
        per_run.append({'score': score, 'changed': changed, 'snaps': snaps})
        print(f'loaded {run}', flush=True)

    trips = per_run[0]['snaps'][90]['sel'].sum(axis=1).astype(float)
    out = {'runs': a.runs, 'params': {'cell_ft': a.cell_ft, 'od_cell_ft': a.od_cell_ft, 'min_size': a.min_size,
                                      'eps': EPS, 'taus': TAUS}, 'groupings': {}}
    car, pt = MODES.index('car'), MODES.index('pt')
    for name, (u, g) in codes.items():
        ng = len(u); size = np.bincount(g, minlength=ng).astype(float); res = {}
        res['groups'] = ng; res['size_quantiles'] = np.quantile(size, [0, 0.1, 0.5, 0.9, 1]).tolist()
        res['fallback_persons'] = {lvl: float(size[[lvl in k for k in u]].sum() / size.sum()) for lvl in ('|other', '|h|', '|hp|', '|od|')}
        with np.errstate(invalid='ignore', divide='ignore'):
            sel90 = per_run[0]['snaps'][90]['sel']
            res['eta2'] = {'car': eta2(sel90[:, car] / trips, g, ng), 'pt': eta2(sel90[:, pt] / trips, g, ng)}
        T = {f'score_eps{e}': [] for e in EPS} | {f'mode_tau{t}': [] for t in TAUS}
        online = {key: {t: [] for t in ONLINE} for key in T}; forgo = {key: {t: [] for t in (20, 30, 40, 50)} for key in T}
        noise90 = []
        for r in per_run:
            ys = gmean(r['score'], g, ng); roll = rolling(ys)
            best = np.stack([gshares(r['snaps'][k]['best'], g, ng) for k in SNAPS], axis=1)   # [G, K, M]
            ref = gshares(r['snaps'][90]['sel'], g, ng)
            bscore = np.stack([gmean(r['snaps'][k]['best_score'].astype(float), g, ng)[:, 0] for k in SNAPS], axis=1)
            K = {k: j for j, k in enumerate(SNAPS)}
            for e in EPS:
                key = f'score_eps{e}'; ts = settle_score(ys, e); T[key].append(ts)
                for t in ONLINE:
                    dec = np.abs(roll[:, t] - roll[:, t - 10]) <= e * np.abs(roll[:, t] - roll[:, 10]); online[key][t].append((dec, ts <= t))
            for tau in TAUS:
                key = f'mode_tau{tau}'; tm = settle_mode(best[:, K[10]:K[70] + 1], ref, tau); T[key].append(tm)
                for t in ONLINE:
                    dec = tv(best[:, K[t]], best[:, K[t - 10]]) <= tau / 2; online[key][t].append((dec, tm <= t))
            for key in T:
                for k in forgo[key]:
                    gain = bscore[:, K[80]] - bscore[:, K[k]]; settled = T[key][-1] <= k
                    forgo[key][k].append((wmean(gain, size * settled), wmean(gain, size * ~settled), float((size * settled).sum() / size.sum())))
            noise90.append(ref)
        res['seed_noise_tv90'] = wquantiles(np.concatenate([tv(x, y) for x, y in itertools.combinations(noise90, 2)]) if len(noise90) > 1 else np.array([np.nan]),
                                            np.tile(size, max(len(noise90) * (len(noise90) - 1) // 2, 1)), (0.5, 0.9))
        res['settling'] = {}
        for key, runs_t in T.items():
            allT = np.stack(runs_t); w = np.tile(size, (len(runs_t), 1))
            rho = [spearmanr(x, y, nan_policy='omit')[0] for x, y in itertools.combinations(runs_t, 2)]
            on = {}
            for t, lst in online[key].items():
                dec = np.concatenate([d for d, _ in lst]); tru = np.concatenate([s for _, s in lst]); ww = np.tile(size, len(lst))
                on[t] = {'declared': float((ww * dec).sum() / ww.sum()),
                         'precision': float((ww * (dec & tru)).sum() / (ww * dec).sum()) if dec.any() else float('nan'),
                         'recall': float((ww * (dec & tru)).sum() / (ww * tru).sum()) if tru.any() else float('nan')}
            fg = {k: {'gain_settled': float(np.nanmean([x[0] for x in v])), 'gain_unsettled': float(np.nanmean([x[1] for x in v])),
                      'settled_share': float(np.mean([x[2] for x in v]))} for k, v in forgo[key].items()}
            res['settling'][key] = {'quantiles_10_25_50_75_90': wquantiles(allT.ravel(), w.ravel()),
                                    'settled_by': {t: float((w * (allT <= t)).sum() / w.sum()) for t in (20, 30, 40, 50, 60, 70)},
                                    'seed_spearman': [float(x) for x in rho], 'online': on, 'forgo_best_score_to_80': fg}
        res['table'] = [{'group': str(k), 'persons': int(n), **{key: [float(x[i]) for x in v] for key, v in T.items()}}
                        for i, (k, n) in enumerate(zip(u, size))]
        out['groupings'][name] = res
    Path(a.out).write_text(json.dumps(out, indent=1, default=float) + '\n')

    for name, res in out['groupings'].items():
        q = res['size_quantiles']
        print(f"\n== {name}: {res['groups']} groups, size min/median/max {q[0]:.0f}/{q[2]:.0f}/{q[4]:.0f}, "
              f"eta2 car {res['eta2']['car']:.3f} pt {res['eta2']['pt']:.3f}, seed noise tv90 median {res['seed_noise_tv90'][0]:.3f}")
        for key, s in res['settling'].items():
            qs = s['quantiles_10_25_50_75_90']; rho = np.mean(s['seed_spearman']) if s['seed_spearman'] else float('nan')
            on = ' '.join(f"t{t}:{v['declared']:.2f}/{v['precision']:.2f}" for t, v in s['online'].items())
            print(f"  {key:15} T q10/50/90 {qs[0]:.0f}/{qs[2]:.0f}/{qs[4]:.0f}  settled by 30/50 {s['settled_by'][30]:.2f}/{s['settled_by'][50]:.2f}"
                  f"  seed rho {rho:+.2f}  online declared/precision {on}")
            fg = s['forgo_best_score_to_80']
            print('  ' + ' ' * 15 + ' forgo (best score gain to 80, settled | unsettled): ' +
                  ' '.join(f"k{k}: {v['gain_settled']:+.2f}|{v['gain_unsettled']:+.2f}" for k, v in fg.items()))


if __name__ == '__main__':
    main()

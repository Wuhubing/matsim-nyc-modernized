#!/usr/bin/env python3
"""A5 (groups) and A3': step-by-step dynamics of group-level state, read as L2Seg reads a solver step
(docs/aggregate-regularity-plan.md Section 2.1).

  group_dynamics.py --runs RUN [RUN ...] --snaps SNAPDIR --out FILE.json [--window 5]

Groups as in A3 (group_stability.py: cohort, home, od; persons.npz from SNAPDIR, cohorts from the first run).
Per group and iteration, from research/persons-N.csv.gz: mean executed score, completed car legs per person,
transit wait segments per person, completed travel seconds per person.
With W-iteration window means a(t) = mean over t-W+1..t, the change into t is d0 = a(t) - a(t-W) and the change after
t is d1 = a(t+W) - a(t). Noise sd per group = sd of first differences over iterations 60-79 / sqrt(2); a difference
of two window means then has sd se = sd * sqrt(2 / W), and z = d / se. Only t with t + W <= 79 (before the
innovation switch-off jump). Reported per grouping, metric and t, mean over runs (dynamics()):
- signal_share: weight (persons) of groups whose next change is clearly beyond noise (|z1| > 2);
- top10/top20_energy: share of the excess signal energy sum w max(z1^2 - 1, 0) in the groups with the largest
  |z1| holding 10% / 20% of the weight (concentration of where things change);
- top20_recall: share of that next-window energy that lies in the groups with the largest |z0| (top 20% of weight)
  - can the current change tell where the next change happens? (0.2 = no better than random);
- spearman_abs: rank correlation of |z0| and |z1| over groups;
- cos: weighted cosine of z0 and z1 over groups (is the drift direction consistent?);
- extrapolation to t + m (m = 5, 10, 20, target window <= 79): weighted RMS error of persistence a(t) and of the
  linear extrapolation a(t) + (m / W) d0, their ratio (< 1: extrapolation helps), and the noise floor sd / sqrt(W).
dynamics() is shared with link_dynamics.py."""
import argparse, csv, gzip, json, sys, warnings
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
sys.path.insert(0, str(Path(__file__).resolve().parent))
from group_stability import groupings, SUBPOPS

METRICS = ('score', 'car_legs', 'waits', 'travel_s')
COLS = {'score': 'score', 'car_legs': 'completed_car_legs', 'waits': 'wait_segments', 'travel_s': 'completed_travel_seconds'}
LAST = 79


def wm(Y, t, W):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning); return np.nanmean(Y[:, t - W + 1:t + 1], axis=1)


def noise_sd(Y, lo=60, hi=LAST):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning); return np.nanstd(np.diff(Y[:, lo:hi + 1], axis=1), axis=1) / np.sqrt(2)


def wrms(x, w):
    ok = np.isfinite(x) & (w > 0); return float(np.sqrt(np.average(x[ok] ** 2, weights=w[ok]))) if ok.any() else float('nan')


def top_mask(score, w, share):
    """Rows with the largest score holding `share` of the weight."""
    o = np.argsort(-score); cw = np.cumsum(w[o]) / w.sum(); m = np.zeros(len(score), bool); m[o[:np.searchsorted(cw, share) + 1]] = True
    return m


def dynamics(Y, w, sd, ts, W=5, ms=(5, 10, 20)):
    """Y [rows, iterations], w [rows] weights, sd [rows] per-iteration noise sd -> {t: metrics} (see module doc)."""
    se = sd * np.sqrt(2.0 / W); out = {}
    for t in ts:
        if t - 2 * W + 1 < 0 or t + W > LAST: continue
        a, b, c = wm(Y, t, W), wm(Y, t - W, W), wm(Y, t + W, W)
        with np.errstate(invalid='ignore', divide='ignore'): z0, z1 = (a - b) / se, (c - a) / se
        ok = np.isfinite(z0) & np.isfinite(z1) & (se > 0) & (w > 0)
        if ok.sum() < 3: continue
        z0, z1, ww, aa, bb = z0[ok], z1[ok], w[ok], a[ok], b[ok]
        e = np.maximum(z1 ** 2 - 1, 0) * ww; E = e.sum()
        row = {'rows': int(ok.sum()), 'signal_share': float(ww[np.abs(z1) > 2].sum() / ww.sum()),
               'top10_energy': float(e[top_mask(np.abs(z1), ww, 0.1)].sum() / E) if E else float('nan'),
               'top20_energy': float(e[top_mask(np.abs(z1), ww, 0.2)].sum() / E) if E else float('nan'),
               'top20_recall': float(e[top_mask(np.abs(z0), ww, 0.2)].sum() / E) if E else float('nan'),
               'spearman_abs': float(spearmanr(np.abs(z0), np.abs(z1))[0]),
               'cos': float((ww * z0 * z1).sum() / np.sqrt((ww * z0 ** 2).sum() * (ww * z1 ** 2).sum()))}
        for m in ms:
            if t + m > LAST: continue
            target = wm(Y, t + m, W)[ok]; lin = aa + (m / W) * (aa - bb)
            p, l = wrms(target - aa, ww), wrms(target - lin, ww)
            row[f'm{m}'] = {'persistence': p, 'linear': l, 'ratio': l / p if p else float('nan'), 'noise_floor': wrms(sd[ok] / np.sqrt(W), ww)}
        out[t] = row
    return out


def mean_rows(rows):
    """Mean over runs of nested dicts of numbers."""
    if isinstance(rows[0], dict): return {k: mean_rows([r[k] for r in rows if k in r]) for k in rows[0] if all(k in r for r in rows)}
    return float(np.nanmean(rows))


def person_matrix(run, pos):
    n = len(pos); Y = {k: np.full((n, LAST + 21), np.nan, np.float32) for k in METRICS}
    for t in range(LAST + 21):
        f = Path(run)/'simulation'/'research'/f'persons-{t}.csv.gz'
        if not f.exists(): continue
        with gzip.open(f, 'rt') as fh:
            r = csv.reader(fh); h = next(r); ip = h.index('person_id'); ix = {k: h.index(c) for k, c in COLS.items()}
            for row in r:
                i = pos.get(row[ip])
                if i is None: continue
                for k, j in ix.items():
                    if row[j]: Y[k][i, t] = float(row[j])
    return Y


def gmeans(X, g, ng):
    out = np.full((ng, X.shape[1]), np.nan)
    for t in range(X.shape[1]):
        ok = np.isfinite(X[:, t]); n = np.bincount(g[ok], minlength=ng)
        with np.errstate(invalid='ignore', divide='ignore'): out[:, t] = np.bincount(g[ok], weights=X[ok, t], minlength=ng) / n
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--runs', nargs='+', required=True); ap.add_argument('--snaps', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--window', type=int, default=5)
    ap.add_argument('--cell-ft', type=float, default=10000); ap.add_argument('--od-cell-ft', type=float, default=20000)
    ap.add_argument('--min-size', type=int, default=300)
    a = ap.parse_args(); W = a.window; ts = list(range(2 * W, LAST - W + 1, 5))
    persons = dict(np.load(Path(a.snaps)/'persons.npz'))
    keep = np.isin(persons['subpopulation'], SUBPOPS); persons = {k: v[keep] for k, v in persons.items()}
    ids = persons['id']; pos = {p: i for i, p in enumerate(ids)}
    with gzip.open(Path(a.runs[0])/'simulation'/'research'/'cohorts.csv.gz', 'rt') as f:
        coh = {r['person_id']: r['charging_cohort'] for r in csv.DictReader(f)}
    G = groupings(persons, np.array([coh.get(p, 'unknown') for p in ids], dtype=object), a.cell_ft, a.od_cell_ft, a.min_size)
    codes = {name: np.unique(keys, return_inverse=True) for name, keys in G.items()}
    res = {name: {k: [] for k in METRICS} for name in codes}
    for run in a.runs:
        P = person_matrix(run, pos)
        for name, (u, g) in codes.items():
            w = np.bincount(g, minlength=len(u)).astype(float)
            for k in METRICS:
                Y = gmeans(P[k], g, len(u)); res[name][k].append(dynamics(Y, w, noise_sd(Y), ts, W))
        print(f'done {run}', flush=True); del P
    out = {'runs': a.runs, 'window': W, 'ts': ts, 'groupings': {name: {k: mean_rows(v) for k, v in m.items()} for name, m in res.items()}}
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    for name, m in out['groupings'].items():
        print(f'\n== {name} ({len(codes[name][0])} groups); per t: signal share | top20 energy | top20 recall (0.2 = random) | cos | extrapolation/persistence m=5,10,20')
        for k, rows in m.items():
            print(f'  {k}')
            for t, r in rows.items():
                ex = ' '.join(f"{r[f'm{x}']['ratio']:.2f}" if f'm{x}' in r else '  - ' for x in (5, 10, 20))
                print(f"    t={t:2d}  {r['signal_share']:.2f} | {r['top20_energy']:.2f} | {r['top20_recall']:.2f} | {r['cos']:+.2f} | {ex}"
                      f"   (persist/noise m5 {r['m5']['persistence'] / r['m5']['noise_floor']:.1f})" if 'm5' in r else '')


if __name__ == '__main__':
    main()

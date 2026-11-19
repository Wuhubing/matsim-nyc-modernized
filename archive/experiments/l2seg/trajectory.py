#!/usr/bin/env python3
"""How regular are the aggregate trajectories, and how early do they determine the end state? (plan Section 8.3)

  trajectory.py TOLERANCE.json RUN [RUN ...] --out FILE.json [--ks 10,20,30,40,50,60,70]

Per indicator (plan Section 4 indicators, plus the mean best stored score from scorestats) and per cut-off k:
- seed spread: max - min across runs at iteration k, in units of the tolerance sigma;
- extrapolation of the innovation phase: fit x(t) = a + b exp(-t / tau) to iterations 1..k of each run, predict the
  mean over 70-79 (the state when innovation stops), compare with the actual mean; "persistence" (mean over k-9..k)
  is the naive baseline. Errors in sigma units and as the share of the remaining change (actual - persistence) not
  explained by the fit;
- leading indicator: the mean best stored score (MATSim avg_best) at k against the end-state executed score (mean
  over 90-99), i.e. how close "switch innovation off now" would get if every agent then played its best plan.
Only existing per-iteration statistics are read; nothing is simulated."""
import argparse, csv, json, math, sys, warnings
from pathlib import Path
import numpy as np
from scipy.optimize import curve_fit
sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicators import indicators

NAMES = ['score', 'best_score', 'share_car', 'share_pt', 'share_walk', 'share_taxi', 'share_FHV', 'unfinished',
         'car_departures', 'wait_person_hours', 'counts_sim']


def load(run):
    s = indicators(run)
    with open(Path(run)/'simulation'/'BUILT.scorestats.csv', newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            it = int(r['iteration'])
            if it in s: s[it]['best_score'] = float(r['avg_best'])
    return s


def series(s, name, lo, hi):
    return np.array([s[i].get(name, np.nan) if i in s else np.nan for i in range(lo, hi + 1)], float)


def sat(t, a, b, tau): return a + b * np.exp(-t / tau)


def fit_predict(t, y, t_pred):
    ok = np.isfinite(y); t, y = t[ok], y[ok]
    if len(t) < 5: return float('nan')
    p0 = (y[-1], y[0] - y[-1], max(t[-1] / 3, 1.0))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        try:
            p, _ = curve_fit(sat, t, y, p0=p0, bounds=([-np.inf, -np.inf, 0.5], [np.inf, np.inf, 1e4]), maxfev=20000)
        except (RuntimeError, ValueError):
            return float('nan')
    return float(np.mean(sat(np.asarray(t_pred, float), *p)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tolerance'); ap.add_argument('runs', nargs='+'); ap.add_argument('--out', required=True)
    ap.add_argument('--ks', default='10,20,30,40,50,60,70'); a = ap.parse_args()
    tol = json.loads(Path(a.tolerance).read_text())['indicators']
    runs = [load(r) for r in a.runs]; ks = [int(k) for k in a.ks.split(',')]
    out = {'runs': a.runs, 'ks': ks, 'indicators': {}}
    for n in NAMES:
        sigma = tol.get(n, {}).get('sigma', float('nan')) if n != 'best_score' else tol.get('score', {}).get('sigma', float('nan'))
        end = [np.nanmean(series(s, 'score' if n == 'best_score' else n, 90, 99)) for s in runs]
        at79 = [np.nanmean(series(s, n, 70, 79)) for s in runs]
        rows = {}
        for k in ks:
            spread = np.ptp([s[k].get(n, np.nan) for s in runs])
            pers, fit = [], []
            for s in runs:
                y = series(s, n, 1, k); t = np.arange(1, k + 1, dtype=float)
                pers.append(np.nanmean(series(s, n, k - 9, k)))
                fit.append(fit_predict(t, y, range(70, 80)))
            pers, fit = np.array(pers), np.array(fit)
            e_fit, e_pers = fit - np.array(at79), pers - np.array(at79)
            rows[k] = {'seed_spread_sigma': spread / sigma if sigma else float('nan'),
                       'pred_70_79_fit': fit.tolist(), 'actual_70_79': at79,
                       'err_fit_sigma': (e_fit / sigma).tolist() if sigma else None,
                       'err_persistence_sigma': (e_pers / sigma).tolist() if sigma else None,
                       'remaining_change_unexplained': float(np.nanmean(np.abs(e_fit) / np.abs(e_pers))) if np.all(e_pers != 0) else float('nan')}
            if n == 'best_score':
                rows[k]['best_minus_end_score'] = (np.array([s[k]['best_score'] for s in runs]) - np.array(end)).tolist()
                rows[k]['best_fit_70_79_minus_end_score'] = (fit - np.array(end)).tolist()
        out['indicators'][n] = {'sigma': sigma, 'end_90_99': end, 'mean_70_79': at79, 'by_k': rows}
    Path(a.out).write_text(json.dumps(out, indent=1, default=float) + '\n')
    print(f"{'indicator':18} {'sigma':>10} {'70-79':>12} {'90-99':>12} | per k: seed spread/σ, fit err/σ, persistence err/σ, unexplained share")
    for n, v in out['indicators'].items():
        print(f"{n:18} {v['sigma']:10.4g} {np.mean(v['mean_70_79']):12.5g} {np.mean(v['end_90_99']):12.5g}")
        for k, r in v['by_k'].items():
            ef = r['err_fit_sigma']; ep = r['err_persistence_sigma']
            extra = ''
            if 'best_minus_end_score' in r:
                extra = f" | best(k)-end {np.mean(r['best_minus_end_score']):+.2f}, fitted best(70-79)-end {np.nanmean(r['best_fit_70_79_minus_end_score']):+.2f}"
            print(f"   k={k:3d} spread {r['seed_spread_sigma']:6.1f}  fit {np.nanmean(np.abs(ef)) if ef else float('nan'):8.1f}  persist {np.nanmean(np.abs(ep)) if ep else float('nan'):8.1f}  unexpl {r['remaining_change_unexplained']:.2f}{extra}")


if __name__ == '__main__':
    main()

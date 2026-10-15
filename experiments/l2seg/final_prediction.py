#!/usr/bin/env python3
"""P1: from the first k iterations, how well can the end state of the full protocol (mean over iterations 90-99, after
the innovation switch-off at 80) be predicted? (docs/aggregate-regularity-plan.md Section 2.1, methods M1/M7)

  final_prediction.py TOLERANCE.json RUN [RUN ...] --out FILE.json [--ks 20,30,40,50,60]

Indicators as in trajectory.py (A1). Predictors of the final value of run i from iterations 1..k:
single run (uses nothing but run i):
- persist: mean over k-9..k;
- sat: a + b exp(-t/tau) fitted to 1..k, mean over 70-79 (A1's predictor, which ignores the jump at 80);
- lin_sat: a + c t + b exp(-t/tau), mean over 70-79 (for indicators that drift rather than saturate);
learned from the other runs j != i (leave one out; M7, 'learning curves'):
- sat+jump, lin_sat+jump: the above plus the mean jump final_j - mean_70-79_j;
- ratio: persist_i x mean_j(final_j / persist_j);
- shift: persist_i + mean_j(final_j - persist_j);
- best_shift (score only): best stored score at k (scorestats avg_best) + mean_j(final_j - best_j(k)).
The learned predictors transfer between seeds of one scenario, which differ very little; that is an upper bound.
Whether they transfer between policies needs policy runs (plan B3).
Errors: absolute relative error (% of the final value; score in points) and |error| / tolerance sigma; per method,
indicator and k, mean over runs."""
import argparse, json, sys, warnings
from pathlib import Path
import numpy as np
from scipy.optimize import curve_fit
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trajectory import load, series, fit_predict, NAMES

LEARNED = ('sat+jump', 'lin_sat+jump', 'ratio', 'shift', 'best_shift')


def linsat(t, a, c, b, tau): return a + c * t + b * np.exp(-t / tau)


def fit_lin_predict(t, y, t_pred):
    ok = np.isfinite(y); t, y = t[ok], y[ok]
    if len(t) < 6: return float('nan')
    slope = np.polyfit(t[-10:], y[-10:], 1)[0] if len(t) >= 10 else 0.0
    p0 = (y[-1] - slope * t[-1], slope, y[0] - y[-1], max(t[-1] / 3, 1.0))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        try:
            p, _ = curve_fit(linsat, t, y, p0=p0, bounds=([-np.inf, -np.inf, -np.inf, 0.5], [np.inf, np.inf, np.inf, 1e4]), maxfev=20000)
        except (RuntimeError, ValueError):
            return float('nan')
    return float(np.mean(linsat(np.asarray(t_pred, float), *p)))


def predictions(runs, name, k):
    """{method: [prediction per run]} and the finals."""
    final = np.array([np.nanmean(series(s, name, 90, 99)) for s in runs])
    m79 = np.array([np.nanmean(series(s, name, 70, 79)) for s in runs])
    persist = np.array([np.nanmean(series(s, name, k - 9, k)) for s in runs])
    t = np.arange(1, k + 1, dtype=float)
    sat = np.array([fit_predict(t, series(s, name, 1, k), range(70, 80)) for s in runs])
    lsat = np.array([fit_lin_predict(t, series(s, name, 1, k), range(70, 80)) for s in runs])
    best = np.array([s[k].get('best_score', np.nan) if k in s else np.nan for s in runs]) if name == 'score' else None
    P = {'persist': persist, 'sat': sat, 'lin_sat': lsat}
    n = len(runs)
    if n > 1:
        loo = lambda x: np.array([np.mean(np.delete(x, i)) for i in range(n)])
        jump = loo(final - m79)
        P['sat+jump'] = sat + jump; P['lin_sat+jump'] = lsat + jump
        with np.errstate(invalid='ignore', divide='ignore'): P['ratio'] = persist * loo(final / persist)
        P['shift'] = persist + loo(final - persist)
        if best is not None: P['best_shift'] = best + loo(final - best)
    return P, final


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tolerance'); ap.add_argument('runs', nargs='+'); ap.add_argument('--out', required=True)
    ap.add_argument('--ks', default='20,30,40,50,60'); a = ap.parse_args()
    tol = json.loads(Path(a.tolerance).read_text())['indicators']
    runs = [load(r) for r in a.runs]; ks = [int(k) for k in a.ks.split(',')]
    out = {'runs': a.runs, 'ks': ks, 'indicators': {}}
    for name in NAMES:
        if name == 'best_score': continue
        sigma = tol.get(name, {}).get('sigma', float('nan')); rows = {}
        for k in ks:
            P, final = predictions(runs, name, k)
            rows[k] = {m: {'pred': p.tolist(), 'final': final.tolist(),
                           'abs_err': float(np.nanmean(np.abs(p - final))),
                           'rel_err_pct': float(np.nanmean(np.abs(p - final) / np.abs(final))) * 100,
                           'err_sigma': float(np.nanmean(np.abs(p - final)) / sigma) if sigma else float('nan')} for m, p in P.items()}
        out['indicators'][name] = {'sigma': sigma, 'by_k': rows}
    Path(a.out).write_text(json.dumps(out, indent=1, default=float) + '\n')
    methods = list(next(iter(out['indicators'].values()))['by_k'][ks[0]].keys())
    print('relative error of the predicted final (90-99) value, % (score: absolute, points); mean over runs')
    print(f"{'indicator':18} {'k':>3} " + ' '.join(f'{m:>12}' for m in methods))
    for name, v in out['indicators'].items():
        for k in ks:
            r = v['by_k'][k]
            print(f"{name:18} {k:3d} " + ' '.join((f"{(r[m]['abs_err'] if name == 'score' else r[m]['rel_err_pct']):12.2f}" if m in r else f"{'-':>12}") for m in methods))


if __name__ == '__main__':
    main()

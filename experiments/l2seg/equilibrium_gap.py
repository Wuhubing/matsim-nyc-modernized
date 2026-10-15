#!/usr/bin/env python3
"""Selection gap per iteration from the W1 replanning log, and a check of it at the innovation switch-off
(docs/research-charter.md, H0).

  equilibrium_gap.py RUN [RUN ...] --out FILE.json [--jobs 4] [--switch-off 80]

The log is written at the end of each iteration, after scoring: executed_score is the score of the plan executed in
that iteration (its fresh evaluation; with score MSA the running mean), best_score the highest stored score over the
agent's plans (other plans keep the score of their last execution). Selection gap of agent i at k:
    g_i(k) = best_score - executed_score >= 0,
the utility the agent could have had with a plan already in memory, as far as stored scores tell. It is the part of
the gap to equilibrium that is found but not selected; plans not yet in memory (route, mode or time best responses)
are not covered, so it is a lower bound on the full gap.

Per iteration, residents ('man', 'nonman') split by what they did at k:
- selectors (a non-innovative strategy): g as above;
- innovators (executed a new or mutated plan): best - executed is the loss of trying an untested plan.

Check at the switch-off (runs that reach switch_off + 19): from switch_off on only selection is left, so the stored
scores at switch_off - 1 can be compared with what the same agents get later:
    predicted_i = g_i(switch_off - 1), realized_i = mean executed over the last 10 iterations - executed at switch_off - 1.
Reported for selectors at switch_off - 1: Spearman correlation, least-squares slope of realized on predicted, means by
decile of predicted, and the aggregate mean predicted against mean realized. A slope near 1 means stored best scores
are unbiased predictions of what the agents get once they settle; below 1 means they are optimistic (a best of up to
five single noisy evaluations, and an environment that changes once everyone settles)."""
import argparse, csv, gzip, json, sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from logs import ReplanningLog

RESIDENTS = ('man', 'nonman')


def read(job):
    """(k, strategy, executed, best) arrays aligned with persons.csv for iteration k; only the columns needed here."""
    run, k, n, row = job
    strat = np.full(n, -1, np.int16); ex = np.full(n, np.nan); be = np.full(n, np.nan)
    with gzip.open(Path(run)/'simulation'/'replanning-log'/f'agents-{k}.csv.gz', 'rt', newline='') as f:
        r = csv.reader(f); next(r)
        for p, s, _, _, _, e, b, _ in r:
            i = row[int(p)]; strat[i] = int(s)
            if e: ex[i] = float(e)
            if b: be[i] = float(b)
    return k, strat, ex, be


def stats(v):
    v = v[np.isfinite(v)]
    if not len(v): return {'n': 0}
    return {'n': int(len(v)), 'mean': float(v.mean()), 'p50': float(np.median(v)), 'p90': float(np.quantile(v, .9)),
            'share_gt_1': float((v > 1).mean()), 'share_gt_3': float((v > 3).mean())}


def spearman(x, y):
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def check(pred, real):
    ok = np.isfinite(pred) & np.isfinite(real); pred, real = pred[ok], real[ok]
    if not len(pred): return {'n': 0}
    slope = float(np.polyfit(pred, real, 1)[0]) if len(pred) > 2 and pred.std() > 0 else float('nan')
    edges = np.quantile(pred, np.linspace(0, 1, 11)); deciles = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (pred >= lo) & (pred <= hi)
        if m.any(): deciles.append({'pred': float(pred[m].mean()), 'real': float(real[m].mean()), 'n': int(m.sum())})
    return {'n': int(len(pred)), 'spearman': spearman(pred, real) if len(pred) > 2 else float('nan'), 'slope': slope,
            'mean_pred': float(pred.mean()), 'mean_real': float(real.mean()), 'deciles': deciles}


def analyse(run, jobs, switch_off):
    log = ReplanningLog(run); n = len(log.index); row = log.row
    res = np.isin(log.subpopulation, RESIDENTS); innov = np.array(sorted(log.innovative_codes))
    with Pool(jobs) as pool: data = {k: v for k, *v in pool.map(read, [(run, k, n, row) for k in log.iterations])}
    by_k = {}
    for k in sorted(data):
        strat, ex, be = data[k]; inn = np.isin(strat, innov); g = be - ex
        by_k[k] = {'selectors': stats(g[res & ~inn & (strat >= 0)]), 'innovators': stats(g[res & inn]),
                   'innovating_share': float(inn[res].mean()), 'mean_executed': float(np.nanmean(ex[res])),
                   'mean_best': float(np.nanmean(be[res]))}
    out = {'run': run, 'iterations': len(data), 'by_k': by_k}
    last = max(data); k0 = switch_off - 1
    if k0 in data and last >= switch_off + 19:
        strat, ex, be = data[k0]; inn = np.isin(strat, innov)
        later = np.nanmean(np.stack([data[k][1] for k in range(last - 9, last + 1)]), axis=0)
        sel = res & ~inn & (strat >= 0)
        out['switch_off_check'] = {'k0': k0, 'later': [last - 9, last],
                                   'selectors': check((be - ex)[sel], (later - ex)[sel]),
                                   'innovators': check((be - ex)[res & inn], (later - ex)[res & inn]),
                                   'residents_best_vs_later': {'mean_best_k0': float(np.nanmean(be[res])),
                                                               'mean_later': float(np.nanmean(later[res]))}}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('runs', nargs='+'); ap.add_argument('--out', required=True)
    ap.add_argument('--jobs', type=int, default=1); ap.add_argument('--switch-off', type=int, default=80)
    a = ap.parse_args()
    result = {}
    for run in a.runs:
        r = analyse(run, a.jobs, a.switch_off); result[Path(run).name] = r
        print(f'== {Path(run).name}: {r["iterations"]} iterations')
        print(' k  innov%  selectors: mean   p50   p90  >1   >3 | innovators: mean  | executed  best')
        for k, v in r['by_k'].items():
            if k % 10 and k not in (79, 80): continue
            s, i = v['selectors'], v['innovators']
            print(f"{k:2d}  {100*v['innovating_share']:5.1f}  {s.get('mean', np.nan):12.2f} {s.get('p50', np.nan):5.2f} {s.get('p90', np.nan):5.2f}"
                  f" {s.get('share_gt_1', np.nan):.2f} {s.get('share_gt_3', np.nan):.2f} | {i.get('mean', np.nan):10.2f}"
                  f"        | {v['mean_executed']:7.2f} {v['mean_best']:5.2f}")
        c = r.get('switch_off_check')
        if c:
            s = c['selectors']
            print(f"switch-off check (selectors at {c['k0']} vs mean of {c['later']}): n={s['n']} spearman={s['spearman']:.3f}"
                  f" slope={s['slope']:.3f} mean predicted={s['mean_pred']:.3f} realized={s['mean_real']:.3f}")
    Path(a.out).write_text(json.dumps(result, indent=1) + '\n')


if __name__ == '__main__':
    main()

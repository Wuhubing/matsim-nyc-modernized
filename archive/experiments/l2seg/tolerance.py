#!/usr/bin/env python3
"""Tolerance table, steady-state iteration T* and reference match (plan Section 4).

  table RUN...        x_bar and sigma per indicator from reference runs: per run the mean over the window
                      (default iterations 90-99), then mean and sample standard deviation across runs.
                      Also T* per run. Writes --out (JSON) and prints a table.
  check TABLE RUN...  T* of each run and whether its last-10-iteration mean is within k*sigma of x_bar.

T*: the first iteration t such that every indicator stays within k*sigma (k = 2) of x_bar in iterations
t..t+4. Indicators with sigma = 0 across the reference runs must match x_bar exactly and are listed as such.
Indicators missing in some iterations (counts are written at the configured interval) are checked only where
present. These rules are fixed in the plan and are not tuned after seeing results.
"""
import argparse, json, math, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicators import indicators

SKIP = {'counts_obs'}   # observed counts are inputs, identical across runs


def window_mean(series, lo, hi, name):
    vals = [series[i][name] for i in range(lo, hi + 1) if i in series and name in series[i] and not math.isnan(series[i][name])]
    return statistics.fmean(vals) if vals else float('nan')


def build_table(runs, lo, hi):
    series = [indicators(r) for r in runs]
    names = sorted(set.intersection(*(set(k for row in s.values() for k in row) for s in series)) - SKIP)
    for s, r in zip(series, runs):
        if not all(i in s for i in range(lo, hi + 1)): raise SystemExit(f'{r}: iterations {lo}-{hi} incomplete')
    table = {}
    for n in names:
        means = [window_mean(s, lo, hi, n) for s in series]
        table[n] = {'mean': statistics.fmean(means), 'sigma': statistics.stdev(means) if len(means) > 1 else float('nan'), 'run_means': means}
    return table, series


def within(value, entry, k):
    # sigma = 0: equal up to floating-point rounding of the mean
    return abs(value - entry['mean']) <= k * entry['sigma'] if entry['sigma'] > 0 else math.isclose(value, entry['mean'], rel_tol=1e-12, abs_tol=1e-12)


def steady_state(series, table, k=2.0, run_length=5):
    """First iteration starting run_length consecutive iterations with every indicator within tolerance."""
    its = sorted(series); streak = 0
    for i in its:
        ok = all(within(series[i][n], e, k) for n, e in table.items() if n in series[i] and not math.isnan(series[i][n]))
        streak = streak + 1 if ok else 0
        if streak == run_length: return i - run_length + 1
    return None


def match(series, table, k=2.0, last=10):
    its = sorted(series)[-last:]
    result = {}
    for n, e in table.items():
        m = window_mean(series, its[0], its[-1], n)
        result[n] = {'last_mean': m, 'z': (m - e['mean']) / e['sigma'] if e['sigma'] > 0 else (0.0 if within(m, e, k) else math.inf),
                     'within': within(m, e, k)}
    return all(v['within'] for v in result.values()), result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('table'); t.add_argument('runs', nargs='+'); t.add_argument('--window', nargs=2, type=int, default=[90, 99])
    t.add_argument('--k', type=float, default=2.0); t.add_argument('--out', required=True)
    c = sub.add_parser('check'); c.add_argument('table'); c.add_argument('runs', nargs='+'); c.add_argument('--k', type=float, default=2.0)
    a = ap.parse_args()
    if a.cmd == 'table':
        table, series = build_table(a.runs, *a.window)
        tstar = {r: steady_state(s, table, a.k) for r, s in zip(a.runs, series)}
        Path(a.out).write_text(json.dumps({'window': a.window, 'k': a.k, 'runs': a.runs, 'indicators': table, 't_star': tstar}, indent=2) + '\n')
        print(f"{'indicator':28} {'mean':>14} {'sigma':>12} {'sigma/|mean|':>12}")
        for n, e in table.items():
            rel = e['sigma'] / abs(e['mean']) if e['mean'] else float('nan')
            print(f"{n:28} {e['mean']:14.6g} {e['sigma']:12.4g} {rel:12.2e}{'  (sigma = 0: exact match required)' if e['sigma'] == 0 else ''}")
        for r, v in tstar.items(): print('T*', r, v)
    else:
        spec = json.loads(Path(a.table).read_text()); table = spec['indicators']; ok_all = True
        for r in a.runs:
            s = indicators(r); ok, detail = match(s, table, a.k); ok_all &= ok
            worst = max(detail.items(), key=lambda kv: abs(kv[1]['z']))
            print(r, 'T*', steady_state(s, table, a.k), 'matches' if ok else 'DOES NOT match', 'max |z|', worst[0], f"{worst[1]['z']:.2f}")
        sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()

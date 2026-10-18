#!/usr/bin/env python3
"""Per-indicator policy-effect paths: for each 10-iteration window start t, the seed-mean Delta(t) = policy - baseline
(same seed, same arm) minus the final reference Delta, in units of the acceptance tolerance epsilon (04 section 6).
Arms: cold reference (RQ1 baseline + policy references) and E1 (elite baseline + elite policies).

  delta_paths.py --root .../matsim-work --ref deltas-reference.json --out paths.json [--arm elite]

--arm: run-directory prefix of the arm under test (elite = E1, elite-tamrr = E3, warm = W0/W1); output keys keep 'e1'.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compute_deltas as cd                                   # noqa: E402
from analyze_e1_x1_w1 import EPS, SEEDS, n_iters              # noqa: E402

IND = ('legs_car_charging:related', 'share_car', 'share_pt', 'revenue', 'cordon_entries')
STARTS = list(range(30, 91, 5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); ap.add_argument('--ref', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--arm', default='elite'); a = ap.parse_args()
    R = Path(a.root); P = R/'policy'; ref = json.loads(Path(a.ref).read_text())
    runs = {('cold', 'baseline'): {s: R/'rq1'/f'baseline-s{s}-100it-rq1' for s in SEEDS}}
    for p in ('schema1', 'schema2'):
        runs[('cold', p)] = {s: P/f'{p}-s{s}-100it' for s in SEEDS}
    for p in ('baseline', 'schema1', 'schema2'):
        runs[('e1', p)] = {s: d for s in SEEDS if n_iters(d := P/f'{a.arm}-{p}-s{s}-100it') >= 100}
    T = {k: {s: [cd.iteration_indicators(d, it) for it in range(100)] for s, d in v.items()} for k, v in runs.items()}
    out = {}
    for p in ('schema1', 'schema2'):
        target = {k: float(np.mean(list(ref['policies'][p]['indicators'][k]['delta'].values()))) for k in IND}
        for arm in ('cold', 'e1'):
            seeds = [s for s in T[(arm, p)] if s in T[(arm, 'baseline')]]
            rows = {}
            for k in IND:
                vals = []
                for t in range(91):
                    d = np.mean([np.mean([T[(arm, p)][s][i][k] - T[(arm, 'baseline')][s][i][k] for i in range(t, t + 10)])
                                 for s in seeds])
                    vals.append((d - target[k]) / EPS[p][k])
                stay = next((t for t in range(91) if all(abs(v) <= 1 for v in vals[t:])), None)
                rows[k] = {'by_start': {t: vals[t] for t in STARTS}, 'stays_within_from': stay}
            all_stay = next((t for t in range(91) if all(all(abs(rows[k]['by_start'].get(u, 0)) <= 1 for k in IND)
                                                       for u in STARTS if u >= t)), None)
            out[f'{p}-{arm}'] = rows
            print(f'\n== {p} {arm} (seeds {seeds}): (Delta(t) - final reference Delta) / eps, window t..t+9')
            print(f"  {'indicator':28}" + ''.join(f'{t:>7}' for t in STARTS) + '   stays within from')
            for k in IND:
                r = rows[k]
                print(f'  {k:28}' + ''.join(f"{r['by_start'][t]:+7.2f}" for t in STARTS) + f"   {r['stays_within_from']}")
            first_all = max((rows[k]['stays_within_from'] if rows[k]['stays_within_from'] is not None else 999) for k in IND)
            print(f'  all indicators stay within from t = {first_all if first_all < 999 else None}')
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')


if __name__ == '__main__':
    main()

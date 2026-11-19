#!/usr/bin/env python3
"""A5 (network): step-by-step dynamics of the link-hour travel-time field, read as L2Seg reads a solver step
(docs/aggregate-regularity-plan.md Section 2.1). The travel-time field is what agents see of each other.

  link_dynamics.py RUN --out FILE.json [--window 5] [--min-traversals 5]

Rows: link-hours (car, taxi and FHV pooled, entry hour; research/link-hours-N.csv.gz) with at least --min-traversals
completed traversals per iteration over 90-99, weighted by those traversals (as link_stability.py). Values: log of
the travel time, so changes are relative. Metrics: dynamics() of group_dynamics.py (signal share, concentration of
the next change, whether the current change predicts where the next one happens, direction cosine, linear
extrapolation vs persistence), for t with t + W <= 79."""
import argparse, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from link_stability import LinkHours, pad, travel_time
from group_dynamics import dynamics, noise_sd, LAST


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True)
    ap.add_argument('--window', type=int, default=5); ap.add_argument('--min-traversals', type=float, default=5)
    a = ap.parse_args(); W = a.window; ts = list(range(2 * W, LAST - W + 1, 5))
    lh = LinkHours(a.run); rc = np.zeros(0)
    for t in range(90, 100):
        c, s = lh.read(t); rc = pad(rc, len(c), 0.0) + c
    keep = np.flatnonzero(rc / 10 >= a.min_traversals); size = len(rc)
    Y = np.full((len(keep), LAST + 1), np.nan, np.float32)
    for t in range(0, LAST + 1):
        tt = pad(travel_time(*lh.read(t)), size)
        with np.errstate(invalid='ignore', divide='ignore'): Y[:, t] = np.log(tt[keep])
        if t % 10 == 0: print(f'iteration {t} read', flush=True)
    w = rc[keep]; res = dynamics(Y, w, noise_sd(Y), ts, W)
    out = {'run': a.run, 'window': W, 'min_traversals': a.min_traversals, 'cells': int(len(keep)),
           'coverage_traversals': float(w.sum() / rc.sum()), 'by_t': res}
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    print(f"{len(keep)} link-hours, {out['coverage_traversals']:.3f} of traversals")
    print('per t: signal share | top20 energy | top20 recall (0.2 = random) | spearman |z0|,|z1| | cos | extrapolation/persistence m=5,10,20 | persistence/noise m5')
    for t, r in res.items():
        ex = ' '.join(f"{r[f'm{x}']['ratio']:.2f}" if f'm{x}' in r else '  - ' for x in (5, 10, 20))
        print(f"  t={t:2d}  {r['signal_share']:.2f} | {r['top20_energy']:.2f} | {r['top20_recall']:.2f} | {r['spearman_abs']:+.2f} | {r['cos']:+.2f} | {ex} | "
              f"{r['m5']['persistence'] / r['m5']['noise_floor']:.2f}")


if __name__ == '__main__':
    main()

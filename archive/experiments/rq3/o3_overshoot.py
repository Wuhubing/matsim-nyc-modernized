#!/usr/bin/env python3
"""O3: does best-responding to the previous iteration overshoot (Cournot adjustment)?

MATSim 2026.0 routes on the previous iteration's travel times only (TravelTimeCalculator.reset clears them each
iteration). At iteration k ReRoute routes a copy of a stored plan on T(k-1). If many agents move at once, the routes
that looked best under T(k-1) gain less under T(k), the traffic they actually meet.

  o3_overshoot.py RUN --out FILE.json [--ks 10,20,30,40,50,60,70] [--jobs 4]

For every ReRoute innovation at snapshot iteration k (as in route_gap.py), the parent route and the new route of each
network leg are re-estimated with the same router-like estimator on three travel-time fields:
  T(k-1)  what the router saw (predicted gain);
  T(k)    the traffic of the iteration in which the new plan is executed (realised-environment gain);
  T(k+1)  one iteration later (persistence).
Gain = sum(T_parent - T_new) / sum(T_parent) over legs present in both plans with the same index; also the share of legs
whose new route is >1% faster. Both routes are evaluated on the same field each time, so estimator bias common to both
largely cancels. Car, taxi and FHV link-hour means are pooled, as in route_gap.py."""
import argparse, json, os, sys
import xml.etree.ElementTree as ET
from multiprocessing import Pool
from pathlib import Path
import numpy as np

_SIBLING = Path(__file__).resolve().parent.parent/'l2seg'
REPO = Path(os.environ.get('L2SEG_DIR', str(_SIBLING if _SIBLING.is_dir() else Path.home()/'matsim-work'/'matsim-nyc-modernized'/'experiments'/'l2seg')))
sys.path.insert(0, str(REPO))
from logs import ReplanningLog                    # noqa: E402
from plans_stats import stream                    # noqa: E402
from plan_snapshots import snapshot_path          # noqa: E402
from link_stability import LinkHours, route_kinds  # noqa: E402
import route_gap                                  # noqa: E402

H = 32
OFFSETS = (-1, 0, 1)


def field(lh, t):
    cnt, sec = lh.read(t)
    with np.errstate(invalid='ignore', divide='ignore'):
        mean = np.where(cnt > 0, sec / cnt, np.nan)
    def tt(link, hour):
        i = lh.idx.get(link)
        if i is None or (i + 1) * H > len(mean):
            return None
        v = mean[i * H + min(max(hour, 0), H - 1)]
        return None if np.isnan(v) else float(v)
    return tt


def at(job):
    run, k = job
    route_gap.load_network(run)
    log = ReplanningLog(run); codes = route_kinds(run)
    a, prev = log.agents(k), log.agents(k - 1)
    rows = np.nonzero(a['innovated'] & (a['created'] == k) & np.isin(a['strategy'], list(codes)))[0]
    want = {log.person_id[i]: (int(a['parent'][i]), bool(a['parent'][i] == prev['plan'][i])) for i in rows}
    lh = LinkHours(run)
    fields = {off: field(lh, k + off) for off in OFFSETS}
    acc = {off: {'all': [0.0, 0.0, 0, 0], 'executed': [0.0, 0.0, 0, 0]} for off in OFFSETS}
    with stream(snapshot_path(run, k)) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person':
                continue
            w = want.get(el.get('id'))
            if w is not None:
                par = new = None
                for p in el.findall('plan'):
                    pid = p.find("attributes/attribute[@name='planId']"); cr = p.find("attributes/attribute[@name='iterationCreated']")
                    if pid is None or int(pid.text, 36) != w[0]:
                        continue
                    if cr is not None and int(cr.text) == k:
                        new = route_gap.legs_of(p)
                    else:
                        par = route_gap.legs_of(p)
                if par is not None and new is not None and len(par) == len(new):
                    for lp, ln in zip(par, new):
                        if lp is None or ln is None or len(lp[1]) < 2 or len(ln[1]) < 2:
                            continue
                        for off in OFFSETS:
                            tt = fields[off]
                            tp, tn = route_gap.estimate(lp[1], lp[0], tt), route_gap.estimate(ln[1], ln[0], tt)
                            for key in (('all', 'executed') if w[1] else ('all',)):
                                r = acc[off][key]; r[0] += tp; r[1] += tp - tn; r[2] += 1; r[3] += (tn < 0.99 * tp)
            root.remove(el)
    out = {'reroutes': int(len(rows))}
    for off in OFFSETS:
        name = {-1: 'predicted_T(k-1)', 0: 'realised_T(k)', 1: 'next_T(k+1)'}[off]
        out[name] = {key: {'legs': r[2], 'gain': r[1] / r[0] if r[0] else float('nan'),
                           'share_new_faster_1pct': r[3] / r[2] if r[2] else float('nan')} for key, r in acc[off].items()}
    p, q = out['predicted_T(k-1)']['all']['gain'], out['realised_T(k)']['all']['gain']
    out['realised_over_predicted'] = q / p if p else float('nan')
    return k, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True)
    ap.add_argument('--ks', default='10,20,30,40,50,60,70'); ap.add_argument('--jobs', type=int, default=1)
    a = ap.parse_args(); ks = [int(x) for x in a.ks.split(',')]
    with Pool(a.jobs) as pool:
        res = dict(pool.map(at, [(a.run, k) for k in ks]))
    Path(a.out).write_text(json.dumps({'run': a.run, 'by_k': res}, indent=1) + '\n')
    print(' k  reroutes | gain T(k-1)  T(k)  T(k+1) | faster>1%: T(k-1)  T(k)  T(k+1) | realised/predicted')
    for k, r in sorted(res.items()):
        g = [r[n]['all']['gain'] for n in ('predicted_T(k-1)', 'realised_T(k)', 'next_T(k+1)')]
        s = [r[n]['all']['share_new_faster_1pct'] for n in ('predicted_T(k-1)', 'realised_T(k)', 'next_T(k+1)')]
        print(f"{k:2d} {r['reroutes']:8d} | {g[0]:.3f} {g[1]:.3f} {g[2]:.3f} | {s[0]:.3f} {s[1]:.3f} {s[2]:.3f} | {r['realised_over_predicted']:.2f}")


if __name__ == '__main__':
    main()

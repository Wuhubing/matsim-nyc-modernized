#!/usr/bin/env python3
"""O4: would a minimum predicted saving keep the useful re-routes and drop the overshooting ones? (modification 2)

  o4_reroute_threshold.py RUN --out FILE.json [--ks 10,20,30,40,50,60,70] [--jobs 4]

Same re-routes and estimator as o3_overshoot.py, but per plan: predicted saving = sum over legs (T_parent - T_new) /
sum T_parent on T(k-1) (what the router saw), realised saving on T(k) and on T(k+1). Plans are binned by predicted
saving; per bin: count, share with realised saving > 0 and > 1%, mean realised saving. For thresholds on the
predicted saving: share of re-routes kept and the realised saving of the kept ones (sum-weighted)."""
import argparse, json, os, sys
import xml.etree.ElementTree as ET
from multiprocessing import Pool
from pathlib import Path
import numpy as np

_SIBLING = Path(__file__).resolve().parent.parent/'l2seg'
REPO = Path(os.environ.get('L2SEG_DIR', str(_SIBLING if _SIBLING.is_dir() else Path.home()/'matsim-work'/'matsim-nyc-modernized'/'experiments'/'l2seg')))
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(Path(__file__).resolve().parent))
from logs import ReplanningLog                    # noqa: E402
from plans_stats import stream                    # noqa: E402
from plan_snapshots import snapshot_path          # noqa: E402
from link_stability import LinkHours, route_kinds  # noqa: E402
import route_gap                                  # noqa: E402
from o3_overshoot import field, OFFSETS           # noqa: E402

BINS = [(-1e9, 0.0, '<= 0'), (0.0, 0.05, '(0, 5%]'), (0.05, 0.10, '(5, 10%]'), (0.10, 0.20, '(10, 20%]'),
        (0.20, 0.40, '(20, 40%]'), (0.40, 1e9, '> 40%')]
THRESHOLDS = (0.0, 0.02, 0.05, 0.10, 0.20, 0.30)


def at(job):
    run, k = job
    route_gap.load_network(run)
    log = ReplanningLog(run); codes = route_kinds(run)
    a = log.agents(k)
    rows = np.nonzero(a['innovated'] & (a['created'] == k) & np.isin(a['strategy'], list(codes)))[0]
    want = {log.person_id[i]: int(a['parent'][i]) for i in rows}
    lh = LinkHours(run); fields = {off: field(lh, k + off) for off in OFFSETS}
    plans = []                                     # per plan: [parent and new sums per offset]
    with stream(snapshot_path(run, k)) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person':
                continue
            pid0 = want.get(el.get('id'))
            if pid0 is not None:
                par = new = None
                for p in el.findall('plan'):
                    pid = p.find("attributes/attribute[@name='planId']"); cr = p.find("attributes/attribute[@name='iterationCreated']")
                    if pid is None or int(pid.text, 36) != pid0:
                        continue
                    if cr is not None and int(cr.text) == k:
                        new = route_gap.legs_of(p)
                    else:
                        par = route_gap.legs_of(p)
                if par is not None and new is not None and len(par) == len(new):
                    sums = {off: [0.0, 0.0] for off in OFFSETS}; n = 0
                    for lp, ln in zip(par, new):
                        if lp is None or ln is None or len(lp[1]) < 2 or len(ln[1]) < 2:
                            continue
                        n += 1
                        for off in OFFSETS:
                            sums[off][0] += route_gap.estimate(lp[1], lp[0], fields[off])
                            sums[off][1] += route_gap.estimate(ln[1], ln[0], fields[off])
                    if n and all(sums[o][0] > 0 for o in OFFSETS):
                        plans.append([sums[o][i] for o in OFFSETS for i in (0, 1)])
            root.remove(el)
    return k, plans


def analyse(P):
    P = np.array(P).reshape(-1, 6)
    tp = {o: P[:, 2 * j] for j, o in enumerate(OFFSETS)}; tn = {o: P[:, 2 * j + 1] for j, o in enumerate(OFFSETS)}
    pred = (tp[-1] - tn[-1]) / tp[-1]; real = (tp[0] - tn[0]) / tp[0]; nxt = (tp[1] - tn[1]) / tp[1]
    res = {'n': int(len(pred)), 'bins': {}, 'thresholds': {}}
    for lo, hi, name in BINS:
        m = (pred > lo) & (pred <= hi)
        res['bins'][name] = {'n': int(m.sum()), 'share': float(m.mean()) if len(m) else None,
                             'realised_positive': float((real[m] > 0).mean()) if m.any() else None,
                             'realised_above_1pct': float((real[m] > 0.01).mean()) if m.any() else None,
                             'mean_realised': float(real[m].mean()) if m.any() else None,
                             'mean_next': float(nxt[m].mean()) if m.any() else None}
    for th in THRESHOLDS:
        m = pred > th
        res['thresholds'][f'{th:.2f}'] = {'kept_share': float(m.mean()),
                                          'kept_realised_gain': float((tp[0][m] - tn[0][m]).sum() / tp[0][m].sum()) if m.any() else None,
                                          'dropped_realised_gain': float((tp[0][~m] - tn[0][~m]).sum() / tp[0][~m].sum()) if (~m).any() else None}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True)
    ap.add_argument('--ks', default='10,20,30,40,50,60,70'); ap.add_argument('--jobs', type=int, default=1)
    a = ap.parse_args(); ks = [int(x) for x in a.ks.split(',')]
    with Pool(a.jobs) as pool:
        res = dict(pool.map(at, [(a.run, k) for k in ks]))
    out = {'run': a.run, 'by_k': {k: analyse(v) for k, v in res.items() if v},
           'pooled': analyse([p for v in res.values() for p in v])}
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    r = out['pooled']
    print(f"pooled plans {r['n']}\npredicted saving bin   n      share  realised>0  realised>1%  mean realised  mean next")
    for name, b in r['bins'].items():
        if b['n']:
            print(f"  {name:12} {b['n']:8d} {b['share']:.3f}   {b['realised_positive']:.3f}      {b['realised_above_1pct']:.3f}       {b['mean_realised']:+.3f}      {b['mean_next']:+.3f}")
    print('threshold  kept share  kept realised gain  dropped realised gain')
    for th, t in r['thresholds'].items():
        kg = '-' if t['kept_realised_gain'] is None else f"{t['kept_realised_gain']:+.3f}"
        dg = '-' if t['dropped_realised_gain'] is None else f"{t['dropped_realised_gain']:+.3f}"
        print(f"  {th}      {t['kept_share']:.3f}       {kg}              {dg}")


if __name__ == '__main__':
    main()

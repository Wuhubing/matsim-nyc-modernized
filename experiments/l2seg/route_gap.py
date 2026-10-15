#!/usr/bin/env python3
"""Route-choice relative gap: how far are the car routes agents hold from the best response under the travel times
they face? A measure of distance to (route) equilibrium, independent of mode shares.

  route_gap.py RUN --out FILE.json [--ks 10,20,30,40,50,60,70] [--jobs 4]

MATSim's ReRoute is a best response: at iteration k it routes a copy of a plan on the travel times of iteration k-1.
In the snapshot at k (written after the replanning of k) a plan re-routed at k sits next to its parent (same planId,
iterationCreated = k), so both routes of every ReRoute innovation at k are available. Both are re-estimated on the same
travel-time field: link-hour mean travel times of iteration k-1 (research/link-hours-(k-1), car, taxi and FHV pooled,
entry hour), with the network's free-flow time where a link-hour has no traversal; like the router, the start link is
skipped, each further link is entered at the accumulated time and the end link is added at free-flow speed.
Relative gap at k = sum(T_parent - T_new) / sum(T_parent) over network legs (route type 'links') present in both
plans with the same index. Also reported: the share of legs whose new route is >1% faster, the gap for parents that
were the plan executed at k-1 (the state agents actually play), and how well the estimate matches the router's own
estimate stored on the new legs (ratio T_new / stored; the router uses 15-minute bins and its own data).
Caveats: the router minimises generalised cost (time plus distance cost; tolls are zero in the baseline), so a new
route can be slower in time; the gap is in travel time only. Only ReRoute innovations (about 10% of man and nonman
per iteration; the parent is a random stored plan) are sampled."""
import argparse, json, sys
import xml.etree.ElementTree as ET
from multiprocessing import Pool
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from logs import ReplanningLog
from plans_stats import stream
from plan_snapshots import snapshot_path, seconds
from link_stability import LinkHours, route_kinds

NET = {}   # link id -> (length m, free speed m/s); filled in main before the pool forks


def load_network(run):
    with stream(Path(run)/'simulation'/'BUILT.output_network.xml.zst') as f:
        for ev, el in ET.iterparse(f):
            if el.tag == 'link':
                NET[el.get('id')] = (float(el.get('length')), float(el.get('freespeed')))
                el.clear()


def estimate(links, dep, tt):
    """Router-like travel time of a link route (list of link ids, start and end link included) departing at dep.
    tt(link, hour) -> mean travel time or None."""
    t = dep
    for l in links[1:-1]:
        v = tt(l, int(t // 3600))
        t += v if v is not None else NET[l][0] / NET[l][1]
    end = NET[links[-1]]
    return (t - dep) + end[0] / end[1]


def legs_of(plan):
    out = []
    for leg in plan.findall('leg'):
        r = leg.find('route')
        if r is not None and r.get('type') == 'links' and r.text and np.isfinite(seconds(leg.get('dep_time'))):
            out.append((seconds(leg.get('dep_time')), r.text.split(), seconds(r.get('trav_time'))))
        else:
            out.append(None)
    return out


def gap_at(job):
    run, k = job
    log = ReplanningLog(run); codes = route_kinds(run)
    a, prev = log.agents(k), log.agents(k - 1)
    rows = np.nonzero(a['innovated'] & (a['created'] == k) & np.isin(a['strategy'], list(codes)))[0]
    want = {log.person_id[i]: (int(a['parent'][i]), bool(a['parent'][i] == prev['plan'][i])) for i in rows}
    lh = LinkHours(run); cnt, sec = lh.read(k - 1)
    with np.errstate(invalid='ignore', divide='ignore'): mean = np.where(cnt > 0, sec / cnt, np.nan)
    H = 32
    def tt(link, hour):
        i = lh.idx.get(link)
        if i is None: return None
        v = mean[i * H + min(max(hour, 0), H - 1)]
        return None if np.isnan(v) else float(v)
    res = {'all': [0.0, 0.0, 0, 0], 'executed': [0.0, 0.0, 0, 0]}; ratio = []
    with stream(snapshot_path(run, k)) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            w = want.get(el.get('id'))
            if w is not None:
                par = new = None
                for p in el.findall('plan'):
                    pid = p.find("attributes/attribute[@name='planId']"); cr = p.find("attributes/attribute[@name='iterationCreated']")
                    if pid is None or int(pid.text, 36) != w[0]: continue
                    if cr is not None and int(cr.text) == k: new = legs_of(p)
                    else: par = legs_of(p)
                if par is not None and new is not None and len(par) == len(new):
                    for lp, ln in zip(par, new):
                        if lp is None or ln is None or len(lp[1]) < 2 or len(ln[1]) < 2: continue
                        tp, tn = estimate(lp[1], lp[0], tt), estimate(ln[1], ln[0], tt)
                        for key in ('all', 'executed') if w[1] else ('all',):
                            r = res[key]; r[0] += tp; r[1] += tp - tn; r[2] += 1; r[3] += (tn < 0.99 * tp)
                        if ln[2] and ln[2] > 0: ratio.append(tn / ln[2])
            root.remove(el)
    out = {'reroutes': int(len(rows))}
    for key, r in res.items():
        out[key] = {'legs': r[2], 'relative_gap': r[1] / r[0] if r[0] else float('nan'), 'share_new_faster_1pct': r[3] / r[2] if r[2] else float('nan')}
    ratio = np.array(ratio)
    out['estimate_vs_router'] = {'median_ratio': float(np.median(ratio)) if len(ratio) else float('nan'),
                                 'p10': float(np.quantile(ratio, .1)) if len(ratio) else float('nan'),
                                 'p90': float(np.quantile(ratio, .9)) if len(ratio) else float('nan')}
    return k, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True)
    ap.add_argument('--ks', default='10,20,30,40,50,60,70'); ap.add_argument('--jobs', type=int, default=1)
    a = ap.parse_args(); ks = [int(x) for x in a.ks.split(',')]
    load_network(a.run); print(f'network: {len(NET)} links', flush=True)
    with Pool(a.jobs) as pool: res = dict(pool.map(gap_at, [(a.run, k) for k in ks]))
    Path(a.out).write_text(json.dumps({'run': a.run, 'by_k': res}, indent=1) + '\n')
    print('k   reroutes  legs    rel.gap  new>1%faster | executed parents: legs  rel.gap | estimate/router median (p10-p90)')
    for k, r in res.items():
        e = r['estimate_vs_router']
        print(f"{k:2d} {r['reroutes']:8d} {r['all']['legs']:7d} {r['all']['relative_gap']:8.4f} {r['all']['share_new_faster_1pct']:8.3f}"
              f"     | {r['executed']['legs']:7d} {r['executed']['relative_gap']:8.4f} | {e['median_ratio']:.3f} ({e['p10']:.3f}-{e['p90']:.3f})")


if __name__ == '__main__':
    main()

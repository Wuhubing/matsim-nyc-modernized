#!/usr/bin/env python3
"""A4: how stable are link-hour travel times, and can 'nothing on my route changed' spot a duplicate ReRoute before
routing? (docs/aggregate-regularity-plan.md Sections 3.1 and 5, method M8)

  link_stability.py RUN --out FILE.json [--ts 10,20,30,40,50,60,70] [--min-traversals 5]

Link-hour travel time = total_traversal_seconds / completed_traversals summed over car, taxi and FHV (they share
the road), by entry hour (research/link-hours-N.csv.gz). Reference = iterations 90-99 pooled.
Part 1, every iteration: traversal-weighted share of link-hours whose travel time is within 2/5/10% of the previous
iteration and within 5/10/20% of the reference; settling iteration = last iteration up to 79 outside the band + 1.
Only link-hours with at least --min-traversals completed traversals per iteration over 90-99 (the population is a
15% sample, thinner cells are mostly noise); their share of all traversals is reported. A link-hour without
traversals in an iteration is skipped for that iteration.
Part 2, ReRoute innovations (RandomPlanSelector_ReRoute) at t+1 for t in --ts: the parent comes from the snapshot
at t (plans as executed in t; ReRoute at t+1 routes on the travel times of t). Duplicate = trips-(t+1) shows no mode
and no route change in any trip (as in innovation_outcomes.py). Features over the parent's network legs (route type
'links'; every link takes the hour of its leg's departure; link-hours without data in either iteration are left out):
- since: relative change of the summed route travel time between iteration c-1 and t, c = the parent's
  iterationCreated (exact when c's mutator re-routed; time mutation and initial plans keep older routes, reported
  separately as 'route age approximate'; c = 0 uses iteration 0);
- last: the same between t-1 and t.
Reported per t and pooled: duplicate share overall and for parents without network legs; duplicate share by feature
bin; AUC (small change -> duplicate); for thresholds e the share of all ReRoute innovations with feature <= e
('skippable') and the duplicate share among them (precision)."""
import argparse, csv, gzip, json, sys
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from scipy.stats import rankdata
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plans_stats import stream
from plan_snapshots import seconds, snapshot_path

H = 32
PREV_BANDS = (0.02, 0.05, 0.10); REF_BANDS = (0.05, 0.10, 0.20)
BINS = (0, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, np.inf); THRESHOLDS = (0.002, 0.005, 0.01, 0.02, 0.05)


class LinkHours:
    def __init__(self, run):
        self.dir = Path(run)/'simulation'/'research'; self.idx = {}

    def cell(self, link, hour):
        k = self.idx.get(link)
        if k is None: k = self.idx[link] = len(self.idx)
        return k * H + min(max(hour, 0), H - 1)

    def read(self, t):
        """(completed traversals, traversal seconds) per cell, arrays of length len(idx) * H at read time."""
        cells, n, sec = [], [], []
        with gzip.open(self.dir/f'link-hours-{t}.csv.gz', 'rt') as f:
            r = csv.reader(f); h = next(r)
            il, ih, ic, isec = h.index('link_id'), h.index('entry_hour'), h.index('completed_traversals'), h.index('total_traversal_seconds')
            for row in r:
                cells.append(self.cell(row[il], int(row[ih]))); n.append(float(row[ic])); sec.append(float(row[isec]))
        size = len(self.idx) * H; cells = np.array(cells, np.int64)
        return np.bincount(cells, weights=n, minlength=size), np.bincount(cells, weights=sec, minlength=size)


def pad(x, size, fill=np.nan):
    return x if len(x) >= size else np.concatenate([x, np.full(size - len(x), fill, x.dtype)])


def travel_time(cnt, sec):
    with np.errstate(invalid='ignore', divide='ignore'): return np.where(cnt > 0, sec / cnt, np.nan).astype(np.float32)


def route_kinds(run):
    with open(Path(run)/'simulation'/'replanning-log'/'strategies.csv', newline='') as f:
        return {int(r['strategy']) for r in csv.DictReader(f) if r['description'].startswith('RandomPlanSelector_ReRoute')}


def reroute_innovations(run, t1, codes):
    """{person_id: (parent plan id as int, duplicate)} for ReRoute innovations at iteration t1."""
    d = Path(run)/'simulation'/'replanning-log'
    with gzip.open(d/'persons.csv.gz', 'rt') as f:
        pid = {r['person']: r['person_id'] for r in csv.DictReader(f)}
    parent = {}
    with gzip.open(d/f'agents-{t1}.csv.gz', 'rt') as f:
        for r in csv.DictReader(f):
            if int(r['strategy']) in codes and r['parent_plan_id']: parent[r['person']] = int(r['parent_plan_id'], 36)
    changed = {}
    with gzip.open(d/f'trips-{t1}.csv.gz', 'rt') as f:
        for r in csv.DictReader(f):
            if r['person'] in parent:
                changed[r['person']] = changed.get(r['person'], False) or r['trip'] == '-1' or r['mode_changed'] == '1' or r['route_changed'] == '1'
    return {pid[p]: (pl, not changed.get(p, False)) for p, pl in parent.items() if p in changed}


def parent_routes(run, t, wanted, lh):
    """{person_id: (iterationCreated, mutator, cells of network legs)} for the parent plans in the snapshot at t."""
    out = {}
    with stream(snapshot_path(run, t)) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            w = wanted.get(el.get('id'))
            if w is not None:
                for plan in el.findall('plan'):
                    a = {x.get('name'): x.text for x in plan.findall('attributes/attribute')}
                    if a.get('planId') is None or int(a['planId'], 36) != w: continue
                    cells = []
                    for leg in plan.findall('leg'):
                        r = leg.find('route')
                        if r is None or r.get('type') != 'links' or not r.text: continue
                        hour = int(seconds(leg.get('dep_time')) // 3600) if leg.get('dep_time') else 0
                        cells.extend(lh.cell(l, hour) for l in r.text.split())
                    out[el.get('id')] = (int(a.get('iterationCreated', 0)), a.get('planMutator', ''), np.array(cells, np.int64))
                    break
            root.remove(el)
    return out


def wshare(ok, w): return float(w[ok].sum() / w.sum()) if w.sum() else float('nan')


def auc(f, dup):
    """P(feature of a duplicate < feature of a non-duplicate), ties half."""
    ok = np.isfinite(f); f, dup = f[ok], dup[ok]; n1, n0 = dup.sum(), (~dup).sum()
    if not n1 or not n0: return float('nan')
    r = rankdata(-f); return float((r[dup].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def evaluate(rows):
    """rows: list of (duplicate, since, last, exact_age, has_network)."""
    if not rows: return {}
    dup = np.array([r[0] for r in rows]); net = np.array([r[4] for r in rows]); exact = np.array([r[3] for r in rows])
    out = {'innovations': len(rows), 'duplicate_share': float(dup.mean()), 'no_network_share': float((~net).mean()),
           'duplicate_share_no_network': float(dup[~net].mean()) if (~net).any() else float('nan')}
    for j, name in ((1, 'since'), (2, 'last')):
        f = np.array([r[j] for r in rows], float)
        b = np.digitize(f, BINS[1:-1])
        out[name] = {'auc': auc(f, dup), 'auc_exact_age': auc(np.where(exact, f, np.nan), dup),
                     'bins': [{'lo': BINS[i], 'hi': BINS[i + 1], 'n': int(((b == i) & np.isfinite(f)).sum()),
                               'duplicate_share': float(dup[(b == i) & np.isfinite(f)].mean()) if ((b == i) & np.isfinite(f)).any() else float('nan')}
                              for i in range(len(BINS) - 1)],
                     'thresholds': [{'e': e, 'skippable_share': float((f <= e).mean()),
                                     'precision': float(dup[f <= e].mean()) if (f <= e).any() else float('nan')} for e in THRESHOLDS]}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True)
    ap.add_argument('--ts', default='10,20,30,40,50,60,70'); ap.add_argument('--min-traversals', type=float, default=5)
    a = ap.parse_args(); ts = [int(x) for x in a.ts.split(',')]
    lh = LinkHours(a.run)

    # reference 90-99 (kept for the stream below)
    cache, rc, rs = {}, np.zeros(0), np.zeros(0)
    for t in range(90, 100):
        c, s = lh.read(t); size = len(c); rc, rs = pad(rc, size, 0.0) + c, pad(rs, size, 0.0) + s; cache[t] = travel_time(c, s)
    print('reference read', flush=True)

    # part 2 inputs: parents of ReRoute innovations
    codes = route_kinds(a.run); inno = {}
    for t in ts:
        want = reroute_innovations(a.run, t + 1, codes)
        routes = parent_routes(a.run, t, {p: v[0] for p, v in want.items()}, lh)
        inno[t] = [(want[p][1], c, m, cells) for p, (c, m, cells) in routes.items()]
        print(f'snapshot {t}: {len(want)} ReRoute innovations at {t + 1}, {len(routes)} parents found', flush=True)
    need = np.unique(np.concatenate([x[3] for v in inno.values() for x in v] or [np.zeros(0, np.int64)]))
    vals = np.full((len(need), 100), np.nan, np.float32)

    # part 1 stream
    size = len(lh.idx) * H; rc, rs = pad(rc, size, 0.0), pad(rs, size, 0.0)
    ref = travel_time(rc, rs); w = rc; keep = rc / 10 >= a.min_traversals; wk = np.where(keep, w, 0.0)
    part1 = {'coverage_traversals': float(wk.sum() / w.sum()), 'cells_kept': int(keep.sum()), 'by_iteration': {}}
    last_bad = {b: np.full(size, -1, np.int16) for b in REF_BANDS}; prev = None
    for t in range(100):
        if t in cache: tt = cache.pop(t)
        else: tt = travel_time(*lh.read(t))
        tt = pad(tt, size)[:size] if len(tt) < size else tt[:size]
        vals[:, t] = tt[need] if len(need) else vals[:, t]
        row = {}
        with np.errstate(invalid='ignore', divide='ignore'):
            dr = np.abs(tt / ref - 1)
            if prev is not None:
                dp = np.abs(tt / prev - 1); okp = np.isfinite(dp) & keep
                row['prev_observed'] = wshare(okp, wk)
                for b in PREV_BANDS: row[f'prev_within_{b}'] = float(wk[okp & (dp <= b)].sum() / wk[okp].sum()) if okp.any() else float('nan')
            okr = np.isfinite(dr) & keep
            for b in REF_BANDS:
                row[f'ref_within_{b}'] = float(wk[okr & (dr <= b)].sum() / wk[okr].sum()) if okr.any() else float('nan')
                if t <= 79: last_bad[b][okr & (dr > b)] = t
        part1['by_iteration'][t] = row; prev = tt
        if t % 10 == 0: print(f'iteration {t} read', flush=True)
    part1['settled_by'] = {b: {t: float(wk[last_bad[b] + 1 <= t].sum() / wk.sum()) for t in (10, 20, 30, 40, 50, 60, 70, 79)} for b in REF_BANDS}

    # part 2 features
    def change(cells, i0, i1):
        if not len(cells): return np.nan
        p = np.searchsorted(need, cells); x0, x1 = vals[p, i0], vals[p, i1]; ok = np.isfinite(x0) & np.isfinite(x1)
        return float(abs(x1[ok].sum() - x0[ok].sum()) / x0[ok].sum()) if ok.any() and x0[ok].sum() > 0 else np.nan
    part2, pooled = {}, []
    for t, rows in inno.items():
        ev = [(dup, change(cells, max(c - 1, 0), t), change(cells, t - 1, t), 'ReRoute' in m and c > 0, len(cells) > 0) for dup, c, m, cells in rows]
        part2[t] = evaluate(ev); pooled += ev
    part2['pooled'] = evaluate(pooled)
    Path(a.out).write_text(json.dumps({'run': a.run, 'min_traversals': a.min_traversals, 'part1': part1, 'part2': part2}, indent=1, default=float) + '\n')

    print(f"\npart 1: kept link-hours carry {part1['coverage_traversals']:.3f} of traversals ({part1['cells_kept']} cells)")
    for t in (1, 5, 10, 20, 30, 40, 50, 60, 70, 79, 80, 90):
        r = part1['by_iteration'][t]
        print(f"  it {t:2d}: vs previous within 2/5/10% " + '/'.join(f"{r.get(f'prev_within_{b}', float('nan')):.2f}" for b in PREV_BANDS) +
              "  vs ref within 5/10/20% " + '/'.join(f"{r[f'ref_within_{b}']:.2f}" for b in REF_BANDS))
    for b, v in part1['settled_by'].items():
        print(f"  settled within {b:.0%} of reference by t: " + ' '.join(f'{t}:{x:.2f}' for t, x in v.items()))
    print('\npart 2 (ReRoute at t+1): n, duplicate share, no-network share (its dup share), AUC since/last, skippable/precision at e (since)')
    for t, r in part2.items():
        if not r: continue
        th = ' '.join(f"{x['e']:.3f}:{x['skippable_share']:.2f}/{x['precision']:.2f}" for x in r['since']['thresholds'])
        print(f"  {str(t):6} {r['innovations']:6d} {r['duplicate_share']:.2f} {r['no_network_share']:.2f} ({r['duplicate_share_no_network']:.2f}) "
              f"AUC {r['since']['auc']:.2f}/{r['last']['auc']:.2f}  {th}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Per-person summaries of the plan snapshots, the input of A2 (best_state.py) and A3 (group_stability.py);
docs/aggregate-regularity-plan.md Section 5.

  plan_snapshots.py RUN --out DIR [--its 0,10,20,30,40,50,60,70,80,90,output] [--jobs 4] [--limit N]

Per snapshot DIR/snap-K.npz, persons in file order:
- id: person ids;
- sel, best: trips per main mode (MODES order) of the selected plan and of the best-scored plan (highest stored
  score; plans without a score, i.e. created in this iteration and not executed yet, are skipped; no scored plan ->
  the selected plan);
- sel_score, best_score (nan when unscored), plans (plans in memory).
Snapshots are written before the mobsim of iteration K: the selected plan is the one executed in K, stored scores
come from earlier executions. 'output' is BUILT.output_plans.xml.zst, the state after the last iteration.
With the first snapshot also DIR/persons.npz from the selected plan: subpopulation, home x/y (first activity),
primary activity x/y (first Work activity, else first non-Home activity; nan if none), departure of the first trip
(seconds), trips. Activity locations never change in this setup (no location choice), so these are fixed; the
departure moves by at most the time mutation range. Coordinates are EPSG:2263 (feet)."""
import argparse, sys
import xml.etree.ElementTree as ET
from multiprocessing import Pool
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plans_stats import MAIN, stream

MODES = MAIN + ['walk']
INDEX = {m: k for k, m in enumerate(MODES)}


def seconds(s):
    if not s: return float('nan')
    h, m, x = s.split(':'); return int(h) * 3600 + int(m) * 60 + float(x)


def is_act(x): return x.tag in ('act', 'activity')


def trip_modes(plan):
    """Trips per main mode of one plan element (main mode as in plans_stats.py)."""
    counts = [0] * len(MODES); legs = []
    for x in plan:
        if is_act(x):
            if not x.get('type', '').endswith('interaction') and legs:
                counts[INDEX[next((m for m in MAIN if m in legs), 'walk')]] += 1; legs = []
        elif x.tag == 'leg':
            legs.append(x.get('mode'))
    return counts


def attributes(plan):
    acts = [x for x in plan if is_act(x) and not x.get('type', '').endswith('interaction')]
    nan = float('nan')
    if not acts: return nan, nan, nan, nan, nan, 0
    home = acts[0]; rest = acts[1:]
    prim = next((a for a in rest if a.get('type', '').lower().startswith('work')), None)
    if prim is None: prim = next((a for a in rest if not a.get('type', '').lower().startswith('home')), None)
    px, py = (float(prim.get('x')), float(prim.get('y'))) if prim is not None else (nan, nan)
    dep = seconds(home.get('end_time')) if rest else nan
    return float(home.get('x')), float(home.get('y')), px, py, dep, len(rest)


def summarise(path, with_attributes=False, limit=None):
    ids, sel, best, sel_score, best_score, plans, attrs, subpop = [], [], [], [], [], [], [], []
    with stream(path) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            ps = el.findall('plan')
            selected = next((p for p in ps if p.get('selected') == 'yes'), ps[0] if ps else None)
            scored = [p for p in ps if p.get('score') is not None]
            top = max(scored, key=lambda p: float(p.get('score'))) if scored else selected
            ids.append(el.get('id')); plans.append(len(ps))
            sel.append(trip_modes(selected) if selected is not None else [0] * len(MODES))
            best.append(trip_modes(top) if top is not None else [0] * len(MODES))
            sel_score.append(float(selected.get('score')) if selected is not None and selected.get('score') is not None else np.nan)
            best_score.append(float(top.get('score')) if top is not None and top.get('score') is not None else np.nan)
            if with_attributes:
                s = el.find("attributes/attribute[@name='subpopulation']")
                subpop.append(s.text if s is not None else '')
                attrs.append(attributes(selected) if selected is not None else (np.nan,) * 5 + (0,))
            root.remove(el)
            if limit and len(ids) >= limit: break
    snap = {'id': np.array(ids), 'sel': np.array(sel, np.int16), 'best': np.array(best, np.int16),
            'sel_score': np.array(sel_score), 'best_score': np.array(best_score), 'plans': np.array(plans, np.int16)}
    if not with_attributes: return snap, None
    a = np.array(attrs, float)
    return snap, {'id': snap['id'], 'subpopulation': np.array(subpop), 'home_x': a[:, 0], 'home_y': a[:, 1],
                  'prim_x': a[:, 2], 'prim_y': a[:, 3], 'departure': a[:, 4], 'trips': a[:, 5].astype(np.int16)}


def snapshot_path(run, k):
    sim = Path(run)/'simulation'
    return sim/'BUILT.output_plans.xml.zst' if k == 'output' else sim/'ITERS'/f'it.{k}'/f'BUILT.{k}.plans.xml.zst'


def work(job):
    run, k, out, first, limit = job
    snap, persons = summarise(snapshot_path(run, k), first, limit)
    np.savez_compressed(Path(out)/f'snap-{k}.npz', **snap)
    if persons is not None: np.savez_compressed(Path(out)/'persons.npz', **persons)
    shares = snap['sel'].sum(axis=0) / max(snap['sel'].sum(), 1)
    return f"snap {k}: {len(snap['id'])} persons, selected shares " + ' '.join(f'{m} {s:.3f}' for m, s in zip(MODES, shares))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True)
    ap.add_argument('--its', default='0,10,20,30,40,50,60,70,80,90,output')
    ap.add_argument('--jobs', type=int, default=1); ap.add_argument('--limit', type=int)
    a = ap.parse_args(); Path(a.out).mkdir(parents=True, exist_ok=True)
    its = a.its.split(',')
    jobs = [(a.run, k, a.out, n == 0, a.limit) for n, k in enumerate(its)]
    with Pool(a.jobs) as pool:
        for line in pool.imap(work, jobs): print(line, flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Which ReRoute innovations come back unchanged, by what the picked plan contains and how it was made? Re-targets
M8 after A4 found that duplicates come mostly from plans without car legs (docs/aggregate-regularity-plan.md
Section 7).

  reroute_duplicates.py RUN --out FILE.json [--ts 10,20,30,40,50,60,70] [--jobs 4]

For ReRoute innovations (RandomPlanSelector_ReRoute*) at t+1, the parent plan comes from the snapshot at t and the
outcome from trips-(t+1) (duplicate = no mode and no route change in any trip), as in link_stability.py.
Parent categories:
- content: 'car' (any network leg, route type links), else 'pt' (any pt leg), else 'teleport' (walk, bike, ride, ...);
- origin: the parent's planMutator - initial, reroute (RandomPlanSelector_ReRoute), mode (SubtourModeChoice +
  ReRoute), time (TimeAllocationMutator, which shifts times and keeps the routes), other;
- age: t - iterationCreated (0-4, 5-19, 20+).
Reported: count and duplicate share per content, per content x origin, per content x origin x age; and candidate
skip rules (share of all ReRoute innovations they would skip, duplicate share among those = precision)."""
import argparse, json, sys
import xml.etree.ElementTree as ET
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plans_stats import stream
from plan_snapshots import snapshot_path
from link_stability import route_kinds, reroute_innovations


def origin(mutator):
    if not mutator or mutator == 'initialPlan': return 'initial'
    if 'TimeAllocation' in mutator: return 'time'
    if 'SubtourModeChoice' in mutator: return 'mode'
    if 'ReRoute' in mutator: return 'reroute'
    return 'other'


def age(a): return '0-4' if a < 5 else '5-19' if a < 20 else '20+'


def classify(job):
    run, t = job
    want = reroute_innovations(run, t + 1, route_kinds(run)); rows = []
    with stream(snapshot_path(run, t)) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            w = want.get(el.get('id'))
            if w is not None:
                for plan in el.findall('plan'):
                    a = {x.get('name'): x.text for x in plan.findall('attributes/attribute')}
                    if a.get('planId') is None or int(a['planId'], 36) != w[0]: continue
                    legs = plan.findall('leg')
                    car = any((l.find('route') is not None and l.find('route').get('type') == 'links') for l in legs)
                    pt = any(l.get('mode') == 'pt' for l in legs)
                    rows.append(('car' if car else 'pt' if pt else 'teleport', origin(a.get('planMutator')),
                                 age(t - int(a.get('iterationCreated', 0))), w[1]))
                    break
            root.remove(el)
    return t, len(want), rows


def table(rows, key):
    n, d = Counter(), Counter()
    for r in rows: k = key(r); n[k] += 1; d[k] += r[3]
    return {'|'.join(k) if isinstance(k, tuple) else k: {'n': n[k], 'duplicate_share': d[k] / n[k]} for k in sorted(n)}


RULES = {
    'teleport': lambda r: r[0] == 'teleport',
    'teleport or pt': lambda r: r[0] in ('teleport', 'pt'),
    'pt, not time-mutated': lambda r: r[0] == 'pt' and r[1] != 'time',
    'teleport, or pt not time-mutated': lambda r: r[0] == 'teleport' or (r[0] == 'pt' and r[1] != 'time'),
    'not car, not time-mutated': lambda r: r[0] != 'car' and r[1] != 'time',
    'any content, not time-mutated': lambda r: r[1] != 'time',
}


def rules(rows):
    out = {}
    for name, f in RULES.items():
        hit = [r for r in rows if f(r)]
        out[name] = {'skippable_share': len(hit) / len(rows) if rows else float('nan'),
                     'precision': sum(r[3] for r in hit) / len(hit) if hit else float('nan'),
                     'duplicates_caught': sum(r[3] for r in hit) / max(sum(r[3] for r in rows), 1)}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True)
    ap.add_argument('--ts', default='10,20,30,40,50,60,70'); ap.add_argument('--jobs', type=int, default=1)
    a = ap.parse_args(); ts = [int(x) for x in a.ts.split(',')]
    with Pool(a.jobs) as pool: res = pool.map(classify, [(a.run, t) for t in ts])
    out = {'run': a.run, 'by_t': {}, 'pooled': {}}; pooled = []
    for t, n, rows in res:
        out['by_t'][t] = {'innovations': n, 'parents_found': len(rows), 'content': table(rows, lambda r: r[0]),
                          'content_origin': table(rows, lambda r: (r[0], r[1])), 'rules': rules(rows)}
        pooled += rows
    out['pooled'] = {'parents_found': len(pooled), 'content': table(pooled, lambda r: r[0]),
                     'content_origin': table(pooled, lambda r: (r[0], r[1])),
                     'content_origin_age': table(pooled, lambda r: (r[0], r[1], r[2])), 'rules': rules(pooled)}
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    p = out['pooled']; total = p['parents_found']
    print(f'pooled over t = {ts}: {total} ReRoute innovations with parent found')
    print(f"{'content|origin':24} {'share':>6} {'dup':>6}")
    for k, v in p['content_origin'].items(): print(f"{k:24} {v['n'] / total:6.3f} {v['duplicate_share']:6.3f}")
    print('\nby t, duplicate share per content (share of innovations):')
    for t, r in out['by_t'].items():
        print(f'  t={t:2d} ' + '  '.join(f"{k} {v['duplicate_share']:.2f} ({v['n'] / r['parents_found']:.2f})" for k, v in r['content'].items()))
    print(f"\n{'rule':36} {'skippable':>9} {'precision':>9} {'dups caught':>11}")
    for k, v in p['rules'].items(): print(f"{k:36} {v['skippable_share']:9.3f} {v['precision']:9.3f} {v['duplicates_caught']:11.3f}")


if __name__ == '__main__':
    main()

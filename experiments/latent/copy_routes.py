#!/usr/bin/env python3
"""Seed plans with the stable state's car routes, a diagnostic (docs/converged-plan-plan.md, 6e.1).

  copy_routes.py SEED.xml.gz STABLE_OUTPUT_PLANS.xml.zst --out OUT.xml.gz

SEED: seed_plans.py PREFIX-1.xml.gz (one plan per person, legs carry only the mode). For every trip of a person's
plan whose mode is car, and whose stable selected plan (same trip count, same activity types) also has car on that
trip, the trip's leg is replaced by the stable trip's legs and interaction activities (routes, as MATSim wrote them),
the origin activity takes the stable departure (end_time), and both activities take the stable link. MATSim keeps
routes that are already there, so iteration 0 drives car on routes computed under stable congestion. Every other trip
stays as in SEED and MATSim routes it in iteration 0. Uses the run's output, so it measures the upper bound of a
congestion prediction and is not a usable method."""
import argparse, gzip, json, sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_plans import MAIN, stream, is_act       # noqa: E402


def split(plan):
    """Main activities and, per trip, the elements between them."""
    acts, trips, cur = [], [], []
    for x in plan:
        if is_act(x) and not x.get('type', '').endswith('interaction'):
            if acts: trips.append(cur)
            acts.append(x); cur = []
        elif x.tag in ('leg', 'activity', 'act'):
            cur.append(x)
    return acts, trips


def main_mode(elements):
    legs = [x.get('mode') for x in elements if x.tag == 'leg']
    return next((m for m in MAIN if m in legs), 'walk')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('seed'); ap.add_argument('stable'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    stable = {}
    with stream(a.stable) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            plan = next((p for p in el.findall('plan') if p.get('selected') == 'yes'), None)
            if plan is not None:
                acts, trips = split(plan)
                cars = {j: (acts[j].get('end_time'), acts[j].get('link'), acts[j + 1].get('link'), [ET.tostring(x) for x in t])
                        for j, t in enumerate(trips) if main_mode(t) == 'car'}
                if cars: stable[el.get('id')] = ([x.get('type') for x in acts], cars)
            el.clear(); root.clear()
    print(f'{len(stable)} persons with stable car trips', flush=True)
    n = {'persons': 0, 'car_trips': 0, 'copied': 0, 'stable_not_car': 0, 'structure_differs': 0}
    out = gzip.open(a.out, 'wt')
    out.write('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE population SYSTEM "http://www.matsim.org/files/dtd/population_v6.dtd">\n<population>\n')
    with gzip.open(a.seed, 'rb') as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            n['persons'] += 1
            plan = el.find('plan'); acts, trips = split(plan)
            cars = [j for j, t in enumerate(trips) if main_mode(t) == 'car']
            n['car_trips'] += len(cars)
            st = stable.get(el.get('id'))
            if cars and st and st[0] != [x.get('type') for x in acts]:
                n['structure_differs'] += len(cars); st = None
            if cars and st:
                for j in reversed(cars):
                    if j not in st[1]: n['stable_not_car'] += 1; continue
                    end, o_link, d_link, elements = st[1][j]
                    if end: acts[j].set('end_time', end)
                    if o_link: acts[j].set('link', o_link)
                    if d_link: acts[j + 1].set('link', d_link)
                    pos = list(plan).index(trips[j][0])
                    for x in trips[j]: plan.remove(x)
                    for k, s in enumerate(elements): plan.insert(pos + k, ET.fromstring(s))
                    n['copied'] += 1
            elif cars and el.get('id') not in stable:
                n['stable_not_car'] += len(cars)
            out.write(ET.tostring(el, encoding='unicode') + '\n')
            el.clear(); root.clear()
    out.write('</population>\n'); out.close()
    n['copied_share'] = n['copied'] / max(n['car_trips'], 1)
    with open(a.out.replace('.xml.gz', '-summary.json'), 'w') as f: json.dump(n, f, indent=1)
    print(json.dumps(n, indent=1), flush=True)


if __name__ == '__main__':
    main()

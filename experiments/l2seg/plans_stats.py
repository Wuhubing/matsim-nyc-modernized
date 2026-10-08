#!/usr/bin/env python3
"""Trips, main modes and PT legs per person in a population file (selected plans), by subpopulation.

  plans_stats.py PLANS.xml(.gz|.zst) [--out FILE.json]

Main mode of a trip: the first non-walk leg mode among {car, taxi, FHV, pt, ride, bike, cb}, else walk
(access/egress/transit walks are walk legs inside a trip). Trips are split at non-interaction activities."""
import argparse, collections, gzip, io, json
import xml.etree.ElementTree as ET
from pathlib import Path

MAIN = ['car', 'taxi', 'FHV', 'pt', 'ride', 'bike', 'cb']


def stream(path):
    path = Path(path)
    if path.suffix == '.zst':
        import zstandard
        return io.BufferedReader(zstandard.ZstdDecompressor().stream_reader(open(path, 'rb')))
    return gzip.open(path, 'rb') if path.suffix == '.gz' else open(path, 'rb')


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('plans'); ap.add_argument('--out')
    a = ap.parse_args()
    persons = collections.Counter(); trips = collections.Counter(); pt_legs = collections.Counter()
    modes = collections.defaultdict(collections.Counter)
    with stream(a.plans) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            sub_el = el.find("attributes/attribute[@name='subpopulation']")
            sub = sub_el.text if sub_el is not None else ''
            plan = next((p for p in el.findall('plan') if p.get('selected') == 'yes'), None)
            persons[sub] += 1
            if plan is not None:
                legs = []
                for x in plan:
                    if x.tag == 'act' or x.tag == 'activity':
                        if not x.get('type', '').endswith('interaction'):
                            if legs:
                                main = next((m for m in MAIN if m in legs), 'walk')
                                modes[sub][main] += 1; trips[sub] += 1; legs = []
                    elif x.tag == 'leg':
                        legs.append(x.get('mode')); pt_legs[sub] += x.get('mode') == 'pt'
            root.remove(el)
    out = {}
    for s in sorted(persons):
        n = persons[s]; t = trips[s]
        out[s] = {'persons': n, 'trips': t, 'trips_per_person': t / n, 'pt_legs': pt_legs[s], 'pt_legs_per_person': pt_legs[s] / n,
                  'main_mode_share': {m: modes[s][m] / t for m in MAIN + ['walk'] if t}}
        print(f"{s:8} persons {n:7d} trips/person {t/n:5.2f} pt legs/person {pt_legs[s]/n:5.2f} shares " +
              ' '.join(f"{m} {modes[s][m]/t:.3f}" for m in MAIN + ['walk'] if t))
    if a.out: Path(a.out).write_text(json.dumps(out, indent=2) + '\n')


if __name__ == '__main__':
    main()

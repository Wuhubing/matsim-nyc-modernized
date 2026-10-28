#!/usr/bin/env python3
"""Per-plan trip sequences of a sample of agents in one plan snapshot (docs/latent-choice-plan.md, step 2).

  extract_plans.py SNAPSHOT.plans.xml.zst --out FILE.pkl [--sample-mod 1000 --sample-keep 128]

Agents are sampled by crc32(person id) % mod < keep, so every seed and snapshot keeps the same agents.
Per agent: subpopulation and every stored plan with planId, score (nan if not executed yet), selected,
iterationCreated, planMutator, and its trips. A trip runs between two non-interaction activities:
(main mode, departure seconds, origin x, y, destination x, y, origin activity type, destination activity type).
Main mode as in experiments/l2seg/plans_stats.py: first of MAIN among the trip's legs, else walk.
Departure: end_time of the origin activity, else dep_time of the trip's first leg."""
import argparse, io, math, pickle, zlib
import xml.etree.ElementTree as ET
from pathlib import Path

MAIN = ['car', 'taxi', 'FHV', 'pt', 'ride', 'bike', 'cb']


def stream(path):
    import zstandard
    return io.BufferedReader(zstandard.ZstdDecompressor().stream_reader(open(path, 'rb')))


def seconds(s):
    if not s: return math.nan
    h, m, x = s.split(':'); return int(h) * 3600 + int(m) * 60 + float(x)


def is_act(x): return x.tag in ('act', 'activity')


def trips(plan):
    out, origin, legs, first_dep = [], None, [], math.nan
    for x in plan:
        if is_act(x):
            if x.get('type', '').endswith('interaction'): continue
            if origin is not None and legs:
                mode = next((m for m in MAIN if m in legs), 'walk')
                dep = seconds(origin.get('end_time'))
                if math.isnan(dep): dep = first_dep
                out.append((mode, dep, float(origin.get('x')), float(origin.get('y')),
                            float(x.get('x')), float(x.get('y')), origin.get('type'), x.get('type')))
            origin, legs, first_dep = x, [], math.nan
        elif x.tag == 'leg':
            if not legs: first_dep = seconds(x.get('dep_time'))
            legs.append(x.get('mode'))
    return out


def attr(el, name):
    a = el.find(f"attributes/attribute[@name='{name}']")
    return a.text if a is not None else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('snapshot'); ap.add_argument('--out', required=True)
    ap.add_argument('--sample-mod', type=int, default=1000); ap.add_argument('--sample-keep', type=int, default=128)
    a = ap.parse_args()
    agents = {}
    with stream(a.snapshot) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            pid = el.get('id')
            if zlib.crc32(pid.encode()) % a.sample_mod < a.sample_keep:
                plans = []
                for p in el.findall('plan'):
                    s = p.get('score')
                    plans.append({'id': attr(p, 'planId'), 'score': float(s) if s is not None else math.nan,
                                  'selected': p.get('selected') == 'yes',
                                  'created': int(attr(p, 'iterationCreated') or -1),
                                  'mutator': attr(p, 'planMutator'), 'trips': trips(p)})
                agents[pid] = {'subpop': attr(el, 'subpopulation'), 'plans': plans}
            el.clear(); root.clear()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, 'wb') as f: pickle.dump(agents, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f'{a.snapshot}: {len(agents)} agents, {sum(len(v["plans"]) for v in agents.values())} plans -> {a.out}')


if __name__ == '__main__':
    main()

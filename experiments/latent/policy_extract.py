#!/usr/bin/env python3
"""Per-plan inputs for predicting policy effects (docs/policy-prediction-plan.md, step 1).

  policy_extract.py links NETWORK.xml.zst TOLLS.xml(.gz) --city city.npz --out links.pkl
  policy_extract.py plans SNAPSHOT.plans.xml.zst --links links.pkl --out FILE.pkl [--sample-mod 1000 --sample-keep 128]

'links': per road link its grid cell (city.npz grid, -1 outside the used cells), free-flow seconds and whether it
is tolled (same 289 links in both schemas). 'plans': agents sampled as in extract_plans.py; per agent subpopulation
and every stored plan with score, selected, iterationCreated, a choice signature (leg modes and departure quarter
hours), leg counts per mode (as research group-modes counts legs, walk access included) and per car leg
(departure seconds, tolled crossings, {cell: [links, free-flow seconds]}). Toll of a plan under a price schedule =
sum over car legs of crossings x amount(departure); the departure stands in for the crossing time."""
import argparse, gzip, io, math, pickle, zlib
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
import numpy as np


def stream(path):
    if path.endswith('.gz'): return gzip.open(path, 'rb')
    import zstandard
    return io.BufferedReader(zstandard.ZstdDecompressor().stream_reader(open(path, 'rb')))


def seconds(s):
    if not s: return math.nan
    h, m, x = s.split(':'); return int(h) * 3600 + int(m) * 60 + float(x)


def links(a):
    city = np.load(a.city)
    x0, y0, size, nx, ny = city['grid']; ny = int(ny)
    index = {int(c): i for i, c in enumerate(city['cells'])}
    tolled = set()
    with stream(a.tolls) as f:
        for ev, el in ET.iterparse(f):
            if el.tag == 'link': tolled.add(el.get('id'))
    nodes, out = {}, {}
    with stream(a.network) as f:
        for ev, el in ET.iterparse(f):
            if el.tag == 'node':
                nodes[el.get('id')] = (float(el.get('x')), float(el.get('y')))
            elif el.tag == 'link':
                (xa, ya), (xb, yb) = nodes[el.get('from')], nodes[el.get('to')]
                c = index.get(int(((xa + xb) / 2 - x0) // size) * ny + int(((ya + yb) / 2 - y0) // size), -1)
                sp = float(el.get('freespeed'))
                out[el.get('id')] = (c, float(el.get('length')) / sp if sp > 0 else 0.0, el.get('id') in tolled)
                el.clear()
    with open(a.out, 'wb') as f: pickle.dump(out, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f'{len(out)} links, {sum(v[2] for v in out.values())} tolled -> {a.out}')


def attr(el, name):
    x = el.find(f"attributes/attribute[@name='{name}']")
    return x.text if x is not None else None


def plan_record(p, L):
    legs, sig, car = Counter(), [], []
    for x in p:
        if x.tag != 'leg': continue
        mode = x.get('mode'); dep = seconds(x.get('dep_time'))
        legs[mode] += 1
        sig.append((mode, -1 if math.isnan(dep) else int(dep // 900)))
        if mode == 'car':
            r = x.find('route'); cells, toll = {}, 0
            for lid in (r.text or '').split() if r is not None else ():
                c, ff, t = L.get(lid, (-1, 0.0, False))
                toll += t
                v = cells.setdefault(c, [0, 0.0]); v[0] += 1; v[1] += ff
            car.append((dep, toll, cells))
    s = p.get('score')
    return {'score': float(s) if s is not None else math.nan, 'selected': p.get('selected') == 'yes',
            'created': int(attr(p, 'iterationCreated') or -1), 'sig': zlib.crc32(repr(sig).encode()), 'legs': dict(legs), 'car': car}


def plans(a):
    with open(a.links, 'rb') as f: L = pickle.load(f)
    agents = {}
    with stream(a.snapshot) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            pid = el.get('id')
            if zlib.crc32(pid.encode()) % a.sample_mod < a.sample_keep:
                agents[pid] = {'subpop': attr(el, 'subpopulation'), 'plans': [plan_record(p, L) for p in el.findall('plan')]}
            el.clear(); root.clear()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out + '.tmp', 'wb') as f: pickle.dump(agents, f, protocol=pickle.HIGHEST_PROTOCOL)
    Path(a.out + '.tmp').rename(a.out)
    print(f'{a.snapshot}: {len(agents)} agents, {sum(len(v["plans"]) for v in agents.values())} plans -> {a.out}')


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd', required=True)
    l = sub.add_parser('links'); l.add_argument('network'); l.add_argument('tolls')
    l.add_argument('--city', required=True); l.add_argument('--out', required=True)
    p = sub.add_parser('plans'); p.add_argument('snapshot'); p.add_argument('--links', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--sample-mod', type=int, default=1000); p.add_argument('--sample-keep', type=int, default=128)
    a = ap.parse_args()
    (links if a.cmd == 'links' else plans)(a)


if __name__ == '__main__':
    main()

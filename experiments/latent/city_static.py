#!/usr/bin/env python3
"""Run-independent inputs of the city and agent encoders (docs/policy-prediction-plan.md, step 1).

  city_static.py NETWORK.xml.zst SCHEDULE.xml.gz COLD_PLANS.xml.gz --city city.npz --out static.npz --agents agents.pkl
                 [--sample-mod 1000 --sample-keep 128]

Cells and grid as in city.npz (road cells; anything else is the 'other' cell, index C).
- road [C+1, 8]: log1p road km, log1p lane km, log1p capacity x km / 1000, length-weighted mean free speed (m/s / 30),
  share of length faster than 15 m/s, log1p links, cell centre x and y (scaled to 0..1 over the grid);
- transit [C+1, 30, 2]: log1p scheduled stop departures per hour at stops in the cell, rail (subway, rail, tram,
  ferry) and bus separately; hour of the stop departure (route departure + stop offset), >= 30 folded into 29;
- agents.pkl: per sampled person (crc32 % mod < keep, as everywhere) subpopulation and the activities of the
  selected initial plan: (type, cell, start hours, end hours), start nan for the first, end nan for the last."""
import argparse, gzip, io, math, pickle, zlib
import xml.etree.ElementTree as ET
import numpy as np

ROAD = {'car', 'taxi', 'FHV'}
RAIL = {'subway', 'rail', 'tram', 'ferry'}


def stream(path):
    if path.endswith('.gz'): return gzip.open(path, 'rb')
    import zstandard
    return io.BufferedReader(zstandard.ZstdDecompressor().stream_reader(open(path, 'rb')))


def seconds(s):
    if not s: return math.nan
    h, m, x = s.split(':'); return int(h) * 3600 + int(m) * 60 + float(x)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('network'); ap.add_argument('schedule'); ap.add_argument('cold')
    ap.add_argument('--city', required=True); ap.add_argument('--out', required=True); ap.add_argument('--agents', required=True)
    ap.add_argument('--sample-mod', type=int, default=1000); ap.add_argument('--sample-keep', type=int, default=128)
    a = ap.parse_args()
    city = np.load(a.city)
    x0, y0, size, nx, ny = city['grid']; nx, ny = int(nx), int(ny)
    index = {int(c): i for i, c in enumerate(city['cells'])}; C = len(index)

    def cell(x, y): return index.get(int((x - x0) // size) * ny + int((y - y0) // size), C)

    road = np.zeros((C + 1, 8)); fast = np.zeros(C + 1); speed = np.zeros(C + 1)
    nodes = {}
    with stream(a.network) as f:
        for ev, el in ET.iterparse(f):
            if el.tag == 'node':
                nodes[el.get('id')] = (float(el.get('x')), float(el.get('y')))
            elif el.tag == 'link':
                if ROAD & set(el.get('modes', '').split(',')):
                    (xa, ya), (xb, yb) = nodes[el.get('from')], nodes[el.get('to')]
                    c = cell((xa + xb) / 2, (ya + yb) / 2); km = float(el.get('length')) / 1000
                    v = float(el.get('freespeed'))
                    road[c, 0] += km; road[c, 1] += km * float(el.get('permlanes')); road[c, 2] += km * float(el.get('capacity')) / 1000
                    speed[c] += km * v; fast[c] += km * (v > 15); road[c, 5] += 1
                el.clear()
    km = np.maximum(road[:, 0], 1e-9)
    road[:, 3] = speed / km / 30; road[:, 4] = fast / km
    road[:, [0, 1, 2, 5]] = np.log1p(road[:, [0, 1, 2, 5]])
    for raw, i in index.items():
        ix, iy = divmod(raw, ny); road[i, 6] = (ix + 0.5) / nx; road[i, 7] = (iy + 0.5) / ny

    transit = np.zeros((C + 1, 30, 2)); stops = {}
    with stream(a.schedule) as f:
        for ev, el in ET.iterparse(f):
            if el.tag == 'stopFacility':
                stops[el.get('id')] = cell(float(el.get('x')), float(el.get('y')))
            elif el.tag == 'transitRoute':
                rail = (el.findtext('transportMode') or '').strip() in RAIL
                prof = [(stops.get(s.get('refId'), C), seconds(s.get('departureOffset') or s.get('arrivalOffset')))
                        for s in el.find('routeProfile')]
                for d in el.find('departures'):
                    t0 = seconds(d.get('departureTime'))
                    for c, off in prof:
                        transit[c, min(int((t0 + (0 if math.isnan(off) else off)) // 3600), 29), int(not rail)] += 1
                el.clear()
    transit = np.log1p(transit)

    agents = {}
    with stream(a.cold) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            pid = el.get('id')
            if zlib.crc32(pid.encode()) % a.sample_mod < a.sample_keep:
                sub = el.find("attributes/attribute[@name='subpopulation']")
                plan = next((p for p in el.findall('plan') if p.get('selected') == 'yes'), el.find('plan'))
                acts = [(x.get('type'), cell(float(x.get('x')), float(x.get('y'))), seconds(x.get('start_time')) / 3600,
                         seconds(x.get('end_time')) / 3600)
                        for x in plan if x.tag in ('act', 'activity') and not x.get('type', '').endswith('interaction')]
                agents[pid] = {'subpop': sub.text if sub is not None else None, 'acts': acts}
            el.clear(); root.clear()
    np.savez_compressed(a.out, road=road.astype(np.float32), transit=transit.astype(np.float32))
    with open(a.agents, 'wb') as f: pickle.dump(agents, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f'{C} cells; road km {np.expm1(road[:, 0]).sum():.0f}; stop departures rail {np.expm1(transit[..., 0]).sum():.0f} '
          f'bus {np.expm1(transit[..., 1]).sum():.0f}; {len(agents)} agents -> {a.out}, {a.agents}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Road congestion per grid cell and hour, the input of the city encoder (docs/latent-choice-plan.md, step 3).

  city_tensor.py NETWORK.xml.zst --runs SEED=RUN_DIR ... --its 9,19,... --out FILE.npz [--cell-ft 6562]

Grid: square cells of --cell-ft feet (EPSG:3628 is in US feet; 6562 ft = 2 km) over the network's node extent.
A link belongs to the cell of its midpoint. Only road modes car/taxi/FHV count. Per cell, entry hour 0..29
(>= 30 folded into 29) and iteration, from research/link-hours-IT.csv.gz:
- log1p(entries);
- congestion = sum of traversal seconds / sum(completed traversals x free-flow seconds), 1 where nothing completed;
- observed: 1 if any traversal completed.
Free flow = length / freespeed of the base network (time-variant speed factors are not applied, so the ratio
also absorbs them; it is used only to compare states). Saves grid parameters, cell adjacency (8-neighbourhood
among cells with road links) and X[state, cell, hour, feature] with states listed in 'states' as 'SEED-IT'."""
import argparse, csv, gzip, io, math
import xml.etree.ElementTree as ET
import numpy as np

ROAD = {'car', 'taxi', 'FHV'}
HOURS = 30


def stream(path):
    import zstandard
    return io.BufferedReader(zstandard.ZstdDecompressor().stream_reader(open(path, 'rb')))


def network(path):
    nodes, links = {}, {}
    with stream(path) as f:
        for ev, el in ET.iterparse(f, events=('end',)):
            if el.tag == 'node':
                nodes[el.get('id')] = (float(el.get('x')), float(el.get('y')))
            elif el.tag == 'link':
                if ROAD & set(el.get('modes', '').split(',')):
                    links[el.get('id')] = (el.get('from'), el.get('to'), float(el.get('length')), float(el.get('freespeed')))
                el.clear()
    return nodes, links


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('network'); ap.add_argument('--runs', nargs='+', required=True)
    ap.add_argument('--its', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--cell-ft', type=float, default=6562.0)
    a = ap.parse_args()
    nodes, links = network(a.network)
    xy = np.array(list(nodes.values()))
    x0, y0 = xy.min(0); nx = int((xy[:, 0].max() - x0) // a.cell_ft) + 1; ny = int((xy[:, 1].max() - y0) // a.cell_ft) + 1
    raw_cell, ff = {}, {}
    for lid, (fr, to, length, speed) in links.items():
        (xa, ya), (xb, yb) = nodes[fr], nodes[to]
        raw_cell[lid] = int(((xa + xb) / 2 - x0) // a.cell_ft) * ny + int(((ya + yb) / 2 - y0) // a.cell_ft)
        ff[lid] = length / speed if speed > 0 else math.nan
    used = sorted(set(raw_cell.values()))
    index = {c: i for i, c in enumerate(used)}
    cell_of = {lid: index[c] for lid, c in raw_cell.items()}
    adj = []
    for c in used:
        ix, iy = divmod(c, ny)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (ix + dx) * ny + (iy + dy)
                if (dx or dy) and 0 <= ix + dx < nx and 0 <= iy + dy < ny and n in index:
                    adj.append((index[c], index[n]))
    its = [int(i) for i in a.its.split(',')]
    runs = [r.split('=', 1) for r in a.runs]
    states, X = [], np.zeros((len(runs) * len(its), len(used), HOURS, 3), np.float32)
    s = 0
    for seed, run in runs:
        for it in its:
            ent = np.zeros((len(used), HOURS)); sec = np.zeros_like(ent); free = np.zeros_like(ent)
            with gzip.open(f'{run}/research/link-hours-{it}.csv.gz', 'rt') as f:
                for row in csv.DictReader(f):
                    lid = row['link_id']
                    if row['network_mode'] not in ROAD or lid not in cell_of: continue
                    c, h = cell_of[lid], min(int(row['entry_hour']), HOURS - 1)
                    ent[c, h] += float(row['entries'])
                    done = float(row['completed_traversals'])
                    if done > 0 and not math.isnan(ff[lid]):
                        sec[c, h] += float(row['total_traversal_seconds']); free[c, h] += done * ff[lid]
            obs = free > 0
            X[s, :, :, 0] = np.log1p(ent)
            X[s, :, :, 1] = np.where(obs, sec / np.where(obs, free, 1), 1.0)
            X[s, :, :, 2] = obs
            states.append(f'{seed}-{it}'); s += 1
            print(f'state {seed}-{it}: entries {ent.sum():.0f}, median congestion {np.median(X[s-1,:,:,1][obs]):.2f}', flush=True)
    np.savez_compressed(a.out, X=X, states=np.array(states), adj=np.array(adj, np.int32),
                        cells=np.array(used, np.int64), grid=np.array([x0, y0, a.cell_ft, nx, ny], np.float64))
    print(f'{len(used)} cells, {len(adj)} adjacency pairs, X {X.shape} -> {a.out}')


if __name__ == '__main__':
    main()

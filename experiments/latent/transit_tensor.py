#!/usr/bin/env python3
"""Transit crowding per grid cell and hour, second input of the city encoder (docs/latent-choice-plan.md, version 2).

  transit_tensor.py --city city.npz --runs SEED=RUN_DIR ... --its 0,10,... --out FILE.npz

Only iterations with experienced plans (every 10) have boarding times, so the transit state of a sample in
iteration k comes from iteration k-10 (the road state from k-1). Grid and cells as in city.npz; a pt leg belongs
to the cell of the stop it boards at (the 'pt interaction' before it) and the hour of its departure (>= 30 folded
into 29). Per cell and hour, over all agents:
- log1p(pt legs);
- mean wait in minutes, enterVehicleTime - dep_time, each wait capped at 60;
- long-wait share: legs that never boarded or waited more than 20 minutes. Waits have a long tail (iteration 30:
  median 4 min, 90th percentile 1.8 h), mostly full vehicles. The route's boardingTime cannot be used for this:
  in experienced plans it is rewritten to the actual boarding time;
- observed: 1 if any pt leg departed there.
Experienced plans are read line by line (one element per line in MATSim's writer) instead of as XML, for speed.
Saves T[state, cell, hour, feature] with states listed in 'states' as 'SEED-IT'."""
import argparse, io, re
import numpy as np

HOURS = 30
NUM = r'"([^"]*)"'
ACT = re.compile(r'<activity type="pt interaction"[^>]* x=' + NUM + ' y=' + NUM)
LEG = re.compile(r'<leg mode=' + NUM + ' dep_time=' + NUM)
ENTER = re.compile(r'name="enterVehicleTime"[^>]*>([^<]+)<')
LONG = 20 * 60


def stream(path):
    import zstandard
    return io.TextIOWrapper(io.BufferedReader(zstandard.ZstdDecompressor().stream_reader(open(path, 'rb'))))


def seconds(s):
    h, m, x = s.split(':'); return int(h) * 3600 + int(m) * 60 + float(x)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--city', required=True)
    ap.add_argument('--runs', nargs='+', required=True); ap.add_argument('--its', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    city = np.load(a.city)
    x0, y0, size, nx, ny = city['grid']; ny = int(ny)
    cell_index = {int(c): i for i, c in enumerate(city['cells'])}
    C = len(cell_index)
    its = [int(i) for i in a.its.split(',')]
    runs = [r.split('=', 1) for r in a.runs]
    T, states = np.zeros((len(runs) * len(its), C, HOURS, 4), np.float32), []
    s = 0
    for seed, run in runs:
        for it in its:
            n = np.zeros((C, HOURS)); nb = np.zeros_like(n); wait = np.zeros_like(n); miss = np.zeros_like(n)
            stop, leg = None, None                       # last boarding stop (x, y); open pt leg [cell, hour, dep, enter]

            def close(l):
                if l is None or l[0] < 0: return
                c, h, dep, enter = l
                n[c, h] += 1
                if enter is None: miss[c, h] += 1; return
                nb[c, h] += 1; wait[c, h] += min(enter - dep, 3600) / 60
                if enter - dep > LONG: miss[c, h] += 1

            with stream(f'{run}/ITERS/it.{it}/BUILT.{it}.experienced_plans.xml.zst') as f:
                for line in f:
                    if '<activity' in line:
                        m = ACT.search(line)
                        stop = (float(m.group(1)), float(m.group(2))) if m else None
                    elif '<leg' in line:
                        m = LEG.search(line)
                        if m and m.group(1) == 'pt' and stop is not None:
                            dep = seconds(m.group(2))
                            c = cell_index.get(int((stop[0] - x0) // size) * ny + int((stop[1] - y0) // size), -1)
                            leg = [c, min(int(dep // 3600), HOURS - 1), dep, None]
                    elif leg is not None and 'enterVehicleTime' in line:
                        leg[3] = float(ENTER.search(line).group(1))
                    elif leg is not None and '</leg>' in line:
                        close(leg); leg = None
            obs = n > 0
            T[s, :, :, 0] = np.log1p(n)
            T[s, :, :, 1] = np.where(nb > 0, wait / np.maximum(nb, 1), 0)
            T[s, :, :, 2] = np.where(obs, miss / np.maximum(n, 1), 0)
            T[s, :, :, 3] = obs
            states.append(f'{seed}-{it}')
            print(f'state {seed}-{it}: pt legs {n.sum():.0f}, long waits {miss.sum():.0f}, mean wait {wait.sum() / max(nb.sum(), 1):.1f} min', flush=True)
            s += 1
    np.savez_compressed(a.out, T=T, states=np.array(states))


if __name__ == '__main__':
    main()

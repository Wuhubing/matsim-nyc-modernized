#!/usr/bin/env python3
"""Offline iteration-to-iteration redundancy of a completed MATSim run (no simulation).

extract: stream one ITERS/it.N events file into a compact state pickle:
  persons  : person -> [choice_hash, outcome_hash, travel_seconds, legs]
             choice  = leg modes + realized network-route link sequence (decided by replanning)
             outcome = all person/vehicle event times (determined by the mobsim interaction)
  links    : (link, hour) -> [vehicle entries, summed link travel seconds]
  events   : event counts by type
compare: consecutive iterations -> how much of each mobsim re-simulates an unchanged state.
"""
import argparse, collections, json, os, pickle, re, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ATTR = re.compile(rb'(\w+)="([^"]*)"')
PERSON_TYPES = {b'actend', b'actstart', b'departure', b'arrival', b'PersonEntersVehicle', b'PersonLeavesVehicle',
                b'waitingForPt', b'PersonEntersPtVehicle', b'PersonLeavesPtVehicle', b'stuckAndAbort', b'travelled'}


def field(line, name):
    at = line.find(name)
    start = at + len(name)
    return line[start:line.find(b'"', start)]


def extract(events, dest):
    started = time.monotonic()
    proc = subprocess.Popen(['zstd', '-dc', str(events)], stdout=subprocess.PIPE, bufsize=1 << 20)
    choice = collections.defaultdict(int); outcome = collections.defaultdict(int)
    travel = collections.Counter(); legs = collections.Counter()
    depart = {}; driver = {}; entered = {}
    links = collections.defaultdict(lambda: [0, 0.0]); counts = collections.Counter()
    for line in proc.stdout:
        at = line.find(b'type="')
        if at < 0:
            continue
        typ = line[at + 6:line.find(b'"', at + 6)]
        counts[typ] += 1
        if typ == b'entered link' or typ == b'left link':
            t = float(field(line, b'time="')); v = field(line, b'vehicle="'); link = field(line, b'link="')
            if typ == b'entered link':
                entered[v] = (link, t)
                p = driver.get(v)
                if p is not None:
                    choice[p] = hash((choice[p], link)); outcome[p] = hash((outcome[p], t))
            else:
                start = entered.pop(v, None)
                if start is not None and start[0] == link:
                    cell = links[(link, int(start[1] // 3600))]; cell[0] += 1; cell[1] += t - start[1]
            continue
        if typ == b'vehicle enters traffic':
            e = dict(ATTR.findall(line)); driver[e[b'vehicle']] = e[b'person']
            continue
        if typ == b'vehicle leaves traffic' or typ == b'vehicle aborts':
            v = field(line, b'vehicle="'); driver.pop(v, None)
            entered.pop(v, None)   # arrival link is never left; do not pair it with a later departure
            continue
        if typ not in PERSON_TYPES:
            continue
        e = dict(ATTR.findall(line)); p = e.get(b'person')
        if p is None:
            continue
        t = float(e[b'time'])
        outcome[p] = hash((outcome[p], typ, t))
        if typ == b'departure':
            choice[p] = hash((choice[p], b'leg', e[b'legMode'])); depart[p] = t; legs[p] += 1
        elif typ == b'arrival' and p in depart:
            travel[p] += t - depart.pop(p)
    if proc.wait() != 0:
        raise RuntimeError(f'zstd failed for {events}')
    persons = {p: (choice[p], outcome[p], travel[p], legs[p]) for p in set(choice) | set(outcome)}
    state = {'source': str(events), 'persons': persons, 'links': {k: tuple(v) for k, v in links.items()},
             'events': {k.decode(): v for k, v in counts.items()}, 'extract_seconds': time.monotonic() - started}
    with open(dest, 'wb') as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    return dest, state['extract_seconds'], sum(counts.values())


def compare(prev, cur):
    pp, cp = prev['persons'], cur['persons']
    common = pp.keys() & cp.keys()
    cat = collections.Counter(); dt = collections.Counter()
    for p in common:
        a, b = pp[p], cp[p]
        if a[0] != b[0]:
            cat['choice_changed'] += 1
        elif a[1] == b[1]:
            cat['identical_replay'] += 1
        else:
            cat['same_choice_outcome_changed'] += 1
            d = abs(b[2] - a[2])
            dt['<=60s' if d <= 60 else '<=300s' if d <= 300 else '>300s'] += 1
    pl, cl = prev['links'], cur['links']
    cells = pl.keys() | cl.keys()
    same_count = within_5pct = 0; entries_on_stable = total_entries = 0
    for k in cells:
        a = pl.get(k, (0, 0.0)); b = cl.get(k, (0, 0.0)); total_entries += b[0]
        if a[0] == b[0]:
            same_count += 1
        ma = a[1] / a[0] if a[0] else 0.0; mb = b[1] / b[0] if b[0] else 0.0
        if a[0] == b[0] and abs(mb - ma) <= 0.05 * max(ma, 1.0):
            within_5pct += 1; entries_on_stable += b[0]
    n = len(common)
    return {'persons_compared': n,
            'person_share': {k: v / n for k, v in cat.items()},
            'same_choice_travel_change': dict(dt),
            'link_hours': len(cells),
            'link_hour_share_same_volume': same_count / len(cells),
            'link_hour_share_same_volume_and_time_5pct': within_5pct / len(cells),
            'link_entry_share_on_stable_link_hours': entries_on_stable / total_entries if total_entries else None,
            'events': sum(cur['events'].values())}


def main():
    # Hashes of bytes are salted per interpreter; worker processes and reruns must share one seed.
    if os.environ.get('PYTHONHASHSEED') != '0':
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, 'PYTHONHASHSEED': '0'})
    ap = argparse.ArgumentParser(); ap.add_argument('simulation', type=Path, help='MATSim output directory containing ITERS')
    ap.add_argument('--out', type=Path, required=True); ap.add_argument('--workers', type=int, default=4)
    a = ap.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    files = sorted(a.simulation.glob('ITERS/it.*/*.events.xml.zst'), key=lambda p: int(p.parent.name[3:]))
    jobs = [(f, a.out / f'state-{int(f.parent.name[3:])}.pkl') for f in files]
    todo = [j for j in jobs if not j[1].exists()]
    with ProcessPoolExecutor(a.workers) as pool:
        for dest, seconds, n in pool.map(extract, *zip(*todo)) if todo else []:
            print(f'{dest.name}: {n:,} events in {seconds:.0f}s', flush=True)
    rows = []; prev = None
    for f, dest in jobs:
        with open(dest, 'rb') as fh:
            cur = pickle.load(fh)
        if prev is not None:
            rows.append({'iteration': int(f.parent.name[3:]), **compare(prev, cur)})
        prev = cur
    (a.out / 'redundancy.json').write_text(json.dumps(rows, indent=2) + '\n')
    for r in rows:
        s = r['person_share']
        print(r['iteration'], f"identical={s.get('identical_replay',0):.3f} same_choice_changed={s.get('same_choice_outcome_changed',0):.3f} "
              f"choice_changed={s.get('choice_changed',0):.3f} stable_link_hours={r['link_hour_share_same_volume_and_time_5pct']:.3f} "
              f"entries_on_stable={r['link_entry_share_on_stable_link_hours']:.3f}")


if __name__ == '__main__':
    sys.exit(main())

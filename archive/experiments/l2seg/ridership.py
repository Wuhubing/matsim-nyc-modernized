#!/usr/bin/env python3
"""Daily subway boardings at the stations of the paper's validation table (arXiv:2008.04762, Table 5).

  ridership.py SCHEDULE.xml.gz EVENTS.xml(.gz|.zst) [--scale 25] [--out FILE.json]

A boarding is a PersonEntersPtVehicle (MATSim 2026; PersonEntersVehicle also accepted) of a non-driver; its stop is the facility the vehicle
last arrived at (VehicleArrivesAtFacility). Only stops served by subway routes count; stops are grouped into
stations by name keywords below. Every boarding counts, so transfers inside a station count again, while
turnstile counts do not: simulated values are an upper bound for comparison. Scaled by the sample factor."""
import argparse, collections, gzip, io, json, re
from pathlib import Path

PAPER = {  # station: (keywords that must all occur in the GTFS stop name, real, paper simulated)
    '14 St - Union Square': (['14 ST', 'UNION'], 106718, 97825),
    'Grand Central - 42 St': (['GRAND CENTRAL'], 158580, 170025),
    'Penn Station - 123 & ACE': (['34 ST', 'PENN'], 173108, 256825),
    'Times Square': (['TIMES SQ'], 202363, 191425),
    'Fulton St': (['FULTON ST'], 85440, 83025),
    'Canal St': (['CANAL ST'], 70806, 78250),
    '59 St - Columbus Circle': (['59 ST', 'COLUMBUS'], 73836, 75050),
    '34 St - Herald Sq': (['34 ST', 'HERALD'], 125682, 124500),
    'Atlantic Av - Barclays Ctr': (['ATLANTIC', 'BARCLAYS'], 42711, 59350),
    'Jackson Hts - Roosevelt Av': (['JACKSON', 'ROOSEVELT'], 52296, 41200),
}


def open_any(path):
    path = Path(path)
    if path.suffix == '.zst':
        import zstandard
        return io.TextIOWrapper(io.BufferedReader(zstandard.ZstdDecompressor().stream_reader(open(path, 'rb'))))
    return gzip.open(path, 'rt') if path.suffix == '.gz' else open(path)


def subway_stops(schedule):
    names, subway = {}, set()
    route_stops, mode = [], None
    with open_any(schedule) as f:
        for line in f:
            if '<stopFacility' in line:
                names[re.search(r'id="([^"]+)"', line).group(1)] = (re.search(r'name="([^"]*)"', line) or re.search('()', '')).group(1).upper()
            elif '<transitRoute' in line: route_stops, mode = [], None
            elif '<transportMode>' in line: mode = re.search(r'<transportMode>([^<]*)', line).group(1)
            elif '<stop ' in line and 'refId' in line: route_stops.append(re.search(r'refId="([^"]+)"', line).group(1))
            elif '</transitRoute>' in line and mode == 'subway': subway.update(route_stops)
    return {s: names.get(s, '') for s in subway}


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('schedule'); ap.add_argument('events')
    ap.add_argument('--scale', type=float, default=25); ap.add_argument('--out'); a = ap.parse_args()
    stops = subway_stops(a.schedule)
    station_of = {}
    for s, name in stops.items():
        for st, (keys, _, _) in PAPER.items():
            if all(k in name for k in keys): station_of[s] = st
    at = {}; boardings = collections.Counter(); total_subway = 0
    veh = re.compile(r'vehicle="([^"]+)"'); fac = re.compile(r'facility="([^"]+)"'); per = re.compile(r'person="([^"]+)"')
    with open_any(a.events) as f:
        for line in f:
            if 'type="VehicleArrivesAtFacility"' in line:
                at[veh.search(line).group(1)] = fac.search(line).group(1)
            elif 'type="PersonEntersPtVehicle"' in line or 'type="PersonEntersVehicle"' in line:
                v = veh.search(line).group(1); stop = at.get(v)
                if stop is None or stop not in stops or per.search(line).group(1).startswith('pt_'): continue
                total_subway += 1
                if stop in station_of: boardings[station_of[stop]] += 1
    rows = {st: {'real': real, 'paper_simulated': paper, 'simulated': boardings[st] * a.scale,
                 'difference': boardings[st] * a.scale / real - 1} for st, (_, real, paper) in PAPER.items()}
    tot = sum(r['simulated'] for r in rows.values()); real = sum(r['real'] for r in rows.values())
    for st, r in rows.items(): print(f"{st:30} real {r['real']:8d} paper {r['paper_simulated']:8d} here {r['simulated']:9.0f} ({r['difference']:+.0%})")
    print(f"{'ten stations':30} real {real:8d} paper {1177475:8d} here {tot:9.0f} ({tot/real-1:+.0%}); all subway boardings x scale {total_subway*a.scale:.0f}")
    print('stops matched per station:', {st: sum(1 for v in station_of.values() if v == st) for st in PAPER})
    if a.out: Path(a.out).write_text(json.dumps({'stations': rows, 'ten_station_total': tot, 'subway_boardings_scaled': total_subway * a.scale}, indent=2) + '\n')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Transit level of service from a transit schedule and one iteration's events (plan Section 0, C1).

  transit_los.py SCHEDULE.xml.gz EVENTS.xml(.gz|.zst) [--out FILE.json]

Schedule: lines, routes and departures per mode; vehicles assigned to departures that overlap in time (a vehicle
cannot serve two departures at once). Events: per boarding, the wait (waitingForPt -> PersonEntersPtVehicle) and the
number of vehicles of the same transit route that departed from that stop while the agent waited (> 0: the agent
did not or could not board them, i.e. capacity); waits never ending in a boarding are censored at the end of the
simulation. Vehicle delay at stops (VehicleDepartsAtFacility delay) by mode and hour. Stops with most waiting time."""
import argparse, bisect, collections, gzip, io, json, re, statistics
from pathlib import Path


def open_any(path):
    path = Path(path)
    if path.suffix == '.zst':
        import zstandard
        return io.TextIOWrapper(io.BufferedReader(zstandard.ZstdDecompressor().stream_reader(open(path, 'rb'))))
    return gzip.open(path, 'rt') if path.suffix == '.gz' else open(path)


def secs(t):
    h, m, s = t.split(':'); return int(h) * 3600 + int(m) * 60 + float(s)


def schedule(path):
    """Per route: mode, line, duration (last stop offset); departures (time, vehicle); stop names."""
    routes = {}; names = {}; line = None; cur = None
    with open_any(path) as f:
        for l in f:
            if '<stopFacility' in l:
                m = re.search(r'id="([^"]+)"', l); n = re.search(r'name="([^"]*)"', l); names[m.group(1)] = n.group(1) if n else ''
            elif '<transitLine' in l: line = re.search(r'id="([^"]+)"', l).group(1)
            elif '<transitRoute ' in l or '<transitRoute>' in l:
                cur = {'line': line, 'mode': None, 'duration': 0.0, 'departures': [], 'stops': 0}
                routes[re.search(r'id="([^"]+)"', l).group(1)] = cur
            elif '<transportMode>' in l: cur['mode'] = re.search(r'<transportMode>([^<]*)', l).group(1)
            elif '<stop ' in l and 'refId' in l:
                cur['stops'] += 1
                for key in ('arrivalOffset', 'departureOffset'):
                    m = re.search(key + r'="([^"]+)"', l)
                    if m: cur['duration'] = max(cur['duration'], secs(m.group(1)))
            elif '<departure ' in l:
                cur['departures'].append((secs(re.search(r'departureTime="([^"]+)"', l).group(1)), re.search(r'vehicleRefId="([^"]+)"', l).group(1)))
    return routes, names


def schedule_summary(routes):
    by_mode = collections.defaultdict(lambda: {'lines': set(), 'routes': 0, 'departures': 0})
    vehicle_use = collections.defaultdict(list)
    for rid, r in routes.items():
        b = by_mode[r['mode']]; b['lines'].add(r['line']); b['routes'] += 1; b['departures'] += len(r['departures'])
        for t, v in r['departures']: vehicle_use[v].append((t, t + r['duration'], rid))
    conflicts = collections.Counter(); vehicles = collections.Counter(); multi = 0
    for v, uses in vehicle_use.items():
        uses.sort(); mode = routes[uses[0][2]]['mode']; vehicles[mode] += 1; multi += len(uses) > 1
        conflicts[mode] += sum(1 for a, b in zip(uses, uses[1:]) if b[0] < a[1])
    return {m: {'lines': len(b['lines']), 'routes': b['routes'], 'departures': b['departures'], 'vehicles': vehicles[m],
                'overlapping_departure_pairs': conflicts[m]} for m, b in by_mode.items()}, multi


def quantiles(xs):
    if not xs: return {}
    xs = sorted(xs); q = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))]
    return {'n': len(xs), 'mean_min': statistics.fmean(xs) / 60, 'median_min': q(.5) / 60, 'p90_min': q(.9) / 60, 'p99_min': q(.99) / 60}


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('schedule'); ap.add_argument('events'); ap.add_argument('--out')
    ap.add_argument('--end', type=float, default=108000.0)
    ap.add_argument('--cohorts', help='ResearchMetrics cohorts.csv.gz (person_id, subpopulation) to split waits by subpopulation')
    a = ap.parse_args()
    import csv as _csv
    subpop = {r['person_id']: r['subpopulation'] for r in _csv.DictReader(gzip.open(a.cohorts, 'rt'))} if a.cohorts else {}
    by_sub = collections.defaultdict(list); stop_sub = collections.defaultdict(collections.Counter); never_sub = collections.Counter()
    routes, names = schedule(a.schedule)
    sched, multi = schedule_summary(routes)
    route_mode = {rid: r['mode'] for rid, r in routes.items()}
    vehicle_route = {}; deps = collections.defaultdict(list); delay = collections.defaultdict(list)
    waiting = {}; waits = collections.defaultdict(list); passed = collections.Counter(); stop_wait = collections.Counter()
    driver_starts = 0
    attr = lambda l, k: re.search(k + r'="([^"]*)"', l).group(1)
    with open_any(a.events) as f:
        for l in f:
            if 'type="' not in l: continue
            if 'type="VehicleDepartsAtFacility"' in l:
                v = attr(l, 'vehicle'); r = vehicle_route.get(v); t = float(attr(l, 'time'))
                if r is not None:
                    deps[(attr(l, 'facility'), r)].append(t)
                    delay[(route_mode.get(r), int(t // 3600))].append(float(attr(l, 'delay')))
            elif 'type="TransitDriverStarts"' in l:
                vehicle_route[attr(l, 'vehicleId')] = attr(l, 'transitRouteId'); driver_starts += 1
            elif 'type="waitingForPt"' in l:
                waiting[attr(l, 'person')] = (float(attr(l, 'time')), attr(l, 'atStop'))
            elif 'type="PersonEntersPtVehicle"' in l:
                p = attr(l, 'person'); w = waiting.pop(p, None)
                if w is None: continue
                t = float(attr(l, 'time')); r = attr(l, 'transitRoute'); mode = route_mode.get(r)
                lst = deps.get((w[1], r), []); k = bisect.bisect_right(lst, t) - bisect.bisect_right(lst, w[0])
                waits[mode].append(t - w[0]); stop_wait[w[1]] += t - w[0]
                sp = subpop.get(p, '?'); by_sub[(mode, sp)].append(t - w[0]); stop_sub[w[1]][sp] += t - w[0]
                passed[(mode, min(k, 3))] += 1
    censored = [a.end - w[0] for w in waiting.values()]
    for p, w in waiting.items():
        stop_wait[w[1]] += a.end - w[0]; sp = subpop.get(p, '?'); stop_sub[w[1]][sp] += a.end - w[0]; never_sub[sp] += 1
    out = {'schedule': sched, 'vehicles_with_several_departures': multi,
           'transit_driver_starts': driver_starts,
           'boarded_waits': {m: quantiles(x) for m, x in waits.items()},
           'never_boarded': {'n': len(censored), 'mean_censored_wait_min': statistics.fmean(censored) / 60 if censored else 0},
           'vehicles_of_same_route_departed_while_waiting': {f'{m}:{k if k < 3 else "3+"}': n for (m, k), n in sorted(passed.items(), key=str)},
           'delay_by_mode_hour': {f'{m}:{h:02d}': {'mean_min': statistics.fmean(x) / 60, 'p90_min': sorted(x)[int(.9 * len(x))] / 60, 'n': len(x)}
                                  for (m, h), x in sorted(delay.items(), key=str) if x},
           'top_stops_by_waiting_hours': [(names.get(s, s), s, round(v / 3600)) for s, v in stop_wait.most_common(15)]}
    if subpop:
        out['boarded_waits_by_subpopulation'] = {f'{m}:{sp}': quantiles(x) for (m, sp), x in sorted(by_sub.items(), key=str)}
        out['never_boarded_by_subpopulation'] = dict(never_sub)
        out['top_stops_waiting_hours_by_subpopulation'] = [(names.get(s, s), {sp: round(v / 3600) for sp, v in stop_sub[s].items()}) for s, _ in stop_wait.most_common(15)]
    print(json.dumps({k: v for k, v in out.items() if k != 'delay_by_mode_hour'}, indent=1))
    peak = {k: v for k, v in out['delay_by_mode_hour'].items() if k.split(':')[1] in ('06', '08', '12', '17', '20')}
    print('delay at selected hours:', json.dumps(peak, indent=1))
    if a.out: Path(a.out).write_text(json.dumps(out, indent=2) + '\n')


if __name__ == '__main__':
    main()

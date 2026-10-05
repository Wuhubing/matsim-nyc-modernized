#!/usr/bin/env python3
"""Surrogate-study data: pre-mobsim plan projection and post-mobsim road state.

Leakage rule: inputs for iteration i use only (a) the plans dumped before iteration i's mobsim and
(b) states measured in iterations < i. Targets are iteration i's measured state.

  network(path)           link -> (length, freespeed, capacity, lanes)
  free_flow(net, l, h)    archived period speed rule (ArchiveNetwork.speed), seconds
  road_state(events)      (link, hour) -> [entries, summed link seconds]; car-leg durations per person
  project(plans, net, tt) PSim-style day replay of selected plans with link-hour travel times
                          -> projected (link, hour) entries and per-person car-leg durations
"""
import collections, math, re, subprocess
from pathlib import Path

SPEED = [[.472941, .497564, .502572, .435369, .484185, .568571], [.276634, .265192, .261024, .254357, .279059, .308127],
         [.409828, .392877, .386702, .376825, .413420, .456485], [.737691, .707178, .696064, .678285, .744156, .821673]]
HOURS, PERIODS = [0, 7, 10, 13, 16, 19, 22], [5, 0, 1, 2, 3, 4, 5]
NETWORK_MODES = {b'car', b'taxi', b'FHV'}
ATTR = re.compile(rb'(\w+)="([^"]*)"')


def stream(path):
    proc = subprocess.Popen(['zstd', '-dc', str(path)] if str(path).endswith('.zst') else ['gzip', '-dc', str(path)],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 20)
    yield from proc.stdout
    if proc.wait():
        raise RuntimeError(f'decompression failed: {path}')


def network(path):
    links = {}
    for line in stream(path):
        if b'<link ' in line:
            a = dict(ATTR.findall(line))
            if b'car' in a.get(b'modes', b''):
                links[a[b'id']] = (float(a[b'length']), float(a[b'freespeed']), float(a[b'capacity']), float(a[b'permlanes']))
    return links


def period(hour):
    h = hour % 24
    return PERIODS[max(i for i, start in enumerate(HOURS) if start <= h)]


def free_flow(net, link, hour):
    length, v, _, _ = net[link]
    if v != 10:
        v = v * SPEED[0 if v > 33 else 1 if v > 22 else 2 if v > 10 else 3][period(hour)]
    return max(1.0, length / v)


def clock(text):
    h, m, s = text.split(b':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def road_state(events, bin_seconds=3600):
    """Link-hour [entries, summed seconds, summed log(1+seconds)] and per-person network-leg durations.
    Link means are heavy-tailed (gridlocked vehicles), so the log sum gives a robust geometric mean."""
    links = collections.defaultdict(lambda: [0, 0.0, 0.0]); entered = {}; depart = {}; legs = collections.defaultdict(list)
    for line in stream(events):
        at = line.find(b'type="')
        if at < 0:
            continue
        typ = line[at + 6:line.find(b'"', at + 6)]
        if typ == b'entered link' or typ == b'left link':
            a = dict(ATTR.findall(line)); t = float(a[b'time']); v = a[b'vehicle']
            if typ == b'entered link':
                entered[v] = (a[b'link'], t)
            else:
                s = entered.pop(v, None)
                if s and s[0] == a[b'link']:
                    d = t - s[1]; c = links[(s[0], int(s[1] // bin_seconds))]; c[0] += 1; c[1] += d; c[2] += math.log1p(d)
        elif typ == b'departure' or typ == b'arrival':
            a = dict(ATTR.findall(line))
            if a.get(b'legMode') not in NETWORK_MODES:
                continue
            p = a[b'person']; t = float(a[b'time'])
            if typ == b'departure':
                depart[p] = t
            elif p in depart:
                legs[p].append(t - depart.pop(p))
    return {k: tuple(v) for k, v in links.items()}, dict(legs)


def selected_plans(plans):
    """Yield (person, [elements]) for selected plans; element = ('act', end, dur) or ('leg', mode, trav, route_links)."""
    person = None; selected = False; elements = []; in_leg = None
    for line in stream(plans):
        s = line.strip()
        if s.startswith(b'<person '):
            person = dict(ATTR.findall(s))[b'id']
        elif s.startswith(b'<plan '):
            selected = b'selected="yes"' in s; elements = []
        elif not selected:
            continue
        elif s.startswith(b'<activity '):
            a = dict(ATTR.findall(s))
            elements.append(('act', clock(a[b'end_time']) if b'end_time' in a else None, clock(a[b'max_dur']) if b'max_dur' in a else None))
        elif s.startswith(b'<leg '):
            a = dict(ATTR.findall(s)); in_leg = [a[b'mode'], clock(a[b'trav_time']) if b'trav_time' in a else 0.0, None]
        elif s.startswith(b'<route ') and in_leg is not None:
            if b'type="links"' in s:
                in_leg[2] = s[s.find(b'>') + 1:s.rfind(b'</route>')].split()
            if b'trav_time="' in s and not in_leg[1]:
                in_leg[1] = clock(dict(ATTR.findall(s[:s.find(b'>')]))[b'trav_time'])
        elif s.startswith(b'</leg>') and in_leg is not None:
            elements.append(('leg', *in_leg)); in_leg = None
        elif s.startswith(b'</plan>'):
            if person is not None:
                yield person, elements
            selected = False


def geometric(state):
    return {k: math.expm1(v[2] / v[0]) for k, v in state.items() if v[0] and len(v) > 2}


def project(plans, net, tt, horizon=30 * 3600, skip_last=False, times=None, bin_seconds=3600):
    """Replay each selected plan's day. Network legs traverse route links (after the start link) with tt[(link, hour)]
    mean seconds, falling back to free flow; other legs use the plan's trav_time. Activities follow MATSim's
    end-time-then-duration rule. Returns projected link-hour entries and per-person projected network-leg durations."""
    demand = collections.Counter(); legs = {}; cache = {}
    def link_time(link, b):
        k = (link, b)
        if k not in cache:
            if times is not None and k in times:
                cache[k] = times[k]
            else:
                c = tt.get(k)
                cache[k] = c[1] / c[0] if c and c[0] else free_flow(net, link, int(b * bin_seconds // 3600)) if link in net else 1.0
        return cache[k]
    for person, elements in selected_plans(plans):
        t = 0.0; durations = []
        for kind, *x in elements:
            if kind == 'act':
                end, dur = x
                t = max(t, end) if end is not None else t + (dur or 0)
            else:
                mode, trav, route = x
                if mode in NETWORK_MODES and route:
                    start = t
                    for link in (route[1:-1] if skip_last else route[1:]):
                        h = int(t // bin_seconds)
                        if t < horizon:
                            demand[(link, h)] += 1
                        t += link_time(link, h)
                    durations.append(t - start)
                else:
                    t += trav
        if durations:
            legs[person] = durations
    return demand, legs

#!/usr/bin/env python3
"""Critical-path view of a JFR recording over several iterations (offline).

Wall time spent *blocked* (jdk.ThreadPark / jdk.JavaMonitorWait >= threshold) is real duration, unlike
execution samples. For each stopwatch phase of each iteration it reports:
  - main/QSim threads blocked waiting for the parallel events manager to drain (critical-path cost of events)
  - event-processing thread execution samples by handler category
Usage: critical_path.py ATTEMPT_DIR JFR_TOOL
"""
import collections, datetime as dt, json, re, subprocess, sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from analyze_baseline_diagnostic import table

HANDLERS = [  # first matching frame (top-down) wins
    ('event_xml_write', ('org.matsim.core.events.algorithms.EventWriterXML', 'org.matsim.api.core.v01.events.Event.writeAsXML',
                         'org.matsim.api.core.v01.events.Event.writeXMLStart', 'com.github.luben.zstd', 'java.io.')),
    ('scoring', ('org.matsim.core.scoring',)),
    ('pricing_custom', ('org.c2smart.matsimnyc.Pricing2025', 'org.c2smart.matsimnyc.LegacyCosts', 'org.c2smart.matsimnyc.PricingAudit',
                        'org.c2smart.matsimnyc.IterationMetrics')),
    ('pt_occupancy', ('ch.sbb.matsim',)),
    ('travel_time', ('org.matsim.core.trafficmonitoring',)),
    ('analysis', ('org.matsim.analysis', 'org.matsim.counts', 'org.matsim.core.events.algorithms')),
    ('dispatch', ('org.matsim.core.events',)),
]


def frames(event):
    st = event['values'].get('stackTrace') or {}
    return [f['method']['type']['name'].replace('/', '.')+'.'+f['method']['name'] for f in st.get('frames', [])]


def thread(event):
    v = event['values']
    t = v.get('eventThread') or v.get('sampledThread') or {}
    return t.get('javaName') or t.get('osName') or 'unknown'


def kind(name):
    if 'ProcessEventsRunnable' in name:
        return 'events'
    if name.startswith('QNetsimEngine'):
        return 'qsim_worker'
    if name == 'main':
        return 'main'
    if name.startswith('PersonPrepareForSim') or 'Replanning' in name or 'ForkJoinPool' in name:
        return 'replanning_or_routing'
    return 'other'


def seconds(duration):
    # JFR JSON durations are ISO-8601, e.g. "PT0.012S" or "PT1M0.0038S"
    m = re.fullmatch(r'PT(?:([\d.]+)H)?(?:([\d.]+)M)?(?:([\d.]+)S)?', duration or '')
    if not m:
        raise ValueError('Unexpected JFR duration: '+str(duration))
    return sum(float(x or 0)*f for x, f in zip(m.groups(), (3600, 60, 1)))


def phases(stopwatch, day):
    out = []
    for row in table(stopwatch):
        i = int(row['iteration'])
        for name in ('replanning', 'mobsim', 'scoring', 'iterationEndsListeners'):
            b, e = row.get('BEGIN '+name), row.get('END '+name)
            if b and e:
                ts = [dt.datetime.combine(day, dt.time.fromisoformat(x), ZoneInfo('America/New_York')).timestamp() for x in (b, e)]
                out.append((ts[0], ts[1] + 1, f'it{i}.{name}'))
    return out


def locate(t, spans):
    for b, e, name in spans:
        if b <= t < e:
            return name
    return 'outside_stopwatch_phases'


def main():
    attempt, jfr = Path(sys.argv[1]), sys.argv[2]
    manifest = json.loads((attempt.parent/'manifest.json').read_text())
    a = next(x for x in manifest['attempts'] if x['name'] == attempt.name)
    day = dt.datetime.fromisoformat(a['started_utc']).astimezone(ZoneInfo('America/New_York')).date()
    spans = phases(attempt/'simulation/BUILT.stopwatch.csv', day)
    data = json.loads(subprocess.run([jfr, 'print', '--json', '--stack-depth', '64', '--events', 'jdk.ThreadPark,jdk.JavaMonitorWait,jdk.ExecutionSample',
                                      str(attempt/'profile.jfr')], capture_output=True, text=True, check=True).stdout)
    blocked = collections.defaultdict(lambda: collections.defaultdict(float))
    blocked_sites = collections.defaultdict(collections.Counter)
    samples = collections.defaultdict(collections.Counter)
    for e in data['recording']['events']:
        t = dt.datetime.fromisoformat(e['values']['startTime']).timestamp(); phase = locate(t, spans); th = thread(e)
        if e['type'] in ('jdk.ThreadPark', 'jdk.JavaMonitorWait'):
            f = frames(e); site = next((x for x in f if not x.startswith(('java.', 'jdk.', 'sun.'))), f[0] if f else '?')
            d = seconds(e['values'].get('duration'))
            blocked[phase][kind(th)+' @ '+site] += d
            blocked_sites[kind(th)][site] += d
        elif e['type'] == 'jdk.ExecutionSample':
            k = kind(th)
            if k == 'events':
                f = frames(e)
                cat = next((c for c, prefixes in HANDLERS if any(x.startswith(prefixes) for x in f)), 'other')
                samples[phase]['events:'+cat] += 1
            samples[phase]['thread:'+k] += 1
    stopwatch = {name: e - 1 - b for b, e, name in spans}
    result = {'source': str(attempt/'profile.jfr'), 'stopwatch_seconds': stopwatch,
              'blocked_seconds_by_phase': {p: dict(sorted(v.items(), key=lambda x: -x[1])[:12]) for p, v in blocked.items()},
              'blocked_seconds_by_thread_kind_site': {k: dict(v.most_common(10)) for k, v in blocked_sites.items()},
              'execution_samples_by_phase': {p: dict(v) for p, v in samples.items()},
              'limitations': 'Only blocking episodes >= the JFR threshold are counted, so blocked time is a lower bound; '
                             'execution samples are proportions, not wall time; JFR adds overhead; one run.'}
    (attempt.parent/'critical-path.json').write_text(json.dumps(result, indent=2)+'\n')
    for p in sorted(stopwatch):
        if p.endswith('mobsim'):
            top = sorted(blocked.get(p, {}).items(), key=lambda x: -x[1])[:4]
            ev = {k[7:]: v for k, v in samples.get(p, {}).items() if k.startswith('events:')}
            print(p, f'{stopwatch[p]:.0f}s', '| blocked:', ', '.join(f'{k} {v:.1f}s' for k, v in top), '| event-thread samples:', ev)


if __name__ == '__main__':
    main()

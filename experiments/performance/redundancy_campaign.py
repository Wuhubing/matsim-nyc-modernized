#!/usr/bin/env python3
"""Timed screening of the exact engineering items E1/E2 on an independent simulation ledger.

Arms (same input, seed, threads, behaviour; only the listed differences):
  baseline : pre-E2 jar (commit 1093340), full event XML every iteration
  e2       : HEAD jar (index-based pricing lookups), full event XML every iteration
  e12      : HEAD jar + -Dnyc.onlineMetrics=true + controller.writeEventsInterval=0
  profile  : e2 with JFR (profile settings + ThreadPark/MonitorWait >= 2 ms); never ranked
Short arms run iterations 0-2. The fastest exact candidate (>=5% faster) gets a 12-iteration
pair against a fresh baseline. Metrics: offline event scan for event-writing arms, the online
IterationMetrics JSON for e12; both pass the same conservation/histogram/revenue gates.
"""
import argparse, copy, csv, datetime, fcntl, json, random, re, shutil, subprocess, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark as B
P, D, EM, ROOT = B.P, B.D, B.EM, B.ROOT

SHORT_ITERATIONS, FULL_ITERATIONS = 3, 12
E1_SETTINGS = {('controller', 'writeEventsInterval'): '0'}
ARMS = {'baseline': ('baseline.jar', {}, []), 'e2': ('candidate.jar', {}, []),
        'e12': ('candidate.jar', E1_SETTINGS, ['-Dnyc.onlineMetrics=true']), 'profile': ('candidate.jar', {}, [])}
JFR = 'settings=profile,jdk.ThreadPark#threshold=2 ms,jdk.JavaMonitorWait#threshold=2 ms,dumponexit=true'


def read(path):
    return json.loads(Path(path).read_text())


def arm_config(m, dest, arm, iterations):
    root = B.config_tree(Path(m['source']), dest, 'baseline', iterations)
    for (module, name), value in ARMS[arm][1].items():
        P.setparam(root, module, name, value)
    return root


def check_configs(base, cand, arm):
    a, b = copy.deepcopy(base), copy.deepcopy(cand)
    for root in (a, b):
        P.setparam(root, 'controller', 'outputDirectory', 'OUTPUT')
    for (module, name), expected in ARMS[arm][1].items():
        p = b.find(f"module[@name='{module}']/param[@name='{name}']"); old = a.find(f"module[@name='{module}']/param[@name='{name}']")
        if p is None or old is None or p.get('value') != expected:
            raise ValueError('Whitelisted setting missing: ' + name)
        p.set('value', old.get('value'))
    if B.canonical(a) != B.canonical(b):
        raise ValueError('Configuration differs outside whitelist')


def prepare(source, baseline_jar, out, limit):
    start = time.monotonic(); source, out = source.resolve(), out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(baseline_jar, out/'baseline.jar'); shutil.copy2(ROOT/'target/matsim-nyc-modernized-1.0.0.jar', out/'candidate.jar')
    code = out/'code'; code.mkdir()
    paths = [Path(__file__), Path(B.__file__), ROOT/'experiments/acceleration/pilot.py', ROOT/'experiments/acceleration/event_metrics.py']
    for p in paths:
        shutil.copy2(p, code/p.name)
    inputs = {out/'baseline.jar', out/'candidate.jar', source/'cold-attempt-1/config.xml', *paths}
    for p in ET.parse(source/'cold-attempt-1/config.xml').findall('.//param'):
        v = p.get('value', '')
        if v.startswith('/') and Path(v).is_file():
            inputs.add(Path(v))
    order = ['baseline', 'e2', 'e12']; random.Random(4711).shuffle(order)
    full = ['full-baseline', 'full-candidate']; random.Random(4712).shuffle(full)
    ledger = {'limit_seconds': limit, 'used_seconds': 0.0, 'active': None, 'updated_utc': D.now(),
              'note': 'Independent ledger authorized by the user on 2026-10-04 for this campaign only; the pilot ledger is untouched.'}
    D.save(out/'budget.json', ledger); (out/'executor.lock').touch()
    m = {'created_utc': D.now(), 'source': str(source), 'ledger': str(out/'budget.json'), 'lock': str(out/'executor.lock'),
         'branch': D.command(['git', 'branch', '--show-current']).strip(), 'head_commit': D.command(['git', 'rev-parse', 'HEAD']).strip(),
         'baseline_commit': '1093340', 'short_order': ['profile', *order], 'full_order': full, 'attempts': [], 'status': 'prepared',
         'short_limit_seconds': 4*1000, 'full_limit_seconds': 2*2700, 'speed_gate': .05,
         'inputs': [{'path': str(p), 'sha256': D.sha(p)} for p in sorted(inputs)],
         'java_home': read(ROOT/'.tools/environment.json')['java_home'],
         'machine': D.command(['sysctl', 'hw.model', 'hw.physicalcpu', 'hw.logicalcpu', 'hw.memsize']).strip()}
    for arm in ARMS:
        B.write_config(arm_config(m, out/('short-'+arm), arm, SHORT_ITERATIONS), out/(arm+'-planned.xml'))
    java = Path(m['java_home'])/'bin/java'
    proc = subprocess.run([str(java), '--class-path', str(out/'candidate.jar'), str(ROOT/'experiments/performance/VerifyConfig.java'),
                           *[('online:' if a == 'e12' else '')+str(out/(a+'-planned.xml')) for a in ARMS]], capture_output=True, text=True)
    (out/'config-preflight.log').write_text(proc.stdout+proc.stderr)
    m.update(config_preflight_exit_code=proc.returncode, preparation_seconds=time.monotonic()-start)
    D.save(out/'manifest.json', m)
    if proc.returncode:
        raise RuntimeError('MATSim config preflight failed; no simulation launched')
    print(out, flush=True)


def execute(out, m, ledger, name, arm, iterations, phase):
    if any(a['name'] == name for a in m['attempts']):
        raise ValueError('Attempt exists; never overwrite or retry automatically')
    used_phase = sum(a.get('elapsed_seconds', 0) for a in m['attempts'] if a['phase'] == phase)
    limit = min(ledger['limit_seconds']-ledger['used_seconds'], m[phase+'_limit_seconds']-used_phase)
    if limit <= 0:
        raise RuntimeError('Budget exhausted')
    initial = D.system_sample()
    if initial['disk_free_bytes'] < 30*D.GIB or initial['pressure_level'] == 4:
        raise RuntimeError('Resource preflight failed')
    B.verify_hashes(m)
    dest = out/name; dest.mkdir(exist_ok=False)
    B.write_config(arm_config(m, dest, arm, iterations), dest/'config.xml')
    jar, _, props = ARMS[arm]
    cmd = ['/usr/bin/time', '-l', str(Path(m['java_home'])/'bin/java'), '-Duser.language=en', '-Duser.country=US', '-Xmx16g',
           '-Xlog:gc*:file='+str(dest/'gc.log')+':time,uptime,level,tags', *props]
    if arm == 'profile':
        cmd.append('-XX:StartFlightRecording=filename='+str(dest/'profile.jfr')+','+JFR)
    cmd += ['-jar', str(out/jar), str(dest/'config.xml')]
    a = {'name': name, 'arm': arm, 'variant': arm, 'phase': phase, 'iterations': iterations, 'command': cmd, 'started_utc': D.now(),
         'status': 'running', 'profile_overhead': arm == 'profile'}
    m['attempts'].append(a); D.save(out/'manifest.json', m)
    start = time.monotonic(); before = ledger['used_seconds']; proc = None; reason = None; peak = 0; history = []; critical = None
    try:
        with (dest/'run.log').open('w') as log, (dest/'resources.csv').open('w') as res:
            w = csv.DictWriter(res, fieldnames=['utc', 'elapsed_seconds', 'rss_bytes', 'disk_free_bytes', 'pressure_level', 'swap_used_bytes']); w.writeheader()
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            ledger.update(active={'pid': proc.pid, 'directory': str(dest), 'started_utc': a['started_utc']}, updated_utc=D.now()); D.save(Path(m['ledger']), ledger)
            system = initial; next_system = 0
            while proc.poll() is None:
                elapsed = time.monotonic()-start
                ledger.update(used_seconds=before+elapsed, updated_utc=D.now()); D.save(Path(m['ledger']), ledger)
                rss = D.memory_sample(proc.pid); peak = max(peak, rss or 0)
                if elapsed >= next_system:
                    system = D.system_sample(); history.append((elapsed, system['swap_used_bytes']))
                    reason, critical = D.resource_reason(system, history, critical, elapsed); next_system = elapsed+60
                w.writerow(dict(utc=D.now(), elapsed_seconds=elapsed, rss_bytes=rss, **system)); res.flush()
                if elapsed >= limit-2:
                    reason = 'budget_exhausted'
                if reason:
                    D.stop_group(proc, max(0, min(30, limit-elapsed))); break
                try:
                    proc.wait(timeout=min(5, max(.001, limit-elapsed-2)))
                except subprocess.TimeoutExpired:
                    pass
            proc.wait()
    except BaseException:
        reason = 'executor_interrupted'
        if proc is not None and proc.poll() is None:
            D.stop_group(proc, 30)
        raise
    finally:
        elapsed = time.monotonic()-start
        ledger.update(used_seconds=before+elapsed, updated_utc=D.now(), active=None); D.save(Path(m['ledger']), ledger)
        a.update(elapsed_seconds=elapsed, ended_utc=D.now(), peak_rss_bytes=peak, exit_code=proc.returncode if proc else None, reason=reason, status='interrupted')
        D.save(out/'manifest.json', m)
    log = (dest/'run.log').read_text(errors='replace'); sim = dest/'simulation'
    per_iteration = (lambda i: (sim/f'iteration-metrics-{i}.json').exists()) if arm == 'e12' else (lambda i: any((sim/f'ITERS/it.{i}').glob('*.events.xml*')))
    complete = (proc.returncode == 0 and not reason and 'shutdown completed' in log.lower()
                and all(f'ITERATION {i} ENDS' in log for i in range(iterations)) and (sim/'BUILT.output_config.xml').exists()
                and all(per_iteration(i) for i in range(iterations)))
    a['status'] = 'complete' if complete else 'interrupted' if reason else 'failed'; D.save(out/'manifest.json', m)
    print(name, a['status'], round(elapsed, 1), flush=True)
    if not complete:
        raise RuntimeError('Simulation did not complete; no retry: '+name)


def event_source(sim, i, people, entries, cache):
    online = sim/f'iteration-metrics-{i}.json'
    if online.exists():
        value = read(online); value['xml_closed'] = True; value['source'] = {'path': str(online)}
        value['private_car_entries_by_hour'] = {int(k): v for k, v in value['private_car_entries_by_hour'].items()}
        return value
    path = next((sim/f'ITERS/it.{i}').glob('*.events.xml*'))
    identity = {'path': str(path), 'bytes': path.stat().st_size, 'mtime_ns': path.stat().st_mtime_ns}
    if cache.exists() and read(cache)['source'] == identity:
        return read(cache)
    t = time.monotonic(); value = dict(source=identity, **EM.measure(path, people, entries)); value['analysis_seconds'] = time.monotonic()-t
    D.save(cache, value)
    return value


def analyze_attempt(out, a, people, entries):
    """Same gates and row definition as benchmark.analyze_attempt; event metrics may come from IterationMetrics."""
    dest = out/a['name']; sim = dest/'simulation'
    scores = P.table(sim/'BUILT.scorestats.csv'); modes = P.table(sim/'BUILT.modestats.csv'); audits = P.table(sim/'pricing-audit.csv')
    if not len(scores) == len(modes) == len(audits) == a['iterations']:
        raise ValueError('Missing metric rows')
    rows = []
    for i in range(a['iterations']):
        event = event_source(sim, i, people, entries, dest/f'event-metrics-{i}.json')
        if event['errors'] or not event['xml_closed']:
            raise ValueError('Event conservation check failed')
        score, mode, audit = scores[i], modes[i], audits[i]
        if any(int(x['iteration']) != i for x in (score, mode, audit)):
            raise ValueError('Iteration mismatch')
        if abs(float(audit['sample_revenue_usd'])-event['net_congestion_revenue']) >= .011:
            raise ValueError('Revenue audit mismatch')
        hist = P.table(sim/f'ITERS/it.{i}/BUILT.{i}.legHistogram.txt')
        if sum(float(h['stuck_all']) for h in hist) != event['unfinished_all']:
            raise ValueError('Unfinished histogram mismatch')
        for kind, prefix in [('departures', 'departures_'), ('completed', 'arrivals_')]:
            for mode_name, n in event[kind].items():
                if sum(float(h[prefix+mode_name]) for h in hist) != n:
                    raise ValueError('Leg histogram mismatch')
        ncar = event['completed'].get('car', 0); carmean = event['mean_completed_car_leg_seconds']
        row = {'iteration': i, 'score': float(score['avg_executed']), 'count_unfinished': event['unfinished_all'],
               'count_car_entries': event['private_car_entry_crossings'], 'count_completed_car': ncar,
               'completed_car_total_seconds': carmean*ncar, 'censored_wait_seconds': event['censored_wait_person_hours']*3600,
               'count_not_boarded': event['waiting_at_cutoff'], 'revenue_cents': round(float(audit['sample_revenue_usd'])*100)}
        row.update({'mode_'+k: float(v) for k, v in mode.items() if k != 'iteration'})
        rows.append(row)
    watch = P.table(sim/'BUILT.stopwatch.csv'); phases = {}
    for k in ['replanning', 'dump all plans', 'prepareForMobsim', 'mobsim', 'scoring', 'iterationEndsListeners', 'iteration_duration']:
        phases[k] = [sum(float(v)*f for v, f in zip(r[k].split(':'), [3600, 60, 1])) if r.get(k) else None for r in watch]
    log = (dest/'run.log').read_text(errors='replace')
    cpu = re.search(r'([\d.]+) real\s+([\d.]+) user\s+([\d.]+) sys', log)
    pauses = [float(x) for x in re.findall(r'Pause[^\n]*? ([\d.]+)ms', (dest/'gc.log').read_text())]
    starts, _, _ = P.log_times(log)
    timing = {'wall_seconds': a['elapsed_seconds'], 'phases_seconds_by_iteration': phases,
              'mobsim_seconds': sum(x for x in phases['mobsim'] if x), 'replanning_seconds': sum(x for x in phases['replanning'] if x),
              'startup_seconds': starts[0]-datetime.datetime.fromisoformat(a['started_utc']).timestamp() if 0 in starts else None,
              'cpu_user_seconds': float(cpu[2]) if cpu else None, 'cpu_system_seconds': float(cpu[3]) if cpu else None,
              'gc_pause_seconds': sum(pauses)/1000, 'peak_rss_gib': a['peak_rss_bytes']/D.GIB,
              'output_bytes': sum(p.stat().st_size for p in sim.rglob('*') if p.is_file()), 'profile_overhead': a['profile_overhead']}
    D.save(dest/'metrics.json', rows); D.save(dest/'timing.json', timing)
    return rows, timing


def analyze(out):
    m = read(out/'manifest.json')
    people = B.population_ids(Path(m['source'])/'inputs/cold.xml.gz')
    entries = {r['id'].encode() for r in csv.DictReader((ROOT/'scenarios/nyc-2025/links.csv').open()) if r['entry'] == '1'}
    results, timings, diffs = {}, {}, {}
    for a in m['attempts']:
        if a['status'] == 'complete':
            results[a['name']], timings[a['name']] = analyze_attempt(out, a, people, entries)
    for a in m['attempts']:
        base = 'short-baseline' if a['phase'] == 'short' else 'full-baseline'
        if a['name'] in results and base in results and a['name'] != base:
            check_configs(ET.parse(out/base/'simulation/BUILT.output_config.xml').getroot(),
                          ET.parse(out/a['name']/'simulation/BUILT.output_config.xml').getroot(), a['arm'])
            diffs[a['name']] = B.compare_rows(results[base], results[a['name']])
    s = {'timings': timings, 'differences': diffs, 'budget': read(Path(m['ledger'])), 'status': m['status'],
         'attempts': [{k: a.get(k) for k in ('name', 'arm', 'status', 'reason', 'elapsed_seconds')} for a in m['attempts']]}
    D.save(out/'analysis.json', s)
    return s


def choose(s):
    base = s['timings'].get('short-baseline')
    ok = [arm for arm in ('e2', 'e12') if 'short-'+arm in s['timings'] and not s['differences'].get('short-'+arm)
          and s['timings']['short-'+arm]['wall_seconds'] <= .95*base['wall_seconds']] if base else []
    return min(ok, key=lambda arm: s['timings']['short-'+arm]['wall_seconds']) if ok else None


def run(out):
    m = read(out/'manifest.json')
    with Path(m['lock']).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = read(Path(m['ledger']))
        if ledger['active']:
            raise RuntimeError('Ledger has an active attempt; inspect before continuing')
        if m['status'] == 'insufficient_budget' and m.get('estimator_revision') == 2:
            m['status'] = 'screening_complete'
        if any(a['status'] != 'complete' for a in m['attempts']):
            raise RuntimeError('Incomplete attempt requires inspection; no automatic retry')
        m['status'] = 'screening'; D.save(out/'manifest.json', m)
        for arm in m['short_order']:
            if not any(a['name'] == 'short-'+arm for a in m['attempts']):
                execute(out, m, ledger, 'short-'+arm, arm, SHORT_ITERATIONS, 'short')
        s = analyze(out); selected = choose(s)
        m['selected_candidate'] = selected
        if selected is None:
            m['status'] = 'no_candidate'; D.save(out/'manifest.json', m); return
        # Startup is paid once per run; only the per-iteration part scales with the horizon.
        def projected(arm):
            t = s['timings']['short-'+arm]
            return t['startup_seconds'] + FULL_ITERATIONS*(t['wall_seconds']-t['startup_seconds'])/SHORT_ITERATIONS
        estimate = (projected('baseline') + projected(selected))*1.15
        if estimate > min(ledger['limit_seconds']-ledger['used_seconds'], m['full_limit_seconds']):
            m.update(status='insufficient_budget', full_estimate_seconds=estimate); D.save(out/'manifest.json', m); return
        m.update(status='full_validation', full_estimate_seconds=estimate); D.save(out/'manifest.json', m)
        for name in m['full_order']:
            if not any(a['name'] == name for a in m['attempts']):
                execute(out, m, ledger, name, 'baseline' if name == 'full-baseline' else selected, FULL_ITERATIONS, 'full')
        m['status'] = 'complete'; D.save(out/'manifest.json', m); analyze(out)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('action', choices=['prepare', 'run', 'analyze'])
    ap.add_argument('--source', type=Path, default=B.DEFAULT_SOURCE); ap.add_argument('--baseline-jar', type=Path)
    ap.add_argument('--run-dir', type=Path); ap.add_argument('--limit-seconds', type=float, default=14400)
    a = ap.parse_args()
    if a.action == 'prepare':
        prepare(a.source, a.baseline_jar, a.run_dir or ROOT/'outputs'/('performance-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-redundancy'), a.limit_seconds)
    elif a.action == 'run':
        run(a.run_dir.resolve())
    else:
        print(json.dumps(analyze(a.run_dir.resolve()), indent=2, default=str))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Self-contained long reference runs (Linux or macOS), using only files in this repository.

  inputs     build outputs/reference-inputs/cold.xml.gz (selected plan per person from
             scenarios/nyc/population-v6.xml.gz), as the earlier pilot runs did
  run        one run: --seed, --iterations, online metrics, no per-iteration event XML by default;
             --research adds ResearchMetrics records (and events every 10 iterations unless set otherwise)
  summarize  per-iteration table (score, mode shares, online metrics, stage times) of a run directory
  verify     compare a 12-iteration seed-4711 run with the reference values recorded on the original machine

The scenario is the launch-2025 pricing configuration (scenarios/nyc-zip-aligned/config-actual2025.xml) with the
archived capacity factors (assumptions/archive-capacity-factors.csv; equal to the paper's Table 4 to 2 decimals).
"""
import argparse, csv, datetime, hashlib, json, os, platform, shutil, signal, subprocess, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import population_inputs as P   # selected_only, setparam (same preparation as the recorded runs)

BASE = ROOT/'scenarios/nyc-zip-aligned/config-actual2025.xml'
FACTORS = ROOT/'assumptions/archive-capacity-factors.csv'
INPUTS = ROOT/'outputs/reference-inputs'
JAR = ROOT/'target/matsim-nyc-modernized-1.0.0.jar'
EXPECTED = Path(__file__).with_name('expected-seed4711-12it.json')


def java():
    env = ROOT/'.tools/environment.json'
    if os.environ.get('JAVA_HOME'):
        return str(Path(os.environ['JAVA_HOME'])/'bin/java')
    if env.exists():
        return str(Path(json.loads(env.read_text())['java_home'])/'bin/java')
    return shutil.which('java') or 'java'


def build_inputs(args):
    INPUTS.mkdir(parents=True, exist_ok=True)
    target = INPUTS/'cold.xml.gz'
    if target.exists() and not args.force:
        print('exists', target); return
    info = P.selected_only(ROOT/'scenarios/nyc/population-v6.xml.gz', target)
    if info['persons'] != 389301:
        raise SystemExit(f"expected 389301 persons, got {info['persons']}")
    (INPUTS/'cold.json').write_text(json.dumps(info, indent=2) + '\n')
    print('wrote', target, info['groups'])


def write_config(dest, seed, iterations, events_interval, plans_every, threads, *, scenario='actual2025',
                 plans=None, innovation_until=None, factors=FACTORS, events_threads=None):
    base = ROOT/f'scenarios/nyc-zip-aligned/config-{scenario}.xml'
    root = ET.parse(base).getroot()
    folder = base.parent
    for module in root:
        for p in module.findall('param'):
            k, v = p.get('name'), p.get('value')
            if k in ['inputCountsFile', 'inputNetworkFile', 'inputPlansFile', 'transitScheduleFile', 'vehiclesFile', 'tollLinksFile'] and v != 'null':
                p.set('value', str((folder/v).resolve()))
            if k == 'pricing2025Links':
                p.set('value', str(ROOT/'scenarios/nyc-2025/links.csv'))
            if k == 'archiveCapacityFactors':
                p.set('value', str(Path(factors).resolve()))
    for mod in root.findall('module'):
        mod.set('name', {'controler': 'controller', 'planCalcScore': 'scoring'}.get(mod.get('name'), mod.get('name')))
    if innovation_until is not None:
        # Absolute schedule (MATSim's disableAfterIteration): shortening the horizon does not move the cutoff.
        P.setparam(root, 'strategy', 'fractionOfIterationsToDisableInnovation', '1.0')
        for strategy in root.findall("./module[@name='strategy']/parameterset"):
            name = strategy.find("param[@name='strategyName']")
            if name is not None and name.get('value') not in ('SelectExpBeta', 'ChangeExpBeta', 'BestScore', 'KeepLastSelected'):
                param = strategy.find("param[@name='disableAfterIteration']")
                if param is None: param = ET.SubElement(strategy, 'param', name='disableAfterIteration')
                param.set('value', str(innovation_until))
    for module, name, value in [('plans', 'inputPlansFile', Path(plans).resolve() if plans else INPUTS/'cold.xml.gz'), ('controller', 'outputDirectory', dest/'simulation'),
                                ('controller', 'firstIteration', 0), ('controller', 'lastIteration', iterations - 1),
                                ('controller', 'writeEventsInterval', events_interval), ('controller', 'writePlansInterval', plans_every),
                                ('controller', 'createGraphsInterval', 1), ('global', 'randomSeed', seed),
                                ('global', 'numberOfThreads', threads), ('qsim', 'numberOfThreads', threads)]:
        P.setparam(root, module, name, str(value))
    if events_threads:
        # MATSim's SimStepParallelEventsManagerImpl with this many threads (default: 1); handlers are spread over them.
        if root.find("module[@name='eventsManager']") is None: ET.SubElement(root, 'module', name='eventsManager')
        P.setparam(root, 'eventsManager', 'numberOfThreads', str(events_threads))
    ET.indent(root)
    path = dest/'config.xml'
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE config SYSTEM "http://www.matsim.org/files/dtd/config_v2.dtd">\n' + ET.tostring(root, encoding='unicode'))
    return path


def rss_of(pid):
    try:
        out = subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
        return int(out) * 1024 if out else 0
    except Exception:
        return 0


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()


def process_sample(pid):
    sample = {'rss_bytes': rss_of(pid)}
    try:
        stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        sample['cpu_seconds'] = (int(stat[11]) + int(stat[12])) / os.sysconf('SC_CLK_TCK')
        sample['threads'] = int(stat[17])
        for line in Path(f'/proc/{pid}/io').read_text().splitlines():
            k, v = line.split(':'); sample[k] = int(v)
    except (OSError, ValueError): pass
    return sample


def check_polygon(path):
    """GeoJSON Feature or geometry with a closed Polygon exterior ring in WGS84 (what ResearchMetrics reads)."""
    data = json.loads(Path(path).read_text())
    geometry = data.get('geometry', data)
    ring = (geometry.get('coordinates') or [None])[0]
    if geometry.get('type') != 'Polygon' or not ring or len(ring) < 4 or ring[0] != ring[-1]:
        raise SystemExit(f'{path}: expected a GeoJSON Polygon with a closed exterior ring of at least 4 points')
    if not all(-180 <= x <= 180 and -90 <= y <= 90 for x, y, *_ in ring):
        raise SystemExit(f'{path}: coordinates must be longitude/latitude (EPSG:4326)')
    return {'points': len(ring), 'status': data.get('properties', {}).get('status')}


def check_metric_links(path):
    """CSV with header id,entry,... and entry in {0,1} (what IterationMetrics and ResearchMetrics read)."""
    with open(path, newline='') as f:
        reader = csv.reader(f); header = next(reader)
        if header[:2] != ['id', 'entry']: raise SystemExit(f'{path}: expected header starting with id,entry, got {header}')
        rows = [r for r in reader if r]
    if not rows or any(r[1] not in ('0', '1') for r in rows): raise SystemExit(f'{path}: entry column must be 0 or 1')
    return {'links': len(rows), 'entry_links': sum(r[1] == '1' for r in rows)}


def run(args):
    if not os.environ.get('SLURM_JOB_ID'):
        raise SystemExit('Full simulations require a Slurm allocation; submit reference.sbatch.')
    plans = Path(args.plans).resolve() if args.plans else INPUTS/'cold.xml.gz'
    if not plans.is_file(): raise SystemExit('Missing input plans: run inputs first, or supply --plans')
    if not JAR.exists(): raise SystemExit('build first: mvn -DskipTests package')
    if args.iterations < 1 or args.threads < 1 or args.min_free_gib < 0: raise SystemExit('Invalid resource/iteration setting')
    if args.innovation_until is not None and args.innovation_until < 0: raise SystemExit('innovation-until must be nonnegative')
    if args.events_interval is not None and args.events_interval < 0: raise SystemExit('events-interval must be nonnegative')
    if args.plans_every is not None and args.plans_every < 1: raise SystemExit('plans-every must be positive')
    if args.events_interval is not None and args.events != 'none': raise SystemExit('Use either --events or --events-interval')
    metric_links, polygon = Path(args.metric_links).resolve(), Path(args.cohort_polygon).resolve()
    inputs_checked = {'metric_links': check_metric_links(metric_links)}
    if args.research: inputs_checked['cohort_polygon'] = check_polygon(polygon)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    dest = Path(args.out or ROOT/'outputs'/f'{args.scenario}-s{args.seed}-{args.iterations}it-{stamp}').resolve()
    dest.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(dest).free < args.min_free_gib * 2**30:
        raise SystemExit('Insufficient filesystem free space; this check cannot see your user quota')
    # Each run loads a private copy of the JAR, so rebuilding target/ cannot change a running job.
    jar = dest/'runner.jar'
    shutil.copy2(JAR, jar)
    events_interval = args.events_interval
    if events_interval is None:
        events_interval = 10 if args.research and args.events == 'none' else {'none': 0, 'last': max(1, args.iterations - 1), 'all': 1}[args.events]
    plans_every = args.plans_every or max(1, args.iterations - 1)
    cfg = write_config(dest, args.seed, args.iterations, events_interval, plans_every, args.threads, scenario=args.scenario,
                       plans=plans, innovation_until=args.innovation_until, factors=args.factors, events_threads=args.events_threads)
    check = subprocess.run([java(), '-cp', str(jar), 'org.c2smart.matsimnyc.ReferenceConfigCheck', str(cfg), str(args.iterations),
                            str(-1 if args.innovation_until is None else args.innovation_until), str(events_interval), str(plans_every)],
                           capture_output=True, text=True)
    if check.returncode != 0: raise SystemExit('MATSim config check failed:\n' + check.stdout[-2000:] + check.stderr[-2000:])
    config_check = [l for l in check.stdout.splitlines() if l.startswith('PASS')]
    extra = (['-Dnyc.replanningLog=true'] if args.replanning_log else []) \
        + ([f'-Dnyc.targeted.priority={Path(args.targeted_priority).resolve()}'] if args.targeted_priority else []) \
        + ([f'-Dnyc.targeted.epsilon={args.targeted_epsilon}'] if args.targeted_epsilon is not None else []) \
        + (['-Dnyc.researchMetrics=true', f'-Dnyc.cohortPolygon={polygon}'] if args.research else []) \
        + (['-Dnyc.legacyTollRouting=true'] if args.legacy_toll_routing else [])
    cmd = [java(), '-Duser.language=en', '-Duser.country=US', f'-Xmx{args.heap}', '-Dnyc.onlineMetrics=true',
           f'-Dnyc.metricLinks={metric_links}', *extra, '-Xlog:gc*:file=' + str(dest/'gc.log') + ':time,uptime,level,tags']
    if args.jfr:
        cmd += ['-XX:StartFlightRecording=settings=default,disk=true,maxsize=256m,dumponexit=true,filename=' + str(dest/'profile.jfr')]
    cmd += ['-jar', str(jar), str(cfg)]
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    # Hash the concrete configuration and inputs, not just the Git revision of a possibly dirty checkout.
    files = {str(plans): sha256(plans), str(jar): sha256(jar), str(cfg): sha256(cfg), str(metric_links): sha256(metric_links)}
    if args.research: files[str(polygon)] = sha256(polygon)
    for module in ET.parse(cfg).getroot():
        for param in module.findall('param'):
            path = Path(param.get('value', ''))
            if path.is_absolute() and path.is_file(): files[str(path)] = sha256(path)
    meta = {'schema_version': 3, 'seed': args.seed, 'scenario': args.scenario, 'iterations': args.iterations,
            'events': args.events, 'events_interval': events_interval, 'plans_interval': plans_every,
            'research': args.research, 'replanning_log': args.replanning_log, 'legacy_toll_routing': args.legacy_toll_routing,
            'targeted_priority': args.targeted_priority, 'targeted_epsilon': args.targeted_epsilon,
            'innovation_until': args.innovation_until, 'innovation_fraction': 0.8 if args.innovation_until is None else 1.0,
            'plans': str(plans), 'expected_persons': json.loads((INPUTS/'cold.json').read_text())['persons'] if plans == INPUTS/'cold.xml.gz' and (INPUTS/'cold.json').exists() else None,
            'metric_links': str(metric_links), 'cohort_polygon': str(polygon) if args.research else None,
            'inputs_checked': inputs_checked, 'config_check': config_check,
            'threads': args.threads, 'events_threads': args.events_threads, 'heap': args.heap, 'jfr': args.jfr, 'command': cmd,
            'commit': commit, 'worktree_dirty': bool(dirty), 'sha256': files,
            'host': os.uname().nodename, 'platform': platform.platform(),
            'java_version': subprocess.run([java(), '-version'], capture_output=True, text=True).stderr,
            'allocated_cpus': os.environ.get('SLURM_CPUS_PER_TASK'), 'allocated_memory_mb': os.environ.get('SLURM_MEM_PER_NODE'),
            'slurm_job_id': os.environ.get('SLURM_JOB_ID'), 'started': datetime.datetime.now().isoformat(), 'state': 'running'}
    (dest/'run.json').write_text(json.dumps(meta, indent=2) + '\n')
    shutil.copy2(__file__, dest/'run_reference.py')
    print('running in', dest, flush=True)
    start = time.monotonic(); peak = 0; proc = None; reason = None; code = None
    def terminate(signum, frame):
        nonlocal reason
        reason = f'signal {signum}'
        if proc and proc.poll() is None: proc.terminate()
    previous = {sig: signal.signal(sig, terminate) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        with open(dest/'run.log', 'w') as log, open(dest/'resources.jsonl', 'w') as resources:
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            while proc.poll() is None:
                sample = process_sample(proc.pid); peak = max(peak, sample['rss_bytes'])
                sample.update(elapsed_seconds=time.monotonic() - start, free_bytes=shutil.disk_usage(dest).free)
                resources.write(json.dumps(sample) + '\n'); resources.flush()
                if sample['free_bytes'] < args.min_free_gib * 2**30:
                    reason = 'filesystem free-space floor reached'; proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if reason: proc.kill(); proc.wait()
            code = proc.returncode
        meta.update(ended=datetime.datetime.now().isoformat(), exit_code=code, wall_seconds=time.monotonic() - start,
                    peak_rss_gib=peak / 2**30, state='completed' if code == 0 and not reason else 'failed', stop_reason=reason)
    except BaseException as exc:
        if proc and proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        meta.update(state='failed', error=repr(exc), wall_seconds=time.monotonic() - start)
        raise
    finally:
        for sig, handler in previous.items(): signal.signal(sig, handler)
        (dest/'run.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(json.dumps({k: meta.get(k) for k in ['state', 'exit_code', 'wall_seconds', 'peak_rss_gib', 'stop_reason']}), flush=True)
    if code == 0 and not reason: summarize_dir(dest)
    sys.exit(code if code else (1 if reason else 0))


def secs(t):
    h, m, s = t.split(':')
    return int(h) * 3600 + int(m) * 60 + int(s)


def table(path):
    with open(path) as f:
        return list(csv.DictReader(f, delimiter=';'))


def stopwatch_table(path):
    # MATSim 2026 writes both the integer index and the duration as "iteration".
    # csv.DictReader silently overwrites the former with the latter.
    with open(path, newline='') as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader)
        seen_index = False
        names = []
        for name in header:
            if name == 'iteration':
                names.append('iteration_duration' if seen_index else 'iteration')
                seen_index = True
            else:
                names.append(name)
        return [dict(zip(names, row)) for row in reader if row]


def summarize_dir(dest):
    sim = Path(dest)/'simulation'
    scores = {int(r['iteration']): float(r['avg_executed']) for r in table(sim/'BUILT.scorestats.csv')}
    modes = {int(r['iteration']): r for r in table(sim/'BUILT.modestats.csv')}
    watch = {int(r['iteration']): r for r in stopwatch_table(sim/'BUILT.stopwatch.csv')}
    rows = []
    for i in sorted(scores):
        m = json.loads((sim/f'iteration-metrics-{i}.json').read_text()) if (sim/f'iteration-metrics-{i}.json').exists() else {}
        w = watch.get(i, {})
        rows.append({'iteration': i, 'score': scores[i], 'car_share': float(modes[i]['car']), 'pt_share': float(modes[i]['pt']),
                     'unfinished': m.get('unfinished_all'), 'car_entries': m.get('private_car_entry_crossings'),
                     'not_boarded': m.get('waiting_at_cutoff'), 'revenue_usd': m.get('net_congestion_revenue'),
                     'iteration_s': secs(w['iteration_duration']) if w.get('iteration_duration') else None,
                     'mobsim_s': secs(w['mobsim']) if w.get('mobsim') else None,
                     'replanning_s': secs(w['replanning']) if w.get('replanning') else None})
    with open(Path(dest)/'summary.csv', 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
    for r in rows:
        print(' '.join(f'{k}={v:.4f}' if isinstance(v, float) else f'{k}={v}' for k, v in r.items()))
    return rows


def verify(args):
    run_dir = Path(args.run_dir)
    meta = json.loads((run_dir/'run.json').read_text())
    if (meta.get('seed') != 4711 or meta.get('iterations') != 12 or meta.get('scenario', 'actual2025') != 'actual2025'
            or meta.get('innovation_until') is not None or meta.get('plans', str(INPUTS/'cold.xml.gz')) != str(INPUTS/'cold.xml.gz')
            or meta.get('exit_code') != 0):
        raise SystemExit('Historical verification needs a successful cold actual2025 seed-4711 12-iteration run with the historical innovation schedule')
    expected = json.loads(EXPECTED.read_text())
    sim = run_dir/'simulation'; bad = 0
    for i, exp in enumerate(expected['iteration_metrics']):
        got = json.loads((sim/f'iteration-metrics-{i}.json').read_text())
        got.pop('iteration', None); e = dict(exp); e.pop('iteration', None)
        if got != e:
            bad += 1; print(f'iteration {i}: differs', {k: (e.get(k), got.get(k)) for k in e if e.get(k) != got.get(k)})
    scores = [float(r['avg_executed']) for r in table(sim/'BUILT.scorestats.csv')]
    if scores != expected['scores']:
        bad += 1; print('scores differ', list(zip(expected['scores'], scores)))
    (run_dir/'verification.json').write_text(json.dumps({'passed': not bad, 'differences': bad, 'reference': str(EXPECTED),
                                                         'reference_sha256': sha256(EXPECTED)}, indent=2) + '\n')
    print('IDENTICAL to the original machine' if not bad else f'{bad} differences (see above)')
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('inputs'); a.add_argument('--force', action='store_true')
    r = sub.add_parser('run')
    r.add_argument('--seed', type=int, default=4711); r.add_argument('--iterations', type=int, default=100)
    r.add_argument('--events', choices=['none', 'last', 'all'], default='none', help='event XML: none (default), last iteration(s), or every iteration')
    r.add_argument('--plans-every', type=int, help='write plans every N iterations (default: last iteration)')
    r.add_argument('--threads', type=int, default=16); r.add_argument('--heap', default='16g'); r.add_argument('--out')
    r.add_argument('--replanning-log', action='store_true', help='write OUTPUT/simulation/replanning-log/ (W1)')
    r.add_argument('--targeted-priority', help='priority CSV file or directory for the targeted chooser (W3)')
    r.add_argument('--targeted-epsilon', type=float, help='random share of the innovation budget for the targeted chooser (W3)')
    r.add_argument('--scenario', choices=['baseline', 'schema1', 'actual2025'], default='actual2025')
    r.add_argument('--plans', help='warm-start plans instead of outputs/reference-inputs/cold.xml.gz')
    r.add_argument('--factors', type=Path, default=FACTORS)
    r.add_argument('--events-interval', type=int, help='write events every N iterations and in the last one (0 = never); research default 10')
    r.add_argument('--innovation-until', type=int, help="absolute disableAfterIteration for innovation strategies; omitted keeps the historical fraction 0.8")
    r.add_argument('--research', action='store_true', help='detailed per-person, group and link-hour records (ResearchMetrics)')
    r.add_argument('--metric-links', default=str(ROOT/'scenarios/nyc-2025/links.csv'), help='entry-link CSV for private-car crossing counts')
    r.add_argument('--cohort-polygon', default=str(ROOT/'scenarios/nyc-schema1/cordon-outline.geojson'), help='GeoJSON polygon defining the charging-related cohort')
    r.add_argument('--jfr', action='store_true', help='bounded Java Flight Recorder profile')
    r.add_argument('--min-free-gib', type=float, default=5)
    r.add_argument('--legacy-toll-routing', action='store_true', help='diagnostic: let car routing see the historical facility tolls (baseline only; changes results)')
    r.add_argument('--events-threads', type=int, help="eventsManager.numberOfThreads (MATSim default 1); must be verified against the expected values")
    s = sub.add_parser('summarize'); s.add_argument('run_dir')
    v = sub.add_parser('verify'); v.add_argument('run_dir')
    args = ap.parse_args()
    {'inputs': build_inputs, 'run': run, 'summarize': lambda a: summarize_dir(a.run_dir), 'verify': verify}[args.cmd](args)


if __name__ == '__main__':
    main()

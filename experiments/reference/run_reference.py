#!/usr/bin/env python3
"""Self-contained long reference runs (Linux or macOS), using only files in this repository.

  inputs     build outputs/reference-inputs/cold.xml.gz (selected plan per person from
             scenarios/nyc/population-v6.xml.gz), as the earlier pilot runs did
  run        one run: --seed, --iterations, online metrics, no per-iteration event XML by default
  summarize  per-iteration table (score, mode shares, online metrics, stage times) of a run directory
  verify     compare a 12-iteration seed-4711 run with the reference values recorded on the original machine

The scenario is the launch-2025 pricing configuration (scenarios/nyc-zip-aligned/config-actual2025.xml) with the
archived capacity factors (assumptions/archive-capacity-factors.csv; equal to the paper's Table 4 to 2 decimals).
"""
import argparse, csv, datetime, hashlib, json, os, platform, shutil, signal, subprocess, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'experiments/acceleration'))
import pilot as P   # selected_only, setparam, stream (same preparation as the recorded runs)

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


def write_config(dest, seed, iterations, events, plans_every, threads, *, scenario='actual2025',
                 plans=None, events_interval=None, innovation_until=None, factors=FACTORS):
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
    interval = events_interval if events_interval is not None else {'none': 0, 'last': max(1, iterations - 1), 'all': 1}[events]
    if innovation_until is not None:
        # Absolute iteration schedule: shortening the horizon must not silently move the cutoff.
        P.setparam(root, 'strategy', 'fractionOfIterationsToDisableInnovation', '1.0')
        for strategy in root.findall("./module[@name='strategy']/parameterset"):
            name = strategy.find("param[@name='strategyName']")
            if name is not None and name.get('value') not in ('SelectExpBeta', 'ChangeExpBeta', 'BestScore', 'KeepLastSelected'):
                param = strategy.find("param[@name='disableAfter']")
                if param is None: param = ET.SubElement(strategy, 'param', name='disableAfter')
                param.set('value', str(innovation_until))
    for module, name, value in [('plans', 'inputPlansFile', Path(plans).resolve() if plans else INPUTS/'cold.xml.gz'), ('controller', 'outputDirectory', dest/'simulation'),
                                ('controller', 'firstIteration', 0), ('controller', 'lastIteration', iterations - 1),
                                ('controller', 'writeEventsInterval', interval), ('controller', 'writePlansInterval', plans_every),
                                ('counts', 'writeCountsInterval', 1), ('controller', 'createGraphsInterval', 1), ('global', 'randomSeed', seed),
                                ('global', 'numberOfThreads', threads), ('qsim', 'numberOfThreads', threads)]:
        P.setparam(root, module, name, str(value))
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
        sample['cpu_seconds'] = (int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK')
        sample['threads'] = int(stat[17])
        for line in Path(f'/proc/{pid}/io').read_text().splitlines():
            k, v = line.split(':'); sample[k] = int(v)
    except (OSError, ValueError): pass
    return sample


def run(args):
    if not os.environ.get('SLURM_JOB_ID'):
        raise SystemExit('Full simulations require a Slurm allocation; submit reference.sbatch.')
    plans = Path(args.plans).resolve() if args.plans else INPUTS/'cold.xml.gz'
    jar = Path(args.jar).resolve()
    if not plans.is_file(): raise SystemExit('Missing input plans: run inputs first, or supply --plans')
    if not jar.is_file(): raise SystemExit('Build first, or supply --jar')
    if args.iterations < 1 or args.threads < 1 or args.min_free_gib < 0: raise SystemExit('Invalid resource/iteration setting')
    if args.innovation_until is not None and args.innovation_until < 0: raise SystemExit('innovation-until must be nonnegative')
    if args.events_interval is not None and args.events_interval < 0: raise SystemExit('events-interval must be nonnegative')
    if args.plans_every is not None and args.plans_every < 1: raise SystemExit('plans-every must be positive')
    if args.events_interval is not None and args.events != 'none': raise SystemExit('Use either --events or --events-interval')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    dest = Path(args.out or ROOT/'outputs'/f'{args.scenario}-s{args.seed}-{args.iterations}it-{stamp}').resolve()
    dest.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(dest).free < args.min_free_gib * 2**30:
        raise SystemExit('Insufficient filesystem free space; this check cannot see your user quota')
    # Every run loads a private JAR; rebuilding the workspace cannot change a running job.
    frozen_jar = dest/'runner.jar'; shutil.copy2(jar, frozen_jar)
    events_interval = args.events_interval
    if args.research and events_interval is None and args.events == 'none': events_interval = 10
    cfg = write_config(dest, args.seed, args.iterations, args.events,
                       args.plans_every or max(1,args.iterations-1), args.threads,
                       scenario=args.scenario, plans=plans, events_interval=events_interval,
                       innovation_until=args.innovation_until, factors=args.factors)
    cmd = [java(), '-Duser.language=en', '-Duser.country=US', f'-Xmx{args.heap}', '-Dnyc.onlineMetrics=true',
           '-Dnyc.metricLinks='+str(ROOT/'scenarios/nyc-2025/links.csv'),
           '-Xlog:gc*:file=' + str(dest/'gc.log') + ':time,uptime,level,tags']
    if args.research:
        cmd += ['-Dnyc.researchMetrics=true', '-Dnyc.cohortPolygon='+str(ROOT/'scenarios/nyc-schema1/cordon-outline.geojson')]
    if args.jfr:
        cmd += ['-XX:StartFlightRecording=settings=default,disk=true,maxsize=256m,dumponexit=true,filename='+str(dest/'profile.jfr')]
    cmd += ['-jar', str(frozen_jar), str(cfg)]
    commit = subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()
    snapshot = ROOT/'snapshot.json'
    provenance = json.loads(snapshot.read_text()) if snapshot.exists() else {'commit':commit}
    # Hash concrete configuration and inputs, not just the Git revision of a possibly dirty checkout.
    files = {str(plans):sha256(plans), str(frozen_jar):sha256(frozen_jar), str(cfg):sha256(cfg)}
    for module in ET.parse(cfg).getroot():
        for param in module.findall('param'):
            value = param.get('value',''); path = Path(value)
            if path.is_absolute() and path.is_file(): files[value] = sha256(path)
    for path in [Path(args.factors), ROOT/'scenarios/nyc-schema1/cordon-outline.geojson', ROOT/'scenarios/nyc-2025/links.csv']:
        files[str(path.resolve())] = sha256(path)
    meta = {'schema_version':2,'seed':args.seed,'scenario':args.scenario,'iterations':args.iterations,
            'events':args.events,'events_interval':events_interval,'research':args.research,
            'innovation_until':args.innovation_until,'innovation_fraction':0.8 if args.innovation_until is None else 1.0,
            'plans':str(plans),'threads':args.threads,'heap':args.heap,'jfr':args.jfr,
            'command':cmd,'commit':commit or provenance.get('commit'),'provenance':provenance,'sha256':files,
            'host':os.uname().nodename,'platform':platform.platform(),
            'java_version':subprocess.run([java(),'-version'],capture_output=True,text=True).stderr,
            'allocated_cpus':os.environ.get('SLURM_CPUS_PER_TASK'),
            'allocated_memory_mb':os.environ.get('SLURM_MEM_PER_NODE'),
            'slurm_job_id':os.environ.get('SLURM_JOB_ID'),
            'started':datetime.datetime.now().isoformat(),'state':'running'}
    (dest/'run.json').write_text(json.dumps(meta,indent=2)+'\n')
    shutil.copy2(__file__,dest/'run_reference.py')
    print('running in',dest,flush=True)
    start=time.monotonic();peak=0;proc=None;reason=None
    def terminate(signum, frame):
        nonlocal reason
        reason=f'signal {signum}'
        if proc and proc.poll() is None: proc.terminate()
    previous={sig:signal.signal(sig,terminate) for sig in (signal.SIGTERM,signal.SIGINT)}
    try:
        with open(dest/'run.log','w') as log, open(dest/'resources.jsonl','w') as resources:
            proc=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            while proc.poll() is None:
                sample=process_sample(proc.pid);peak=max(peak,sample['rss_bytes'])
                sample.update(elapsed_seconds=time.monotonic()-start,free_bytes=shutil.disk_usage(dest).free)
                resources.write(json.dumps(sample)+'\n');resources.flush()
                if sample['free_bytes'] < args.min_free_gib*2**30:
                    reason='filesystem free-space floor reached';proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if reason: proc.kill();proc.wait()
            code=proc.returncode
        meta.update(ended=datetime.datetime.now().isoformat(),exit_code=code,wall_seconds=time.monotonic()-start,
                    peak_rss_gib=peak/2**30,state='completed' if code==0 and not reason else 'failed',stop_reason=reason)
    except BaseException as exc:
        if proc and proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired: proc.kill();proc.wait()
        meta.update(state='failed',error=repr(exc),wall_seconds=time.monotonic()-start)
        raise
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)
        (dest/'run.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps(meta,indent=2),flush=True)
    if code==0 and not reason: summarize_dir(dest)
    sys.exit(code if code else (1 if reason else 0))


def secs(t):
    h, m, s = t.split(':')
    return int(h) * 3600 + int(m) * 60 + int(s)


def table(path):
    with open(path) as f:
        return list(csv.DictReader(f, delimiter=';'))


def summarize_dir(dest):
    sim = Path(dest)/'simulation'
    scores = {int(r['iteration']): float(r['avg_executed']) for r in table(sim/'BUILT.scorestats.csv')}
    modes = {int(r['iteration']): r for r in table(sim/'BUILT.modestats.csv')}
    watch = {int(r['iteration']): r for r in table(sim/'BUILT.stopwatch.csv')}
    rows = []
    for i in sorted(scores):
        m = json.loads((sim/f'iteration-metrics-{i}.json').read_text()) if (sim/f'iteration-metrics-{i}.json').exists() else {}
        w = watch.get(i, {})
        rows.append({'iteration': i, 'score': scores[i], 'car_share': float(modes[i]['car']), 'pt_share': float(modes[i]['pt']),
                     'unfinished': m.get('unfinished_all'), 'car_entries': m.get('private_car_entry_crossings'),
                     'not_boarded': m.get('waiting_at_cutoff'), 'revenue_usd': m.get('net_congestion_revenue'),
                     'mean_completed_car_leg_seconds': m.get('mean_completed_car_leg_seconds'),
                     'censored_wait_person_hours': m.get('censored_wait_person_hours'),
                     'iteration_s': secs(w['iteration_duration']) if w.get('iteration_duration') else None,
                     'mobsim_s': secs(w['mobsim']) if w.get('mobsim') else None,
                     'replanning_s': secs(w['replanning']) if w.get('replanning') else None})
    if not rows: raise ValueError('No completed iterations found')
    with open(Path(dest)/'summary.csv', 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
    for r in rows:
        print(' '.join(f'{k}={v:.4f}' if isinstance(v, float) else f'{k}={v}' for k, v in r.items()))
    return rows


def verify(args):
    run_dir = Path(args.run_dir)
    meta = json.loads((run_dir/'run.json').read_text())
    if meta.get('seed') != 4711 or meta.get('iterations') != 12 or meta.get('scenario','actual2025') != 'actual2025' or meta.get('exit_code') != 0:
        raise SystemExit('Historical verification requires a successful actual2025 seed-4711 12-iteration run')
    expected = json.loads(EXPECTED.read_text())
    sim = Path(args.run_dir)/'simulation'; bad = 0
    for i, exp in enumerate(expected['iteration_metrics']):
        got = json.loads((sim/f'iteration-metrics-{i}.json').read_text())
        got.pop('iteration', None); e = dict(exp); e.pop('iteration', None)
        if got != e:
            bad += 1; print(f'iteration {i}: differs', {k: (e.get(k), got.get(k)) for k in e if e.get(k) != got.get(k)})
    scores = [float(r['avg_executed']) for r in table(sim/'BUILT.scorestats.csv')]
    if scores != expected['scores']:
        bad += 1; print('scores differ', list(zip(expected['scores'], scores)))
    (run_dir/'verification.json').write_text(json.dumps({'passed':not bad,'differences':bad,'reference':str(EXPECTED),'reference_sha256':sha256(EXPECTED)},indent=2)+'\n')
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
    r.add_argument('--scenario',choices=['baseline','schema1','actual2025'],default='actual2025')
    r.add_argument('--plans',help='Warm-start plans (full baseline plan set for paper policy experiments)')
    r.add_argument('--jar',default=str(JAR))
    r.add_argument('--factors',type=Path,default=FACTORS)
    r.add_argument('--events-interval',type=int,help='0 disables events; research default is 10')
    r.add_argument('--innovation-until',type=int,help='Absolute disableAfter for innovation strategies; omitted preserves historical fraction 0.8')
    r.add_argument('--research',action='store_true',help='Separate per-person, cohort and link-hour data')
    r.add_argument('--jfr',action='store_true',help='Bounded Java Flight Recorder for CPU/allocation/lock/GC diagnosis')
    r.add_argument('--min-free-gib',type=float,default=5)
    s = sub.add_parser('summarize'); s.add_argument('run_dir')
    v = sub.add_parser('verify'); v.add_argument('run_dir')
    args = ap.parse_args()
    {'inputs': build_inputs, 'run': run, 'summarize': lambda a: summarize_dir(a.run_dir), 'verify': verify}[args.cmd](args)


if __name__ == '__main__':
    main()

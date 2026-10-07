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
import argparse, csv, datetime, json, os, shutil, subprocess, sys, time
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


def write_config(dest, seed, iterations, events, plans_every, threads):
    root = ET.parse(BASE).getroot()
    folder = BASE.parent
    for module in root:
        for p in module.findall('param'):
            k, v = p.get('name'), p.get('value')
            if k in ['inputCountsFile', 'inputNetworkFile', 'inputPlansFile', 'transitScheduleFile', 'vehiclesFile', 'tollLinksFile'] and v != 'null':
                p.set('value', str((folder/v).resolve()))
            if k == 'pricing2025Links':
                p.set('value', str(ROOT/'scenarios/nyc-2025/links.csv'))
            if k == 'archiveCapacityFactors':
                p.set('value', str(FACTORS))
    for mod in root.findall('module'):
        mod.set('name', {'controler': 'controller', 'planCalcScore': 'scoring'}.get(mod.get('name'), mod.get('name')))
    interval = {'none': 0, 'last': max(1, iterations - 1), 'all': 1}[events]
    for module, name, value in [('plans', 'inputPlansFile', INPUTS/'cold.xml.gz'), ('controller', 'outputDirectory', dest/'simulation'),
                                ('controller', 'firstIteration', 0), ('controller', 'lastIteration', iterations - 1),
                                ('controller', 'writeEventsInterval', interval), ('controller', 'writePlansInterval', plans_every),
                                ('controller', 'createGraphsInterval', 1), ('global', 'randomSeed', seed),
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


def run(args):
    if not (INPUTS/'cold.xml.gz').exists():
        raise SystemExit('run "inputs" first')
    if not JAR.exists():
        raise SystemExit('build first: mvn -DskipTests package')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    dest = Path(args.out or ROOT/'outputs'/f'reference-s{args.seed}-{args.iterations}it-{stamp}').resolve()
    dest.mkdir(parents=True, exist_ok=False)
    cfg = write_config(dest, args.seed, args.iterations, args.events, args.plans_every or max(1, args.iterations - 1), args.threads)
    cmd = [java(), '-Duser.language=en', '-Duser.country=US', f'-Xmx{args.heap}', '-Dnyc.onlineMetrics=true',
           '-Xlog:gc*:file=' + str(dest/'gc.log') + ':time,uptime,level,tags', '-jar', str(JAR), str(cfg)]
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    meta = {'seed': args.seed, 'iterations': args.iterations, 'events': args.events, 'threads': args.threads, 'heap': args.heap,
            'command': cmd, 'commit': commit, 'host': os.uname().nodename, 'started': datetime.datetime.now().isoformat()}
    (dest/'run.json').write_text(json.dumps(meta, indent=2) + '\n')
    print('running in', dest, flush=True)
    start = time.monotonic(); peak = 0
    with open(dest/'run.log', 'w') as log:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            peak = max(peak, rss_of(proc.pid))
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
    meta.update(ended=datetime.datetime.now().isoformat(), exit_code=proc.returncode, wall_seconds=time.monotonic() - start, peak_rss_gib=peak / 2**30)
    (dest/'run.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(json.dumps({k: meta[k] for k in ['exit_code', 'wall_seconds', 'peak_rss_gib']}), flush=True)
    if proc.returncode == 0:
        summarize_dir(dest)
    sys.exit(proc.returncode)


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
    s = sub.add_parser('summarize'); s.add_argument('run_dir')
    v = sub.add_parser('verify'); v.add_argument('run_dir')
    args = ap.parse_args()
    {'inputs': build_inputs, 'run': run, 'summarize': lambda a: summarize_dir(a.run_dir), 'verify': verify}[args.cmd](args)


if __name__ == '__main__':
    main()

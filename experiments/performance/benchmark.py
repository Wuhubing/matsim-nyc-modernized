#!/usr/bin/env python3
"""Sequential, shared-budget performance experiment. No simulation on import."""
import argparse
import copy
import csv
import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'experiments/acceleration'))
import pilot as P
import event_metrics as EM
D = P.D
DEFAULT_SOURCE = ROOT / 'outputs/acceleration-pilot-20261004-032117'
SHORTS = [('profile', 'baseline'), ('baseline', 'baseline'), ('qsim10', 'qsim10'), ('output', 'output')]
OUTPUT_SETTINGS = {('controller', 'createGraphsInterval'): '0', ('controller', 'writePlansInterval'): '0', ('scoring', 'writeExperiencedPlans'): 'false'}
RTOL, ATOL = 1e-9, 1e-8


def read(path):
    return json.loads(path.read_text())


def config_tree(source, dest, variant, iterations):
    root = ET.parse(source / 'cold-attempt-1/config.xml').getroot()
    for mod in root.findall('module'):
        # Use current names, including legacy names accepted in historical input.
        mod.set('name', {'controler': 'controller', 'planCalcScore': 'scoring'}.get(mod.get('name'), mod.get('name')))
    settings = {('controller', 'outputDirectory'): str(dest / 'simulation'), ('controller', 'lastIteration'): str(iterations-1), ('controller', 'createGraphsInterval'): '1'}
    if variant == 'qsim10':
        settings[('qsim', 'numberOfThreads')] = '10'
    elif variant == 'output':
        settings.update(OUTPUT_SETTINGS)
    elif variant != 'baseline':
        raise ValueError('Unknown variant')
    for (module, name), value in settings.items():
        P.setparam(root, module, name, value)
    return root


def write_config(root, path):
    ET.indent(root)
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE config SYSTEM "http://www.matsim.org/files/dtd/config_v2.dtd">\n'+ET.tostring(root,encoding='unicode'))


def canonical(root):
    def walk(e):
        return (e.tag, tuple(sorted(e.attrib.items())), (e.text or '').strip(), tuple(sorted(walk(c) for c in e)))
    return walk(root)


def check_configs(base, candidate, variant):
    a, b = copy.deepcopy(base), copy.deepcopy(candidate)
    allowed = dict(OUTPUT_SETTINGS) if variant == 'output' else {('qsim', 'numberOfThreads'): '10'} if variant == 'qsim10' else {}
    for root in (a, b):
        P.setparam(root, 'controller', 'outputDirectory', 'OUTPUT')
    for (module, name), expected in allowed.items():
        p = b.find(f"module[@name='{module}']/param[@name='{name}']")
        if p is None or p.get('value') != expected:
            raise ValueError('Candidate setting missing: ' + name)
        old = a.find(f"module[@name='{module}']/param[@name='{name}']")
        if old is None:
            raise ValueError('Baseline setting missing: ' + name)
        p.set('value', old.get('value'))
    if canonical(a) != canonical(b):
        raise ValueError('Configuration differs outside whitelist')


def verify_hashes(m):
    for item in m['inputs']:
        if D.sha(Path(item['path'])) != item['sha256']:
            raise ValueError('Input or executable changed: ' + item['path'])


def prepare(source, out):
    preparation_start = time.monotonic()
    source, out = source.resolve(), out.resolve()
    with (source / 'executor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = read(source / 'budget.json')
        if budget['active']:
            raise ValueError('Shared ledger has an active attempt')
        out.mkdir(parents=True, exist_ok=False)
        shutil.copy2(source / 'runner.jar', out / 'runner.jar')
        provenance = out/'preexisting-work'; provenance.mkdir()
        (provenance/'status.txt').write_text(D.command(['git','status','--short']))
        (provenance/'tracked.diff').write_text(D.command(['git','diff','--binary']))
        (provenance/'untracked.txt').write_text(D.command(['git','ls-files','--others','--exclude-standard']))
        if (ROOT/'outputs/performance-provenance').exists():
            shutil.copytree(ROOT/'outputs/performance-provenance', provenance/'before-branch')
        code = out / 'code'; code.mkdir()
        paths = [Path(__file__), Path(__file__).with_name('profile_analysis.py'), Path(__file__).with_name('VerifyConfig.java'), ROOT/'experiments/acceleration/pilot.py', ROOT/'experiments/acceleration/event_metrics.py', ROOT/'scripts/run_baseline_diagnostic.py', ROOT/'scripts/analyze_baseline_diagnostic.py']
        for p in paths:
            shutil.copy2(p, code / p.name)
        config = ET.parse(source / 'cold-attempt-1/config.xml')
        inputs = {out/'runner.jar', source/'cold-attempt-1/config.xml'}
        for p in config.findall('.//param'):
            v = p.get('value', '')
            if v.startswith('/') and Path(v).is_file():
                inputs.add(Path(v))
        inputs.update(paths)
        inputs.update(code.iterdir())
        order = ['full-baseline', 'full-candidate']; random.Random(4711).shuffle(order)
        m = {'created_utc': D.now(), 'source': str(source), 'ledger': str(source/'budget.json'), 'lock': str(source/'executor.lock'),
             'branch': D.command(['git', 'branch', '--show-current']).strip(), 'base_commit': D.command(['git', 'rev-parse', 'HEAD']).strip(),
             'initial_budget': budget, 'short_limit_seconds': 1200, 'full_limit_seconds': 4800, 'full_order': order,
             'inputs': [{'path': str(p), 'sha256': D.sha(p)} for p in sorted(inputs)], 'attempts': [], 'status': 'prepared',
             'rtol': RTOL, 'atol': ATOL, 'speed_gate': .05, 'tie_fraction': .02,
             'java_home': read(ROOT/'.tools/environment.json')['java_home'],
             'machine': D.command(['sysctl', 'hw.model', 'hw.physicalcpu', 'hw.logicalcpu', 'hw.memsize', 'hw.perflevel0.physicalcpu', 'hw.perflevel1.physicalcpu']).strip()}
        D.save(out/'manifest.json', m)
        D.save(out/'budget-start.json', budget)
        for name, variant in SHORTS:
            root = config_tree(source, out/('short-'+name), variant, 1)
            ET.indent(root)
            write_config(root, out/(name+'-planned.xml'))
        # Parse all planned variants with the real MATSim parser before launching any scenario.
        java = Path(m['java_home'])/'bin/java'
        proc = subprocess.run([str(java),'--class-path',str(out/'runner.jar'),str(code/'VerifyConfig.java'),
                               *[str(out/(name+'-planned.xml')) for name,_ in SHORTS]], capture_output=True,text=True)
        (out/'config-preflight.log').write_text(proc.stdout+proc.stderr)
        m['config_preflight_exit_code'] = proc.returncode
        m['preparation_seconds'] = time.monotonic()-preparation_start
        if proc.returncode:
            m['status']='configuration_preflight_failed'
        D.save(out/'manifest.json',m)
        if proc.returncode:
            raise RuntimeError('MATSim config preflight failed; no simulation launched')
        print(out, flush=True)
    return out


def reconcile_stale(out, m, ledger):
    active = ledger.get('active')
    if not active:
        return
    try:
        os.kill(active['pid'], 0)
    except ProcessLookupError:
        pass
    else:
        raise RuntimeError('Recorded PID still exists; inspect it before reconciliation')
    # Unknown time after last checkpoint is conservatively charged, never refunded.
    last = datetime.datetime.fromisoformat(ledger.get('updated_utc', active['started_utc']))
    delta = max(0, (datetime.datetime.now(datetime.timezone.utc)-last).total_seconds())
    ledger['used_seconds'] += delta
    ledger.update(active=None, updated_utc=D.now(), reconciliation={'unknown_seconds_charged': delta, 'previous_active': active})
    D.save(Path(m['ledger']), ledger)
    for a in m['attempts']:
        if a['status'] == 'running':
            a.update(status='interrupted', reason='stale_executor_conservative_reconciliation')
    m['status'] = 'interrupted'; D.save(out/'manifest.json', m)
    raise RuntimeError('Interrupted run accounted conservatively; inspect before any further campaign. No automatic retry.')


def execute_one(out, m, ledger, name, variant, iterations, phase):
    if any(a['name'] == name for a in m['attempts']):
        raise ValueError('Attempt already exists; never overwrite or retry automatically')
    phase_used = sum(a.get('elapsed_seconds', 0) for a in m['attempts'] if a['phase'] == phase)
    limit = min(ledger['limit_seconds']-ledger['used_seconds'], m[phase+'_limit_seconds']-phase_used)
    if limit <= 0:
        raise RuntimeError('Budget exhausted')
    initial = D.system_sample()
    if initial['disk_free_bytes'] < 30*D.GIB or initial['pressure_level'] == 4:
        raise RuntimeError('Resource preflight failed')
    verify_hashes(m)
    dest = out/name; dest.mkdir(exist_ok=False)
    root = config_tree(Path(m['source']), dest, variant, iterations)
    write_config(root, dest/'config.xml')
    java = Path(m['java_home'])/'bin/java'
    cmd = ['/usr/bin/time', '-l', str(java), '-Duser.language=en', '-Duser.country=US', '-Xmx16g', '-Xlog:gc*:file='+str(dest/'gc.log')+':time,uptime,level,tags']
    if name == 'short-profile':
        cmd += ['-XX:StartFlightRecording=filename='+str(dest/'profile.jfr')+',settings=profile,dumponexit=true']
    cmd += ['-jar', str(out/'runner.jar'), str(dest/'config.xml')]
    a = {'name': name, 'variant': variant, 'phase': phase, 'iterations': iterations, 'command': cmd, 'started_utc': D.now(), 'status': 'running', 'config_sha256': D.sha(dest/'config.xml'), 'profile_overhead': name=='short-profile'}
    m['attempts'].append(a); D.save(out/'manifest.json', m)
    start = time.monotonic(); used_before = ledger['used_seconds']; proc = None; reason = None; peak = 0; history = []; critical = None
    try:
        with (dest/'run.log').open('w') as log, (dest/'resources.csv').open('w') as resources:
            writer = csv.DictWriter(resources, fieldnames=['utc', 'elapsed_seconds', 'rss_bytes', 'disk_free_bytes', 'pressure_level', 'swap_used_bytes']); writer.writeheader()
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            ledger.update(active={'pid': proc.pid, 'directory': str(dest), 'started_utc': a['started_utc']}, updated_utc=D.now())
            D.save(Path(m['ledger']), ledger)
            system = initial; next_system = 0
            while proc.poll() is None:
                elapsed = time.monotonic()-start
                ledger.update(used_seconds=used_before+elapsed, updated_utc=D.now()); D.save(Path(m['ledger']), ledger)
                rss = D.memory_sample(proc.pid); peak = max(peak, rss or 0)
                if elapsed >= next_system:
                    system = D.system_sample(); history.append((elapsed, system['swap_used_bytes']))
                    reason, critical = D.resource_reason(system, history, critical, elapsed); next_system = elapsed+60
                writer.writerow(dict(utc=D.now(), elapsed_seconds=elapsed, rss_bytes=rss, **system)); resources.flush()
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
            D.stop_group(proc, max(0, min(30, limit-(time.monotonic()-start))))
        raise
    finally:
        elapsed = time.monotonic()-start
        ledger.update(used_seconds=used_before+elapsed, updated_utc=D.now(), active=None)
        D.save(Path(m['ledger']), ledger)
        a.update(elapsed_seconds=elapsed, ended_utc=D.now(), peak_rss_bytes=peak, exit_code=proc.returncode if proc else None, reason=reason, status='interrupted')
        D.save(out/'manifest.json', m)
    log = (dest/'run.log').read_text(errors='replace')
    complete = (proc.returncode == 0 and not reason and 'shutdown completed' in log.lower()
                and all(f'ITERATION {i} ENDS' in log for i in range(iterations))
                and (dest/'simulation/BUILT.output_config.xml').exists()
                and all(list((dest/f'simulation/ITERS/it.{i}').glob('*.events.xml*')) for i in range(iterations)))
    a['status'] = 'complete' if complete else 'interrupted' if reason else 'failed'; D.save(out/'manifest.json', m)
    print(name, a['status'], round(elapsed, 2), flush=True)
    if not complete:
        raise RuntimeError('Simulation did not complete; no retry: '+name)


def close(x, y):
    return isinstance(x, (int, float)) and isinstance(y, (int, float)) and math.isfinite(x) and math.isfinite(y) and math.isclose(x, y, rel_tol=RTOL, abs_tol=ATOL)


def compare_rows(base, cand):
    diffs = []
    if len(base) != len(cand) or not base:
        return [{'field': 'iterations', 'baseline': len(base), 'candidate': len(cand)}]
    for i, (a, b) in enumerate(zip(base, cand)):
        for key in sorted(set(a)|set(b)):
            x, y = a.get(key), b.get(key)
            if key.startswith('count_') or key in ('iteration', 'revenue_cents'):
                ok = x is not None and y is not None and x == y
            else:
                ok = close(x, y)
            if not ok:
                diffs.append({'iteration': i, 'field': key, 'baseline': x, 'candidate': y, 'delta': y-x if isinstance(x,(int,float)) and isinstance(y,(int,float)) else None})
    return diffs


def population_ids(path):
    people = set()
    with P.stream(path) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, e in it:
            if ev == 'end' and e.tag == 'person':
                people.add(e.get('id').encode()); root.remove(e)
    return people


def analyze_attempt(out, a, people, entries):
    dest = out/a['name']; sim = dest/'simulation'
    scores = P.table(sim/'BUILT.scorestats.csv'); modes = P.table(sim/'BUILT.modestats.csv'); audits = P.table(sim/'pricing-audit.csv')
    if not len(scores) == len(modes) == len(audits) == a['iterations']:
        raise ValueError('Missing metric rows')
    rows = []
    for i in range(a['iterations']):
        cache = dest/f'event-metrics-{i}.json'
        path = next((sim/f'ITERS/it.{i}').glob('*.events.xml*'))
        identity = {'path': str(path), 'bytes': path.stat().st_size, 'mtime_ns': path.stat().st_mtime_ns}
        if cache.exists():
            event = read(cache)
            if event['source'] != identity:
                raise ValueError('Event source changed')
        else:
            start = time.monotonic()
            event = dict(source=identity, **EM.measure(path, people, entries))
            event['analysis_seconds'] = time.monotonic()-start
            D.save(cache, event)
        if event['errors'] or not event['xml_closed']:
            raise ValueError('Event conservation check failed')
        score, mode, audit = scores[i], modes[i], audits[i]
        if not {'car','pt','taxi','FHV','bike','walk','ride','cb'}.issubset(mode):
            raise ValueError('Required mode shares missing')
        if any(int(x['iteration']) != i for x in (score, mode, audit)):
            raise ValueError('Iteration mismatch')
        if abs(float(audit['sample_revenue_usd'])-event['net_congestion_revenue']) >= .011:
            raise ValueError('Revenue audit mismatch')
        hist = P.table(sim/f'ITERS/it.{i}/BUILT.{i}.legHistogram.txt')
        if sum(float(h['stuck_all']) for h in hist) != event['unfinished_all']:
            raise ValueError('Unfinished histogram mismatch')
        for kind, prefix in [('departures','departures_'), ('completed','arrivals_')]:
            for mode_name, n in event[kind].items():
                if sum(float(h[prefix+mode_name]) for h in hist) != n:
                    raise ValueError('Leg histogram mismatch')
        ncar = event['completed'].get('car', 0)
        carmean = event['mean_completed_car_leg_seconds']
        if carmean is None:
            raise ValueError('Missing completed car leg duration')
        row = {'iteration': i, 'score': float(score['avg_executed']), 'count_unfinished': event['unfinished_all'],
               'count_car_entries': event['private_car_entry_crossings'], 'count_completed_car': ncar,
               'completed_car_total_seconds': carmean*ncar, 'censored_wait_seconds': event['censored_wait_person_hours']*3600,
               'count_not_boarded': event['waiting_at_cutoff'], 'revenue_cents': round(float(audit['sample_revenue_usd'])*100)}
        row.update({'mode_'+k: float(v) for k,v in mode.items() if k != 'iteration'})
        rows.append(row)
    watch = P.table(sim/'BUILT.stopwatch.csv')
    phases = {}
    for k in ['replanning','dump all plans','beforeMobsimListeners','prepareForMobsim','mobsim','afterMobsimListeners','scoring','iterationEndsListeners','iteration_duration']:
        vals = [r.get(k) for r in watch if r.get(k)]
        phases[k] = sum(sum(float(v)*s for v,s in zip(t.split(':'), [3600,60,1])) for t in vals) if vals else None
    log = (dest/'run.log').read_text(errors='replace')
    cpu = re.search(r'([\d.]+) real\s+([\d.]+) user\s+([\d.]+) sys', log)
    gc = (dest/'gc.log').read_text()
    pauses = [float(x) for x in re.findall(r'Pause[^\n]*? ([\d.]+)ms', gc)]
    starts, _, _ = P.log_times(log)
    timing = {'wall_seconds': a['elapsed_seconds'], 'phases_seconds': phases,
              'startup_seconds': starts[0]-datetime.datetime.fromisoformat(a['started_utc']).timestamp() if 0 in starts else None,
              'cpu_user_seconds': float(cpu[2]) if cpu else None, 'cpu_system_seconds': float(cpu[3]) if cpu else None,
              'gc_pause_seconds': sum(pauses)/1000, 'gc_pause_count': len(pauses), 'peak_rss_gib': a['peak_rss_bytes']/D.GIB,
              'output_bytes': sum(p.stat().st_size for p in sim.rglob('*') if p.is_file()), 'profile_overhead': a['profile_overhead']}
    if cpu:
        timing['average_cpu_cores'] = (float(cpu[2])+float(cpu[3]))/a['elapsed_seconds']
    D.save(dest/'metrics.json', rows); D.save(dest/'timing.json', timing)
    return rows, timing


def choose_candidate(results, timings, config_checks):
    base = timings['short-baseline']['wall_seconds']; eligible = []
    for variant in ('qsim10', 'output'):
        name = 'short-'+variant
        if name in results and config_checks.get(name) and not compare_rows(results['short-baseline'], results[name]) and timings[name]['wall_seconds'] <= .95*base:
            eligible.append(variant)
    if len(eligible) == 2:
        fast = min(eligible, key=lambda v: timings['short-'+v]['wall_seconds'])
        slow = max(eligible, key=lambda v: timings['short-'+v]['wall_seconds'])
        if (timings['short-'+slow]['wall_seconds']-timings['short-'+fast]['wall_seconds'])/timings['short-'+fast]['wall_seconds'] < .02:
            return 'output'
        return fast
    return eligible[0] if eligible else None


def analyze(out):
    analysis_start = time.monotonic()
    m = read(out/'manifest.json'); ledger = read(Path(m['ledger']))
    if ledger['active']:
        raise RuntimeError('Do not analyze while shared simulation is active')
    verify_hashes(m)
    people = population_ids(Path(m['source'])/'inputs/cold.xml.gz')
    entries = {r['id'].encode() for r in csv.DictReader((ROOT/'scenarios/nyc-2025/links.csv').open()) if r['entry']=='1'}
    results, timings, checks, differences = {}, {}, {}, {}
    for a in m['attempts']:
        if a['status'] != 'complete':
            continue
        results[a['name']], timings[a['name']] = analyze_attempt(out, a, people, entries)
    for a in m['attempts']:
        name = a['name']; baseline = 'short-baseline' if a['phase']=='short' else 'full-baseline'
        if name not in results or baseline not in results:
            continue
        check_configs(ET.parse(out/baseline/'simulation/BUILT.output_config.xml').getroot(), ET.parse(out/name/'simulation/BUILT.output_config.xml').getroot(), a['variant'])
        checks[name] = True
        differences[name] = compare_rows(results[baseline], results[name])
    candidate = choose_candidate(results, timings, checks) if 'short-baseline' in results else None
    recommended = None
    if 'full-candidate' in results and 'full-baseline' in results and checks.get('full-candidate') and not differences['full-candidate'] and timings['full-candidate']['wall_seconds'] <= .95*timings['full-baseline']['wall_seconds']:
        recommended = m['selected_candidate']
    summary = {'candidate': candidate, 'recommended': recommended, 'timings': timings, 'differences': differences, 'config_checks': checks,
               'status': m['status'], 'budget': ledger, 'limitations': 'single scenario/seed; descriptive wall time; iteration-0 screening is not convergence evidence; nested stopwatch phases must not be added'}
    summary['attempts'] = [{'name':a['name'],'status':a['status'],'reason':a.get('reason'),'elapsed_seconds':a.get('elapsed_seconds')} for a in m['attempts']]
    D.save(out/'analysis.json', summary)
    with (out/'differences.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=['attempt','iteration','field','baseline','candidate','delta']); w.writeheader()
        for name, values in differences.items():
            for v in values:
                w.writerow(dict(attempt=name, **v))
    with (out/'timings.csv').open('w') as f:
        w = csv.writer(f); w.writerow(['attempt','wall_seconds','startup_seconds','cpu_user_seconds','cpu_system_seconds','gc_pause_seconds','peak_rss_gib','output_bytes','mobsim_seconds','replanning_seconds'])
        for name,t in timings.items():
            w.writerow([name]+[t[k] for k in ['wall_seconds','startup_seconds','cpu_user_seconds','cpu_system_seconds','gc_pause_seconds','peak_rss_gib','output_bytes']]+[t['phases_seconds'][k] for k in ['mobsim','replanning']])
    profile = out/'short-profile/profile.jfr'
    if profile.exists() and not (out/'short-profile/jfr-summary.txt').exists():
        jfr = Path(m['java_home'])/'bin/jfr'
        for args, filename in [(['summary'], 'jfr-summary.txt'), (['view','hot-methods'], 'jfr-hot-methods.txt'), (['view','thread-cpu-load'], 'jfr-thread-cpu-load.txt'), (['view','gc-pauses'], 'jfr-gc-pauses.txt')]:
            proc = subprocess.run([str(jfr),*args,str(profile)], capture_output=True, text=True)
            (profile.parent/filename).write_text(proc.stdout+proc.stderr)
    attribution = profile.with_name('sample-attribution.json')
    if profile.exists() and not attribution.exists():
        from profile_analysis import analyze as attribute_profile
        attribute_profile(Path(m['java_home'])/'bin/jfr', profile)
    if attribution.exists():
        summary['profile_attribution'] = read(attribution)
    summary['this_analysis_seconds'] = time.monotonic()-analysis_start
    summary['analysis_cache_policy'] = 'Reuse metrics only when event path, size, and mtime match; fresh scan seconds are recorded when available.'
    summary['preparation_seconds'] = m.get('preparation_seconds')
    D.save(out/'analysis.json',summary)
    report(out, m, summary)
    return summary


def report(out, m, s):
    lines = ['# MATSim 性能先导实验', '', '单一情景、种子 4711、全人口；严格结果一致。计时为单次描述性观察，不证明普遍加速或收敛。', '',
             f"状态：{m['status']}。推荐配置：{s['recommended'] or '暂无'}。短跑候选：{s['candidate'] or '无'}。", '',
             f"共享预算账本占用（可能含其他实验预留）：{s['budget']['used_seconds']/60:.2f} / {s['budget']['limit_seconds']/60:.2f} 分钟；本批次仿真 {sum(a.get('elapsed_seconds',0) for a in m['attempts'])/60:.2f} 分钟。准备和离线分析另计。", '',
             '| 运行 | 总秒数 | CPU 用户秒 | GC 暂停秒 | 峰值 RSS GiB | 输出 GiB | 差异项数 |', '|---|---:|---:|---:|---:|---:|---:|']
    for name,t in s['timings'].items():
        lines.append(f"|{name}|{t['wall_seconds']:.2f}|{t['cpu_user_seconds']}|{t['gc_pause_seconds']:.3f}|{t['peak_rss_gib']:.2f}|{t['output_bytes']/D.GIB:.2f}|{len(s['differences'].get(name,[]))}|")
    reserved=sum(v.get('seconds',0) for v in s['budget'].get('collective_reservations',{}).values() if v.get('status')=='reserved')
    if reserved:
        lines += ['', f'账本另列其他实验预留 {reserved/60:.2f} 分钟；该预留不是本分支仿真消耗。本报告读取当前账本并保留外部预留。']
    lines += ['', '本地首次准备与完整事件扫描未独立计时；analysis.json 的 this_analysis_seconds 是本次分析调用耗时（可使用缓存），不能当作首次离线分析成本。后续运行已补准备与逐事件文件扫描计时。' if m.get('preparation_seconds') is None else f"准备耗时 {m['preparation_seconds']:.2f} 秒另计；逐事件扫描耗时见缓存，重分析调用耗时见 analysis.json。", '', '## 未完成运行与结论', '']
    for a in m['attempts']:
        if a['status'] != 'complete':
            lines.append(f"- {a['name']}：{a['status']}，{a.get('elapsed_seconds',0):.2f} 秒；原因：{a.get('reason') or a.get('reviewed_failure') or '见日志'}。不参加速度排名或质量比较。")
    if m['status']=='insufficient_budget':
        lines.append('- 短跑阶段预算不足，输出候选被截断，没有完成四组筛选，也没有执行完整 12 轮配对。结论为证据不足，不能把未完成运行当作更快。')
    if 'short-qsim10' in s['timings'] and 'short-baseline' in s['timings']:
        base=s['timings']['short-baseline']; candidate=s['timings']['short-qsim10']
        lines.append(f"- 10 线程总耗时相对基准变化 {(candidate['wall_seconds']/base['wall_seconds']-1)*100:+.2f}%；所列逐轮指标差异 {len(s['differences'].get('short-qsim10',[]))} 项。单次顺序运行不能把耗时差归因于线程配置。")
        lines.append(f"- 基准启动 {base['startup_seconds']:.1f} 秒、mobsim {base['phases_seconds']['mobsim']:.1f} 秒；10 线程启动 {candidate['startup_seconds']:.1f} 秒、mobsim {candidate['phases_seconds']['mobsim']:.1f} 秒。本次差异主要在启动阶段。")
    if 'profile_attribution' in s:
        p=s['profile_attribution']; total=p['execution_samples']; custom=p['custom_inclusive_samples'].get('org.c2smart.matsimnyc.Pricing2025$1$1.getLinkTravelDisutility',0)
        lines += ['', '## 剖析发现', '', f"- JFR 执行采样 {total} 条；收费路由成本函数出现在 {custom} 条采样栈中（{100*custom/total:.2f}%）。道路/公交路由、交通队列和事件 XML 写出均有热点。",
                  '- 这些是全程采样且调用栈类别可重叠，不是独占 CPU 时间或可节省的墙钟比例。详见 short-profile/sample-attribution.json 和 JFR 派生视图。',
                  '- 下一次工程检查可检验按 link 预计算静态收费区/隧道成员关系是否减少路由查询成本；必须保持随时间变化的费率、随机成本及实际记账逻辑，并重新完成严格核验。本批不新增该候选。']
    lines += ['', 'profile 行开启 JFR，具有额外测量开销，不参加候选速度排名。QSim 和输出候选分别修改一个预定配置组，没有组合调参。完整结束的运行保留完整原始事件；预算截断组只保留已有产物，不参加核验。', '',
              '若短跑无合格候选，按计划停止。若未完成完整配对，不能推荐替换配置。即使通过全部指标，结论也仅为已观测指标一致，不保证事件顺序、个人轨迹或真实世界效度。', '',
              '收费按美分、计数精确比较；其他数值 rtol=1e-9、atol=1e-8。详见 differences.csv、analysis.json、各运行 metrics.json。阶段时间有嵌套，不可直接相加；mobsim 含事件处理等成本，不等于纯道路运算。', '',
              '## 后续方法问题', '', '能否根据道路与公交容量压力、需求及路线变化，判断何时可以复用近似结果、何时必须执行完整仿真，从而降低达到政策指标质量要求的总成本？', '',
              '- 已有特征：每轮方式比例、平均分、未完成、收费区进入、候车、未上车、道路/公交事件及计算成本。',
              '- 待构建：路段和班次负荷、容量饱和程度、群体服务差异、路线变化、近似误差标签；在线特征只允许使用决策前可得信息，并计入采集成本。',
              '- PSim 检查：锁定版本与接口；公交容量与排队/未上车反馈；时变路网；汽车/出租车/FHV；有状态日收费与退款；历史成本及评分；事件语义和随机性；完整仿真刷新后的状态交接。当前尚未验证兼容。',
              '- 下一阶段先比较完整仿真与固定间隔近似，再比较简单刷新规则和学习型控制器。训练/核验按政策和种子分离，计入源生成、特征计算、近似、控制器与完整核验总成本。',
              '- 更长参考运行及多政策、多种子需另定预算。10–20 倍仅为研究愿景，本次不训练模型、不调用 LLM、不接入近似仿真。', '']
    (out/'report_zh.md').write_text('\n'.join(lines))


def run(out):
    m = read(out/'manifest.json')
    with Path(m['lock']).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = read(Path(m['ledger'])); reconcile_stale(out,m,ledger)
        if m['status'] in ('no_candidate','complete','insufficient_budget'):
            print('Campaign terminal:', m['status']); return
        if any(a['status'] != 'complete' and not a.get('reviewed_failure') for a in m['attempts']):
            raise RuntimeError('Incomplete attempt requires inspection; no automatic retry')
        m['status'] = 'screening'; D.save(out/'manifest.json',m)
        for suffix,variant in SHORTS:
            name = 'short-'+suffix
            if any(a['name']==name for a in m['attempts']):
                continue
            used = sum(a['elapsed_seconds'] for a in m['attempts'] if a['phase']=='short')
            if used >= m['short_limit_seconds'] or ledger['limit_seconds']-ledger['used_seconds'] <= 0:
                m['status']='insufficient_budget'; D.save(out/'manifest.json',m); analyze(out); return
            execute_one(out,m,ledger,name,variant,1,'short')
        s = analyze(out); selected = s['candidate']
        if selected is None:
            m['status']='no_candidate'; D.save(out/'manifest.json',m); analyze(out); return
        m['selected_candidate']=selected
        if 'full_estimate_seconds' not in m:
            historical = read(Path(m['source'])/'summary.json')['arms']['cold']['elapsed_seconds']
            ratio = s['timings']['short-'+selected]['wall_seconds']/s['timings']['short-baseline']['wall_seconds']
            m['full_estimate_seconds'] = historical*(1+ratio)*1.15
        remaining = ledger['limit_seconds']-ledger['used_seconds']
        completed_full = [a for a in m['attempts'] if a['phase']=='full']
        if not completed_full and m['full_estimate_seconds'] > min(remaining,m['full_limit_seconds']):
            m['status']='insufficient_budget'; D.save(out/'manifest.json',m); analyze(out); return
        m['status']='full_validation'; D.save(out/'manifest.json',m)
        for name in m['full_order']:
            if any(a['name']==name for a in m['attempts']):
                continue
            execute_one(out,m,ledger,name,'baseline' if name=='full-baseline' else selected,12,'full')
        m['status']='complete'; D.save(out/'manifest.json',m); analyze(out)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['prepare','run','analyze'])
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE); parser.add_argument('--run-dir', type=Path)
    a = parser.parse_args()
    if a.action=='prepare':
        prepare(a.source, a.run_dir or ROOT/'outputs'/('performance-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')))
    else:
        if not a.run_dir:
            parser.error('--run-dir required')
        out=a.run_dir.resolve()
        if a.action=='run':
            try:
                run(out)
            except BaseException:
                m=read(out/'manifest.json')
                if not read(Path(m['ledger']))['active']:
                    m['status']='insufficient_budget' if any(a.get('reason')=='budget_exhausted' for a in m['attempts']) else 'interrupted_or_failed'; D.save(out/'manifest.json',m)
                    try:
                        with Path(m['lock']).open('a') as lock:
                            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                            analyze(out)
                    except Exception as error: D.save(out/'analysis-error.json', {'error': str(error)})
                raise
        else:
            m=read(out/'manifest.json')
            with Path(m['lock']).open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); analyze(out)

if __name__=='__main__':
    main()

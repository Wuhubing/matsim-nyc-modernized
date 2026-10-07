#!/usr/bin/env python3
"""Read-only integrity audit of a run made with --research. Checks the recording, not simulation quality.

Expected output files are derived from the config MATSim actually used (simulation/*output_config.xml), with
MATSim 2026.0's rules: events at it > 0 and it % N == 0, it <= writeEventsUntilIteration, and the last iteration;
plans at it > 0 and it % N == 0 and it <= writePlansUntilIteration (the final state is output_plans);
counts comparisons by CountsControllerListener's averaging schedule, only if the counts output format has txt.
Writes RUN/research-audit.json; exit code 0 only if every check passes."""
import argparse, csv, gzip, json, math
import xml.etree.ElementTree as ET
from pathlib import Path


def rows(path):
    with gzip.open(path, 'rt') as f: yield from csv.DictReader(f)


def params(config):
    """{module: {param: value}} of top-level module params."""
    root = ET.parse(config).getroot()
    return {m.get('name'): {p.get('name'): p.get('value') for p in m.findall('param')} for m in root.findall('module')}


def counts_iterations(first, last, interval, averaging):
    """Iterations with a counts comparison, replicating CountsControllerListener (MATSim 2026.0)."""
    if interval <= 0: return set()
    used, out = 0, set()
    for it in range(first, last + 1):
        mod, effective, avg = it % interval, it - first, min(averaging, interval)
        use = (averaging <= 1 or effective >= avg) if mod == 0 else (mod > interval - averaging and effective + (interval - mod) >= avg)
        if use: used += 1
        if it % interval == 0 and used >= averaging: out.add(it); used = 0
    return out


def scheduled(first, last, interval, until, include_last):
    if interval <= 0: return set()
    out = {it for it in range(first, last + 1) if (it > 0 and it % interval == 0) or it <= until}
    if include_last: out.add(last)
    return out


def present(directory, pattern):
    return bool(list(directory.glob(pattern)))


def audit(run):
    run = Path(run); meta = json.loads((run/'run.json').read_text()); out = run/'simulation'; data = out/'research'
    failures = []; details = []
    if meta.get('exit_code') != 0 or meta.get('state') != 'completed': failures.append('run not successfully completed')
    config = next(out.glob('*output_config.xml'), None)
    if config is None: return finish(run, meta, ['missing output_config.xml'], [], {})
    cfg = params(config); ctl = cfg['controller']; cnt = cfg.get('counts', {})
    first, last = int(ctl['firstIteration']), int(ctl['lastIteration'])
    expect = {
        'events': scheduled(first, last, int(ctl['writeEventsInterval']), int(ctl.get('writeEventsUntilIteration', 0)), True),
        'plans': scheduled(first, last, int(ctl['writePlansInterval']), int(ctl.get('writePlansUntilIteration', 1)), False),
        'counts': counts_iterations(first, last, int(cnt.get('writeCountsInterval', 0)), int(cnt.get('averageCountsOverIterations', 1)))
                  if cnt.get('inputCountsFile') not in (None, 'null') and 'txt' in cnt.get('outputformat', '') + cnt.get('outputFormat', '') else set(),
    }
    if not present(out, '*output_plans.xml*'): failures.append('missing final output_plans snapshot')
    cohorts = list(rows(data/'cohorts.csv.gz'))
    population = meta.get('expected_persons') or len(cohorts)
    if len(cohorts) != population: failures.append(f'cohorts cover {len(cohorts)} of {population} persons')
    schema = json.loads((data/'schema.json').read_text())
    if 'not authoritative' not in schema.get('polygon_status', ''): failures.append('schema.json does not label the cohort boundary as a reconstruction')
    overhead = {'plan_fingerprint_seconds': 0.0, 'research_output_seconds': 0.0}
    for i in range(first, last + 1):
        it_dir = out/f'ITERS/it.{i}'
        legacy = json.loads((out/f'iteration-metrics-{i}.json').read_text())
        diag = json.loads((data/f'diagnostics-{i}.json').read_text())
        for k in overhead: overhead[k] += diag.get(k, 0)
        if diag['errors']: failures.append(f'iteration {i}: research invariant errors {diag["errors"]}')
        if legacy.get('errors'): failures.append(f'iteration {i}: legacy invariant errors {legacy["errors"]}')
        groups = {r['group']: r for r in rows(data/f'groups-{i}.csv.gz')}; total = groups['all']
        for key, legacy_key in {'unfinished': 'unfinished_all', 'waiting_at_cutoff': 'waiting_at_cutoff',
                                'toll_revenue': 'net_congestion_revenue', 'private_car_entry_crossings': 'private_car_entry_crossings'}.items():
            if not math.isclose(float(total[key]), legacy[legacy_key], rel_tol=1e-9, abs_tol=1e-6): failures.append(f'iteration {i}: {key} differs from IterationMetrics')
        if not math.isclose(float(total['censored_wait_seconds'])/3600, legacy['censored_wait_person_hours'], rel_tol=1e-9, abs_tol=1e-6):
            failures.append(f'iteration {i}: censored wait differs from IterationMetrics')
        for prefix in ['subpopulation:', 'charging:', 'joint:']:
            for key in list(total)[1:]:
                value = sum(float(r[key]) for g, r in groups.items() if g.startswith(prefix))
                if not math.isclose(value, float(total[key]), rel_tol=1e-9, abs_tol=1e-6): failures.append(f'iteration {i}: {prefix} {key} does not sum to all')
        modes = list(rows(data/f'group-modes-{i}.csv.gz'))
        for prefix in ['subpopulation:', 'charging:', 'joint:']:
            for key in ['departures', 'completed', 'stuck', 'completed_seconds']:
                part = sum(float(r[key]) for r in modes if r['group'].startswith(prefix)); whole = sum(float(r[key]) for r in modes if r['group'] == 'all')
                if not math.isclose(part, whole, rel_tol=1e-9, abs_tol=1e-6): failures.append(f'iteration {i}: group-modes {prefix} {key} does not sum to all')
        n = sum(1 for _ in rows(data/f'persons-{i}.csv.gz'))
        if n != population or n != int(float(total['persons'])): failures.append(f'iteration {i}: persons file covers {n} of {population}')
        bad_links = sum(1 for r in rows(data/f'link-hours-{i}.csv.gz')
                        if not 0 <= int(r['completed_traversals']) <= int(r['entries']) or float(r['total_traversal_seconds']) < 0)
        if bad_links: failures.append(f'iteration {i}: {bad_links} link-hour rows with completed > entries or negative time')
        found = {'events': present(it_dir, '*.events.xml*'), 'plans': present(it_dir, f'*.{i}.plans.xml*'), 'counts': present(it_dir, '*.countscompare.txt')}
        for kind, has in found.items():
            if (i in expect[kind]) != has: failures.append(f'iteration {i}: {kind} file {"missing" if i in expect[kind] else "unexpected"}')
        details.append({'iteration': i, 'persons': n, **found, **diag})
    return finish(run, meta, failures, details, {'expected': {k: sorted(v) for k, v in expect.items()}, 'recorder_seconds': overhead})


def finish(run, meta, failures, details, extra):
    def size(path): return sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) if path.exists() else 0
    storage = size(run); research = size(run/'simulation/research'); iterations = meta.get('iterations') or 1
    report = {'passed': not failures, 'failures': failures, **extra,
              'wall_seconds': meta.get('wall_seconds'), 'peak_rss_gib': meta.get('peak_rss_gib'),
              'bytes_on_disk': storage, 'research_bytes': research,
              'projected_100_iteration_gib_linear': storage/iterations*100/2**30,
              'storage_note': 'Rough linear extrapolation includes fixed artifacts. Filesystem free space is not the user quota.',
              'iterations': details}
    (run/'research-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'iterations'}, indent=2))
    return not failures


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('run', type=Path); a = p.parse_args()
    raise SystemExit(0 if audit(a.run) else 1)

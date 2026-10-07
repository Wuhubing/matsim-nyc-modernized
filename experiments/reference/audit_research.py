#!/usr/bin/env python3
"""Read-only integrity audit. Never confuses added instrumentation with simulation quality."""
import argparse, csv, gzip, json, math
from pathlib import Path


def rows(path):
    with gzip.open(path,'rt') as f: yield from csv.DictReader(f)


def audit(run):
    run=Path(run); meta=json.loads((run/'run.json').read_text()); out=run/'simulation'; data=out/'research'
    failures=[]; details=[]
    if meta.get('exit_code') != 0 or meta.get('state') != 'completed': failures.append('run not successfully completed')
    expected_persons=sum(1 for _ in rows(data/'cohorts.csv.gz'))
    for i in range(meta['iterations']):
        legacy=json.loads((out/f'iteration-metrics-{i}.json').read_text())
        diag=json.loads((data/f'diagnostics-{i}.json').read_text())
        if diag['errors']: failures.append(f'iteration {i}: research invariant errors {diag["errors"]}')
        if legacy.get('errors'): failures.append(f'iteration {i}: legacy invariant errors')
        groups={r['group']:r for r in rows(data/f'groups-{i}.csv.gz')}; total=groups['all']
        mappings={'unfinished':'unfinished_all','waiting_at_cutoff':'waiting_at_cutoff','toll_revenue':'net_congestion_revenue',
                  'private_car_entry_crossings':'private_car_entry_crossings'}
        for key,legacy_key in mappings.items():
            if not math.isclose(float(total[key]),legacy[legacy_key],rel_tol=1e-9,abs_tol=1e-6): failures.append(f'iteration {i}: {key} differs from legacy')
        if not math.isclose(float(total['censored_wait_seconds'])/3600,legacy['censored_wait_person_hours'],rel_tol=1e-9,abs_tol=1e-6): failures.append(f'iteration {i}: wait total differs')
        for prefix in ['subpopulation:','charging:','joint:']:
            for key in list(total)[1:]:
                value=sum(float(r[key]) for g,r in groups.items() if g.startswith(prefix))
                if not math.isclose(value,float(total[key]),rel_tol=1e-9,abs_tol=1e-6): failures.append(f'iteration {i}: {prefix} {key} conservation')
        n=sum(1 for _ in rows(data/f'persons-{i}.csv.gz'))
        if n != expected_persons or n != int(float(total['persons'])): failures.append(f'iteration {i}: person coverage')
        for r in rows(data/f'link-hours-{i}.csv.gz'):
            if not (0<=int(r['completed_traversals'])<=int(r['entries'])) or float(r['total_traversal_seconds'])<0:
                failures.append(f'iteration {i}: invalid link traversal counts');break
        if not list((out/f'ITERS/it.{i}').glob('*.countscompare.txt')): failures.append(f'iteration {i}: missing counts comparison')
        interval=meta.get('events_interval')
        if interval and (i % interval == 0):
            if not list((out/f'ITERS/it.{i}').glob('*.events.xml*')): failures.append(f'iteration {i}: missing scheduled events')
        details.append({'iteration':i,'persons':n,**diag})
    storage=sum(p.stat().st_size for p in run.rglob('*') if p.is_file())
    report={'passed':not failures,'failures':failures,'iterations':details,'bytes_on_disk':storage,
            'projected_100_iteration_gib_linear':storage/meta['iterations']*100/2**30,
            'storage_note':'Rough linear extrapolation includes fixed artifacts. Filesystem capacity is not user quota.'}
    (run/'research-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='iterations'},indent=2))
    return not failures

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
    raise SystemExit(0 if audit(a.run) else 1)

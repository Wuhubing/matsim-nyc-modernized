#!/usr/bin/env python3
"""Gate long jobs on successful historical checks, observer equivalence and baseline smoke audit."""
import argparse,json
from pathlib import Path
from run_reference import table

def check(root):
    runs={}
    for p in root.glob('*/run.json'):
        m=json.loads(p.read_text())
        role='baseline' if m.get('scenario')=='baseline' else ('rich' if m.get('research') else 'plain')
        if role in runs:raise ValueError(f'Multiple {role} runs in {root}; select a single validation batch')
        runs[role]=(p.parent,m)
    if set(runs)!={'baseline','rich','plain'}:raise ValueError('Need plain/rich actual2025 checks and baseline smoke results')
    for role,(p,m) in runs.items():
        if m.get('exit_code')!=0 or m.get('state')!='completed':raise ValueError(f'{role} incomplete or failed')
        if role!='plain' and not json.loads((p/'research-audit.json').read_text())['passed']:raise ValueError(f'{role} research audit failed')
        if role!='baseline' and not json.loads((p/'verification.json').read_text())['passed']:raise ValueError(f'{role} historical verification failed; inspect cross-platform differences before proceeding')
    plain,pm=runs['plain'];rich,rm=runs['rich']
    if pm.get('provenance') != rm.get('provenance'):
        raise ValueError('Validation runs have different source snapshots')
    for m in [pm,rm]:
        if not m.get('sha256'): raise ValueError('Validation input fingerprints are missing')
    if pm['sha256'][pm['plans']] != rm['sha256'][rm['plans']]:
        raise ValueError('Validation input populations differ')
    for key in ['seed','iterations','threads','heap','innovation_until','scenario']:
        if pm[key]!=rm[key]:raise ValueError(f'Pair mismatch: {key}')
    for i in range(pm['iterations']):
        a=json.loads((plain/f'simulation/iteration-metrics-{i}.json').read_text())
        b=json.loads((rich/f'simulation/iteration-metrics-{i}.json').read_text())
        if a!=b:raise ValueError(f'Instrumentation changes metrics at iteration {i}')
    if table(plain/'simulation/BUILT.scorestats.csv')!=table(rich/'simulation/BUILT.scorestats.csv'):raise ValueError('Instrumentation changes scores')
    if table(plain/'simulation/BUILT.modestats.csv')!=table(rich/'simulation/BUILT.modestats.csv'):raise ValueError('Instrumentation changes mode shares')
    with (rich/'summary.csv').open() as f:
        import csv
        durations=[float(row['iteration_s']) for row in csv.DictReader(f) if row.get('iteration_s')]
    projected_hours=(sum(durations)/len(durations)*100*1.3 + max(0,rm['wall_seconds']-sum(durations)))/3600 if durations else None
    report={'projected_100_iteration_hours_with_30pct_margin':projected_hours,'passed':True,'runs':{k:str(p) for k,(p,m) in runs.items()},
            'observed_wall_time_ratio_rich_over_plain':rm['wall_seconds']/pm['wall_seconds'],
            'warning':'Concurrent jobs and node differences confound timing. This ratio is screening only; benchmark paired sequential runs on comparable hardware.'}
    (root/'validation-passed.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    print(json.dumps(check(a.root),indent=2))

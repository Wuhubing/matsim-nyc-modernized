#!/usr/bin/env python3
"""Exploratory convergence, seed spread, timings and observed-count diagnostics; no automatic calibration claim."""
import argparse,csv,json,statistics
from pathlib import Path

METRICS=['score','car_share','pt_share','unfinished','car_entries','not_boarded','revenue_usd','mean_completed_car_leg_seconds','censored_wait_person_hours']

def counts(path):
    with open(path) as f: rows=list(csv.DictReader(f,delimiter='\t'))
    observed=sum(float(r['Count volumes']) for r in rows)
    simulated=sum(float(r['MATSIM volumes']) for r in rows)
    errors=[abs(float(r['MATSIM volumes'])-float(r['Count volumes'])) for r in rows]
    return {'cells':len(rows),'observed_total':observed,'simulated_total':simulated,
            'total_relative_bias':(simulated-observed)/observed if observed else None,
            'wape':sum(errors)/observed if observed else None,
            'note':'All supplied count stations, already MATSim-scaled. NOT automatically the paper East River screenline.'}

def analyze(paths,window,tolerance):
    report={'window':window,'exploratory_relative_tolerance':tolerance,
            'caution':'Three seeds are preliminary. Seed spread is not an acceptance margin. Adjacent-window stability is not proof of equilibrium. Evaluate the innovation phase separately. Independent replication and predefined per-metric quality margins are required.',
            'runs':[],'seed_spread':{}}
    finals={}
    for path in paths:
        meta=json.loads((path/'run.json').read_text())
        with open(path/'summary.csv') as f: rows=list(csv.DictReader(f))
        results={}; cutoff=meta.get('innovation_until')
        # Legacy fractional runs are intentionally not assigned an inferred exact disableAfter.
        for metric in METRICS:
            series=[(int(r['iteration']),float(r[metric])) for r in rows if r.get(metric) not in (None,'')]
            if len(series)<window:continue
            tail=[v for _,v in series[-window:]];mean=statistics.mean(tail)
            checks=[]
            for stop in range(2*window,len(series)+1):
                before=[v for _,v in series[stop-2*window:stop-window]];after=[v for _,v in series[stop-window:stop]]
                a,b=statistics.mean(before),statistics.mean(after);change=abs(b-a)/max(abs(a),abs(b),1e-12)
                checks.append({'end_iteration':series[stop-1][0],'relative_mean_change':change,'within_exploratory_tolerance':change<=tolerance,
                               'innovation_active_entire_window':None if cutoff is None else series[stop-1][0]<=cutoff})
            results[metric]={'tail_mean':mean,'tail_sd':statistics.stdev(tail) if len(tail)>1 else 0,'windows':checks}
            key=(meta.get('scenario','actual2025'),metric,meta['iterations'],str(meta.get('innovation_until')),meta.get('threads'),meta.get('research',False))
            finals.setdefault(key,[]).append({'seed':meta['seed'],'mean':mean})
        durations=[float(r['iteration_s']) for r in rows if r.get('iteration_s')]
        countfiles=sorted((path/'simulation/ITERS').glob('it.*/*.countscompare.txt'),key=lambda p:int(p.parent.name[3:]))
        result={'path':str(path),'scenario':meta.get('scenario','actual2025'),'seed':meta['seed'],'innovation_until':cutoff,
                'metrics':results,'mean_iteration_seconds':statistics.mean(durations) if durations else None,
                'estimated_100_iterations_hours':statistics.mean(durations)*100/3600 if durations else None,
                'counts':counts(countfiles[-1]) if countfiles else None,
                'calibration_eligible_scenario':meta.get('scenario')=='baseline'}
        report['runs'].append(result)
    for key, values in finals.items():
        means=[v['mean'] for v in values]
        report['seed_spread']['|'.join(map(str,key))]={'samples':values,'distinct_seeds':len(set(v['seed'] for v in values)),
            'min':min(means),'max':max(means),'sd':statistics.stdev(means) if len(means)>1 else None,
            'acceptance_margin':None,'note':'Check matching inputs, schedules and build fingerprints before pooling; no automatic pass/fail.'}
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--window',type=int,default=10)
    p.add_argument('--relative-tolerance',type=float,default=0.01);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.window<2 or a.relative_tolerance<0:p.error('window >=2 and tolerance >=0 required')
    a.out.write_text(json.dumps(analyze(a.runs,a.window,a.relative_tolerance),indent=2)+'\n');print(a.out)

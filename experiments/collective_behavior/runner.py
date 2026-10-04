#!/usr/bin/env python3
"""Run once; archive all observations and outcomes. No simulations on import."""
import argparse
import concurrent.futures as F
import csv
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import shutil
import statistics as S
import time

from environment import Config, Environment, SCENARIOS, costs, parameters
from observations import observe
from policies import Policy, BASELINES
from metrics import summarize, interval
from budget import save, read, reserve, settle, lock
from llm import Client, BudgetStop, MODEL

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_SHARED=ROOT/'outputs/acceleration-pilot-20261004-032117'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append(path, value):
    with (gzip.open(path,'at') if path.suffix=='.gz' else path.open('a')) as f:
        f.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')


def pairing_check():
    """Same travel-time observations; different optimal actions conditional on others.

    This establishes possible value of information, NOT ability to anticipate others.
    """
    rows=[]
    for capacity,background in ((.5,0),(1.,16)):
        row={'day':11,'actions':[0]*16+[1]*8,'costs':costs(16,24,capacity,background),
             'endogenous_flow':[16,8],'total_flow':[16+background,8],
             'truth':{'capacity':capacity,'background':background}}
        # Seven OTHER agents choose A on the next day, fixed in both worlds.
        cf=[costs(8,24,capacity,background)[0],costs(7,24,capacity,background)[1]]
        rows.append({'observation_time':observe([row],0,information='time'),
                     'observation_flow':observe([row],0,information='flow'),
                     'counterfactual_costs':cf,'best_route':min(range(2),key=lambda r:cf[r])})
    return {'worlds':rows,'time_observations_equal':rows[0]['observation_time']==rows[1]['observation_time'],
            'flow_observations_differ':rows[0]['observation_flow']!=rows[1]['observation_flow'],
            'action_relevant':rows[0]['best_route']!=rows[1]['best_route'],
            'scope':'Conditional intervention fixing others next-day choices; not a forecast of spontaneous flow.'}


def numeric_episode(config, method, information, seed, deadline):
    env=Environment(config).reset(seed)
    policies=[Policy(method,seed*1000+i) for i in range(config.population)]
    decisions=[]
    for day in range(config.days):
        if time.monotonic() >= deadline: raise BudgetStop('Simulation time cap')
        observations=[observe(env.history,i,config.population,information) for i in range(config.population)]
        choices=[p.decide(o) for p,o in zip(policies,observations)]
        row=env.step({i:c['route'] for i,c in enumerate(choices)})
        decisions.append({'observations':observations,'choices':choices})
        for p in policies: p.update(row)
    return {'config':asdict(config),'method':method,'information':information,'seed':seed,
            'metrics':summarize(env.history,config),'rows':env.history,'decisions':decisions}


def numerical(out,deadline):
    runs=[]; candidates={s:[] for s in SCENARIOS}
    for scenario in SCENARIOS:
        for strength in ((1,) if scenario=='none' else (1,2)):
            for information in ('time','flow'):
                for method in BASELINES:
                    for seed in range(30):
                        config=Config(scenario=scenario,strength=strength)
                        run=numeric_episode(config,method,information,seed,deadline)
                        append(out/'numerical.jsonl.gz',run)
                        runs.append({k:v for k,v in run.items() if k not in ('rows','decisions')})
                        if method=='smooth' and information=='flow' and seed<15:
                            # Predeclared stratified sampling: no outcome-based replay selection.
                            day=12+(seed%8); agent=seed%config.population
                            candidates[scenario].append({'config':asdict(config),'seed':seed,'agent':agent,
                                'history':run['rows'][:day-1],'next_row':run['rows'][day-1]})
    rng=random.Random(20261004)
    states=[]
    for scenario in SCENARIOS:
        rng.shuffle(candidates[scenario])
        states.extend(candidates[scenario][:15])
    for i,state in enumerate(states): state['id']=i
    save(out/'replay-states.json',states)
    save(out/'numerical-summary.json',runs)
    # Select by predeclared smooth/time excess over system lower bound; no LLM outcomes used.
    grouped={}
    for r in runs:
        if r['method']=='smooth' and r['information']=='time' and r['config']['scenario']!='none':
            key=(r['config']['scenario'],r['config']['strength'])
            grouped.setdefault(key,[]).append(r['metrics']['excess_cost'])
    ranked=sorted(grouped,key=lambda k:(S.mean(grouped[k]),k))
    selected=[{'scenario':ranked[-1][0],'strength':ranked[-1][1],'selection':'high_baseline_excess'},
              {'scenario':ranked[0][0],'strength':ranked[0][1],'selection':'low_baseline_excess'},
              {'scenario':'none','strength':1,'selection':'null_control'}]
    save(out/'selected-conditions.json',selected)
    return runs,states,selected


def replay_score(state,choice,information):
    agent=state['agent']; nxt=state['next_row']; capacity=nxt['truth']['capacity']; background=nxt['truth']['background']
    other_a=nxt['endogenous_flow'][0]-(nxt['actions'][agent]==0)
    cf=[costs(other_a+1,24,capacity,background)[0],costs(other_a,24,capacity,background)[1]]
    last=state['history'][-1]
    # Current cause is directly arithmetically identifiable with contemporaneous A cost + total flows.
    identifiable=information=='flow' and last['actions'][agent]==0 and last['total_flow'][0]>0
    result={'cost':cf[choice['route']],'counterfactual_regret':cf[choice['route']]-min(cf),
            'counterfactual_costs':cf,'truth_last_cause':last['truth']['cause'],
            'contemporaneously_identifiable':identifiable,'valid':choice['valid']}
    if choice['valid']:
        result.update(prediction_mae=S.mean(abs(a-b) for a,b in zip(choice['predicted_costs'],cf)),
                      cause_correct=choice['cause']==last['truth']['cause'],abstained=choice['cause']=='insufficient')
    return result


def replay(out,states,client,pool):
    # Interleave methods, information and repetitions so a cap does not omit an entire arm.
    for repeat in range(3):
        for state in states:
            tasks=[]
            for information in ('time','flow'):
                obs=observe(state['history'],state['agent'],information=information)
                for method in BASELINES:
                    choice=Policy(method,50000+state['id']*10+repeat).decide(obs)
                    append(out/'replay-baselines.jsonl',{'state':state['id'],'repeat':repeat,'information':information,
                        'method':method,'observation':obs,'choice':choice,'score':replay_score(state,choice,information)})
                for mode in ('direct','diagnose'):
                    call_id=f'replay-{state["id"]:02d}-{repeat}-{information}-{mode}'
                    tasks.append((information,mode,obs,pool.submit(client.decide,obs,mode,call_id,repeat*100+state['id'])))
            stopped=False
            for information,mode,obs,future in tasks:
                try: choice=future.result()
                except BudgetStop: stopped=True; continue
                append(out/'replay.jsonl',{'state':state['id'],'repeat':repeat,'information':information,
                    'method':mode,'observation':obs,'choice':choice,'score':replay_score(state,choice,information)})
            if stopped: raise BudgetStop('Replay stopped at budget/error guard')
        print(f'Replay repetition {repeat+1}/3 complete',flush=True)


def closed_loop(out,selected,client,pool):
    worlds=[]
    for seed in range(3):
        for idx,condition in enumerate(selected):
            for mode in ('direct','diagnose'):
                cfg=Config(scenario=condition['scenario'],strength=condition['strength'])
                worlds.append({'id':f'closed-{idx}-{seed}-{mode}','config':cfg,'seed':seed,'mode':mode,
                               'env':Environment(cfg),'decisions':[]})
    # Complete one day across all worlds before proceeding, preserving comparable horizon.
    for day in range(1,31):
        for world in worlds:
            observations=[observe(world['env'].history,i,information='flow') for i in range(24)]
            tasks=[pool.submit(client.decide,obs,world['mode'],f'{world["id"]}-{day:02d}-{i:02d}',world['seed']*100+i) for i,obs in enumerate(observations)]
            choices=[]; stopped=False
            for future in tasks:
                try: choices.append(future.result())
                except BudgetStop: stopped=True
            if stopped:
                save(out/'closed-partial.json',{'day':day,'world':world['id'],'completed_calls':len(choices),
                    'reason':'No partial joint action applied. Calls remain in calls/.'})
                raise BudgetStop('Closed-loop stopped at budget/error guard')
            row=world['env'].step(dict(enumerate(c['route'] for c in choices)))
            append(out/'closed-steps.jsonl',{'world':world['id'],'config':asdict(world['config']),
                'seed':world['seed'],'method':world['mode'],'information':'flow','observations':observations,'choices':choices,'row':row})
        print(f'Closed-loop day {day}/30 complete',flush=True)


def run(out,shared,key_file):
    out.mkdir(parents=True,exist_ok=False)
    (out/'code').mkdir()
    for p in Path(__file__).parent.glob('*.py'): shutil.copy2(p,out/'code'/p.name)
    manifest={'status':'prepared','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'model':MODEL,'config':asdict(Config()),'numerical_seeds':list(range(30)),
        'source_hashes':{p.name:digest(p) for p in sorted((out/'code').glob('*.py'))},
        'replay_planned_calls':720,'closed_planned_calls':12960,'closed_information':'flow',
        'selection_rule':'highest/lowest mean smooth/time excess over system lower bound, plus null; exploratory selection',
        'limits':{'seconds':1800,'usd':5},'scope':'synthetic mechanisms, not human calibration or NYC policy evidence'}
    save(out/'manifest.json',manifest)
    try: allocation=reserve(shared,out)
    except (BlockingIOError,RuntimeError) as e:
        manifest.update(status='budget_unavailable',reason=str(e) if not isinstance(e,BlockingIOError) else 'Shared executor lock held')
        save(out/'manifest.json',manifest)
        print(json.dumps(manifest,ensure_ascii=False),flush=True)
        return
    start=time.monotonic(); deadline=start+allocation['seconds']; client=None
    try:
        manifest['status']='numerical'; save(out/'manifest.json',manifest)
        gate=pairing_check(); save(out/'identifiability.json',gate)
        runs,states,selected=numerical(out,deadline)
        print(f'Numerical complete: {len(runs)} runs',flush=True)
        if not (gate['time_observations_equal'] and gate['flow_observations_differ'] and gate['action_relevant']):
            manifest['status']='gate_failed'; return
        manifest['status']='replay'; save(out/'manifest.json',manifest)
        client=Client(out,key_file,allocation['dollars'],deadline)
        with F.ThreadPoolExecutor(max_workers=8) as pool:
            replay(out,states,client,pool)
            manifest['status']='closed_loop'; save(out/'manifest.json',manifest)
            closed_loop(out,selected,client,pool)
        manifest['status']='complete'
    except BudgetStop as e:
        manifest.update(status='budget_or_transport_stop',reason=str(e))
    except Exception as e:
        manifest.update(status='failed',error_type=type(e).__name__)
        # Do not print exceptions from network/auth code or credential content.
    finally:
        elapsed=time.monotonic()-start
        manifest['elapsed_seconds']=elapsed
        if client: manifest['api']=client.snapshot()
        save(out/'manifest.json',manifest)
        try: settle(out,elapsed,(client.spent+client.unknown) if client else 0.)
        except (BlockingIOError,RuntimeError):
            manifest['settlement']='pending: shared writer active; full reservation remains charged'
            save(out/'manifest.json',manifest)
        from report import report
        report(out)
        print(json.dumps({'output':str(out),'status':manifest['status'],'seconds':elapsed,'api':manifest.get('api')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--shared',type=Path,default=DEFAULT_SHARED)
    p.add_argument('--key-file',type=Path,default=ROOT.parent/'token.txt')
    a=p.parse_args(); run(a.out.resolve(),a.shared.resolve(),a.key_file)

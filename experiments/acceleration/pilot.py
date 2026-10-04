#!/usr/bin/env python3
"""Budgeted initialization ablations. LLM only selects a preregistered input ID."""
import argparse, collections, csv, datetime, fcntl, gzip, hashlib, json, math, os, re, shutil, sys, time
import urllib.request, urllib.error
from pathlib import Path
import xml.etree.ElementTree as E
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import run_baseline_diagnostic as D
from analyze_baseline_diagnostic import stream, table, log_times
SOURCE = ROOT/'outputs/baseline-diagnostic-20261004-003141-495380'
MODEL = 'gpt-4.1-mini-2025-04-14'
ARMS = ('cold', 'warm_early', 'warm_latest')
# Preregistered screening tolerances, not validated convergence guarantees.
TOLERANCES = {'score': .25, 'car_share': .005, 'pt_share': .005, 'unfinished': 1500}

def selected_only(source, target):
    count=0; ids=hashlib.sha256(); groups=collections.Counter()
    with stream(source) as f, gzip.open(target,'wt') as out:
        out.write('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE population SYSTEM "http://www.matsim.org/files/dtd/population_v6.dtd">\n<population>\n')
        it=E.iterparse(f,events=('start','end'));_,root=next(it)
        for event,person in it:
            if event!='end' or person.tag!='person':continue
            plans=person.findall('plan'); selected=[p for p in plans if p.get('selected')=='yes']
            if len(selected)!=1:raise ValueError('Expected one selected plan')
            for p in plans:
                if p is not selected[0]:person.remove(p)
            selected[0].attrib.pop('score',None)
            pid=person.get('id');ids.update((pid+'\n').encode());count+=1
            groups[person.find("attributes/attribute[@name='subpopulation']").text]+=1
            out.write(E.tostring(person,encoding='unicode'));root.remove(person)
        out.write('</population>\n')
    return dict(persons=count,ordered_person_ids_sha256=ids.hexdigest(),groups=dict(groups),source=str(source),source_sha256=D.sha(source),output_sha256=D.sha(target))

def setparam(root,module,name,value):
    m=root.find(f"module[@name='{module}']")
    if m is None:raise ValueError('Missing module '+module)
    p=m.find(f"param[@name='{name}']")
    if p is None:p=E.SubElement(m,'param',name=name)
    p.set('value',str(value))

def prepare(iterations):
    start=time.monotonic()
    if not 6<=iterations<=20:raise ValueError('Pilot horizon must be 6..20')
    out=ROOT/'outputs'/('acceleration-pilot-'+time.strftime('%Y%m%d-%H%M%S'));out.mkdir()
    (out/'inputs').mkdir();(out/'code').mkdir()
    for p in Path(__file__).parent.glob('*.py'):shutil.copy2(p,out/'code'/p.name)
    shutil.copy2(ROOT/'scripts/run_baseline_diagnostic.py',out/'code/run_baseline_diagnostic.py')
    shutil.copy2(ROOT/'scripts/analyze_baseline_diagnostic.py',out/'code/analyze_baseline_diagnostic.py')
    shutil.copy2(ROOT/'target/matsim-nyc-modernized-1.0.0.jar',out/'runner.jar')
    shutil.copy2(SOURCE/'capacity-factors.csv',out/'capacity-factors.csv')
    sim=SOURCE/'five-attempt-1/simulation'
    sources={'cold':ROOT/'scenarios/nyc/population-v6.xml.gz',
             'warm_early':sim/'ITERS/it.1/BUILT.1.plans.xml.zst',
             'warm_latest':sim/'BUILT.output_plans.xml.zst'}
    inventories={}
    for arm,source in sources.items():
        inventories[arm]=selected_only(source,out/'inputs'/f'{arm}.xml.gz')
        print('Prepared '+arm,flush=True)
    identities={(x['persons'],x['ordered_person_ids_sha256']) for x in inventories.values()}
    # XML ordering can differ; verify actual membership separately if so.
    if any(x['persons']!=389301 for x in inventories.values()):raise ValueError('Population changed')
    if len({json.dumps(x['groups'],sort_keys=True) for x in inventories.values()})!=1:raise ValueError('Groups changed')
    def members(path):
        with stream(path) as f:
            it=E.iterparse(f,events=('start','end'));_,r=next(it);result=set()
            for ev,e in it:
                if ev=='end' and e.tag=='person':result.add(e.get('id'));r.remove(e)
            return result
    expected=members(out/'inputs/cold.xml.gz')
    for arm in ARMS[1:]:
        if members(out/'inputs'/f'{arm}.xml.gz')!=expected:raise ValueError('Person membership changed')
    history=[]
    for r in csv.DictReader((SOURCE/'iteration_metrics.csv').open()):
        if r['stage']=='five':history.append({k:float(r[v]) for k,v in {'iteration':'iteration','score':'score_avg_executed','car_share':'mode_share_car','pt_share':'mode_share_pt','unfinished':'unique_stuck_persons'}.items()})
    context={'target':'actual2025 weekday pricing on historical NYC demand; same road and transit capacities as source',
      'candidates':{'cold':'original selected plans','warm_early':'selected plans before source iteration 1; do not attribute iteration-1 outcomes to an after-iteration checkpoint','warm_latest':'selected plans from source final output after iteration 4'},
      'source':'baseline diagnostic, not converged; innovation disabled at source iteration 4',
      'history':history,'known_limitations':['bus capacity bottleneck','road unfinished trips','routing/scoring group mismatch'],
      'transfer':'selected plans only; all scores and alternatives removed; route/travel-time engine state not restored',
      'available_target_outcomes':None}
    D.save(out/'context.json',context)
    manifest={'created_utc':D.now(),'status':'prepared','attempts':[],'iterations':iterations,'arms':list(ARMS),
      'target':'actual2025','seed':4711,'budget_seconds':14400,'api_budget_usd':20,'runner_sha256':D.sha(out/'runner.jar'),
      'initialization':inventories,'input_inventory':D.input_inventory(),'source_campaign':str(SOURCE),
      'scope':'single target and seed; finite horizon pilot, no converged reference or policy ranking claim',
      'tolerances':TOLERANCES,'preparation_seconds':time.monotonic()-start,
      'source_simulation_seconds':json.loads((SOURCE/'run_manifest.json').read_text())['attempts'][-1]['elapsed_seconds']}
    D.save(out/'run_manifest.json',manifest)
    D.save(out/'budget.json',{'limit_seconds':14400,'used_seconds':0,'active':None})
    D.save(out/'api-budget.json',{'limit_usd':20,'reserved_usd':0,'measured_usd':0,'calls':[]})
    (out/'workspace-before.diff').write_text(D.command(['git','diff']))
    hashes={str(p.relative_to(out)):D.sha(p) for p in [out/'runner.jar',out/'capacity-factors.csv',out/'context.json',*sorted((out/'inputs').glob('*'))]}
    D.save(out/'prepared-hashes.json',hashes)
    print(out,flush=True)
    return out

def llm_select(out,key_file,enriched=False):
    # Small one-shot call; reserve a conservative $0.10 even for unknown outcomes.
    with (out/'api.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        variant='constraints' if enriched else 'base'
        suffix='-constraints' if enriched else ''
        dest=out/f'llm-selection{suffix}.json'
        if dest.exists():return json.loads(dest.read_text())
        ledger=json.loads((out/'api-budget.json').read_text())
        if any(c.get('variant','base')==variant for c in ledger['calls']):raise ValueError('Previous API attempt retained; no automatic retry')
        if len(ledger['calls'])>=2:raise ValueError('Pilot permits at most two API calls')
        if ledger['reserved_usd']+.10>ledger['limit_usd']:raise ValueError('API budget exceeded')
        context=json.loads((out/'context.json').read_text())
        if enriched:
            context['static_model_constraints']={'outside_group_persons':60203,'outside_group_strategy':'SelectExpBeta only: no time mutation, mode mutation, or rerouting innovation','warm_route_risk':'Existing routes were prepared under baseline. Normal initialization may preserve valid routes. For noninnovating agents, initialization differences may persist. This is a risk, not a measured target result.','evaluation_goal':'Match a common target result, not simply maximize finite-horizon score'}
        schema={'type':'object','properties':{'candidate':{'type':'string','enum':list(ARMS)},'reason':{'type':'string'},'risks':{'type':'array','items':{'type':'string'}}},'required':['candidate','reason','risks'],'additionalProperties':False}
        body={'model':MODEL,'store':False,'max_output_tokens':600,
          'instructions':'Choose a starting population for a finite-horizon MATSim acceleration pilot. Use only supplied historical aggregate evidence. No target results are available. Prefer reducing adaptation cost without claiming convergence or realism. Your choice is advisory, not a command. Explain uncertainty briefly.',
          'input':json.dumps(context),'text':{'format':{'type':'json_schema','name':'initialization','strict':True,'schema':schema}}}
        raw=json.dumps(body).encode()
        if len(raw)>30000:raise ValueError('Request unexpectedly large')
        key=key_file.read_text().strip()
        if not key or any(c.isspace() for c in key):raise ValueError('Credential file must contain only the API key')
        D.save(out/f'llm-request{suffix}.json',body)
        record={'variant':variant,'started_utc':D.now(),'model':MODEL,'reservation_usd':.10,'status':'pending'}
        ledger['calls'].append(record);ledger['reserved_usd']+=.10;D.save(out/'api-budget.json',ledger)
        start=time.monotonic()
        try:
            req=urllib.request.Request('https://api.openai.com/v1/responses',data=raw,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=60) as response:result=json.load(response)
            if result.get('status')!='completed':raise ValueError('API response incomplete')
            text=''.join(c.get('text','') for o in result.get('output',[]) if o.get('type')=='message' for c in o.get('content',[]) if c.get('type')=='output_text')
            choice=json.loads(text)
            if choice.get('candidate') not in ARMS:raise ValueError('Invalid candidate')
            usage=result['usage'];cost=(usage['input_tokens']*.40+usage['output_tokens']*1.60)/1e6
            record.update(status='complete',usage=usage,estimated_usd=cost,seconds=time.monotonic()-start)
            ledger['measured_usd']+=cost
            D.save(dest,dict(**choice,context_variant=variant,model=result.get('model'),usage=usage,estimated_usd=cost,seconds=record['seconds']))
        except Exception as error:
            # Never persist response bodies, credential, headers, or raw error text.
            record.update(status='failed',error_type=type(error).__name__,http_status=getattr(error,'code',None),seconds=time.monotonic()-start)
            raise RuntimeError('API selection failed; see sanitized api-budget.json') from None
        finally:D.save(out/'api-budget.json',ledger)
        return choice

def config(out,dest,iterations):
    arm=dest.name.split('-attempt-')[0]
    folder=ROOT/'scenarios/nyc-zip-aligned';root=E.parse(folder/'config-actual2025.xml').getroot()
    for module in root:
        for p in module.findall('param'):
            k,v=p.get('name'),p.get('value')
            if k in ['inputCountsFile','inputNetworkFile','inputPlansFile','transitScheduleFile','vehiclesFile','tollLinksFile'] and v!='null':p.set('value',str((folder/v).resolve()))
            if k=='pricing2025Links':p.set('value',str(ROOT/'scenarios/nyc-2025/links.csv'))
            if k=='archiveCapacityFactors':p.set('value',str(out/'capacity-factors.csv'))
    for module,name,value in [('plans','inputPlansFile',out/'inputs'/f'{arm}.xml.gz'),('controler','outputDirectory',dest/'simulation'),('controler','firstIteration',0),('controler','lastIteration',iterations-1),('controler','writeEventsInterval',1),('controler','writePlansInterval',iterations-1)]:setparam(root,module,name,value)
    p=dest/'config.xml';p.write_text('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE config SYSTEM "http://www.matsim.org/files/dtd/config_v2.dtd">\n'+E.tostring(root,encoding='unicode'))
    return p

def execute(out):
    with (out/'executor.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=json.loads((out/'run_manifest.json').read_text());b=json.loads((out/'budget.json').read_text())
        if b['active']:raise ValueError('Reconcile interrupted budget before resuming')
        m['status']='running';D.save(out/'run_manifest.json',m)
        for rel,digest in json.loads((out/'prepared-hashes.json').read_text()).items():
            if D.sha(out/rel)!=digest:raise ValueError('Prepared input changed: '+rel)
        for arm in ARMS:
            previous=[a for a in m['attempts'] if a['stage']==arm]
            if previous:
                if previous[-1]['status']=='complete':continue
                raise ValueError('Failed attempt must be inspected before retry')
            env=json.loads((ROOT/'.tools/environment.json').read_text())
            D.generate_config=config
            a=D.run_attempt(out,arm,m['iterations'],'16g',m,b,Path(env['java_home'])/'bin/java')
            if a['status']!='complete':raise RuntimeError('Pilot stopped: '+a['status'])
        m['status']='simulations_complete';D.save(out/'run_manifest.json',m)

def stable(rows):
    if len(rows)<3:return False
    return all(all(math.isfinite(r[k]) for r in rows[-3:]) and max(r[k] for r in rows[-3:])-min(r[k] for r in rows[-3:])<=tol for k,tol in TOLERANCES.items())

def summarize(out):
    m=json.loads((out/'run_manifest.json').read_text());allrows=[];results={}
    for a in m['attempts']:
        if a['status']!='complete':continue
        dest=out/a['directory'];sim=dest/'simulation'
        scores=table(sim/'BUILT.scorestats.csv');modes=table(sim/'BUILT.modestats.csv')
        log=(dest/'run.log').read_text()
        starts,ends,_=log_times(log)
        match=re.search(r'global innovation switch off after iteration: (\d+)',log)
        innovation_off_from=int(match[1])+1 if match else None
        rows=[]
        for s,mode in zip(scores,modes):
            i=int(s['iteration'])
            if i!=int(mode['iteration']):raise ValueError('Metric iteration mismatch')
            h=table(sim/f'ITERS/it.{i}/BUILT.{i}.legHistogram.txt')
            row={'arm':a['stage'],'iteration':i,'score':float(s['avg_executed']),'car_share':float(mode['car']),'pt_share':float(mode['pt']),
                 'unfinished':sum(float(x['stuck_all']) for x in h),'pt_unfinished':sum(float(x['stuck_pt']) for x in h),
                 'iteration_seconds':ends[i]-starts[i]}
            row['elapsed_to_iteration_end_seconds']=ends[i]-datetime.datetime.fromisoformat(a['started_utc']).timestamp()
            rows.append(row)
        for i,r in enumerate(rows):
            r['screen_stable']=stable(rows[:i+1])
            r['innovation_enabled']=None if innovation_off_from is None else i<innovation_off_from
        tail={k:sum(r[k] for r in rows[-3:])/3 for k in TOLERANCES}
        screens=[r['iteration'] for r in rows if r['screen_stable']]
        first=screens[0] if screens else None
        results[a['stage']]={'elapsed_seconds':a['elapsed_seconds'],'pre_iteration_seconds':starts[0]-datetime.datetime.fromisoformat(a['started_utc']).timestamp(),'mean_iteration_seconds':sum(r['iteration_seconds'] for r in rows)/len(rows),'final_three_mean':tail,'tail_stable':stable(rows),
          'first_stability_screen':first,'post_screen_observations':None if first is None else len(rows)-1-first,'independent_future_tail_available':first is not None and first<len(rows)-3,'screen_matches_tail':None if first is None else all(abs(rows[first][k]-tail[k])<=tol for k,tol in TOLERANCES.items()),
          'peak_rss_gib':a['sampled_peak_group_rss_bytes']/1024**3,'innovation_off_from':innovation_off_from}
        allrows+=rows
    if 'cold' in results:
        ref=results['cold']['final_three_mean']
        for arm,r in results.items():
            rr=[x for x in allrows if x['arm']==arm]
            hits=[]
            for i in range(2,len(rr)):
                means={k:sum(x[k] for x in rr[i-2:i+1])/3 for k in TOLERANCES}
                if all(abs(means[k]-ref[k])<=tol for k,tol in TOLERANCES.items()):hits.append(i)
            sustained=next((i for i in hits if all(j in hits for j in range(i,len(rr)))),None)
            r['finite_cold_reference']={'final_within_tolerances':all(abs(r['final_three_mean'][k]-ref[k])<=tol for k,tol in TOLERANCES.items()),'first_matching_window_end':hits[0] if hits else None,'sustained_matching_window_end':sustained,'sustained_elapsed_seconds':rr[sustained]['elapsed_to_iteration_end_seconds'] if sustained is not None else None,'independent_convergence_reference':False}
    if allrows:
        with (out/'trajectory.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
    D.save(out/'summary.json',{'arms':results,'tolerances':TOLERANCES,'reference':'finite-horizon endpoints only; not ground truth','source_cost_seconds':m['source_simulation_seconds']})
    return results

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','select','run','summarize']);p.add_argument('--run-dir',type=Path);p.add_argument('--iterations',type=int,default=12);p.add_argument('--key-file',type=Path);p.add_argument('--context-constraints',action='store_true')
    a=p.parse_args()
    if a.action=='prepare':prepare(a.iterations);return
    if not a.run_dir:p.error('--run-dir required')
    out=a.run_dir.resolve()
    if a.action=='select':
        if not a.key_file:p.error('--key-file required')
        print(json.dumps(llm_select(out,a.key_file,a.context_constraints),ensure_ascii=False))
    elif a.action=='run':execute(out);summarize(out)
    else:print(json.dumps(summarize(out),indent=2))
if __name__=='__main__':main()

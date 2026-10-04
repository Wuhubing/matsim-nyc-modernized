#!/usr/bin/env python3
"""Two independent fixed-plan baseline runs, opt-in initialization guard, shared budget."""
import argparse,collections as C,copy,csv,datetime,fcntl,gzip,json,os,shutil,subprocess,sys,time,xml.etree.ElementTree as E
from pathlib import Path
import run_baseline_diagnostic as D
from analyze_baseline_diagnostic import stream
ROOT=D.ROOT
SOURCE=ROOT/'outputs/baseline-diagnostic-20261004-003141-495380'
ANALYSIS=SOURCE/'unfinished-analysis-20261004'
def persons(path):
 with stream(path) as f:
  it=E.iterparse(f,events=('start','end'));_,root=next(it)
  for ev,e in it:
   if ev=='end' and e.tag=='person':yield e;root.remove(e)
def xmlwrite(path,root):
 E.indent(root)
 if root.tag=='vehicleDefinitions':root.set('xmlns','http://www.matsim.org/files/dtd')
 data=E.tostring(root,encoding='utf-8',xml_declaration=True)
 if root.tag=='transitSchedule':data=data.replace(b'?>',b'?>\n<!DOCTYPE transitSchedule SYSTEM "http://www.matsim.org/files/dtd/transitSchedule_v2.dtd">',1)
 with gzip.open(path,'wb') as f:f.write(data)
def vehicle_data(path):
 with stream(path) as f:root=E.parse(f).getroot()
 for e in root.iter():e.tag=e.tag.split('}')[-1]
 return root

def normalize_transit(schedule,vehicles):
 usage=C.defaultdict(set)
 for line in schedule.findall('transitLine'):
  for route in line.findall('transitRoute'):
   for dep in route.findall('departures/departure'):usage[dep.get('vehicleRefId')].add(route.findtext('transportMode'))
 vs={v.get('id'):v for v in vehicles.findall('vehicle')};split=[]
 for v,modes in list(usage.items()):
  if 'bus' in modes and len(modes)>1:
   name=v+'__bus_diagnostic';assert name not in vs
   cloned=copy.deepcopy(vs[v]);cloned.set('id',name);vehicles.append(cloned);vs[name]=cloned;split.append([v,name])
   for line in schedule.findall('transitLine'):
    for route in line.findall('transitRoute'):
     if route.findtext('transportMode')=='bus':
      for dep in route.findall('departures/departure'):
       if dep.get('vehicleRefId')==v:dep.set('vehicleRefId',name)
   usage[name]={'bus'};usage[v]-={'bus'}
 bus={v for v,mode in usage.items() if mode=={'bus'}};types={v.get('id'):v for v in vehicles.findall('vehicleType')};bus_types=set();type_splits=[]
 for typ in sorted({vs[v].get('type') for v in bus}):
  others=any(v.get('id') not in bus and v.get('type')==typ for v in vs.values())
  target=typ
  if others:
   target=typ+'__bus_diagnostic';assert target not in types;clone=copy.deepcopy(types[typ]);clone.set('id',target);vehicles.append(clone);types[target]=clone;type_splits.append([typ,target])
   for v in bus:
    if vs[v].get('type')==typ:vs[v].set('type',target)
  bus_types.add(target)
 changed=[];treatment=copy.deepcopy(vehicles)
 for v in treatment.findall('vehicleType'):
  if v.get('id') in bus_types:
   cap=v.find('capacity');before=dict(cap.attrib)
   for k in ['seats','standingRoomInPersons']:cap.set(k,str(2*int(cap.get(k))))
   changed.append(dict(type=v.get('id'),before=before,after=dict(cap.attrib)))
 return vehicles,treatment,dict(vehicle_splits=split,type_splits=type_splits,bus_vehicle_ids=sorted(bus),capacity_changes=changed,departures=len(schedule.findall('.//departure')))

def prepare():
 out=ROOT/'outputs'/('bus-capacity-diagnostic-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'));out.mkdir();(out/'common').mkdir()
 subprocess.run(['git','diff'],cwd=ROOT,stdout=(out/'workspace-before.diff').open('w'),check=True)
 manifest={'created_utc':D.now(),'attempts':[],'status':'preparing','source_campaign':str(SOURCE),'source_commit':D.command(['git','rev-parse','HEAD'],ROOT).strip(),'source_plan_stage':'before-mobsim plans dump (MATSim PlansDumpingImpl); serialized reconstruction, not a complete internal-state snapshot','input_inventory_reference':str(SOURCE/'input_inventory.json'),'budget_seconds':7200}
 D.save(out/'run_manifest.json',manifest);D.save(out/'budget.json',dict(limit_seconds=7200,used_seconds=0,active=None,updated_utc=D.now()))
 shutil.copy2(ROOT/'target/matsim-nyc-modernized-1.0.0.jar',out/'runner.jar');shutil.copy2(SOURCE/'capacity-factors.csv',out/'capacity-factors.csv')
 for script in ['run_bus_capacity_diagnostic.py','run_baseline_diagnostic.py','analyze_baseline_diagnostic.py']:
  shutil.copy2(ROOT/'scripts'/script,out/script)
 original={r['person']:int(r['ordinal']) for r in csv.DictReader(open(ANALYSIS/'4-unfinished.csv'))}
 cohort={r['person']:original[r['person']] for r in csv.DictReader(open(ANALYSIS/'4-compatible-service.csv')) if r['category']=='all_compatible_departures_full'};assert len(cohort)==29018;D.save(out/'original-cohort.json',cohort)
 counts=C.Counter()
 with gzip.open(out/'common/frozen-plans.xml.gz','wt') as f,gzip.open(out/'common/plan-index.jsonl.gz','wt') as meta:
  f.write('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE population SYSTEM "http://www.matsim.org/files/dtd/population_v6.dtd">\n<population>\n')
  for pe in persons(SOURCE/'five-attempt-1/simulation/ITERS/it.4/BUILT.4.plans.xml.zst'):
   plan=pe.find("plan[@selected='yes']");assert plan is not None
   for x in list(pe):
    if x.tag=='plan' and x is not plan:pe.remove(x)
   plan.attrib.pop('score',None);pid=pe.get('id');group=pe.find("attributes/attribute[@name='subpopulation']").text;legs=plan.findall('leg');acts=plan.findall('activity');pts={}
   for i,leg in enumerate(legs,1):
    if leg.get('mode')=='pt':pts[i]=json.loads(leg.find('route').text)
   assert len(acts)==len(legs)+1
   meta.write(json.dumps(dict(person=pid,group=group,modes=[l.get('mode') for l in legs],activities=[a.get('type') for a in acts],pt=pts))+'\n');counts[group]+=1;f.write(E.tostring(pe,encoding='unicode'))
  f.write('</population>\n')
 assert sum(counts.values())==389301
 schedule=E.parse(gzip.open(ROOT/'scenarios/nyc/separated-schedule.xml.gz')).getroot()
 vehicles=vehicle_data(SOURCE/'five-attempt-1/simulation/BUILT.output_transitVehicles.xml.zst')
 vehicles,treatment,normalization=normalize_transit(schedule,vehicles)
 normalization['population_groups']=dict(counts)
 xmlwrite(out/'common/schedule.xml.gz',schedule);xmlwrite(out/'common/control-vehicles.xml.gz',vehicles);xmlwrite(out/'common/treatment-vehicles.xml.gz',treatment)
 D.save(out/'normalization.json',normalization)
 tree=E.parse(SOURCE/'five-attempt-1/config.xml');root=tree.getroot()
 for m in root.findall('module'):
  name=m.get('name')
  if name in ['strategy','replanning']:
   for x in list(m):
    if x.tag=='parameterset':m.remove(x)
  for p in m.findall('param'):
   k=p.get('name')
   if k=='inputPlansFile':p.set('value',str(out/'common/frozen-plans.xml.gz'))
   if k=='transitScheduleFile':p.set('value',str(out/'common/schedule.xml.gz'))
   if k=='archiveCapacityFactors':p.set('value',str(out/'capacity-factors.csv'))
   if k in ['firstIteration','lastIteration']:p.set('value','0')
 # Empty strategies are valid with no replanning iterations.
 E.indent(root);tree.write(out/'common/base-config.xml',encoding='utf-8',xml_declaration=True)
 manifest.update(status='prepared',runner_sha256=D.sha(out/'runner.jar'),common_hashes={str(p.relative_to(out)):D.sha(p) for p in (out/'common').iterdir()});D.save(out/'run_manifest.json',manifest)
 print(out,flush=True);return out

def config(out,dest,iterations):
 arm=dest.name.split('-attempt')[0];tree=E.parse(out/'common/base-config.xml');root=tree.getroot()
 for m in root.findall('module'):
  for p in m.findall('param'):
   if p.get('name')=='outputDirectory':p.set('value',str(dest/'simulation'))
   if m.get('name')=='transit' and p.get('name')=='vehiclesFile':p.set('value',str(out/f'common/{arm}-vehicles.xml.gz'))
 (dest/'config.xml').write_text('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE config SYSTEM "http://www.matsim.org/files/dtd/config_v2.dtd">\n'+E.tostring(root,encoding='unicode'));return dest/'config.xml'

def validate_arm(out,arm,attempt):
 dest=out/attempt['directory']
 guard=json.load(open(dest/'fixed-plan-guard.json'))
 assert guard['changed']==0 and guard['persons']==389301
 actual=vehicle_data(dest/'simulation/BUILT.output_transitVehicles.xml.zst')
 expected=vehicle_data(out/f'common/{arm}-vehicles.xml.gz')
 caps=lambda r:{e.get('id'):dict(e.find('capacity').attrib) for e in r.findall('vehicleType')}
 assert caps(actual)==caps(expected)


def execute(out):
 lock=(out/'executor.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 m=json.load(open(out/'run_manifest.json'));b=json.load(open(out/'budget.json'))
 if b['active']:raise RuntimeError('Reconcile interrupted active budget entry before resume')
 for path,expected_hash in m['common_hashes'].items():
  if D.sha(out/path)!=expected_hash:raise RuntimeError('Prepared input changed: '+path)
 D.generate_config=config;java=ROOT/'.tools/jdk-25.0.4.1+1/Contents/Home/bin/java'
 for arm in ['control','treatment']:
  prior=[a for a in m['attempts'] if a['stage']==arm]
  if prior and prior[-1]['status']=='complete':
   validate_arm(out,arm,prior[-1]);continue
  heaps=['16g'] if not prior or (out/'compat-retry.json').exists() else []
  if (out/'compat-retry.json').exists():(out/'compat-retry.json').unlink()
  if prior and prior[-1].get('java_heap_oom') and len(prior)==1 and not prior[-1].get('reason'):heaps=['24g']
  if not heaps:raise RuntimeError('No automatic retry allowed for '+arm)
  for heap in heaps:
   index=len([a for a in m['attempts'] if a['stage']==arm])+1
   os.environ['JAVA_TOOL_OPTIONS']='-Dnyc.fixedPlanGuard='+str(out/f'{arm}-attempt-{index}/fixed-plan-guard.json')
   a=D.run_attempt(out,arm,1,heap,m,b,java)
   if a['status']!='complete':raise RuntimeError('Run stopped: '+str(a))
   validate_arm(out,arm,a)
 m['status']='both_runs_complete';D.save(out/'run_manifest.json',m)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--prepare-only',action='store_true');p.add_argument('--run-dir',type=Path);p.add_argument('--analyze-only',action='store_true');a=p.parse_args();out=a.run_dir.resolve() if a.run_dir else prepare()
 if not a.prepare_only:
  if not a.analyze_only:execute(out)
  subprocess.run([sys.executable,str(ROOT/'scripts/analyze_bus_capacity_diagnostic.py'),str(out)],check=True)
  subprocess.run([sys.executable,str(ROOT/'scripts/report_bus_capacity_diagnostic.py'),str(out)],check=True)

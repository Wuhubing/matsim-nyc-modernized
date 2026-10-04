#!/usr/bin/env python3
"""Baseline-only diagnostic: prepare once, run smoke then independent 0..4, analyze.
No simulation or source-data changes are made by importing this module.
"""
import argparse, collections, csv, datetime, fcntl, gzip, hashlib, json, os
from pathlib import Path
import re, shutil, signal, subprocess, sys, tarfile, time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'C2SMART-Year3-Project'
SOURCE = OLD / 'src/main/java/org/matsim/codeexamples/network/timeDependentNetwork/RunTimeDependentNetworkExample.java'
GIB = 1024**3

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path, obj):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n')
    tmp.replace(path)
def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def command(args, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True).stdout

def factors_from_source(path):
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', path.read_text(), flags=re.S)
    result = []
    for name in ('ExpressFactor', 'ArterialFactor'):
        values = re.findall(r'double\s+'+name+r'\s*\[\]\s*=\s*\{([^}]+)\}', text)
        if len(values) != 1: raise ValueError('Expected one active array: '+name)
        row = [v.strip() for v in values[0].split(',')]
        if len(row)!=6 or any(not 0<float(v)<float('inf') for v in row): raise ValueError(name)
        result.append(row)
    return result

def input_inventory():
    cachepath=ROOT/'.tools/input-checks.json'
    cache=json.loads(cachepath.read_text()) if cachepath.exists() else {}
    inventory=[]
    for rel,expected in json.loads((ROOT/'inputs-sha256.json').read_text()).items():
        p=(ROOT/rel).resolve(); st=p.stat(); identity=[str(p),st.st_size,st.st_mtime_ns,st.st_ctime_ns]
        old=cache.get(rel,{})
        digest=old['sha256'] if old.get('identity')==identity else sha(p)
        if digest!=expected: raise ValueError('Input checksum mismatch: '+rel)
        cache[rel]={'identity':identity,'sha256':digest}
        inventory.append({'path':str(p),'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'sha256':digest})
    cachepath.parent.mkdir(exist_ok=True);save(cachepath,cache)
    return inventory

def inventory_counts(out):
    base=ROOT/'scenarios/nyc'; counts={}; groups=collections.Counter(); candidates={}
    with gzip.open(base/'population-v6.xml.gz','rb') as f:
        context=ET.iterparse(f,events=('start','end')); _,root=next(context)
        for event,e in context:
            if event=='end' and e.tag=='person':
                a=e.find("attributes/attribute[@name='subpopulation']")
                group=a.text if a is not None else '<missing>';groups[group]+=1
                plans=e.findall('plan'); selected=next((p for p in plans if p.get('selected')=='yes'),plans[0] if plans else None)
                modes={l.get('mode') for l in selected.findall('leg')} if selected is not None else set()
                for category,match in [('car','car' in modes),('pt','pt' in modes)]:
                    if match:
                        key=(group,category); row={'person_id':e.get('id'),'subpopulation':group,'category':category,'selection':'pre-run; first two lexical IDs per group/mode; no assumed toll exposure','input_person_xml':ET.tostring(e,encoding='unicode')}
                        candidates[key]=sorted(candidates.get(key,[])+[row],key=lambda x:x['person_id'])[:2]
                root.remove(e)
    counts['persons']=sum(groups.values());counts['subpopulations']=dict(groups)
    for name,tags in [('separated-network.xml.gz',('node','link')),('separated-schedule.xml.gz',('transitLine','transitRoute','stopFacility')),('separated-vehicle.xml.gz',('vehicle','vehicleType'))]:
        c=collections.Counter()
        with gzip.open(base/name,'rb') as f:
            context=ET.iterparse(f,events=('start','end'));_,root=next(context)
            for event,e in context:
                if event=='end':
                    tag=e.tag.rsplit('}',1)[-1]
                    if tag in tags:c[tag]+=1
                    e.clear();root.clear()
        counts[name]=dict(c)
    selected=[];seen=set()
    for key in sorted(candidates):
        for row in candidates[key]:
            if row['person_id'] not in seen and len(selected)<16:selected.append(row);seen.add(row['person_id'])
    save(out/'diagnostic_people.json',selected);save(out/'scenario_inventory.json',counts)
    if counts['persons']!=389301: raise ValueError('Unexpected population size')

def prepare(budget):
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    out=ROOT/'outputs'/('baseline-diagnostic-'+stamp);out.mkdir(parents=True)
    start=time.monotonic()
    manifest={'created_utc':now(),'status':'preparing','root':str(ROOT),'commit':command(['git','rev-parse','HEAD']).strip(),
        'initial_git_status':command(['git','status','--short']),'old_git_status':command(['git','status','--short'],OLD),
        'budget_seconds':budget*3600,'seed':4711,'threads':{'global':16,'qsim':16},
        'profile':'modern engine + exact old fixed-entry capacities; not final calibrated factors',
        'scope':'baseline only; full population; no behavior change; diagnostic 0..4 is not full-run prefix',
        'python':sys.version,'machine':command(['uname','-a']).strip(),'attempts':[]}
    save(out/'run_manifest.json',manifest)
    (out/'workspace.diff').write_text(command(['git','diff','--binary']))
    rows=factors_from_source(SOURCE)
    factor=out/'capacity-factors.csv'
    factor.write_text('period,expressway,arterial\n'+''.join(f'{i},{rows[0][i]},{rows[1][i]}\n' for i in range(6)))
    save(out/'capacity-provenance.json',{'source':str(SOURCE),'source_sha256':sha(SOURCE),'source_git_commit':command(['git','rev-parse','HEAD'],OLD).strip(),'source_has_local_changes':bool(command(['git','diff','--',str(SOURCE)],OLD).strip()),'label':'old fixed-entry parameters; final calibration unverified','csv_sha256':sha(factor),'rows':rows})
    shutil.copy2(SOURCE,out/'old-fixed-entry.java.txt')
    save(out/'input_inventory.json',input_inventory());inventory_counts(out)
    with tarfile.open(out/'diagnostic-sources.tar.gz','w:gz') as tar:
        for directory in ['src','scripts']:
            for p in sorted((ROOT/directory).rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts:tar.add(p,arcname=str(p.relative_to(ROOT)))
        for p in ['pom.xml','README.md','PROVENANCE.md','inputs-sha256.json']:tar.add(ROOT/p,arcname=p)
    save(out/'budget.json',{'limit_seconds':budget*3600,'used_seconds':0,'active':None,'updated_utc':now()})
    manifest.update(status='prepared',preparation_seconds=time.monotonic()-start)
    save(out/'run_manifest.json',manifest)
    print(out,flush=True);return out

def generate_config(out, dest, iterations):
    source=ROOT/'scenarios/nyc-zip-aligned/config-baseline.xml'
    tree=ET.parse(source);root=tree.getroot()
    paths={'inputCountsFile','inputNetworkFile','inputPlansFile','transitScheduleFile','vehiclesFile','tollLinksFile'}
    for m in root:
        for p in m.findall('param'):
            k,v=p.get('name'),p.get('value')
            if k in paths and v!='null':p.set('value',str((source.parent/v).resolve()))
            if k=='archiveCapacityFactors':p.set('value',str(out/'capacity-factors.csv'))
            if k=='outputDirectory':p.set('value',str(dest/'simulation'))
            if k=='firstIteration':p.set('value','0')
            if k=='lastIteration':p.set('value',str(iterations-1))
            if k in ('writePlansInterval','writeEventsInterval'):p.set('value','1')
    # Only output settings are added. Do not adjust strategies or their shutdown fraction.
    scoring=root.find("module[@name='planCalcScore']")
    if scoring is None:scoring=root.find("module[@name='scoring']")
    if scoring is None:raise ValueError('Missing scoring module')
    p=scoring.find("param[@name='writeExperiencedPlans']")
    if p is None:p=ET.SubElement(scoring,'param',name='writeExperiencedPlans')
    p.set('value','true')
    ET.indent(root)
    path=dest/'config.xml'
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE config SYSTEM "http://www.matsim.org/files/dtd/config_v2.dtd">\n'+ET.tostring(root,encoding='unicode'))
    return path

def memory_sample(pgid):
    rss=0;found=False
    for line in command(['ps','-axo','pgid=,rss=']).splitlines():
        parts=line.split()
        if len(parts)==2 and int(parts[0])==pgid:rss+=int(parts[1])*1024;found=True
    return rss if found else None

def system_sample():
    result={'disk_free_bytes':shutil.disk_usage(ROOT).free,'pressure_level':None,'swap_used_bytes':None}
    for key,args in [('pressure_level',['sysctl','-n','kern.memorystatus_vm_pressure_level']),('swap_used_bytes',['sysctl','-n','vm.swapusage'])]:
        try:
            value=command(args).strip()
            if key=='pressure_level':result[key]=int(value)
            else:
                m=re.search(r'used\s*=\s*([\d.]+)([MGT])',value)
                if m:result[key]=int(float(m[1])*{'M':1024**2,'G':GIB,'T':1024**4}[m[2]])
        except (subprocess.CalledProcessError,ValueError):pass
    return result

def resource_reason(sample, history, critical_since, elapsed):
    if sample['disk_free_bytes']<30*GIB:return 'disk_below_30_GiB',critical_since
    if sample.get('pressure_level')==4:
        critical_since=elapsed if critical_since is None else critical_since
        if elapsed-critical_since>=60:return 'sustained_critical_memory_pressure',critical_since
    else:critical_since=None
    swaps=[(t,s) for t,s in history if elapsed-t<=300 and s is not None]
    if sample.get('swap_used_bytes') is not None and swaps and sample['swap_used_bytes']-min(s for _,s in swaps)>2*GIB:
        return 'swap_growth_over_2_GiB_in_5_minutes',critical_since
    return None,critical_since

def stop_group(proc, grace_seconds=60):
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:proc.wait(timeout=max(0,grace_seconds))
    except subprocess.TimeoutExpired:
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        proc.wait()

def run_attempt(out, stage, iterations, heap, manifest, ledger, java):
    index=sum(a['stage']==stage for a in manifest['attempts'])+1
    dest=out/f'{stage}-attempt-{index}';dest.mkdir()
    config=generate_config(out,dest,iterations)
    remaining=ledger['limit_seconds']-ledger['used_seconds']
    print(f'{stage}: used={ledger["used_seconds"]:.1f}s remaining={remaining:.1f}s heap={heap}',flush=True)
    if remaining<=0:raise RuntimeError('Shared simulation budget exhausted')
    cmd=['/usr/bin/time','-l',str(java),'-Duser.language=en','-Duser.country=US','-Xmx'+heap,'-jar',str(out/'runner.jar'),str(config)]
    attempt={'stage':stage,'iterations':iterations,'heap':heap,'directory':dest.name,'command':cmd,'started_utc':now(),'status':'running','config_sha256':sha(config)}
    manifest['attempts'].append(attempt);save(out/'run_manifest.json',manifest)
    used_before=ledger['used_seconds'];start=time.monotonic();history=[];critical=None;peak=0;reason=None;proc=None
    initial=system_sample()
    if initial['disk_free_bytes']<30*GIB or initial.get('pressure_level')==4:
        attempt.update(status='blocked',reason='preflight_resource_pressure');save(out/'run_manifest.json',manifest);return attempt
    try:
        with (dest/'run.log').open('w') as log,(dest/'resources.csv').open('w',newline='') as resource:
            writer=csv.DictWriter(resource,fieldnames=['utc','elapsed_seconds','rss_bytes','disk_free_bytes','pressure_level','swap_used_bytes']);writer.writeheader()
            proc=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            ledger['active']={'pid':proc.pid,'directory':dest.name,'started_utc':now()};save(out/'budget.json',ledger)
            next_system=0;system={}
            while proc.poll() is None:
                elapsed=time.monotonic()-start;ledger.update(used_seconds=used_before+elapsed,updated_utc=now());save(out/'budget.json',ledger)
                rss=memory_sample(proc.pid);peak=max(peak,rss or 0)
                if elapsed>=next_system:
                    system=system_sample();history.append((elapsed,system['swap_used_bytes']))
                    reason,critical=resource_reason(system,history,critical,elapsed);next_system=elapsed+60
                writer.writerow({'utc':now(),'elapsed_seconds':round(elapsed,3),'rss_bytes':rss,**system});resource.flush()
                if ledger['used_seconds']>=ledger['limit_seconds']:reason='shared_budget_exhausted'
                if reason:
                    stop_group(proc,min(60,max(0,ledger['limit_seconds']-ledger['used_seconds'])));break
                try:proc.wait(timeout=min(10,max(.001,ledger['limit_seconds']-ledger['used_seconds'])))
                except subprocess.TimeoutExpired:pass
            proc.wait()
    except BaseException:
        if proc is not None and proc.poll() is None:stop_group(proc,min(60,max(0,ledger['limit_seconds']-used_before-(time.monotonic()-start))))
        reason='executor_interrupted';raise
    finally:
        ledger.update(used_seconds=used_before+time.monotonic()-start,active=None,updated_utc=now());save(out/'budget.json',ledger)
        attempt.update(elapsed_seconds=time.monotonic()-start,ended_utc=now(),sampled_peak_group_rss_bytes=peak,exit_code=proc.returncode if proc else None,status='interrupted',reason=reason)
        save(out/'run_manifest.json',manifest)
    log=(dest/'run.log').read_text(errors='replace')
    ended=all(f'ITERATION {i} ENDS' in log for i in range(iterations))
    shutdown='shutdown completed' in log.lower()
    files=list((dest/'simulation').glob('*output_config*'))
    events=all(list((dest/'simulation/ITERS'/f'it.{i}').glob('*.events.xml*')) for i in range(iterations))
    success=proc.returncode==0 and ended and shutdown and bool(files) and events
    attempt.update(status='complete' if success else 'interrupted' if reason else 'failed',iteration_end_evidence=ended,normal_shutdown=shutdown,effective_config_present=bool(files),events_present=events,
        java_heap_oom=('OutOfMemoryError: Java heap space' in log or 'OutOfMemoryError: GC overhead limit exceeded' in log))
    save(out/'run_manifest.json',manifest);print(json.dumps(attempt,ensure_ascii=False),flush=True)
    return attempt

def execute(out):
    lock=(out/'executor.lock').open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Another executor owns this diagnostic')
    manifest=json.loads((out/'run_manifest.json').read_text());ledger=json.loads((out/'budget.json').read_text())
    if ledger['active']:raise SystemExit('Unclean prior executor termination: reconcile active PID and budget before resuming')
    env=json.loads((ROOT/'.tools/environment.json').read_text());java=Path(env['java_home'])/'bin/java'
    if not (out/'runner.jar').exists():shutil.copy2(ROOT/'target/matsim-nyc-modernized-1.0.0.jar',out/'runner.jar')
    for name in ['build.log','build-status.json','verify.log','verify-status.json','environment.json','jdk.sha256','maven.sha512']:
        if (ROOT/'.tools'/name).exists():shutil.copy2(ROOT/'.tools'/name,out/name)
    for name in ['build-status.json','verify-status.json']:
        if json.loads((out/name).read_text())['exit_code']!=0:raise SystemExit('Build/regression gate failed: '+name)
    source_dir=out/'executed-scripts';source_dir.mkdir(exist_ok=True)
    for p in (ROOT/'scripts').glob('*.py'):shutil.copy2(p,source_dir/p.name)
    manifest.update(java=command([str(java),'-version']).strip(),toolchain=env,runner_sha256=sha(out/'runner.jar'),status='running')
    save(out/'run_manifest.json',manifest)
    heap='16g'
    for stage,iterations in [('smoke',1),('five',5)]:
        completed=next((a for a in manifest['attempts'] if a['stage']==stage and a['status']=='complete'),None)
        if completed:heap=completed['heap'];continue
        prior=[a for a in manifest['attempts'] if a['stage']==stage]
        if prior:raise SystemExit('Failed/interrupted stage retained; inspect before explicitly creating any further attempt')
        attempt=run_attempt(out,stage,iterations,heap,manifest,ledger,java)
        if attempt.get('java_heap_oom') and not attempt.get('reason') and heap=='16g':
            sample=system_sample()
            if sample['pressure_level']==1 and sample['disk_free_bytes']>=30*GIB and ledger['used_seconds']<ledger['limit_seconds']:
                heap='24g';attempt=run_attempt(out,stage,iterations,heap,manifest,ledger,java)
        if attempt['status']!='complete':break
    manifest['status']='complete' if all(any(a['stage']==s and a['status']=='complete' for a in manifest['attempts']) for s in ['smoke','five']) else 'incomplete'
    save(out/'run_manifest.json',manifest)

def build():
    tools=ROOT/'.tools';e=json.loads((tools/'environment.json').read_text())
    env=os.environ.copy();env['JAVA_HOME']=e['java_home'];env['PATH']=e['java_home']+'/bin:'+env.get('PATH','')
    commands=[('build',[e['maven'],'-B','-DskipTests','package']),('verify',[sys.executable,str(ROOT/'scripts/verify.py')])]
    for label,cmd in commands:
        start=time.monotonic()
        with (tools/(label+'.log')).open('w') as log:
            result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        save(tools/(label+'-status.json'),{'exit_code':result.returncode,'seconds':time.monotonic()-start,'command':cmd,'finished_utc':now()})
        if result.returncode:raise SystemExit(label+' failed; inspect '+str(tools/(label+'.log')))
    print('Build and regression checks passed.',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-only',action='store_true');p.add_argument('--prepare-only',action='store_true');p.add_argument('--run-dir',type=Path);p.add_argument('--analyze-only',action='store_true');p.add_argument('--budget-hours',type=float,default=8)
    args=p.parse_args()
    if args.build_only:
        build();return
    if not 0<args.budget_hours<=8:p.error('Budget must be positive and at most eight hours')
    if args.analyze_only and not args.run_dir:p.error('--analyze-only requires --run-dir')
    out=args.run_dir.resolve() if args.run_dir else prepare(args.budget_hours)
    if args.prepare_only:return
    if not args.analyze_only:execute(out)
    subprocess.run([sys.executable,str(ROOT/'scripts/analyze_baseline_diagnostic.py'),str(out)],check=True)
if __name__=='__main__':main()

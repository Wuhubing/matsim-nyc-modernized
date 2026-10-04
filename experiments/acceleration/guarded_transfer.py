#!/usr/bin/env python3
"""Optional follow-up: transfer only groups allowed to innovate, same budget ledger."""
import collections,fcntl,gzip,json,shutil,sys,time
from pathlib import Path
import xml.etree.ElementTree as E
import pilot

def persons(path):
    with pilot.stream(path) as f:
        it=E.iterparse(f,events=('start','end'));_,root=next(it)
        for event,p in it:
            if event=='end' and p.tag=='person':yield p;root.remove(p)

def transfer(cold,warm,target):
    fixed={}
    for p in persons(cold):
        if p.find("attributes/attribute[@name='subpopulation']").text!='outside':continue
        selected=p.find("plan[@selected='yes']")
        if selected is None:raise ValueError('Missing selected cold plan')
        for plan in p.findall('plan'):
            if plan is not selected:p.remove(plan)
        selected.attrib.pop('score',None)
        fixed[p.get('id')]=E.tostring(p,encoding='unicode')
    count=0;replaced=set();groups=collections.Counter()
    with gzip.open(target,'wt') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE population SYSTEM "http://www.matsim.org/files/dtd/population_v6.dtd">\n<population>\n')
        for p in persons(warm):
            pid=p.get('id');group=p.find("attributes/attribute[@name='subpopulation']").text
            if group=='outside':
                if pid not in fixed or pid in replaced:raise ValueError('Fixed population mismatch')
                f.write(fixed[pid]);replaced.add(pid)
            else:f.write(E.tostring(p,encoding='unicode'))
            groups[group]+=1;count+=1
        f.write('</population>\n')
    if replaced!=set(fixed):raise ValueError('Incomplete fixed-group transfer')
    return {'persons':count,'replaced_with_cold':len(replaced),'groups':dict(groups),'output_sha256':pilot.D.sha(target)}

def run(out):
    with (out/'executor.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=json.loads((out/'run_manifest.json').read_text());b=json.loads((out/'budget.json').read_text())
        if b['active'] or m['status']!='simulations_complete':raise ValueError('Initial pilot must be complete')
        arm='guarded_warm_latest'
        if any(a['stage']==arm for a in m['attempts']):raise ValueError('Follow-up already attempted; no automatic retry')
        if b['limit_seconds']-b['used_seconds']<2400:raise ValueError('Insufficient remaining shared budget')
        diagnostic=json.loads((out/'transfer-diagnostic.json').read_text())
        if diagnostic['arms']['warm_latest']['final_car_route_signatures_different_from_cold']==0:raise ValueError('No demonstrated fixed-group route difference; follow-up not justified')
        hashes=json.loads((out/'prepared-hashes.json').read_text())
        for rel,digest in hashes.items():
            if pilot.D.sha(out/rel)!=digest:raise ValueError('Prepared input changed')
        start=time.monotonic();target=out/'inputs'/f'{arm}.xml.gz'
        if target.exists():raise ValueError('Follow-up input already exists; inspect rather than overwrite')
        cold_attempt=next(a for a in m['attempts'] if a['stage']=='cold' and a['status']=='complete')
        cold_prepared=next((out/cold_attempt['directory']/'simulation/ITERS/it.0').glob('*.plans.xml*'))
        inventory=transfer(cold_prepared,out/'inputs/warm_latest.xml.gz',target)
        if inventory['persons']!=389301 or inventory['replaced_with_cold']!=60203:raise ValueError('Population size changed')
        inventory.update(preparation_seconds=time.monotonic()-start,source='warm_latest selected plans except outside group restored from cold pre-mobsim iteration-0 prepared plans',background_source=str(cold_prepared),background_source_sha256=pilot.D.sha(cold_prepared),requires_target_background_routing_preparation=True,exploratory_posthoc=True)
        hashes[str(target.relative_to(out))]=inventory['output_sha256'];pilot.D.save(out/'prepared-hashes.json',hashes)
        m['arms'].append(arm);m['initialization'][arm]=inventory;m['status']='running_guarded'
        m['guarded_followup_reason']='Observed persistent outside-group route differences; preserve cold background and transfer only innovating groups. Exploratory follow-up, same 4-hour ledger.'
        pilot.D.save(out/'run_manifest.json',m)
        shutil.copy2(Path(__file__),out/'code/guarded_transfer.py')
        env=json.loads((pilot.ROOT/'.tools/environment.json').read_text())
        pilot.D.generate_config=pilot.config
        attempt=pilot.D.run_attempt(out,arm,m['iterations'],'16g',m,b,Path(env['java_home'])/'bin/java')
        if attempt['status']!='complete':raise RuntimeError('Guarded follow-up stopped')
        m['status']='simulations_complete';pilot.D.save(out/'run_manifest.json',m)
    pilot.summarize(out)
if __name__=='__main__':run(Path(sys.argv[1]).resolve())

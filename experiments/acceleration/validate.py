#!/usr/bin/env python3
"""Check executed configs and reconcile offline event counts with engine tables."""
import json,sys
from pathlib import Path
import xml.etree.ElementTree as E
import pilot

def validate(out):
    m=json.loads((out/'run_manifest.json').read_text());b=json.loads((out/'budget.json').read_text())
    configs=[];checks=[]
    for a in m['attempts']:
        if a['status']!='complete':raise ValueError('Incomplete attempt')
        dest=out/a['directory'];root=E.parse(dest/'simulation/BUILT.output_config.xml').getroot()
        seen={}
        for mod in root.findall('module'):
            for p in mod.findall('param'):
                k=p.get('name')
                if k=='inputPlansFile':
                    assert Path(p.get('value')).resolve()==out/'inputs'/f"{a['stage']}.xml.gz"
                    p.set('value','ARM_SPECIFIC');seen['plans']=True
                if k=='outputDirectory':p.set('value','ARM_SPECIFIC');seen['output']=True
        assert seen=={'plans':True,'output':True}
        configs.append(E.tostring(root))
        event_files=list(dest.glob('event-metrics-*.json'))
        expected=set(range(max(0,m['iterations']-3),m['iterations']))
        observed={json.loads(p.read_text())['iteration'] for p in event_files}
        assert expected.issubset(observed),'Missing tail event analysis'
        for p in event_files:
            r=json.loads(p.read_text());i=r['iteration'];h=pilot.table(dest/f'simulation/ITERS/it.{i}/BUILT.{i}.legHistogram.txt')
            assert r['errors']=={} and r['xml_closed']
            audit=next(x for x in pilot.table(dest/'simulation/pricing-audit.csv') if int(x['iteration'])==i)
            assert abs(float(audit['sample_revenue_usd'])-r['net_congestion_revenue'])<.011
            assert sum(float(x['stuck_all']) for x in h)==r['unfinished_all']
            for mode,n in r['departures'].items():assert sum(float(x['departures_'+mode]) for x in h)==n
            for mode,n in r['completed'].items():assert sum(float(x['arrivals_'+mode]) for x in h)==n
        checks.append({'arm':a['stage'],'effective_config_checked':True,'events_reconciled':len(list(dest.glob('event-metrics-*.json')))})
    if len(configs)!=len(m['arms']):raise ValueError('Missing declared arms')
    assert not b['active'],'Simulation still active'
    assert b['used_seconds']<=b['limit_seconds'],'Simulation budget exceeded'
    assert len(set(configs))==1,'Effective configs differ beyond plans/output'
    for rel,digest in json.loads((out/'prepared-hashes.json').read_text()).items():assert pilot.D.sha(out/rel)==digest
    for item in m['input_inventory']:assert pilot.D.sha(Path(item['path']))==item['sha256']
    transfer_path=out/'transfer-diagnostic.json'
    if transfer_path.exists():
        transfer=json.loads(transfer_path.read_text())['arms']
        assert set(transfer)==set(m['arms']),'Transfer audit does not cover every arm'
        assert all(t['prepared_person_attribute_differences_from_cold']==0 for t in transfer.values()),'Prepared person attributes differ'
        if 'guarded_warm_latest' in transfer:
            guarded=transfer['guarded_warm_latest']
            assert guarded['initial_car_route_signatures_different_from_cold']==0,'Guard did not preserve target background routes'
            assert guarded['final_car_route_signatures_different_from_cold']==0,'Guarded background routes diverged'
    # Wall-clock accounting includes process termination overhead; no budget reset.
    result={'arms':checks,'effective_configs_match_except_plans_and_output':True,'inputs_preserved':True,'budget_active':b['active'],'budget_used_seconds':b['used_seconds'],'budget_limit_seconds':b['limit_seconds']}
    pilot.D.save(out/'validation.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':validate(Path(sys.argv[1]).resolve())

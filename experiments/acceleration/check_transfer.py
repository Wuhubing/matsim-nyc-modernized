#!/usr/bin/env python3
"""Compare road-route signatures of the noninnovating outside group."""
import hashlib,json,sys
from pathlib import Path
import xml.etree.ElementTree as E
import pilot

def signatures(path):
    result={};car_people=set();attributes={}
    with pilot.stream(path) as f:
        it=E.iterparse(f,events=('start','end'));_,root=next(it)
        for event,p in it:
            if event!='end' or p.tag!='person':continue
            attrs=[]
            for node in p.findall('attributes/attribute'):
                text=(node.text or '').strip()
                try:text=json.dumps(json.loads(text),sort_keys=True)
                except (ValueError,TypeError):pass
                attrs.append((node.get('name'),node.get('class'),text))
            attributes[p.get('id')]=hashlib.sha256(json.dumps(sorted(attrs)).encode()).hexdigest()
            a=p.find("attributes/attribute[@name='subpopulation']")
            if a is not None and a.text=='outside':
                plan=p.find("plan[@selected='yes']")
                if plan is None:raise ValueError('Missing selected plan')
                routes=[]
                for leg in plan.findall('leg'):
                    if leg.get('mode')!='car':continue
                    r=leg.find('route')
                    if r is None:raise ValueError('Prepared car leg lacks route')
                    routes.append((r.get('type'),r.get('start_link'),r.get('end_link'),' '.join((r.text or '').split())))
                pid=p.get('id');result[pid]=hashlib.sha256(json.dumps(routes).encode()).hexdigest()
                if routes:car_people.add(pid)
            root.remove(p)
    return result,car_people,attributes

def main(out):
    m=json.loads((out/'run_manifest.json').read_text());initial={};final={};people={};attributes={}
    for a in m['attempts']:
        if a['status']!='complete':raise ValueError('Wait for completed simulations')
        sim=out/a['directory']/'simulation';arm=a['stage']
        initial[arm],people[arm],attributes[arm]=signatures(next((sim/'ITERS/it.0').glob('*.plans.xml*')))
        final[arm],_,_=signatures(next(sim.glob('*.output_plans.xml*')))
    result={'group':'outside','definition':'person-level hash of selected-plan car route type, endpoints and normalized link sequence; no score or travel-time fields','arms':{}}
    for arm in initial:
        if set(initial[arm])!=set(initial['cold']):raise ValueError('Group membership differs')
        result['arms'][arm]={'prepared_person_attribute_differences_from_cold':sum(attributes[arm][p]!=attributes['cold'][p] for p in attributes['cold']),'persons':len(initial[arm]),'persons_with_car':len(people[arm]),
          'initial_car_route_signatures_different_from_cold':sum(initial[arm][p]!=initial['cold'][p] for p in initial[arm]),
          'car_route_signatures_changed_during_target_run':sum(initial[arm][p]!=final[arm][p] for p in initial[arm]),
          'final_car_route_signatures_different_from_cold':sum(final[arm][p]!=final['cold'][p] for p in final[arm])}
    pilot.D.save(out/'transfer-diagnostic.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())

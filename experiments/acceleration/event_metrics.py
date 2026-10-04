#!/usr/bin/env python3
"""Offline event metrics; censored waits retained, completed-leg means labeled."""
import argparse, collections, csv, json, re, time
from pathlib import Path
import pilot
ATTR=re.compile(rb'(\w+)="([^"]*)"')

def measure(path,people,entries,cutoff=108000):
    active={};waiting={};drivers={};departures=collections.Counter();completed=collections.Counter();stuck=collections.Counter()
    durations=collections.Counter();crossings=collections.Counter();wait_seconds=0.;wait_count=0;closed=False;net_revenue=0.;errors=collections.Counter()
    relevant={b'departure',b'arrival',b'stuckAndAbort',b'waitingForPt',b'PersonEntersPtVehicle',b'vehicle enters traffic',b'vehicle leaves traffic',b'entered link',b'personMoney'}
    with pilot.stream(path) as f:
        for line in f:
            if b'</events>' in line:closed=True
            at=line.find(b'type="')
            if at<0:continue
            typ=line[at+6:line.find(b'"',at+6)]
            if typ not in relevant:continue
            if typ==b'entered link':
                link=line.split(b'link="',1)[1].split(b'"',1)[0]
                if link not in entries:continue
            e=dict(ATTR.findall(line));p=e.get(b'person');v=e.get(b'vehicle');t=float(e[b'time'])
            if typ==b'vehicle enters traffic':
                if p in people and e.get(b'networkMode')==b'car':drivers[v]=p
            elif typ==b'vehicle leaves traffic':drivers.pop(v,None)
            elif typ==b'entered link':
                if v in drivers:crossings[int(t//3600)]+=1
            elif p in people:
                if typ==b'departure':
                    if p in active:errors['overlapping_departures']+=1
                    mode=e[b'legMode'].decode();active[p]=(t,mode);departures[mode]+=1
                elif typ==b'arrival':
                    if p not in active:errors['unmatched_arrivals']+=1;continue
                    start,mode=active.pop(p)
                    if mode!=e[b'legMode'].decode():errors['arrival_mode_mismatch']+=1
                    completed[mode]+=1;durations[mode]+=t-start
                elif typ==b'waitingForPt':
                    if p in waiting:errors['overlapping_waits']+=1
                    waiting[p]=t;wait_count+=1
                elif typ==b'PersonEntersPtVehicle':
                    if p not in waiting:errors['boarding_without_wait']+=1
                    else:wait_seconds+=t-waiting.pop(p)
                elif typ==b'stuckAndAbort':stuck[e[b'legMode'].decode()]+=1
                elif typ==b'personMoney' and e.get(b'purpose')==b'toll':net_revenue-=float(e[b'amount'])
    unfinished=collections.Counter(mode for _,mode in active.values())
    wait_seconds+=sum(max(0,cutoff-t) for t in waiting.values())
    if not closed:errors['unclosed_xml']+=1
    if unfinished!=stuck:errors['stuck_active_mismatch']+=1
    if any(p not in active or active[p][1]!='pt' for p in waiting):errors['waiting_not_active_pt']+=1
    if any(departures[k]!=completed[k]+unfinished[k] for k in departures):errors['leg_conservation']+=1
    return {'departures':dict(departures),'completed':dict(completed),'unfinished':dict(unfinished),'unfinished_all':len(active),
      'mean_completed_car_leg_seconds':durations['car']/completed['car'] if completed['car'] else None,
      'censored_wait_person_hours':wait_seconds/3600,'waiting_segments_started':wait_count,'waiting_at_cutoff':len(waiting),
      'private_car_entry_crossings':sum(crossings.values()),'private_car_entries_by_hour':dict(crossings),
      'net_congestion_revenue':net_revenue,'errors':dict(errors),'xml_closed':closed}

def main():
    p=argparse.ArgumentParser();p.add_argument('run_dir',type=Path);p.add_argument('--tail',type=int,default=3);a=p.parse_args();out=a.run_dir.resolve()
    people=set()
    import xml.etree.ElementTree as E
    with pilot.stream(out/'inputs/cold.xml.gz') as f:
        it=E.iterparse(f,events=('start','end'));_,root=next(it)
        for ev,e in it:
            if ev=='end' and e.tag=='person':people.add(e.get('id').encode());root.remove(e)
    entries={r['id'].encode() for r in csv.DictReader((pilot.ROOT/'scenarios/nyc-2025/links.csv').open()) if r['entry']=='1'}
    m=json.loads((out/'run_manifest.json').read_text());results=[]
    for attempt in m['attempts']:
        if attempt['status']!='complete':continue
        for i in range(max(0,m['iterations']-a.tail),m['iterations']):
            dest=out/attempt['directory']/f'event-metrics-{i}.json'
            path=next((out/attempt['directory']/f'simulation/ITERS/it.{i}').glob('*.events.xml*'))
            identity={'path':str(path),'bytes':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns}
            if dest.exists():
                value=json.loads(dest.read_text())
                if value['source']!=identity:raise ValueError('Cached event input changed')
            else:
                start=time.monotonic();value=dict(arm=attempt['stage'],iteration=i,source=identity,**measure(path,people,entries));value['analysis_seconds']=time.monotonic()-start
                pilot.D.save(dest,value)
            if value['errors']:raise ValueError('Event consistency failed: '+str(value['errors']))
            results.append(value);print(attempt['stage'],i,value['unfinished_all'],flush=True)
    pilot.D.save(out/'event-metrics.json',results)
if __name__=='__main__':main()

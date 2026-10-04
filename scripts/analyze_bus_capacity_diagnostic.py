#!/usr/bin/env python3
"""Population-wide paired leg, daily completion and censored waiting analysis."""
import collections as C,csv,gzip,html,json,sys,time,bisect,statistics,xml.etree.ElementTree as E
from pathlib import Path
from analyze_baseline_diagnostic import stream,ATTR
from run_bus_capacity_diagnostic import vehicle_data
import run_baseline_diagnostic as D

def writecsv(path,rows):
 rows=list(rows)
 if not rows:return
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with path.open('w') as f:w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rows)
def compatible(route_stops,index,destination):return destination in route_stops[index+1:]
def analyze(out,arm,meta,targets):
 m=json.load(open(out/'run_manifest.json'));attempt=[a for a in m['attempts'] if a['stage']==arm and a['status']=='complete'][-1];dest=out/attempt['directory'];sim=dest/'simulation';start=time.time()
 veh=vehicle_data(sim/'BUILT.output_transitVehicles.xml.zst');caps={e.get('id'):int(e.find('capacity').get('seats'))+int(e.find('capacity').get('standingRoomInPersons')) for e in veh.findall('vehicleType')};vc={e.get('id'):caps[e.get('type')] for e in veh.findall('vehicle')};control=vehicle_data(out/'common/control-vehicles.xml.gz');cc={e.get('id'):int(e.find('capacity').get('seats'))+int(e.find('capacity').get('standingRoomInPersons')) for e in control.findall('vehicleType')};oldcap={e.get('id'):cc[e.get('type')] for e in control.findall('vehicle')}
 schedule=E.parse(gzip.open(out/'common/schedule.xml.gz')).getroot();routes={};rmode={}
 for l in schedule.findall('transitLine'):
  for r in l.findall('transitRoute'):
   k=(l.get('id'),r.get('id'));routes[k]=[s.get('refId') for s in r.findall('routeProfile/stop')];rmode[k]=r.findtext('transportMode')
 active={};ordinal=C.Counter();completed=C.Counter();actindex=C.Counter();wait={};wait_total=C.Counter();wait_n=C.Counter();wait_bins=C.defaultdict(lambda:[0,0.,0]);boarded_wait=[];vehicle={};vindex={};occupancy=C.Counter();visits=C.defaultdict(list);target_state={(p,j):{'person':p,'leg':j,'started':False,'boarded':False,'completed':False} for p,js in targets.items() for j in js};stuck=set();daily=set();errors=C.Counter();above_old=set();service_count=0;seq=0;closed=False
 wanted={b'departure',b'arrival',b'actstart',b'waitingForPt',b'PersonEntersPtVehicle',b'PersonLeavesPtVehicle',b'PersonEntersVehicle',b'PersonLeavesVehicle',b'TransitDriverStarts',b'VehicleDepartsAtFacility',b'stuckAndAbort'}
 def finish_wait(p,t,boarded):
  w=wait.pop(p);d=t-w['time'];assert d>=0;wait_total[p]+=d;k=(meta[p]['group'],w['mode'],int(w['time']//3600));wait_bins[k][1]+=d
  if boarded:boarded_wait.append(d);wait_bins[k][2]+=1
 def event_target(p):return target_state.get((p,ordinal[p]))
 with stream(sim/'ITERS/it.0/BUILT.0.events.xml.zst') as f:
  for raw in f:
   seq+=1
   if b'</events>' in raw:closed=True
   at=raw.find(b'type="');typ=raw[at+6:raw.find(b'"',at+6)] if at>=0 else b''
   if typ not in wanted:continue
   e={k.decode():html.unescape(v.decode()) for k,v in ATTR.findall(raw)};typ=e['type'];p=e.get('person',e.get('agent'));v=e.get('vehicle',e.get('vehicleId'));t=float(e['time'])
   if typ=='TransitDriverStarts':vehicle[v]=(e['transitLineId'],e['transitRouteId']);vindex[v]=-1
   if typ in ['PersonEntersVehicle','PersonEntersPtVehicle'] and p in meta and v in vc:
    occupancy[v]+=1
    if occupancy[v]>vc[v]:errors['over_capacity']+=1
    if occupancy[v]>oldcap[v]:above_old.add(v)
   if typ in ['PersonLeavesVehicle','PersonLeavesPtVehicle'] and p in meta and v in vc:
    occupancy[v]-=1
    if occupancy[v]<0:errors['negative_occupancy']+=1
   if typ=='VehicleDepartsAtFacility' and v in vehicle:
    line,route=vehicle[v];profile=routes[(line,route)];stop=e['facility']
    try:idx=profile.index(stop,vindex[v]+1)
    except ValueError:idx=profile.index(stop)
    vindex[v]=idx;visits[(line,stop)].append((t,seq,route,idx,occupancy[v],vc[v],v));service_count+=1
   if p not in meta:continue
   target=event_target(p)
   if typ=='departure':
    if p in active:errors['overlap_departure']+=1
    ordinal[p]+=1;j=ordinal[p]
    if j>len(meta[p]['modes']) or meta[p]['modes'][j-1]!=e['legMode']:errors['departure_plan_mismatch']+=1
    active[p]=dict(leg=j,mode=e['legMode'],departure=t)
    target=event_target(p)
    if target is not None:target.update(started=True,departure_s=t)
   elif typ=='waitingForPt':
    if p in wait:errors['overlap_wait']+=1
    route=meta[p]['pt'][str(ordinal[p])];mode=rmode[(route['transitLineId'],route['transitRouteId'])];wait[p]=dict(time=t,seq=seq,stop=e['atStop'],destination=e['destinationStop'],line=route['transitLineId'],mode=mode,leg=ordinal[p]);wait_n[p]+=1;wait_bins[(meta[p]['group'],mode,int(t//3600))][0]+=1
   elif typ=='PersonEntersPtVehicle':
    if p not in wait:errors['boarding_without_wait']+=1
    else:finish_wait(p,t,True)
    if target is not None:target.update(boarded=True,boarding_s=t,vehicle=v)
   elif typ=='arrival':
    if p not in active:errors['unmatched_arrival']+=1
    else:active.pop(p);completed[p]+=1
    if target is not None:target.update(completed=True,arrival_s=t)
   elif typ=='actstart':
    actindex[p]+=1;k=actindex[p];acts=meta[p]['activities']
    if k>=len(acts) or acts[k]!=e['actType']:errors['activity_plan_mismatch']+=1
    elif k==len(acts)-1 and not acts[k].endswith(' interaction'):daily.add(p)
   elif typ=='stuckAndAbort':stuck.add(p)
 assert closed and set(active)==stuck
 assert not errors,dict(errors)
 waiting=dict(wait);service=[];new={}
 for p,w in waiting.items():
  vs=visits.get((w['line'],w['stop']),[]);pos=bisect.bisect_left(vs,(w['time'],));eligible=[x for x in vs[pos:] if compatible(routes[(w['line'],x[2])],x[3],w['destination'])];full=[x for x in eligible if x[4]==x[5]];spare=[x for x in eligible if x[4]<x[5]]
  category='no_compatible_service' if not eligible else 'all_full' if len(full)==len(eligible) else 'same_second_boundary' if all(x[0]==w['time'] for x in spare) else 'spare_capacity_unexplained'
  if category=='all_full':new[p]=w['leg']
  service.append(dict(person=p,leg=w['leg'],mode=w['mode'],line=w['line'],stop=w['stop'],wait_start_s=w['time'],compatible=len(eligible),full=len(full),category=category));finish_wait(p,108000,False)
 population=[]
 for p,x in meta.items():
  population.append(dict(person=p,group=x['group'],departed_legs=ordinal[p],completed_legs=completed[p],unstarted_legs=len(x['modes'])-ordinal[p],final_activity_reached=p in daily,no_planned_travel=not x['modes'],active_mode=active[p]['mode'] if p in active else '',waiting=p in waiting,wait_segments=wait_n[p],wait_seconds=wait_total[p]))
 for (p,j),a in target_state.items():a.update(final_activity_reached=p in daily,cutoff_waiting=p in waiting,active_leg=active[p]['leg'] if p in active else '',active_mode=active[p]['mode'] if p in active else '',wait_seconds_person=wait_total[p])
 # New control labels are selected after this run, so their target legs are known unfinished and waiting.
 for p,j in new.items():
  if (p,j) not in target_state:target_state[(p,j)]=dict(person=p,leg=j,started=True,boarded=False,completed=False,final_activity_reached=p in daily,cutoff_waiting=True,active_leg=j,active_mode='pt',wait_seconds_person=wait_total[p])
 writecsv(dest/'person-results.csv',population);writecsv(dest/'target-results.csv',target_state.values());writecsv(dest/'waiting-service.csv',service);writecsv(dest/'waiting-by-group-mode-hour.csv',[dict(group=g,mode=mo,departure_hour=h,started_wait_segments=v[0],wait_person_hours=v[1]/3600,boarded_segments=v[2]) for (g,mo,h),v in sorted(wait_bins.items())]);D.save(dest/'new-full-cohort.json',new)
 boarded_wait.sort();quant=lambda q:boarded_wait[round(q*(len(boarded_wait)-1))] if boarded_wait else None
 result=dict(persons=len(meta),daily_completed=len(daily),daily_not_completed=sum(bool(x['modes']) and p not in daily for p,x in meta.items()),no_planned_travel=sum(not x['modes'] for x in meta.values()),active_legs=len(active),active_modes=dict(C.Counter(x['mode'] for x in active.values())),waiting_persons=len(waiting),waiting_modes=dict(C.Counter(x['mode'] for x in waiting.values())),wait_person_hours=sum(wait_total.values())/3600,started_wait_segments=sum(wait_n.values()),boarded_wait_segments=len(boarded_wait),conditional_boarded_wait_seconds=dict(mean=sum(boarded_wait)/len(boarded_wait),p50=quant(.5),p90=quant(.9),p99=quant(.99)),not_started_persons=sum(ordinal[p]==0 and bool(x['modes']) for p,x in meta.items()),unstarted_legs=sum(len(x['modes'])-ordinal[p] for p,x in meta.items()),service_categories=dict(C.Counter(x['category'] for x in service)),new_all_full=len(new),vehicles_observed_above_control_capacity=len(above_old),capacity_errors=dict(errors),analysis_seconds=time.time()-start)
 D.save(dest/'analysis.json',result);print(arm,result,flush=True);return dest,new

def main(out):
 meta={x['person']:x for line in gzip.open(out/'common/plan-index.jsonl.gz','rt') if (x:=json.loads(line))};original=json.load(open(out/'original-cohort.json'));targets={p:{j} for p,j in original.items()};control,new=analyze(out,'control',meta,targets)
 for p,j in new.items():targets.setdefault(p,set()).add(j)
 treatment,_=analyze(out,'treatment',meta,targets)
 summaries={arm:json.load(open(dest/'analysis.json')) for arm,dest in [('control',control),('treatment',treatment)]};results={arm:{(r['person'],int(r['leg'])):r for r in csv.DictReader(open(dest/'target-results.csv'))} for arm,dest in [('control',control),('treatment',treatment)]}
 rows=[]
 for label,cohort in [('original',original),('new_control_all_full',new)]:
  for metric in ['started','boarded','completed','final_activity_reached']:
   counts={arm:sum(results[arm][(p,j)][metric]=='True' for p,j in cohort.items()) for arm in results};rows.append(dict(cohort=label,metric=metric,**counts,difference=counts['treatment']-counts['control']))
 for metric in ['waiting_persons','wait_person_hours','started_wait_segments','active_legs','daily_not_completed','not_started_persons','unstarted_legs']:
  c=summaries['control'][metric];t=summaries['treatment'][metric];rows.append(dict(cohort='all_population',metric=metric,control=c,treatment=t,difference=t-c))
 writecsv(out/'comparison.csv',rows);D.save(out/'comparison.json',dict(metrics=rows,original_count=len(original),new_control_count=len(new),overlap_same_person_leg=sum(new.get(p)==j for p,j in original.items()),exited_original=sum(new.get(p)!=j for p,j in original.items()),new_labels=sum(original.get(p)!=j for p,j in new.items())))
 paired=[]
 for label,cohort in [('original',original),('new_control_all_full',new)]:
  for p,j in cohort.items():
   c=results['control'][(p,j)];t=results['treatment'][(p,j)];paired.append(dict(cohort=label,person=p,leg=j,**{'control_'+k:v for k,v in c.items() if k not in ['person','leg']},**{'treatment_'+k:v for k,v in t.items() if k not in ['person','leg']}))
 writecsv(out/'paired-targets.csv',paired)
if __name__=='__main__':main(Path(sys.argv[1]).resolve())

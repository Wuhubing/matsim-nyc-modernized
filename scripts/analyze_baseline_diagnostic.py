#!/usr/bin/env python3
"""Offline, streaming baseline diagnostics. No simulation or billing state changes."""
import collections, csv, datetime, gzip, html, io, json, re, sys, shutil, time
from pathlib import Path
import xml.etree.ElementTree as ET
from run_baseline_diagnostic import ROOT, save

ATTR=re.compile(rb'([\w]+)="([^"]*)"')
LEGACY=(ROOT/'src/main/java/org/c2smart/matsimnyc/LegacyCosts.java').read_text()
UTILITY=float(re.search(r'MONEY_UTILITY\s*=\s*([\d.]+)',LEGACY)[1])
def toll_set(name):return set(re.findall(r'"([^"]+)"',re.search(name+r' = Set.of\((.*?)\);',LEGACY,re.S)[1]))
PANYNJ=toll_set('PANYNJ');MTA=toll_set('MTA')
def dollar_rate(link,t):
    if link in MTA:return 6.12
    # ZIP-aligned behavior: after midnight remains off-peak.
    return 12.5 if 6*3600<=t<10*3600 or 16*3600<=t<20*3600 else 10.5

def stream(path):
    if path.suffix=='.zst':
        import zstandard
        return io.BufferedReader(zstandard.open(path,'rb'))
    if path.suffix=='.gz':return gzip.open(path,'rb')
    return path.open('rb')

def population():
    result={}
    with gzip.open(ROOT/'scenarios/nyc/population-v6.xml.gz','rb') as f:
        ctx=ET.iterparse(f,events=('start','end'));_,root=next(ctx)
        for event,e in ctx:
            if event=='end' and e.tag=='person':
                a=e.find("attributes/attribute[@name='subpopulation']")
                result[e.get('id')]=a.text if a is not None else '<missing>'
                root.remove(e)
    return result

def analyze_events(path,people,selected,trace_path):
    drivers={};vehicle_info={};departing={};completed=collections.Counter();departures=collections.Counter();stuck=collections.Counter();stuck_ids=set();durations=collections.Counter()
    expected=collections.Counter();actual=collections.Counter();types=collections.Counter();kind_counts=collections.Counter();kind_scores=collections.Counter()
    toll_drivers=set();car_drivers=set();unknown_toll=collections.Counter();unknown_reasons=collections.Counter();nominal=collections.Counter();credits=0.;money_events=0;missing_person_scores=0;overlapping_departures=0;unmatched_arrivals=0;closed=False
    # Correlation key is person, timestamp, kind, rounded amount, retaining multiplicities.
    # Matching is conditional on events carrying these fields; never compare entire final scores to tolls.
    wanted={b'vehicle enters traffic',b'vehicle leaves traffic',b'left link',b'departure',b'arrival',b'stuckAndAbort',b'personScore',b'personMoney'}
    with stream(path) as f,trace_path.open('w') as trace:
        for line in f:
            if b'</events>' in line:closed=True
            if b'<event ' not in line:continue
            # Skip high-volume events not relevant to attribution or trip accounting.
            at=line.find(b'type="')
            if at<0:continue
            event_type=line[at+6:line.find(b'"',at+6)]
            if event_type not in wanted:continue
            if b'type="left link"' in line:
                linkraw=line.split(b'link="',1)[1].split(b'"',1)[0].decode()
                if linkraw not in PANYNJ and linkraw not in MTA:continue
            e={k.decode():html.unescape(v.decode()) for k,v in ATTR.findall(line)};typ=e.get('type');t=float(e['time']);pid=e.get('person');vehicle=e.get('vehicle');types[typ]+=1
            if typ=='vehicle enters traffic':
                vehicle_info[vehicle]=(pid,e.get('networkMode'))
                if pid in people and e.get('networkMode') in ('car','taxi','FHV'):
                    drivers[vehicle]=pid
                    if e.get('networkMode')=='car':car_drivers.add(pid)
            elif typ=='vehicle leaves traffic':
                drivers.pop(vehicle,None);vehicle_info.pop(vehicle,None)
            elif typ=='left link':
                pid=drivers.get(vehicle)
                if pid is None:
                    unknown_toll[e['link']]+=1
                    info=vehicle_info.get(vehicle)
                    unknown_reasons['no_traffic_entry' if info is None else 'non_population_driver' if info[0] not in people else 'unsupported_mode']+=1
                else:
                    toll_drivers.add(pid);amount=dollar_rate(e['link'],t);nominal['facility']+=amount
                    expected[(pid,t,'nyc-legacy-facility-toll',round(-amount*UTILITY,9))]+=1
            elif typ=='departure' and pid in people:
                mode=e['legMode'];departures[mode]+=1
                if pid in departing:overlapping_departures+=1
                departing[pid]=(t,mode)
            elif typ=='arrival' and pid in people:
                prior=departing.pop(pid,None)
                if prior:
                    completed[prior[1]]+=1;durations[prior[1]]+=t-prior[0]
                else:unmatched_arrivals+=1
                cost={'car':5.19,'taxi':5.8,'FHV':5.25}.get(e['legMode'])
                if cost is not None:
                    nominal[e['legMode']]+=cost
                    expected[(pid,t,'nyc-legacy-'+e['legMode'],round(-cost*UTILITY,9))]+=1
            elif typ=='stuckAndAbort' and pid in people:
                stuck[e.get('legMode','<missing>')]+=1;stuck_ids.add(pid)
                # Retain departure: stuck legs are unfinished, not additional legs.
            elif typ=='personScore':
                kind=e.get('kind','<missing>');kind_counts[kind]+=1;kind_scores[kind]+=float(e['amount'])
                if kind.startswith('nyc-legacy-'):
                    if pid not in people:missing_person_scores+=1
                    actual[(pid,t,kind,round(float(e['amount']),9))]+=1
            elif typ=='personMoney' and e.get('purpose')=='toll':credits-=float(e['amount']);money_events+=1
            trace_pid=pid if pid else drivers.get(vehicle)
            if trace_pid in selected:
                trace.write(json.dumps({'attributed_person':trace_pid,**e},ensure_ascii=False)+'\n')
    if not closed:raise ValueError('Events XML has no closing tag: '+str(path))
    unmatched_expected=expected-actual;unmatched_actual=actual-expected
    case_ids=set(selected)|set(sorted(toll_drivers-selected)[:2])|set(sorted(car_drivers-toll_drivers-selected)[:2])
    cases={pid:{'subpopulation':people[pid],'observed_legacy_toll_link_leave':pid in toll_drivers,'expected':[],'observed':[]} for pid in sorted(case_ids) if pid in people}
    for label,counts in [('expected',expected),('observed',actual)]:
        for (pid,t,kind,amount),count in counts.items():
            if pid in cases:cases[pid][label].append({'time':t,'kind':kind,'utility':amount,'count':count})
    result={'selected_charge_cases':cases,'source':str(path),'source_bytes':path.stat().st_size,'source_mtime_ns':path.stat().st_mtime_ns,'overlapping_departures':overlapping_departures,'unmatched_arrivals':unmatched_arrivals,'processed_event_type_counts':dict(types),'event_filter_note':'Only listed diagnostic event types; left-link events restricted to historical toll IDs.','departures_by_mode':dict(departures),'completed_legs_by_mode':dict(completed),
        'unfinished_legs_by_mode':dict(collections.Counter(m for _,m in departing.values())),
        'mean_completed_leg_seconds_by_mode':{m:durations[m]/n for m,n in completed.items()},'stuck_events_by_mode':dict(stuck),'unique_stuck_persons':len(stuck_ids),
        'legacy_expected_triggers':sum(expected.values()),'legacy_observed_score_events':sum(actual.values()),'legacy_score_events_missing_population_person':missing_person_scores,
        'legacy_observed_by_kind':dict(kind_counts),'legacy_score_sum_by_kind':dict(kind_scores),'legacy_expected_nominal_amount_by_kind':dict(nominal),
        'legacy_unmatched_expected':sum(unmatched_expected.values()),'legacy_unmatched_actual':sum(unmatched_actual.values()),
        'legacy_unmatched_examples':{'expected':[{'key':k,'count':v} for k,v in list(unmatched_expected.items())[:10]],'actual':[{'key':k,'count':v} for k,v in list(unmatched_actual.items())[:10]]},
        'toll_link_leaves_without_population_road_driver':sum(unknown_toll.values()),'unknown_driver_categories':dict(unknown_reasons),'unknown_driver_note':'May include transit vehicles; not automatically missed road-user fees.',
        'toll_money_events':money_events,'net_added_toll_money':credits,
        'correlation':'Compare person/time/kind/rounded amount multisets, not event ordering. Matching requires emitted identifiable personScore events.',
        'utility_rule':{'source':'LegacyCosts.java','multiplier':UTILITY,'sign':'negative charge','not_welfare_conversion':True},
        'population_leg_definition':'Matched departure/arrival pairs for population persons; unfinished includes stuck departures; stages are legs, not door-to-door trips.'}
    return result,toll_drivers,car_drivers

def extract_people(source, ids, target):
    root_out=ET.Element('population',source=str(source))
    with stream(source) as f:
        ctx=ET.iterparse(f,events=('start','end'));_,root=next(ctx)
        for event,e in ctx:
            if event=='end' and e.tag=='person':
                if e.get('id') in ids:root_out.append(e)
                root.remove(e)
    ET.indent(root_out);ET.ElementTree(root_out).write(target,encoding='utf-8',xml_declaration=True)


def table(path):
    if not path:return []
    with path.open() as f:
        first=f.readline();f.seek(0)
        reader=csv.reader(f,delimiter=';' if ';' in first else '\t' if '\t' in first else ',')
        names=next(reader);seen=collections.Counter();header=[]
        for name in names:
            seen[name]+=1
            header.append(name if seen[name]==1 else name+'_duration' if name=='iteration' else name+'_'+str(seen[name]))
        return [dict(zip(header,row)) for row in reader]


def log_times(log):
    starts={};ends={};notes=[]
    for line in log.splitlines():
        if any(s in line.lower() for s in ['innovation switch','change request','setting weight','strategy with','disabled','enable','disable']):notes.append(line)
        m=re.search(r'ITERATION (\d+) (BEGINS|ENDS)',line)
        if m:
            dt=re.search(r'(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d(?:[.,]\d+)?)',line)
            if dt:
                t=datetime.datetime.fromisoformat(dt[1]+'T'+dt[2].replace(',','.')).timestamp()
                (starts if m[2]=='BEGINS' else ends)[int(m[1])]=t
    return starts,ends,notes

def main(out):
    analysis_start=time.monotonic()
    for p in [Path(__file__),ROOT/'scripts/run_baseline_diagnostic.py']:
        shutil.copy2(p,out/('analysis-source-'+p.name))
    manifest=json.loads((out/'run_manifest.json').read_text());selected_rows=json.loads((out/'diagnostic_people.json').read_text());selected={r['person_id'] for r in selected_rows}
    people=None;metrics=[];reports=[];summaries={}
    for a in manifest['attempts']:
        dest=out/a['directory'];sim=dest/'simulation';log=(dest/'run.log').read_text(errors='replace') if (dest/'run.log').exists() else ''
        starts,ends,notes=log_times(log);(dest/'strategy-evidence.txt').write_text('\n'.join(notes))
        score=table(next(sim.glob('*scorestats.csv'),None));modes=table(next(sim.glob('*modestats.csv'),None));watch=table(next(sim.glob('*stopwatch.csv'),None))
        save(dest/'basic-output-tables.json',{'scorestats':score,'modestats':modes,'stopwatch':watch})
        peak=re.search(r'(\d+)\s+maximum resident set size',log)
        process_time=re.search(r'([\d.]+) real\s+([\d.]+) user\s+([\d.]+) sys',log)
        a['process_real_seconds']=float(process_time[1]) if process_time else None
        resources=table(dest/'resources.csv') if (dest/'resources.csv').exists() else []
        a['os_peak_rss_bytes']=int(peak[1]) if peak else None
        a['output_bytes']=sum(p.stat().st_size for p in dest.rglob('*') if p.is_file())
        for it in range(a['iterations']):
            folder=sim/'ITERS'/f'it.{it}';event=next(folder.glob('*.events.xml*'),None)
            row={'stage':a['stage'],'attempt':a['directory'],'iteration':it,'completed':f'ITERATION {it} ENDS' in log,
                'iteration_wall_seconds':ends[it]-starts[it] if it in starts and it in ends else None,
                'run_pre_iteration_seconds':starts.get(0)-datetime.datetime.fromisoformat(a['started_utc']).timestamp() if 0 in starts else None,
                'run_process_real_seconds':a['process_real_seconds'],
                'run_total_seconds':a.get('elapsed_seconds'),'run_os_peak_rss_bytes':a['os_peak_rss_bytes'],'run_sampled_peak_group_rss_bytes':a.get('sampled_peak_group_rss_bytes'),
                'iteration_output_bytes':sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()) if folder.exists() else None}
            samples=[float(r['rss_bytes']) for r in resources if r.get('rss_bytes') and it in starts and it in ends and starts[it]<=datetime.datetime.fromisoformat(r['utc']).timestamp()<=ends[it]]
            row['iteration_sampled_peak_group_rss_bytes']=max(samples) if samples else None
            group_tables=[(table(p),'score_'+p.stem.split('scorestats_',1)[1]+'_') for p in sorted(sim.glob('*scorestats_*.csv'))]
            for rows,prefix in [(score,'score_'),(modes,'mode_share_'),(watch,'stopwatch_')]+group_tables:
                record=next((r for r in rows if str(r.get('iteration',r.get('Iteration','')))==str(it)),{})
                for k,v in record.items():
                    if k and k.lower()!='iteration':
                        row[prefix+k]=v
                        if prefix=='stopwatch_' and not k.startswith(('BEGIN ','END ')) and v and re.fullmatch(r'\d+:\d+:\d+(?:\.\d+)?',v):
                            h,m,sec=map(float,v.split(':'));row[prefix+k+'_seconds']=h*3600+m*60+sec
            # Avoid pretending truncated event files yield valid totals.
            if event and a['status']=='complete':
                resultpath=dest/f'iteration-{it}-events.json'
                if people is None:people=population()
                cached=json.loads(resultpath.read_text()) if resultpath.exists() else {}
                if cached.get('source_bytes')==event.stat().st_size and cached.get('source_mtime_ns')==event.stat().st_mtime_ns:
                    result=cached;tolled=set();cars=set()
                else:
                    print(f'Analyzing {a["directory"]} iteration {it}: {event.stat().st_size} compressed bytes',flush=True)
                    result,tolled,cars=analyze_events(event,people,selected,dest/f'iteration-{it}-selected-events.jsonl')
                for category,pool in [('observed toll exposure',tolled),('observed car; no legacy toll link leave',cars-tolled)]:
                    for pid in sorted(pool):
                        if len(selected)>=24:break
                        if pid not in selected:
                            selected.add(pid);selected_rows.append({'person_id':pid,'subpopulation':people[pid],'selection':'post-run: '+category,'selected_from':str(event)})
                            break
                histpath=next(folder.glob('*.legHistogram.txt'),None)
                hist=table(histpath)
                result['histogram_totals']={key:sum(int(r[key]) for r in hist) for key in ['departures_all','arrivals_all','stuck_all']} if hist else None
                if hist:
                    result['histogram_minus_event_counts']={'departures':result['histogram_totals']['departures_all']-sum(result['departures_by_mode'].values()),'arrivals':result['histogram_totals']['arrivals_all']-sum(result['completed_legs_by_mode'].values()),'stuck':result['histogram_totals']['stuck_all']-sum(result['stuck_events_by_mode'].values())}
                save(resultpath,result)
                if it in {0,a['iterations']-1}:
                    experienced=next(folder.glob('*.experienced_plans.xml*'),None)
                    if experienced:extract_people(experienced,selected,dest/f'iteration-{it}-selected-experienced-plans.xml')
                print(f'Completed event audit {a["directory"]} iteration {it}',flush=True)
                row.update(completed_legs=sum(result['completed_legs_by_mode'].values()),unfinished_legs=sum(result['unfinished_legs_by_mode'].values()),stuck_events=sum(result['stuck_events_by_mode'].values()),unique_stuck_persons=result['unique_stuck_persons'],legacy_expected=result['legacy_expected_triggers'],legacy_observed=result['legacy_observed_score_events'],legacy_unmatched_expected=result['legacy_unmatched_expected'],legacy_unmatched_actual=result['legacy_unmatched_actual'])
                summaries[(a['stage'],it)]=result
            metrics.append(row)
        reports.append(f"- {a['directory']}: **{a['status']}**, elapsed {a.get('elapsed_seconds',0):.1f} s, exit {a.get('exit_code')}, OS peak RSS {a['os_peak_rss_bytes']}, output {a['output_bytes']} bytes.")
    fields=list(dict.fromkeys(k for r in metrics for k in r))
    with (out/'iteration_metrics.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields or ['stage','iteration']);writer.writeheader();writer.writerows(metrics)
    if people is not None:extract_people(ROOT/'scenarios/nyc/population-v6.xml.gz',selected,out/'selected-input-plans.xml')
    save(out/'diagnostic_people.json',selected_rows);manifest['analysis_seconds']=time.monotonic()-analysis_start;save(out/'run_manifest.json',manifest)
    comparison={}
    if ('smoke',0) in summaries and ('five',0) in summaries:
        for k in ['departures_by_mode','completed_legs_by_mode','stuck_events_by_mode','legacy_expected_triggers','legacy_observed_score_events','legacy_score_sum_by_kind']:
            comparison[k]={'smoke':summaries[('smoke',0)][k],'five':summaries[('five',0)][k],'equal':summaries[('smoke',0)][k]==summaries[('five',0)][k]}
    save(out/'iteration-zero-comparison.json',comparison)
    text=['# Baseline diagnostic validation','',f"Status: **{manifest['status']}**. Full population; old fixed-entry capacities; modern engine.",'',*reports,'',
        '## Interpretation and unavailable measurements','',
        '- Iterations 0–4 retain innovation fraction 0.8; they are not the first five iterations of a 0–100 experiment. See each strategy-evidence.txt and effective output_config.',
        '- CSV blank means unavailable. Stopwatch operations may overlap I/O and callbacks; do not interpret scoring or listener timing as pure exclusive computational cost. Loading is not separately measured unless a supported log boundary is present.',
        '- RSS is physical resident memory, not Java heap. Sampled peak can miss spikes; OS peak is reported separately. Run-level cost fields repeat on each iteration and must not be summed.',
        '- Mode shares count main modes of trips in selected plans (MATSim ModeStatsControllerListener), not event legs. Scores retain original avg_executed/avg_worst/avg_average/avg_best definitions. Event leg counts exclude non-population drivers, include transit stages, and are not door-to-door trip shares.',
        '- Legacy nominal amounts and negative utility changes are not government revenue or dollar welfare. PricingAudit only covers added monetary toll events.',
        '- Event correlation requires person/time/kind/amount observability. Unmatched events require investigation; even exact matching verifies implementation, not real-world policy validity.',
        '- Successful startup, successful short run, fee correctness, stable outcomes and real-world validity are separate conclusions. Stability and predictive validity are untested.',
        '- No policy scenario was executed. Consider one historical fee change only after attribution evidence passes; this is a mechanism test, not CBD pricing plus transit reinvestment.',
        '', '## Evidence files','', 'run_manifest.json; budget.json; input_inventory.json; scenario_inventory.json; capacity-provenance.json; iteration_metrics.csv; diagnostic_people.json; iteration-zero-comparison.json; per-attempt logs, resources, effective configs and event summaries.']
    (out/'validation_report.md').write_text('\n'.join(text)+'\n')
    print(out/'validation_report.md')
if __name__=='__main__':main(Path(sys.argv[1]).resolve())

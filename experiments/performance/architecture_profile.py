#!/usr/bin/env python3
"""Partition the recorded iteration-0 JFR by its stopwatch phase boundaries."""
import collections
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo


def summarize(run):
    manifest=json.loads((run/'manifest.json').read_text())
    java=Path(manifest['java_home'])/'bin/jfr'
    profile=run/'short-profile'
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
    from analyze_baseline_diagnostic import table
    row=table(profile/'simulation/BUILT.stopwatch.csv')[0]
    # The recorded log and stopwatch use America/New_York local wall time.
    attempt=next(a for a in manifest['attempts'] if a['name']=='short-profile')
    day=dt.datetime.fromisoformat(attempt['started_utc']).astimezone(ZoneInfo('America/New_York')).date()
    boundaries=[dt.datetime.combine(day,dt.time.fromisoformat(row[k]),ZoneInfo('America/New_York')).timestamp()
                for k in ['BEGIN iteration','BEGIN mobsim','END mobsim']]
    data=json.loads(subprocess.run([str(java),'print','--json','--events','jdk.ExecutionSample',str(profile/'profile.jfr')],capture_output=True,text=True,check=True).stdout)
    groups={k:{'samples':0,'top_methods':collections.Counter(),'threads':collections.Counter(),'inclusive_categories':collections.Counter()} for k in ['startup','pre_mobsim','mobsim','after_mobsim_and_shutdown']}
    prefixes={'road_routing':'org.matsim.core.router','pt_routing':'ch.sbb.matsim.routing',
              'pricing_route_cost':'org.c2smart.matsimnyc.Pricing2025$1$1.getLinkTravelDisutility',
              'qsim':'org.matsim.core.mobsim.qsim','event_dispatch':'org.matsim.core.events.EventsManagerImpl',
              'event_xml':'org.matsim.core.events.algorithms.EventWriterXML','scoring':'org.matsim.core.scoring'}
    for event in data['recording']['events']:
        v=event['values']; t=dt.datetime.fromisoformat(v['startTime']).timestamp()
        phase=list(groups)[sum(t>=b for b in boundaries)];g=groups[phase];g['samples']+=1
        frames=(v.get('stackTrace') or {}).get('frames',[])
        names=[f['method']['type']['name'].replace('/','.')+'.'+f['method']['name'] for f in frames]
        if names:g['top_methods'][names[0]]+=1
        g['threads'][(v.get('sampledThread') or {}).get('javaName','unknown')]+=1
        for label,prefix in prefixes.items():
            if any(n.startswith(prefix) for n in names):g['inclusive_categories'][label]+=1
    for g in groups.values():
        g['top_methods']=dict(g['top_methods'].most_common(12));g['threads']=dict(g['threads'].most_common(8));g['inclusive_categories']=dict(g['inclusive_categories'])
    result={'source':str(profile/'profile.jfr'),'phase_boundaries_local':{k:row[k] for k in ['BEGIN iteration','BEGIN mobsim','END mobsim']},'phases':groups,
            'limitations':'Iteration 0 only, no replanning; JFR execution samples, not wall-time attribution; inclusive categories overlap; stopwatch has second precision.'}
    (run/'architecture-profile.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':print(json.dumps(summarize(Path(sys.argv[1]).resolve()),indent=2))

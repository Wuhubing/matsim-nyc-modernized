#!/usr/bin/env python3
"""Small-file progress snapshot; never scans event files or reads credentials."""
import json,sys
from pathlib import Path
import pilot
out=Path(sys.argv[1]).resolve();m=json.loads((out/'run_manifest.json').read_text());b=json.loads((out/'budget.json').read_text())
rows=[]
for a in m['attempts']:
    s=out/a['directory']/'simulation';p=s/'BUILT.scorestats.csv';scores=pilot.table(p) if p.exists() and p.stat().st_size else []
    last=scores[-1] if scores else None
    row={'arm':a['stage'],'status':a['status'],'latest_scored_iteration':int(last['iteration']) if last else None,'score':float(last['avg_executed']) if last else None}
    if last:
        h=s/f"ITERS/it.{int(last['iteration'])}/BUILT.{int(last['iteration'])}.legHistogram.txt"
        if h.exists():row['unfinished']=sum(float(x['stuck_all']) for x in pilot.table(h))
    rows.append(row)
print(json.dumps({'status':'running' if any(a['status']=='running' for a in m['attempts']) else m['status'],'budget_used_minutes':round(b['used_seconds']/60,2),'arms':rows},ensure_ascii=False))

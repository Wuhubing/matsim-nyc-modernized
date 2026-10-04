"""Read-only audit of completed artifacts, independent of the runner's summaries."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from environment import Config, costs, parameters
from observations import observe


def audit(out):
    failures=[]; counts={'numerical_runs':0,'numerical_days':0,'api_calls':0,'closed_days':0}
    manifest=json.loads((out/'manifest.json').read_text())
    for name,digest in manifest['source_hashes'].items():
        if hashlib.sha256((out/'code'/name).read_bytes()).hexdigest()!=digest:
            failures.append('Archived source hash mismatch: '+name)
    with gzip.open(out/'numerical.jsonl.gz','rt') as f:
        for line in f:
            run=json.loads(line); cfg=Config(**run['config']); counts['numerical_runs']+=1
            history=[]
            for row,decision in zip(run['rows'],run['decisions']):
                counts['numerical_days']+=1
                n_a=sum(a==0 for a in row['actions']); cap,bg=parameters(cfg,row['day'])
                if row['costs']!=costs(n_a,cfg.population,cap,bg): failures.append('Cost mismatch')
                if row['total_flow']!=[n_a+bg,cfg.population-n_a]: failures.append('Flow mismatch')
                for i,obs in enumerate(decision['observations']):
                    if obs!=observe(history,i,cfg.population,run['information']): failures.append('Observation mismatch')
                if [c['route'] for c in decision['choices']]!=row['actions']: failures.append('Action mismatch')
                history.append(row)
    charged=0.; unknown=0.; pending=0
    for path in (out/'calls').glob('*.json') if (out/'calls').exists() else []:
        d=json.loads(path.read_text()); counts['api_calls']+=1
        pending+=d['status']=='pending'
        if 'usage' in d:
            cost=(d['usage']['input_tokens']*.4+d['usage']['output_tokens']*1.6)/1e6
            if not math.isclose(cost,d['estimated_usd'],abs_tol=1e-10): failures.append('API cost mismatch')
            charged+=cost
        elif d['status']!='pending': unknown+=d['reserved_usd']
        obs=json.loads(d['request']['input'])
        if set(obs)!={'population','information','history'}: failures.append('Unexpected public observation fields')
        allowed={'day','route','travel_time'} | ({'total_route_flows'} if obs['information']=='flow' else set())
        if any(set(r)!=allowed for r in obs['history']): failures.append('Unexpected history fields')
        if 'Authorization' in d['request']: failures.append('Authorization header logged')
    if 'elapsed_seconds' in manifest:
        if pending: failures.append('Unsettled API requests after run')
        account=manifest.get('api',{})
        if account and (not math.isclose(charged,account['estimated_usd'],abs_tol=1e-8) or
                        not math.isclose(unknown,account['unknown_reserved_usd'],abs_tol=1e-8)):
            failures.append('API ledger mismatch')
        if charged+unknown>manifest['limits']['usd']: failures.append('API cap exceeded')
        if manifest['elapsed_seconds']>manifest['limits']['seconds']: failures.append('Time cap exceeded')
    p=out/'closed-steps.jsonl'
    worlds={}
    if p.exists():
        for line in p.read_text().splitlines():
            step=json.loads(line); counts['closed_days']+=1; history=worlds.setdefault(step['world'],[])
            cfg=Config(**step['config']); row=step['row']
            n_a=sum(a==0 for a in row['actions']); cap,bg=parameters(cfg,row['day'])
            if len(row['actions'])!=cfg.population or row['costs']!=costs(n_a,cfg.population,cap,bg):
                failures.append('Closed cost/action mismatch')
            if row['total_flow']!=[n_a+bg,cfg.population-n_a]: failures.append('Closed flow mismatch')
            if [c['route'] for c in step['choices']]!=row['actions']: failures.append('Closed choice mismatch')
            if step['row']['day']!=len(history)+1: failures.append('Closed day sequence mismatch')
            for i,obs in enumerate(step['observations']):
                if obs!=observe(history,i,information=step['information']): failures.append('Closed observation mismatch')
            history.append(step['row'])
    return {'counts':counts,'passed':not failures,'failures':failures[:20]}

if __name__=='__main__':
    result=audit(Path(sys.argv[1])); print(json.dumps(result,ensure_ascii=False,indent=2)); sys.exit(0 if result['passed'] else 1)

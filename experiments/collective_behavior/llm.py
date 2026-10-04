"""Bounded, independent Responses calls. No response cache and no automatic retry."""
import json
import math
import threading
import time
import urllib.request
from pathlib import Path
from budget import save
from policies import CAUSES, validate_choice, fallback

MODEL='gpt-4.1-mini-2025-04-14'
INPUT_PER_MILLION=.40
OUTPUT_PER_MILLION=1.60
MAX_OUTPUT=180

COMMON = '''You choose route 0 or 1 for one of 24 travelers, all acting simultaneously.
Minimize your own travel time. Others may change routes too. Baseline cost functions in minutes:
route 0 = 10 + 0.5 * total_route_0_flow / capacity_multiplier;
route 1 = 16 + 0.25 * total_route_1_flow. Baseline capacity_multiplier=1, no background traffic.
Only route 0 may experience capacity reduction, extra background traffic, both, or neither.
The event timing, duration, and size are unknown to you. Total flows, when provided, include
background vehicles. Only your own traveled route's time is observed. Other travelers need not
keep their previous routes. Use exactly the supplied last five experiences, no external knowledge.
An observed high travel time alone may not identify a cause. Use insufficient when evidence
cannot distinguish causes; do not invent observations. Predict next-day route costs, then select
one route. No explanations are required. Output JSON only.'''


def request_body(obs, mode):
    if mode not in ('direct','diagnose'):
        raise ValueError(mode)
    fields={'route':{'type':'integer','enum':[0,1]},
            'cause':{'type':'string','enum':list(CAUSES)},
            'confidence':{'type':'number','minimum':0,'maximum':1},
            'predicted_costs':{'type':'array','items':{'type':'number'},'minItems':2,'maxItems':2}}
    order=['route','predicted_costs','cause','confidence'] if mode=='direct' else ['cause','confidence','predicted_costs','route']
    instruction = ('Choose a route directly from experience first; then report cost predictions and your diagnostic assessment.' if mode=='direct'
                   else 'Assess the cause and uncertainty first; use that assessment to predict costs and choose a route.')
    return {'model':MODEL,'store':False,'temperature':.7,'max_output_tokens':MAX_OUTPUT,
            'instructions':COMMON+'\n'+instruction,'input':json.dumps(obs,sort_keys=True),
            'text':{'format':{'type':'json_schema','name':'choice','strict':True,
                    'schema':{'type':'object','properties':{k:fields[k] for k in order},'required':order,'additionalProperties':False}}}}


class BudgetStop(Exception):
    pass


class Client:
    def __init__(self, out, key_file, limit, deadline):
        self.out=Path(out); (self.out/'calls').mkdir(exist_ok=True)
        self.limit=limit; self.deadline=deadline
        self.lock=threading.Lock(); self.spent=0.; self.held=0.; self.unknown=0.; self.count=0; self.errors=0
        self.key=Path(key_file).read_text().strip()
        if not self.key or any(c.isspace() for c in self.key):
            raise ValueError('Credential must be a single key')

    def snapshot(self):
        return {'model':MODEL,'limit_usd':self.limit,'estimated_usd':self.spent,'unknown_reserved_usd':self.unknown,
                'inflight_reserved_usd':self.held,'calls':self.count,'errors':self.errors,
                'pricing':{'input_per_million':INPUT_PER_MILLION,'output_per_million':OUTPUT_PER_MILLION}}

    def decide(self, obs, mode, call_id, seed):
        body=request_body(obs,mode); raw=json.dumps(body).encode()
        # UTF-8 bytes upper-bound ordinary text tokens; extra allowance covers protocol framing.
        reserve=(len(raw)+2048)*INPUT_PER_MILLION/1e6+MAX_OUTPUT*OUTPUT_PER_MILLION/1e6
        with self.lock:
            if time.monotonic()+30 >= self.deadline or self.spent+self.held+self.unknown+reserve>self.limit or self.errors>=3:
                raise BudgetStop('Time/API budget or transport-error stop')
            path=self.out/'calls'/f'{call_id}.json'
            if path.exists():
                raise RuntimeError('Duplicate call ID; requests are never silently replayed')
            self.held+=reserve; self.count+=1
            record={'id':call_id,'mode':mode,'request':body,'status':'pending','reserved_usd':reserve}
            save(path,record); save(self.out/'api-budget.json',self.snapshot())
        start=time.monotonic(); measured=None
        choice={'route':fallback(obs,seed),'cause':'insufficient','confidence':0.,'predicted_costs':[18.,18.],'valid':False}
        try:
            req=urllib.request.Request('https://api.openai.com/v1/responses',data=raw,
                headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=25) as response:
                result=json.load(response)
            usage=result.get('usage')
            if usage:
                measured=(usage['input_tokens']*INPUT_PER_MILLION+usage['output_tokens']*OUTPUT_PER_MILLION)/1e6
                record.update(usage=usage,estimated_usd=measured)
            record.update(response=result,returned_model=result.get('model'))
            if result.get('status')!='completed':
                raise ValueError('Incomplete response')
            text=''.join(c.get('text','') for o in result.get('output',[]) if o.get('type')=='message' for c in o.get('content',[]) if c.get('type')=='output_text')
            choice=validate_choice(json.loads(text)); choice['valid']=True
            record['status']='complete'
        except Exception as error:
            record.update(status='fallback',error_type=type(error).__name__,http_status=getattr(error,'code',None))
            if not isinstance(error,(ValueError,KeyError,TypeError)):
                with self.lock: self.errors+=1
        finally:
            record.update(choice=choice,elapsed_seconds=time.monotonic()-start)
            with self.lock:
                self.held-=reserve
                if measured is None: self.unknown+=reserve
                else: self.spent+=measured
                save(path,record); save(self.out/'api-budget.json',self.snapshot())
        return choice

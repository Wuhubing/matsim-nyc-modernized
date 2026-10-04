"""Reserve against the existing campaign, without racing other experiment writers."""
import contextlib
import datetime
import fcntl
import json
import os
import time
from pathlib import Path


def save(path, value):
    path=Path(path)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)


def read(path):
    return json.loads(Path(path).read_text())


@contextlib.contextmanager
def lock(path):
    with Path(path).open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def reserve(source, out, seconds=1800, dollars=5):
    """Shared writer lock spans both reservations. Crash leaves conservative commitments.

    Shared simulation time is prepaid. Other legacy writers already count it in used_seconds.
    No concurrent writer needs to understand the new reservation format.
    """
    with lock(source/'executor.lock'), lock(source/'api.lock'):
        sim=read(source/'budget.json'); api=read(source/'api-budget.json')
        if sim.get('active'):
            raise RuntimeError('Shared simulation ledger has an active attempt; do not overwrite')
        # Existing unknown API outcomes remain reserved. Completed calls use measured costs.
        commitments=sum(c.get('estimated_usd',c.get('reservation_usd',0)) if c.get('status')=='complete'
                        else c.get('reservation_usd',0) for c in api['calls'])
        seconds=min(seconds, max(0,sim['limit_seconds']-sim['used_seconds']))
        dollars=min(dollars,max(0,api['limit_usd']-commitments))
        if seconds <= 0:
            raise RuntimeError('Shared simulation budget exhausted')
        reservation={'id':out.name,'source':str(source),'seconds':seconds,'dollars':dollars,
                     'sim_before':sim['used_seconds'],'api_before_commitments':commitments,'settled':False}
        save(out/'reservation.json',reservation)
        sim['used_seconds']+=seconds
        sim.setdefault('collective_reservations',{})[out.name]={'seconds':seconds,'status':'reserved'}
        save(source/'budget.json',sim)
        api['calls'].append({'variant':out.name,'status':'pending','reservation_usd':dollars})
        api['reserved_usd']+=dollars
        save(source/'api-budget.json',api)
        return reservation


def settle(out, used_seconds, api_commitment):
    r=read(out/'reservation.json'); source=Path(r['source'])
    if r['settled']:
        return
    # Refuse to reconcile if a legacy writer holds a snapshot. Safe to leave prepaid.
    with lock(source/'executor.lock'), lock(source/'api.lock'):
        sim=read(source/'budget.json'); api=read(source/'api-budget.json')
        if sim.get('active'):
            raise RuntimeError('Shared campaign active; reservation remains conservatively charged')
        item=sim['collective_reservations'][out.name]
        if item['status']=='reserved':
            sim['used_seconds']-=max(0,r['seconds']-used_seconds)
            item.update(status='settled',seconds=used_seconds)
            save(source/'budget.json',sim)
        for call in api['calls']:
            if call.get('variant')==out.name and call['status']=='pending':
                # Commitment includes full reservations for requests with unknown billing.
                call.update(status='complete',estimated_usd=api_commitment,includes_unknown_reservations=True)
                api['measured_usd']+=api_commitment
                save(source/'api-budget.json',api)
        r.update(settled=True,used_seconds=used_seconds,api_commitment=api_commitment)
        save(out/'reservation.json',r)

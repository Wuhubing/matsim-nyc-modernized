#!/usr/bin/env python3
"""How often is each kind of proposal useful, over the iterations and by proposed mode? Offline input for an adaptive
proposal controller (a bandit over proposal types; docs/aggregate-regularity-plan.md, lever 2).

  proposal_success.py RUN --out FILE.json [--ks 10,20,30,40,50,60,70] [--horizon 10] [--jobs 4]

Outcome of an innovation at t (new plan created and selected at t), as in innovation_outcomes.py / labels.py:
- useful: selected again within t+1..t+H and its last score in t..t+H above the agent's best stored score at t-1;
- first_better: executed score at t above the best stored score at t-1.
(a) every iteration 1..79: per strategy kind (mode = SubtourModeChoice + ReRoute, route = ReRoute, time =
    TimeAllocationMutator): innovations, useful share, first_better share.
(b) at snapshot iterations k: mode innovations at k compared with their parent in the snapshot (plans as after the
    replanning of k): the main mode (plans_stats.py rule) of the first trip whose main mode changed, from -> to;
    useful and first_better shares by proposed (to) mode and by from -> to. Bandit potential: with the observed
    useful share s_m per proposed mode and the observed proposal mix p_m, the useful rate of the current mix
    sum p_m s_m against a mix proportional to s_m (floor 2% per mode). This ignores that availability limits which
    modes can be proposed to whom and that success rates would change once the mix changes."""
import argparse, json, sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from logs import ReplanningLog
import labels
from innovation_outcomes import kinds
from plans_stats import MAIN, stream
from plan_snapshots import snapshot_path

MODES = MAIN + ['walk']


def trip_main_modes(plan):
    out, legs = [], []
    for x in plan:
        if x.tag in ('act', 'activity'):
            if not x.get('type', '').endswith('interaction') and legs:
                out.append(next((m for m in MAIN if m in legs), 'walk')); legs = []
        elif x.tag == 'leg':
            legs.append(x.get('mode'))
    return out


def transitions(job):
    """{person_id: (from, to, changed trips)} for mode innovations at k (wanted: person_id -> (new id, parent id));
    the new id is not used: see below."""
    run, k, wanted = job; out = {}
    with stream(snapshot_path(run, k)) as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            w = wanted.get(el.get('id'))
            if w is not None:
                # In the snapshot the copy made at k still carries its parent's planId (the new id is assigned
                # later); tell them apart by iterationCreated.
                new = par = None
                for p in el.findall('plan'):
                    pid = p.find("attributes/attribute[@name='planId']"); cr = p.find("attributes/attribute[@name='iterationCreated']")
                    if pid is None or int(pid.text, 36) != w[1]: continue
                    if cr is not None and int(cr.text) == k: new = trip_main_modes(p)
                    else: par = trip_main_modes(p)
                if new is not None and par is not None and len(new) == len(par):
                    ch = [(a, b) for a, b in zip(par, new) if a != b]
                    if ch: out[el.get('id')] = (ch[0][0], ch[0][1], len(ch))
            root.remove(el)
    return k, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True); ap.add_argument('--ks', default='10,20,30,40,50,60,70')
    ap.add_argument('--horizon', type=int, default=10); ap.add_argument('--jobs', type=int, default=1)
    a = ap.parse_args(); H = a.horizon; ks = [int(x) for x in a.ks.split(',')]
    log = ReplanningLog(a.run); its, d = labels.load(log); kind = kinds(log)
    T = len(its); code_kind = np.vectorize(lambda c: kind.get(int(c), 'select'))
    useful, first, kinds_at = {}, {}, {}
    part_a = {}
    for t in range(1, min(80, T - H)):
        strat = log.agents(t)['strategy']
        new = d['innovated'][t] & (d['created'][t] == t); idx = np.nonzero(new)[0]
        window = d['plan'][t:t + H + 1, idx] == d['plan'][t, idx][None, :]
        again = window[1:].any(axis=0); last = H - np.argmax(window[::-1], axis=0)
        u = again & (d['executed'][t + last, idx] > d['best'][t - 1, idx])
        f1 = d['executed'][t, idx] > d['best'][t - 1, idx]
        ty = code_kind(strat[idx]) if len(idx) else np.zeros(0, str)
        useful[t], first[t], kinds_at[t] = dict(zip(idx.tolist(), u.tolist())), dict(zip(idx.tolist(), f1.tolist())), dict(zip(idx.tolist(), ty.tolist()))
        part_a[t] = {k_: {'n': int((ty == k_).sum()), 'useful': float(u[ty == k_].mean()) if (ty == k_).any() else float('nan'),
                          'first_better': float(f1[ty == k_].mean()) if (ty == k_).any() else float('nan')} for k_ in ('mode', 'route', 'time')}
    print('part (a) done', flush=True)

    jobs = []
    for k in ks:
        if k not in useful: continue
        par = log.agents(k)['parent']
        want = {log.person_id[i]: (int(d['plan'][k, i]), int(par[i])) for i, ty in kinds_at[k].items() if ty == 'mode'}
        jobs.append((a.run, k, want))
    with Pool(a.jobs) as pool: res = pool.map(transitions, jobs)
    row_of = {p: i for i, p in enumerate(log.person_id)}
    part_b, pooled = {}, defaultdict(lambda: [0, 0, 0])
    for k, tr in res:
        to_n, to_u, to_f, pair = Counter(), Counter(), Counter(), defaultdict(lambda: [0, 0])
        for p, (fr, to, nch) in tr.items():
            i = row_of[p]; u, f1 = useful[k][i], first[k][i]
            to_n[to] += 1; to_u[to] += u; to_f[to] += f1; pair[f'{fr}->{to}'][0] += 1; pair[f'{fr}->{to}'][1] += u
            pooled[to][0] += 1; pooled[to][1] += u; pooled[to][2] += f1
        n = sum(to_n.values())
        by_to = {m: {'share_of_proposals': to_n[m] / n, 'useful': to_u[m] / to_n[m], 'first_better': to_f[m] / to_n[m]} for m in MODES if to_n[m]}
        s = np.array([by_to[m]['useful'] if m in by_to else 0.0 for m in MODES]); p_ = np.array([by_to[m]['share_of_proposals'] if m in by_to else 0.0 for m in MODES])
        w = np.maximum(s / s.sum() if s.sum() else s, 0.02); w = w / w.sum()
        part_b[k] = {'mode_innovations_matched': n, 'by_to_mode': by_to,
                     'by_pair': {kk: {'n': v[0], 'useful': v[1] / v[0]} for kk, v in sorted(pair.items(), key=lambda x: -x[1][0]) if v[0] >= 30},
                     'useful_rate_current_mix': float((p_ * s).sum()), 'useful_rate_success_weighted': float((w * s).sum())}
    out = {'run': a.run, 'horizon': H, 'per_iteration': part_a, 'by_snapshot': part_b,
           'pooled_by_to_mode': {m: {'n': v[0], 'useful': v[1] / v[0], 'first_better': v[2] / v[0]} for m, v in pooled.items() if v[0]}}
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    print('\n(a) useful share by strategy kind (first_better in brackets)')
    for t in (1, 5, 10, 20, 30, 40, 50, 60, 69, 79):
        if t in part_a: print(f'  t={t:2d} ' + '  '.join(f"{k_} {v['useful']:.3f} ({v['first_better']:.3f}) n={v['n']}" for k_, v in part_a[t].items()))
    print('\n(b) mode innovations by proposed mode: share of proposals / useful share')
    for k, r in part_b.items():
        print(f"  k={k} n={r['mode_innovations_matched']}: " + '  '.join(f"{m} {v['share_of_proposals']:.2f}/{v['useful']:.3f}" for m, v in r['by_to_mode'].items())
              + f"  | useful rate current {r['useful_rate_current_mix']:.3f} -> success-weighted {r['useful_rate_success_weighted']:.3f}")
    print('\npooled by proposed mode: n, useful, first_better')
    for m, v in sorted(out['pooled_by_to_mode'].items(), key=lambda x: -x[1]['useful']): print(f"  {m:5} {v['n']:7d} {v['useful']:.3f} {v['first_better']:.3f}")


if __name__ == '__main__':
    main()

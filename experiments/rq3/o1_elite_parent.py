#!/usr/bin/env python3
"""O1: natural experiment for elite parents.

MATSim 2026.0 picks the plan to mutate uniformly at random from the stored plans (RandomPlanSelector in
strategies/ReRoute.java:45, TimeAllocationMutator.java:40, SubtourModeChoice.java:47). So whether the parent happened
to be the agent's best stored plan is random, and comparing innovations with best versus non-best parents estimates
what an elite-parent rule would give, without a new simulation.

  o1_elite_parent.py RUN --out FILE.json [--ks 10,20,30,40,50,60,70] [--jobs 4]

Innovations at snapshot iteration k (resident subpopulations, plan created at k). Outcome from the W1 log, as in
proposal_predictor.py:  delta = executed score at k - best stored score at k-1.
From the plan snapshot at k (written after the replanning of k): the parent's stored score, the stored scores of the
other plans (the new plan excluded), the parent's rank (1 = best) and the parent gap = parent score - best stored.
Reported per strategy kind and pooled over k: share with a best parent, better-at-once share (delta > 0) and clearly
worse share (delta < -3) for best versus non-best parents, and by parent-gap bins."""
import argparse, json, os, sys
import xml.etree.ElementTree as ET
from multiprocessing import Pool
from pathlib import Path
import numpy as np

_SIBLING = Path(__file__).resolve().parent.parent/'l2seg'
REPO = Path(os.environ.get('L2SEG_DIR', str(_SIBLING if _SIBLING.is_dir() else Path.home()/'matsim-work'/'matsim-nyc-modernized'/'experiments'/'l2seg')))
sys.path.insert(0, str(REPO))
from logs import ReplanningLog                    # noqa: E402
from innovation_outcomes import kinds             # noqa: E402
from plans_stats import stream                    # noqa: E402
from plan_snapshots import snapshot_path          # noqa: E402

RESIDENTS = ('man', 'nonman')
BINS = [(-1e-9, 1e-9, 'parent is best (gap 0)'), (-0.5, -1e-9, 'gap (-0.5, 0)'), (-2, -0.5, 'gap (-2, -0.5]'),
        (-5, -2, 'gap (-5, -2]'), (-1e9, -5, 'gap <= -5')]


def attr(p, name):
    a = p.find(f"attributes/attribute[@name='{name}']")
    return None if a is None else a.text


def parse(job):
    """{person_id: (parent score, best stored score excluding the new plan, parent rank, stored count)} at k."""
    run, k, want = job
    out = {}
    with stream(snapshot_path(run, k)) as f:
        it = ET.iterparse(f, events=('start', 'end'))
        _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person':
                continue
            parent_id = want.get(el.get('id'))
            if parent_id is not None:
                par, stored = None, []
                for p in el.findall('plan'):
                    pid, cr, sc = attr(p, 'planId'), attr(p, 'iterationCreated'), p.get('score')
                    is_new = pid is not None and int(pid, 36) == parent_id and cr is not None and int(cr) == k
                    if is_new or sc is None:
                        continue
                    stored.append(float(sc))
                    if pid is not None and int(pid, 36) == parent_id:
                        par = float(sc)
                if par is not None and stored:
                    rank = 1 + sum(s > par for s in stored)
                    out[el.get('id')] = (par, max(stored), rank, len(stored))
            root.remove(el)
    return k, out


def summary(delta, gap, rank):
    def rates(m):
        n = int(m.sum())
        return {'n': n, 'better_share': float((delta[m] > 0).mean()) if n else None,
                'worse3_share': float((delta[m] < -3).mean()) if n else None,
                'mean_delta': float(delta[m].mean()) if n else None}
    best = rank == 1
    res = {'n': int(len(delta)), 'share_best_parent': float(best.mean()) if len(delta) else None,
           'best_parent': rates(best), 'other_parent': rates(~best), 'all': rates(np.ones(len(delta), bool)), 'by_gap': {}}
    for lo, hi, name in BINS:
        res['by_gap'][name] = rates((gap > lo) & (gap <= hi) if lo > -1e8 else gap <= hi)
    b, a = res['best_parent']['better_share'], res['all']['better_share']
    res['uplift_better_if_elite'] = (b / a) if (b is not None and a) else None
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run'); ap.add_argument('--out', required=True)
    ap.add_argument('--ks', default='10,20,30,40,50,60,70'); ap.add_argument('--jobs', type=int, default=1)
    a = ap.parse_args()
    ks = [int(x) for x in a.ks.split(',')]
    log = ReplanningLog(a.run)
    kind = kinds(log)
    rows, jobs = {}, []
    for k in ks:
        ag, prev = log.agents(k), log.agents(k - 1)
        idx = np.nonzero(ag['innovated'] & (ag['created'] == k) & np.isin(log.subpopulation, RESIDENTS))[0]
        rows[k] = {log.person_id[i]: (float(ag['executed'][i]), float(prev['best'][i]), kind.get(int(ag['strategy'][i]), 'select'))
                   for i in idx}
        jobs.append((a.run, k, {log.person_id[i]: int(ag['parent'][i]) for i in idx}))
    with Pool(a.jobs) as pool:
        parsed = dict(pool.map(parse, jobs))
    print('parsed: ' + ', '.join(f'k={k} {len(v)}/{len(rows[k])}' for k, v in parsed.items()), flush=True)

    out = {'run': a.run, 'by_k': {}, 'pooled': {}}
    pooled = {kd: [[], [], []] for kd in ('mode', 'route', 'time', 'all')}
    for k in ks:
        ids = [p for p in parsed[k] if np.isfinite(rows[k][p][0]) and np.isfinite(rows[k][p][1])]
        delta = np.array([rows[k][p][0] - rows[k][p][1] for p in ids])
        gap = np.array([parsed[k][p][0] - parsed[k][p][1] for p in ids])
        rank = np.array([parsed[k][p][2] for p in ids])
        kd_arr = np.array([rows[k][p][2] for p in ids])
        out['by_k'][k] = {}
        for kd in ('mode', 'route', 'time', 'all'):
            m = np.ones(len(ids), bool) if kd == 'all' else kd_arr == kd
            out['by_k'][k][kd] = summary(delta[m], gap[m], rank[m])
            pooled[kd][0].append(delta[m]); pooled[kd][1].append(gap[m]); pooled[kd][2].append(rank[m])
    for kd, (d, g, r) in pooled.items():
        out['pooled'][kd] = summary(np.concatenate(d), np.concatenate(g), np.concatenate(r))
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')

    print('\npooled over k: kind  n  share best parent | better: best / other / all | worse<-3: best / other | uplift')
    f = lambda v: '  -  ' if v is None else f'{v:.3f}'
    for kd, r in out['pooled'].items():
        bp, op, al = r['best_parent'], r['other_parent'], r['all']
        print(f"{kd:6} {r['n']:7d} {f(r['share_best_parent'])} | {f(bp['better_share'])} / {f(op['better_share'])} / "
              f"{f(al['better_share'])} | {f(bp['worse3_share'])} / {f(op['worse3_share'])} | {f(r['uplift_better_if_elite'])}")


if __name__ == '__main__':
    main()

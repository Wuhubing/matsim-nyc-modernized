#!/usr/bin/env python3
"""Who actually changes plan because of the policy, and where the policy effect on car legs lives.

  plan_change.py --root /orcd/scratch/.../matsim-work --out out/plan-change.json [--seeds 4711 4712 4713] [--jobs 4]

Runs per seed (directories under --root, all read from simulation/research/persons-<it>.csv.gz):
  W0  policy/warm-baseline-s<seed>-100it       baseline warm-started from RQ1 iteration 99
  W1  policy/warm-schema{1,2}-s<seed>-100it    policies warm-started from the same plans (same seed)
  X1  policy/x1-baseline-s<seed>-from99-50it   selection only from the same plans (noise floor without innovation)
  cold pair: policy/schema{1,2}-s<seed>-100it minus rq1/baseline-s<seed>-100it-rq1 (for the effect location only)

1. Exposure at the start: W1 iteration 0 executes the RQ1 iteration-99 plans under the toll, so toll_revenue > 0
   there marks who would pay without changing anything ("charged"). Groups: cohort (related / unrelated, the
   acceptance protocol's charging_cohort) x charged. Sanity: share of persons whose iteration-0 choice is the same in
   W0, W1 and X1 (expected 1.0).
2. Switching relative to the start: share of persons whose selected choice (choice_sha256) at iteration k differs from
   their own iteration-0 choice, per run and group. Policy-induced excess = W1 - W0 (same seed); X1 shows the share
   that moves by selection alone.
3. Effect location: per group, the policy difference of car legs summed over the group's persons, window mean
   (W1 - W0 over iterations 90-99, and cold policy - RQ1 baseline). Reported with each group's share of the total
   difference (how much of the effect a group captures) and its share of the population (what restricting search
   to it would keep).
Groups always come from the warm start (iteration 0), never from the policy run's later iterations.
"""
import argparse, csv, gzip, json
from multiprocessing import Pool
from pathlib import Path
import numpy as np

CHECK = (0, 1, 2, 3, 5, 10, 20, 30, 40, 50, 60, 70, 79, 85, 90, 99)
WINDOW = tuple(range(90, 100))
CHECK_X1 = (0, 1, 2, 3, 5, 10, 20, 30, 40, 49)
WINDOW_X1 = tuple(range(40, 50))
COHORT = {'related': 0, 'unrelated': 1}
POLICIES = ('schema1', 'schema2')


def research(run):
    return Path(run)/'simulation'/'research'


def read_iteration(run, it):
    """person ids, cohort code, choice hash (first 16 hex digits), car legs, toll paid, cordon entries."""
    ids, coh, ch, car, toll, cross = [], [], [], [], [], []
    with gzip.open(research(run)/f'persons-{it}.csv.gz', 'rt') as f:
        for r in csv.DictReader(f):
            ids.append(r['person_id'])
            coh.append(COHORT.get(r['charging_cohort'], 2))
            ch.append(int(r['choice_sha256'][:16], 16) if r['choice_sha256'] else 0)
            car.append(int(r['completed_car_legs'] or 0))
            toll.append(float(r['toll_revenue'] or 0.0))
            cross.append(int(r['private_car_entry_crossings'] or 0))
    return (ids, np.array(coh, np.int8), np.array(ch, np.uint64), np.array(car, np.int16),
            np.array(toll, np.float32), np.array(cross, np.int16))


def summarise_run(args):
    """Per-person arrays of one run, aligned to the person order of its iteration 0."""
    run, check, window = args
    ids0, coh, ch0, car0, toll0, cross0 = read_iteration(run, 0)
    pos = {p: i for i, p in enumerate(ids0)}
    its = sorted(set(check) | set(window))
    switched, car_at, car_w, cross_w = {}, {}, np.zeros(len(ids0)), np.zeros(len(ids0))
    for it in its:
        if it == 0:
            ch, car, cross = ch0, car0, cross0
        else:
            ids, _, ch, car, _, cross = read_iteration(run, it)
            if ids != ids0:                       # align by person id if the order differs
                order = np.array([pos[p] for p in ids])
                ch2, car2, cr2 = np.zeros_like(ch0), np.zeros_like(car0), np.zeros_like(cross0)
                ch2[order], car2[order], cr2[order] = ch, car, cross
                ch, car, cross = ch2, car2, cr2
        if it in check:
            switched[it] = ch != ch0
            car_at[it] = car
        if it in window:
            car_w += car; cross_w += cross
    return {'run': str(run), 'ids': ids0, 'cohort': coh, 'choice0': ch0, 'toll0': toll0,
            'switched': switched, 'car_at': car_at,
            'car_window': car_w / len(window), 'cross_window': cross_w / len(window)}


def frac(x):
    """Mean of a boolean array, None for an empty group."""
    return float(x.mean()) if len(x) else None


def groups(cohort, charged):
    g = {'all': np.ones(len(cohort), bool),
         'related': cohort == 0, 'unrelated': cohort == 1,
         'charged': charged, 'not charged': ~charged,
         'related & charged': (cohort == 0) & charged, 'related & not charged': (cohort == 0) & ~charged,
         'unrelated & charged': (cohort == 1) & charged, 'unrelated & not charged': (cohort == 1) & ~charged}
    if (cohort == 2).any():
        g['other cohort'] = cohort == 2
    return g


def effect_location(G, pol_car, base_car):
    d = pol_car - base_car
    total = float(d.sum())
    n = len(d)
    return {name: {'diff': float(d[m].sum()), 'share_of_diff': (float(d[m].sum()) / total) if total else None,
                   'share_of_persons': float(m.sum()) / n} for name, m in G.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--seeds', nargs='+', default=['4711', '4712', '4713']); ap.add_argument('--jobs', type=int, default=4)
    a = ap.parse_args()
    R, P = Path(a.root), Path(a.root)/'policy'
    out = {'checkpoints': CHECK, 'window': WINDOW, 'checkpoints_x1': CHECK_X1, 'seeds': {}}
    for s in a.seeds:
        runs = {'W0': (P/f'warm-baseline-s{s}-100it', CHECK, WINDOW),
                'X1': (P/f'x1-baseline-s{s}-from99-50it', CHECK_X1, WINDOW_X1),
                'RQ1': (R/'rq1'/f'baseline-s{s}-100it-rq1', (0,), WINDOW)}
        for p in POLICIES:
            runs[f'W1-{p}'] = (P/f'warm-{p}-s{s}-100it', CHECK, WINDOW)
            runs[f'cold-{p}'] = (P/f'{p}-s{s}-100it', (0,), WINDOW)
        names = list(runs)
        with Pool(a.jobs) as pool:
            res = dict(zip(names, pool.map(summarise_run, [runs[n] for n in names])))
        ref_ids = res['W0']['ids']
        for n in names:
            assert res[n]['ids'] == ref_ids, f'person order differs in {n}'
        o = {'n_persons': len(ref_ids)}
        o['start_identical'] = {n: float(np.mean(res[n]['choice0'] == res['W0']['choice0']))
                                for n in ('X1',) + tuple(f'W1-{p}' for p in POLICIES)}
        o['policies'] = {}
        for p in POLICIES:
            w1 = res[f'W1-{p}']
            charged = w1['toll0'] > 0
            G = groups(w1['cohort'], charged)
            q = {'group_size': {g: int(m.sum()) for g, m in G.items()}}
            q['switch'] = {}
            for g, m in G.items():
                row = {}
                for k in CHECK:
                    r1, r0 = frac(w1['switched'][k][m]), frac(res['W0']['switched'][k][m])
                    row[k] = {'W1': r1, 'W0': r0, 'excess': None if r1 is None else r1 - r0}
                for k in CHECK_X1:
                    row.setdefault('X1', {})[k] = frac(res['X1']['switched'][k][m])
                q['switch'][g] = row
            q['effect_warm'] = effect_location(G, w1['car_window'], res['W0']['car_window'])
            q['effect_cold'] = effect_location(G, res[f'cold-{p}']['car_window'], res['RQ1']['car_window'])
            q['cordon_warm'] = effect_location(G, w1['cross_window'], res['W0']['cross_window'])
            q['effect_warm_path'] = {k: effect_location(G, w1['car_at'][k].astype(float),
                                                        res['W0']['car_at'][k].astype(float))
                                     for k in CHECK if k > 0}
            o['policies'][p] = q
        out['seeds'][s] = o
        print_seed(s, o)
    print_mean(out)
    Path(a.out).write_text(json.dumps(out, indent=1, default=lambda x: x.item() if hasattr(x, 'item') else str(x)))
    print(f'\nwrote {a.out}')


def print_seed(s, o):
    print(f'\n######## seed {s}: {o["n_persons"]} persons; iteration-0 choice identical to W0: '
          + ', '.join(f'{k} {v:.4f}' for k, v in o['start_identical'].items()))
    for p, q in o['policies'].items():
        print(f'\n== {p}: group sizes  ' + '  '.join(f'{g}={n}' for g, n in q['group_size'].items()))
        print(f'   switched from iteration 0 (W1 / W0 / excess) at k = 10, 40, 79, 99')
        for g, row in q['switch'].items():
            if row[10]['W1'] is None:
                continue
            print(f'   {g:26} ' + '  '.join(f'{row[k]["W1"]:.3f}/{row[k]["W0"]:.3f}/{row[k]["excess"]:+.3f}'
                                             for k in (10, 40, 79, 99)))
        print('   car-leg difference, window 90-99: group | warm diff (share of total) | cold diff (share) | share of persons')
        for g in q['effect_warm']:
            w, c = q['effect_warm'][g], q['effect_cold'][g]
            fw = '-' if w['share_of_diff'] is None else f'{w["share_of_diff"]:.2f}'
            fc = '-' if c['share_of_diff'] is None else f'{c["share_of_diff"]:.2f}'
            print(f'   {g:26} {w["diff"]:+10.1f} ({fw})  {c["diff"]:+10.1f} ({fc})  {w["share_of_persons"]:.3f}')


def print_mean(out):
    seeds = list(out['seeds'])
    print(f'\n######## mean over seeds {seeds}')
    for p in POLICIES:
        print(f'\n== {p}: share of the car-leg difference (window 90-99), warm and cold, vs share of persons')
        for g in out['seeds'][seeds[0]]['policies'][p]['effect_warm']:
            fw = [out['seeds'][s]['policies'][p]['effect_warm'][g]['share_of_diff'] for s in seeds]
            fc = [out['seeds'][s]['policies'][p]['effect_cold'][g]['share_of_diff'] for s in seeds]
            n = out['seeds'][seeds[0]]['policies'][p]['effect_warm'][g]['share_of_persons']
            fw = [x for x in fw if x is not None]; fc = [x for x in fc if x is not None]
            print(f'   {g:26} warm {np.mean(fw) if fw else float("nan"):6.2f}  cold {np.mean(fc) if fc else float("nan"):6.2f}'
                  f'  persons {n:.3f}')
        print(f'   excess switch share (W1 - W0), seed mean, k = 1, 5, 10, 20, 40, 79, 99')
        for g in out['seeds'][seeds[0]]['policies'][p]['switch']:
            v = [[out['seeds'][s]['policies'][p]['switch'][g][k]['excess'] for s in seeds] for k in (1, 5, 10, 20, 40, 79, 99)]
            if any(x is None for xs in v for x in xs):
                continue
            v = [np.mean(xs) for xs in v]
            print(f'   {g:26} ' + ' '.join(f'{x:+.4f}' for x in v))


if __name__ == '__main__':
    main()

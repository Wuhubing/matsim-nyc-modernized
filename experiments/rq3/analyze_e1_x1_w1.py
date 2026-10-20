#!/usr/bin/env python3
"""E1 acceptance (gates 2 and 3 of 04_acceptance_protocol.md), iterations to reach the reference policy effect,
X1 stationarity, and W1 versus cold references. Reads run directories only; writes one JSON and prints a summary.

  analyze_e1_x1_w1.py --root /orcd/scratch/.../matsim-work --ref deltas-reference.json --out e1.json [--arm elite]

--arm picks the run directories of the arm under test: <arm>-<scenario>-s<seed>-100it (elite = E1, elite-tamrr = E3,
warm = W0/W1). The output keys keep the name 'e1' for every arm; printed labels and first_within keys use the arm's
name (E1, E3, W1).
"""
import argparse, csv, gzip, json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compute_deltas as cd                                   # noqa: E402

SEEDS = ('4711', '4712', '4713')
PRIMARY = ('legs_car_charging:related', 'share_car', 'share_pt', 'revenue', 'usd_charging:related', 'usd_charging:unrelated')
# 04 section 6.1 / 6.2 (finalised 2026-10-17)
EPS = {'schema1': {'legs_car_charging:related': 712, 'share_car': 0.0005, 'share_pt': 0.0005, 'revenue': 4340,
                   'usd_charging:related': 0.42, 'usd_charging:unrelated': 0.24, 'cordon_entries': 248},
       'schema2': {'legs_car_charging:related': 736, 'share_car': 0.0005, 'share_pt': 0.0005, 'revenue': 5252,
                   'usd_charging:related': 1.33, 'usd_charging:unrelated': 0.34, 'cordon_entries': 286}}
EPS_D = {'legs_car_charging:related': 526, 'share_car': 0.0005, 'share_pt': 0.0005, 'revenue': 3273,
         'cordon_entries': 203, 'usd_all': 0.10, 'usd_charging:unrelated': 0.48}
GATE2 = ('share_car', 'share_pt', 'share_walk', 'usd_all', 'unfinished', 'cordon_entries', 'wait_person_hours')
TRAJ = ('legs_car_charging:related', 'share_car', 'share_pt', 'revenue', 'cordon_entries')


def n_iters(run):
    return len(list((Path(run)/'simulation').glob('iteration-metrics-*.json')))


def mean_score(run, it):
    with gzip.open(Path(run)/'simulation'/'research'/f'groups-{it}.csv.gz', 'rt') as f:
        g = {r['group']: r for r in csv.DictReader(f)}['all']
    return float(g['score_sum']) / float(g['persons'])


def trajectory(run, n):
    rows = []
    for it in range(n):
        x = cd.iteration_indicators(run, it); x['score'] = mean_score(run, it); rows.append(x)
    return rows


def win(rows, k, t, w=10):
    return float(np.mean([r[k] for r in rows[t:t + w]]))


ARM_LABEL = {'elite': 'E1', 'elite-tamrr': 'E3', 'warm': 'W1'}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); ap.add_argument('--ref', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--arm', default='elite'); a = ap.parse_args()
    L = ARM_LABEL.get(a.arm, a.arm)  # printed name of the arm under test
    R = Path(a.root); P = R/'policy'
    ref = json.loads(Path(a.ref).read_text())
    rq1 = {s: R/'rq1'/f'baseline-s{s}-100it-rq1' for s in SEEDS}
    cold = {p: {s: P/f'{p}-s{s}-100it' for s in SEEDS} for p in ('schema1', 'schema2')}
    elite = {p: {s: P/f'{a.arm}-{p}-s{s}-100it' for s in SEEDS} for p in ('baseline', 'schema1', 'schema2')}
    out = {}
    W = list(range(90, 100))

    # ---- E1 gate 3: Delta per seed with complete runs
    E = {p: {s: d for s, d in runs.items() if n_iters(d) >= 100} for p, runs in elite.items()}
    print(f'{a.arm} complete runs:', {p: sorted(r) for p, r in E.items()})
    SB = {s: cd.summarise_run(d, W) for s, d in E['baseline'].items()}
    out['e1'] = {'baseline': {s: SB[s][0] for s in SB}, 'policies': {}}
    dE = {}
    for p in ('schema1', 'schema2'):
        SP = {s: cd.summarise_run(d, W) for s, d in E[p].items() if s in SB}
        dE[p] = {k: {s: SP[s][0][k] - SB[s][0][k] for s in SP} for k in SP[next(iter(SP))][0]}
        res = {}
        print(f'\n== {L} gate 3, {p} (seeds {sorted(SP)}): indicator | {L} Delta mean | ref Delta mean (all 3 seeds) | '
              f'ref same seeds | |diff| / eps | same sign')
        for k in PRIMARY + ('cordon_entries', 'usd_all'):
            e = list(dE[p][k].values()); r_all = ref['policies'][p]['indicators'][k]['delta']
            r_same = [r_all[s] for s in dE[p][k]]
            m_e, m_r, m_rs = float(np.mean(e)), float(np.mean(list(r_all.values()))), float(np.mean(r_same))
            eps = EPS[p].get(k)
            ratio = abs(m_e - m_r) / eps if eps else None
            res[k] = {'e1': dE[p][k], 'e1_mean': m_e, 'ref_mean': m_r, 'ref_same_seeds_mean': m_rs, 'eps': eps,
                      'ratio': ratio, 'pass': (ratio is not None and ratio <= 1 and np.sign(m_e) == np.sign(m_r))}
            print(f'  {k:28} {m_e:+12.5g} {m_r:+12.5g} {m_rs:+12.5g}   {"-" if ratio is None else f"{ratio:5.2f}"}'
                  f'   {np.sign(m_e) == np.sign(m_r)}')
        out['e1']['policies'][p] = res
    seeds_d = [s for s in dE['schema1']['share_car'] if s in dE['schema2']['share_car']]
    print(f'\n== {L} D = schema1 - schema2 (seeds {seeds_d}): {L} | ref (3 seeds) | |diff|/eps')
    out['e1']['D'] = {}
    for k, eps in EPS_D.items():
        v = [dE['schema1'][k][s] - dE['schema2'][k][s] for s in seeds_d]
        r = ref['D']['indicators'][k]['stats']['mean']
        out['e1']['D'][k] = {'e1': dict(zip(seeds_d, v)), 'ref': r, 'ratio': abs(np.mean(v) - r) / eps}
        print(f'  {k:28} {np.mean(v):+12.5g} {r:+12.5g}   {abs(np.mean(v) - r) / eps:5.2f}')

    # ---- gate 2: baseline end state
    print(f'\n== {L} gate 2, baseline end state: {L} mean | RQ1 mean | RQ1 sd | |diff| / max(2sd, m)')
    out['e1']['gate2'] = {}
    for k in GATE2:
        e = [SB[s][0][k] for s in SB]; r = [ref['baseline'][s][k] for s in SEEDS]
        tol = max(2 * np.std(r, ddof=1), 0.0005 if k.startswith('share') else 0)
        out['e1']['gate2'][k] = {'e1': float(np.mean(e)), 'rq1': float(np.mean(r)), 'tol': float(tol),
                                 'ratio': float(abs(np.mean(e) - np.mean(r)) / tol)}
        print(f'  {k:20} {np.mean(e):12.6g} {np.mean(r):12.6g} {np.std(r, ddof=1):10.4g}   {abs(np.mean(e) - np.mean(r)) / tol:6.2f}')

    # ---- trajectories: Delta(t) over a sliding 10-iteration window, cold reference vs E1
    T = {}
    for name, d in list(rq1.items()):
        T[('rq1', name)] = trajectory(d, 100)
    for p in ('schema1', 'schema2'):
        for s, d in cold[p].items():
            T[(p, s)] = trajectory(d, 100)
    for p, runs in E.items():
        for s, d in runs.items():
            T[('e1-' + p, s)] = trajectory(d, 100)
    print('\n== first window start t (t..t+9) where the seed-mean Delta is within eps of the final reference Delta, all of '
          + ', '.join(TRAJ))
    out['first_within'] = {}
    for p in ('schema1', 'schema2'):
        target = {k: float(np.mean(list(ref['policies'][p]['indicators'][k]['delta'].values()))) for k in TRAJ}
        for label, bkey, pkey, seeds in (('cold', 'rq1', p, SEEDS),
                                         (L, 'e1-baseline', 'e1-' + p, [s for s in E[p] if s in E['baseline']])):
            first = {}
            for k in TRAJ + ('all',):
                ks = TRAJ if k == 'all' else (k,)
                hit = None
                for t in range(91):
                    ok = all(abs(np.mean([win(T[(pkey, s)], kk, t) - win(T[(bkey, s)], kk, t) for s in seeds]) - target[kk])
                             <= EPS[p][kk] for kk in ks)
                    if ok:
                        hit = t; break
                first[k] = hit
            out['first_within'][f'{p}-{label}'] = first
            print(f'  {p:8} {label:5} ' + '  '.join(f'{k}={v}' for k, v in first.items()))
    print('\n== mean executed score, seed mean, at iterations 10/20/40/60/79/89/99 (10-iteration window ending there)')
    for key in ('rq1', 'e1-baseline', 'schema1', 'e1-schema1', 'schema2', 'e1-schema2'):
        seeds = [s for (n, s) in T if n == key]
        vals = [float(np.mean([win(T[(key, s)], 'score', t - 9) for s in seeds])) for t in (10, 20, 40, 60, 79, 89, 99)]
        out.setdefault('score_path', {})[key] = vals
        print(f'  {key:12} ' + ' '.join(f'{v:8.3f}' for v in vals))

    # ---- X1: selection-only continuation of the baselines
    print('\n== X1 (selection only, 50 iterations after RQ1 baseline it 99): 10-iteration block means minus RQ1 90-99')
    out['x1'] = {}
    for s in SEEDS:
        d = P/f'x1-baseline-s{s}-from99-50it'
        if n_iters(d) < 50:
            print('  incomplete', d); continue
        x = trajectory(d, 50); r = T[('rq1', s)]
        rows = {}
        for k in ('score', 'share_car', 'share_pt', 'cordon_entries', 'wait_person_hours'):
            base = win(r, k, 90)
            rows[k] = [win(x, k, b) - base for b in range(0, 50, 10)]
        out['x1'][s] = rows
        print(f'  seed {s}: ' + ' | '.join(f"{k} " + ' '.join(f'{v:+.4g}' for v in vals) for k, vals in rows.items()))

    # ---- W1: warm-started policies vs cold references, 90-99
    print('\n== W1 minus cold reference, 90-99 window')
    out['w1'] = {}
    for p in ('schema1', 'schema2'):
        for s in SEEDS:
            w = P/f'warm-{p}-s{s}-100it'
            if n_iters(w) < 100:
                print('  incomplete', w); continue
            x = trajectory(w, 100); c = T[(p, s)]
            diff = {k: win(x, k, 90) - win(c, k, 90) for k in ('share_car', 'share_pt', 'cordon_entries', 'revenue', 'wait_person_hours', 'score')}
            out['w1'][f'{p}-{s}'] = diff
            print(f'  {p} {s}: ' + '  '.join(f'{k} {v:+.4g}' for k, v in diff.items()))
    Path(a.out).write_text(json.dumps(out, indent=1, default=float) + '\n')
    print('\nwrote', a.out)


if __name__ == '__main__':
    main()

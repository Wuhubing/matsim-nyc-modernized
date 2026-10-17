#!/usr/bin/env python3
"""Synthetic checks for compute_deltas.py, replay_stop.py and o4_reroute_threshold.py with hand-computable answers.

  L2SEG_DIR=/path/to/experiments/l2seg python test_new_scripts.py"""
import csv, gzip, json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_o_scripts as T          # reuses the synthetic run of the O1-O3 tests for O4

MODES = ('car', 'pt', 'walk', 'taxi', 'FHV', 'ride', 'bike', 'cb')


def gz(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', newline='') as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def make_run(d, its, car, pt, revenue, scores, drift=0.0):
    """Constant indicators per iteration (car/pt legs for every group), plus an optional drift of car legs before 10."""
    sim = d/'simulation'
    for it in its:
        c = car + (drift * (10 - it) if it < 10 else 0)
        dep = {m: 0 for m in MODES}; dep['car'] = c; dep['pt'] = pt; dep['walk'] = 100
        (sim).mkdir(parents=True, exist_ok=True)
        (sim/f'iteration-metrics-{it}.json').write_text(json.dumps({
            'departures': dep, 'private_car_entry_crossings': c / 2, 'net_congestion_revenue': revenue,
            'unfinished_all': 10, 'mean_completed_car_leg_seconds': 600, 'censored_wait_person_hours': 50}))
        rows = []
        for g in ('all', 'charging:related', 'charging:unrelated'):
            for m in MODES:
                rows.append([g, m, dep[m], dep[m], 0, 0])
        gz(sim/'research'/f'group-modes-{it}.csv.gz', ['group', 'leg_mode', 'departures', 'completed', 'stuck', 'completed_seconds'], rows)
        tot = sum(scores)
        gz(sim/'research'/f'groups-{it}.csv.gz', ['group', 'persons', 'score_sum'], [['all', len(scores), tot]])
        gz(sim/'research'/f'persons-{it}.csv.gz', ['person_id', 'subpopulation', 'charging_cohort', 'score'],
           [[f'p{i}', 'man' if i % 2 == 0 else 'nonman', 'related' if i < 2 else 'unrelated', s] for i, s in enumerate(scores)])


def run(script, *args):
    r = subprocess.run([sys.executable, str(HERE/script), *args], capture_output=True, text=True, env=os.environ)
    if r.returncode:
        print(r.stdout, r.stderr); raise SystemExit(f'{script} failed')
    return r.stdout


def close(a, b, tol=1e-9):
    assert abs(a - b) < tol, (a, b)


def main():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d); its = range(0, 20)
        # baseline seeds 1, 2; P1 = baseline with 10 fewer car legs, revenue 100; P2 = 20 fewer car legs, revenue 150
        # person scores: baseline [10, 10, 10, 10]; P1 [9, 11, 10, 8] -> loser share related (p0, p1) = 0.5, all = 0.5
        for s, extra in ((1, 0), (2, 4)):
            make_run(d/f'B{s}', its, 200 + extra, 50, 0, [10, 10, 10, 10])
            make_run(d/f'P1_{s}', its, 190 + extra, 60, 100, [9, 11, 10, 8])
            make_run(d/f'P2_{s}', its, 180 + extra, 70, 150, [8, 10, 10, 10])
        run('compute_deltas.py', '--baseline', f'1={d}/B1', f'2={d}/B2',
            '--policy', f'P1:1={d}/P1_1', f'P1:2={d}/P1_2', f'P2:1={d}/P2_1', f'P2:2={d}/P2_2',
            '--window', '10-19', '--out', f'{d}/delta.json')
        o = json.loads((d/'delta.json').read_text())
        p1 = o['policies']['P1']['indicators']
        close(p1['legs_car_charging:related']['delta_stats']['mean'], -10)
        close(p1['legs_car_charging:related']['delta_stats']['sd'], 0)       # paired: identical Delta across seeds
        assert p1['legs_car_charging:related']['unpaired_var'] > 0              # unpaired sees the seed offset (+4)
        close(p1['revenue']['delta_stats']['mean'], 100)
        close(p1['loser_share_charging:related']['delta_stats']['mean'], 0.5)
        close(p1['loser_share_all']['delta_stats']['mean'], 0.5)
        # usd: p0 man (0.062227) -1 -> -16.07; p1 nonman +1 -> +18.386; related mean = (-1/0.062227 + 1/0.0543894) / 2
        close(p1['usd_charging:related']['delta_stats']['mean'], (-1 / 0.062227 + 1 / 0.0543894) / 2, 1e-6)
        close(o['D']['indicators']['legs_car_charging:related']['stats']['mean'], 10)      # (-10) - (-20)
        close(o['D']['indicators']['revenue']['stats']['mean'], -50)
        print('compute_deltas ok')
        # replay: two runs whose car legs drift before iteration 10 and are flat afterwards
        make_run(d/'R1', range(0, 40), 200, 50, 0, [10, 10, 10, 10], drift=5)
        make_run(d/'R2', range(0, 40), 202, 50, 0, [10, 10, 10, 11], drift=5)
        run('replay_stop.py', f'1={d}/R1', f'2={d}/R2', '--out', f'{d}/stop.json', '--ref-window', '30-39', '--switch-off', '20')
        st = json.loads((d/'stop.json').read_text())
        for s in ('1', '2'):
            r = st['runs'][s]
            assert r['T_star'] is not None and 5 <= r['T_star'] <= 10, r['T_star']   # 10-iteration mean: windows from 7 already mostly flat
            t = r['C1_H10_L5_K3_after_switch_off']['stop']
            assert t is not None and t >= 20, t
        print('replay_stop ok')
        # O4 on the O1-O3 synthetic run: one re-route, predicted 40/61 (> 40% bin), realised -20/41
        rd = d/'o4run'; T.build(rd)
        run('o4_reroute_threshold.py', str(rd), '--out', f'{d}/o4.json', '--ks', '10')
        o4 = json.loads((d/'o4.json').read_text())['pooled']
        assert o4['n'] == 1 and o4['bins']['> 40%']['n'] == 1
        close(o4['bins']['> 40%']['mean_realised'], -20 / 41)
        assert o4['bins']['> 40%']['realised_positive'] == 0.0
        close(o4['thresholds']['0.20']['kept_share'], 1.0)
        print('o4 ok')


if __name__ == '__main__':
    main()

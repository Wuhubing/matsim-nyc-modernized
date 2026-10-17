#!/usr/bin/env python3
"""Synthetic checks for o1_elite_parent.py, o2_staleness.py and o3_overshoot.py with hand-computable answers.

  L2SEG_DIR=/path/to/experiments/l2seg python test_o_scripts.py"""
import csv, gzip, io, json, os, subprocess, sys, tempfile
from pathlib import Path
import zstandard

HERE = Path(__file__).resolve().parent
B36 = lambda n: format(n, 'x') if n < 10 else ('0123456789abcdefghijklmnopqrstuvwxyz'[n] if n < 36 else str(n))


def gz_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', newline='') as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def zst(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zstandard.ZstdCompressor().compress(text.encode()))


def plan_xml(pid, created, score, legs=()):
    s = '' if score is None else f' score="{score}"'
    body = ''.join(f'<activity type="h"/><leg mode="car" dep_time="{d}"><route type="links" trav_time="{tt}">{r}</route></leg>'
                   for d, r, tt in legs)
    return (f'<plan{s}><attributes><attribute name="planId" class="java.lang.String">{pid}</attribute>'
            f'<attribute name="iterationCreated" class="java.lang.Integer">{created}</attribute></attributes>{body}<activity type="h"/></plan>')


def build(run):
    sim = run/'simulation'; rl = sim/'replanning-log'
    gz_csv(rl/'persons.csv.gz', ['person', 'person_id', 'subpopulation'],
           [[0, 'a', 'man'], [1, 'b', 'nonman'], [2, 'c', 'man'], [3, 'o', 'outside']])
    rl.mkdir(parents=True, exist_ok=True)
    with open(rl/'strategies.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['strategy', 'innovative', 'description'])
        w.writerows([[0, 0, 'ExpBetaPlanSelector'], [1, 1, 'RandomPlanSelector_ReRoute'],
                     [2, 1, 'RandomPlanSelector_TimeAllocationMutator'], [3, 1, 'RandomPlanSelector_SubtourModeChoice_ReRoute']])
    head = ['person', 'strategy', 'plan_id', 'plan_created', 'parent_plan_id', 'executed_score', 'best_score', 'plans']
    # O2 history (iterations 0..12): person a executes plan 1 at 0 (score 10), plan 2 at 1..4, plan 1 again at 5 (score 7)
    #   -> re-execution of plan 1 with age 5 and diff -3; plan 2 consecutive -> age 1 diffs 0.5 each.
    # person b executes plan 3 every iteration, score rising by 1 -> age 1 diffs +1.
    for t in range(0, 13):
        rows = []
        pa, sa = (1, 10.0) if t == 0 else ((1, 7.0) if t == 5 else (2, 8.0 + 0.5 * t))
        rows.append([0, 0 if t else -1, B36(pa), 0, '', sa, 12.0, 3])
        rows.append([1, 0 if t else -1, B36(3), 0, '', 5.0 + t, 6.0 + t, 2])
        rows.append([2, 0 if t else -1, B36(4), 0, '', 1.0, 1.0, 1])
        rows.append([3, 0 if t else -1, B36(5), 0, '', 0.0, 0.0, 1])
        if t == 10:
            # O1/O3 innovations at k = 10:
            # a: ReRoute from parent plan 2 (stored 9, best 12 -> rank 2), executed 13 vs best(9)=12 -> delta +1 (better)
            # b: TimeAllocationMutator from parent plan 3 (stored 14 = best -> rank 1), executed 10 vs best(9)=15 -> delta -5
            rows[0] = [0, 1, B36(2), 10, B36(2), 13.0, 13.0, 4]
            rows[1] = [1, 2, B36(3), 10, B36(3), 10.0, 15.0, 3]
        gz_csv(rl/f'agents-{t}.csv.gz', head, rows)
    # snapshot at k = 10 (after replanning of 10): a has plans 1 (12), 2 parent (9), 2 new (created 10, score 9 inherited)
    links_parent = 'L0 L1 L2 L9'; links_new = 'L0 L3 L9'
    snap = ('<?xml version="1.0"?><population>'
            '<person id="a">' + plan_xml(B36(1), 0, 12.0) +
            plan_xml(B36(2), 0, 9.0, [('08:00:00', links_parent, '00:01:40')]) +
            plan_xml(B36(2), 10, 9.0, [('08:00:00', links_new, '00:00:50')]) + '</person>'
            '<person id="b">' + plan_xml(B36(3), 0, 14.0) + plan_xml(B36(7), 0, 11.0) + plan_xml(B36(3), 10, 14.0) + '</person>'
            '<person id="c">' + plan_xml(B36(4), 0, 1.0) + '</person></population>')
    zst(sim/'ITERS'/'it.10'/'BUILT.10.plans.xml.zst', snap)
    # network: L1, L2, L3 length 100 m, free speed 10 m/s (10 s); start and end links L0, L9 length 10 m at 10 m/s
    net = ('<network><links>' + ''.join(f'<link id="{l}" length="{ln}" freespeed="10"/>' for l, ln in
           (('L0', 10), ('L1', 100), ('L2', 100), ('L3', 100), ('L9', 10))) + '</links></network>')
    zst(sim/'BUILT.output_network.xml.zst', net)
    # link-hour fields at 8h. Parent route = L1 + L2 (+1 s end link), new route = L3 (+1 s).
    #   T(9):  L1 30, L2 30, L3 20 -> parent 61, new 21 -> gain 40/61
    #   T(10): L1 20, L2 20, L3 60 -> parent 41, new 61 -> gain -20/41 (overshoot: everyone moved to L3)
    #   T(11): L1 25, L2 25, L3 25 -> parent 51, new 26 -> gain 25/51
    lhh = ['link_id', 'entry_hour', 'network_mode', 'entries', 'completed_traversals', 'total_traversal_seconds']
    for t, (a1, a2, a3) in {9: (30, 30, 20), 10: (20, 20, 60), 11: (25, 25, 25)}.items():
        gz_csv(sim/'research'/f'link-hours-{t}.csv.gz', lhh,
               [['L1', 8, 'car', 1, 1, a1], ['L2', 8, 'car', 1, 1, a2], ['L3', 8, 'car', 1, 1, a3]])


def run(script, *args):
    r = subprocess.run([sys.executable, str(HERE/script), *args], capture_output=True, text=True, env=os.environ)
    if r.returncode:
        print(r.stdout, r.stderr); raise SystemExit(f'{script} failed')
    return r.stdout


def close(a, b, tol=1e-9):
    assert abs(a - b) < tol, (a, b)


def main():
    with tempfile.TemporaryDirectory() as d:
        run_dir = Path(d)/'run'; build(run_dir)
        # O1
        run('o1_elite_parent.py', str(run_dir), '--out', f'{d}/o1.json', '--ks', '10')
        o1 = json.loads(Path(f'{d}/o1.json').read_text())['pooled']
        assert o1['all']['n'] == 2, o1['all']
        close(o1['all']['share_best_parent'], 0.5)
        assert o1['all']['best_parent']['n'] == 1 and o1['all']['best_parent']['better_share'] == 0.0
        assert o1['all']['best_parent']['worse3_share'] == 1.0
        assert o1['all']['other_parent']['better_share'] == 1.0
        assert o1['route']['n'] == 1 and o1['time']['n'] == 1
        assert o1['all']['by_gap']['gap (-5, -2]']['n'] == 1      # a: 9 - 12 = -3
        print('O1 ok')
        # O2
        run('o2_staleness.py', str(run_dir), '--out', f'{d}/o2.json', '--last', '12', '--switch-off', '8')
        o2 = json.loads(Path(f'{d}/o2.json').read_text())['phases']
        inn = o2['innovation']['by_age']
        # innovation phase t < 8: a plan 2 consecutive t=2..4 (3 x +0.5), plan1 age 5 diff -3 at t=5,
        #   plan 2 again at t=6 (age 2 from t=4: 8+3 - 8+2 = +1), t=7 (+0.5); b t=1..7 (7 x +1)
        assert inn['5']['n'] if '5' in inn else True
        assert inn['3-5']['n'] == 1 and abs(inn['3-5']['mean'] + 3.0) < 1e-9, inn['3-5']
        assert inn['2']['n'] == 1 and abs(inn['2']['mean'] - 1.0) < 1e-9, inn['2']
        assert inn['1']['n'] == 4 + 7 + 7 and abs(inn['1']['mean'] - 0.5) < 1e-9, inn['1']   # a: 4, b: 7 (+1), c: 7 (0)
        print('O2 ok')
        # O3
        run('o3_overshoot.py', str(run_dir), '--out', f'{d}/o3.json', '--ks', '10')
        o3 = json.loads(Path(f'{d}/o3.json').read_text())['by_k']['10']
        close(o3['predicted_T(k-1)']['all']['gain'], 40 / 61)
        close(o3['realised_T(k)']['all']['gain'], -20 / 41)
        close(o3['next_T(k+1)']['all']['gain'], 25 / 51)
        assert o3['predicted_T(k-1)']['executed']['legs'] == 1    # parent plan 2 was executed at 9
        print('O3 ok')


if __name__ == '__main__':
    main()

"""Synthetic checks for A2-A4 (run: .venv/bin/python -m unittest experiments/l2seg/test_aggregate.py)."""
import csv, gzip, json, subprocess, sys, tempfile, unittest
from pathlib import Path
import numpy as np
import zstandard
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan_snapshots, group_stability, link_stability

PY = sys.executable


def act(t, x, y, end=None):
    return f'<activity type="{t}" link="l1" x="{x}" y="{y}"' + (f' end_time="{end}"' if end else '') + ' ></activity>'


def leg(mode, dep='08:00:00', route=None):
    r = f'<route type="links" start_link="a" end_link="b">{route}</route>' if route else '<route type="generic"></route>'
    return f'<leg mode="{mode}" dep_time="{dep}">{r}</leg>'


def plan(body, score=None, selected=False, pid='1', created=0, mutator='initialPlan'):
    s = f' score="{score}"' if score is not None else ''
    return (f'<plan{s} selected="{"yes" if selected else "no"}"><attributes>'
            f'<attribute name="iterationCreated" class="java.lang.Integer">{created}</attribute>'
            f'<attribute name="planId" class="java.lang.String">{pid}</attribute>'
            f'<attribute name="planMutator" class="java.lang.String">{mutator}</attribute></attributes>{body}</plan>')


def person(pid, sub, plans):
    return (f'<person id="{pid}"><attributes><attribute name="subpopulation" class="java.lang.String">{sub}</attribute>'
            f'</attributes>{"".join(plans)}</person>')


def write_plans(path, persons):
    path.parent.mkdir(parents=True, exist_ok=True)
    xml = '<?xml version="1.0"?><population>' + ''.join(persons) + '</population>'
    path.write_bytes(zstandard.ZstdCompressor().compress(xml.encode()))


def gz(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt') as f:
        f.write(header + '\n'); f.writelines(','.join(str(x) for x in r) + '\n' for r in rows)


# person a: home -> work by car (selected, score 1) or pt (score 3, best); work is primary, departs 07:30
CAR = act('Home', 0, 0, '07:30:00') + leg('walk') + act('car interaction', 0, 0) + leg('car') + act('Work', 25000, 5000, '17:00:00') + leg('car') + act('Home', 0, 0)
PT = act('Home', 0, 0, '07:30:00') + leg('walk') + leg('pt') + leg('walk') + act('Work', 25000, 5000, '17:00:00') + leg('pt') + act('Home', 0, 0)
# person b: a single unscored plan (created this iteration), walking to a Secondary activity
WALK = act('Home', 12000, 0, '10:00:00') + leg('walk') + act('Secondary', 13000, 0, '11:00:00') + leg('walk') + act('Home', 12000, 0)


class Snapshots(unittest.TestCase):
    def test_summary_and_attributes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'p.xml.zst'
            write_plans(p, [person('a', 'man', [plan(CAR, 1.0, True), plan(PT, 3.0, pid='2')]), person('b', 'nonman', [plan(WALK, None, True)])])
            snap, attrs = plan_snapshots.summarise(p, True)
        car, pt, walk = (plan_snapshots.MODES.index(m) for m in ('car', 'pt', 'walk'))
        self.assertEqual(list(snap['id']), ['a', 'b'])
        self.assertEqual(snap['sel'][0, car], 2); self.assertEqual(snap['best'][0, pt], 2); self.assertEqual(snap['best'][0, car], 0)
        self.assertEqual(snap['best_score'][0], 3.0); self.assertTrue(np.isnan(snap['best_score'][1]))
        self.assertEqual(snap['best'][1, walk], 2)                       # unscored -> selected plan
        self.assertEqual((attrs['prim_x'][0], attrs['departure'][0], attrs['trips'][0]), (25000.0, 7.5 * 3600, 2))
        self.assertEqual((attrs['prim_x'][1], attrs['home_x'][1]), (13000.0, 12000.0))   # no Work -> first non-Home


class Groups(unittest.TestCase):
    def test_assign_falls_back(self):
        fine = np.array(['x', 'x', 'x', 'y', 'z'], dtype=object); coarse = np.array(['c'] * 5, dtype=object)
        self.assertEqual(list(group_stability.assign([fine, coarse], 3)), ['x', 'x', 'x', 'c', 'c'])

    def test_settle_score(self):
        t = np.arange(100.0)
        early = np.where(t < 20, t, 20.0); late = np.where(t < 60, t, 60.0)           # plateau from 20 resp. 60
        ts = group_stability.settle_score(np.stack([early, late, np.ones(100)]), 0.1)
        self.assertTrue(20 <= ts[0] < 30 and 60 <= ts[1] < 70, ts); self.assertTrue(np.isnan(ts[2]))

    def test_settle_mode(self):
        ref = np.array([[0.5, 0.5]] * 2)
        best = np.array([[[0.9, 0.1], [0.5, 0.5]] + [[0.5, 0.5]] * 5, [[0.5, 0.5]] * 6 + [[0.9, 0.1]]])   # snapshots 10..70
        self.assertEqual(list(group_stability.settle_mode(best, ref, 0.05)), [20.0, 80.0])

    def test_end_to_end(self):
        """Two groups by home cell; group 'early' settles at 20, 'late' at 60, same in both runs."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); runs, snaps = [], []
            ids = [f'p{i}' for i in range(8)]; early = [i < 4 for i in range(8)]
            for r in range(2):
                run, sd = d/f'run{r}', d/f'snap{r}'; sd.mkdir(); runs.append(str(run)); snaps.append(str(sd))
                res = run/'simulation'/'research'
                gz(res/'cohorts.csv.gz', 'person_id,subpopulation,charging_cohort', [(p, 'man', 'related') for p in ids])
                for t in range(100):
                    gz(res/f'persons-{t}.csv.gz', 'person_id,score,choice_changed',
                       [(p, min(t, 20 if e else 60) + 0.01 * r, '' if t == 0 else 'True') for p, e in zip(ids, early)])
                np.savez(sd/'persons.npz', id=np.array(ids), subpopulation=np.array(['man'] * 8),
                         home_x=np.array([0.0 if e else 50000.0 for e in early]), home_y=np.zeros(8),
                         prim_x=np.zeros(8), prim_y=np.zeros(8), departure=np.full(8, 8 * 3600.0), trips=np.full(8, 2))
                for k in group_stability.SNAPS:
                    best = np.array([[2, 0, 0, 0, 0, 0, 0, 0] if (e and k >= 20) or (not e and k >= 60) else [0, 0, 0, 2, 0, 0, 0, 0] for e in early], np.int16)
                    np.savez(sd/f'snap-{k}.npz', id=np.array(ids), sel=best, best=best, sel_score=np.zeros(8), best_score=np.full(8, float(k)), plans=np.ones(8))
            out = d/'g.json'
            subprocess.run([PY, str(HERE/'group_stability.py'), '--runs', *runs, '--snaps', *snaps, '--out', str(out), '--min-size', '2'],
                           check=True, capture_output=True)
            res = json.loads(out.read_text())['groupings']['home']
        self.assertEqual(res['groups'], 2)
        tab = {row['group']: row for row in res['table']}
        tm = sorted((row['mode_tau0.05'][0], row['persons']) for row in tab.values())
        self.assertEqual(tm, [(20.0, 4), (60.0, 4)])
        self.assertAlmostEqual(res['settling']['mode_tau0.05']['settled_by']['30'], 0.5)


class Priorities(unittest.TestCase):
    def test_m3_files(self):
        """Home cells A (settled at 20 in the reference runs) and B (60); the steered seed's own column is ignored."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); sd = d/'snap'; sd.mkdir(); run = d/'run'
            ids = ['a1', 'a2', 'b1', 'b2', 'o1']
            np.savez(sd/'persons.npz', id=np.array(ids), subpopulation=np.array(['man', 'man', 'nonman', 'nonman', 'outside']),
                     home_x=np.array([0.0, 0.0, 50000.0, 50000.0, 0.0]), home_y=np.zeros(5), prim_x=np.zeros(5), prim_y=np.zeros(5),
                     departure=np.full(5, 8 * 3600.0), trips=np.full(5, 2))
            gz(run/'simulation'/'research'/'cohorts.csv.gz', 'person_id,subpopulation,charging_cohort', [(p, 's', 'related') for p in ids])
            a3 = {'runs': ['/x/baseline-s4711', '/x/baseline-s4712', '/x/baseline-s4713'],
                  'params': {'cell_ft': 10000, 'od_cell_ft': 20000, 'min_size': 1},
                  'groupings': {'home': {'table': [{'group': 'man|h|0_0', 'mode_tau0.05': [99.0, 20.0, 20.0]},
                                                   {'group': 'nonman|h|5_0', 'mode_tau0.05': [99.0, 60.0, 40.0]}]}}}
            (d/'a3.json').write_text(json.dumps(a3))
            def run_it(out, *extra):
                subprocess.run([PY, str(HERE/'m3_priorities.py'), str(d/'a3.json'), '--snaps', str(sd), '--run', str(run), '--out', str(d/out),
                                '--grouping', 'home', '--last', '60', *extra], check=True, capture_output=True)
                read = lambda t: dict(csv.reader(gzip.open(d/out/f'priority-{t}.csv.gz', 'rt')))
                return read, json.loads((d/out/'summary.json').read_text())
            read, summary = run_it('bin')
            self.assertEqual(read(30), {'person_id': 'priority', 'a1': '0', 'a2': '0', 'b1': '1', 'b2': '1'})   # B median 50
            self.assertEqual(read(10)['a1'], '1'); self.assertEqual(read(55)['b1'], '0')
            self.assertEqual(summary['share_with_priority']['30'], {'man': 0.0, 'nonman': 1.0})
            self.assertEqual(len(summary['reference_runs']), 2)
            read, _ = run_it('rem', '--mode', 'remaining', '--agg', 'max')
            self.assertEqual((read(30)['a1'], read(30)['b1']), ('0', '30'))                                          # B max 60
            read, _ = run_it('plc', '--placebo', '1')
            self.assertEqual(sorted({read(30)['a1'], read(30)['b1']}), ['0', '1'])                                    # permuted, still one of each


class Links(unittest.TestCase):
    def test_end_to_end(self):
        """Persons x and y re-route at 11 from parents created at 5 (by ReRoute). x's links keep their travel time and
        x's re-route is a duplicate; y's links double and y gets a new route."""
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)/'run'; sim = run/'simulation'; res = sim/'research'; log = sim/'replanning-log'
            for t in range(100):
                gz(res/f'link-hours-{t}.csv.gz', 'link_id,entry_hour,network_mode,entries,completed_traversals,total_traversal_seconds',
                   [('"L1"', 8, '"car"', 10, 10, 100.0), ('"L2"', 8, '"car"', 10, 10, 100.0 if t < 7 else 200.0)])
            gz(log/'persons.csv.gz', 'person,person_id,subpopulation', [(0, 'x', 'man'), (1, 'y', 'man'), (2, 'z', 'man')])
            log.mkdir(parents=True, exist_ok=True)
            (log/'strategies.csv').write_text('strategy,innovative,description\n0,0,"ExpBetaPlanSelector"\n2,1,"RandomPlanSelector_ReRoute"\n')
            gz(log/'agents-11.csv.gz', 'person,strategy,plan_id,plan_created,parent_plan_id,executed_score,best_score,plans',
               [(0, 2, 'b', 11, 'a', 0, 0, 2), (1, 2, 'd', 11, 'c', 0, 0, 2), (2, 0, 'e', 0, '', 0, 0, 1)])
            gz(log/'trips-11.csv.gz', 'person,trip,mode_changed,route_changed,est_tt_before,est_tt_after', [(0, 0, 0, 0, 1, 1), (1, 0, 0, 1, 1, 1)])
            body = lambda links: act('Home', 0, 0, '08:00:00') + leg('car', '08:00:00', links) + act('Work', 1, 1)
            write_plans(sim/'ITERS'/'it.10'/'BUILT.10.plans.xml.zst',
                        [person('x', 'man', [plan(body('L1'), 1.0, True, 'a', 5, 'RandomPlanSelector_ReRoute')]),
                         person('y', 'man', [plan(body('L1 L2'), 1.0, True, 'c', 5, 'RandomPlanSelector_ReRoute')]),
                         person('z', 'man', [plan(body('L1'), 1.0, True, 'e', 0)])])
            out = Path(d)/'l.json'
            subprocess.run([PY, str(HERE/'link_stability.py'), str(run), '--out', str(out), '--ts', '10', '--min-traversals', '1'],
                           check=True, capture_output=True)
            r = json.loads(out.read_text())
        p2 = r['part2']['10']
        self.assertEqual((p2['innovations'], p2['duplicate_share']), (2, 0.5))
        self.assertEqual(p2['since']['auc'], 1.0)
        th = {x['e']: x for x in p2['since']['thresholds']}
        self.assertEqual((th[0.01]['skippable_share'], th[0.01]['precision']), (0.5, 1.0))    # only x: change 0
        p1 = r['part1']
        self.assertEqual(p1['by_iteration']['7']['prev_within_0.1'], 0.5)                       # L2 doubled at 7
        self.assertEqual(p1['settled_by']['0.05']['10'], 1.0)


if __name__ == '__main__':
    unittest.main()

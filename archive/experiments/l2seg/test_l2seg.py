"""Synthetic checks for W4 (run: .venv/bin/python -m unittest experiments/l2seg/test_l2seg.py)."""
import csv, gzip, json, sys, tempfile, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import labels, tolerance, features
from logs import ReplanningLog


def write_log(run, persons, agents):
    """persons: [(index, id, subpop)]; agents: {it: [(person, strategy, plan_id, created, parent, executed, best, plans)]}."""
    d = Path(run)/'simulation'/'replanning-log'; d.mkdir(parents=True)
    with gzip.open(d/'persons.csv.gz', 'wt') as f:
        f.write('person,person_id,subpopulation\n'); f.writelines(f'{i},{p},{s}\n' for i, p, s in persons)
    (d/'strategies.csv').write_text('strategy,innovative,description\n0,0,"select"\n1,1,"reroute"\n')
    for it, rows in agents.items():
        with gzip.open(d/f'agents-{it}.csv.gz', 'wt') as f:
            f.write('person,strategy,plan_id,plan_created,parent_plan_id,executed_score,best_score,plans\n')
            f.writelines(','.join(str(x) for x in r) + '\n' for r in rows)


def write_stats(run, values):
    """values: {it: {'score': x, 'car': share, 'entries': n}}; other indicators constant."""
    sim = Path(run)/'simulation'; sim.mkdir(parents=True, exist_ok=True)
    (sim/'BUILT.scorestats.csv').write_text('iteration;avg_executed;avg_worst;avg_average;avg_best\n'
                                            + ''.join(f"{i};{v['score']};0;0;0\n" for i, v in values.items()))
    (sim/'BUILT.modestats.csv').write_text('iteration;car;pt\n' + ''.join(f"{i};{v['car']};{1 - v['car']}\n" for i, v in values.items()))
    for i, v in values.items():
        (sim/f'iteration-metrics-{i}.json').write_text(json.dumps({'departures': {'car': 10}, 'completed': {'car': 9}, 'unfinished_all': 1,
            'private_car_entry_crossings': v['entries'], 'net_congestion_revenue': 0.0, 'censored_wait_person_hours': 2.0}))


class Labels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); run = self.tmp.name
        # a: innovates at 1 (plan 2), reselected at 3 with score 5 > best before (1) -> L-U positive; ends on plan 1 (created 0).
        # b: innovates at 1 (plan 4), never selected again -> L-U negative; final plan (3) created 0.
        # c: innovates at 13 -> censored with horizon 10 and last iteration 14; final plan created 13.
        # o: outside, never innovates.
        T = 15; agents = {}
        for t in range(T):
            a = (1, 2, 1, '1' if t == 1 else '', 5.0 if t == 3 else 0.5, 5.0 if t >= 3 else 1.0, 2) if t in (1, 3) else (0 if t else -1, 1, 0, '', 1.0, 1.0 if t < 3 else 5.0, 1 if t == 0 else 2)
            b = (1, 4, 1, '3', 0.0, 2.0, 2) if t == 1 else (0 if t else -1, 3, 0, '', 2.0, 2.0, 1 if t == 0 else 2)
            c = (1, 6, 13, '5', 1.0, 1.0, 2) if t == 13 else ((0, 6, 13, '', 1.0, 1.0, 2) if t == 14 else (0 if t else -1, 5, 0, '', 1.0, 1.0, 1))
            o = (0 if t else -1, 7, 0, '', 0.0, 0.0, 1)
            agents[t] = [(10, *a), (11, *b), (12, *c), (13, *o)]
        write_log(run, [(10, 'a', 'man'), (11, 'b', 'man'), (12, 'c', 'nonman'), (13, 'o', 'outside')], agents)
        self.log = ReplanningLog(run); self.its, self.d = labels.load(self.log)

    def tearDown(self): self.tmp.cleanup()

    def test_lh(self):
        lh = labels.label_lh(self.d['created'])
        self.assertFalse(lh[:, 0].any())                                   # a: back on plan 1 (created 0) at the end
        self.assertFalse(lh[:, 1].any())                                   # b: final plan created at 0
        self.assertEqual(lh[:, 2].tolist(), [True] * 13 + [False] * 2)     # c: created at 13

    def test_lu(self):
        t, r, lu = labels.label_lu(self.d, horizon=10, delta=0.0)
        got = {(int(i), int(k)): bool(v) for i, k, v in zip(t, r, lu)}
        self.assertEqual(got, {(1, 0): True, (1, 1): False})               # c censored, o never innovates
        _, _, lu_hi = labels.label_lu(self.d, horizon=10, delta=10.0)
        self.assertFalse(lu_hi.any())                                      # delta raises the bar

    def test_stability_and_features(self):
        lh = labels.label_lh(self.d['created'])
        rows = labels.stability(self.its, self.d, lh, {'innovating': self.log.subpopulation != 'outside'})
        self.assertAlmostEqual(rows[1]['innovated'], 2 / 3); self.assertAlmostEqual(rows[2]['revisit'], 2 / 3)
        f = features.features(self.log, self.d, self.its, 3)
        self.assertEqual(f['age'][0], 2); self.assertEqual(f['switches_last5'][0], 3)   # 1->2 (t1), 2->1 (t2), 1->2 (t3)
        self.assertAlmostEqual(f['executed_minus_best'][0], 0.0); self.assertEqual(f['innovations_last5'][1], 1)


class Tolerance(unittest.TestCase):
    def test_table_tstar_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = []
            for k, offset in enumerate([-1.0, 0.0, 1.0]):          # window means differ by seed: sigma = 1 on score
                run = Path(tmp)/f'r{k}'
                write_stats(run, {i: {'score': (100.0 if i < 6 else 10.0 + offset), 'car': 0.3, 'entries': 50} for i in range(20)})
                runs.append(run)
            table, series = tolerance.build_table(runs, 10, 19)
            self.assertAlmostEqual(table['score']['mean'], 10.0); self.assertAlmostEqual(table['score']['sigma'], 1.0)
            self.assertEqual(table['share_car']['sigma'], 0.0)
            self.assertEqual(tolerance.steady_state(series[1], table), 6)  # first of 5 consecutive iterations inside
            ok, _ = tolerance.match(series[2], table); self.assertTrue(ok)
            off = Path(tmp)/'off'; write_stats(off, {i: {'score': 13.0, 'car': 0.3, 'entries': 50} for i in range(20)})
            ok, detail = tolerance.match(tolerance.indicators(off), table)
            self.assertFalse(ok); self.assertAlmostEqual(detail['score']['z'], 3.0)
            self.assertIsNone(tolerance.steady_state(tolerance.indicators(off), table))


if __name__ == '__main__':
    unittest.main()

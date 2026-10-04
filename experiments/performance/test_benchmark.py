import copy
import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
import benchmark as B

class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.original_source = B.DEFAULT_SOURCE
        B.DEFAULT_SOURCE = Path(cls.tmp.name)
        d = B.DEFAULT_SOURCE/'cold-attempt-1'; d.mkdir()
        (d/'config.xml').write_text((B.ROOT/'scenarios/nyc-zip-aligned/config-actual2025.xml').read_text())

    @classmethod
    def tearDownClass(cls):
        B.DEFAULT_SOURCE = cls.original_source
        cls.tmp.cleanup()

    def test_output_and_threads_whitelist(self):
        base = B.config_tree(B.DEFAULT_SOURCE, Path('/tmp/base'), 'baseline', 1)
        for variant in ['baseline','output','qsim10']:
            candidate = B.config_tree(B.DEFAULT_SOURCE, Path('/tmp/candidate'), variant, 1)
            B.check_configs(base,candidate,variant)
            B.P.setparam(candidate,'qsim','flowCapacityFactor','0.9')
            with self.assertRaises(ValueError): B.check_configs(base,candidate,variant)

    def test_mat_sim_config_declares_dtd(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'config.xml'
            B.write_config(B.config_tree(B.DEFAULT_SOURCE,Path(t),'baseline',1),path)
            self.assertIn('<!DOCTYPE config SYSTEM "http://www.matsim.org/files/dtd/config_v2.dtd">',path.read_text())
            self.assertEqual(ET.parse(path).getroot().tag,'config')

    def test_strict_comparison(self):
        row={'iteration':0,'count_car_entries':10,'revenue_cents':123,'score':-4.,'mode_car':.3}
        self.assertEqual(B.compare_rows([row],[dict(row)]),[])
        for key,value in [('count_car_entries',11),('revenue_cents',124),('score',-3.99),('mode_car',float('nan'))]:
            other=dict(row);other[key]=value
            self.assertTrue(B.compare_rows([row],[other]))
        other=dict(row);other.pop('score')
        self.assertTrue(B.compare_rows([row],[other]))
        self.assertTrue(B.compare_rows([],[]))
        self.assertTrue(B.compare_rows([row],[]))

    def test_hash_change_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'input';p.write_text('a')
            m={'inputs':[{'path':str(p),'sha256':B.D.sha(p)}]}
            B.verify_hashes(m);p.write_text('b')
            with self.assertRaises(ValueError):B.verify_hashes(m)

    def test_candidate_gates_and_output_tie(self):
        rows=[{'iteration':0,'count_car_entries':1,'score':-4.}]
        results={k:copy.deepcopy(rows) for k in ['short-baseline','short-qsim10','short-output']}
        timings={k:{'wall_seconds':v} for k,v in [('short-baseline',100),('short-qsim10',90),('short-output',91)]}
        checks={k:True for k in results}
        self.assertEqual(B.choose_candidate(results,timings,checks),'output')
        results['short-output'][0]['count_car_entries']=2
        self.assertEqual(B.choose_candidate(results,timings,checks),'qsim10')
        timings['short-qsim10']['wall_seconds']=96
        self.assertIsNone(B.choose_candidate(results,timings,checks))

    def test_stale_budget_charged_and_no_retry(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);ledger_path=out/'budget.json'
            old=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=10)).isoformat()
            ledger={'used_seconds':100,'limit_seconds':1000,'updated_utc':old,'active':{'pid':123,'started_utc':old}}
            m={'ledger':str(ledger_path),'attempts':[{'status':'running'}]}
            with patch.object(B.os,'kill',side_effect=ProcessLookupError), self.assertRaises(RuntimeError):
                B.reconcile_stale(out,m,ledger)
            actual=B.read(ledger_path)
            self.assertGreaterEqual(actual['used_seconds'],110)
            self.assertIsNone(actual['active'])
            self.assertEqual(m['attempts'][0]['status'],'interrupted')

    def test_live_pid_not_reconciled(self):
        ledger={'active':{'pid':123},'used_seconds':100}
        with patch.object(B.os,'kill'),self.assertRaises(RuntimeError): B.reconcile_stale(Path('/tmp'),{},ledger)
        self.assertEqual(ledger['used_seconds'],100)

    def test_failed_process_still_charged(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);ledger_path=out/'budget.json'
            ledger={'used_seconds':100,'limit_seconds':1000,'active':None}
            m={'attempts':[],'source':str(B.DEFAULT_SOURCE),'short_limit_seconds':1200,
               'ledger':str(ledger_path),'java_home':'/fake/jdk','inputs':[]}
            class Failed:
                pid=123
                returncode=1
                def poll(self):return 1
                def wait(self):return 1
            sample={'disk_free_bytes':100*B.D.GIB,'pressure_level':1,'swap_used_bytes':0}
            with patch.object(B.D,'system_sample',return_value=sample), patch.object(B.subprocess,'Popen',return_value=Failed()), patch.object(B.time,'monotonic',side_effect=[100,104]), self.assertRaises(RuntimeError):
                B.execute_one(out,m,ledger,'failed','baseline',1,'short')
            self.assertEqual(B.read(ledger_path)['used_seconds'],104)
            self.assertIsNone(B.read(ledger_path)['active'])
            self.assertEqual(m['attempts'][0]['status'],'failed')
            with self.assertRaises(ValueError):B.execute_one(out,m,ledger,'failed','baseline',1,'short')

    def test_existing_directory_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t)/'source';source.mkdir()
            B.D.save(source/'budget.json',{'active':None})
            with self.assertRaises(FileExistsError): B.prepare(source,Path(t))

    def test_analysis_uses_events_not_plan_dumps(self):
        # Both output profiles feed identical metric files; no intermediate or
        # experienced plan file is supplied to this fixture.
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);dest=out/'arm';sim=dest/'simulation';it=sim/'ITERS/it.0';it.mkdir(parents=True)
            (sim/'BUILT.scorestats.csv').write_text('iteration;avg_executed\n0;-4\n')
            (sim/'BUILT.modestats.csv').write_text('iteration;car;pt;taxi;FHV;bike;walk;ride;cb\n0;0.3;0.7;0;0;0;0;0;0\n')
            (sim/'pricing-audit.csv').write_text('iteration,sample_revenue_usd\n0,9.00\n')
            (sim/'BUILT.stopwatch.csv').write_text('iteration;mobsim\n0;00:00:10\n')
            (it/'BUILT.0.legHistogram.txt').write_text('stuck_all;departures_car;arrivals_car\n0;1;1\n')
            (it/'BUILT.0.events.xml').write_text('''<events>
<event time="0" type="departure" person="a" legMode="car" />
<event time="10" type="personMoney" person="a" amount="-9" purpose="toll" />
<event time="30" type="arrival" person="a" legMode="car" />
</events>''')
            (dest/'gc.log').write_text('Pause Young 12.0ms\n')
            (dest/'run.log').write_text('10.0 real 20.0 user 1.0 sys\n')
            a={'name':'arm','iterations':1,'elapsed_seconds':10,'started_utc':B.D.now(),'peak_rss_bytes':100,'profile_overhead':False}
            rows,timing=B.analyze_attempt(out,a,{b'a'},set())
            self.assertEqual(rows[0]['completed_car_total_seconds'],30)
            self.assertEqual(rows[0]['revenue_cents'],900)
            self.assertEqual(timing['gc_pause_seconds'],.012)
            (sim/'BUILT.modestats.csv').write_text('iteration;car;pt\n')
            with self.assertRaises(ValueError):B.analyze_attempt(out,a,{b'a'},set())

if __name__=='__main__':unittest.main()

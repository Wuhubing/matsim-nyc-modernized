import contextlib,csv,importlib.util,io,json,tempfile,unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('reference',Path(__file__).with_name('run_reference.py'));R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)

class ReferenceTests(unittest.TestCase):
    def test_scenarios_schedule_and_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            for scenario in ['baseline','schema1','actual2025']:
                for horizon in [50,100]:
                    cfg=R.write_config(path,4711,horizon,'none',10,16,scenario=scenario,events_interval=10,innovation_until=79)
                    tree=ET.parse(cfg)
                    def val(mod,param):return tree.find(f"./module[@name='{mod}']/param[@name='{param}']").get('value')
                    self.assertEqual(val('controller','writeEventsInterval'),'10')
                    self.assertEqual(val('counts','writeCountsInterval'),'1')
                    self.assertEqual(val('strategy','fractionOfIterationsToDisableInnovation'),'1.0')
                    innovative=[x for x in tree.findall("./module[@name='strategy']/parameterset") if x.find("param[@name='strategyName']").get('value')!='SelectExpBeta']
                    self.assertTrue(innovative)
                    self.assertTrue(all(x.find("param[@name='disableAfter']").get('value')=='79' for x in innovative))
                    if scenario=='baseline':self.assertTrue(val('roadpricing','tollLinksFile').endswith('control-zero-tolls.xml'))
                    if scenario=='actual2025':self.assertTrue(val('nycModel','pricing2025Links').endswith('links.csv'))
    def test_legacy_and_warm_start(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);warm=path/'final.xml.gz'
            tree=ET.parse(R.write_config(path,4711,12,'none',10,16,plans=warm))
            self.assertEqual(tree.find("./module[@name='strategy']/param[@name='fractionOfIterationsToDisableInnovation']").get('value'),'0.8')
            self.assertEqual(tree.find("./module[@name='plans']/param[@name='inputPlansFile']").get('value'),str(warm))
    def test_verification_fails_on_drift_and_accepts_extra_files(self):
        expected=json.loads(R.EXPECTED.read_text())
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);sim=path/'simulation';sim.mkdir()
            (path/'run.json').write_text(json.dumps({'seed':4711,'iterations':12,'exit_code':0,'scenario':'actual2025'}))
            for i,m in enumerate(expected['iteration_metrics']):(sim/f'iteration-metrics-{i}.json').write_text(json.dumps(m))
            (sim/'research').mkdir();(sim/'research/extra.json').write_text('{}')
            with (sim/'BUILT.scorestats.csv').open('w') as f:
                w=csv.writer(f,delimiter=';');w.writerow(['avg_executed']);w.writerows([[v] for v in expected['scores']])
            args=type('Args',(),{'run_dir':path})()
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit) as cm:R.verify(args)
            self.assertEqual(cm.exception.code,0)
            m=expected['iteration_metrics'][0];m['unfinished_all']+=1;(sim/'iteration-metrics-0.json').write_text(json.dumps(m))
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit) as cm:R.verify(args)
            self.assertEqual(cm.exception.code,1)
            self.assertFalse(json.loads((path/'verification.json').read_text())['passed'])
    def test_actual_matsim_duplicate_stopwatch_headers(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'stopwatch.csv'
            path.write_text('iteration;BEGIN iteration;mobsim;replanning;iteration\n0;00:11:46;00:02:34;;00:03:27\n1;00:15:13;00:02:35;00:00:32;00:03:49\n')
            rows=R.stopwatch_table(path)
            self.assertEqual([int(r['iteration']) for r in rows],[0,1])
            self.assertEqual([R.secs(r['iteration_duration']) for r in rows],[207,229])
            self.assertEqual(R.secs(rows[1]['replanning']),32)

    def test_login_node_guard(self):
        with patch.dict(R.os.environ,{},clear=True),self.assertRaises(SystemExit) as cm:R.run(None)
        self.assertIn('Slurm',str(cm.exception))

if __name__=='__main__':unittest.main()

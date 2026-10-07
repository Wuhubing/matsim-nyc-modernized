import importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import auto_chain,release_baseline

class ChainTests(unittest.TestCase):
    def fixture(self,d):
        root=Path(d)/'snapshot';root.mkdir();output=Path(d)/'outputs'
        (root/'snapshot.json').write_text(json.dumps({'commit':'test','files_sha256':{}}))
        (root/'output-root.txt').write_text(str(output))
        return root,output
    def test_dependencies_resources_and_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            root,out=self.fixture(d)
            with patch.object(auto_chain.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,f'{j}\n','') for j in [100,101,102]]) as run:
                result=auto_chain.queue(root)
                self.assertEqual(result['jobs'],{'validation':'100','gate':'101','baseline':'102'})
                calls=run.call_args_list
                self.assertIn('--dependency=afterok:100',calls[1].args[0]);self.assertIn('--dependency=afterok:101',calls[2].args[0])
                self.assertIn('--kill-on-invalid-dep=yes',calls[2].args[0]);self.assertIn('--array=0-2',calls[2].args[0])
                self.assertEqual(calls[0].kwargs['env']['OUTPUT_ROOT'],str(out/'validation'))
                self.assertEqual(calls[2].kwargs['env']['OUTPUT_ROOT'],str(out))
                auto_chain.queue(root);self.assertEqual(run.call_count,3)
    def test_uncertain_submission_stops_retry(self):
        with tempfile.TemporaryDirectory() as d:
            root,_=self.fixture(d)
            with patch.object(auto_chain.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','connection lost')) as run:
                with self.assertRaises(RuntimeError):auto_chain.queue(root)
                with self.assertRaises(ValueError):auto_chain.queue(root)
                self.assertEqual(run.call_count,1)
    def test_existing_validation_is_reused(self):
        with tempfile.TemporaryDirectory() as d:
            root,_=self.fixture(d);(root/'validation-job-id.txt').write_text('999\n')
            with patch.object(auto_chain.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,f'{j}\n','') for j in [1000,1001]]) as run:
                auto_chain.queue(root)
                self.assertIn('--dependency=afterok:999',run.call_args_list[0].args[0]);self.assertEqual(run.call_count,2)
    def test_gate_rejects_bad_time_estimate_and_stale_success(self):
        with tempfile.TemporaryDirectory() as d:
            root,out=self.fixture(d);(out/'validation').mkdir(parents=True);marker=out/'validation/release-100.json';marker.write_text('{}')
            for estimate in [None,9,float('nan')]:
                with patch.object(release_baseline,'check',return_value={'projected_100_iteration_hours_with_30pct_margin':estimate}):
                    with self.assertRaises(ValueError):release_baseline.release(root,out)
                self.assertFalse(marker.exists())
    def test_release_is_bound_to_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            root,out=self.fixture(d);(out/'validation').mkdir(parents=True);r=out/'validation/run';r.mkdir()
            (r/'run.json').write_text(json.dumps({'provenance':json.loads((root/'snapshot.json').read_text())}))
            report={'projected_100_iteration_hours_with_30pct_margin':6,'runs':{'rich':str(r)}}
            with patch.object(release_baseline,'check',return_value=report):release_baseline.release(root,out)
            release_baseline.assert_release(root,out)
            (root/'snapshot.json').write_text('{}')
            with self.assertRaises(ValueError):release_baseline.assert_release(root,out)

if __name__=='__main__':unittest.main()

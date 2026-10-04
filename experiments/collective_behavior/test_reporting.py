import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from budget import save, read, reserve, settle, lock
from environment import Config, Environment
from observations import observe
from llm import Client, BudgetStop
from report import report
from runner import replay_score

class ReportingTests(unittest.TestCase):
    def test_counterfactual_removes_focal_before_reinsertion(self):
        env=Environment(Config())
        prior=env.step({i:0 if i<16 else 1 for i in range(24)})
        nxt=env.step({i:0 if i<8 else 1 for i in range(24)})
        state={'agent':0,'history':[prior],'next_row':nxt}
        choice={'route':0,'cause':'none','confidence':1,'predicted_costs':[14,20.25],'valid':True}
        score=replay_score(state,choice,'flow')
        self.assertEqual(score['counterfactual_costs'],[14,20.25])
        self.assertEqual(score['prediction_mae'],0)
        self.assertTrue(score['contemporaneously_identifiable'])

    def test_incomplete_world_not_ranked(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); save(out/'manifest.json',{'status':'budget_or_transport_stop'})
            row=Environment(Config()).step({i:0 for i in range(24)})
            step={'world':'test','config':{'scenario':'none'},'seed':0,'method':'direct','row':row}
            (out/'closed-steps.jsonl').write_text(json.dumps(step)+'\n')
            report(out)
            result=read(out/'results.json')
            self.assertIsNone(result['closed'][0]['metrics'])
            self.assertEqual(result['decision'],'证据不足')

    def test_settlement_while_other_writer_active_stays_reserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'source'; out=root/'out'; source.mkdir(); out.mkdir()
            save(source/'budget.json',{'limit_seconds':14400,'used_seconds':0,'active':None})
            save(source/'api-budget.json',{'limit_usd':20,'reserved_usd':0,'measured_usd':0,'calls':[]})
            reserve(source,out)
            with lock(source/'executor.lock'):
                with self.assertRaises(BlockingIOError): settle(out,1,0)
            self.assertEqual(read(source/'budget.json')['used_seconds'],1800)
            self.assertFalse(read(out/'reservation.json')['settled'])

    def test_paid_invalid_response_charged_and_falls_back(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self):
                return json.dumps({'status':'completed','model':'test','usage':{'input_tokens':100,'output_tokens':20},
                    'output':[{'type':'message','content':[{'type':'output_text','text':'{"route": 7}'}]}]}).encode()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); key=out/'key'; key.write_text('mock')
            client=Client(out,key,1,time.monotonic()+60)
            with patch('urllib.request.urlopen',return_value=Response()):
                choice=client.decide({'history':[{'route':1}]},'direct','invalid',0)
            self.assertFalse(choice['valid']); self.assertEqual(choice['route'],1)
            self.assertAlmostEqual(client.spent,.000072)
            self.assertEqual(client.unknown,0)

if __name__=='__main__': unittest.main()

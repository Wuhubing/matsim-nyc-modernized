import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from environment import Config, Environment, costs, parameters
from observations import observe
from policies import Policy, validate_choice, fallback, estimate
from runner import pairing_check, numeric_episode
from budget import save, read, reserve, settle, lock
from llm import Client, BudgetStop, request_body

class EnvironmentTests(unittest.TestCase):
    def test_hand_calculation_and_simultaneity(self):
        actions={i:0 if i<16 else 1 for i in range(24)}
        a=Environment(Config()).step(actions)
        b=Environment(Config()).step(dict(reversed(list(actions.items()))))
        self.assertEqual(a,b); self.assertEqual(a['costs'],[18.,18.])
        self.assertEqual(sum(a['endogenous_flow']),24)
        self.assertEqual(costs(16,capacity=.5),[26.,18.])
        self.assertEqual(costs(16,background=16),[26.,18.])

    def test_intervention_schedule(self):
        c=Config(scenario='both',strength=2)
        self.assertEqual(parameters(c,10),(1.,0))
        self.assertEqual(parameters(c,11),(.5,16))
        self.assertEqual(parameters(c,20),(.5,16))
        self.assertEqual(parameters(c,21),(1.,0))

    def test_invalid_joint_action_no_mutation(self):
        env=Environment(Config())
        for actions in ({0:0},{i:True for i in range(24)},{i:2 for i in range(24)}):
            with self.assertRaises(ValueError): env.step(actions)
        self.assertEqual(env.history,[]); self.assertEqual(env.day,1)

    def test_whitelist_and_copy(self):
        row=Environment(Config()).step({i:0 for i in range(24)})
        before=observe([row],0,information='flow')
        row['truth']['cause']='secret'; row['secret']='hidden'
        self.assertEqual(before,observe([row],0,information='flow'))
        before['history'][0]['total_route_flows'][0]=999
        self.assertEqual(row['total_flow'][0],24)
        self.assertNotIn('secret',json.dumps(observe([row],0)))
        self.assertNotIn('truth',json.dumps(request_body(observe([row],0),'diagnose')))

    def test_pairing_and_relevance(self):
        p=pairing_check()
        self.assertTrue(p['time_observations_equal']); self.assertTrue(p['flow_observations_differ']); self.assertTrue(p['action_relevant'])
        self.assertEqual([w['best_route'] for w in p['worlds']],[0,1])
        self.assertEqual([estimate(w['observation_flow'])[2] for w in p['worlds']],['capacity','background'])

    def test_seed_replay(self):
        c=Config(scenario='capacity')
        a=numeric_episode(c,'smooth','time',4,time.monotonic()+20)
        b=numeric_episode(c,'smooth','time',4,time.monotonic()+20)
        self.assertEqual(a,b)
        self.assertTrue(a['metrics']['complete'])
        self.assertGreaterEqual(a['metrics']['excess_cost'],-1e-9)

    def test_fallback_and_output_validation(self):
        obs={'history':[{'route':1}]}
        self.assertEqual(fallback(obs,4),1)
        self.assertEqual(fallback({'history':[]},4),fallback({'history':[]},4))
        good={'route':0,'cause':'insufficient','confidence':0.,'predicted_costs':[18.,18.]}
        for key,value in [('route',True),('route',3),('cause','magic'),('confidence',float('nan')),('predicted_costs',[float('inf'),1])]:
            bad=dict(good); bad[key]=value
            with self.assertRaises(ValueError): validate_choice(bad)

class BudgetTests(unittest.TestCase):
    def setup_files(self, root):
        source=root/'shared'; out=root/'run'; source.mkdir(); out.mkdir()
        save(source/'budget.json',{'limit_seconds':14400,'used_seconds':100,'active':None})
        save(source/'api-budget.json',{'limit_usd':20,'reserved_usd':.1,'measured_usd':.01,'calls':[{'status':'complete','reservation_usd':.1,'estimated_usd':.01}]})
        return source,out

    def test_reservation_and_idempotent_settlement(self):
        with tempfile.TemporaryDirectory() as d:
            source,out=self.setup_files(Path(d)); reserve(source,out)
            self.assertEqual(read(source/'budget.json')['used_seconds'],1900)
            settle(out,10,.2); settle(out,10,.2)
            self.assertEqual(read(source/'budget.json')['used_seconds'],110)
            self.assertAlmostEqual(read(source/'api-budget.json')['measured_usd'],.21)

    def test_busy_and_active_do_not_mutate(self):
        with tempfile.TemporaryDirectory() as d:
            source,out=self.setup_files(Path(d))
            with lock(source/'executor.lock'):
                with self.assertRaises(BlockingIOError): reserve(source,out)
            sim=read(source/'budget.json'); sim['active']={'pid':123}; save(source/'budget.json',sim)
            with self.assertRaises(RuntimeError): reserve(source,out)
            self.assertEqual(read(source/'budget.json')['used_seconds'],100)

    def test_api_stop_before_network_and_unknown_failure(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); key=out/'secret'; key.write_text('dummy-test-key')
            client=Client(out,key,0,time.monotonic()+60)
            with patch('urllib.request.urlopen') as network:
                with self.assertRaises(BudgetStop): client.decide({'history':[]},'direct','zero',0)
                network.assert_not_called()
            client.limit=1
            with patch('urllib.request.urlopen',side_effect=TimeoutError('sensitive detail')):
                choice=client.decide({'history':[{'route':1}]},'direct','one',0)
            self.assertFalse(choice['valid']); self.assertEqual(choice['route'],1)
            self.assertGreater(client.unknown,0)
            record=(out/'calls/one.json').read_text()
            self.assertNotIn('dummy-test-key',record); self.assertNotIn('sensitive detail',record)
            with self.assertRaises(RuntimeError): client.decide({'history':[]},'direct','one',0)

if __name__=='__main__': unittest.main()

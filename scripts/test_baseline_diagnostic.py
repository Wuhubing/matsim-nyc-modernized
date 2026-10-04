import unittest,tempfile,os,json
from unittest.mock import patch
from pathlib import Path
from run_baseline_diagnostic import factors_from_source,resource_reason,GIB,generate_config,run_attempt,save
from analyze_baseline_diagnostic import analyze_events,table
import xml.etree.ElementTree as ET
class DiagnosticTests(unittest.TestCase):
 def test_active_parameters_only(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'old.java';p.write_text('/* double ExpressFactor []={9}; */ double ExpressFactor []={1,2,3,4,5,6}; // old\ndouble ArterialFactor []={6,5,4,3,2,1};')
   self.assertEqual(factors_from_source(p)[0],['1','2','3','4','5','6'])
 def test_resource_limits(self):
  s={'disk_free_bytes':40*GIB,'pressure_level':4,'swap_used_bytes':0}
  self.assertEqual(resource_reason(s,[],0,60)[0],'sustained_critical_memory_pressure')
  s.update(pressure_level=1,swap_used_bytes=3*GIB)
  self.assertEqual(resource_reason(s,[(0,0)],None,60)[0],'swap_growth_over_2_GiB_in_5_minutes')
  self.assertIsNone(resource_reason(s,[(0,0)],None,400)[0])
 def test_baseline_and_iteration_count(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);root=ET.parse(generate_config(p,p,5)).getroot()
   self.assertEqual(root.find("module[@name='controler']/param[@name='lastIteration']").get('value'),'4')
   self.assertEqual(root.find("module[@name='global']/param[@name='randomSeed']").get('value'),'4711')
   self.assertTrue(root.find("module[@name='roadpricing']/param[@name='tollLinksFile']").get('value').endswith('control-zero-tolls.xml'))
 def test_shared_budget_survives_attempt(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);fake=p/'fake-java';fake.write_text('#!/bin/sh\nsleep 10\n');fake.chmod(0o755)
   manifest={'attempts':[]};ledger={'limit_seconds':.1,'used_seconds':0,'active':None}
   with patch('run_baseline_diagnostic.system_sample',return_value={'disk_free_bytes':40*GIB,'pressure_level':1,'swap_used_bytes':0}),patch('run_baseline_diagnostic.memory_sample',return_value=1024):
    a=run_attempt(p,'smoke',1,'16g',manifest,ledger,fake)
    self.assertEqual(a['reason'],'shared_budget_exhausted')
    persisted=json.loads((p/'budget.json').read_text())
    self.assertGreaterEqual(persisted['used_seconds'],persisted['limit_seconds'])
    self.assertIsNone(persisted['active'])
    with self.assertRaises(RuntimeError):run_attempt(p,'five',5,'16g',manifest,persisted,fake)
 def test_duplicate_stopwatch_header(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'stopwatch.csv';p.write_text('iteration;mobsim;iteration\n0;00:02:12;00:02:49\n')
   self.assertEqual(table(p)[0]['iteration'],'0')
   self.assertEqual(table(p)[0]['iteration_duration'],'00:02:49')
 def test_attribution_and_unfinished(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);f=p/'events.xml'
   f.write_text('<events>\n'+ '\n'.join([
    '<event time="21600" type="departure" person="p" legMode="car" />',
    '<event time="21600" type="vehicle enters traffic" person="p" vehicle="v" networkMode="car" />',
    '<event time="21601" type="left link" vehicle="v" link="320888283_0" />',
    '<event time="21601" type="personScore" person="p" kind="nyc-legacy-facility-toll" amount="-0.77094" />',
    '<event time="22000" type="stuckAndAbort" person="p" legMode="car" />'])+'\n</events>')
   r,_,_=analyze_events(f,{'p':'man'},{'p'},p/'trace.jsonl')
   self.assertEqual(r['legacy_unmatched_expected'],0);self.assertEqual(r['legacy_unmatched_actual'],0)
   self.assertEqual(r['unfinished_legs_by_mode'],{'car':1});self.assertEqual(r['unique_stuck_persons'],1)
if __name__=='__main__':unittest.main()

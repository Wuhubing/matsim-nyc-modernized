"""Offline end-to-end event fixture; no MATSim simulation."""
import tempfile,unittest,json,gzip,csv,sys
from pathlib import Path
import zstandard
from analyze_bus_capacity_diagnostic import analyze,compatible
class EventTests(unittest.TestCase):
 def test_censored_wait_repeated_activity_and_target_completion(self):
  with tempfile.TemporaryDirectory() as d:
   o=Path(d);(o/'common').mkdir();sim=o/'control-attempt-1/simulation';(sim/'ITERS/it.0').mkdir(parents=True)
   (o/'run_manifest.json').write_text(json.dumps({'attempts':[{'stage':'control','status':'complete','directory':'control-attempt-1'}]}))
   vehicles='<vehicleDefinitions><vehicleType id="bus"><capacity seats="1" standingRoomInPersons="0"/></vehicleType><vehicle id="v" type="bus"/></vehicleDefinitions>'
   (sim/'BUILT.output_transitVehicles.xml.zst').write_bytes(zstandard.compress(vehicles.encode()))
   with gzip.open(o/'common/control-vehicles.xml.gz','wt') as f:f.write(vehicles)
   schedule='<transitSchedule><transitLine id="L"><transitRoute id="R"><transportMode>bus</transportMode><routeProfile><stop refId="A"/><stop refId="B"/></routeProfile></transitRoute></transitLine></transitSchedule>'
   with gzip.open(o/'common/schedule.xml.gz','wt') as f:f.write(schedule)
   meta={p:dict(person=p,group='g',modes=['pt']*n,activities=['Home']*(n+1),pt={str(j):dict(transitLineId='L',transitRouteId='R') for j in range(1,n+1)}) for p,n in [('p',2),('q',1),('z',0)]}
   ev=[]
   def add(t,typ,**kw):ev.append('<event '+ ' '.join(f'{k}="{v}"' for k,v in dict(time=t,type=typ,**kw).items())+'/>')
   add(0,'TransitDriverStarts',vehicleId='v',transitLineId='L',transitRouteId='R')
   for p in ['p','q']:add(0,'departure',person=p,legMode='pt');add(0,'waitingForPt',person=p,atStop='A',destinationStop='B')
   add(1,'PersonEntersPtVehicle',person='p',vehicle='v');add(1,'VehicleDepartsAtFacility',vehicle='v',facility='A')
   add(2,'PersonLeavesPtVehicle',person='p',vehicle='v');add(2,'arrival',person='p',legMode='pt');add(2,'actstart',person='p',actType='Home')
   add(2,'departure',person='p',legMode='pt');add(2,'waitingForPt',person='p',atStop='A',destinationStop='B')
   for p in ['p','q']:add(108000,'stuckAndAbort',person=p,legMode='pt')
   (sim/'ITERS/it.0/BUILT.0.events.xml.zst').write_bytes(zstandard.compress(('<events>\n'+'\n'.join(ev)+'\n</events>').encode()))
   dest,new=analyze(o,'control',meta,{'p':{1},'q':{1}});a=json.load(open(dest/'analysis.json'));r={(x['person'],int(x['leg'])):x for x in csv.DictReader(open(dest/'target-results.csv'))}
   self.assertEqual(a['waiting_persons'],2);self.assertEqual(a['started_wait_segments'],3);self.assertAlmostEqual(a['wait_person_hours'],(1+107998+108000)/3600)
   self.assertEqual(r[('p',1)]['completed'],'True');self.assertEqual(r[('p',1)]['final_activity_reached'],'False');self.assertEqual(a['no_planned_travel'],1);self.assertEqual(new,{'q':1})
 def test_shared_vehicle_and_type_are_normalized_in_both_arms(self):
  import xml.etree.ElementTree as E
  from run_bus_capacity_diagnostic import normalize_transit
  schedule=E.fromstring('<transitSchedule><transitLine id="L"><transitRoute id="bus"><transportMode>bus</transportMode><departures><departure id="b" vehicleRefId="shared"/></departures></transitRoute><transitRoute id="train"><transportMode>rail</transportMode><departures><departure id="t" vehicleRefId="shared"/></departures></transitRoute></transitLine></transitSchedule>')
  vehicles=E.fromstring('<vehicleDefinitions><vehicleType id="T"><capacity seats="2" standingRoomInPersons="3"/><length meter="10"/></vehicleType><vehicle id="shared" type="T"/></vehicleDefinitions>')
  control,treatment,info=normalize_transit(schedule,vehicles)
  self.assertEqual(len(info['vehicle_splits']),1);self.assertEqual(len(info['type_splits']),1)
  self.assertEqual([v.attrib for v in control.findall('vehicle')],[v.attrib for v in treatment.findall('vehicle')])
  self.assertEqual(treatment.find("vehicleType[@id='T']/capacity").get('seats'),'2')
  self.assertEqual(treatment.find("vehicleType[@id='T__bus_diagnostic']/capacity").get('seats'),'4')
  self.assertEqual(control.find("vehicleType[@id='T__bus_diagnostic']/capacity").get('standingRoomInPersons'),'3')
  self.assertEqual(schedule.find(".//departure[@id='t']").get('vehicleRefId'),'shared')
 def test_downstream_compatibility(self):
  self.assertTrue(compatible(['A','B','C'],0,'C'));self.assertFalse(compatible(['A','B','C'],1,'A'))
if __name__=='__main__':unittest.main()

package org.c2smart.matsimnyc;
import java.nio.file.*;
import java.util.*;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.events.*;
import org.matsim.api.core.v01.events.handler.*;
import org.matsim.api.core.v01.population.Person;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.network.NetworkUtils;
import org.matsim.core.network.io.MatsimNetworkReader;
import org.matsim.core.network.io.NetworkChangeEventsParser;
import org.matsim.core.population.io.StreamingPopulationReader;
import org.matsim.core.scenario.ScenarioUtils;
/** Real-data parity of NycPSim.features with experiments/surrogate/agent_surrogate.py.
 * Usage: NETWORK CHANGE_EVENTS PREVIOUS_EVENTS PLANS PARITY_CSV */
public final class VerifyPSimFeatures {
 public static void main(String[] a) throws Exception {
  var config=ConfigUtils.createConfig();config.network().setTimeVariantNetwork(true);config.qsim().setEndTime(108000);
  var s=ScenarioUtils.createScenario(config);
  new MatsimNetworkReader(s.getNetwork()).readFile(a[0]);
  var changes=new ArrayList<org.matsim.core.network.NetworkChangeEvent>();
  new NetworkChangeEventsParser(s.getNetwork(),changes).readFile(a[1]);NetworkUtils.setNetworkChangeEvents(s.getNetwork(),changes);
  var robust=new NycPSim.RobustTimes();var ev=EventsUtils.createEventsManager();
  ev.addHandler(new VehicleEntersTrafficEventHandler(){public void handleEvent(VehicleEntersTrafficEvent e){robust.traffic(e);}});
  ev.addHandler(new VehicleLeavesTrafficEventHandler(){public void handleEvent(VehicleLeavesTrafficEvent e){robust.untrack(e.getVehicleId());}});
  ev.addHandler(new LinkEnterEventHandler(){public void handleEvent(LinkEnterEvent e){robust.enter(e);}});
  ev.addHandler(new LinkLeaveEventHandler(){public void handleEvent(LinkLeaveEvent e){robust.leave(e);}});
  ev.initProcessing();EventsUtils.readEvents(ev,a[2]);ev.finishProcessing();
  var expected=new HashMap<String,double[]>();
  for(String line:Files.readAllLines(Path.of(a[4]))){var v=line.split(",");expected.put(v[0],Arrays.stream(v,1,8).mapToDouble(Double::parseDouble).toArray());}
  var psim=new NycPSim.PSim(s,null,null,null,robust,null);
  var reader=new StreamingPopulationReader(s);int[] counts=new int[2];double[] worst={0};String[] where={""};
  reader.addAlgorithm(person->{
   double[] want=expected.get(person.getId().toString());if(want==null)return;
   double[] got=psim.features(person.getSelectedPlan());counts[0]++;
   for(int k=0;k<7;k++){double d=Math.abs(got[k]-want[k])/Math.max(1,Math.abs(want[k]));if(d>worst[0]){worst[0]=d;where[0]=person.getId()+" col "+k+" java "+got[k]+" python "+want[k];}}
  });
  reader.readFile(a[3]);
  if(counts[0]!=expected.size())throw new AssertionError("matched "+counts[0]+" of "+expected.size());
  if(worst[0]>1e-6)throw new AssertionError("max relative difference "+worst[0]+" at "+where[0]);
  System.out.println("PASS: Java PSim features match Python for "+counts[0]+" persons (max rel diff "+worst[0]+")");
 }
}

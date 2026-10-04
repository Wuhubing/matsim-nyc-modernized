package org.c2smart.matsimnyc;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import org.matsim.api.core.v01.*;
import org.matsim.api.core.v01.events.*;
import org.matsim.api.core.v01.network.Link;
import org.matsim.contrib.roadpricing.RoadPricingConfigGroup;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.events.handler.BasicEventHandler;
import org.matsim.core.network.io.MatsimNetworkReader;
import org.matsim.core.population.io.PopulationReader;
import org.matsim.core.scenario.ScenarioUtils;

/** Full-scale exactness check for the index-based pricing lookups (offline, no simulation).
 * Usage: VerifyPricingReplay CONFIG EVENTS
 * 1. Every network link x 15-minute grid over 0-30h: routingToll equals the original String-set formula.
 * 2. Replays a recorded events file through fresh Pricing2025 and LegacyCosts handlers and requires the
 *    generated money/score events to equal, in order, those recorded by the original implementation. */
public class VerifyPricingReplay {
 static final Set<String> TUNNELS=Set.of("320888283_0","60325668_0","415882710_0","11878036_0","413749473_0"),MTA_IN=Set.of("11878036_0","413749473_0");
 static String key(Event e){
  if(e instanceof PersonMoneyEvent m)return m.getTime()+"|"+m.getPersonId()+"|"+m.getAmount()+"|"+m.getPurpose()+"|"+m.getTransactionPartner()+"|"+m.getReference();
  var s=(PersonScoreEvent)e;return s.getTime()+"|"+s.getPersonId()+"|"+s.getAmount()+"|"+s.getKind();
 }
 public static void main(String[] args) throws Exception {
  var config=ConfigUtils.loadConfig(args[0],new RoadPricingConfigGroup(),new NycModelConfig());
  var nyc=ConfigUtils.addOrGetModule(config,NycModelConfig.class);
  var s=ScenarioUtils.createScenario(config);
  new MatsimNetworkReader(s.getNetwork()).readFile(config.network().getInputFile());
  new PopulationReader(s).readFile(config.plans().getInputFile());
  var policy=new Pricing2025(s,nyc.getPricing2025Links());
  // 1. Routing grid against the original String formula.
  var entry=new HashSet<String>();
  for(String row:Files.readAllLines(Path.of(nyc.getPricing2025Links())).subList(1,Files.readAllLines(Path.of(nyc.getPricing2025Links())).size())){var v=row.split(",");if(v[1].equals("1"))entry.add(v[0]);}
  long cells=0,nonzero=0;
  for(Link l:s.getNetwork().getLinks().values())for(int t=0;t<=108000;t+=900)for(double time:new double[]{t,t+0.5}){
   String id=l.getId().toString();
   double expected=entry.contains(id)?Pricing2025.carRate(time,false)-(Pricing2025.peak(time)&&TUNNELS.contains(id)?(MTA_IN.contains(id)?1.5:3):0):0;
   double actual=policy.routingToll(l.getId(),time);
   if(Double.doubleToLongBits(expected)!=Double.doubleToLongBits(actual))throw new AssertionError("routing toll "+id+" "+time+" "+expected+" "+actual);
   cells++;if(actual!=0)nonzero++;
  }
  System.out.println("PASS routing grid: "+cells+" link-time cells identical, "+nonzero+" nonzero");
  // 2. Replay.
  var emitted=new ArrayList<String>();
  var sink=EventsUtils.createEventsManager();
  sink.addHandler(new BasicEventHandler(){public void handleEvent(Event e){emitted.add(key(e));}});
  var field=Pricing2025.class.getDeclaredField("events");field.setAccessible(true);field.set(policy,sink);
  var legacy=new LegacyCosts(sink,s);
  var recorded=new ArrayList<String>();
  var source=EventsUtils.createEventsManager();
  source.addHandler(policy);source.addHandler(legacy);
  source.addHandler(new BasicEventHandler(){public void handleEvent(Event e){
   if(e instanceof PersonMoneyEvent m&&"toll".equals(m.getPurpose())&&"NYC2025".equals(m.getTransactionPartner()))recorded.add(key(e));
   else if(e instanceof PersonScoreEvent p&&p.getKind().startsWith("nyc-legacy"))recorded.add(key(e));
  }});
  source.initProcessing();
  EventsUtils.readEvents(source,args[1]);
  source.finishProcessing();
  if(!recorded.equals(emitted)){
   int i=0;while(i<Math.min(recorded.size(),emitted.size())&&recorded.get(i).equals(emitted.get(i)))i++;
   throw new AssertionError("replay differs at "+i+" recorded="+recorded.size()+" emitted="+emitted.size()+" "+(i<recorded.size()?recorded.get(i):"-")+" vs "+(i<emitted.size()?emitted.get(i):"-"));
  }
  System.out.println("PASS replay: "+emitted.size()+" pricing/legacy events identical in order");
 }
}

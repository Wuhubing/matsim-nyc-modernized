package org.c2smart.matsimnyc;
import java.nio.file.*;
import java.util.*;
import org.matsim.api.core.v01.*;
import org.matsim.api.core.v01.events.*;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.controler.events.*;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.events.handler.BasicEventHandler;
import org.matsim.core.network.NetworkUtils;
import org.matsim.core.population.routes.RouteUtils;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.vehicles.VehicleUtils;

/** Synthetic checks of NycPSim: event sequence/times, network-mode vehicles, end-link rule, stuck handling,
 * and which plans PSim evaluates versus keeps. */
public final class VerifyPSim {
 static List<Event> replay(Scenario s, NycPSim.Switch sw, NycPSim.RobustTimes robust) {
  var out=new ArrayList<Event>();var ev=EventsUtils.createEventsManager();
  ev.addHandler(new BasicEventHandler(){public void handleEvent(Event e){out.add(e);}});
  new NycPSim.PSim(s,ev,sw,(link,time,p,v)->20.0,robust).run();return out;
 }
 static double time(List<Event> events,Class<?> type,int nth){
  int k=0;for(var e:events)if(type.isInstance(e)&&k++==nth)return e.getTime();throw new AssertionError("missing "+type.getSimpleName());
 }
 public static void main(String[] args) throws Exception {
  var config=ConfigUtils.createConfig();config.qsim().setEndTime(108000);
  var s=ScenarioUtils.createScenario(config);var n=s.getNetwork();var f=s.getPopulation().getFactory();
  var nodes=new ArrayList<org.matsim.api.core.v01.network.Node>();
  for(int i=0;i<4;i++)nodes.add(NetworkUtils.createAndAddNode(n,Id.createNodeId("n"+i),new Coord(100*i,0)));
  var ids=new ArrayList<Id<Link>>();
  for(int i=0;i<3;i++){ids.add(Id.createLinkId("l"+i));NetworkUtils.createAndAddLink(n,ids.get(i),nodes.get(i),nodes.get(i+1),100,10,1000,1);}
  Person a=person(s,"a",3600,"car",ids),b=person(s,"b",107990,"taxi",ids),c=person(s,"c",3600,"car",ids);
  var dir=Files.createTempDirectory("psim-verify");
  var sw=new NycPSim.Switch(s,3,0,11,dir);
  // Iteration 1 is a PSim iteration (cycle 3). Person c changes plan in "replanning"; a and b keep theirs.
  sw.notifyIterationStarts(new IterationStartsEvent(null,1,false));
  if(sw.isQSim())throw new AssertionError("iteration 1 must be PSim");
  for(Person p:List.of(a,b))p.getSelectedPlan().setScore(-1.0);
  var newPlan=person(s,"tmp",3700,"car",ids).getSelectedPlan();s.getPopulation().removePerson(Id.createPersonId("tmp"));
  c.addPlan(newPlan);c.setSelectedPlan(newPlan);
  sw.notifyBeforeMobsim(new BeforeMobsimEvent(null,1,false));
  if(sw.toSimulate.size()!=1||sw.toSimulate.getFirst()!=newPlan)throw new AssertionError("only the changed plan is simulated");
  // Replay all three plans directly to check event semantics.
  sw.toSimulate.clear();sw.toSimulate.addAll(List.of(a.getSelectedPlan(),b.getSelectedPlan()));
  var mean=replay(s,sw,null);
  // a: depart 3600, l1 (20 s), end link l2 (20 s, mean variant) -> arrival 3640; walk 300 s after work end 7200.
  if(time(mean,PersonDepartureEvent.class,0)!=3600||time(mean,LinkEnterEvent.class,0)!=3600||time(mean,LinkLeaveEvent.class,1)!=3620
     ||time(mean,PersonArrivalEvent.class,0)!=3640||time(mean,PersonArrivalEvent.class,1)!=7500)throw new AssertionError("mean timing "+mean);
  var vte=(VehicleEntersTrafficEvent)mean.stream().filter(e->e instanceof VehicleEntersTrafficEvent).findFirst().orElseThrow();
  if(!vte.getVehicleId().toString().equals("a_car")||!vte.getNetworkMode().equals("car"))throw new AssertionError("vehicle/mode");
  var stuck=mean.stream().filter(e->e instanceof PersonStuckEvent).map(e->(PersonStuckEvent)e).toList();
  if(stuck.size()!=1||!stuck.getFirst().getPersonId().toString().equals("b")||!"taxi".equals(stuck.getFirst().getLegMode())||stuck.getFirst().getTime()!=108000)
   throw new AssertionError("taxi leg past end time must be stuck with its mode: "+stuck);
  // Geometric variant: no observations -> calculator fallback per link, free flow (10 s) on the end link.
  var geo=replay(s,sw,new NycPSim.RobustTimes());
  if(time(geo,PersonArrivalEvent.class,0)!=3630)throw new AssertionError("end link free flow "+time(geo,PersonArrivalEvent.class,0));
  // Kept scores are restored after scoring overwrote them.
  a.getSelectedPlan().setScore(99.0);
  sw.notifyIterationEnds(new IterationEndsEvent(null,1,false));
  if(a.getSelectedPlan().getScore()!=-1.0)throw new AssertionError("kept score restored");
  sw.notifyIterationStarts(new IterationStartsEvent(null,3,false));
  if(!sw.isQSim())throw new AssertionError("iteration 3 must be QSim");
  sw.notifyIterationStarts(new IterationStartsEvent(null,11,true));
  if(!sw.isQSim())throw new AssertionError("last iteration must be QSim");
  Files.walk(dir).sorted(Comparator.reverseOrder()).forEach(p->p.toFile().delete());
  System.out.println("PASS: PSim evaluates only changed plans, restores kept scores, network-mode vehicles/events/times, end-link rule, stuck legs");
 }
 static Person person(Scenario s,String id,double end,String mode,List<Id<Link>> ids){
  var f=s.getPopulation().getFactory();var p=f.createPerson(Id.createPersonId(id));var plan=f.createPlan();
  var home=f.createActivityFromLinkId("Home",ids.get(0));home.setEndTime(end);plan.addActivity(home);
  var leg=f.createLeg(mode);var route=RouteUtils.createLinkNetworkRouteImpl(ids.get(0),List.of(ids.get(1)),ids.get(2));leg.setRoute(route);plan.addLeg(leg);
  var work=f.createActivityFromLinkId("Work",ids.get(2));work.setEndTime(7200);plan.addActivity(work);
  var walk=f.createLeg("walk");var wr=RouteUtils.createGenericRouteImpl(ids.get(2),ids.get(0));wr.setTravelTime(300);wr.setDistance(100);walk.setRoute(wr);plan.addLeg(walk);
  plan.addActivity(f.createActivityFromLinkId("Home",ids.get(0)));p.addPlan(plan);
  VehicleUtils.insertVehicleIdsIntoPersonAttributes(p,Map.of(mode,Id.createVehicleId(id+"_"+mode)));
  s.getPopulation().addPerson(p);return p;
 }
}

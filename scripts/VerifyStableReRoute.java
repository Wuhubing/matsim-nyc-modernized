package org.c2smart.matsimnyc;
import java.nio.file.*;
import java.util.*;
import org.matsim.api.core.v01.*;
import org.matsim.api.core.v01.network.*;
import org.matsim.api.core.v01.population.*;
import org.matsim.api.core.v01.replanning.PlanStrategyModule;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.gbl.MatsimRandom;
import org.matsim.core.network.NetworkUtils;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.population.routes.NetworkRoute;
import org.matsim.core.population.routes.RouteUtils;
import org.matsim.core.replanning.*;
import org.matsim.core.replanning.selectors.ExpBetaPlanSelector;
import org.matsim.core.router.util.TravelTime;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.vehicles.*;
/** Synthetic checks for M8 (StableReRoute). Compile with the runner JAR on the class path, then run the class.
 *  Network L0 -> L1 -> L2 -> L3 (100 m each, free speed 10 m/s); route L0 [L1 L2] L3. */
public class VerifyStableReRoute {
 static int fails=0;
 static void check(boolean ok,String what){System.out.println((ok?"PASS ":"FAIL ")+what);if(!ok)fails++;}
 static double slow=1;   // travel time factor on L2 (changes "since routing")
 public static void main(String[] args) throws Exception {
  var sc=ScenarioUtils.createScenario(ConfigUtils.createConfig()); Network net=sc.getNetwork(); var nf=net.getFactory();
  Node[] n=new Node[5]; for(int i=0;i<5;i++){n[i]=nf.createNode(Id.createNodeId(i),new Coord(i*100,0));net.addNode(n[i]);}
  for(int i=0;i<4;i++){Link l=nf.createLink(Id.createLinkId("L"+i),n[i],n[i+1]);l.setLength(100);l.setFreespeed(10);l.setCapacity(1000);net.addLink(l);}
  VehicleType vt=VehicleUtils.createVehicleType(Id.create("car",VehicleType.class)); vt.setMaximumVelocity(5); sc.getVehicles().addVehicleType(vt);
  Vehicle v=VehicleUtils.createVehicle(Id.createVehicleId("v"),vt); sc.getVehicles().addVehicle(v);
  // link time: 20 s, L2 x slow, +1 s after 08:00:30 so the entry time matters
  TravelTime tt=(link,time,p,veh)->(link.getId().toString().equals("L2")?20*slow:20)+(time>8*3600+30?1:0);
  Map<String,TravelTime> tts=Map.of("car",tt);
  // estimate: enter L1 at 08:00:00 (20 s), L2 at 08:00:20 (20 s), end link L3 at min(5, 10) m/s = 20 s
  NetworkRoute r=RouteUtils.createLinkNetworkRouteImpl(Id.createLinkId("L0"),List.of(Id.createLinkId("L1"),Id.createLinkId("L2")),Id.createLinkId("L3"));
  check(StableReRoute.estimate(r,8*3600,null,v,tt,net)==60,"estimate follows the router: entry times, end link at vehicle speed, whole seconds");
  check(StableReRoute.estimate(r,8*3600+15,null,v,tt,net)==61,"estimate uses the time each link is entered (L2 entered after 08:00:30)");

  var pop=sc.getPopulation(); var pf=pop.getFactory();
  var stats=new StableReRoute.Stats(Files.createTempFile("stable",".csv"));
  Person car=person(pf,"car"); pop.addPerson(car);
  Plan pc=carPlan(pf,v,60); car.addPlan(pc); car.setSelectedPlan(pc); pc.setScore(1.0);
  StableReRoute s0=strategy(sc,tts,stats,-1,noop());
  check(s0.change(pc)==0,"unchanged travel times give change exactly 0");
  slow=2; check(Math.abs(s0.change(pc)-20/60.)<1e-12,"L2 twice as slow: change 20/60"); slow=1;
  Plan pt=pf.createPlan(); pt.addActivity(pf.createActivityFromLinkId("h",Id.createLinkId("L0")));
  Leg ptLeg=pf.createLeg("pt"); pt.addLeg(ptLeg); pt.addActivity(pf.createActivityFromLinkId("w",Id.createLinkId("L3")));
  check(Double.isNaN(s0.change(pt)),"a pt leg cannot be judged (NaN)");
  Plan walk=pf.createPlan(); walk.addActivity(pf.createActivityFromLinkId("h",Id.createLinkId("L0")));
  Leg wl=pf.createLeg("walk"); wl.setRoute(RouteUtils.createGenericRouteImpl(Id.createLinkId("L0"),Id.createLinkId("L3"))); walk.addLeg(wl);
  walk.addActivity(pf.createActivityFromLinkId("w",Id.createLinkId("L3")));
  check(s0.change(walk)==0,"teleported legs only: change 0");

  // shadow mode draws exactly like MATSim's ReRoute (RandomPlanSelector + module) and records duplicates
  List<String> mine=new ArrayList<>(), matsim=new ArrayList<>();
  for(int k=0;k<2;k++){
   var p2=PopulationUtils.getFactory().createPerson(Id.createPersonId("m"+k)); for(int j=0;j<4;j++){Plan pl=carPlan(pf,v,60);pl.setScore((double)j);pl.setType("p"+j);p2.addPlan(pl);} p2.setSelectedPlan(p2.getPlans().get(0));
   MatsimRandom.reset(42); GenericPlanStrategy<Plan,Person> st=k==0?strategy(sc,tts,stats,-1,noop()):new PlanStrategyImpl.Builder(new org.matsim.core.replanning.selectors.RandomPlanSelector<>()).addStrategyModule(noop()).build();
   st.init(()->3); List<String> out=k==0?mine:matsim;
   for(int i=0;i<20;i++){st.run(p2);out.add(p2.getSelectedPlan().getType()+":"+p2.getPlans().size());while(p2.getPlans().size()>4)p2.removePlan(p2.getPlans().get(4));p2.setSelectedPlan(p2.getPlans().get(0));}
   st.finish(); out.add("next draw "+MatsimRandom.getRandom().nextInt(1000));
  }
  check(mine.equals(matsim),"shadow mode: same picks, same copies, same RNG stream as ReRoute");
  stats.write(3);
  List<String> csv=Files.readAllLines(stats.file());
  String[] h=csv.get(0).split(","), row=csv.get(1).split(","); Map<String,String> m=new HashMap<>(); for(int i=0;i<h.length;i++)m.put(h[i],row[i]);
  check(m.get("routed").equals("20")&&m.get("duplicates").equals("20")&&m.get("routed_eq0").equals("20")&&m.get("skipped").equals("0"),"shadow mode: 20 routed, all identical copies, all in bin eq0, none skipped");
  check(m.get("estimate_checked").equals("20")&&m.get("estimate_mismatch").equals("0"),"estimator self-check on the unchanged routes");

  // active mode: change 0 <= threshold -> no copy, ExpBeta selection; changed plan -> re-routed
  StableReRoute s1=strategy(sc,tts,stats,0.01,noop()); s1.init(()->4);
  int before=car.getPlans().size(); s1.run(car); s1.finish();
  check(car.getPlans().size()==before,"active mode: a stable plan is not copied or re-routed");
  slow=2; s1.init(()->5); s1.run(car); s1.finish(); slow=1;
  check(car.getPlans().size()==before+1,"active mode: a plan whose route got slower is re-routed");
  stats.write(4);
  csv=Files.readAllLines(stats.file()); row=csv.get(2).split(",");
  check(row[0].equals("4")&&row[4].equals("1")&&row[5].equals("1"),"stats: one skipped and one routed in that iteration ("+csv.get(2).substring(0,Math.min(40,csv.get(2).length()))+")");
  check(new StableReRoute(null,null,null,null,sc,stats,-1).toString().startsWith("RandomPlanSelector_ReRoute"),"description starts like ReRoute's");
  System.out.println(fails==0?"ALL PASS":fails+" FAILED"); System.exit(fails==0?0:1);
 }
 static Person person(PopulationFactory pf,String id){return pf.createPerson(Id.createPersonId(id));}
 static Plan carPlan(PopulationFactory pf,Vehicle v,double stored){
  Plan p=pf.createPlan(); Activity h=pf.createActivityFromLinkId("h",Id.createLinkId("L0")); h.setEndTime(8*3600); p.addActivity(h);
  Leg l=pf.createLeg("car"); l.setDepartureTime(8*3600);
  NetworkRoute r=RouteUtils.createLinkNetworkRouteImpl(Id.createLinkId("L0"),List.of(Id.createLinkId("L1"),Id.createLinkId("L2")),Id.createLinkId("L3"));
  r.setTravelTime(stored); r.setVehicleId(v.getId()); l.setRoute(r); p.addLeg(l); p.addActivity(pf.createActivityFromLinkId("w",Id.createLinkId("L3"))); return p;}
 static PlanStrategyModule noop(){return new PlanStrategyModule(){public void prepareReplanning(ReplanningContext c){} public void handlePlan(Plan p){} public void finishReplanning(){}};}
 static StableReRoute strategy(Scenario sc,Map<String,TravelTime> tts,StableReRoute.Stats stats,double threshold,PlanStrategyModule module){
  var pick=new StableReRoute.RandomPlanSelector();
  return new StableReRoute(new PlanStrategyImpl.Builder(pick).addStrategyModule(module).build(),pick,new ExpBetaPlanSelector<>(2.0),tts,sc,stats,threshold);}
}

package org.c2smart.matsimnyc;
import java.util.*;
import java.nio.file.*;
import org.matsim.api.core.v01.*;
import org.matsim.api.core.v01.events.*;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.network.NetworkUtils;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.events.handler.BasicEventHandler;
public class Verify2025 {
 public static void main(String[] args) throws Exception {
  var s=ScenarioUtils.createScenario(ConfigUtils.createConfig());
  var n=s.getNetwork(); var a=NetworkUtils.createAndAddNode(n,Id.createNodeId("a"),new Coord(0,0));
  var b=NetworkUtils.createAndAddNode(n,Id.createNodeId("b"),new Coord(1,0));
  for(String id:List.of("entry","inside","outside","320888283_0","11878036_0","46469739_0")) NetworkUtils.createAndAddLink(n,Id.createLinkId(id),a,b,1,1,100,1);
  var p=Id.createPersonId("p");s.getPopulation().addPerson(s.getPopulation().getFactory().createPerson(p));
  var file=Files.createTempFile("pricing2025-test", ".csv");Files.writeString(file,"id,entry,inside\nentry,1,1\ninside,0,1\n");
  var policy=new Pricing2025(s,file.toString());Files.delete(file);
  var events=EventsUtils.createEventsManager();var field=Pricing2025.class.getDeclaredField("events");field.setAccessible(true);field.set(policy,events);
  var amounts=new ArrayList<Double>();events.addHandler(new BasicEventHandler(){public void handleEvent(Event e){if(e instanceof PersonMoneyEvent m)amounts.add(m.getAmount());}});
  var v=Id.createVehicleId("v");var outside=Id.createLinkId("outside");var entry=Id.createLinkId("entry");
  policy.handleEvent(new VehicleEntersTrafficEvent(0,p,outside,v,"car",0));
  policy.handleEvent(new LinkEnterEvent(100,v,entry)); // overnight first entry
  policy.handleEvent(new LinkEnterEvent(20000,v,entry)); // no peak top-up
  policy.handleEvent(new LinkEnterEvent(86400+20000,v,entry)); // next day resets
  if(!amounts.equals(List.of(-2.25,-9.0)))throw new AssertionError(amounts);
  policy.reset(1);amounts.clear();
  policy.handleEvent(new VehicleEntersTrafficEvent(20000,p,outside,v,"car",0));
  policy.handleEvent(new LinkEnterEvent(20001,v,Id.createLinkId("320888283_0")));
  policy.handleEvent(new LinkEnterEvent(20002,v,entry));
  if(!amounts.equals(List.of(-6.0)))throw new AssertionError(amounts);
  policy.handleEvent(new VehicleLeavesTrafficEvent(21000,p,entry,v,"car",1));
  policy.handleEvent(new VehicleEntersTrafficEvent(22000,p,entry,v,"taxi",0));
  policy.handleEvent(new LinkEnterEvent(22001,v,entry));
  policy.handleEvent(new VehicleLeavesTrafficEvent(23000,p,entry,v,"taxi",1));
  policy.handleEvent(new VehicleEntersTrafficEvent(24000,p,entry,v,"FHV",0));
  if(!amounts.equals(List.of(-6.0,-.75,-1.5)))throw new AssertionError(amounts);
  if(Pricing2025.carRate(17999,true)!=2.25 || Pricing2025.carRate(18000,true)!=6 || Pricing2025.carRate(75600,true)!=2.25)throw new AssertionError("boundaries");
  policy.reset(2);amounts.clear();
  policy.handleEvent(new VehicleEntersTrafficEvent(20000,p,Id.createLinkId("inside"),v,"car",0));
  policy.handleEvent(new LinkEnterEvent(20001,v,outside));
  if(!amounts.isEmpty())throw new AssertionError("Charged start inside or exit");
  policy.handleEvent(new LinkEnterEvent(20002,v,entry));
  if(!amounts.equals(List.of(-9.0)))throw new AssertionError("Wrong first re-entry");
  policy.handleEvent(new VehicleLeavesTrafficEvent(21000,p,entry,v,"car",1));
  policy.handleEvent(new VehicleEntersTrafficEvent(22000,p,outside,v,"car",0));
  policy.handleEvent(new LinkEnterEvent(22001,v,entry));
  if(amounts.size()!=1)throw new AssertionError("Cap did not survive traffic-leg boundary");
  policy.reset(3);amounts.clear();
  policy.handleEvent(new VehicleEntersTrafficEvent(100,p,outside,v,"car",0));
  policy.handleEvent(new LinkEnterEvent(101,v,Id.createLinkId("320888283_0")));
  policy.handleEvent(new LinkEnterEvent(102,v,entry));
  if(!amounts.equals(List.of(-2.25)))throw new AssertionError("Overnight credit applied");
  policy.reset(4);amounts.clear();
  policy.handleEvent(new VehicleEntersTrafficEvent(20000,p,outside,v,"car",0));
  policy.handleEvent(new LinkEnterEvent(20001,v,Id.createLinkId("11878036_0")));
  policy.handleEvent(new LinkEnterEvent(20002,v,entry));
  if(!amounts.equals(List.of(-7.5)))throw new AssertionError("MTA inbound credit must be 1.50");
  policy.handleEvent(new VehicleLeavesTrafficEvent(21000,p,entry,v,"car",1));
  policy.handleEvent(new VehicleEntersTrafficEvent(22000,p,Id.createLinkId("inside"),v,"car",0));
  policy.handleEvent(new LinkEnterEvent(22001,v,Id.createLinkId("46469739_0")));
  policy.handleEvent(new LinkEnterEvent(22002,v,Id.createLinkId("46469739_0")));
  policy.handleEvent(new LinkEnterEvent(22003,v,Id.createLinkId("46469739_0")));
  policy.handleEvent(new LinkEnterEvent(22004,v,Id.createLinkId("46469739_0")));
  if(!amounts.equals(List.of(-7.5,1.5,1.5,.5)))throw new AssertionError("MTA exit credit / published $5 daily credit cap: "+amounts);
  policy.reset(5);amounts.clear();
  policy.handleEvent(new VehicleEntersTrafficEvent(20000,p,Id.createLinkId("inside"),v,"car",0));
  policy.handleEvent(new LinkEnterEvent(20001,v,Id.createLinkId("46469739_0")));
  if(!amounts.isEmpty())throw new AssertionError("Refund without any charge");
  policy.handleEvent(new VehicleLeavesTrafficEvent(21000,p,outside,v,"car",1));
  policy.handleEvent(new VehicleEntersTrafficEvent(22000,p,outside,v,"car",0));
  policy.handleEvent(new LinkEnterEvent(22001,v,Id.createLinkId("11878036_0")));
  policy.handleEvent(new LinkEnterEvent(22002,v,entry));
  if(!amounts.equals(List.of(-6.0)))throw new AssertionError("Same-day return credit");
  policy.reset(6);amounts.clear();
  var factory=s.getPopulation().getFactory();var plan=factory.createPlan();
  for(String mode:List.of("taxi","FHV","taxi")) {
   var leg=factory.createLeg(mode);
   var route=org.matsim.core.population.routes.RouteUtils.createLinkNetworkRouteImpl(outside,outside);
   route.setLinkIds(outside,mode.equals("FHV")?List.of():List.of(Id.createLinkId("inside")),outside);
   leg.setRoute(route);plan.addLeg(leg);
  }
  var person=s.getPopulation().getPersons().get(p);person.addPlan(plan);person.setSelectedPlan(plan);
  policy.handleEvent(new PersonDepartureEvent(20000,p,outside,"taxi","taxi"));
  policy.handleEvent(new PersonDepartureEvent(21000,p,outside,"FHV","FHV"));
  policy.handleEvent(new PersonDepartureEvent(22000,p,outside,"taxi","taxi"));
  if(!amounts.equals(List.of(-.75,-.75)))throw new AssertionError("Teleported route-based trip fees / outside exemption: "+amounts);
  policy.reset(7);amounts.clear();
  var fhv=factory.createPlan();var fhvLeg=factory.createLeg("FHV");
  fhvLeg.setRoute(org.matsim.core.population.routes.RouteUtils.createLinkNetworkRouteImpl(Id.createLinkId("inside"),outside));fhv.addLeg(fhvLeg);person.addPlan(fhv);person.setSelectedPlan(fhv);
  policy.handleEvent(new PersonDepartureEvent(20000,p,Id.createLinkId("inside"),"FHV","FHV"));
  if(!amounts.equals(List.of(-1.5)))throw new AssertionError("Teleported FHV origin inside fee");
  System.out.println("PASS: first entry, daily reset, no top-up, tunnel credit, taxi/FHV single-trip fees, iteration reset and peak boundaries");
 }
}

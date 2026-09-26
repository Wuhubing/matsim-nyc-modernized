package org.c2smart.matsimnyc;

import java.util.ArrayList;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.events.*;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.events.handler.BasicEventHandler;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.scoring.functions.CharyparNagelScoringFunctionFactory;
import org.matsim.core.network.NetworkUtils;

public class VerifyRestoration {
    static void close(double a, double b) {
        if (Math.abs(a-b)>1e-9) throw new AssertionError(a+" != "+b);
    }
    public static void main(String[] args) {
        var config = ConfigUtils.createConfig();
        config.network().setTimeVariantNetwork(true);
        var scenario = ScenarioUtils.createScenario(config);
        var person = scenario.getPopulation().getFactory().createPerson(Id.createPersonId("driver"));
        scenario.getPopulation().addPerson(person);
        var events = EventsUtils.createEventsManager();
        var observed = new ArrayList<PersonScoreEvent>();
        events.addHandler(new BasicEventHandler() {
            public void handleEvent(Event e) { if (e instanceof PersonScoreEvent s) observed.add(s); }
        });
        var costs = new LegacyCosts(events, scenario);
        var vehicle = Id.createVehicleId("vehicle-with-unrelated-id");
        var toll = Id.createLinkId("320888283_0");
        costs.handleEvent(new VehicleEntersTrafficEvent(21600,person.getId(),toll,vehicle,"car",0));
        costs.handleEvent(new LinkLeaveEvent(21601,vehicle,toll));
        if (observed.size()!=1 || !observed.getFirst().getPersonId().equals(person.getId()))
            throw new AssertionError("First-trip driver mapping failed");
        close(observed.getFirst().getAmount(),-12.5*LegacyCosts.MONEY_UTILITY);
        costs.handleEvent(new PersonArrivalEvent(22000,person.getId(),toll,"car"));
        costs.handleEvent(new PersonArrivalEvent(22000,person.getId(),toll,"taxi"));
        costs.handleEvent(new PersonArrivalEvent(22000,person.getId(),toll,"FHV"));
        costs.handleEvent(new PersonArrivalEvent(22000,person.getId(),toll,"pt"));
        costs.handleEvent(new PersonArrivalEvent(22000,Id.createPersonId("pt_driver"),toll,"car"));
        if (observed.size()!=4) throw new AssertionError("Wrong arrival charges");
        close(observed.get(1).getAmount(),-5.19*LegacyCosts.MONEY_UTILITY);
        close(observed.get(2).getAmount(),-5.80*LegacyCosts.MONEY_UTILITY);
        close(observed.get(3).getAmount(),-5.25*LegacyCosts.MONEY_UTILITY);
        costs.reset(1);
        costs.handleEvent(new LinkLeaveEvent(22000,vehicle,toll));
        if (observed.size()!=4) throw new AssertionError("Driver map leaked across iterations");
        close(LegacyCosts.toll(toll.toString(),21599),10.5);
        close(LegacyCosts.toll(toll.toString(),36000),10.5);
        close(LegacyCosts.toll(toll.toString(),57600),12.5);
        close(LegacyCosts.toll(toll.toString(),72000),10.5);
        close(LegacyCosts.toll(toll.toString(),108000),12.5);
        close(LegacyCosts.toll("40596823_0",1),6.12);
        close(LegacyCosts.toll("untolled",1),0);
        var scoring = new CharyparNagelScoringFunctionFactory(scenario).createNewScoringFunction(person);
        scoring.addScore(observed.getFirst().getAmount());
        close(scoring.getScore(),observed.getFirst().getAmount());
        close(PublishedNetwork.speed(33.333333333333336,0),36.88*.44704);
        close(PublishedNetwork.speed(8.333333333333334,0),14.10*.44704);
        close(PublishedNetwork.period(21599),5);
        close(PublishedNetwork.period(21600),0);
        close(PublishedNetwork.period(75600),5);
        var network=scenario.getNetwork();
        var a=network.getFactory().createNode(Id.createNodeId("a"),new org.matsim.api.core.v01.Coord(0,0));
        var b=network.getFactory().createNode(Id.createNodeId("b"),new org.matsim.api.core.v01.Coord(100,0));
        network.addNode(a);network.addNode(b);
        var link=network.getFactory().createLink(Id.createLinkId("road"),a,b);
        link.setFreespeed(33.333333333333336);link.setCapacity(3600);network.addLink(link);
        PublishedNetwork.apply(network,108000);
        var changes=NetworkUtils.getNetworkChangeEvents(network);
        if(changes.size()!=8) throw new AssertionError("Expected 0,6,9,12,15,18,21,30 hours");
        for(var change:changes) if(change.getStartTime()==21600) {
            close(change.getFlowCapacityChange().getValue(),.61);
            close(change.getFreespeedChange().getValue(),36.88*.44704);
        }
        var sc=config.scoring();
        sc.setUtilityOfLineSwitch(0);
        sc.getOrCreateModeParams("walk").setConstant(9);
        sc.getOrCreateModeParams("pt").setConstant(2);
        sc.getOrCreateModeParams("pt").setMarginalUtilityOfTraveling(0);
        for(var mode:java.util.List.of("access_walk","egress_walk","transit_walk")) {
            sc.getOrCreateModeParams(mode).setConstant(0);
            sc.getOrCreateModeParams(mode).setMarginalUtilityOfTraveling(
                    mode.equals("access_walk")?-1:mode.equals("egress_walk")?-2:-3);
        }
        var parameters=new org.matsim.core.scoring.functions.SubpopulationScoringParameters(scenario).getScoringParameters(person);
        var pts=new NycScoring.TransitWalkScoring(parameters,java.util.Set.of("pt"));
        var elements=new java.util.ArrayList<org.matsim.api.core.v01.population.PlanElement>();
        elements.add(org.matsim.core.population.PopulationUtils.createActivityFromCoord("Home",a.getCoord()));
        String[] modes={"walk","pt","walk","pt","walk"};
        double[] durations={60,600,30,600,120};
        for(int i=0;i<modes.length;i++) {
            var leg=org.matsim.core.population.PopulationUtils.createLeg(modes[i]);
            leg.setTravelTime(durations[i]);leg.setDepartureTime(0);
            var route=org.matsim.core.population.routes.RouteUtils.createGenericRouteImpl(toll,toll);
            route.setDistance(0);leg.setRoute(route);elements.add(leg);
            if(i<4) elements.add(org.matsim.core.population.PopulationUtils.createActivityFromCoord("pt interaction",a.getCoord()));
        }
        elements.add(org.matsim.core.population.PopulationUtils.createActivityFromCoord("Work",a.getCoord()));
        var trip=org.matsim.core.router.TripStructureUtils.getTrips(elements).getFirst();
        pts.handleTrip(trip);
        var zipScoring=new NycScoring.TransitWalkScoring(parameters,java.util.Set.of("pt"),false);
        zipScoring.handleTrip(trip);
        close(zipScoring.getScore()-pts.getScore(),2.75*parameters.marginalUtilityOfMoney);
        close(pts.getScore(),2-(60+120*2+30*3)/3600.0-2.75*parameters.marginalUtilityOfMoney);
        if(!trip.getLegsOnly().getFirst().getMode().equals("walk")) throw new AssertionError("Scoring changed the plan");
        var perPerson=new org.matsim.core.scoring.functions.SubpopulationScoringParameters(scenario);
        var tracker=new NycOccupancyTracker(new ch.sbb.matsim.routing.pt.raptor.OccupancyData(),scenario,
                new ch.sbb.matsim.routing.pt.raptor.DefaultRaptorInVehicleCostCalculator(),events,perPerson);
        tracker.handleEvent(new PersonDepartureEvent(0,Id.createPersonId("synthetic-transit-driver"),toll,"car","car"));
        var routeParams=new NycTransitRouting(new ch.sbb.matsim.routing.pt.raptor.IndividualRaptorParametersForPerson(config,perPerson),perPerson)
                .getRaptorParameters(person);
        close(routeParams.getMarginalUtilityOfTravelTime_utl_s("walk"),-3.0/3600-parameters.marginalUtilityOfPerforming_s);
        var walkElements=java.util.List.<org.matsim.api.core.v01.population.PlanElement>of(elements.getFirst(),trip.getLegsOnly().getFirst(),elements.getLast());
        var walkScoring=new NycScoring.TransitWalkScoring(parameters,java.util.Set.of("pt"));
        walkScoring.handleTrip(org.matsim.core.router.TripStructureUtils.getTrips(walkElements).getFirst());
        close(walkScoring.getScore(),9+60*parameters.modeParams.get("walk").marginalUtilityOfTraveling_s);
        System.out.println("PASS: actual score events, first-trip attribution, fixed fares, exemptions, reset, toll boundaries, published network units/times");
        System.out.println("PASS: separate access/egress/transfer utilities, no spurious walking constant, original plans preserved");
    }
}

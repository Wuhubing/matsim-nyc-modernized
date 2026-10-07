package org.c2smart.matsimnyc;
import java.nio.file.*;
import java.util.zip.GZIPInputStream;
import java.nio.charset.StandardCharsets;
import org.matsim.api.core.v01.*;
import org.matsim.api.core.v01.events.*;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.controler.events.BeforeMobsimEvent;
import org.matsim.core.population.routes.RouteUtils;

public class VerifyResearchMetrics {
    static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    static String read(Path p)throws Exception{try(var in=new GZIPInputStream(Files.newInputStream(p))){return new String(in.readAllBytes(),StandardCharsets.UTF_8);}}
    public static void main(String[] args)throws Exception {
        var cfg=ConfigUtils.createConfig();cfg.global().setCoordinateSystem("EPSG:4326");cfg.qsim().setEndTime(108000);
        var s=ScenarioUtils.createScenario(cfg);var f=s.getPopulation().getFactory();
        var p=f.createPerson(Id.createPersonId("p"));p.getAttributes().putAttribute("subpopulation","man");
        var plan=f.createPlan();var a=f.createActivityFromCoord("home",new Coord(0.5,0.5));a.setEndTime(3600);plan.addActivity(a);
        var leg=f.createLeg("car");leg.setDepartureTime(3600);leg.setTravelTime(10);
        var route=RouteUtils.createLinkNetworkRouteImpl(Id.createLinkId("l"),Id.createLinkId("l"));leg.setRoute(route);plan.addLeg(leg);
        plan.addActivity(f.createActivityFromCoord("work",new Coord(2,2)));p.addPlan(plan);p.setSelectedPlan(plan);plan.setScore(3.0);s.getPopulation().addPerson(p);
        var nf=s.getNetwork().getFactory();var n1=nf.createNode(Id.createNodeId("n1"),new Coord(0,0));var n2=nf.createNode(Id.createNodeId("n2"),new Coord(1,1));s.getNetwork().addNode(n1);s.getNetwork().addNode(n2);
        var link=nf.createLink(Id.createLinkId("l"),n1,n2);s.getNetwork().addLink(link);
        var dir=Files.createTempDirectory("research-test");var polygon=dir.resolve("zone.json");
        Files.writeString(polygon,"{\"geometry\":{\"coordinates\":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}}");
        var entry=dir.resolve("entries.csv");Files.writeString(entry,"link,entry\nl,1\n");System.setProperty("nyc.metricLinks",entry.toString());
        var m=new ResearchMetrics(s,dir,polygon);
        check(!Files.exists(dir.resolve("research")),"Constructor must not create controller output files");
        check(ResearchMetrics.inside(0,0.5,new double[][]{{0,0},{1,0},{1,1},{0,1},{0,0}}),"boundary inclusion");
        String choice=ResearchMetrics.fingerprint(plan,false),full=ResearchMetrics.fingerprint(plan,true);
        leg.setTravelTime(999);plan.setScore(4.0);
        check(full.equals(ResearchMetrics.fingerprint(plan,true)),"Mutable score/travel estimates must not change chosen plan hash");
        a.setEndTime(3601);check(choice.equals(ResearchMetrics.fingerprint(plan,false)),"timing excluded from choice");check(!full.equals(ResearchMetrics.fingerprint(plan,true)),"timing included in full plan");
        var legacy=new IterationMetrics(s,entry.toString(),dir.toString());
        var events=org.matsim.core.events.EventsUtils.createEventsManager();events.addHandler(m);events.addHandler(legacy);
        legacy.reset(0);
        m.reset(0);m.notifyBeforeMobsim(new BeforeMobsimEvent(null,0,false));
        var v=Id.createVehicleId("v");var l=link.getId();
        events.processEvent(new PersonDepartureEvent(3600,p.getId(),l,"car","car"));
        events.processEvent(new VehicleEntersTrafficEvent(3600,p.getId(),l,v,"car",0));
        events.processEvent(new LinkEnterEvent(3610,v,l));events.processEvent(new LinkLeaveEvent(3630,v,l));
        events.processEvent(new LinkEnterEvent(3640,v,l));events.processEvent(new VehicleLeavesTrafficEvent(3650,p.getId(),l,v,"car",1));
        events.processEvent(new VehicleEntersTrafficEvent(80000,p.getId(),l,v,"car",0));events.processEvent(new LinkLeaveEvent(80001,v,l));
        events.processEvent(new VehicleAbortsEvent(80002,v,l));
        events.processEvent(new PersonArrivalEvent(80003,p.getId(),l,"car"));
        events.processEvent(new PersonMoneyEvent(80004,p.getId(),-9.0,"toll","test",null));
        events.processEvent(new PersonDepartureEvent(81000,p.getId(),l,"pt","pt"));
        events.processEvent(new org.matsim.core.api.experimental.events.AgentWaitingForPtEvent(81000,p.getId(),null,null));
        events.processEvent(new org.matsim.core.mobsim.qsim.pt.PersonEntersPtVehicleEvent(81010,p.getId(),v,null,null));
        events.processEvent(new PersonArrivalEvent(81100,p.getId(),l,"pt"));
        events.processEvent(new PersonDepartureEvent(107500,p.getId(),l,"pt","pt"));
        events.processEvent(new org.matsim.core.api.experimental.events.AgentWaitingForPtEvent(107500,p.getId(),null,null));
        events.processEvent(new PersonStuckEvent(108000,p.getId(),l,"pt"));
        legacy.notifyIterationEnds(new org.matsim.core.controler.events.IterationEndsEvent(null,0,false));
        m.finish(0);
        var json=new com.fasterxml.jackson.databind.ObjectMapper().readTree(dir.resolve("iteration-metrics-0.json").toFile());
        check(json.get("private_car_entry_crossings").asLong()==2,"legacy crossing equivalence");
        check(json.get("unfinished_all").asLong()==1,"legacy unfinished equivalence");
        check(Math.abs(json.get("censored_wait_person_hours").asDouble()*3600-510)<1e-8,"censored waits equivalence");
        String rows=read(dir.resolve("research/link-hours-0.csv.gz"));
        check(rows.contains("\"l\",1,\"car\",2,1,20.0"),"entry hour, correct denominator, no parked-time pairing: "+rows);
        String people=read(dir.resolve("research/persons-0.csv.gz"));check(people.contains("\"p\",\"man\",\"related\""),"fixed activity cohort");
        check(people.contains(",510.0,9.0,2\n"),"revenue and entries");
        m.reset(1);m.notifyBeforeMobsim(new BeforeMobsimEvent(null,1,false));m.finish(1);
        check(read(dir.resolve("research/persons-1.csv.gz")).contains(",false,false,"),"previous signatures survive reset");
        check(read(dir.resolve("research/link-hours-1.csv.gz")).lines().count()==1,"link state resets");
        check(Files.readString(dir.resolve("research/diagnostics-0.json")).contains("\"errors\" : { }"),"event conservation");
        // Exercise actual MATSim output-directory initialization, not only handler methods.
        var startupConfig=ConfigUtils.createConfig();startupConfig.global().setCoordinateSystem("EPSG:4326");startupConfig.qsim().setEndTime(60);
        startupConfig.controller().setOutputDirectory(dir.resolve("startup-simulation").toString());
        var startupScenario=ScenarioUtils.createScenario(startupConfig);
        var startupMetrics=new ResearchMetrics(startupScenario,dir.resolve("startup-simulation"),polygon);
        var controller=new org.matsim.core.controler.Controler(startupScenario);
        controller.addOverridingModule(new org.matsim.core.controler.AbstractModule(){
            @Override public void install(){addEventHandlerBinding().toInstance(startupMetrics);addControllerListenerBinding().toInstance(startupMetrics);}
        });
        controller.getInjector();
        check(Files.isDirectory(dir.resolve("startup-simulation")),"MATSim owns output directory initialization");
        startupMetrics.notifyBeforeMobsim(new BeforeMobsimEvent(null,0,false));
        check(Files.isRegularFile(dir.resolve("startup-simulation/research/schema.json")),"Deferred metadata written after initialization");
        System.out.println("PASS: controller startup and deferred output creation");
        System.out.println("PASS: research cohorts, signatures, group counters, link-hour pairing, exit/abort, reset, observational plan state");
    }
}

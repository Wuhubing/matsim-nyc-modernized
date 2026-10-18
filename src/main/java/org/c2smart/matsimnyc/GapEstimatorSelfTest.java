package org.c2smart.matsimnyc;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.matsim.api.core.v01.Coord;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.TransportMode;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.api.core.v01.network.Node;
import org.matsim.api.core.v01.population.Activity;
import org.matsim.api.core.v01.population.Leg;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.Plan;
import org.matsim.api.core.v01.population.Population;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.config.groups.ScoringConfigGroup;
import org.matsim.core.controler.AbstractModule;
import org.matsim.core.controler.Controler;
import org.matsim.core.controler.ControlerDefaultsModule;
import org.matsim.core.controler.Injector;
import org.matsim.core.controler.NewControlerModule;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.population.routes.NetworkRoute;
import org.matsim.core.population.routes.RouteUtils;
import org.matsim.core.router.TripRouter;
import org.matsim.core.router.TripStructureUtils;
import org.matsim.core.scenario.ScenarioByInstanceModule;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.scoring.ScoringFunctionFactory;

/**
 * V0 of QR3/06_G_estimator_design.md: checks of {@link PlanEstimator} on a tiny synthetic network with known answers.
 *   T1 a plan on the fastest routes has route gap exactly 0;
 *   T2 a plan with a slow outbound route: re-routing gives exactly the score of the T1 plan, and a positive gap;
 *   T3 the best single-subtour mode change is at least the current plan, and equals a direct estimate of that plan;
 *   T4 the estimate of the T2 plan matches the score MATSim's own QSim and scoring give it (one iteration, no replanning).
 * Run: java -cp runner.jar org.c2smart.matsimnyc.GapEstimatorSelfTest
 */
public final class GapEstimatorSelfTest {
    private GapEstimatorSelfTest() {}

    public static void main(String[] args) throws Exception {
        Path tmp = Files.createTempDirectory("gap-selftest-");
        Config config = config(tmp.resolve("inj"));
        Scenario scenario = scenario(config);
        LinkHourTravelTime tt = LinkHourTravelTime.freeFlow();
        AbstractModule base = new AbstractModule() {
            @Override public void install() {
                install(new NewControlerModule()); install(PlanEstimator.coreListenersModule()); 
                install(new ControlerDefaultsModule()); install(new ScenarioByInstanceModule(scenario));
            }
        };
        AbstractModule overrides = new AbstractModule() {
            @Override public void install() { addTravelTimeBinding(TransportMode.car).toInstance(tt); }
        };
        var injector = Injector.createInjector(config, AbstractModule.override(List.of(base), overrides));
        PlanEstimator.ensureVehicles(injector, scenario);
        TripRouter router = injector.getInstance(TripRouter.class);
        ScoringFunctionFactory scoring = injector.getInstance(ScoringFunctionFactory.class);
        PlanEstimator est = new PlanEstimator(scenario, tt, scoring, Set.of(TransportMode.car), false, false, null, 30 * 3600);
        Person fast = scenario.getPopulation().getPersons().get(Id.createPersonId("fast"));
        Person slow = scenario.getPopulation().getPersons().get(Id.createPersonId("slow"));
        List<String> failed = new ArrayList<>();

        var f0 = est.estimate(fast, PlanEstimator.copy(fast.getSelectedPlan()), Set.of(), router);
        var f1 = est.estimate(fast, PlanEstimator.copy(fast.getSelectedPlan()), new HashSet<>(est.networkTrips(fast.getSelectedPlan())), router);
        check(failed, "T1 fastest plan: route gap = 0", Math.abs(f1.score() - f0.score()) < 1e-9, f0.score() + " vs " + f1.score());

        var s0 = est.estimate(slow, PlanEstimator.copy(slow.getSelectedPlan()), Set.of(), router);
        var s1 = est.estimate(slow, PlanEstimator.copy(slow.getSelectedPlan()), new HashSet<>(est.networkTrips(slow.getSelectedPlan())), router);
        check(failed, "T2 slow plan: route gap > 0", s1.score() - s0.score() > 1e-6, "gap " + (s1.score() - s0.score()) + ", failures " + s1.failures() + ", error " + s1.error());
        check(failed, "T2 re-routed slow plan = fastest plan", Math.abs(s1.score() - f0.score()) < 1e-9, s1.score() + " vs " + f0.score());

        Plan walk = PlanEstimator.copy(slow.getSelectedPlan());
        PlanEstimator.setTripMode(walk, 0, TransportMode.walk);
        PlanEstimator.setTripMode(walk, 1, TransportMode.walk);
        var w = est.estimate(slow, walk, Set.of(0, 1), router);
        check(failed, "T3 walk alternative is estimated", w.failures() == 0 && !Double.isNaN(w.score()), "score " + w.score());
        double best = Math.max(s0.score(), w.score());
        check(failed, "T3 best mode >= current", best >= s0.score(), best + " vs " + s0.score());

        // T4: MATSim itself, iteration 0 only, same plans
        Config c2 = config(tmp.resolve("qsim"));
        Scenario sc2 = scenario(c2);
        c2.controller().setLastIteration(0);
        new Controler(sc2).run();
        Plan executed = sc2.getPopulation().getPersons().get(Id.createPersonId("slow")).getSelectedPlan();
        double matsim = executed.getScore();
        // QSim moves vehicles in whole seconds and needs one second per node; allow a few seconds per leg
        double perSecond = 6.0 / 3600 + config.scoring().getPerforming_utils_hr() / 3600;
        check(failed, "T4 estimate vs MATSim score", Math.abs(matsim - s0.score()) < 20 * perSecond,
                "MATSim " + matsim + ", estimate " + s0.score() + ", diff " + (matsim - s0.score()));

        System.out.println(failed.isEmpty() ? "ALL PASSED" : "FAILED: " + failed);
        if (!failed.isEmpty()) System.exit(1);
    }

    private static void check(List<String> failed, String name, boolean ok, String detail) {
        System.out.printf("%-45s %s  (%s)%n", name, ok ? "ok" : "FAIL", detail);
        if (!ok) failed.add(name);
    }

    static Config config(Path out) {
        Config config = ConfigUtils.createConfig();
        config.controller().setOutputDirectory(out.toString());
        config.controller().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.deleteDirectoryIfExists);
        config.controller().setLastIteration(0);
        config.controller().setWriteEventsInterval(0);
        config.controller().setWritePlansInterval(0);
        config.controller().setCreateGraphsInterval(0);
        config.controller().setDumpDataAtEnd(false);
        config.routing().setRoutingRandomness(0.0);
        config.qsim().setEndTime(30 * 3600);
        for (String type : List.of("home", "work")) {
            var p = new ScoringConfigGroup.ActivityParams(type);
            p.setTypicalDuration(type.equals("home") ? 14 * 3600 : 8 * 3600);
            config.scoring().addActivityParams(p);
        }
        config.scoring().getOrCreateModeParams(TransportMode.car).setMarginalUtilityOfTraveling(-6);
        config.scoring().getOrCreateModeParams(TransportMode.walk).setMarginalUtilityOfTraveling(-6);
        var strategy = new org.matsim.core.config.groups.ReplanningConfigGroup.StrategySettings();
        strategy.setStrategyName("BestScore"); strategy.setWeight(1);
        config.replanning().addStrategySettings(strategy);
        return config;
    }

    /** Home link h, work link w; outbound fast via n2 (2 km) or slow via n4 (3 km); return fast via n2. */
    static Scenario scenario(Config config) {
        Scenario scenario = ScenarioUtils.createScenario(config);
        Network net = scenario.getNetwork();
        var nf = net.getFactory();
        Node n0 = node(net, "n0", 0, 0), n1 = node(net, "n1", 100, 0), n2 = node(net, "n2", 1100, 0), n3 = node(net, "n3", 2100, 0),
                n4 = node(net, "n4", 1100, 1118), n5 = node(net, "n5", 2200, 0);
        link(net, "h", n0, n1, 100); link(net, "hr", n1, n0, 100);
        link(net, "f1", n1, n2, 1000); link(net, "f2", n2, n3, 1000); link(net, "f2r", n3, n2, 1000); link(net, "f1r", n2, n1, 1000);
        link(net, "s1", n1, n4, 1500); link(net, "s2", n4, n3, 1500);
        link(net, "w", n3, n5, 100); link(net, "wr", n5, n3, 100);
        Population pop = scenario.getPopulation();
        pop.addPerson(person(pop, "fast", List.of("f1", "f2")));
        pop.addPerson(person(pop, "slow", List.of("s1", "s2")));
        return scenario;
    }

    private static Node node(Network net, String id, double x, double y) {
        Node n = net.getFactory().createNode(Id.createNodeId(id), new Coord(x, y)); net.addNode(n); return n;
    }

    private static void link(Network net, String id, Node from, Node to, double length) {
        Link l = net.getFactory().createLink(Id.createLinkId(id), from, to);
        l.setLength(length); l.setFreespeed(10); l.setCapacity(3600); l.setNumberOfLanes(1);
        l.setAllowedModes(Set.of(TransportMode.car)); net.addLink(l);
    }

    private static Person person(Population pop, String id, List<String> outbound) {
        var f = pop.getFactory();
        Person p = f.createPerson(Id.createPersonId(id));
        Plan plan = f.createPlan();
        Activity home = f.createActivityFromLinkId("home", Id.createLinkId("h")); home.setEndTime(7 * 3600); home.setCoord(new Coord(50, 0));
        Activity work = f.createActivityFromLinkId("work", Id.createLinkId("w")); work.setEndTime(16 * 3600); work.setCoord(new Coord(2150, 0));
        Activity back = f.createActivityFromLinkId("home", Id.createLinkId("h")); back.setCoord(new Coord(50, 0));
        plan.addActivity(home);
        plan.addLeg(leg(f, "h", outbound, "w"));
        plan.addActivity(work);
        plan.addLeg(leg(f, "w", List.of("wr", "f2r", "f1r", "hr"), "h"));
        plan.addActivity(back);
        p.addPlan(plan);
        PopulationUtils.putSubpopulation(p, "man");
        return p;
    }

    private static Leg leg(org.matsim.api.core.v01.population.PopulationFactory f, String from, List<String> links, String to) {
        Leg leg = f.createLeg(TransportMode.car);
        TripStructureUtils.setRoutingMode(leg, TransportMode.car);
        List<Id<Link>> ids = new ArrayList<>();
        for (String s : links) ids.add(Id.createLinkId(s));
        NetworkRoute r = RouteUtils.createLinkNetworkRouteImpl(Id.createLinkId(from), ids, Id.createLinkId(to));
        leg.setRoute(r);
        return leg;
    }
}

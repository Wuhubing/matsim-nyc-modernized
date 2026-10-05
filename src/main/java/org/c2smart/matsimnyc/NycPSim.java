package org.c2smart.matsimnyc;

import com.google.inject.Inject;
import com.google.inject.name.Names;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.events.*;
import org.matsim.api.core.v01.events.handler.*;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.api.experimental.events.EventsManager;
import org.matsim.core.api.experimental.events.TeleportationArrivalEvent;
import org.matsim.core.api.experimental.events.VehicleArrivesAtFacilityEvent;
import org.matsim.core.api.experimental.events.handler.VehicleArrivesAtFacilityEventHandler;
import org.matsim.core.controler.AbstractModule;
import org.matsim.core.controler.Controler;
import org.matsim.core.controler.events.*;
import org.matsim.core.controler.listener.*;
import org.matsim.core.mobsim.framework.Mobsim;
import org.matsim.core.mobsim.qsim.QSimProvider;
import org.matsim.core.router.TripStructureUtils;
import org.matsim.core.router.util.TravelTime;
import org.matsim.core.trafficmonitoring.TravelTimeCalculator;
import org.matsim.vehicles.Vehicle;
import org.matsim.vehicles.VehicleUtils;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Collectors;

/** Pseudo-simulation (PSim) adapted to the NYC scenario, after org.matsim.contrib.pseudosimulation.
 *
 * In PSim iterations only plans that replanning changed are evaluated, by replaying them on frozen link
 * travel times from the latest QSim iteration; unchanged selected plans keep their previous score.
 * Differences from the contrib: car, taxi and FHV are all network modes with their own vehicles (so
 * congestion charges and facility tolls are billed by the normal handlers), transit legs use their routed
 * travel time instead of an emulator, the router's car travel times are frozen during PSim iterations by
 * gating the calculator's events and resets, and link times can use a robust geometric mean.
 *
 * Enable with -Dnyc.psim=cycle:K (QSim on the first, last and every K-th iteration; K=1 is all-QSim) and
 * optionally -Dnyc.psim.linkTime=mean|geometric (default mean = contrib behaviour). */
public final class NycPSim {
    static final Set<String> NETWORK_MODES = Set.of("car", "taxi", "FHV");
    static final double BIN = 900;

    private NycPSim() {}

    public static void install(Controler controler, Scenario scenario, String schedule, String linkTime) {
        int cycle = Integer.parseInt(schedule.replace("cycle:", ""));
        if (!schedule.startsWith("cycle:") || cycle < 1) throw new IllegalArgumentException("nyc.psim must be cycle:K with K>=1");
        boolean geometric = "geometric".equals(linkTime);
        if (!geometric && !"mean".equals(linkTime)) throw new IllegalArgumentException("nyc.psim.linkTime must be mean or geometric");
        var config = scenario.getConfig();
        if (!config.travelTimeCalculator().getSeparateModes() || !config.routing().getNetworkModes().equals(Set.of("car")))
            throw new IllegalArgumentException("NycPSim expects separate travel times with car as the only routed network mode");
        Switch sw = new Switch(scenario, cycle, config.controller().getFirstIteration(), config.controller().getLastIteration(),
                Path.of(config.controller().getOutputDirectory()));
        // Same construction as TravelTimeCalculatorModule.SingleModeTravelTimeCalculatorProvider, but registered
        // behind a gate instead of directly with the events manager.
        var builder = new TravelTimeCalculator.Builder(scenario.getNetwork());
        var tt = config.travelTimeCalculator();
        builder.setTimeslice(tt.getTraveltimeBinSize()); builder.setMaxTime(tt.getMaxTime());
        builder.setCalculateLinkTravelTimes(tt.isCalculateLinkTravelTimes());
        builder.setCalculateLinkToLinkTravelTimes(tt.isCalculateLinkToLinkTravelTimes());
        builder.setFilterModes(true); builder.setAnalyzedModes(Set.of("car")); builder.configure(tt);
        TravelTimeCalculator calculator = builder.build();
        Gate gate = new Gate(calculator, sw, geometric ? new RobustTimes() : null);
        controler.addOverridingModule(new AbstractModule() {
            @Override public void install() {
                bind(TravelTimeCalculator.class).annotatedWith(Names.named("car")).toInstance(calculator);
                addEventHandlerBinding().toInstance(gate);
                addControllerListenerBinding().toInstance(sw);
                bind(Switch.class).toInstance(sw);
                bind(Gate.class).toInstance(gate);
                bind(QSimProvider.class);
                bindMobsim().toProvider(SwitchingProvider.class);
            }
        });
    }

    /** Decides QSim vs PSim per iteration and preserves the scores of plans PSim does not evaluate. */
    public static final class Switch implements IterationStartsListener, BeforeMobsimListener, IterationEndsListener {
        private final Scenario scenario;
        private final int cycle, first, last;
        private final Path log;
        private boolean qsim = true;
        private Map<Id<Person>, Plan> before = Map.of();
        private final Map<Id<Person>, Double> keptScores = new HashMap<>();
        final List<Plan> toSimulate = new ArrayList<>();
        long psimMillis;

        Switch(Scenario scenario, int cycle, int first, int last, Path outputDirectory) {
            this.scenario = scenario; this.cycle = cycle; this.first = first; this.last = last; this.log = outputDirectory.resolve("psim-log.csv");
        }
        boolean isQSim() { return qsim; }
        @Override public void notifyIterationStarts(IterationStartsEvent e) {
            int i = e.getIteration();
            qsim = i == first || i == last || (i - first) % cycle == 0;
            if (!qsim) before = scenario.getPopulation().getPersons().values().stream()
                    .collect(Collectors.toMap(Person::getId, Person::getSelectedPlan));
        }
        @Override public void notifyBeforeMobsim(BeforeMobsimEvent e) {
            keptScores.clear(); toSimulate.clear();
            if (qsim) return;
            for (Person p : scenario.getPopulation().getPersons().values()) {
                Plan selected = p.getSelectedPlan();
                if (selected == before.get(p.getId()) && selected.getScore() != null) keptScores.put(p.getId(), selected.getScore());
                else toSimulate.add(selected);
            }
        }
        @Override public void notifyIterationEnds(IterationEndsEvent e) {
            for (var entry : keptScores.entrySet())
                scenario.getPopulation().getPersons().get(entry.getKey()).getSelectedPlan().setScore(entry.getValue());
            try {
                if (!Files.exists(log)) Files.writeString(log, "iteration,mobsim,plans_simulated,plans_kept,psim_seconds\n");
                Files.writeString(log, String.format(Locale.ROOT, "%d,%s,%d,%d,%.3f%n", e.getIteration(), qsim ? "qsim" : "psim",
                        qsim ? scenario.getPopulation().getPersons().size() : toSimulate.size(), keptScores.size(), qsim ? 0 : psimMillis / 1000.0),
                        StandardOpenOption.APPEND);
            } catch (IOException x) { throw new UncheckedIOException(x); }
            before = Map.of();
        }
    }

    /** Forwards traffic events and resets to the router's car travel-time calculator only in QSim iterations. */
    public static final class Gate implements LinkEnterEventHandler, LinkLeaveEventHandler, VehicleEntersTrafficEventHandler,
            VehicleLeavesTrafficEventHandler, VehicleArrivesAtFacilityEventHandler, VehicleAbortsEventHandler {
        final TravelTimeCalculator calculator; final Switch sw; final RobustTimes robust;
        Gate(TravelTimeCalculator calculator, Switch sw, RobustTimes robust) { this.calculator = calculator; this.sw = sw; this.robust = robust; }
        @Override public void reset(int iteration) { if (sw.isQSim()) { calculator.reset(iteration); if (robust != null) robust.reset(); } }
        @Override public void handleEvent(LinkEnterEvent e) { if (sw.isQSim()) { calculator.handleEvent(e); if (robust != null) robust.enter(e); } }
        @Override public void handleEvent(LinkLeaveEvent e) { if (sw.isQSim()) { calculator.handleEvent(e); if (robust != null) robust.leave(e); } }
        @Override public void handleEvent(VehicleEntersTrafficEvent e) { if (sw.isQSim()) { calculator.handleEvent(e); if (robust != null) robust.traffic(e); } }
        @Override public void handleEvent(VehicleLeavesTrafficEvent e) { if (sw.isQSim()) { calculator.handleEvent(e); if (robust != null) robust.untrack(e.getVehicleId()); } }
        @Override public void handleEvent(VehicleArrivesAtFacilityEvent e) { if (sw.isQSim()) calculator.handleEvent(e); }
        @Override public void handleEvent(VehicleAbortsEvent e) { if (sw.isQSim()) { calculator.handleEvent(e); if (robust != null) robust.untrack(e.getVehicleId()); } }
    }

    /** Geometric-mean link traversal time per 15-minute bin for car/taxi/FHV vehicles (heavy-tail robust). */
    static final class RobustTimes {
        private final Map<Long, double[]> bins = new HashMap<>();
        private final Map<Id<Vehicle>, double[]> entered = new HashMap<>();
        private final Set<Id<Vehicle>> tracked = new HashSet<>();
        void reset() { bins.clear(); entered.clear(); tracked.clear(); }
        void traffic(VehicleEntersTrafficEvent e) { if (NETWORK_MODES.contains(e.getNetworkMode())) tracked.add(e.getVehicleId()); }
        void untrack(Id<Vehicle> v) { tracked.remove(v); entered.remove(v); }
        void enter(LinkEnterEvent e) { if (tracked.contains(e.getVehicleId())) entered.put(e.getVehicleId(), new double[]{e.getLinkId().index(), e.getTime()}); }
        void leave(LinkLeaveEvent e) {
            double[] s = entered.remove(e.getVehicleId());
            if (s == null || (int) s[0] != e.getLinkId().index()) return;
            double[] c = bins.computeIfAbsent(key((int) s[0], s[1]), k -> new double[2]);
            c[0]++; c[1] += Math.log1p(e.getTime() - s[1]);
        }
        static long key(int link, double time) { return (long) link * 1000 + (long) (time / BIN); }
        double get(int link, double time) { double[] c = bins.get(key(link, time)); return c == null ? Double.NaN : Math.expm1(c[1] / c[0]); }
    }

    public static final class SwitchingProvider implements com.google.inject.Provider<Mobsim> {
        @Inject Switch sw; @Inject QSimProvider qsim; @Inject Scenario scenario; @Inject EventsManager events; @Inject Gate gate;
        @Inject @com.google.inject.name.Named("car") TravelTimeCalculator calculator;
        @Override public Mobsim get() {
            return sw.isQSim() ? qsim.get() : new PSim(scenario, events, sw, calculator.getLinkTravelTimes(), gate.robust);
        }
    }

    /** Replays changed plans on frozen link times and emits the events the scoring, pricing and metrics handlers use. */
    static final class PSim implements Mobsim {
        private final Scenario scenario; private final EventsManager events; private final Switch sw;
        private final TravelTime times; private final RobustTimes robust; private final double endTime;
        PSim(Scenario scenario, EventsManager events, Switch sw, TravelTime times, RobustTimes robust) {
            this.scenario = scenario; this.events = events; this.sw = sw; this.times = times; this.robust = robust;
            this.endTime = scenario.getConfig().qsim().getEndTime().seconds();
        }
        @Override public void run() {
            long start = System.currentTimeMillis();
            List<List<Event>> perPlan = sw.toSimulate.parallelStream().map(this::replay).toList();
            events.initProcessing();
            for (List<Event> list : perPlan) for (Event e : list) events.processEvent(e);
            events.finishProcessing();
            sw.psimMillis = System.currentTimeMillis() - start;
        }
        private double linkTime(Link link, double t, boolean last) {
            double fallback = Math.max(1, times.getLinkTravelTime(link, t, null, null));
            if (robust == null) return fallback;
            if (last) return Math.max(1, link.getLength() / link.getFreespeed(t));
            double g = robust.get(link.getId().index(), t);
            return Double.isNaN(g) ? fallback : Math.max(1, g);
        }
        private List<Event> replay(Plan plan) {
            List<Event> out = new ArrayList<>();
            Person person = plan.getPerson(); Id<Person> pid = person.getId();
            var elements = plan.getPlanElements(); var links = scenario.getNetwork().getLinks();
            double t = 0;
            for (int i = 0; i < elements.size(); i += 2) {
                Activity act = (Activity) elements.get(i);
                if (i > 0) out.add(new ActivityStartEvent(t, pid, act.getLinkId(), act.getFacilityId(), act.getType(), act.getCoord()));
                if (i == elements.size() - 1) break;
                double end = act.getEndTime().isDefined() ? Math.max(t, act.getEndTime().seconds())
                        : t + act.getMaximumDuration().orElse(0);
                if (end > endTime) return out; // still performing the activity at the end: not stuck in QSim either
                t = end;
                Leg leg = (Leg) elements.get(i + 1);
                Activity next = (Activity) elements.get(i + 2);
                String mode = leg.getMode();
                out.add(new ActivityEndEvent(t, pid, act.getLinkId(), act.getFacilityId(), act.getType(), act.getCoord()));
                out.add(new PersonDepartureEvent(t, pid, act.getLinkId(), mode, TripStructureUtils.getRoutingMode(leg)));
                if (NETWORK_MODES.contains(mode) && leg.getRoute() instanceof org.matsim.core.population.routes.NetworkRoute route) {
                    Id<Vehicle> v = VehicleUtils.getVehicleId(person, mode);
                    out.add(new PersonEntersVehicleEvent(t, pid, v));
                    out.add(new VehicleEntersTrafficEvent(t, pid, route.getStartLinkId(), v, mode, 1.0));
                    if (!route.getStartLinkId().equals(route.getEndLinkId())) {
                        out.add(new LinkLeaveEvent(t, v, route.getStartLinkId()));
                        for (Id<Link> l : route.getLinkIds()) {
                            out.add(new LinkEnterEvent(t, v, l));
                            t += linkTime(links.get(l), t, false);
                            out.add(new LinkLeaveEvent(t, v, l));
                        }
                        out.add(new LinkEnterEvent(t, v, route.getEndLinkId()));
                        t += linkTime(links.get(route.getEndLinkId()), t, true);
                    }
                    if (t > endTime) { out.add(new PersonStuckEvent(endTime, pid, route.getEndLinkId(), mode)); return out; }
                    out.add(new VehicleLeavesTrafficEvent(t, pid, route.getEndLinkId(), v, mode, 1.0));
                    out.add(new PersonLeavesVehicleEvent(t, pid, v));
                } else {
                    Route route = leg.getRoute();
                    double travel = route != null && route.getTravelTime().isDefined() ? route.getTravelTime().seconds() : leg.getTravelTime().orElse(0);
                    t += Math.max(0, travel);
                    if (t > endTime) { out.add(new PersonStuckEvent(endTime, pid, next.getLinkId(), mode)); return out; }
                    if (route != null) out.add(new TeleportationArrivalEvent(t, pid, route.getDistance(), mode));
                }
                out.add(new PersonArrivalEvent(t, pid, next.getLinkId(), mode));
            }
            return out;
        }
    }
}

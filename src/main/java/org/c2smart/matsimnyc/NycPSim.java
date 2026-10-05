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
        install(controler, scenario, schedule, linkTime, null);
    }

    public static void install(Controler controler, Scenario scenario, String schedule, String linkTime, String model) {
        int cycle; double drift;
        if (schedule.startsWith("cycle:")) { cycle = Integer.parseInt(schedule.substring(6)); drift = Double.NaN; }
        else if (schedule.startsWith("drift:")) { cycle = Integer.MAX_VALUE; drift = Double.parseDouble(schedule.substring(6)); }
        else throw new IllegalArgumentException("nyc.psim must be cycle:K or drift:THETA");
        if (cycle < 1 || drift <= 0) throw new IllegalArgumentException("cycle K>=1, drift THETA>0");
        boolean geometric = "geometric".equals(linkTime);
        if (!geometric && !"mean".equals(linkTime)) throw new IllegalArgumentException("nyc.psim.linkTime must be mean or geometric");
        Correction correction = model == null ? null : Correction.load(Path.of(model));
        // The correction needs the robust link statistics for its features whichever base it uses.
        var config = scenario.getConfig();
        if (!config.travelTimeCalculator().getSeparateModes() || !NETWORK_MODES.containsAll(config.routing().getNetworkModes())
                || !config.travelTimeCalculator().getAnalyzedModes().containsAll(config.routing().getNetworkModes()))
            throw new IllegalArgumentException("NycPSim expects separate, analyzed travel times for routed network modes within car/taxi/FHV");
        Switch sw = new Switch(scenario, cycle, config.controller().getFirstIteration(), config.controller().getLastIteration(),
                Path.of(config.controller().getOutputDirectory()));
        sw.drift = drift;
        // Same construction as TravelTimeCalculatorModule.SingleModeTravelTimeCalculatorProvider (one per routed
        // network mode), but registered behind a gate instead of directly with the events manager.
        var tt = config.travelTimeCalculator();
        Map<String, TravelTimeCalculator> calculators = new TreeMap<>();
        for (String mode : config.routing().getNetworkModes()) {
            var builder = new TravelTimeCalculator.Builder(scenario.getNetwork());
            builder.setTimeslice(tt.getTraveltimeBinSize()); builder.setMaxTime(tt.getMaxTime());
            builder.setCalculateLinkTravelTimes(tt.isCalculateLinkTravelTimes());
            builder.setCalculateLinkToLinkTravelTimes(tt.isCalculateLinkToLinkTravelTimes());
            builder.setFilterModes(true); builder.setAnalyzedModes(Set.of(mode)); builder.configure(tt);
            calculators.put(mode, builder.build());
        }
        Gate gate = new Gate(calculators, sw, geometric || correction != null ? new RobustTimes() : null, correction);
        controler.addOverridingModule(new AbstractModule() {
            @Override public void install() {
                calculators.forEach((mode, c) -> bind(TravelTimeCalculator.class).annotatedWith(Names.named(mode)).toInstance(c));
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
        /** drift:THETA refresh rule: run QSim once the changed-plan shares of PSim iterations since the last QSim sum to THETA. */
        double drift = Double.NaN; double accumulated;
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
            qsim = i == first || i == last || (Double.isNaN(drift) ? (i - first) % cycle == 0 : accumulated >= drift);
            if (qsim) accumulated = 0;
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
            accumulated += toSimulate.size() / (double) scenario.getPopulation().getPersons().size();
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
        final Map<String, TravelTimeCalculator> calculators; final Collection<TravelTimeCalculator> all;
        final Switch sw; final RobustTimes robust; final Correction correction;
        Gate(Map<String, TravelTimeCalculator> calculators, Switch sw, RobustTimes robust, Correction correction) {
            this.calculators = calculators; this.all = calculators.values(); this.sw = sw; this.robust = robust; this.correction = correction;
        }
        @Override public void reset(int iteration) { if (sw.isQSim()) { for (var c : all) c.reset(iteration); if (robust != null) robust.reset(); } }
        @Override public void handleEvent(LinkEnterEvent e) { if (sw.isQSim()) { for (var c : all) c.handleEvent(e); if (robust != null) robust.enter(e); } }
        @Override public void handleEvent(LinkLeaveEvent e) { if (sw.isQSim()) { for (var c : all) c.handleEvent(e); if (robust != null) robust.leave(e); } }
        @Override public void handleEvent(VehicleEntersTrafficEvent e) { if (sw.isQSim()) { for (var c : all) c.handleEvent(e); if (robust != null) robust.traffic(e); } }
        @Override public void handleEvent(VehicleLeavesTrafficEvent e) { if (sw.isQSim()) { for (var c : all) c.handleEvent(e); if (robust != null) robust.untrack(e.getVehicleId()); } }
        @Override public void handleEvent(VehicleArrivesAtFacilityEvent e) { if (sw.isQSim()) for (var c : all) c.handleEvent(e); }
        @Override public void handleEvent(VehicleAbortsEvent e) { if (sw.isQSim()) { for (var c : all) c.handleEvent(e); if (robust != null) robust.untrack(e.getVehicleId()); } }
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
            double[] c = bins.computeIfAbsent(key((int) s[0], s[1]), k -> new double[3]);
            double d = e.getTime() - s[1];
            c[0]++; c[1] += Math.log1p(d); c[2] += d;
        }
        static long key(int link, double time) { return (long) link * 1000 + (long) (time / BIN); }
        double get(int link, double time) { double[] c = bins.get(key(link, time)); return c == null ? Double.NaN : Math.expm1(c[1] / c[0]); }
        double mean(int link, double time) { double[] c = bins.get(key(link, time)); return c == null ? Double.NaN : c[2] / c[0]; }
    }

    public static final class SwitchingProvider implements com.google.inject.Provider<Mobsim> {
        @Inject Switch sw; @Inject QSimProvider qsim; @Inject Scenario scenario; @Inject EventsManager events; @Inject Gate gate;
        @Override public Mobsim get() {
            if (sw.isQSim()) return qsim.get();
            Map<String, TravelTime> times = new HashMap<>();
            gate.calculators.forEach((mode, c) -> times.put(mode, c.getLinkTravelTimes()));
            return new PSim(scenario, events, sw, times, gate.robust, gate.correction);
        }
    }

    /** Replays changed plans on frozen link times and emits the events the scoring, pricing and metrics handlers use. */
    static final class PSim implements Mobsim {
        private final Scenario scenario; private final EventsManager events; private final Switch sw;
        private final Map<String, TravelTime> times; private final RobustTimes robust; private final Correction correction; private final double endTime;
        /** Single travel time for every network mode (tests). */
        PSim(Scenario scenario, EventsManager events, Switch sw, TravelTime times, RobustTimes robust) {
            this(scenario, events, sw, times == null ? Map.of() : Map.of("car", times, "taxi", times, "FHV", times), robust, null);
        }
        PSim(Scenario scenario, EventsManager events, Switch sw, Map<String, TravelTime> times, RobustTimes robust, Correction correction) {
            this.scenario = scenario; this.events = events; this.sw = sw; this.times = times; this.robust = robust; this.correction = correction;
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
        /** With a correction: the exact base used for its features (observed mean or geometric mean per 15-min bin,
         *  free flow when unobserved and on the end link), so factor * base total equals the predicted total. */
        private double baseTime(Link link, double t, boolean last) {
            double ff = Math.max(1, link.getLength() / link.getFreespeed(t));
            if (last) return ff;
            int i = link.getId().index();
            return Math.max(1, orElse(correction.base == 0 ? robust.mean(i, t) : robust.get(i, t), ff));
        }
        private double linkTime(String mode, Link link, double t, boolean last) {
            if (correction != null) return baseTime(link, t, last);
            TravelTime modeTimes = times.getOrDefault(mode, times.get("car"));
            double fallback = Math.max(1, modeTimes.getLinkTravelTime(link, t, null, null));
            if (robust == null) return fallback;
            if (last) return Math.max(1, link.getLength() / link.getFreespeed(t));
            double g = robust.get(link.getId().index(), t);
            return Double.isNaN(g) ? fallback : Math.max(1, g);
        }
        /** Same definitions as experiments/surrogate/agent_surrogate.py features(), columns 0-6. */
        double[] features(Plan plan) {
            var elements = plan.getPlanElements(); var links = scenario.getNetwork().getLinks();
            double t = 0, totMean = 0, totGeo = 0, totFf = 0, firstDep = Double.NaN; int legs = 0, nLinks = 0, congested = 0;
            for (int i = 0; i < elements.size(); i++) {
                if (elements.get(i) instanceof Activity act) {
                    t = act.getEndTime().isDefined() ? Math.max(t, act.getEndTime().seconds()) : t + act.getMaximumDuration().orElse(0);
                    continue;
                }
                Leg leg = (Leg) elements.get(i);
                if (NETWORK_MODES.contains(leg.getMode()) && leg.getRoute() instanceof org.matsim.core.population.routes.NetworkRoute route) {
                    legs++; if (Double.isNaN(firstDep)) firstDep = t;
                    double a = t, b = t;
                    List<Id<Link>> ids = new ArrayList<>();
                    if (!route.getStartLinkId().equals(route.getEndLinkId())) { ids.addAll(route.getLinkIds()); ids.add(route.getEndLinkId()); }
                    for (int k = 0; k < ids.size(); k++) {
                        Link link = links.get(ids.get(k)); boolean last = k == ids.size() - 1;
                        double ffB = Math.max(1, link.getLength() / link.getFreespeed(b));
                        double g = last ? ffB : orElse(robust.get(link.getId().index(), b), ffB);
                        double ffA = Math.max(1, link.getLength() / link.getFreespeed(a));
                        double m = last ? ffA : orElse(robust.mean(link.getId().index(), a), ffA);
                        a += Math.max(1, m); b += Math.max(1, g); totFf += ffB; nLinks++; if (g > 2 * ffB) congested++;
                    }
                    totMean += a - t; totGeo += b - t; t = b;
                } else {
                    Route route = leg.getRoute();
                    t += route != null && route.getTravelTime().isDefined() ? route.getTravelTime().seconds() : leg.getTravelTime().orElse(0);
                }
            }
            return new double[]{totMean, totGeo, totFf, legs, nLinks, Double.isNaN(firstDep) ? 0 : firstDep / 3600, congested / (double) Math.max(nLinks, 1)};
        }
        private static double orElse(double v, double fallback) { return Double.isNaN(v) ? fallback : v; }

        private List<Event> replay(Plan plan) {
            double factor = correction == null ? 1 : correction.factor(features(plan));
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
                            t += factor * linkTime(mode, links.get(l), t, false);
                            out.add(new LinkLeaveEvent(t, v, l));
                        }
                        out.add(new LinkEnterEvent(t, v, route.getEndLinkId()));
                        t += factor * linkTime(mode, links.get(route.getEndLinkId()), t, true);
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

    /** Gradient-boosted log-ratio correction exported by experiments/surrogate/export_model.py. */
    static final class Correction {
        final double baseline; final List<double[][]> trees; final int base;   // base feature column: 0 = mean, 1 = geometric
        Correction(double baseline, List<double[][]> trees, int base) { this.baseline = baseline; this.trees = trees; this.base = base; }
        static Correction load(Path path) {
            try {
                var lines = Files.readAllLines(path); int start = 0, base = 1;
                if (lines.get(0).startsWith("base ")) { base = Integer.parseInt(lines.get(0).substring(5).trim()); start = 1; }
                double baseline = Double.parseDouble(lines.get(start).trim());
                List<double[][]> trees = new ArrayList<>();
                for (int i = start + 1; i < lines.size(); ) {
                    int n = Integer.parseInt(lines.get(i).split(" ")[1]); double[][] nodes = new double[n][];
                    for (int k = 0; k < n; k++) nodes[k] = Arrays.stream(lines.get(i + 1 + k).trim().split(" ")).mapToDouble(Double::parseDouble).toArray();
                    trees.add(nodes); i += n + 1;
                }
                return new Correction(baseline, trees, base);
            } catch (IOException e) { throw new UncheckedIOException(e); }
        }
        /** Raw prediction: baseline plus the leaf value of every tree (feature, threshold, left, right, leaf, value, missingLeft). */
        double predict(double[] x) {
            double sum = baseline;
            for (double[][] nodes : trees) {
                int k = 0;
                while (nodes[k][4] == 0) {
                    double v = x[(int) nodes[k][0]];
                    boolean left = Double.isNaN(v) ? nodes[k][6] == 1 : v <= nodes[k][1];
                    k = (int) (left ? nodes[k][2] : nodes[k][3]);
                }
                sum += nodes[k][5];
            }
            return sum;
        }
        /** Multiplier for the plan's base link times so its total matches the predicted total (clamped to [0.05, 20]). */
        double factor(double[] x) {
            double b = x[base];
            if (!(b > 0)) return 1;
            double predicted = Math.expm1(predict(x) + Math.log1p(b));
            return Math.max(0.05, Math.min(20, predicted / b));
        }
    }
}

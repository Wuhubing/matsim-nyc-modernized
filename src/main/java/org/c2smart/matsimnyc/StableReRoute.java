package org.c2smart.matsimnyc;

import com.google.inject.Inject;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.TransportMode;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.config.groups.GlobalConfigGroup;
import org.matsim.core.config.groups.ScoringConfigGroup;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.controler.events.IterationEndsEvent;
import org.matsim.core.controler.listener.IterationEndsListener;
import org.matsim.core.population.routes.NetworkRoute;
import org.matsim.core.replanning.PlanStrategy;
import org.matsim.core.replanning.PlanStrategyImpl;
import org.matsim.core.replanning.ReplanningContext;
import org.matsim.core.replanning.selectors.ExpBetaPlanSelector;
import org.matsim.core.replanning.selectors.PlanSelector;
import org.matsim.core.router.TripRouter;
import org.matsim.core.router.TripStructureUtils;
import org.matsim.core.router.util.TravelTime;
import org.matsim.core.utils.timing.TimeInterpretation;
import org.matsim.facilities.ActivityFacilities;
import org.matsim.pt.routes.TransitPassengerRoute;
import org.matsim.vehicles.Vehicle;

import java.io.*;
import java.nio.file.*;
import java.util.*;

/** M8: MATSim's ReRoute strategy (random plan, copy, re-route every trip) that first asks whether the routes of the
 * picked plan would very likely come back unchanged, and if so lets the agent select among its plans instead.
 *
 * Change of a plan = largest relative difference, over its network legs, between the travel time stored in the
 * route (what the router estimated when it made the route) and the same route re-estimated on the current travel
 * times, computed exactly as NetworkRoutingInclAccessEgressModule and SpeedyALT do: from the leg's departure, add the
 * link travel time at the time each route link is entered (start and end link excluded), add the end link at
 * min(vehicle maximum, free speed), truncate to whole seconds. Unchanged travel times therefore give exactly 0.
 * Teleported legs (walk, bike, ride, access/egress) are deterministic and ignored. Plans with a pt leg cannot be
 * judged this way and are always re-routed (change = NaN).
 *
 * threshold < 0 (shadow mode): never skips, so the run is identical to ReRoute (same plan pick and RNG draws, same
 * plan mutator "RandomPlanSelector_ReRoute"); it records how often the re-routed plan came back identical, by bin of
 * change. threshold >= 0: plans with change <= threshold are not re-routed, the agent selects with ExpBeta (as
 * SelectExpBeta). Per iteration OUTPUT/stable-reroute.csv; it also checks the estimator: right after routing, the
 * new routes re-estimated on the same travel times must equal their stored travel time ('estimate_mismatch').
 * Plans with an unscored plan in memory are passed to ReRoute unchanged, as MATSim would pick the unscored plan.
 * run() is called sequentially (GenericStrategyManagerImpl.run, MATSim 2026.0). */
public final class StableReRoute implements PlanStrategy {
    public static final String NAME = "StableReRoute";
    static final double[] BINS = {0, 0.005, 0.01, 0.02, 0.05, 0.10, Double.POSITIVE_INFINITY};   // bin 0 = exactly 0

    /** Hands the plan picked by run() to MATSim's strategy; named like MATSim's selector so plan mutators keep reading
     * RandomPlanSelector_ReRoute. */
    static final class RandomPlanSelector implements PlanSelector<Plan, Person> {
        private final org.matsim.core.replanning.selectors.RandomPlanSelector<Plan, Person> random = new org.matsim.core.replanning.selectors.RandomPlanSelector<>();
        Plan next;
        @Override public Plan selectPlan(HasPlansAndId<Plan, Person> person) { Plan p = next; next = null; return p != null ? p : random.selectPlan(person); }
    }

    /** Counters shared by the strategy instances (one per subpopulation); one CSV row per iteration. */
    public static final class Stats implements IterationEndsListener {
        private final Path file;
        long handled, unscored, notJudged, skipped, routed, duplicates, estimateChecked, estimateMismatch;
        final long[] skippedBy = new long[BINS.length], routedBy = new long[BINS.length], duplicateBy = new long[BINS.length];

        @Inject Stats(OutputDirectoryHierarchy out) { this(Path.of(out.getOutputFilename("stable-reroute.csv"))); }
        Stats(Path file) { this.file = file; }
        Path file() { return file; }

        static int bin(double change) {
            if (change == 0) return 0;
            for (int b = 1; b < BINS.length; b++) if (change <= BINS[b]) return b;
            return BINS.length - 1;
        }

        @Override public void notifyIterationEnds(IterationEndsEvent event) { write(event.getIteration()); }

        void write(int iteration) {
            try {
                boolean header = !Files.exists(file) || Files.size(file) == 0;
                try (Writer w = Files.newBufferedWriter(file, StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
                    if (header) {
                        w.write("iteration,handled,unscored,not_judged,skipped,routed,duplicates,estimate_checked,estimate_mismatch");
                        for (String k : List.of("skipped", "routed", "duplicates")) for (int b = 0; b < BINS.length; b++) w.write("," + k + "_" + label(b));
                        w.write("\n");
                    }
                    w.write(iteration + "," + handled + "," + unscored + "," + notJudged + "," + skipped + "," + routed + "," + duplicates + "," + estimateChecked + "," + estimateMismatch);
                    for (long[] a : List.of(skippedBy, routedBy, duplicateBy)) for (long x : a) w.write("," + x);
                    w.write("\n");
                }
            } catch (IOException e) { throw new UncheckedIOException(e); }
            handled = unscored = notJudged = skipped = routed = duplicates = estimateChecked = estimateMismatch = 0;
            Arrays.fill(skippedBy, 0); Arrays.fill(routedBy, 0); Arrays.fill(duplicateBy, 0);
        }

        static String label(int b) { return b == 0 ? "eq0" : "le" + (Double.isInfinite(BINS[b]) ? "inf" : BINS[b]); }
    }

    public static final class Provider implements com.google.inject.Provider<PlanStrategy> {
        @Inject private GlobalConfigGroup globalConfigGroup;
        @Inject private ActivityFacilities facilities;
        @Inject private com.google.inject.Provider<TripRouter> tripRouterProvider;
        @Inject private TimeInterpretation timeInterpretation;
        @Inject private ScoringConfigGroup scoring;
        @Inject private Map<String, TravelTime> travelTimes;
        @Inject private Scenario scenario;
        @Inject private Stats stats;

        @Override public PlanStrategy get() {
            double threshold = Double.parseDouble(System.getProperty("nyc.stableReRoute.threshold", "-1"));
            RandomPlanSelector pick = new RandomPlanSelector();
            PlanStrategy reroute = new PlanStrategyImpl.Builder(pick)
                    .addStrategyModule(new org.matsim.core.replanning.modules.ReRoute(facilities, tripRouterProvider, globalConfigGroup, timeInterpretation)).build();
            return new StableReRoute(reroute, pick, new ExpBetaPlanSelector<>(scoring), travelTimes, scenario, stats, threshold);
        }
    }

    private record Pending(Plan parent, Plan copy, double change) {}

    private final PlanStrategy reroute;
    private final RandomPlanSelector pick;
    private final org.matsim.core.replanning.selectors.RandomPlanSelector<Plan, Person> random = new org.matsim.core.replanning.selectors.RandomPlanSelector<>();
    private final PlanSelector<Plan, Person> fallback;
    private final Map<String, TravelTime> travelTimes;
    private final Network network;
    private final Scenario scenario;
    private final Stats stats;
    private final double threshold;
    private final List<Pending> pending = new ArrayList<>();

    StableReRoute(PlanStrategy reroute, RandomPlanSelector pick, PlanSelector<Plan, Person> fallback, Map<String, TravelTime> travelTimes,
                  Scenario scenario, Stats stats, double threshold) {
        this.reroute = reroute; this.pick = pick; this.fallback = fallback; this.travelTimes = travelTimes;
        this.scenario = scenario; this.network = scenario.getNetwork(); this.stats = stats; this.threshold = threshold;
    }

    @Override public void init(ReplanningContext context) { reroute.init(context); }

    @Override public void run(HasPlansAndId<Plan, Person> person) {
        stats.handled++;
        if (person.getPlans().stream().anyMatch(p -> p.getScore() == null)) { stats.unscored++; reroute.run(person); return; }
        Plan parent = random.selectPlan(person);                 // the same draw as MATSim's RandomPlanSelector
        if (parent == null) { reroute.run(person); return; }
        double change = change(parent);
        if (Double.isNaN(change)) stats.notJudged++;
        else if (threshold >= 0 && change <= threshold) {
            stats.skipped++; stats.skippedBy[Stats.bin(change)]++;
            Plan s = fallback.selectPlan(person);
            if (s != null) person.setSelectedPlan(s);
            return;
        }
        pick.next = parent; reroute.run(person);
        pending.add(new Pending(parent, person.getSelectedPlan(), change));
    }

    @Override public void finish() {
        reroute.finish();                                         // ReRoute routes the copies here
        for (Pending x : pending) {
            boolean dup = samePlan(x.parent, x.copy);
            stats.routed++; if (dup) stats.duplicates++;
            if (!Double.isNaN(x.change)) { int b = Stats.bin(x.change); stats.routedBy[b]++; if (dup) stats.duplicateBy[b]++; }
            double self = change(x.copy);
            if (!Double.isNaN(self)) { stats.estimateChecked++; if (self != 0) stats.estimateMismatch++; }
        }
        pending.clear();
    }

    /** Largest relative change of a network leg's travel time since routing; NaN if the plan cannot be judged. */
    double change(Plan plan) {
        double worst = 0;
        for (Leg leg : TripStructureUtils.getLegs(plan)) {
            Route r = leg.getRoute();
            if (r instanceof TransitPassengerRoute || TransportMode.pt.equals(leg.getMode())) return Double.NaN;
            if (!(r instanceof NetworkRoute nr)) continue;
            if (nr.getStartLinkId().equals(nr.getEndLinkId())) continue;   // stays on its link whatever the travel times
            TravelTime tt = travelTimes.get(leg.getMode());
            Vehicle v = nr.getVehicleId() == null ? null : scenario.getVehicles().getVehicles().get(nr.getVehicleId());
            if (tt == null || v == null || nr.getTravelTime().isUndefined() || leg.getDepartureTime().isUndefined()) return Double.NaN;
            double old = nr.getTravelTime().seconds(), now = estimate(nr, leg.getDepartureTime().seconds(), plan.getPerson(), v, tt, network);
            worst = Math.max(worst, Math.abs(now - old) / Math.max(old, 1));
        }
        return worst;
    }

    static double estimate(NetworkRoute r, double departure, Person person, Vehicle v, TravelTime tt, Network network) {
        double t = departure;
        for (Id<Link> id : r.getLinkIds()) t += tt.getLinkTravelTime(network.getLinks().get(id), t, person, v);
        Link to = network.getLinks().get(r.getEndLinkId());
        return (int) ((t - departure) + to.getLength() / Math.min(v.getType().getMaximumVelocity(), to.getFreespeed()));
    }

    /** Same legs (mode, start and end link, route description) in the same order. */
    static boolean samePlan(Plan a, Plan b) {
        List<Leg> x = TripStructureUtils.getLegs(a), y = TripStructureUtils.getLegs(b);
        if (x.size() != y.size()) return false;
        for (int i = 0; i < x.size(); i++) {
            Leg p = x.get(i), q = y.get(i);
            if (!Objects.equals(p.getMode(), q.getMode())) return false;
            Route r = p.getRoute(), s = q.getRoute();
            if (r == null || s == null) { if (r != s) return false; continue; }
            if (!r.getStartLinkId().equals(s.getStartLinkId()) || !r.getEndLinkId().equals(s.getEndLinkId())
                    || !Objects.equals(r.getRouteDescription(), s.getRouteDescription())) return false;
        }
        return true;
    }

    @Override public String toString() { return "RandomPlanSelector_ReRoute_" + NAME; }
}

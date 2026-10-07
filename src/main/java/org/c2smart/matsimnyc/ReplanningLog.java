package org.c2smart.matsimnyc;

import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.controler.events.BeforeMobsimEvent;
import org.matsim.core.controler.events.IterationEndsEvent;
import org.matsim.core.controler.events.StartupEvent;
import org.matsim.core.controler.listener.BeforeMobsimListener;
import org.matsim.core.controler.listener.IterationEndsListener;
import org.matsim.core.controler.listener.StartupListener;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.population.routes.NetworkRoute;
import org.matsim.core.replanning.inheritance.PlanInheritanceModule;
import org.matsim.core.router.TripStructureUtils;
import org.matsim.pt.routes.TransitPassengerRoute;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.GZIPOutputStream;

/** W1: compact per-iteration replanning log under OUTPUT/replanning-log/.
 *
 * persons.csv.gz (once): person index, person id, subpopulation.
 * strategies.csv (at the end of each iteration, cumulative): strategy code, innovative, MATSim description.
 * agents-IT.csv.gz: per person, the strategy chosen in this iteration's replanning (-1 in iteration 0), the
 *   selected plan's id, iterationCreated and executed score (after this iteration's scoring), the best stored
 *   score and the number of stored plans; for a plan created in this iteration also the id of the plan it was
 *   copied from.
 * trips-IT.csv.gz: per trip of a plan created in this iteration, compared with the same trip of its parent plan:
 *   whether the mode chain or the route changed (road: link sequence; transit: line, route, access and egress
 *   stop; other: start and end link) and the router-estimated travel time stored on the legs before and after.
 *   The "before" value is the estimate stored when the parent was routed, not a re-evaluation under current
 *   travel times; a trip count mismatch is written as trip -1.
 *
 * Plan ids come from MATSim's plan inheritance (RunNyc enables it with the log). A new plan is a copy of its
 * parent including the plan-id attribute until PlanInheritanceModule assigns a new id in its BeforeMobsim
 * listener (priority 0); this listener runs first (priority 1) to read the parent. Nothing here changes plans,
 * scores or random draws. */
public final class ReplanningLog implements StartupListener, BeforeMobsimListener, IterationEndsListener {
    private final Population population;
    private final RecordingStrategyChooser chooser;
    private final Path directory;
    private final Map<Id<Person>, Id<Plan>> parents = new HashMap<>();
    private int iteration = -1;

    public ReplanningLog(Population population, RecordingStrategyChooser chooser, String outputDirectory) {
        this.population = population; this.chooser = chooser;
        this.directory = Path.of(outputDirectory, "replanning-log");
    }

    @Override public double priority() { return 1; }

    @Override public void notifyStartup(StartupEvent event) {
        try {
            Files.createDirectories(directory);
            try (Writer w = gzip(directory.resolve("persons.csv.gz"))) {
                w.write("person,person_id,subpopulation\n");
                for (Person p : population.getPersons().values())
                    w.write(p.getId().index() + "," + p.getId() + "," + Objects.toString(PopulationUtils.getSubpopulation(p), "") + "\n");
            }
        } catch (IOException e) { throw new UncheckedIOException(e); }
    }

    @Override public void notifyBeforeMobsim(BeforeMobsimEvent event) {
        iteration = event.getIteration();
        parents.clear();
        try (Writer w = gzip(directory.resolve("trips-" + iteration + ".csv.gz"))) {
            w.write("person,trip,mode_changed,route_changed,est_tt_before,est_tt_after\n");
            for (Person p : population.getPersons().values()) {
                Plan plan = p.getSelectedPlan();
                if (plan == null || created(plan) != iteration || plan.getId() == null) continue;
                Plan parent = null;
                for (Plan q : p.getPlans()) if (q != plan && plan.getId().equals(q.getId())) { parent = q; break; }
                if (parent == null) continue;
                parents.put(p.getId(), parent.getId());
                List<TripStructureUtils.Trip> after = TripStructureUtils.getTrips(plan), before = TripStructureUtils.getTrips(parent);
                int person = p.getId().index();
                if (after.size() != before.size()) { w.write(person + ",-1,1,1,,\n"); continue; }
                for (int t = 0; t < after.size(); t++) {
                    List<Leg> a = after.get(t).getLegsOnly(), b = before.get(t).getLegsOnly();
                    boolean modeChanged = !modes(a).equals(modes(b));
                    boolean routeChanged = modeChanged || !routes(a).equals(routes(b));
                    w.write(person + "," + t + "," + (modeChanged ? 1 : 0) + "," + (routeChanged ? 1 : 0) + "," + time(b) + "," + time(a) + "\n");
                }
            }
        } catch (IOException e) { throw new UncheckedIOException(e); }
    }

    @Override public void notifyIterationEnds(IterationEndsEvent event) {
        int it = event.getIteration();
        try (Writer w = gzip(directory.resolve("agents-" + it + ".csv.gz"))) {
            w.write("person,strategy,plan_id,plan_created,parent_plan_id,executed_score,best_score,plans\n");
            boolean replanned = chooser.iteration() == it;
            for (Person p : population.getPersons().values()) {
                Plan plan = p.getSelectedPlan();
                double best = Double.NEGATIVE_INFINITY;
                for (Plan q : p.getPlans()) if (q.getScore() != null) best = Math.max(best, q.getScore());
                Id<Plan> parent = parents.get(p.getId());
                w.write(p.getId().index() + "," + (replanned ? chooser.strategy(p.getId()) : RecordingStrategyChooser.NONE) + ","
                        + plan.getId() + "," + created(plan) + "," + (parent == null ? "" : parent) + ","
                        + num(plan.getScore()) + "," + (best == Double.NEGATIVE_INFINITY ? "" : num(best)) + "," + p.getPlans().size() + "\n");
            }
        } catch (IOException e) { throw new UncheckedIOException(e); }
        try (Writer w = Files.newBufferedWriter(directory.resolve("strategies.csv"))) {
            w.write("strategy,innovative,description\n");
            List<String> names = chooser.names();
            for (short i = 0; i < names.size(); i++) w.write(i + "," + (chooser.innovative(i) ? 1 : 0) + ",\"" + names.get(i).replace("\"", "\"\"") + "\"\n");
        } catch (IOException e) { throw new UncheckedIOException(e); }
    }

    /** iterationCreated without the NullPointerException PlanImpl throws for plans that never had it set. */
    static int created(Plan plan) {
        Object v = plan.getAttributes().getAttribute(PlanInheritanceModule.ITERATION_CREATED);
        return v == null ? -1 : (int) v;
    }
    private static String num(Double v) { return v == null ? "" : Double.toString(v); }
    private static List<String> modes(List<Leg> legs) { List<String> m = new ArrayList<>(); for (Leg l : legs) m.add(l.getMode()); return m; }
    private static List<Object> routes(List<Leg> legs) {
        List<Object> r = new ArrayList<>();
        for (Leg l : legs) {
            Route route = l.getRoute();
            if (route instanceof NetworkRoute n) r.add(Arrays.asList(n.getStartLinkId(), n.getLinkIds(), n.getEndLinkId()));
            else if (route instanceof TransitPassengerRoute t) r.add(Arrays.asList(t.getLineId(), t.getRouteId(), t.getAccessStopId(), t.getEgressStopId()));
            else if (route != null) r.add(Arrays.asList(route.getStartLinkId(), route.getEndLinkId()));
            else r.add("none");
        }
        return r;
    }
    private static String time(List<Leg> legs) {
        double s = 0;
        for (Leg l : legs) { if (l.getTravelTime().isUndefined()) return ""; s += l.getTravelTime().seconds(); }
        return Double.toString(s);
    }
    private static Writer gzip(Path file) throws IOException {
        return new BufferedWriter(new OutputStreamWriter(new GZIPOutputStream(Files.newOutputStream(file), 1 << 16)), 1 << 16);
    }
}

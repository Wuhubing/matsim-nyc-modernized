package org.c2smart.matsimnyc;

import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.events.*;
import org.matsim.api.core.v01.events.handler.*;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.Person;
import org.matsim.core.api.experimental.events.handler.*;
import org.matsim.core.api.experimental.events.*;
import org.matsim.core.controler.events.IterationEndsEvent;
import org.matsim.core.controler.listener.IterationEndsListener;
import org.matsim.vehicles.Vehicle;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.*;
import java.util.*;

/** Online equivalent of experiments/acceleration/event_metrics.py::measure, so full event XML
 * need not be written every iteration. Same event order and summation order as the offline scan. */
public final class IterationMetrics implements PersonDepartureEventHandler, PersonArrivalEventHandler,
        PersonStuckEventHandler, AgentWaitingForPtEventHandler, PersonEntersVehicleEventHandler,
        VehicleEntersTrafficEventHandler, VehicleLeavesTrafficEventHandler, LinkEnterEventHandler,
        PersonMoneyEventHandler, IterationEndsListener {
    private static final double CUTOFF = 108000;
    private final Scenario scenario;
    private final Path directory;
    private final boolean[] entry;
    private final Map<Id<Person>, Object[]> active = new LinkedHashMap<>();
    private final Map<Id<Person>, Double> waiting = new LinkedHashMap<>();
    private final Map<Id<Vehicle>, Id<Person>> drivers = new HashMap<>();
    private final Map<String, Long> departures = new TreeMap<>(), completed = new TreeMap<>(), stuck = new TreeMap<>(), errors = new TreeMap<>();
    private final Map<String, Double> durations = new HashMap<>();
    private final Map<Integer, Long> crossings = new TreeMap<>();
    private double waitSeconds, netRevenue;
    private long waitCount;

    public IterationMetrics(Scenario scenario, String pricingLinks, String outputDirectory) {
        this.scenario = scenario;
        this.directory = Path.of(outputDirectory);
        int size = Id.getNumberOfIds(Link.class);
        entry = new boolean[size];
        try {
            var rows = Files.readAllLines(Path.of(pricingLinks));
            for (String row : rows.subList(1, rows.size())) {
                String[] v = row.split(",");
                if (v[1].equals("1")) entry[Id.createLinkId(v[0]).index()] = true;
            }
        } catch (IOException e) { throw new UncheckedIOException(e); }
    }

    private boolean person(Id<Person> id) { return id != null && scenario.getPopulation().getPersons().containsKey(id); }
    private static <K> void add(Map<K, Long> m, K k) { m.merge(k, 1L, Long::sum); }

    @Override public void reset(int iteration) {
        active.clear(); waiting.clear(); drivers.clear(); departures.clear(); completed.clear(); stuck.clear(); errors.clear();
        durations.clear(); crossings.clear(); waitSeconds = 0; netRevenue = 0; waitCount = 0;
    }
    @Override public void handleEvent(VehicleEntersTrafficEvent e) {
        if (person(e.getPersonId()) && "car".equals(e.getNetworkMode())) drivers.put(e.getVehicleId(), e.getPersonId());
    }
    @Override public void handleEvent(VehicleLeavesTrafficEvent e) { drivers.remove(e.getVehicleId()); }
    @Override public void handleEvent(LinkEnterEvent e) {
        int i = e.getLinkId().index();
        if (i < entry.length && entry[i] && drivers.containsKey(e.getVehicleId())) crossings.merge((int) Math.floor(e.getTime() / 3600), 1L, Long::sum);
    }
    @Override public void handleEvent(PersonDepartureEvent e) {
        if (!person(e.getPersonId())) return;
        if (active.containsKey(e.getPersonId())) add(errors, "overlapping_departures");
        active.put(e.getPersonId(), new Object[]{e.getTime(), e.getLegMode()});
        add(departures, e.getLegMode());
    }
    @Override public void handleEvent(PersonArrivalEvent e) {
        if (!person(e.getPersonId())) return;
        Object[] a = active.remove(e.getPersonId());
        if (a == null) { add(errors, "unmatched_arrivals"); return; }
        String mode = (String) a[1];
        if (!mode.equals(e.getLegMode())) add(errors, "arrival_mode_mismatch");
        add(completed, mode);
        durations.merge(mode, e.getTime() - (double) a[0], Double::sum);
    }
    @Override public void handleEvent(AgentWaitingForPtEvent e) {
        if (!person(e.getPersonId())) return;
        if (waiting.containsKey(e.getPersonId())) add(errors, "overlapping_waits");
        waiting.put(e.getPersonId(), e.getTime()); waitCount++;
    }
    @Override public void handleEvent(PersonEntersVehicleEvent e) {
        if (!(e instanceof org.matsim.core.mobsim.qsim.pt.PersonEntersPtVehicleEvent) || !person(e.getPersonId())) return;
        Double start = waiting.remove(e.getPersonId());
        if (start == null) add(errors, "boarding_without_wait"); else waitSeconds += e.getTime() - start;
    }
    @Override public void handleEvent(PersonStuckEvent e) {
        if (person(e.getPersonId())) add(stuck, e.getLegMode());
    }
    @Override public void handleEvent(PersonMoneyEvent e) {
        if (person(e.getPersonId()) && "toll".equals(e.getPurpose())) netRevenue -= e.getAmount();
    }
    @Override public void notifyIterationEnds(IterationEndsEvent event) {
        Map<String, Long> unfinished = new TreeMap<>();
        for (Object[] a : active.values()) add(unfinished, (String) a[1]);
        double censored = waitSeconds;
        for (double t : waiting.values()) censored += Math.max(0, CUTOFF - t);
        if (!unfinished.equals(stuck)) add(errors, "stuck_active_mismatch");
        for (var p : waiting.keySet()) { Object[] a = active.get(p); if (a == null || !"pt".equals(a[1])) { add(errors, "waiting_not_active_pt"); break; } }
        for (var k : departures.keySet()) if (departures.get(k) != completed.getOrDefault(k, 0L) + unfinished.getOrDefault(k, 0L)) { add(errors, "leg_conservation"); break; }
        long carDone = completed.getOrDefault("car", 0L);
        long entries = crossings.values().stream().mapToLong(Long::longValue).sum();
        String json = "{\"iteration\":" + event.getIteration()
                + ",\"departures\":" + obj(departures) + ",\"completed\":" + obj(completed) + ",\"unfinished\":" + obj(unfinished)
                + ",\"unfinished_all\":" + active.size()
                + ",\"mean_completed_car_leg_seconds\":" + (carDone > 0 ? Double.toString(durations.get("car") / carDone) : "null")
                + ",\"censored_wait_person_hours\":" + (censored / 3600) + ",\"waiting_segments_started\":" + waitCount
                + ",\"waiting_at_cutoff\":" + waiting.size() + ",\"private_car_entry_crossings\":" + entries
                + ",\"private_car_entries_by_hour\":" + obj(crossings) + ",\"net_congestion_revenue\":" + netRevenue
                + ",\"errors\":" + obj(errors) + "}\n";
        try {
            Files.writeString(directory.resolve("iteration-metrics-" + event.getIteration() + ".json"), json);
        } catch (IOException e) { throw new UncheckedIOException(e); }
    }
    private static String obj(Map<?, Long> m) {
        var b = new StringJoiner(",", "{", "}");
        m.forEach((k, v) -> b.add("\"" + k + "\":" + v));
        return b.toString();
    }
}

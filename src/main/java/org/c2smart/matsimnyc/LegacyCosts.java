package org.c2smart.matsimnyc;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.events.*;
import org.matsim.api.core.v01.events.handler.*;
import org.matsim.api.core.v01.population.Person;
import org.matsim.core.api.experimental.events.EventsManager;
import org.matsim.vehicles.Vehicle;

/** Restores NewScoring.java's fixed utility charges, separately from cordon money events.
 * Uses traffic-entry driver mapping (the archive erroneously populated it on exit).
 * Rates are historical model inputs, not today's fares/tolls.
 */
public final class LegacyCosts implements PersonArrivalEventHandler, LinkLeaveEventHandler,
        VehicleEntersTrafficEventHandler, VehicleLeavesTrafficEventHandler {
    static final double MONEY_UTILITY = 0.0616752;
    static final Set<String> PANYNJ = Set.of("320888283_0", "60325668_0", "415882710_0",
            "232473896_0", "49032026_0", "644974431_0", "360639917_1");
    static final Set<String> MTA = Set.of("40596823_0", "25154607_0", "40595084_0",
            "375623292_0", "25464382_0", "5669174_0", "90086370_0", "5699313_0",
            "413749473_0", "5681925_0", "11878036_0", "46469739_0");
    private final EventsManager events;
    private final Scenario scenario;
    private final boolean zipAligned;
    private final Map<Id<Vehicle>, Id<Person>> drivers = new HashMap<>();

    @com.google.inject.Inject
    public LegacyCosts(EventsManager events, Scenario scenario) {
        this.events = events; this.scenario = scenario;
        this.zipAligned=org.matsim.core.config.ConfigUtils.addOrGetModule(scenario.getConfig(),NycModelConfig.class).getZipAligned();
    }

    public static void validate(Scenario scenario) {
        for (Set<String> ids : java.util.List.of(PANYNJ, MTA))
            for (String id : ids) {
                var link = scenario.getNetwork().getLinks().get(Id.createLinkId(id));
                if (link == null || !link.getAllowedModes().contains("car"))
                    throw new IllegalArgumentException("Historical toll link missing/not a road: " + id);
            }
    }

    static double fixedCost(String mode) {
        return switch (mode) { case "car" -> 5.19; case "taxi" -> 5.80; case "FHV" -> 5.25; default -> 0; };
    }
    static double toll(String link, double time) {
        if (MTA.contains(link)) return 6.12;
        if (!PANYNJ.contains(link)) return 0;
        double hour = (time % 86400) / 3600;
        return (hour >= 6 && hour < 10 || hour >= 16 && hour < 20) ? 12.50 : 10.50;
    }
    private void charge(double time, Id<Person> person, double dollars, String kind) {
        if (dollars > 0 && person != null)
            events.processEvent(new PersonScoreEvent(time, person, -dollars * MONEY_UTILITY, kind));
    }
    @Override public void handleEvent(PersonArrivalEvent e) {
        if (!scenario.getPopulation().getPersons().containsKey(e.getPersonId())) return;
        charge(e.getTime(), e.getPersonId(), fixedCost(e.getLegMode()), "nyc-legacy-" + e.getLegMode());
    }
    @Override public void handleEvent(VehicleEntersTrafficEvent e) {
        if (Set.of("car", "taxi", "FHV").contains(e.getNetworkMode())
                && scenario.getPopulation().getPersons().containsKey(e.getPersonId()))
            drivers.put(e.getVehicleId(), e.getPersonId());
    }
    @Override public void handleEvent(VehicleLeavesTrafficEvent e) { drivers.remove(e.getVehicleId()); }
    @Override public void handleEvent(LinkLeaveEvent e) {
        // Archived NewScoring keeps all times >=20:00 off-peak, including after midnight.
        double tariffTime=zipAligned && e.getTime()>=86400?0:e.getTime();
        charge(e.getTime(), drivers.get(e.getVehicleId()), toll(e.getLinkId().toString(), tariffTime), "nyc-legacy-facility-toll");
    }
    @Override public void reset(int iteration) { drivers.clear(); }
}

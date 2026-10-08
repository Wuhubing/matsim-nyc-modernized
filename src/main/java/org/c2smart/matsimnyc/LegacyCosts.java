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
    private static final Set<String> NETWORK_MODES = Set.of("car", "taxi", "FHV");
    // Facility class by Id.index(): 0 none, 1 MTA, 2 PANYNJ. MTA wins, matching toll(String,double).
    private final byte[] facility;

    @com.google.inject.Inject
    public LegacyCosts(EventsManager events, Scenario scenario) {
        this.events = events; this.scenario = scenario;
        this.zipAligned=org.matsim.core.config.ConfigUtils.addOrGetModule(scenario.getConfig(),NycModelConfig.class).getZipAligned();
        int size=0;
        for (Set<String> ids : java.util.List.of(PANYNJ, MTA)) for (String id : ids) size=Math.max(size,Id.createLinkId(id).index()+1);
        facility=new byte[size];
        for (String id : PANYNJ) facility[Id.createLinkId(id).index()]=2;
        for (String id : MTA) facility[Id.createLinkId(id).index()]=1;
    }

    public static void validate(Scenario scenario) {
        for (Set<String> ids : java.util.List.of(PANYNJ, MTA))
            for (String id : ids) {
                var link = scenario.getNetwork().getLinks().get(Id.createLinkId(id));
                if (link == null || !link.getAllowedModes().contains("car"))
                    throw new IllegalArgumentException("Historical toll link missing/not a road: " + id);
            }
    }

    /** Diagnostic option (-Dnyc.legacyTollRouting=true), off by default: the archived model, like this port, charges
     * facility tolls only in scoring, so car routing treats tolled bridges and tunnels as free. This adds the same
     * tolls, in the same utility units, to the car travel disutility. It replaces the car disutility binding, so
     * it must not be combined with another toll-aware router (RunNyc checks this). */
    public static org.matsim.core.controler.AbstractModule tollAwareRouting(Scenario scenario) {
        boolean zipAligned = org.matsim.core.config.ConfigUtils.addOrGetModule(scenario.getConfig(), NycModelConfig.class).getZipAligned();
        return new org.matsim.core.controler.AbstractModule() {
            @Override public void install() {
                var base = new org.matsim.core.router.costcalculators.RandomizingTimeDistanceTravelDisutilityFactory("car", scenario.getConfig());
                addTravelDisutilityFactoryBinding("car").toInstance(tt -> {
                    var d = base.createTravelDisutility(tt);
                    return new org.matsim.core.router.util.TravelDisutility() {
                        public double getLinkTravelDisutility(org.matsim.api.core.v01.network.Link l, double time, Person p, Vehicle v) {
                            double tariffTime = zipAligned && time >= 86400 ? 0 : time;
                            return d.getLinkTravelDisutility(l, time, p, v) + toll(l.getId().toString(), tariffTime) * MONEY_UTILITY;
                        }
                        public double getLinkMinimumTravelDisutility(org.matsim.api.core.v01.network.Link l) { return d.getLinkMinimumTravelDisutility(l); }
                    };
                });
            }
        };
    }

    static double fixedCost(String mode) {
        return switch (mode) { case "car" -> 5.19; case "taxi" -> 5.80; case "FHV" -> 5.25; default -> 0; };
    }
    static double toll(String link, double time) {
        return toll(MTA.contains(link) ? 1 : PANYNJ.contains(link) ? 2 : 0, time);
    }
    private static double toll(int facility, double time) {
        if (facility == 1) return 6.12;
        if (facility != 2) return 0;
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
        if (NETWORK_MODES.contains(e.getNetworkMode())
                && scenario.getPopulation().getPersons().containsKey(e.getPersonId()))
            drivers.put(e.getVehicleId(), e.getPersonId());
    }
    @Override public void handleEvent(VehicleLeavesTrafficEvent e) { drivers.remove(e.getVehicleId()); }
    @Override public void handleEvent(LinkLeaveEvent e) {
        // Archived NewScoring keeps all times >=20:00 off-peak, including after midnight.
        double tariffTime=zipAligned && e.getTime()>=86400?0:e.getTime();
        int i=e.getLinkId().index();
        charge(e.getTime(), drivers.get(e.getVehicleId()), toll(i<facility.length?facility[i]:0, tariffTime), "nyc-legacy-facility-toll");
    }
    @Override public void reset(int iteration) { drivers.clear(); }
}

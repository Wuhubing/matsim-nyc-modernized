package org.c2smart.matsimnyc;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.Activity;
import org.matsim.api.core.v01.population.Leg;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.Plan;
import org.matsim.api.core.v01.population.PlanElement;
import org.matsim.contrib.roadpricing.RoadPricingScheme;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.population.routes.NetworkRoute;
import org.matsim.core.router.TripRouter;
import org.matsim.core.router.TripStructureUtils;
import org.matsim.core.router.util.TravelTime;
import org.matsim.core.scoring.ScoringFunction;
import org.matsim.core.scoring.ScoringFunctionFactory;
import org.matsim.facilities.FacilitiesUtils;
import org.matsim.utils.objectattributes.attributable.AttributesImpl;
import org.matsim.vehicles.Vehicle;
import org.matsim.vehicles.VehicleUtils;

/**
 * Estimated score of a plan under a fixed environment (G estimator, QR3/06_G_estimator_design.md section 3).
 *
 * A forward pass over a copy of the plan: activities end at their end time (or after their maximum duration), but not
 * before the agent arrives; network legs are timed link by link on the given TravelTime (start link skipped, end link
 * at free-flow speed, as in experiments/l2seg/route_gap.py); teleported legs keep their routed time; pt trips, and the
 * trips listed in {@code reroute}, are routed by the TripRouter at their actual departure. The timed plan is scored with
 * the run's ScoringFunctionFactory, plus the charges the run adds through events: LegacyCosts' fixed costs per network
 * leg and facility tolls on link leave (score units), and road-pricing link tolls on link entry for private cars (money).
 * Both sides of a gap use this estimator, never an executed score.
 */
final class PlanEstimator {
    static final Set<String> PT_ROUTING_MODES = Set.of("pt");

    record Result(double score, boolean stuck, int failures, double lastArrival, String error) {}

    private final Scenario scenario;
    private final TravelTime travelTime;
    private final ScoringFunctionFactory scoring;
    private final Set<String> networkModes;
    private final boolean legacyCosts, zipAligned;
    private final RoadPricingScheme pricing;      // null: no road pricing
    private final double endTime;                 // QSim end; arriving later counts as stuck

    PlanEstimator(Scenario scenario, TravelTime travelTime, ScoringFunctionFactory scoring, Set<String> networkModes,
                  boolean legacyCosts, boolean zipAligned, RoadPricingScheme pricing, double endTime) {
        this.scenario = scenario; this.travelTime = travelTime; this.scoring = scoring; this.networkModes = networkModes;
        this.legacyCosts = legacyCosts; this.zipAligned = zipAligned; this.pricing = pricing; this.endTime = endTime;
    }

    /** MATSim's core listeners module; ControlerDefaultsModule needs its bindings to build an injector without a Controler. */
    static org.matsim.core.controler.AbstractModule coreListenersModule() {
        return new org.matsim.core.controler.corelisteners.ControlerDefaultCoreListenersModule();
    }

    /** Vehicles as at the start of a run. With vehiclesSource = modeVehicleTypesFromVehiclesData, MATSim's PrepareForSim
     * creates one vehicle per person and network mode (type id = mode) and records the ids in the person attribute
     * "vehicles"; plans snapshots keep the attribute but the vehicles themselves are not written. Routing and road
     * pricing need them: create the missing ones from the ids; if a person has no ids at all, run PrepareForSim. */
    static void ensureVehicles(com.google.inject.Injector injector, Scenario scenario) {
        var vehicles = scenario.getVehicles();
        boolean noIds = false; int created = 0;
        for (Person p : scenario.getPopulation().getPersons().values()) {
            java.util.Map<String, Id<Vehicle>> ids;
            try { ids = VehicleUtils.getVehicleIds(p); } catch (RuntimeException e) { ids = null; }
            if (ids == null || ids.isEmpty()) { noIds = true; continue; }
            for (var e : ids.entrySet()) {
                if (vehicles.getVehicles().containsKey(e.getValue())) continue;
                var type = vehicles.getVehicleTypes().get(Id.create(e.getKey(), org.matsim.vehicles.VehicleType.class));
                if (type == null) throw new IllegalStateException("no vehicle type '" + e.getKey() + "' for vehicle " + e.getValue());
                vehicles.addVehicle(VehicleUtils.createVehicle(e.getValue(), type)); created++;
            }
        }
        if (noIds) injector.getInstance(org.matsim.core.controler.PrepareForSim.class).run();
        System.out.printf("vehicles: created %,d from person attributes%s%n", created, noIds ? "; PrepareForSim run for persons without ids" : "");
    }

    static String describe(Throwable e) {
        var s = new StringBuilder(e.toString());
        var st = e.getStackTrace();
        for (int i = 0; i < Math.min(3, st.length); i++) s.append(" @ ").append(st[i].getClassName().replaceAll(".*\\.", "")).append('.').append(st[i].getMethodName()).append(':').append(st[i].getLineNumber());
        return s.toString();
    }

    /** A deep copy of the plan's elements (interaction activities become ordinary activities, so their times can be set). */
    static Plan copy(Plan plan) {
        Plan out = PopulationUtils.createPlan();
        PopulationUtils.copyFromTo(plan, out);
        return out;
    }

    /** Replaces trip {@code tripIndex} (0-based, in plan order) by one placeholder leg of {@code mode}, to be routed. */
    static void setTripMode(Plan plan, int tripIndex, String mode) {
        var trip = TripStructureUtils.getTrips(plan).get(tripIndex);
        Leg leg = PopulationUtils.createLeg(mode);
        TripStructureUtils.setRoutingMode(leg, mode);
        TripRouter.insertTrip(plan, trip.getOriginActivity(), List.of(leg), trip.getDestinationActivity());
    }

    static String routingMode(Leg leg) {
        String m = TripStructureUtils.getRoutingMode(leg);
        return m != null ? m : leg.getMode();
    }

    /** Estimates {@code plan} in place (it must be a copy). Trips whose index is in {@code reroute}, and all pt trips,
     * are routed at their departure; routing failures keep the old trip and are counted. */
    Result estimate(Person person, Plan plan, Set<Integer> reroute, TripRouter router) {
        List<PlanElement> pes = plan.getPlanElements();
        double now = 0, scoreCharges = 0, money = 0;
        int trip = -1, failures = 0;
        String error = null;
        boolean first = true, stuck = false;
        Id<Vehicle> car = carVehicle(person);
        for (int i = 0; i < pes.size(); i++) {
            PlanElement pe = pes.get(i);
            if (pe instanceof Activity a) {
                if (TripStructureUtils.isStageActivityType(a.getType())) {
                    // routed trips contain InteractionActivity, whose times cannot be set; stage activities are not scored
                    try { a.setStartTime(now); a.setEndTime(now); } catch (UnsupportedOperationException ignored) { }
                    continue;
                }
                double end;
                if (first) {
                    a.setStartTimeUndefined();
                    end = a.getEndTime().isDefined() ? a.getEndTime().seconds()
                            : a.getMaximumDuration().isDefined() ? a.getMaximumDuration().seconds() : Double.NaN;
                } else {
                    a.setStartTime(now);
                    end = a.getEndTime().isDefined() ? Math.max(now, a.getEndTime().seconds())
                            : a.getMaximumDuration().isDefined() ? now + a.getMaximumDuration().seconds() : Double.NaN;
                }
                first = false;
                boolean departs = i + 1 < pes.size() && pes.get(i + 1) instanceof Leg;
                if (!departs || Double.isNaN(end)) { a.setEndTimeUndefined(); continue; }
                a.setEndTime(end); now = end;
                trip++;
                int j = i + 1;
                while (!(pes.get(j) instanceof Activity d) || TripStructureUtils.isStageActivityType(d.getType())) j++;
                Activity destination = (Activity) pes.get(j);
                String mode = routingMode((Leg) pes.get(i + 1));
                if (reroute.contains(trip) || PT_ROUTING_MODES.contains(mode)) {
                    List<? extends PlanElement> routed = null;
                    try {
                        routed = router.calcRoute(mode, FacilitiesUtils.toFacility(a, scenario.getActivityFacilities()),
                                FacilitiesUtils.toFacility(destination, scenario.getActivityFacilities()), now, person, new AttributesImpl());
                    } catch (RuntimeException e) { routed = null; error = describe(e); }
                    if (routed == null || routed.isEmpty()) failures++;
                    else TripRouter.insertTrip(pes, a, routed, destination);
                }
                continue;
            }
            Leg leg = (Leg) pe;
            leg.setDepartureTime(now);
            double tt;
            if (networkModes.contains(leg.getMode()) && leg.getRoute() instanceof NetworkRoute route) {
                double[] c = traverse(route, now, person, leg.getMode(), car);
                tt = c[0]; scoreCharges += c[1]; money += c[2];
                route.setDistance(c[3]); route.setTravelTime(tt);
            } else if (leg.getTravelTime().isDefined()) {
                tt = leg.getTravelTime().seconds();
            } else if (leg.getRoute() != null && leg.getRoute().getTravelTime().isDefined()) {
                tt = leg.getRoute().getTravelTime().seconds();
            } else {
                failures++; tt = 0;
            }
            leg.setTravelTime(tt);
            now += tt;
            if (legacyCosts) scoreCharges -= LegacyCosts.fixedCost(leg.getMode()) * LegacyCosts.MONEY_UTILITY;
            if (now > endTime) stuck = true;
        }
        for (PlanElement pe : pes)
            if (pe instanceof Leg l && l.getRoute() == null)
                return new Result(Double.NaN, stuck, Math.max(failures, 1), now, error != null ? error : "unrouted " + l.getMode() + " leg");
        ScoringFunction sf = scoring.createNewScoringFunction(person);
        for (PlanElement pe : pes) {
            if (pe instanceof Activity a) { if (!TripStructureUtils.isStageActivityType(a.getType())) sf.handleActivity(a); }
            else sf.handleLeg((Leg) pe);
        }
        for (var t : TripStructureUtils.getTrips(pes)) sf.handleTrip(t);
        if (scoreCharges != 0) sf.addScore(scoreCharges);
        if (money != 0) sf.addMoney(money);
        if (stuck) sf.agentStuck(endTime);
        sf.finish();
        return new Result(sf.getScore(), stuck, failures, now, error);
    }

    /** {travel time, score charges, money, distance} of one network leg departing at {@code dep}. */
    private double[] traverse(NetworkRoute route, double dep, Person person, String mode, Id<Vehicle> car) {
        var links = scenario.getNetwork().getLinks();
        double t = dep, dist = 0, score = 0, money = 0;
        boolean tolledVehicle = pricing != null && "car".equals(mode) && car != null;
        if (route.getLinkIds().isEmpty() && route.getStartLinkId().equals(route.getEndLinkId())) return new double[] {0, 0, 0, 0};
        if (legacyCosts) score -= LegacyCosts.toll(route.getStartLinkId().toString(), tariff(t)) * LegacyCosts.MONEY_UTILITY;
        for (Id<Link> id : route.getLinkIds()) {
            Link link = links.get(id);
            if (tolledVehicle) money -= toll(id, t, person, car);
            t += travelTime.getLinkTravelTime(link, t, person, null);
            dist += link.getLength();
            if (legacyCosts) score -= LegacyCosts.toll(id.toString(), tariff(t)) * LegacyCosts.MONEY_UTILITY;
        }
        Link end = links.get(route.getEndLinkId());
        if (tolledVehicle) money -= toll(end.getId(), t, person, car);
        t += LinkHourTravelTime.freeFlow(end, t);
        dist += end.getLength();
        return new double[] {t - dep, score, money, dist};
    }

    private double tariff(double t) { return zipAligned && t >= 86400 ? 0 : t; }

    private double toll(Id<Link> link, double time, Person person, Id<Vehicle> car) {
        org.matsim.contrib.roadpricing.RoadPricingSchemeImpl.Cost c = pricing.getLinkCostInfo(link, time, person.getId(), car);
        return c == null ? 0 : c.amount;
    }

    private static Id<Vehicle> carVehicle(Person person) {
        try { return VehicleUtils.getVehicleId(person, "car"); } catch (RuntimeException e) { return null; }
    }

    /** Indices of trips whose routing mode is a network mode. */
    List<Integer> networkTrips(Plan plan) {
        var out = new ArrayList<Integer>();
        var trips = TripStructureUtils.getTrips(plan);
        for (int i = 0; i < trips.size(); i++) {
            var legs = trips.get(i).getLegsOnly();
            if (!legs.isEmpty() && networkModes.contains(routingMode(legs.getFirst()))) out.add(i);
        }
        return out;
    }
}

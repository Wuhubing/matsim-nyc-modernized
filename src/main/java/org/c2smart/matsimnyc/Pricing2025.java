package org.c2smart.matsimnyc;

import org.matsim.api.core.v01.*;
import org.matsim.api.core.v01.events.*;
import org.matsim.api.core.v01.events.handler.*;
import org.matsim.api.core.v01.population.Person;
import org.matsim.core.api.experimental.events.EventsManager;
import org.matsim.core.controler.AbstractModule;
import org.matsim.core.router.costcalculators.RandomizingTimeDistanceTravelDisutilityFactory;
import org.matsim.core.router.util.TravelDisutility;
import org.matsim.api.core.v01.network.Link;
import org.matsim.vehicles.Vehicle;
import java.nio.file.*;
import java.util.*;

/** Launch-2025 weekday/E-ZPass policy on historical demand. Billing is stateful;
 * routing deliberately uses a first-entry link-cost approximation (see scenario README). */
public final class Pricing2025 implements VehicleEntersTrafficEventHandler,
        VehicleLeavesTrafficEventHandler, LinkEnterEventHandler, PersonDepartureEventHandler {
    private final Set<String> entry = new HashSet<>(), inside = new HashSet<>();
    // Per-link flags indexed by Id.index(); avoids String ids on the event thread and in route search.
    private static final byte INSIDE=1, ENTRY=2, TUNNEL=4, MTA_IN_FLAG=8, MTA_OUT_FLAG=16;
    private static final Set<String> NETWORK_MODES = Set.of("car","taxi","FHV"), TRIP_FEE_MODES = Set.of("taxi","FHV");
    private byte[] flags = new byte[0];
    private static final Set<String> TUNNELS = Set.of("320888283_0","60325668_0",
            "415882710_0","11878036_0","413749473_0");
    private static final Set<String> MTA_IN = Set.of("11878036_0","413749473_0");
    private static final Set<String> MTA_OUT = Set.of("46469739_0","5681925_0");
    // The detailed published schedule explicitly labels the daily maximum $5,
    // separately from its Phase-1 per-crossing amounts ($3 / $1.50).
    // Policy lever for response-surface experiments: scales private-car charges and credits together.
    // The default 1.0 leaves every amount bit-identical (x * 1.0 == x).
    static final double SCALE = Double.parseDouble(System.getProperty("nyc.pricing.scale", "1.0"));
    private static final double DAILY_CREDIT_CAP = 5 * SCALE;
    private final Map<Id<Vehicle>, Trip> trips = new HashMap<>();
    private final Map<Id<Vehicle>, Map<Long, Day>> paidDays = new HashMap<>();
    private final Map<Id<Person>,Integer> departureCursor = new HashMap<>();
    private final Scenario scenario;
    @com.google.inject.Inject private EventsManager events;
    private static final class Trip {
        Id<Person> person; String mode; double tunnelCredit; boolean tripFee, touchedZone;
        Trip(Id<Person> p, String m) { person=p; mode=m; }
    }
    private static final class Day { boolean paid, peakCharge; double credit, pending; }
    private Day day(Id<Vehicle> vehicle,double time) {
        return paidDays.computeIfAbsent(vehicle,k->new HashMap<>()).computeIfAbsent((long)Math.floor(time/86400),k->new Day());
    }
    public Pricing2025(Scenario scenario, String filename) {
        this.scenario=scenario;
        try {
            for (String row: Files.readAllLines(Path.of(filename)).subList(1, Files.readAllLines(Path.of(filename)).size())) {
                String[] v=row.split(",");
                if (!scenario.getNetwork().getLinks().containsKey(Id.createLinkId(v[0]))) throw new IllegalArgumentException(row);
                inside.add(v[0]); if (v[1].equals("1")) entry.add(v[0]);
            }
        } catch (java.io.IOException e) { throw new java.io.UncheckedIOException(e); }
        for (String id: inside) mark(id, INSIDE);
        for (String id: entry) mark(id, ENTRY);
        for (String id: TUNNELS) mark(id, TUNNEL);
        for (String id: MTA_IN) mark(id, MTA_IN_FLAG);
        for (String id: MTA_OUT) mark(id, MTA_OUT_FLAG);
    }
    private void mark(String id, byte flag) {
        int i=Id.createLinkId(id).index();
        if (i>=flags.length) flags=Arrays.copyOf(flags,i+1);
        flags[i]|=flag;
    }
    private boolean is(Id<Link> link, byte flag) { int i=link.index(); return i<flags.length && (flags[i]&flag)!=0; }
    public static boolean peak(double time) { double h=(time%86400)/3600; return h>=5 && h<21; }
    public static double carRate(double time, boolean tunnel) { return (peak(time) ? (tunnel?6:9) : 2.25) * SCALE; }
    @Override public void reset(int iteration) { trips.clear(); paidDays.clear(); departureCursor.clear(); }
    @Override public void handleEvent(PersonDepartureEvent e) {
        String mode=e.getLegMode();
        if(!TRIP_FEE_MODES.contains(mode) || scenario.getConfig().qsim().getMainModes().contains(mode)) return;
        Person person=scenario.getPopulation().getPersons().get(e.getPersonId()); if(person==null)return;
        var elements=person.getSelectedPlan().getPlanElements();
        for(int i=departureCursor.getOrDefault(e.getPersonId(),0);i<elements.size();i++) {
            if(elements.get(i) instanceof org.matsim.api.core.v01.population.Leg leg && mode.equals(leg.getMode())) {
                departureCursor.put(e.getPersonId(),i+1);
                if(!(leg.getRoute() instanceof org.matsim.core.population.routes.NetworkRoute route))
                    throw new IllegalStateException("Expected prepared network route for teleported "+mode);
                boolean touches=is(route.getStartLinkId(),INSIDE) || is(route.getEndLinkId(),INSIDE);
                if(!touches) for(var link:route.getLinkIds()) if(is(link,INSIDE)){touches=true;break;}
                if(touches) charge(new Trip(e.getPersonId(),mode),e.getTime(),mode.equals("taxi")?.75:1.5,mode+"-trip");
                return;
            }
        }
        throw new IllegalStateException("Cannot match "+mode+" departure to selected plan");
    }
    @Override public void handleEvent(VehicleEntersTrafficEvent e) {
        if (!scenario.getPopulation().getPersons().containsKey(e.getPersonId())) return;
        if (!NETWORK_MODES.contains(e.getNetworkMode())) return;
        Trip t=new Trip(e.getPersonId(),e.getNetworkMode()); trips.put(e.getVehicleId(),t);
        t.touchedZone=is(e.getLinkId(),INSIDE);
        // Starting inside incurs a passenger trip fee, but is not a private-car entry.
        tripFee(t,e.getLinkId(),e.getTime());
    }
    @Override public void handleEvent(VehicleLeavesTrafficEvent e) { trips.remove(e.getVehicleId()); }
    @Override public void handleEvent(LinkEnterEvent e) {
        Trip t=trips.get(e.getVehicleId()); if(t==null) return;
        Id<Link> link=e.getLinkId();
        if (is(link,TUNNEL)) t.tunnelCredit=peak(e.getTime())?(is(link,MTA_IN_FLAG)?1.5:3)*SCALE:0;
        if(t.mode.equals("car") && is(link,MTA_OUT_FLAG) && t.touchedZone && peak(e.getTime())) {
            Day d=day(e.getVehicleId(),e.getTime());
            if(!d.paid) d.pending=Math.min(DAILY_CREDIT_CAP,d.pending+1.5*SCALE);
            else credit(t,d,e.getTime(),1.5*SCALE);
        }
        if (t.mode.equals("car") && is(link,ENTRY)) {
            Day d=day(e.getVehicleId(),e.getTime());
            if(!d.paid) {
                d.paid=true; d.peakCharge=peak(e.getTime());
                d.credit=d.peakCharge?Math.min(DAILY_CREDIT_CAP,d.pending+t.tunnelCredit):0;
                charge(t,e.getTime(),carRate(e.getTime(),false)-d.credit,"car-entry"+(d.credit>0?"-tunnel-credit":""));
            } else if(peak(e.getTime())) {
                credit(t,d,e.getTime(),t.tunnelCredit);
            }
            t.tunnelCredit=0;
        } else tripFee(t,link,e.getTime());
        t.touchedZone |= is(link,INSIDE);
    }
    private void credit(Trip t,Day d,double time,double candidate) {
        double refund=d.peakCharge?Math.min(candidate,DAILY_CREDIT_CAP-d.credit):0;
        if(refund>0) {d.credit+=refund;charge(t,time,-refund,"car-tunnel-refund");}
    }
    private void tripFee(Trip t,Id<Link> link,double time) {
        if(!t.mode.equals("car") && !t.tripFee && is(link,INSIDE)) {
            t.tripFee=true; charge(t,time,t.mode.equals("taxi")?.75:1.5,t.mode+"-trip");
        }
    }
    private void charge(Trip t,double time,double amount,String reference) {
        events.processEvent(new PersonMoneyEvent(time,t.person,-amount,"toll","NYC2025",reference));
    }
    /** First-entry toll approximation used in route search only. */
    double routingToll(Id<Link> id,double time) {
        return is(id,ENTRY)?carRate(time,false)-(peak(time)&&is(id,TUNNEL)?(is(id,MTA_IN_FLAG)?1.5:3)*SCALE:0):0;
    }
    public AbstractModule module() {
        Pricing2025 self=this;
        return new AbstractModule() {
            @Override public void install() {
                addEventHandlerBinding().toInstance(self);
                // Pure routing proxy: never mutate billing state during path search.
                var base=new RandomizingTimeDistanceTravelDisutilityFactory("car",scenario.getConfig());
                final double moneyUtility=scenario.getConfig().scoring().getMarginalUtilityOfMoney();
                addTravelDisutilityFactoryBinding("car").toInstance(tt -> {
                    TravelDisutility d=base.createTravelDisutility(tt);
                    return new TravelDisutility() {
                        public double getLinkTravelDisutility(Link l,double time,Person p,Vehicle v) {
                            double toll=routingToll(l.getId(),time);
                            return d.getLinkTravelDisutility(l,time,p,v)+toll*moneyUtility;
                        }
                        public double getLinkMinimumTravelDisutility(Link l) { return d.getLinkMinimumTravelDisutility(l); }
                    };
                });
            }
        };
    }
}

package org.c2smart.matsimnyc;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.GZIPOutputStream;
import org.matsim.api.core.v01.*;
import org.matsim.api.core.v01.events.*;
import org.matsim.api.core.v01.events.handler.*;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.api.experimental.events.*;
import org.matsim.core.api.experimental.events.handler.*;
import org.matsim.core.controler.events.*;
import org.matsim.core.controler.listener.*;
import org.matsim.core.population.routes.NetworkRoute;
import org.matsim.core.utils.geometry.transformations.TransformationFactory;
import org.matsim.vehicles.Vehicle;

/** Observational only. Separate versioned files leave historical IterationMetrics untouched. */
public final class ResearchMetrics implements BeforeMobsimListener, IterationEndsListener,
        PersonDepartureEventHandler, PersonArrivalEventHandler, PersonStuckEventHandler,
        AgentWaitingForPtEventHandler, PersonEntersVehicleEventHandler, PersonLeavesVehicleEventHandler,
        VehicleEntersTrafficEventHandler, VehicleLeavesTrafficEventHandler, VehicleAbortsEventHandler,
        LinkEnterEventHandler, LinkLeaveEventHandler, PersonMoneyEventHandler {
    private final Scenario scenario;
    private final Path directory;
    private final LinkedHashMap<Id<Person>, State> persons = new LinkedHashMap<>();
    private final Map<Id<Vehicle>, Traffic> traffic = new HashMap<>();
    private final Map<String, Map<Long, Cell>> links = new TreeMap<>();
    private final Map<String, Map<String, Mode>> groups = new TreeMap<>();
    private final Map<String, Long> errors = new TreeMap<>();
    private final Map<Integer, String> linkNames = new HashMap<>();
    private final Set<Integer> entryLinks = new HashSet<>();
    private double cutoff;
    private long beforeNanos;
    private static final ObjectMapper JSON = new ObjectMapper();
    static final class Mode {
        public long departures, completed, stuck;
        public double completed_seconds;
    }
    static final class State {
        final Person person;
        final String subpopulation, cohort;
        final String[] groupNames;
        String choice, full, previousChoice, previousFull;
        Double previousScore;
        String activeMode;
        double departure, waitStart = Double.NaN, waitSeconds, travel, carSeconds, revenue;
        long departures, completed, carCompleted, stuck, waitCount, entries;
        long realizedChoice = 17, outcome = 17;
        State(Person p, String cohort) {
            person=p;subpopulation=Objects.toString(p.getAttributes().getAttribute("subpopulation"),"unknown");this.cohort=cohort;
            groupNames=new String[]{"all", "subpopulation:"+subpopulation, "charging:"+cohort, "joint:"+subpopulation+":"+cohort};
        }
        String[] groups() { return groupNames; }
        void clear() {
            activeMode=null; departure=0;waitStart=Double.NaN;waitSeconds=travel=carSeconds=revenue=0;
            departures=completed=carCompleted=stuck=waitCount=entries=0;realizedChoice=outcome=17;
        }
    }
    static final class Traffic {
        final State person; final String mode;
        int link=-1; double entered;
        Traffic(State p,String m){person=p;mode=m;}
    }
    static final class Cell { long entries, completed; double seconds; }

    public ResearchMetrics(Scenario scenario, Path directory, Path polygon) {
        this.scenario=scenario;this.directory=directory.resolve("research");
        cutoff=scenario.getConfig().qsim().getEndTime().seconds();
        try {
            Files.createDirectories(this.directory);
            String entryFile=System.getProperty("nyc.metricLinks");
            if(entryFile!=null) {
                var rows=Files.readAllLines(Path.of(entryFile));
                for(String row:rows.subList(1,rows.size())) {
                    var v=row.split(",");if(v[1].equals("1"))entryLinks.add(Id.createLinkId(v[0]).index());
                }
            }
            var ring=JSON.readTree(polygon.toFile()).path("geometry").path("coordinates").get(0);
            if(ring==null || ring.size()<4)throw new IllegalArgumentException("Expected GeoJSON Polygon exterior ring");
            var transform=TransformationFactory.getCoordinateTransformation("EPSG:4326",scenario.getConfig().global().getCoordinateSystem());
            double[][] points=new double[ring.size()][2];
            for(int i=0;i<ring.size();i++) {
                var c=transform.transform(new Coord(ring.get(i).get(0).asDouble(),ring.get(i).get(1).asDouble()));
                points[i]=new double[]{c.getX(),c.getY()};
            }
            for(var p:scenario.getPopulation().getPersons().values())persons.put(p.getId(),new State(p,cohort(p,points)));
            for(var l:scenario.getNetwork().getLinks().values())linkNames.put(l.getId().index(),l.getId().toString());
            var metadata=new LinkedHashMap<String,Object>();
            metadata.put("schema_version",1);
            metadata.put("cohort_definition","Fixed from loaded selected-plan non-stage activity coordinates: any origin/destination inside reconstructed Schema-1 polygon, all modes. Boundary included. Missing coordinates -> unknown unless another activity is inside. Never recomputed after replanning.");
            metadata.put("polygon",polygon.toString());
            metadata.put("polygon_status","Repository exploratory reconstruction; not authoritative paper boundary.");
            metadata.put("cutoff_seconds",cutoff);
            metadata.put("link_definition","LinkEnter entries; matched LinkEnter/LinkLeave traversal times by entry hour and network mode, all network vehicles. Start-link partial traversals omitted; exits/aborts clear pending entries. Sparse output: absent cells mean zero entries/completions.");
            metadata.put("signature_definition","SHA-256 planned choice excludes timing; planned full includes activity/leg timing but excludes mutable travel-time estimates and score. Realized choice/outcome are rolling 64-bit diagnostics (possible collisions), not proof of identical event streams.");
            metadata.put("entry_crossing_definition","Private car entries use nyc.metricLinks (2025 geofence) for all scenarios, to preserve legacy metric equivalence; NOT Schema-1 toll crossings.");
            metadata.put("units","Unexpanded synthetic agents, legs, vehicles and dollars; no countsScaleFactor applied. Mode rows describe legs, not whole trips. Score is total executed-plan utility, not paper travel consumer surplus.");
            JSON.writerWithDefaultPrettyPrinter().writeValue(this.directory.resolve("schema.json").toFile(),metadata);
            try(var w=writer("cohorts.csv.gz")) {
                w.write("person_id,subpopulation,charging_cohort\n");
                for(var s:persons.values())w.write(csv(s.person.getId())+","+csv(s.subpopulation)+","+csv(s.cohort)+"\n");
            }
        }catch(IOException e){throw new UncheckedIOException(e);}
    }
    static boolean inside(double x,double y,double[][] ring) {
        boolean yes=false;
        for(int i=0,j=ring.length-1;i<ring.length;j=i++) {
            double ax=ring[j][0],ay=ring[j][1],bx=ring[i][0],by=ring[i][1];
            double cross=(x-ax)*(by-ay)-(y-ay)*(bx-ax);
            if(Math.abs(cross)<1e-7 && x>=Math.min(ax,bx) && x<=Math.max(ax,bx) && y>=Math.min(ay,by) && y<=Math.max(ay,by))return true;
            if((ay>y)!=(by>y) && x<(bx-ax)*(y-ay)/(by-ay)+ax)yes=!yes;
        }
        return yes;
    }
    static String cohort(Person p,double[][] points) {
        boolean missing=false;
        for(var e:p.getSelectedPlan().getPlanElements())if(e instanceof Activity a && !a.getType().endsWith("interaction")) {
            var c=a.getCoord();if(c==null){missing=true;continue;}
            if(inside(c.getX(),c.getY(),points))return "related";
        }
        return missing?"unknown":"unrelated";
    }
    static String fingerprint(Plan plan,boolean timing) {
        try {
            var d=MessageDigest.getInstance("SHA-256");
            for(var e:plan.getPlanElements()) {
                String v;
                if(e instanceof Activity a)v="A|"+a.getType()+"|"+a.getCoord()+"|"+a.getLinkId()+"|"+a.getFacilityId()+(timing?"|"+a.getStartTime()+"|"+a.getEndTime()+"|"+a.getMaximumDuration():"");
                else {var l=(Leg)e;var r=l.getRoute();v="L|"+l.getMode()+"|"+(r==null?"null":r.getRouteType()+"|"+r.getStartLinkId()+"|"+r.getEndLinkId()+"|"+r.getRouteDescription())+(timing?"|"+l.getDepartureTime():"");}
                byte[] b=v.getBytes(StandardCharsets.UTF_8);
                d.update(java.nio.ByteBuffer.allocate(4).putInt(b.length).array());d.update(b);
            }
            return HexFormat.of().formatHex(d.digest());
        }catch(Exception e){throw new IllegalStateException(e);}
    }
    @Override public void reset(int iteration) {
        traffic.clear();links.clear();groups.clear();errors.clear();for(var s:persons.values())s.clear();
    }
    @Override public void notifyBeforeMobsim(BeforeMobsimEvent event) {
        long t=System.nanoTime();
        for(var s:persons.values()) {s.choice=fingerprint(s.person.getSelectedPlan(),false);s.full=fingerprint(s.person.getSelectedPlan(),true);}
        beforeNanos=System.nanoTime()-t;
    }
    private void error(String key){errors.merge(key,1L,Long::sum);}
    private Mode mode(String group,String mode){return groups.computeIfAbsent(group,k->new TreeMap<>()).computeIfAbsent(mode,k->new Mode());}
    private static long mix(long h,long value){return (h^value)*0x100000001b3L;}
    private void event(State s,int type,double time){if(s!=null){s.outcome=mix(mix(s.outcome,type),Double.doubleToLongBits(time));}}
    @Override public void handleEvent(PersonDepartureEvent e) {
        var s=persons.get(e.getPersonId());if(s==null)return;
        if(s.activeMode!=null)error("overlapping_departures");
        s.activeMode=e.getLegMode();s.departure=e.getTime();s.departures++;
        for(var g:s.groups())mode(g,e.getLegMode()).departures++;
        s.realizedChoice=mix(s.realizedChoice,e.getLegMode().hashCode());event(s,1,e.getTime());
    }
    @Override public void handleEvent(PersonArrivalEvent e) {
        var s=persons.get(e.getPersonId());if(s==null)return;
        if(s.activeMode==null){error("unmatched_arrivals");return;}
        if(!s.activeMode.equals(e.getLegMode()))error("arrival_mode_mismatch");
        double dt=e.getTime()-s.departure;s.completed++;s.travel+=dt;
        if("car".equals(s.activeMode)){s.carCompleted++;s.carSeconds+=dt;}
        for(var g:s.groups()){var m=mode(g,s.activeMode);m.completed++;m.completed_seconds+=dt;}
        s.activeMode=null;event(s,2,e.getTime());
    }
    @Override public void handleEvent(PersonStuckEvent e) {
        var s=persons.get(e.getPersonId());if(s==null)return;s.stuck++;
        for(var g:s.groups())mode(g,e.getLegMode()).stuck++;event(s,3,e.getTime());
    }
    @Override public void handleEvent(AgentWaitingForPtEvent e) {
        var s=persons.get(e.getPersonId());if(s==null)return;
        if(!Double.isNaN(s.waitStart))error("overlapping_waits");s.waitStart=e.getTime();s.waitCount++;event(s,4,e.getTime());
    }
    @Override public void handleEvent(PersonEntersVehicleEvent e) {
        var s=persons.get(e.getPersonId());if(s==null)return;
        if(e instanceof org.matsim.core.mobsim.qsim.pt.PersonEntersPtVehicleEvent) {
            if(Double.isNaN(s.waitStart))error("boarding_without_wait");else s.waitSeconds+=e.getTime()-s.waitStart;
            s.waitStart=Double.NaN;
        }
        event(s,5,e.getTime());s.outcome=mix(s.outcome,e.getVehicleId().toString().hashCode());
    }
    @Override public void handleEvent(PersonLeavesVehicleEvent e){var s=persons.get(e.getPersonId());event(s,6,e.getTime());}
    @Override public void handleEvent(PersonMoneyEvent e){var s=persons.get(e.getPersonId());if(s!=null && "toll".equals(e.getPurpose()))s.revenue-=e.getAmount();}
    @Override public void handleEvent(VehicleEntersTrafficEvent e){traffic.put(e.getVehicleId(),new Traffic(persons.get(e.getPersonId()),e.getNetworkMode()));}
    @Override public void handleEvent(VehicleLeavesTrafficEvent e){traffic.remove(e.getVehicleId());}
    @Override public void handleEvent(VehicleAbortsEvent e){traffic.remove(e.getVehicleId());}
    private Cell cell(Traffic t,int link,double time) {
        long k=((long)link<<32)|(long)(int)Math.floor(time/3600);
        return links.computeIfAbsent(t.mode,k0->new HashMap<>()).computeIfAbsent(k,k0->new Cell());
    }
    @Override public void handleEvent(LinkEnterEvent e) {
        var t=traffic.get(e.getVehicleId());if(t==null)return;
        if(t.link!=-1)error("unmatched_link_entry");
        t.link=e.getLinkId().index();t.entered=e.getTime();cell(t,t.link,t.entered).entries++;
        if(t.person!=null && "car".equals(t.mode) && entryLinks.contains(t.link))t.person.entries++;
        if(t.person!=null){t.person.realizedChoice=mix(t.person.realizedChoice,e.getLinkId().toString().hashCode());event(t.person,7,e.getTime());}
    }
    @Override public void handleEvent(LinkLeaveEvent e) {
        var t=traffic.get(e.getVehicleId());if(t==null || t.link==-1)return;
        if(t.link==e.getLinkId().index() && e.getTime()>=t.entered){var c=cell(t,t.link,t.entered);c.completed++;c.seconds+=e.getTime()-t.entered;}
        else error("link_pair_mismatch");t.link=-1;
    }
    static String csv(Object o){return o==null?"":"\""+o.toString().replace("\"","\"\"")+"\"";}
    private BufferedWriter writer(String name)throws IOException{return new BufferedWriter(new OutputStreamWriter(new GZIPOutputStream(Files.newOutputStream(directory.resolve(name)),65536),StandardCharsets.UTF_8),65536);}
    @Override public void notifyIterationEnds(IterationEndsEvent e){finish(e.getIteration());}
    void finish(int iteration) {
        long start=System.nanoTime();
        try {
            var totals=new TreeMap<String,double[]>();
            try(var w=writer("persons-"+iteration+".csv.gz")) {
                w.write("person_id,subpopulation,charging_cohort,score,score_delta,plans_in_memory,choice_sha256,plan_sha256,choice_changed,plan_changed,realized_choice_hash64,outcome_hash64,departures,completed,unfinished,stuck,completed_travel_seconds,completed_car_legs,completed_car_seconds,wait_segments,waiting_at_cutoff,censored_wait_seconds,toll_revenue,private_car_entry_crossings\n");
                for(var s:persons.values()) {
                    Double score=s.person.getSelectedPlan().getScore();double wait=s.waitSeconds+(Double.isNaN(s.waitStart)?0:Math.max(0,cutoff-s.waitStart));
                    int unfinished=s.activeMode==null?0:1;
                    if(s.departures!=s.completed+unfinished)error("leg_conservation");
                    if(unfinished!=s.stuck)error("stuck_active_mismatch");
                    for(var g:s.groups()) {
                        var a=totals.computeIfAbsent(g,k->new double[14]);a[0]++;if(score!=null){a[1]+=score;a[2]++;}
                        a[3]+=unfinished;a[4]+=s.carCompleted;a[5]+=s.carSeconds;a[6]+=s.waitCount;a[7]+=Double.isNaN(s.waitStart)?0:1;a[8]+=wait;a[9]+=s.revenue;a[13]+=s.entries;
                        if(s.previousChoice!=null){a[10]++;if(!s.choice.equals(s.previousChoice))a[11]++;if(!s.full.equals(s.previousFull))a[12]++;}
                    }
                    w.write(csv(s.person.getId())+","+csv(s.subpopulation)+","+csv(s.cohort)+","+csv(score)+","+csv(score!=null && s.previousScore!=null?score-s.previousScore:null)+","+s.person.getPlans().size()+","+s.choice+","+s.full+","+(s.previousChoice==null?"":!s.choice.equals(s.previousChoice))+","+(s.previousFull==null?"":!s.full.equals(s.previousFull))+","+Long.toUnsignedString(s.realizedChoice)+","+Long.toUnsignedString(s.outcome)+","+s.departures+","+s.completed+","+unfinished+","+s.stuck+","+s.travel+","+s.carCompleted+","+s.carSeconds+","+s.waitCount+","+(Double.isNaN(s.waitStart)?0:1)+","+wait+","+s.revenue+","+s.entries+"\n");
                    s.previousScore=score;s.previousChoice=s.choice;s.previousFull=s.full;
                }
            }
            try(var w=writer("groups-"+iteration+".csv.gz")) {
                w.write("group,persons,score_sum,scored_persons,unfinished,completed_car_legs,completed_car_seconds,wait_segments,waiting_at_cutoff,censored_wait_seconds,toll_revenue,compared_persons,choice_changed,plan_changed,private_car_entry_crossings\n");
                for(var en:totals.entrySet()){w.write(csv(en.getKey()));for(double v:en.getValue())w.write(","+v);w.write("\n");}
            }
            try(var w=writer("group-modes-"+iteration+".csv.gz")) {
                w.write("group,leg_mode,departures,completed,stuck,completed_seconds\n");
                for(var g:groups.entrySet())for(var m:g.getValue().entrySet()){var v=m.getValue();w.write(csv(g.getKey())+","+csv(m.getKey())+","+v.departures+","+v.completed+","+v.stuck+","+v.completed_seconds+"\n");}
            }
            try(var w=writer("link-hours-"+iteration+".csv.gz")) {
                w.write("link_id,entry_hour,network_mode,entries,completed_traversals,total_traversal_seconds\n");
                for(var m:links.entrySet())for(long k:new TreeSet<>(m.getValue().keySet())){var c=m.getValue().get(k);w.write(csv(linkNames.get((int)(k>>>32)))+","+(int)k+","+csv(m.getKey())+","+c.entries+","+c.completed+","+c.seconds+"\n");}
            }
            JSON.writerWithDefaultPrettyPrinter().writeValue(directory.resolve("diagnostics-"+iteration+".json").toFile(),Map.of("iteration",iteration,"errors",errors,"plan_fingerprint_seconds",beforeNanos/1e9,"research_output_seconds",(System.nanoTime()-start)/1e9));
        }catch(IOException ex){throw new UncheckedIOException(ex);}
    }
}

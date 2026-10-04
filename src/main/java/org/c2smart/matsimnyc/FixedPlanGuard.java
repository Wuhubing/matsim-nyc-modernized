package org.c2smart.matsimnyc;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.controler.events.BeforeMobsimEvent;
import org.matsim.core.controler.listener.BeforeMobsimListener;

/** Opt-in diagnostic only: fail before traffic execution if initialization changes a frozen plan. */
final class FixedPlanGuard implements BeforeMobsimListener {
    private final Scenario scenario;
    private final Path output;
    private final Map<String,String> loaded=new TreeMap<>();
    FixedPlanGuard(Scenario scenario, String output) {
        this.scenario=scenario;this.output=Path.of(output);
        for (Person p:scenario.getPopulation().getPersons().values()) loaded.put(p.getId().toString(),fingerprint(p));
    }
    private static String fingerprint(Person p) {
        try {
            var digest=MessageDigest.getInstance("SHA-256");
            for (PlanElement e:p.getSelectedPlan().getPlanElements()) {
                String value;
                if(e instanceof Activity a) value="A|"+a.getType()+"|"+a.getCoord()+"|"+a.getLinkId()+"|"+a.getFacilityId()+"|"+a.getStartTime()+"|"+a.getEndTime()+"|"+a.getMaximumDuration();
                else {
                    Leg l=(Leg)e;var r=l.getRoute();
                    value="L|"+l.getMode()+"|"+l.getDepartureTime()+"|"+l.getTravelTime()+"|"+(r==null?"null":r.getRouteType()+"|"+r.getStartLinkId()+"|"+r.getEndLinkId()+"|"+r.getRouteDescription()+"|"+r.getDistance()+"|"+r.getTravelTime());
                }
                digest.update(value.getBytes(StandardCharsets.UTF_8));digest.update((byte)'\n');
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch(Exception e){throw new RuntimeException(e);}
    }
    @Override public void notifyBeforeMobsim(BeforeMobsimEvent event) {
        try {
            int changed=0;var examples=new ArrayList<String>();var aggregate=MessageDigest.getInstance("SHA-256");
            for(var entry:loaded.entrySet()) {
                var p=scenario.getPopulation().getPersons().get(org.matsim.api.core.v01.Id.createPersonId(entry.getKey()));
                String actual=fingerprint(p);
                aggregate.update((entry.getKey()+":"+actual+"\n").getBytes(StandardCharsets.UTF_8));
                if(!actual.equals(entry.getValue())) {changed++;if(examples.size()<20)examples.add(entry.getKey());}
            }
            Files.writeString(output,"{\"persons\":"+loaded.size()+",\"changed\":"+changed+",\"iteration\":"+event.getIteration()+",\"sha256\":\""+HexFormat.of().formatHex(aggregate.digest())+"\",\"example_ids\":\""+examples+"\"}\n");
            if(changed!=0)throw new IllegalStateException("Frozen plan initialization changed "+changed+" persons; see "+output);
        } catch(Exception e){throw new RuntimeException(e);}
    }
}

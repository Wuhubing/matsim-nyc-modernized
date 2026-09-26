package org.c2smart.matsimnyc;

import java.nio.file.*;
import java.io.*;
import java.util.*;
import org.matsim.api.core.v01.network.*;
import org.matsim.core.network.*;

/** Archived Run.java values, not reconstructed paper tables. Missing capacities are never guessed. */
public final class ArchiveNetwork {
    static final double[][] SPEED = {
        {.472941,.497564,.502572,.435369,.484185,.568571},
        {.276634,.265192,.261024,.254357,.279059,.308127},
        {.409828,.392877,.386702,.376825,.413420,.456485},
        {.737691,.707178,.696064,.678285,.744156,.821673}};
    static final int[] HOURS={0,7,10,13,16,19,22};
    static final int[] PERIODS={5,0,1,2,3,4,5};
    public static double[][] readFactors(Path path) {
        if(path==null || !Files.isRegularFile(path)) throw new IllegalArgumentException(
            "ZIP alignment requires the missing archived capacity factors: "+path+
            ". Supply period,expressway,arterial rows 0..5 from the original calibrated parameter set. No paper-table fallback is used.");
        try {
            var lines=Files.readAllLines(path);
            if(lines.size()!=7 || !lines.getFirst().trim().equals("period,expressway,arterial")) throw new IllegalArgumentException("Expected header and six capacity-factor rows");
            double[][] factors=new double[2][6];
            for(int i=0;i<6;i++) {
                String[] v=lines.get(i+1).split(",");
                if(v.length!=3 || Integer.parseInt(v[0].trim())!=i) throw new IllegalArgumentException("Expected ordered periods 0..5");
                for(int k=0;k<2;k++) {
                    double x=Double.parseDouble(v[k+1].trim());
                    if(!Double.isFinite(x)||x<=0)throw new IllegalArgumentException("Capacity factors must be finite and positive");
                    factors[k][i]=x;
                }
            }
            return factors;
        } catch(IOException e){throw new UncheckedIOException(e);}
    }
    static double speed(double original,int period) {
        if(original==10)return original; // archived branch conditions omit exactly 10 m/s
        return original*SPEED[original>33?0:original>22?1:original>10?2:3][period];
    }
    public static void apply(Network network,double endTime,double[][] capacity) {
        if(Math.abs(network.getCapacityPeriod()-3600)>1e-6)throw new IllegalArgumentException("Archived runner assumes hourly capacities");
        record Original(double speed,double capacity){}
        var groups=new LinkedHashMap<Original,List<Link>>();
        for(Link link:network.getLinks().values())if(link.getAllowedModes().contains("car"))
            groups.computeIfAbsent(new Original(link.getFreespeed(),link.getCapacity()),k->new ArrayList<>()).add(link);
        for(var group:groups.entrySet())for(int i=0;i<HOURS.length;i++) {
            if(HOURS[i]*3600>endTime)continue;
            var original=group.getKey();int p=PERIODS[i];
            var event=new NetworkChangeEvent(HOURS[i]*3600.0);
            group.getValue().forEach(event::addLink);
            event.setFreespeedChange(new NetworkChangeEvent.ChangeValue(NetworkChangeEvent.ChangeType.ABSOLUTE_IN_SI_UNITS,speed(original.speed(),p)));
            event.setFlowCapacityChange(new NetworkChangeEvent.ChangeValue(NetworkChangeEvent.ChangeType.ABSOLUTE_IN_SI_UNITS,original.capacity()/3600*capacity[original.speed()>33?0:1][p]));
            NetworkUtils.addNetworkChangeEvent(network,event);
        }
    }
}

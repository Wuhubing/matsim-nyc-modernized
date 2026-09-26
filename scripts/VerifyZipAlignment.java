package org.c2smart.matsimnyc;

import java.nio.file.*;
import java.util.*;
import org.matsim.api.core.v01.*;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.network.NetworkUtils;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.contrib.roadpricing.RoadPricingConfigGroup;

public class VerifyZipAlignment {
    static void close(double a,double b) {if(Math.abs(a-b)>1e-9)throw new AssertionError(a+" != "+b);}
    public static void main(String[] args) throws Exception {
        for(String arm:List.of("baseline","schema1","actual2025")) {
            var c=ConfigUtils.loadConfig("scenarios/nyc-zip-aligned/config-"+arm+".xml",new NycModelConfig(),new RoadPricingConfigGroup());
            var n=ConfigUtils.addOrGetModule(c,NycModelConfig.class);
            if(!n.getZipAligned() || n.getPublishedNetwork() || !n.getRestoredCosts())throw new AssertionError("Wrong profile");
            if(!new HashSet<>(c.qsim().getMainModes()).equals(Set.of("car","FHV","taxi")))throw new AssertionError("Missing road modes");
        }
        var c=ConfigUtils.createConfig();c.network().setTimeVariantNetwork(true);
        var net=ScenarioUtils.createScenario(c).getNetwork();
        var a=net.getFactory().createNode(Id.createNodeId("a"),new Coord(0,0));
        var b=net.getFactory().createNode(Id.createNodeId("b"),new Coord(100,0));
        net.addNode(a);net.addNode(b);
        var l=net.getFactory().createLink(Id.createLinkId("road"),a,b);
        l.setFreespeed(40);l.setCapacity(7200);l.setAllowedModes(Set.of("car"));net.addLink(l);
        // Synthetic unit-test factors only; never written to a scenario.
        ArchiveNetwork.apply(net,108000,new double[][]{{1,2,3,4,5,6},{1,1,1,1,1,1}});
        var events=NetworkUtils.getNetworkChangeEvents(net);
        if(events.size()!=7)throw new AssertionError("Unexpected next-day repeat");
        for(var e:events) {
            int i=java.util.stream.IntStream.range(0,7).filter(j->ArchiveNetwork.HOURS[j]*3600==e.getStartTime()).findFirst().orElseThrow();
            int p=ArchiveNetwork.PERIODS[i];
            close(e.getFreespeedChange().getValue(),40*ArchiveNetwork.SPEED[0][p]);
            close(e.getFlowCapacityChange().getValue(),2*(p+1));
        }
        close(ArchiveNetwork.speed(10,0),10);
        close(ArchiveNetwork.speed(22,0),22*.409828);
        close(ArchiveNetwork.speed(33,0),33*.276634);
        try {ArchiveNetwork.readFactors(Path.of("missing-test-capacities.csv"));throw new AssertionError("Missing factors accepted");}catch(IllegalArgumentException expected){}
        var temp=Files.createTempFile("zip-factor-test-",".csv");
        try {
            Files.writeString(temp,"period,expressway,arterial\n0,NaN,1\n1,1,1\n2,1,1\n3,1,1\n4,1,1\n5,1,1\n");
            try {ArchiveNetwork.readFactors(temp);throw new AssertionError("NaN accepted");}catch(IllegalArgumentException expected){}
        } finally {Files.delete(temp);}
        System.out.println("PASS: three ZIP configs, road modes, archived speed boundaries/times, capacity units, no next-day repeat, missing/invalid factor rejection");
    }
}

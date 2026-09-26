package org.c2smart.matsimnyc;

import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.core.network.NetworkChangeEvent;
import org.matsim.core.network.NetworkUtils;

/** Rounded published Tables 3/4, arXiv:2008.04762v2, rather than unavailable SPSA files.
 * Road classes use the thresholds in the archived runner. Overnight uses period 6,
 * following section 4.2.2; dedicated transit links are left untouched.
 */
public final class PublishedNetwork {
    private static final double[][] SPEED_MPH = {{36.88,37.93,37.61,33.05,36.25,42.41},
                                                {14.10,13.42,13.11,12.80,13.91,15.34}};
    private static final double[][] CAPACITY = {{.61,.69,.51,.63,.55,.68}, {.59,.51,.57,.50,.46,.68}};
    static int period(double seconds) {
        double hour = (seconds % 86400) / 3600;
        return hour < 6 || hour >= 21 ? 5 : (int)((hour - 6) / 3);
    }
    static double speed(double original, int period) {
        int category = original > 33 ? 0 : 1;
        double reference = original > 33 ? 33.333333333333336 : original > 22 ? 22.22222222222222
                : original > 10 ? 15.0 : 8.333333333333334;
        return original * SPEED_MPH[category][period] * .44704 / reference;
    }
    public static void apply(Network network, double endTime) {
        // Capture original values once: later events must not compound earlier factors.
        record Original(double speed, double capacity) {}
        var groups = new java.util.LinkedHashMap<Original, java.util.List<Link>>();
        for (Link link : network.getLinks().values()) {
            if (!link.getAllowedModes().contains("car")) continue;
            groups.computeIfAbsent(new Original(link.getFreespeed(), link.getCapacity()),
                    k -> new java.util.ArrayList<>()).add(link);
        }
        for (var group : groups.entrySet()) {
            double originalSpeed = group.getKey().speed(), originalCapacity = group.getKey().capacity();
            for (double time = 0; time <= endTime; time += 3 * 3600) {
                if (time % 86400 == 3 * 3600 || time % 86400 == 0 && time != 0) continue;
                int p = period(time);
                NetworkChangeEvent event = new NetworkChangeEvent(time);
                for (Link link : group.getValue()) event.addLink(link);
                event.setFreespeedChange(new NetworkChangeEvent.ChangeValue(
                        NetworkChangeEvent.ChangeType.ABSOLUTE_IN_SI_UNITS, speed(originalSpeed, p)));
                event.setFlowCapacityChange(new NetworkChangeEvent.ChangeValue(
                        NetworkChangeEvent.ChangeType.ABSOLUTE_IN_SI_UNITS,
                        originalCapacity / network.getCapacityPeriod() * CAPACITY[originalSpeed > 33 ? 0 : 1][p]));
                NetworkUtils.addNetworkChangeEvent(network, event);
            }
        }
    }
}

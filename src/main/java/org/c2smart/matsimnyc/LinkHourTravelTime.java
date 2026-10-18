package org.c2smart.matsimnyc;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.zip.GZIPInputStream;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.api.core.v01.population.Person;
import org.matsim.core.router.util.TravelTime;
import org.matsim.vehicles.Vehicle;

/**
 * Travel times of one iteration from ResearchMetrics' research/link-hours-K.csv.gz: per link and entry hour, total
 * traversal seconds / completed traversals, car, taxi and FHV pooled (the same field as experiments/l2seg/route_gap.py).
 * Link-hours without a completed traversal use the free-flow time length / freespeed(time). Hourly bins, unlike
 * MATSim's 15-minute TravelTimeCalculator; both sides of a gap use this same field, so the difference is consistent.
 */
public final class LinkHourTravelTime implements TravelTime {
    static final int HOURS = 32;
    private final float[][] seconds;   // by link index, hour; NaN = no data

    private LinkHourTravelTime(float[][] seconds) { this.seconds = seconds; }

    /** No observations at all: free-flow everywhere (for tests). */
    public static LinkHourTravelTime freeFlow() { return new LinkHourTravelTime(new float[0][]); }

    public static LinkHourTravelTime read(Path file, Network network) throws IOException {
        int size = 0;
        for (Id<Link> id : network.getLinks().keySet()) size = Math.max(size, id.index() + 1);
        double[][] sum = new double[size][], count = new double[size][];
        try (var in = new BufferedReader(new InputStreamReader(new GZIPInputStream(Files.newInputStream(path(file))), StandardCharsets.UTF_8))) {
            String header = in.readLine();
            if (header == null || !header.startsWith("link_id,entry_hour,network_mode,entries,completed_traversals,total_traversal_seconds"))
                throw new IOException("unexpected header in " + file + ": " + header);
            for (String line; (line = in.readLine()) != null; ) {
                String[] f = line.split(",");
                Id<Link> id = Id.createLinkId(f[0].replace("\"", ""));
                if (!network.getLinks().containsKey(id)) continue;
                int hour = Integer.parseInt(f[1]);
                double done = Double.parseDouble(f[4]);
                if (hour < 0 || hour >= HOURS || done <= 0) continue;
                int i = id.index();
                if (sum[i] == null) { sum[i] = new double[HOURS]; count[i] = new double[HOURS]; }
                sum[i][hour] += Double.parseDouble(f[5]); count[i][hour] += done;
            }
        }
        float[][] s = new float[size][];
        for (int i = 0; i < size; i++) if (sum[i] != null) {
            s[i] = new float[HOURS]; Arrays.fill(s[i], Float.NaN);
            for (int h = 0; h < HOURS; h++) if (count[i][h] > 0) s[i][h] = (float) (sum[i][h] / count[i][h]);
        }
        return new LinkHourTravelTime(s);
    }

    private static Path path(Path file) { return file; }

    @Override public double getLinkTravelTime(Link link, double time, Person person, Vehicle vehicle) {
        int i = link.getId().index(), h = (int) Math.floor(time / 3600);
        if (i < seconds.length && seconds[i] != null && h >= 0 && h < HOURS && !Float.isNaN(seconds[i][h])) return seconds[i][h];
        return freeFlow(link, time);
    }

    static double freeFlow(Link link, double time) {
        return link.getLength() / link.getFreespeed(time);
    }
}

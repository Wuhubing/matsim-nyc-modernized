package org.c2smart.matsimnyc;

import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.population.HasPlansAndId;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.Plan;
import org.matsim.api.core.v01.population.Population;
import org.matsim.core.gbl.MatsimRandom;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.replanning.GenericPlanStrategy;
import org.matsim.core.replanning.ReplanningContext;
import org.matsim.core.replanning.ReplanningUtils;
import org.matsim.core.replanning.choosers.StrategyChooser;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.GZIPInputStream;

/** W3: innovation goes to chosen agents instead of a random 30%.
 *
 * On the first decision for a subpopulation in an iteration, the budget B = round(innovation weight share x
 * subpopulation size) is read from the weights MATSim passes in, so the 80% innovation switch-off still applies
 * (B = 0 afterwards, and for subpopulations such as "outside" that only select). The top round((1 - eps) B)
 * agents by priority are marked, plus the rest of B drawn uniformly from the unmarked. Marked agents choose
 * among innovative strategies, the others among selectors, each in configured proportions.
 *
 * Marking uses its own RNG (seed, iteration, subpopulation), so it never consumes MatsimRandom draws; the
 * strategy draw itself uses MatsimRandom like the default chooser. With eps = 1 every agent innovates with
 * probability B/N and then picks a strategy in the configured proportions, which is the default's distribution
 * up to the number of innovators being fixed at B instead of binomial. chooseStrategy is called sequentially
 * (GenericStrategyManagerImpl.run, MATSim 2026.0). */
public final class TargetedInnovationChooser implements StrategyChooser<Plan, Person> {
    /** Priority per person index for an iteration; NaN or missing ranks last. */
    public interface Priorities { double[] forIteration(int iteration); }

    private final Map<String, List<Id<Person>>> members = new LinkedHashMap<>();
    private final Priorities priorities;
    private final double epsilon;
    private final long seed;
    private final Set<String> prepared = new HashSet<>();
    private final Map<String, Integer> budgets = new TreeMap<>();
    private boolean[] marked = new boolean[0];
    private int iteration = -1;

    public TargetedInnovationChooser(Population population, Priorities priorities, double epsilon, long seed) {
        if (!(epsilon >= 0 && epsilon <= 1)) throw new IllegalArgumentException("epsilon must be in [0, 1]: " + epsilon);
        if (priorities == null && epsilon < 1) throw new IllegalArgumentException("a priority source is needed unless epsilon = 1");
        for (Person p : population.getPersons().values())
            members.computeIfAbsent(key(PopulationUtils.getSubpopulation(p)), k -> new ArrayList<>()).add(p.getId());
        this.priorities = priorities; this.epsilon = epsilon; this.seed = seed;
    }

    private static String key(String subpopulation) { return subpopulation == null ? "__none__" : subpopulation; }

    @Override public void beforeReplanning(ReplanningContext context) {
        iteration = context.getIteration();
        prepared.clear(); budgets.clear();
        int size = Id.getNumberOfIds(Person.class);
        if (marked.length < size) marked = new boolean[size]; else Arrays.fill(marked, false);
    }

    @Override public GenericPlanStrategy<Plan, Person> chooseStrategy(HasPlansAndId<Plan, Person> person, String subpopulation,
            ReplanningContext context, Weights<Plan, Person> weights) {
        String key = key(subpopulation);
        if (prepared.add(key)) mark(key, weights);
        boolean innovate = marked[person.getId().index()];
        double total = 0;
        for (int i = 0; i < weights.size(); i++) if (innovative(weights, i) == innovate) total += weights.getWeight(i);
        if (total <= 0) throw new IllegalStateException("no " + (innovate ? "innovative" : "selector") + " strategy with weight > 0 for subpopulation " + key);
        double rnd = MatsimRandom.getRandom().nextDouble() * total, sum = 0;
        GenericPlanStrategy<Plan, Person> last = null;
        for (int i = 0; i < weights.size(); i++) {
            if (innovative(weights, i) != innovate || weights.getWeight(i) <= 0) continue;
            sum += weights.getWeight(i); last = weights.getStrategy(i);
            if (rnd <= sum) return last;
        }
        return last;   // rounding at the upper end
    }

    private static boolean innovative(Weights<Plan, Person> weights, int i) { return !ReplanningUtils.isOnlySelector(weights.getStrategy(i)); }

    private void mark(String key, Weights<Plan, Person> weights) {
        double inno = 0;
        for (int i = 0; i < weights.size(); i++) if (innovative(weights, i)) inno += weights.getWeight(i);
        List<Id<Person>> group = members.getOrDefault(key, List.of());
        int budget = weights.getTotalWeights() > 0 ? (int) Math.round(inno / weights.getTotalWeights() * group.size()) : 0;
        budgets.put(key, budget);
        if (budget == 0) return;
        Random rng = new Random(Objects.hash(seed, iteration, key));
        List<Id<Person>> order = new ArrayList<>(group);
        Collections.shuffle(order, rng);   // random tie-breaking
        int ranked = (int) Math.round((1 - epsilon) * budget);
        if (ranked > 0) {
            double[] p = priorities.forIteration(iteration);
            order.sort(Comparator.comparingDouble((Id<Person> id) -> { int i = id.index(); double v = i < p.length ? p[i] : Double.NaN; return Double.isNaN(v) ? Double.NEGATIVE_INFINITY : v; }).reversed());
            for (Id<Person> id : order.subList(0, ranked)) marked[id.index()] = true;
        }
        List<Id<Person>> rest = new ArrayList<>(order.subList(ranked, order.size()));
        Collections.shuffle(rest, rng);
        for (Id<Person> id : rest.subList(0, budget - ranked)) marked[id.index()] = true;
    }

    /** Budget per subpopulation in the current iteration (only subpopulations seen so far). */
    public Map<String, Integer> budgets() { return Collections.unmodifiableMap(budgets); }
    public boolean marked(Id<Person> person) { int i = person.index(); return i < marked.length && marked[i]; }

    /** Priorities from CSV files with header "person_id,priority": a single file used in every iteration, or a
     * directory holding priority-ITERATION.csv(.gz) for each iteration that innovates (missing file = error). */
    public static Priorities fromFiles(Path path) {
        if (!Files.isDirectory(path)) { double[] fixed = read(path); return it -> fixed; }
        return it -> {
            for (String name : List.of("priority-" + it + ".csv.gz", "priority-" + it + ".csv"))
                if (Files.exists(path.resolve(name))) return read(path.resolve(name));
            throw new IllegalStateException("no priority file for iteration " + it + " in " + path);
        };
    }

    private static double[] read(Path file) {
        double[] p = new double[Id.getNumberOfIds(Person.class)];
        Arrays.fill(p, Double.NaN);
        try (InputStream raw = Files.newInputStream(file);
             BufferedReader r = new BufferedReader(new InputStreamReader(file.toString().endsWith(".gz") ? new GZIPInputStream(raw) : raw))) {
            String header = r.readLine();
            if (!"person_id,priority".equals(header)) throw new IllegalArgumentException(file + ": expected header person_id,priority, got " + header);
            for (String line; (line = r.readLine()) != null; ) {
                int c = line.lastIndexOf(',');
                int i = Id.createPersonId(line.substring(0, c)).index();
                if (i >= p.length) p = grow(p, i + 1);
                p[i] = Double.parseDouble(line.substring(c + 1));
            }
        } catch (IOException e) { throw new UncheckedIOException(e); }
        return p;
    }

    private static double[] grow(double[] p, int size) {
        int old = p.length; p = Arrays.copyOf(p, size); Arrays.fill(p, old, size, Double.NaN); return p;
    }
}

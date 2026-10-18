package org.c2smart.matsimnyc;

import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptorModule;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.zip.GZIPOutputStream;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.Plan;
import org.matsim.contrib.roadpricing.RoadPricingConfigGroup;
import org.matsim.contrib.roadpricing.RoadPricingModule;
import org.matsim.contrib.roadpricing.RoadPricingScheme;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.controler.AbstractModule;
import org.matsim.core.controler.ControlerDefaultsModule;
import org.matsim.core.controler.Injector;
import org.matsim.core.controler.NewControlerModule;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.population.algorithms.PermissibleModesCalculatorImpl;
import org.matsim.core.router.TripRouter;
import org.matsim.core.router.TripStructureUtils;
import org.matsim.core.scenario.ScenarioByInstanceModule;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.scoring.ScoringFunctionFactory;

/**
 * Offline equilibrium-gap estimator (QR3/06_G_estimator_design.md; research-charter-v2 section 3.1). Reads one
 * iteration of a finished reference run (its input config, the plans snapshot of iteration K and research/link-hours-K)
 * and, for a sample of residents, estimates with {@link PlanEstimator}:
 *   est_current  the selected (executed) plan;
 *   est_route    the same plan with every car/taxi/FHV trip re-routed on the iteration's travel times (route component);
 *   est_mode     the best single-subtour mode change, by SubtourModeChoice's rules (mode component).
 * Nothing is simulated. Output: one gzipped CSV row per sampled person.
 *
 *   java -cp runner.jar org.c2smart.matsimnyc.GapEstimator RUN_DIR K OUT.csv.gz [sample=0.05] [seed=1] [threads=8]
 *        [components=route,mode] [plans=FILE] [linkHours=FILE]
 */
public final class GapEstimator {
    private GapEstimator() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 3) throw new IllegalArgumentException("usage: RUN_DIR K OUT.csv.gz [key=value ...]");
        Path run = Path.of(args[0]).toAbsolutePath().normalize();
        int k = Integer.parseInt(args[1]);
        Path out = Path.of(args[2]).toAbsolutePath().normalize();
        double sample = 0.05; long seed = 1; int threads = 8;
        Set<String> components = Set.of("route", "mode");
        Path plans = null, linkHours = null, agents = null;
        for (int i = 3; i < args.length; i++) {
            String[] kv = args[i].split("=", 2);
            switch (kv[0]) {
                case "sample" -> sample = Double.parseDouble(kv[1]);
                case "seed" -> seed = Long.parseLong(kv[1]);
                case "threads" -> threads = Integer.parseInt(kv[1]);
                case "components" -> components = Set.of(kv[1].split(","));
                case "plans" -> plans = Path.of(kv[1]);
                case "linkHours" -> linkHours = Path.of(kv[1]);
                case "agents" -> agents = Path.of(kv[1]);
                default -> throw new IllegalArgumentException("unknown option " + kv[0]);
            }
        }
        Path sim = run.resolve("simulation");
        if (plans == null) {
            plans = sim.resolve("ITERS/it." + k + "/BUILT." + k + ".plans.xml.zst");
            if (!Files.isRegularFile(plans)) plans = sim.resolve("BUILT.output_plans.xml.zst");
        }
        if (linkHours == null) linkHours = sim.resolve("research/link-hours-" + k + ".csv.gz");
        if (agents == null && Files.isRegularFile(sim.resolve("replanning-log/agents-" + k + ".csv.gz"))) agents = sim.resolve("replanning-log/agents-" + k + ".csv.gz");
        for (Path p : List.of(run.resolve("config.xml"), plans, linkHours))
            if (!Files.isRegularFile(p)) throw new IllegalArgumentException("missing " + p);
        long t0 = System.currentTimeMillis();

        // --- scenario, as in RunNyc (same config handling and network adjustments), with the snapshot as population
        Path configPath = run.resolve("config.xml");
        Config config = ConfigUtils.loadConfig(configPath.toString(), new RoadPricingConfigGroup(), new NycModelConfig());
        NycModelConfig nyc = ConfigUtils.addOrGetModule(config, NycModelConfig.class);
        if (nyc.getPricing2025Links() != null) throw new IllegalArgumentException("pricing2025Links is not supported by the gap estimator");
        double[][] archiveFactors = null;
        if (nyc.getZipAligned()) {
            archiveFactors = ArchiveNetwork.readFactors(nyc.getArchiveCapacityFactors() == null ? null
                    : configPath.getParent().resolve(nyc.getArchiveCapacityFactors()).normalize());
            config.network().setTimeVariantNetwork(true);
        }
        if (nyc.getPublishedNetwork()) config.network().setTimeVariantNetwork(true);
        config.global().setRelativeToleranceForSampleSizeFactors(1.0);
        config.plans().setInputFile(plans.toString());
        config.routing().setRoutingRandomness(0.0);          // best response on the deterministic generalized cost
        Path tmp = Files.createTempDirectory(out.getParent(), "gap-tmp-");
        config.controller().setOutputDirectory(tmp.toString());
        config.controller().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.deleteDirectoryIfExists);
        Scenario scenario = ScenarioUtils.loadScenario(config);
        if (nyc.getPublishedNetwork()) PublishedNetwork.apply(scenario.getNetwork(), config.qsim().getEndTime().seconds());
        if (archiveFactors != null) ArchiveNetwork.apply(scenario.getNetwork(), config.qsim().getEndTime().seconds(), archiveFactors);
        LinkHourTravelTime travelTime = LinkHourTravelTime.read(linkHours, scenario.getNetwork());
        System.out.printf("loaded %,d persons, %,d links in %.0f s%n", scenario.getPopulation().getPersons().size(),
                scenario.getNetwork().getLinks().size(), (System.currentTimeMillis() - t0) / 1000.0);

        // --- injector: MATSim defaults plus the run's overrides; travel times of iteration K for the network modes
        RoadPricingConfigGroup pricingConfig = ConfigUtils.addOrGetModule(config, RoadPricingConfigGroup.class);
        RoadPricingScheme pricing = pricingConfig.getTollLinksFile() == null ? null : CarOnlyRoadPricing.load(scenario, pricingConfig.getTollLinksFile());
        Set<String> networkModes = new LinkedHashSet<>(config.routing().getNetworkModes());
        AbstractModule base = new AbstractModule() {
            @Override public void install() {
                install(new NewControlerModule()); install(PlanEstimator.coreListenersModule());
                
                install(new ControlerDefaultsModule());
                install(new ScenarioByInstanceModule(scenario));
            }
        };
        AbstractModule overrides = new AbstractModule() {
            @Override public void install() {
                install(new SwissRailRaptorModule());
                if (nyc.getRestoredCosts()) bindScoringFunctionFactory().to(NycScoring.class);
                if (pricing != null) install(new RoadPricingModule(pricing));
                for (String mode : networkModes) addTravelTimeBinding(mode).toInstance(travelTime);
            }
        };
        var injector = Injector.createInjector(config, AbstractModule.override(List.of(base), overrides));
        PlanEstimator.ensureVehicles(injector, scenario);
        ScoringFunctionFactory scoring = injector.getInstance(ScoringFunctionFactory.class);
        var routerProvider = injector.getProvider(TripRouter.class);
        PlanEstimator estimator = new PlanEstimator(scenario, travelTime, scoring, networkModes, nyc.getRestoredCosts(),
                nyc.getZipAligned(), pricing, config.qsim().getEndTime().seconds());
        var smc = config.subtourModeChoice();
        List<String> modes = Arrays.asList(smc.getModes());
        Set<String> chainBased = Set.of(smc.getChainBasedModes());
        var permissible = new PermissibleModesCalculatorImpl(config);

        // --- sample residents
        List<Person> persons = new ArrayList<>();
        for (Person p : scenario.getPopulation().getPersons().values()) {
            String sub = PopulationUtils.getSubpopulation(p);
            if (("man".equals(sub) || "nonman".equals(sub)) && keep(p.getId().toString(), seed, sample)) persons.add(p);
        }
        persons.sort((a, b) -> a.getId().toString().compareTo(b.getId().toString()));
        System.out.printf("sampled %,d residents (sample %.4f, seed %d); components %s; %d threads%n", persons.size(), sample, seed, components, threads);

        // --- parents of plans created in iteration K (replanning log), for V2: estimated vs realised gain of real switches
        java.util.Map<String, String> parents = new java.util.HashMap<>();
        if (agents != null) {
            try (var in = new java.io.BufferedReader(new java.io.InputStreamReader(new java.util.zip.GZIPInputStream(Files.newInputStream(agents)), StandardCharsets.UTF_8))) {
                String header = in.readLine();
                if (header == null || !header.startsWith("person,strategy,plan_id,plan_created,parent_plan_id")) throw new IOException("unexpected header in " + agents);
                for (String line; (line = in.readLine()) != null; ) {
                    String[] f = line.split(",", -1);
                    if (f[3].equals(Integer.toString(k)) && !f[4].isEmpty()) parents.put(f[0], f[4]);
                }
            }
            System.out.printf("replanning log: %,d plans created in iteration %d with a parent%n", parents.size(), k);
        }
        final int iteration = k;

        // --- estimate
        String[] rows = new String[persons.size()];
        AtomicInteger done = new AtomicInteger();
        // TripRouters are built one at a time: building one fills shared per-mode network caches, which is not thread-safe
        var routers = new java.util.concurrent.ArrayBlockingQueue<TripRouter>(threads);
        for (int i = 0; i < threads; i++) routers.add(routerProvider.get());
        final Set<String> comps = components;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        List<Future<?>> futures = new ArrayList<>();
        int chunk = 200;
        for (int start = 0; start < persons.size(); start += chunk) {
            final int s = start, e = Math.min(persons.size(), start + chunk);
            futures.add(pool.submit(() -> {
                TripRouter router = routers.take();
                try {
                for (int i = s; i < e; i++) {
                    try {
                        rows[i] = row(persons.get(i), estimator, router, comps, modes, chainBased, permissible, parents, iteration);
                    } catch (RuntimeException ex) {
                        rows[i] = String.format(Locale.ROOT, "\"%s\",%s,@K@,,,,,,,,,,,-1,\"%s\",,,,,%n", persons.get(i).getId(),
                                PopulationUtils.getSubpopulation(persons.get(i)), clean(ex.toString()));
                    }
                    int n = done.incrementAndGet();
                    if (n % 2000 == 0) System.out.printf("  %,d / %,d persons, %.0f s%n", n, persons.size(), (System.currentTimeMillis() - t0) / 1000.0);
                }
                } finally { routers.add(router); }
                return null;
            }));
        }
        try { for (var f : futures) f.get(); } finally { pool.shutdownNow(); }
        try (var w = new BufferedWriter(new OutputStreamWriter(new GZIPOutputStream(Files.newOutputStream(out)), StandardCharsets.UTF_8))) {
            w.write("person_id,subpopulation,iteration,trips,current_modes,stored_score,est_current,stuck_current,"
                    + "est_route,route_trips,est_mode,mode_choice,mode_candidates,failures,error,plan_id,plan_created,mutator,parent_id,est_parent\n");
            for (String r : rows) w.write(r.replace("@K@", Integer.toString(k)));
        }
        try (var walk = Files.walk(tmp)) { walk.sorted(java.util.Comparator.reverseOrder()).forEach(p -> p.toFile().delete()); }
        System.out.printf("wrote %s (%,d rows) in %.0f s%n", out, rows.length, (System.currentTimeMillis() - t0) / 1000.0);
    }

    static String attr(Plan p, String name) { Object v = p.getAttributes().getAttribute(name); return v == null ? "" : v.toString(); }

    static String clean(String s) { return s.replace("\"", "'").replace("\n", " ").replace(",", ";"); }

    /** Deterministic Bernoulli sample by person id. */
    static boolean keep(String id, long seed, double sample) {
        long h = id.hashCode() * 0x9E3779B97F4A7C15L ^ seed * 0xC2B2AE3D27D4EB4FL;
        h ^= h >>> 31; h *= 0xBF58476D1CE4E5B9L; h ^= h >>> 29;
        return (h >>> 11) * 0x1.0p-53 < sample;
    }

    private static String row(Person person, PlanEstimator est, TripRouter router, Set<String> comps, List<String> modes,
                              Set<String> chainBased, PermissibleModesCalculatorImpl permissible, java.util.Map<String, String> parents, int k) {
        Plan selected = person.getSelectedPlan();
        var trips = TripStructureUtils.getTrips(selected);
        List<String> current = new ArrayList<>();
        for (var t : trips) current.add(PlanEstimator.routingMode(t.getLegsOnly().getFirst()));
        int failures = 0;
        String error = null;
        var cur = est.estimate(person, PlanEstimator.copy(selected), Set.of(), router);
        failures += cur.failures(); if (cur.error() != null) error = cur.error();
        double route = Double.NaN; int routeTrips = 0;
        if (comps.contains("route")) {
            var network = est.networkTrips(selected);
            routeTrips = network.size();
            if (routeTrips == 0) route = cur.score();
            else {
                var r = est.estimate(person, PlanEstimator.copy(selected), new HashSet<>(network), router);
                route = r.score(); failures += r.failures(); if (r.error() != null) error = r.error();
            }
        }
        double mode = Double.NaN; String choice = ""; int candidates = 0;
        if (comps.contains("mode")) {
            mode = cur.score();
            var allowed = permissible.getPermissibleModes(selected);
            for (var subtour : TripStructureUtils.getSubtours(selected)) {
                List<Integer> idx = new ArrayList<>();
                for (var t : subtour.getTrips())
                    for (int i = 0; i < trips.size(); i++) if (trips.get(i).getOriginActivity() == t.getOriginActivity()) { idx.add(i); break; }
                Set<String> now = new HashSet<>();
                for (int i : idx) now.add(current.get(i));
                if (idx.isEmpty() || !modes.containsAll(now)) continue;
                for (String m : modes) {
                    if (!allowed.contains(m) || now.equals(Set.of(m))) continue;
                    if (chainBased.contains(m) && (!subtour.isClosed() || subtour.getParent() != null)) continue;
                    Plan c = PlanEstimator.copy(selected);
                    for (int i : idx) PlanEstimator.setTripMode(c, i, m);
                    var r = est.estimate(person, c, new HashSet<>(idx), router);
                    candidates++;
                    if (r.failures() > 0 || Double.isNaN(r.score())) { failures += Math.max(1, r.failures()); if (r.error() != null) error = r.error(); continue; }
                    if (r.score() > mode) { mode = r.score(); choice = m + ":" + idx.toString().replace(", ", "+").replace("[", "").replace("]", ""); }
                }
            }
        }
        Double stored = selected.getScore();
        String planId = attr(selected, "planId"), created = attr(selected, "iterationCreated"), mutator = attr(selected, "planMutator");
        String parentId = created.equals(Integer.toString(k)) ? parents.getOrDefault(person.getId().toString(), "") : "";
        double parentScore = Double.NaN;
        if (!parentId.isEmpty())
            for (Plan p : person.getPlans())
                if (p != selected && parentId.equals(attr(p, "planId"))) {
                    var r = est.estimate(person, PlanEstimator.copy(p), Set.of(), router);
                    parentScore = r.score(); break;
                }
        return String.format(Locale.ROOT, "\"%s\",%s,@K@,%d,%s,%s,%.6f,%b,%s,%d,%s,%s,%d,%d,\"%s\",%s,%s,%s,%s,%s%n",
                person.getId(), PopulationUtils.getSubpopulation(person), trips.size(), String.join("|", current),
                stored == null ? "" : String.format(Locale.ROOT, "%.6f", stored), cur.score(), cur.stuck(),
                Double.isNaN(route) ? "" : String.format(Locale.ROOT, "%.6f", route), routeTrips,
                Double.isNaN(mode) ? "" : String.format(Locale.ROOT, "%.6f", mode), choice, candidates, failures, error == null ? "" : clean(error),
                planId, created, mutator, parentId, Double.isNaN(parentScore) ? "" : String.format(Locale.ROOT, "%.6f", parentScore));
    }
}

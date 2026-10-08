package org.c2smart.matsimnyc;

import ch.sbb.matsim.routing.pt.raptor.SwissRailRaptorModule;
import org.matsim.api.core.v01.Scenario;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.controler.Controler;
import org.matsim.core.controler.AbstractModule;
import org.matsim.contrib.roadpricing.RoadPricingConfigGroup;
import org.matsim.contrib.roadpricing.RoadPricingModule;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.Plan;
import org.matsim.core.replanning.choosers.StrategyChooser;
import org.matsim.core.replanning.choosers.WeightedStrategyChooser;
import com.google.inject.TypeLiteral;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Minimal, portable entry point for the public C2SMART MATSim-NYC scenario.
 *
 * Usage:
 *   java -jar target/matsim-nyc-modernized-1.0.0.jar
 *   java -jar target/matsim-nyc-modernized-1.0.0.jar scenarios/nyc-zip-aligned/config-baseline.xml
 */
public final class RunNyc {
    private static final String DEFAULT_CONFIG = "scenarios/nyc-zip-aligned/config-baseline.xml";

    private RunNyc() {}

    public static void main(String[] args) {
        String configFile = args.length > 0 ? args[0] : DEFAULT_CONFIG;
        Path configPath = Path.of(configFile).toAbsolutePath().normalize();

        if (!Files.isRegularFile(configPath)) {
            throw new IllegalArgumentException("Config file not found: " + configPath);
        }

        System.out.println("Loading MATSim-NYC config: " + configPath);
        Config config = ConfigUtils.loadConfig(configPath.toString(), new RoadPricingConfigGroup(), new NycModelConfig());
        NycModelConfig nyc = ConfigUtils.addOrGetModule(config, NycModelConfig.class);
        double[][] archiveFactors=null;
        if(nyc.getZipAligned()) {
            if(nyc.getPublishedNetwork())throw new IllegalArgumentException("Choose ZIP or paper network adjustments, not both");
            if(!new java.util.HashSet<>(config.qsim().getMainModes()).equals(java.util.Set.of("car","taxi","FHV")))
                throw new IllegalArgumentException("ZIP requires QSim mainMode=car,FHV,taxi");
            archiveFactors=ArchiveNetwork.readFactors(nyc.getArchiveCapacityFactors()==null?null:configPath.getParent().resolve(nyc.getArchiveCapacityFactors()).normalize());
            config.network().setTimeVariantNetwork(true);
        }
        if (nyc.getPublishedNetwork()) config.network().setTimeVariantNetwork(true);
        // Preserve the released scenario's unequal flow (0.15), storage (0.30),
        // and counts (25) factors rather than silently recalibrating them.
        config.global().setRelativeToleranceForSampleSizeFactors(1.0);
        Scenario scenario = ScenarioUtils.loadScenario(config);
        if (nyc.getPublishedNetwork()) PublishedNetwork.apply(scenario.getNetwork(), config.qsim().getEndTime().seconds());
        if(archiveFactors!=null)ArchiveNetwork.apply(scenario.getNetwork(),config.qsim().getEndTime().seconds(),archiveFactors);

        System.out.printf(
                "Loaded scenario: %,d persons, %,d links, %,d transit lines%n",
                scenario.getPopulation().getPersons().size(),
                scenario.getNetwork().getLinks().size(),
                scenario.getTransitSchedule().getTransitLines().size()
        );

        Controler controler = new Controler(scenario);
        controler.addOverridingModule(new SwissRailRaptorModule());
        if (nyc.getRestoredCosts()) {
            LegacyCosts.validate(scenario);
            controler.addOverridingModule(new AbstractModule() {
                @Override public void install() {
                    addEventHandlerBinding().to(LegacyCosts.class).asEagerSingleton();
                    bindScoringFunctionFactory().to(NycScoring.class);
                    if(!nyc.getZipAligned()) {
                    bind(ch.sbb.matsim.routing.pt.raptor.IndividualRaptorParametersForPerson.class);
                    bind(ch.sbb.matsim.routing.pt.raptor.DefaultRaptorStopFinder.class);
                    bind(ch.sbb.matsim.routing.pt.raptor.OccupancyTracker.class).to(NycOccupancyTracker.class);
                    bind(ch.sbb.matsim.routing.pt.raptor.RaptorParametersForPerson.class).to(NycTransitRouting.class);
                    bind(ch.sbb.matsim.routing.pt.raptor.RaptorStopFinder.class).to(NycTransitRouting.StopFinder.class);
                    }
                }
            });
        }
        RoadPricingConfigGroup pricing = ConfigUtils.addOrGetModule(config, RoadPricingConfigGroup.class);
        if (nyc.getPricing2025Links() != null) {
            if (pricing.getTollLinksFile() != null) throw new IllegalArgumentException("Choose one pricing policy");
            controler.addOverridingModule(new Pricing2025(scenario, nyc.getPricing2025Links()).module());
        }
        if (pricing.getTollLinksFile() != null) {
            // Kept even when every toll is zero: the module also replaces the car travel disutility, and leaving it
            // out changes routes from iteration 0 (C3.2 check, job 25305770 vs 25218415).
            controler.addOverridingModule(new RoadPricingModule(
                    CarOnlyRoadPricing.load(scenario, pricing.getTollLinksFile())));
        }
        if (pricing.getTollLinksFile() != null || nyc.getPricing2025Links() != null) {
            PricingAudit audit = new PricingAudit(config.controller().getOutputDirectory());
            controler.addOverridingModule(new AbstractModule() {
                @Override public void install() {
                    addEventHandlerBinding().toInstance(audit);
                    addControllerListenerBinding().toInstance(audit);
                }
            });
        }
        if (Boolean.getBoolean("nyc.legacyTollRouting")) {
            if (!nyc.getRestoredCosts()) throw new IllegalArgumentException("nyc.legacyTollRouting needs restoredCosts");
            if (nyc.getPricing2025Links() != null || (pricing.getTollLinksFile() != null && !pricing.getTollLinksFile().endsWith("control-zero-tolls.xml")))
                throw new IllegalArgumentException("nyc.legacyTollRouting is only implemented for the baseline (zero road-pricing tolls)");
            controler.addOverridingModule(LegacyCosts.tollAwareRouting(scenario));
        }
        if (Boolean.getBoolean("nyc.onlineMetrics")) {
            String metricLinks = System.getProperty("nyc.metricLinks", nyc.getPricing2025Links());
            if (metricLinks == null) throw new IllegalArgumentException("nyc.onlineMetrics needs nyc.metricLinks or pricing2025Links");
            IterationMetrics metrics = new IterationMetrics(scenario, metricLinks, config.controller().getOutputDirectory());
            controler.addOverridingModule(new AbstractModule() {
                @Override public void install() {
                    addEventHandlerBinding().toInstance(metrics);
                    addControllerListenerBinding().toInstance(metrics);
                }
            });
        }
        if (Boolean.getBoolean("nyc.researchMetrics")) {
            String polygon = System.getProperty("nyc.cohortPolygon");
            if (polygon == null) throw new IllegalArgumentException("nyc.researchMetrics needs nyc.cohortPolygon");
            ResearchMetrics research = new ResearchMetrics(scenario, Path.of(config.controller().getOutputDirectory()), Path.of(polygon));
            controler.addOverridingModule(new AbstractModule() {
                @Override public void install() {
                    addEventHandlerBinding().toInstance(research);
                    addControllerListenerBinding().toInstance(research);
                }
            });
        }
        String priority = System.getProperty("nyc.targeted.priority"), epsilon = System.getProperty("nyc.targeted.epsilon");
        boolean targeted = priority != null || epsilon != null;
        if (Boolean.getBoolean("nyc.replanningLog") || targeted) {
            StrategyChooser<Plan, Person> delegate = targeted
                    ? new TargetedInnovationChooser(scenario.getPopulation(), priority == null ? null : TargetedInnovationChooser.fromFiles(Path.of(priority)),
                        Double.parseDouble(epsilon == null ? "0.1" : epsilon), config.global().getRandomSeed())
                    : new WeightedStrategyChooser<>();
            RecordingStrategyChooser chooser = new RecordingStrategyChooser(delegate);
            boolean log = Boolean.getBoolean("nyc.replanningLog");
            if (log) config.planInheritance().setEnabled(true);
            controler.addOverridingModule(new AbstractModule() {
                @Override public void install() {
                    bind(new TypeLiteral<StrategyChooser<Plan, Person>>() {}).toInstance(chooser);
                    if (log) addControllerListenerBinding().toInstance(new ReplanningLog(scenario.getPopulation(), chooser, config.controller().getOutputDirectory()));
                }
            });
        }
        controler.run();
    }
}

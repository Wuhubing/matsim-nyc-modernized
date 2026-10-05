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
        String fixedPlanGuard = System.getProperty("nyc.fixedPlanGuard");
        if (fixedPlanGuard != null) controler.addControlerListener(new FixedPlanGuard(scenario, fixedPlanGuard));
        if (Boolean.getBoolean("nyc.onlineMetrics")) {
            if (nyc.getPricing2025Links() == null) throw new IllegalArgumentException("nyc.onlineMetrics needs pricing2025Links");
            IterationMetrics metrics = new IterationMetrics(scenario, nyc.getPricing2025Links(), config.controller().getOutputDirectory());
            controler.addOverridingModule(new AbstractModule() {
                @Override public void install() {
                    addEventHandlerBinding().toInstance(metrics);
                    addControllerListenerBinding().toInstance(metrics);
                }
            });
        }
        String psim = System.getProperty("nyc.psim");
        if (psim != null) NycPSim.install(controler, scenario, psim, System.getProperty("nyc.psim.linkTime", "mean"));
        controler.run();
    }
}

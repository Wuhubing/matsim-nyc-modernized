package org.c2smart.matsimnyc;
import java.nio.file.*;
import org.matsim.contrib.roadpricing.RoadPricingConfigGroup;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.network.io.MatsimNetworkReader;
import org.matsim.core.population.io.PopulationReader;
import org.matsim.core.scenario.ScenarioUtils;

/** Offline: feed a recorded events file through IterationMetrics. Usage: CONFIG EVENTS ITERATION OUTDIR */
public class ReplayIterationMetrics {
 public static void main(String[] args) throws Exception {
  var config=ConfigUtils.loadConfig(args[0],new RoadPricingConfigGroup(),new NycModelConfig());
  var nyc=ConfigUtils.addOrGetModule(config,NycModelConfig.class);
  var s=ScenarioUtils.createScenario(config);
  new MatsimNetworkReader(s.getNetwork()).readFile(config.network().getInputFile());
  new PopulationReader(s).readFile(config.plans().getInputFile());
  Files.createDirectories(Path.of(args[3]));
  var metrics=new IterationMetrics(s,nyc.getPricing2025Links(),args[3]);
  var events=EventsUtils.createEventsManager();events.addHandler(metrics);
  events.initProcessing();EventsUtils.readEvents(events,args[1]);events.finishProcessing();
  metrics.notifyIterationEnds(new org.matsim.core.controler.events.IterationEndsEvent(null,Integer.parseInt(args[2]),false));
 }
}

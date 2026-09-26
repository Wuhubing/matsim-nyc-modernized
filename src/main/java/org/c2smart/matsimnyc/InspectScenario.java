package org.c2smart.matsimnyc;

import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.population.Person;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.scenario.ScenarioUtils;

import java.util.Map;
import java.util.TreeMap;

/** Loads the NYC scenario and prints basic diagnostics without starting iterations. */
public final class InspectScenario {
    private InspectScenario() {}

    public static void main(String[] args) {
        String configFile = args.length > 0 ? args[0] : "scenarios/nyc-zip-aligned/config-baseline.xml";
        Config config = ConfigUtils.loadConfig(configFile);
        Scenario scenario = ScenarioUtils.loadScenario(config);

        Map<String, Integer> subpops = new TreeMap<>();
        for (Person person : scenario.getPopulation().getPersons().values()) {
            Object value = person.getAttributes().getAttribute("subpopulation");
            String subpop = value == null ? "<missing>" : value.toString();
            subpops.merge(subpop, 1, Integer::sum);
        }

        System.out.printf("Persons: %,d%n", scenario.getPopulation().getPersons().size());
        System.out.printf("Nodes: %,d%n", scenario.getNetwork().getNodes().size());
        System.out.printf("Links: %,d%n", scenario.getNetwork().getLinks().size());
        System.out.printf("Transit lines: %,d%n", scenario.getTransitSchedule().getTransitLines().size());
        System.out.println("Subpopulations: " + subpops);
    }
}

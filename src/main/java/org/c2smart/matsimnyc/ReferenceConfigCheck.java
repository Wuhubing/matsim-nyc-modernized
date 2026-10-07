package org.c2smart.matsimnyc;

import org.matsim.contrib.roadpricing.RoadPricingConfigGroup;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;

/** Parses a generated run config with MATSim itself and checks the schedule the runner intended:
 *  java -cp runner.jar org.c2smart.matsimnyc.ReferenceConfigCheck CONFIG ITERATIONS INNOVATION_UNTIL EVENTS_INTERVAL PLANS_INTERVAL
 * INNOVATION_UNTIL = -1 means the historical fractionOfIterationsToDisableInnovation is kept (no disableAfterIteration). */
public final class ReferenceConfigCheck {
    private ReferenceConfigCheck() {}

    public static void main(String[] args) {
        Config c = ConfigUtils.loadConfig(args[0], new RoadPricingConfigGroup(), new NycModelConfig());
        int iterations = Integer.parseInt(args[1]), until = Integer.parseInt(args[2]);
        check(c.controller().getFirstIteration() == 0 && c.controller().getLastIteration() == iterations - 1, "iterations 0.." + (iterations - 1));
        check(c.controller().getWriteEventsInterval() == Integer.parseInt(args[3]), "writeEventsInterval " + args[3]);
        check(c.controller().getWritePlansInterval() == Integer.parseInt(args[4]), "writePlansInterval " + args[4]);
        int innovative = 0;
        for (var s : c.replanning().getStrategySettings()) {
            if (java.util.Set.of("SelectExpBeta", "ChangeExpBeta", "BestScore", "KeepLastSelected").contains(s.getStrategyName())) continue;
            innovative++;
            if (until >= 0) check(s.getDisableAfter() == until, s.getStrategyName() + " disableAfterIteration " + until + ", got " + s.getDisableAfter());
        }
        if (until >= 0) check(c.replanning().getFractionOfIterationsToDisableInnovation() == 1.0, "fraction 1.0 with an absolute cutoff");
        check(innovative > 0, "at least one innovation strategy");
        System.out.println("PASS: MATSim parses " + args[0] + ": " + iterations + " iterations, innovation "
                + (until >= 0 ? "until " + until : "fraction " + c.replanning().getFractionOfIterationsToDisableInnovation())
                + " (" + innovative + " strategies), events every " + args[3] + ", plans every " + args[4]);
    }

    private static void check(boolean ok, String what) { if (!ok) throw new IllegalStateException("config check failed: " + what); }
}

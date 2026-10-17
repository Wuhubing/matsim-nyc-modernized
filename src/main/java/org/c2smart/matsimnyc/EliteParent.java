package org.c2smart.matsimnyc;

import com.google.inject.Inject;
import com.google.inject.Provider;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.Plan;
import org.matsim.core.config.Config;
import org.matsim.core.config.groups.GlobalConfigGroup;
import org.matsim.core.config.groups.ScoringConfigGroup;
import org.matsim.core.config.groups.SubtourModeChoiceConfigGroup;
import org.matsim.core.config.groups.TimeAllocationMutatorConfigGroup;
import org.matsim.core.gbl.MatsimRandom;
import org.matsim.core.population.algorithms.MutateActivityTimeAllocation;
import org.matsim.core.population.algorithms.PermissibleModesCalculator;
import org.matsim.core.population.algorithms.PlanAlgorithm;
import org.matsim.core.replanning.PlanStrategy;
import org.matsim.core.replanning.PlanStrategyImpl;
import org.matsim.core.replanning.modules.AbstractMultithreadedModule;
import org.matsim.core.replanning.modules.ReRoute;
import org.matsim.core.replanning.modules.SubtourModeChoice;
import org.matsim.core.replanning.selectors.BestPlanSelector;
import org.matsim.core.replanning.selectors.ExpBetaPlanSelector;
import org.matsim.core.replanning.selectors.PlanSelector;
import org.matsim.core.router.TripRouter;
import org.matsim.core.utils.timing.TimeInterpretation;
import org.matsim.facilities.ActivityFacilities;

/**
 * RQ3 modification 1 (elite parent): the three innovation strategies copy a plan chosen by its stored score instead
 * of a uniformly random stored plan.
 *
 * MATSim 2026.0 builds ReRoute, TimeAllocationMutator and SubtourModeChoice with RandomPlanSelector
 * (strategies/ReRoute.java:45, TimeAllocationMutator.java:40, SubtourModeChoice.java:47). These providers are the
 * same strategies with a different parent selector; the modules are unchanged. Opt-in via system properties, so runs
 * without them are untouched:
 *
 *   -Dnyc.eliteParent=expbeta|best   parent selector: ExpBeta with beta (default scoring.brainExpBeta) or the best plan
 *   -Dnyc.eliteParent.beta=B         beta for expbeta
 *   -Dnyc.tamReRoute=true            the time mutator re-routes after mutating times (as MATSim's
 *                                    TimeAllocationMutator_ReRoute); also usable without nyc.eliteParent
 *
 * As in GenericPlanStrategyImpl, an unscored plan is still executed first; only the fallback selector changes.
 */
public final class EliteParent {
    public static final String REROUTE = "ReRouteElite";
    public static final String TIME = "TimeAllocationMutatorElite";
    public static final String MODE = "SubtourModeChoiceElite";

    private EliteParent() {}

    /** Mode from the system property, or null when the elite parent is off. */
    static String mode() {
        String m = System.getProperty("nyc.eliteParent");
        if (m == null || m.isBlank() || m.equals("off")) return null;
        if (!m.equals("expbeta") && !m.equals("best")) throw new IllegalArgumentException("nyc.eliteParent must be expbeta, best or off: " + m);
        return m;
    }

    static boolean tamReRoute() { return Boolean.getBoolean("nyc.tamReRoute"); }

    static PlanSelector<Plan, Person> selector(ScoringConfigGroup scoring) {
        String m = mode();
        if ("best".equals(m)) return new BestPlanSelector<>();
        String b = System.getProperty("nyc.eliteParent.beta");
        return new ExpBetaPlanSelector<>(b == null ? scoring.getBrainExpBeta() : Double.parseDouble(b));
    }

    /**
     * Renames the innovation strategies in the config. Returns the number of renamed settings; throws if a requested
     * change finds nothing to rename.
     */
    static int rename(Config config) {
        boolean elite = mode() != null, tam = tamReRoute();
        int n = 0;
        for (var s : config.replanning().getStrategySettings()) {
            String name = s.getStrategyName();
            if (elite && name.equals("ReRoute")) { s.setStrategyName(REROUTE); n++; }
            else if (elite && name.equals("SubtourModeChoice")) { s.setStrategyName(MODE); n++; }
            else if (name.equals("TimeAllocationMutator") && (elite || tam)) {
                s.setStrategyName(elite ? TIME : "TimeAllocationMutator_ReRoute"); n++;
            }
        }
        if ((elite || tam) && n == 0) throw new IllegalArgumentException("nyc.eliteParent / nyc.tamReRoute: no innovation strategy to replace");
        return n;
    }

    /** Same algorithm as MATSim's package-private TimeAllocationMutatorModule. */
    static final class TimeAllocationModule extends AbstractMultithreadedModule {
        private final TimeAllocationMutatorConfigGroup tam;

        TimeAllocationModule(TimeAllocationMutatorConfigGroup tam, GlobalConfigGroup global) {
            super(global);
            this.tam = tam;
        }

        @Override public PlanAlgorithm getPlanAlgoInstance() {
            return new MutateActivityTimeAllocation(tam.getMutationRange(), tam.isAffectingDuration(), MatsimRandom.getLocalInstance(),
                    tam.getLatestActivityEndTime(), tam.isMutateAroundInitialEndTimeOnly(), tam.getMutationRangeStep());
        }
    }

    public static final class ReRouteProvider implements Provider<PlanStrategy> {
        @Inject private GlobalConfigGroup global;
        @Inject private ScoringConfigGroup scoring;
        @Inject private ActivityFacilities facilities;
        @Inject private Provider<TripRouter> tripRouter;
        @Inject private TimeInterpretation time;

        @Override public PlanStrategy get() {
            PlanStrategyImpl.Builder b = new PlanStrategyImpl.Builder(selector(scoring));
            b.addStrategyModule(new ReRoute(facilities, tripRouter, global, time));
            return b.build();
        }
    }

    public static final class TimeProvider implements Provider<PlanStrategy> {
        @Inject private GlobalConfigGroup global;
        @Inject private ScoringConfigGroup scoring;
        @Inject private TimeAllocationMutatorConfigGroup tam;
        @Inject private ActivityFacilities facilities;
        @Inject private Provider<TripRouter> tripRouter;
        @Inject private TimeInterpretation time;

        @Override public PlanStrategy get() {
            PlanStrategyImpl.Builder b = new PlanStrategyImpl.Builder(selector(scoring));
            b.addStrategyModule(new TimeAllocationModule(tam, global));
            if (tamReRoute()) b.addStrategyModule(new ReRoute(facilities, tripRouter, global, time));
            return b.build();
        }
    }

    public static final class ModeProvider implements Provider<PlanStrategy> {
        @Inject private GlobalConfigGroup global;
        @Inject private ScoringConfigGroup scoring;
        @Inject private SubtourModeChoiceConfigGroup smc;
        @Inject private PermissibleModesCalculator permissible;
        @Inject private ActivityFacilities facilities;
        @Inject private Provider<TripRouter> tripRouter;
        @Inject private TimeInterpretation time;

        @Override public PlanStrategy get() {
            PlanStrategyImpl.Builder b = new PlanStrategyImpl.Builder(selector(scoring));
            b.addStrategyModule(new SubtourModeChoice(global, smc, permissible));
            b.addStrategyModule(new ReRoute(facilities, tripRouter, global, time));
            return b.build();
        }
    }
}

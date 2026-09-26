package org.c2smart.matsimnyc;

import java.util.ArrayList;
import java.util.Set;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.population.*;
import org.matsim.core.population.PopulationUtils;
import org.matsim.core.router.TripStructureUtils;
import org.matsim.core.scoring.*;
import org.matsim.core.scoring.functions.*;

/** Preserve archived access/egress/transfer coefficients after modern walk-mode unification. */
public final class NycScoring implements ScoringFunctionFactory {
    private final ScoringParametersForPerson parameters;
    private final Set<String> transitModes;
    private final boolean transitFare;
    @com.google.inject.Inject
    public NycScoring(ScoringParametersForPerson parameters, Scenario scenario) {
        this.parameters=parameters;
        this.transitModes=scenario.getConfig().transit().getTransitModes();
        this.transitFare=!org.matsim.core.config.ConfigUtils.addOrGetModule(scenario.getConfig(),NycModelConfig.class).getZipAligned();
    }
    @Override public ScoringFunction createNewScoringFunction(Person person) {
        var p=parameters.getScoringParameters(person);
        var sum=new SumScoringFunction();
        sum.addScoringFunction(new CharyparNagelActivityScoring(p));
        sum.addScoringFunction(new TransitWalkScoring(p,transitModes,transitFare));
        sum.addScoringFunction(new CharyparNagelMoneyScoring(p));
        sum.addScoringFunction(new CharyparNagelAgentStuckScoring(p));
        sum.addScoringFunction(new ScoreEventScoring());
        return sum;
    }
    static final class TransitWalkScoring extends CharyparNagelLegScoring {
        private final Set<String> transitModes;
        private final double moneyUtility;
        private final boolean transitFare;
        TransitWalkScoring(ScoringParameters p, Set<String> transitModes) {
            this(p,transitModes,true);
        }
        TransitWalkScoring(ScoringParameters p, Set<String> transitModes,boolean transitFare) {
            super(p,transitModes); this.transitModes=transitModes; this.moneyUtility=p.marginalUtilityOfMoney;
            this.transitFare=transitFare;
        }
        @Override public void handleTrip(TripStructureUtils.Trip trip) {
            var legs=trip.getLegsOnly();
            int first=-1,last=-1;
            for(int i=0;i<legs.size();i++) if(transitModes.contains(legs.get(i).getMode())) {
                if(first<0) first=i; last=i;
            }
            if(first<0) { super.handleTrip(trip); return; }
            var elements=new ArrayList<PlanElement>();
            // Synthetic boundaries also support incomplete trips reported at the cutoff.
            elements.add(PopulationUtils.createActivityFromCoord("Home",new org.matsim.api.core.v01.Coord(0,0)));
            int index=0;
            for(var element:trip.getTripElements()) {
                if(element instanceof Leg leg) {
                    var copy=PopulationUtils.createLeg(leg);
                    if(leg.getMode().equals("walk")) copy.setMode(index<first?"access_walk":index>last?"egress_walk":"transit_walk");
                    elements.add(copy); index++;
                } else elements.add(element);
            }
            elements.add(PopulationUtils.createActivityFromCoord("Work",new org.matsim.api.core.v01.Coord(0,0)));
            super.handleTrip(TripStructureUtils.getTrips(elements).getFirst());
            // Paper section 4.1.1: one fare per transit trip, not per transfer.
            // Supplied PT constants are before this fare (3.12598 / 0.907972).
            if(transitFare)score -= 2.75 * moneyUtility;
        }
    }
}

package org.c2smart.matsimnyc;

import ch.sbb.matsim.routing.pt.raptor.*;
import com.google.inject.Inject;
import org.matsim.api.core.v01.population.Person;
import org.matsim.core.scoring.functions.ScoringParametersForPerson;

/** Applies the released population-specific transit-walk coefficients in route search. */
public final class NycTransitRouting implements RaptorParametersForPerson {
    private final IndividualRaptorParametersForPerson delegate;
    private final ScoringParametersForPerson scoring;
    @Inject public NycTransitRouting(IndividualRaptorParametersForPerson delegate, ScoringParametersForPerson scoring) {
        this.delegate=delegate;this.scoring=scoring;
    }
    @Override public RaptorParameters getRaptorParameters(Person person) {
        var result=delegate.getRaptorParameters(person);
        var p=scoring.getScoringParameters(person);
        result.setMarginalUtilityOfTravelTime_utl_s("walk",
                p.modeParams.get("transit_walk").marginalUtilityOfTraveling_s-p.marginalUtilityOfPerforming_s);
        return result;
    }
    public static final class StopFinder implements RaptorStopFinder {
        private final DefaultRaptorStopFinder delegate;
        private final ScoringParametersForPerson scoring;
        @Inject public StopFinder(DefaultRaptorStopFinder delegate, ScoringParametersForPerson scoring) {
            this.delegate=delegate;this.scoring=scoring;
        }
        @Override public java.util.List<InitialStop> findStops(org.matsim.facilities.Facility from,
                org.matsim.facilities.Facility to, Person person, double time,
                org.matsim.utils.objectattributes.attributable.Attributes attributes,
                RaptorParameters parameters, SwissRailRaptorData data, Direction direction) {
            var p=scoring.getScoringParameters(person);
            double old=parameters.getMarginalUtilityOfTravelTime_utl_s("walk");
            parameters.setMarginalUtilityOfTravelTime_utl_s("walk",
                    p.modeParams.get(direction==Direction.ACCESS?"access_walk":"egress_walk").marginalUtilityOfTraveling_s
                            -p.marginalUtilityOfPerforming_s);
            try { return delegate.findStops(from,to,person,time,attributes,parameters,data,direction); }
            finally { parameters.setMarginalUtilityOfTravelTime_utl_s("walk",old); }
        }
    }
}

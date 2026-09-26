package org.c2smart.matsimnyc;

import ch.sbb.matsim.routing.pt.raptor.*;
import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.events.PersonDepartureEvent;
import org.matsim.core.api.experimental.events.EventsManager;
import org.matsim.core.scoring.functions.ScoringParametersForPerson;

/** MATSim 2026's tracker requests scoring parameters for synthetic transit drivers,
 * which are not population members. They are not passengers and need no passenger record.
 */
public final class NycOccupancyTracker extends OccupancyTracker {
    private final Scenario scenario;
    @com.google.inject.Inject
    public NycOccupancyTracker(OccupancyData data, Scenario scenario,
            RaptorInVehicleCostCalculator calculator, EventsManager events, ScoringParametersForPerson parameters) {
        super(data,scenario,calculator,events,parameters); this.scenario=scenario;
    }
    @Override public void handleEvent(PersonDepartureEvent event) {
        if(scenario.getPopulation().getPersons().containsKey(event.getPersonId())) super.handleEvent(event);
    }
}

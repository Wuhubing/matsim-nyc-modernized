package org.c2smart.matsimnyc;

import java.util.ArrayList;
import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.events.*;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.events.EventsUtils;
import org.matsim.core.events.handler.BasicEventHandler;
import org.matsim.core.scenario.ScenarioUtils;
import org.matsim.core.scoring.SumScoringFunction;
import org.matsim.core.scoring.functions.ScoreEventScoring;

/** Missing diagnostic coverage only; never modifies the NYC population/configuration. */
public final class VerifyBaselineDiagnostics {
    public static void main(String[] args) {
        var config=ConfigUtils.createConfig();
        ConfigUtils.addOrGetModule(config,NycModelConfig.class).setZipAligned(true);
        var scenario=ScenarioUtils.createScenario(config);
        var person=scenario.getPopulation().getFactory().createPerson(Id.createPersonId("driver"));
        scenario.getPopulation().addPerson(person);
        var events=EventsUtils.createEventsManager();
        var observed=new ArrayList<PersonScoreEvent>();
        events.addHandler(new BasicEventHandler() {
            @Override public void handleEvent(Event e) { if(e instanceof PersonScoreEvent s) observed.add(s); }
        });
        var costs=new LegacyCosts(events,scenario);
        var vehicle=Id.createVehicleId("unrelated-vehicle-id");
        var link=Id.createLinkId("320888283_0");
        double[] times={21599,21600,35999,36000,57599,57600,71999,72000,86400,108000};
        double[] dollars={10.5,12.5,12.5,10.5,10.5,12.5,12.5,10.5,10.5,10.5};
        for(int i=0;i<times.length;i++) {
            costs.handleEvent(new VehicleEntersTrafficEvent(times[i],person.getId(),link,vehicle,"car",0));
            costs.handleEvent(new LinkLeaveEvent(times[i],vehicle,link));
            var e=observed.getLast();
            if(!e.getPersonId().equals(person.getId()) || !e.getKind().equals("nyc-legacy-facility-toll") || Math.abs(e.getAmount()+dollars[i]*LegacyCosts.MONEY_UTILITY)>1e-9)
                throw new AssertionError("ZIP fee attribution/boundary failure at "+times[i]);
            StringBuilder xml=new StringBuilder();e.writeAsXML(xml);
            for(String attribute:new String[]{"type=\"personScore\"","person=\"driver\"","kind=\"nyc-legacy-facility-toll\"","amount=\"-"})
                if(!xml.toString().contains(attribute))throw new AssertionError("Unobservable score attribute: "+attribute);
            costs.handleEvent(new VehicleLeavesTrafficEvent(times[i],person.getId(),link,vehicle,"car",1));
            int size=observed.size();costs.handleEvent(new LinkLeaveEvent(times[i]+1,vehicle,link));
            if(observed.size()!=size)throw new AssertionError("Vehicle exit leaked mapping");
        }
        var sum=new SumScoringFunction();sum.addScoringFunction(new ScoreEventScoring());
        double expected=0;
        for(var e:observed){sum.addScore(e.getAmount());expected+=e.getAmount();}
        if(Math.abs(sum.getScore()-expected)>1e-9)throw new AssertionError("Score component failed");
        costs.handleEvent(new VehicleEntersTrafficEvent(0,person.getId(),link,vehicle,"car",0));
        costs.reset(1);int before=observed.size();costs.handleEvent(new LinkLeaveEvent(1,vehicle,link));
        if(observed.size()!=before)throw new AssertionError("Iteration reset leaked mapping");
        System.out.println("PASS: ZIP historical toll peak boundaries, after-midnight rule, exit/reset clearing, observable person/type/kind/amount, additive score component. Not full old/new engine equivalence.");
    }
}

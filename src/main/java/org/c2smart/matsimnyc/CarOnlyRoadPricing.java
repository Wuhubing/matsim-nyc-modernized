package org.c2smart.matsimnyc;

import org.matsim.api.core.v01.Scenario;
import org.matsim.contrib.roadpricing.*;
import org.matsim.core.config.ConfigGroup;
import org.matsim.vehicles.Vehicle;

/** Additional Schema 1 cordon charge for private cars, not taxi/FHV/transit. */
public final class CarOnlyRoadPricing {
    private CarOnlyRoadPricing() {}

    public static RoadPricingScheme load(Scenario scenario, String filename) {
        RoadPricingSchemeImpl base = RoadPricingUtils.addOrGetMutableRoadPricingScheme(scenario);
        new RoadPricingReaderXMLv1(base).parse(
                ConfigGroup.getInputFileURL(scenario.getConfig().getContext(), filename));
        if (!RoadPricingScheme.TOLL_TYPE_LINK.equals(base.getType())) {
            throw new IllegalArgumentException("Use link tolls on directed cordon crossings, not an area toll");
        }
        for (var id : base.getTolledLinkIds()) {
            var link = scenario.getNetwork().getLinks().get(id);
            if (link == null || !link.getAllowedModes().contains("car")) {
                throw new IllegalArgumentException("Invalid car toll link: " + id);
            }
        }
        System.out.println("Car-only pricing scheme: " + base.getName()
                + "; directed toll links: " + base.getTolledLinkIds().size());
        return new RoadPricingSchemeUsingTollFactor(base, (person, vehicle, link, time) -> {
            if (vehicle == null) {
                throw new IllegalArgumentException("A vehicle ID is required for charging");
            }
            Vehicle v = scenario.getVehicles().getVehicles().get(vehicle);
            if (v != null) return "car".equals(v.getType().getId().toString()) ? 1.0 : 0.0;
            if (scenario.getTransitVehicles().getVehicles().containsKey(vehicle)) return 0.0;
            throw new IllegalArgumentException("Cannot determine toll eligibility for vehicle " + vehicle);
        });
    }
}

package org.c2smart.matsimnyc;

import org.matsim.core.config.ReflectiveConfigGroup;

/** Explicit opt-in: historical runs retain their original behavior. */
public final class NycModelConfig extends ReflectiveConfigGroup {
    private boolean restoredCosts;
    private boolean publishedNetwork;
    private boolean zipAligned;
    private String archiveCapacityFactors;
    @StringGetter("zipAligned") public boolean getZipAligned() { return zipAligned; }
    @StringSetter("zipAligned") public void setZipAligned(boolean value) { zipAligned=value; }
    @StringGetter("archiveCapacityFactors") public String getArchiveCapacityFactors() { return archiveCapacityFactors; }
    @StringSetter("archiveCapacityFactors") public void setArchiveCapacityFactors(String value) { archiveCapacityFactors=value; }
    private String pricing2025Links;
    @StringGetter("pricing2025Links") public String getPricing2025Links() { return pricing2025Links; }
    @StringSetter("pricing2025Links") public void setPricing2025Links(String value) { pricing2025Links = value; }

    public NycModelConfig() { super("nycModel"); }
    @StringGetter("restoredCosts") public boolean getRestoredCosts() { return restoredCosts; }
    @StringSetter("restoredCosts") public void setRestoredCosts(boolean value) { restoredCosts = value; }
    @StringGetter("publishedNetwork") public boolean getPublishedNetwork() { return publishedNetwork; }
    @StringSetter("publishedNetwork") public void setPublishedNetwork(boolean value) { publishedNetwork = value; }
}

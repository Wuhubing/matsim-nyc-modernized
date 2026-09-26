package org.c2smart.matsimnyc;

import org.matsim.api.core.v01.events.PersonMoneyEvent;
import org.matsim.api.core.v01.events.handler.PersonMoneyEventHandler;
import org.matsim.core.controler.events.IterationEndsEvent;
import org.matsim.core.controler.listener.IterationEndsListener;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/** Audit actual monetary events, in simulated dollars (no population expansion). */
public final class PricingAudit implements PersonMoneyEventHandler, IterationEndsListener {
    private final Path file;
    private long payments;
    private double revenue;
    private long creditEvents;
    private double credits;
    private final Set<String> payers = new HashSet<>();

    public PricingAudit(String outputDirectory) {
        file = Path.of(outputDirectory, "pricing-audit.csv");
    }

    @Override public synchronized void reset(int iteration) {
        payments = 0;
        revenue = 0;
        payers.clear();
        creditEvents=0; credits=0;
    }

    @Override public synchronized void handleEvent(PersonMoneyEvent event) {
        if ("toll".equals(event.getPurpose()) && event.getAmount() < 0) {
            payments++;
            revenue -= event.getAmount();
            payers.add(event.getPersonId().toString());
        }
        if ("toll".equals(event.getPurpose()) && event.getAmount()>0) {
            creditEvents++; credits+=event.getAmount(); revenue-=event.getAmount();
        }
    }

    @Override public synchronized void notifyIterationEnds(IterationEndsEvent event) {
        try {
            if (!Files.exists(file)) {
                Files.writeString(file, "iteration,payment_events,unique_payers,sample_revenue_usd,credit_events,credit_usd\n",
                        StandardOpenOption.CREATE_NEW);
            }
            Files.writeString(file, String.format(Locale.ROOT, "%d,%d,%d,%.2f,%d,%.2f%n",
                    event.getIteration(), payments, payers.size(), revenue, creditEvents, credits), StandardOpenOption.APPEND);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}

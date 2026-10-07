package org.c2smart.matsimnyc;

import org.matsim.api.core.v01.Id;
import org.matsim.api.core.v01.population.HasPlansAndId;
import org.matsim.api.core.v01.population.Person;
import org.matsim.api.core.v01.population.Plan;
import org.matsim.core.replanning.GenericPlanStrategy;
import org.matsim.core.replanning.ReplanningContext;
import org.matsim.core.replanning.ReplanningUtils;
import org.matsim.core.replanning.choosers.StrategyChooser;

import java.util.*;

/** W2: delegates every decision to another chooser (by default MATSim's WeightedStrategyChooser) and records,
 * per person index, which strategy was chosen in the current iteration. It draws no random numbers itself, so
 * the delegate sees exactly the draws it would see without recording. chooseStrategy is called sequentially
 * (GenericStrategyManagerImpl.run, MATSim 2026.0), so the unsynchronised state is safe. */
public final class RecordingStrategyChooser implements StrategyChooser<Plan, Person> {
    public static final short NONE = -1;
    private final StrategyChooser<Plan, Person> delegate;
    private final Map<GenericPlanStrategy<Plan, Person>, Short> codes = new IdentityHashMap<>();
    private final List<String> names = new ArrayList<>();
    private final List<Boolean> innovative = new ArrayList<>();
    private short[] chosen = new short[0];
    private int iteration = -1;

    public RecordingStrategyChooser(StrategyChooser<Plan, Person> delegate) { this.delegate = delegate; }

    @Override public void beforeReplanning(ReplanningContext context) {
        iteration = context.getIteration();
        int size = Id.getNumberOfIds(Person.class);
        if (chosen.length < size) chosen = new short[size];
        Arrays.fill(chosen, NONE);
        delegate.beforeReplanning(context);
    }

    @Override public GenericPlanStrategy<Plan, Person> chooseStrategy(HasPlansAndId<Plan, Person> person, String subpopulation,
            ReplanningContext context, Weights<Plan, Person> weights) {
        GenericPlanStrategy<Plan, Person> strategy = delegate.chooseStrategy(person, subpopulation, context, weights);
        if (strategy != null) chosen[person.getId().index()] = code(strategy);
        return strategy;
    }

    private short code(GenericPlanStrategy<Plan, Person> strategy) {
        return codes.computeIfAbsent(strategy, s -> {
            names.add(s.toString());
            innovative.add(ReplanningUtils.isInnovativeStrategy(s));
            return (short) (names.size() - 1);
        });
    }

    /** Iteration of the last replanning, or -1 before the first one. */
    public int iteration() { return iteration; }
    /** Strategy code chosen for the person in the last replanning, or {@link #NONE}. */
    public short strategy(Id<Person> person) { int i = person.index(); return i < chosen.length ? chosen[i] : NONE; }
    public List<String> names() { return Collections.unmodifiableList(names); }
    public boolean innovative(short code) { return code >= 0 && innovative.get(code); }
}

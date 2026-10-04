import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.contrib.roadpricing.RoadPricingConfigGroup;
import org.c2smart.matsimnyc.NycModelConfig;

/** Parse the actual MATSim configuration before spending scenario runtime. */
public final class VerifyConfig {
    public static void main(String[] args) {
        for (String arg : args) {
            // "online:" marks an arm whose per-iteration metrics come from IterationMetrics instead of event files.
            boolean online = arg.startsWith("online:");
            String path = online ? arg.substring(7) : arg;
            Config config = ConfigUtils.loadConfig(path, new RoadPricingConfigGroup(), new NycModelConfig());
            if (config.qsim().getNumberOfThreads() != 16 && config.qsim().getNumberOfThreads() != 10)
                throw new AssertionError("Unexpected QSim threads");
            if (config.global().getNumberOfThreads() != 16 || config.global().getRandomSeed() != 4711)
                throw new AssertionError("Baseline changed");
            if (config.controller().getWriteEventsInterval() != (online ? 0 : 1))
                throw new AssertionError("All event iterations are required");
            if (!config.transit().isUseTransit()) throw new AssertionError("Transit required");
            System.out.println("CONFIG_OK " + path);
        }
    }
}

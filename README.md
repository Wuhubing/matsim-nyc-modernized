# MATSim NYC: modernized exploratory congestion-pricing scenarios

A Java 25 / MATSim 2026.0 modernization of C2SMART's released NYC model, with a baseline, reconstructed Schema 1 cordon, and a modeled launch-2025 congestion-pricing policy. This is an independent research workspace, not an official MTA model or a validated forecast of 2025 outcomes.

## Included

- Java source, Maven build, and synthetic regression checks.
- Compressed network, migrated synthetic population (389,301 agents), transit schedule/vehicles, mode vehicle types, and traffic counts: approximately 45 MB total repository size.
- Common model settings and the three policy scenarios, cordon geometry/link lists, and explicit capacity assumptions.
- Portable experiment launcher and event-analysis utility.

Raw simulation outputs, JDK/Maven installations, dependency caches, and compiled jars are excluded. The separate 10.9 GB population CSV is not required for these supplied simulation inputs.

## Setup

Install **JDK 25**, **Maven 3.9+**, and **Python 3.11+**. Put `java`, `javac`, and `mvn` on PATH, or set JAVA_HOME for the scripts. Downloads: [Java](https://adoptium.net/), [Maven](https://maven.apache.org/download.cgi), [Python](https://www.python.org/downloads/).

From the repository root:

```sh
mvn -DskipTests package
python scripts/verify.py
```

Maven downloads the pinned dependencies from Maven Central and the MATSim repository. A normal build uses no machine-specific dependency cache. Python's standard library suffices for the launcher; optional analysis packages install with `python -m pip install -r requirements.txt`.

## Run all three scenarios

```sh
python scripts/run_experiment.py --exploratory --iterations 1
```

This runs baseline, Schema 1, then 2025 policy sequentially, each for **iteration 0 only**, using a 16 GB Java heap. Allow additional system memory. Use `--heap 24g` if appropriate for your machine. Results, logs and completion-status files go into a unique `outputs/experiment-*` directory. Existing outputs are never overwritten. `--prepare-only` verifies input hashes and generates configs without launching a simulation. Increase `--iterations` to allow behavioral adaptation; one iteration is not convergence.

The baseline removes only the new congestion charge: historical facility tolls, parking and other fixed costs remain. All arms share the same input population, seed, road modes, scoring and capacity assumptions.

After a completed exploratory run, create the iteration-zero comparison chart and report:

```sh
python -m pip install -r requirements.txt
python scripts/compare.py outputs/experiment-YOUR-TIMESTAMP
```

The comparison tool currently measures iteration 0, even for longer experiments. It streams the three event files and reports common-boundary private-car crossings, completed car-leg times, congestion revenue and unfinished departures. It is intended for the exploratory profile; its labels explicitly describe the assumed capacity factors.

## Calibration boundary

The released ZIP hard-codes speed multipliers but loads capacity multipliers from external `theta_up_down{k}.csv` files not included in the release. No verified final capacity vector is available here. The strict no-argument Java runner therefore requires a separately supplied `scenarios/nyc-zip-aligned/capacity-factors.csv`.

`--exploratory` explicitly uses `assumptions/paper-capacity-factors.csv`: published-table values previously reconstructed for this workspace. Applying those values at the archive's 00/07/10/13/16/19/22 network-change times is a hybrid assumption, **not exact reproduction of the ZIP's calibration**. Alternatively provide a verified vector with `--capacity-factors PATH`; CSV header is `period,expressway,arterial` followed by six positive finite factor rows indexed 0..5.

The modernized profile restores QSim road simulation for car, taxi and FHV, archived speed multipliers and scoring coefficients. It does not add the previously inferred extra PT fare. Modern transit-walk compatibility and safer driver attribution remain deliberate changes. Engine versions differ; exact old-engine equivalence is not claimed.

## Pricing scope and limits

Schema 1 charges private cars on reconstructed entry and exit links ($9.18 in 06–10/14–20 peaks, $3.06 otherwise). The 2025 implementation models weekday E-ZPass charges ($9 first daily entry in 05–21, $2.25 overnight), selected tunnel credits, and participating taxi/FHV per-trip charges ($0.75/$1.50). Historical demand and transit inputs are not updated to 2025.

No explicit empty taxi fleet circulation is modeled. Truck, motorcycle, mail-payment, weekend, low-income and special-exemption categories are not comprehensively represented. Route-search toll costs approximate daily caps/credits even though realized billing is stateful. Zone mapping on the historical network is approximate. See source and [provenance](PROVENANCE.md) before interpreting outcomes.

## Example, not validation

![Exploratory iteration-zero comparison](docs/iteration0-comparison.png)

The chart is from three completed September 26, 2026 exploratory runs. It is retained as a small illustrative artifact; raw outputs are excluded. [Underlying metrics](docs/iteration0-comparison.json). Differences in cordon traffic are initial model responses, not observed 2025 effects. Mode-share adaptation needs further iterations; unfinished trips and geographic aggregation limit interpretation.

## Attribution

Based on [C2SMART Center, Code for MATSim-NYC project (2022), DOI 10.5281/zenodo.7430184](https://doi.org/10.5281/zenodo.7430184) and [the MATSim-NYC paper](https://arxiv.org/abs/2008.04762). Preserve upstream attribution and the supplied [GPL-3.0 license](LICENSE). Source data and boundary provenance are described separately in [PROVENANCE.md](PROVENANCE.md).

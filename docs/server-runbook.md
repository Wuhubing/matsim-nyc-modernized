# Server runbook: building, checking and running long MATSim-NYC references

This runbook takes a fresh Linux server to a running 100-iteration reference. Everything it needs is in this
repository; nothing depends on files from the original workstation.

**Why this run comes next.** Every result so far uses 12 iterations, and at iteration 8 the average score is
still rising by about 0.8 per iteration. Before judging any acceleration method we need to know how many
iterations this model needs to settle, what the settled state looks like, and how much the seeds differ there.

## 1. Server requirements

| Resource | Minimum | Comfortable |
|---|---|---|
| CPU | 16 cores, high single-core clock | 32–64 cores (to run several references at once) |
| Memory | 32 GB (one run: 16 GB Java heap, ≈ 17 GB peak) | 64 GB for 2 parallel runs, 128 GB+ for 3–6 |
| Disk | 100 GB free SSD | 500 GB+ if you write event files |
| OS | Linux (tested commands below are for Ubuntu 22.04/24.04) | |

Single-core speed matters more than core count for one run: the events thread is single-threaded and the
traffic simulation synchronises with it every simulated second. Extra cores pay off by running several
references in parallel.

## On an HPC cluster with Slurm (e.g. MIT ORCD)

Do not run simulations on the login node: build and prepare there, then submit runs to compute nodes.

```sh
# on the login node, once
git clone -b perf/simulation-redundancy https://github.com/Wuhubing/matsim-nyc-modernized.git
cd matsim-nyc-modernized
bash experiments/reference/setup_userspace.sh        # JDK 25 + Maven into ~/tools, no root needed
#   add the two printed export lines to ~/.bashrc, then: source ~/.bashrc
python3 --version                                    # needs 3.11+; otherwise load one with `module avail python`
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
mvn -DskipTests package
.venv/bin/python scripts/verify.py                   # quick synthetic checks; every line must say PASS
.venv/bin/python experiments/reference/run_reference.py inputs

# pick a partition and its time limit
sinfo -o "%P %l %c %m %a"

# reproduction check (12 iterations, compares with the recorded run at the end)
sbatch -p <partition> --time=01:00:00 --export=ALL,SEED=4711,ITERS=12 experiments/reference/reference.sbatch
# 100-iteration references, three seeds in parallel
sbatch -p <partition> --array=0-2 experiments/reference/reference.sbatch

squeue -u $USER                                      # job status
tail -f slurm-matsim-ref-*.out                       # job output; run.log is in each outputs/ directory
```

Each job asks for 16 CPUs, 24 GB and 8 hours; adjust `--time` to the partition limit and the measured
speed. Results are written under `outputs/` in the clone; keep the clone on storage that compute nodes
mount (home or project space), not on a mount that reports errors.

## 2. Install the toolchain (Ubuntu)

```sh
sudo apt update
sudo apt install -y git tmux zstd wget python3 python3-venv

# Java 25 (Eclipse Temurin)
wget -qO- https://packages.adoptium.net/artifactory/api/gpg/key/public | sudo gpg --dearmor -o /usr/share/keyrings/adoptium.gpg
echo "deb [signed-by=/usr/share/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(. /etc/os-release; echo $VERSION_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/adoptium.list
sudo apt update && sudo apt install -y temurin-25-jdk
java -version            # must report 25

# Maven 3.9 (the distribution package may be older)
wget https://archive.apache.org/dist/maven/maven-3/3.9.11/binaries/apache-maven-3.9.11-bin.tar.gz
sudo tar -xzf apache-maven-3.9.11-bin.tar.gz -C /opt
echo 'export PATH=/opt/apache-maven-3.9.11/bin:$PATH' >> ~/.bashrc && source ~/.bashrc
mvn -version             # must report 3.9.x and Java 25
```

If `temurin-25-jdk` is not available for your release, download the JDK 25 tarball from
[adoptium.net](https://adoptium.net/) and set `JAVA_HOME` to it.

## 3. Get the code and build

```sh
git clone -b perf/simulation-redundancy https://github.com/Wuhubing/matsim-nyc-modernized.git
cd matsim-nyc-modernized
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
mvn -DskipTests package                              # downloads dependencies on first build (a few minutes)
JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java)))) .venv/bin/python scripts/verify.py   # every line must say PASS
```

## 4. Prepare the inputs (once)

```sh
.venv/bin/python experiments/reference/run_reference.py inputs
```

This writes `outputs/reference-inputs/cold.xml.gz`: the selected plan of each of the 389,301 persons from
`scenarios/nyc/population-v6.xml.gz` (man 123,290 · nonman 205,808 · outside 60,203). It is byte-identical in
content to the input of all recorded runs. The capacity factors come from
`assumptions/archive-capacity-factors.csv` (the paper's Table 4 values at full precision).

## 5. Step 1: reproduce a recorded run (≈ 25–35 min)

Run the same 12-iteration, seed-4711 configuration that was recorded on the original workstation, then compare:

```sh
tmux new -s check
.venv/bin/python experiments/reference/run_reference.py run --seed 4711 --iterations 12 --out outputs/check-s4711-12it
.venv/bin/python experiments/reference/run_reference.py verify outputs/check-s4711-12it
```

`verify` compares all 12 iterations of online metrics and average scores with
`experiments/reference/expected-seed4711-12it.json`.

- **IDENTICAL**: the server reproduces the recorded results exactly; go on.
- **Differences**: write them down before continuing. MATSim is deterministic for a given seed and thread
  count, but a different CPU architecture can change the last digit of some `Math.exp`/`Math.log` results,
  which can change a plan choice and then grow. Small differences of that kind are not a bug; large or early
  ones (iteration 0) point to a setup problem (wrong input file, Java version, or config).

The run's `run.json` records wall time and peak memory; `summary.csv` holds per-iteration stage times. Use
the seconds per iteration measured here, not the workstation's, to plan the long runs.

## 6. Step 2: the 100-iteration reference (≈ 3.5–5 h per run, estimate)

Three seeds, same configuration, 100 iterations (new plans allowed until iteration 80, as in the paper):

```sh
tmux new -s s4711 '.venv/bin/python experiments/reference/run_reference.py run --seed 4711 --iterations 100 --plans-every 10 --out outputs/ref-s4711-100it; bash'
tmux new -s s4712 '.venv/bin/python experiments/reference/run_reference.py run --seed 4712 --iterations 100 --plans-every 10 --out outputs/ref-s4712-100it; bash'
tmux new -s s4713 '.venv/bin/python experiments/reference/run_reference.py run --seed 4713 --iterations 100 --plans-every 10 --out outputs/ref-s4713-100it; bash'
```

How many at once: each run uses 16 threads and ≈ 17 GB. Start one per 16 physical cores and per ≈ 20 GB of
free memory; otherwise start them one after another. Parallel runs slow each other down slightly, so if wall
time per run is the quantity being measured, run that one alone.

Options:
- `--events last` additionally writes event files for the last iteration(s) (≈ 1.1 GB each), useful for
  detailed analysis. The default writes none; all indicators are computed online.
- `--plans-every 10` keeps the plans every 10 iterations (≈ 0.4 GB each) to study how plans evolve.
- `--threads` and `--heap` change the run; keep the defaults (16, 16g) for anything compared with earlier runs.

## 7. Watching a run

```sh
tmux attach -t s4711                                   # detach again with Ctrl-b d
grep -c "ITERATION .* ENDS" outputs/ref-s4711-100it/run.log     # iterations finished
tail -n 3 outputs/ref-s4711-100it/simulation/BUILT.scorestats.csv
free -h ; htop
```

If a run dies, `run.json` shows the exit code and `run.log` the Java error. Start a new run with a new
`--out` directory; the runner never overwrites an existing one.

## 8. After the runs

```sh
.venv/bin/python experiments/reference/run_reference.py summarize outputs/ref-s4711-100it   # writes summary.csv
```

`summary.csv` has, per iteration: average score, car and pt shares, unfinished persons, cordon entries,
not-boarded passengers, charge revenue and stage times. Copy results home with, for example:

```sh
rsync -av --include='*/' --include='summary.csv' --include='run.json' --include='*.csv' --include='iteration-metrics-*.json' \
  --exclude='*' server:matsim-nyc-modernized/outputs/ ./outputs-from-server/
```

What to read from them:

1. **Settling point**: the iteration after which score and indicators stop trending while new plans are still
   allowed (before iteration 80). That number sets the iteration budget for every later experiment.
2. **Seed spread at the settled state**: the tolerance any acceleration method has to meet.
3. **Calibration check**: MATSim writes `ITERS/it.N/BUILT.N.countscompare.txt` (simulated vs 2016 counts) at
   regular iterations. If the late-iteration bridge and tunnel volumes are within the paper's 5%, the archived
   capacity factors still hold on MATSim 2026; if not, recalibration becomes the next task (≈ 20 h estimated).
4. **Time per iteration over 100 iterations**: replaces every estimate in the current reports.

## 9. What comes after

| If the reference shows | Next step |
|---|---|
| Settles well before iteration 80 | Shorten runs to that length; test warm start and early stopping against the settled state |
| Still trending at 80 | Longer horizon (e.g. 150–200 iterations) before any comparison |
| Counts within 5% | Keep the archived calibration; move to policy experiments and adaptive policy sampling (L3) |
| Counts off by more than 5% | Re-run the capacity calibration (SPSA, 6 steps × 2 runs × 50 iterations) on the server |

## Notes

- `outputs/` is ignored by git. Results stay on the server until you copy them.
- The older campaign scripts (`experiments/performance`, `experiments/surrogate`) still work; their resource
  monitor now reads `/proc/meminfo` on Linux. They were written for one workstation and reference some files
  under `outputs/`, so prefer `run_reference.py` on a new machine.
- See `experiments/redundancy/README.md` and `experiments/surrogate/README.md` for what has been measured so far.

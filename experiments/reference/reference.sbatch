#!/bin/bash
# Slurm job for one MATSim-NYC reference run on a compute node.
#
#   Reproduction check (12 iterations, seed 4711):
#     sbatch --time=01:00:00 --export=ALL,SEED=4711,ITERS=12 experiments/reference/reference.sbatch
#   Same with detailed research records (ResearchMetrics, events every 10 iterations, audit at the end):
#     sbatch --time=01:30:00 --export=ALL,SEED=4711,ITERS=12,RESEARCH=1 experiments/reference/reference.sbatch
#   Extra runner options, e.g. the replanning log (W1): --export=ALL,SEED=4711,ITERS=12,RUN_ARGS=--replanning-log
#   100-iteration references for three seeds (one job per seed, run in parallel):
#     sbatch --array=0-2 experiments/reference/reference.sbatch      # tasks 0,1,2 -> seeds 4711,4712,4713
#
# Environment options: SEED, ITERS, OUT, PLANS_EVERY (10), RESEARCH (0), EVENTS_INTERVAL (runner default),
# INNOVATION_UNTIL (unset = historical fraction 0.8), HEAP (16g), JFR (0), EVENTS_THREADS (MATSim default 1),
# RUN_ARGS (passed through).
# Set the partition for your cluster with -p (see `sinfo`), on the command line or below.
#SBATCH --job-name=matsim-ref
#SBATCH --cpus-per-task=16
#SBATCH --mem=24G
#SBATCH --time=08:00:00
#SBATCH --signal=B:TERM@120
#SBATCH --output=slurm-%x-%A_%a.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/../..}"
SEEDS=(4711 4712 4713)
SEED=${SEED:-${SEEDS[${SLURM_ARRAY_TASK_ID:-0}]}}
ITERS=${ITERS:-100}
PLANS_EVERY=${PLANS_EVERY:-10}
OUT=${OUT:-outputs/ref-s${SEED}-${ITERS}it-job${SLURM_JOB_ID:-local}}
: "${JAVA_HOME:?set JAVA_HOME (see experiments/reference/setup_userspace.sh)}"
echo "host $(hostname)  cpus ${SLURM_CPUS_PER_TASK:-?}  seed $SEED  iterations $ITERS  out $OUT  research ${RESEARCH:-0}"
lscpu | grep -E "Model name|^CPU\(s\)" || true
args=(run --seed "$SEED" --iterations "$ITERS" --out "$OUT" --heap "${HEAP:-16g}"
      --plans-every "$(( ITERS < PLANS_EVERY ? ITERS - 1 : PLANS_EVERY ))")
if [[ "${RESEARCH:-0}" == 1 ]]; then args+=(--research); fi
if [[ -n "${EVENTS_INTERVAL:-}" ]]; then args+=(--events-interval "$EVENTS_INTERVAL"); fi
if [[ -n "${INNOVATION_UNTIL:-}" ]]; then args+=(--innovation-until "$INNOVATION_UNTIL"); fi
if [[ "${JFR:-0}" == 1 ]]; then args+=(--jfr); fi
if [[ -n "${EVENTS_THREADS:-}" ]]; then args+=(--events-threads "$EVENTS_THREADS"); fi
# The runner runs in the background so that Slurm's TERM (120 s before the limit) reaches it.
.venv/bin/python experiments/reference/run_reference.py "${args[@]}" ${RUN_ARGS:-} &
runner=$!
trap 'kill -TERM "$runner" 2>/dev/null || true; wait "$runner" || true; exit 143' TERM INT
wait "$runner"
if [ "$SEED" = 4711 ] && [ "$ITERS" = 12 ] && [ -z "${INNOVATION_UNTIL:-}" ]; then
  .venv/bin/python experiments/reference/run_reference.py verify "$OUT" || true
fi
if [[ "${RESEARCH:-0}" == 1 ]]; then
  .venv/bin/python experiments/reference/audit_research.py "$OUT"
fi

#!/bin/bash
# Slurm job for one MATSim-NYC reference run on a compute node.
#
#   Reproduction check (12 iterations, seed 4711):
#     sbatch --time=01:00:00 --export=ALL,SEED=4711,ITERS=12 experiments/reference/reference.sbatch
#   Extra runner options, e.g. the replanning log (W1): --export=ALL,SEED=4711,ITERS=12,RUN_ARGS=--replanning-log
#   100-iteration references for three seeds (one job per seed, run in parallel):
#     sbatch --array=0-2 experiments/reference/reference.sbatch      # tasks 0,1,2 -> seeds 4711,4712,4713
#
# Set the partition for your cluster with -p (see `sinfo`), on the command line or below.
#SBATCH --job-name=matsim-ref
#SBATCH --cpus-per-task=16
#SBATCH --mem=24G
#SBATCH --time=08:00:00
#SBATCH --output=slurm-%x-%A_%a.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/../..}"
SEEDS=(4711 4712 4713)
SEED=${SEED:-${SEEDS[${SLURM_ARRAY_TASK_ID:-0}]}}
ITERS=${ITERS:-100}
PLANS_EVERY=${PLANS_EVERY:-10}
OUT=${OUT:-outputs/ref-s${SEED}-${ITERS}it-job${SLURM_JOB_ID:-local}}
: "${JAVA_HOME:?set JAVA_HOME (see experiments/reference/setup_userspace.sh)}"
echo "host $(hostname)  cpus ${SLURM_CPUS_PER_TASK:-?}  seed $SEED  iterations $ITERS  out $OUT"
lscpu | grep -E "Model name|^CPU\(s\)" || true
.venv/bin/python experiments/reference/run_reference.py run --seed "$SEED" --iterations "$ITERS" \
  --plans-every "$(( ITERS < PLANS_EVERY ? ITERS - 1 : PLANS_EVERY ))" --out "$OUT" ${RUN_ARGS:-}
if [ "$SEED" = 4711 ] && [ "$ITERS" = 12 ]; then
  .venv/bin/python experiments/reference/run_reference.py verify "$OUT" || true
fi

#!/bin/bash
#SBATCH --job-name=matsim-baseline
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --signal=B:TERM@120
#SBATCH --output=slurm-%x-%A_%a.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
.venv/bin/python experiments/reference/release_baseline.py "$PWD" "${OUTPUT_ROOT:?}" --assert-only
export OUTPUT_ROOT="$OUTPUT_ROOT/baseline"
export SCENARIO=baseline ITERS=100 RESEARCH=1 EVENTS_INTERVAL=10 INNOVATION_UNTIL=79 HEAP=24g JFR=1 PLANS_EVERY=10
unset SEED PLANS
exec bash experiments/reference/reference.sbatch

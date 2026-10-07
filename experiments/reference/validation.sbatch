#!/bin/bash
#SBATCH --job-name=matsim-check
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --array=0-2
#SBATCH --signal=B:TERM@120
#SBATCH --output=slurm-%x-%A_%a.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
export SEED=4711 HEAP=24g PLANS_EVERY=10 INNOVATION_UNTIL=historical
case "$SLURM_ARRAY_TASK_ID" in
  0) export SCENARIO=actual2025 ITERS=12 RESEARCH=0 EVENTS_INTERVAL=0 JFR=0 ;;
  1) export SCENARIO=actual2025 ITERS=12 RESEARCH=1 EVENTS_INTERVAL=10 JFR=1 ;;
  2) export SCENARIO=baseline ITERS=2 RESEARCH=1 EVENTS_INTERVAL=1 JFR=1 ;;
  *) exit 2 ;;
esac
exec bash experiments/reference/reference.sbatch

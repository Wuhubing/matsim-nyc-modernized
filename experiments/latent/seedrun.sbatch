#!/bin/bash
# One short MATSim run for the seeding check (docs/converged-plan-plan.md, 6b), through the reference runner.
# Preempted runs are requeued, and MATSim refuses an existing output folder, so the folder named by OUT is cleared
# first; only folders under matsim-work/latent/seed-* are accepted.
#SBATCH -c 16
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --signal=B:TERM@120
set -euo pipefail
case "$OUT" in /orcd/scratch/orcd/006/weibingw/matsim-work/latent/seed-*) rm -rf "$OUT" ;; *) echo "unexpected OUT $OUT"; exit 1 ;; esac
cd "$HOME/matsim-work/mnm-rq3"
exec bash experiments/reference/reference.sbatch

#!/bin/bash
# Section 2 analysis of the nine original runs (docs/original-runs-analysis-plan.md).
# Copy this folder to ORCD, then from it:
#   sbatch -p mit_preemptable --requeue --array=0 s2.sbatch       # quick check: time + aggregate only
#   sbatch -p mit_preemptable --requeue --array=1-6 s2.sbatch     # persons and links per scenario
#   PY=... python s2_time_noise.py report OUT                     # tables (small, any node)
# Tasks: 0 time+aggregate, 1-3 persons (baseline, schema1, schema2), 4-6 links (same order).
#SBATCH --job-name=orig-s2
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=slurm-%x-%A_%a.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
PY=${PY:-$HOME/matsim-work/venv-latent/bin/python}
OUT=${OUT:-$PWD/out-s2}
SC=(baseline schema1 schema2)
T=${SLURM_ARRAY_TASK_ID:-0}
if [ "$T" -eq 0 ]; then
  $PY s2_time_noise.py time "$OUT"
  $PY s2_time_noise.py aggregate "$OUT"
elif [ "$T" -le 3 ]; then
  $PY s2_time_noise.py persons "$OUT" "${SC[$((T-1))]}"
else
  $PY s2_time_noise.py links "$OUT" "${SC[$((T-4))]}"
fi

#!/bin/bash
# Section 3 (individual behaviour over iterations) for the nine original runs.
#   sbatch -p mit_preemptable --requeue --array=0 s3.sbatch      # check on baseline 4711
#   sbatch -p mit_preemptable --requeue --array=1-8 s3.sbatch    # the rest
#   $PY s3_individual.py report out-s3
# Task t -> scenario (baseline, schema1, schema2)[t/3], seed (4711, 4712, 4713)[t%3].
#SBATCH --job-name=orig-s3
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --output=slurm-%x-%A_%a.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
PY=${PY:-$HOME/matsim-work/venv-latent/bin/python}
SC=(baseline schema1 schema2); SEEDS=(4711 4712 4713)
T=${SLURM_ARRAY_TASK_ID:-0}
$PY s3_individual.py run "${OUT:-$PWD/out-s3}" "${SC[$((T/3))]}" "${SEEDS[$((T%3))]}"

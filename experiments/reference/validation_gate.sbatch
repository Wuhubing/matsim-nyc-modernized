#!/bin/bash
#SBATCH --job-name=matsim-gate
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=slurm-%x-%j.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?}"
.venv/bin/python experiments/reference/release_baseline.py "$PWD" "${OUTPUT_ROOT:?}"

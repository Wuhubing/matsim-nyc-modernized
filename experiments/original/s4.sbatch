#!/bin/bash
# Original-runs analysis stages 2-3 (extract, reconcile, stability, policy, figures). One plain serial job, no array.
#   OUT=$HOME/matsim-work/original-analysis/out-s4-20261124 STAGE=extract sbatch s4.sbatch
# STAGE: extract | reconcile | stability | policy | figures | all (sequential, each stage skips finished outputs)
# Limits (user-approved ceiling): 1 job at a time, <=4 CPU, <=24 GiB, <=2 h per job. Re-entrant: --requeue safe,
# verified caches are reused, outputs are written atomically.
#SBATCH --job-name=orig-s4
#SBATCH --partition=mit_preemptable
#SBATCH --requeue
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --output=slurm-%x-%j.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")}"
PY=${PY:-/orcd/software/core/001/pkg/miniforge/25.11.0-0/bin/python}   # existing system module: numpy 2.3.5, pandas 2.3.3, matplotlib 3.10.8
OUT=${OUT:?set OUT}
STAGE=${STAGE:-all}
NPROC=${NPROC:-${SLURM_CPUS_PER_TASK:-4}}
mkdir -p "$OUT"
echo "job=${SLURM_JOB_ID:-local} stage=$STAGE node=$(hostname) cpus=$NPROC mem=${SLURM_MEM_PER_NODE:-?}MB restart=${SLURM_RESTART_COUNT:-0}"
$PY -I -c "import sys,numpy,pandas;print(sys.version.split()[0],numpy.__version__,pandas.__version__)"
export PYTHONPATH="$PWD"
$PY s4_common.py manifest "$OUT" "$STAGE"
run() { echo "== $* ($(date '+%F %T'))"; "$PY" "$@"; }
case "$STAGE" in
  extract)   run s4_extract.py all "$OUT" --nproc "$NPROC" ;;
  reconcile) run s4_reconcile.py "$OUT" ;;
  stability) run s5_stability.py "$OUT" ;;
  policy)    run s6_policy.py "$OUT" ;;
  figures)   run s4_figures.py "$OUT" ;;
  all)       run s4_extract.py all "$OUT" --nproc "$NPROC"
             run s4_reconcile.py "$OUT"
             run s5_stability.py "$OUT"
             run s6_policy.py "$OUT"
             run s4_figures.py "$OUT" ;;
  test-extract) run s4_extract.py run "$OUT" "${TEST_SC:-baseline}" "${TEST_SEED:-4711}" --iters "${TEST_ITERS:-0,1,50,79,80,98,99}" --nproc "$NPROC" ;;
  *) echo "unknown STAGE"; exit 2 ;;
esac
echo "finished $(date '+%F %T')"

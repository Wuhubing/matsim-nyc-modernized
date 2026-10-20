#!/bin/bash
# RQ3 offline analyses on completed reference runs. Reads existing outputs only; no simulation.
# Submit from experiments/rq3 of the matsim-nyc-modernized checkout (the .venv two levels up is used):
#   CHECK=o1|o2|o3|o4 SEED=4711 sbatch -p mit_preemptable --requeue o_analysis.sbatch
#   CHECK=stop sbatch -p mit_preemptable --requeue o_analysis.sbatch          (RQ1 baselines, three seeds)
#   CHECK=deltas ARGS="--baseline ... --policy ..." OUTNAME=name sbatch -p mit_preemptable --requeue o_analysis.sbatch
#   CHECK=planchange sbatch -p mit_preemptable --requeue --mem=24G --time=04:00:00 o_analysis.sbatch   (W1 vs W0, X1; 3 seeds)
#SBATCH --job-name=rq3-o
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=out/slurm-%x-%j.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
PY=${PY:-${SLURM_SUBMIT_DIR}/../../.venv/bin/python}
RQ1=/orcd/scratch/orcd/006/weibingw/matsim-work/rq1
RUN=$RQ1/baseline-s${SEED:-4711}-100it-rq1
mkdir -p out
echo "host $(hostname)  check $CHECK  seed ${SEED:-}"
$PY test_o_scripts.py
$PY test_new_scripts.py
$PY test_plan_change.py
case "$CHECK" in
  o1) $PY o1_elite_parent.py "$RUN" --out out/o1-s${SEED}.json --jobs 4 ;;
  o2) $PY o2_staleness.py "$RUN" --out out/o2-s${SEED}.json ;;
  o3) $PY o3_overshoot.py "$RUN" --out out/o3-s${SEED}.json --jobs 4 ;;
  o4) $PY o4_reroute_threshold.py "$RUN" --out out/o4-s${SEED}.json --jobs 4 ;;
  stop) $PY replay_stop.py 4711=$RQ1/baseline-s4711-100it-rq1 4712=$RQ1/baseline-s4712-100it-rq1 4713=$RQ1/baseline-s4713-100it-rq1 --out out/stop-rq1-baseline.json ;;
  deltas) $PY compute_deltas.py $ARGS --out out/deltas-${OUTNAME}.json ;;
  planchange) $PY plan_change.py --root /orcd/scratch/orcd/006/weibingw/matsim-work --out out/plan-change.json --jobs 4 ;;
  *) echo "unknown CHECK $CHECK"; exit 2 ;;
esac

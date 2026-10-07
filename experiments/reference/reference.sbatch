#!/bin/bash
#SBATCH --job-name=matsim-ref
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --signal=B:TERM@120
#SBATCH --output=slurm-%x-%A_%a.out
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from a prepared snapshot directory}"
SEEDS=(4711 4712 4713)
SEED=${SEED:-${SEEDS[${SLURM_ARRAY_TASK_ID:-0}]}}
ITERS=${ITERS:-100}
SCENARIO=${SCENARIO:-baseline}
RESEARCH=${RESEARCH:-1}
: "${JAVA_HOME:?source ~/matsim-work/java-maven-env.sh first}"
: "${OUTPUT_ROOT:?set OUTPUT_ROOT to a checked shared filesystem}"
OUT="$OUTPUT_ROOT/${SCENARIO}-s${SEED}-${ITERS}it-job${SLURM_JOB_ID}"
echo "host $(hostname) cpus ${SLURM_CPUS_PER_TASK} seed $SEED iterations $ITERS scenario $SCENARIO out $OUT"
args=(run --seed "$SEED" --iterations "$ITERS" --scenario "$SCENARIO" --out "$OUT"
      --threads "$SLURM_CPUS_PER_TASK" --heap "${HEAP:-24g}" --plans-every "${PLANS_EVERY:-10}"
      --events-interval "${EVENTS_INTERVAL:-10}" --min-free-gib "${MIN_FREE_GIB:-5}")
if [[ "$RESEARCH" == 1 ]]; then args+=(--research); fi
if [[ "${JFR:-1}" == 1 ]]; then args+=(--jfr); fi
# 'historical' is reserved for the unchanged 12-iteration reproducibility schedule.
if [[ "${INNOVATION_UNTIL:-79}" != historical ]]; then args+=(--innovation-until "${INNOVATION_UNTIL:-79}"); fi
if [[ -n "${PLANS:-}" ]]; then args+=(--plans "$PLANS"); fi
.venv/bin/python experiments/reference/run_reference.py "${args[@]}" &
runner=$!
trap 'kill -TERM "$runner" 2>/dev/null || true; wait "$runner" || true; exit 143' TERM INT
wait "$runner"
if [[ "$SCENARIO" == actual2025 && "$SEED" == 4711 && "$ITERS" == 12 && "${INNOVATION_UNTIL:-79}" == historical && -z "${PLANS:-}" ]]; then
    .venv/bin/python experiments/reference/run_reference.py verify "$OUT"
fi
if [[ "$RESEARCH" == 1 ]]; then
    .venv/bin/python experiments/reference/audit_research.py "$OUT"
fi

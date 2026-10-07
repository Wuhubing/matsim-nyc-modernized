#!/bin/bash
# Run from a versioned snapshot; SSH terminal is needed for Slurm connectivity.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
source "$HOME/matsim-work/java-maven-env.sh"
: "${JAVA_HOME:?}"
[[ -f snapshot.json ]] || { echo 'Use a prepared snapshot, not the working checkout.'; exit 1; }
output=$(cat output-root.txt)
phase=${1:-validation}
timeout 20 sinfo -p mit_normal -o '%P %l %a'
mkdir -p "$output"
df -hT "$output"
if command -v quota >/dev/null; then timeout 15 quota -s || true; fi
case "$phase" in
  auto)
    exec .venv/bin/python experiments/reference/auto_chain.py "$root"
    ;;
  validation)
    [[ ! -f validation-job-id.txt ]] || { echo 'Validation already submitted:'; cat validation-job-id.txt; exit 1; }
    mkdir -p "$output/validation"
    export OUTPUT_ROOT="$output/validation"
    job=$(sbatch --parsable -p mit_normal --export=ALL experiments/reference/validation.sbatch)
    printf '%s\n' "$job" > validation-job-id.txt
    echo "Validation array submitted: $job (plain/rich 12 iterations + baseline 2 iterations)"
    ;;
  baseline)
    [[ ! -f baseline-job-id.txt ]] || { echo 'Baseline already submitted:'; cat baseline-job-id.txt; exit 1; }
    .venv/bin/python experiments/reference/check_validation.py "$output/validation"
    .venv/bin/python - "$output/validation/validation-passed.json" <<'PYCODE'
import json,sys
report=json.load(open(sys.argv[1])); estimate=report['projected_100_iteration_hours_with_30pct_margin']
print('Projected 100 iterations with 30% margin (hours):',estimate)
if estimate is None or estimate>8:
    raise SystemExit('Review the batch time limit before submission; the measured estimate is missing or exceeds 8 hours.')
PYCODE
    mkdir -p "$output/baseline"
    export OUTPUT_ROOT="$output/baseline" SCENARIO=baseline ITERS=100 RESEARCH=1 EVENTS_INTERVAL=10
    export INNOVATION_UNTIL=79 HEAP=24g JFR=1 PLANS_EVERY=10
    unset SEED PLANS
    job=$(sbatch --parsable -p mit_normal --array=0-2 --export=ALL experiments/reference/reference.sbatch)
    printf '%s\n' "$job" > baseline-job-id.txt
    echo "Baseline array submitted: $job"
    ;;
  *) echo 'Usage: submit_research.sh [validation|baseline|auto]'; exit 2 ;;
esac

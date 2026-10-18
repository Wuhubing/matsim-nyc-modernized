#!/bin/bash
# Selection probes (plan: step 2): "what if innovation had been switched off at iteration k".
# From the plan snapshot of iteration k of a finished run, run 12 selection-only iterations with the original code
# (main checkout; with innovation off the elite parent never acts, so all arms are probed by the same code).
# Analysis: compute_deltas.py --window 2-11 on the probe directories, compared with the reference Delta (04 section 6).
#
#   probe_submit.sh LABEL "K1 K2 ..." BASELINE_RUN SCHEMA1_RUN SCHEMA2_RUN [--dry-run]
#   e.g. probe_submit.sh cold "80" $S/rq1/baseline-s4711-100it-rq1 $S/policy/schema1-s4711-100it $S/policy/schema2-s4711-100it
# Output: $S/rq3/probe-LABEL-SCENARIO-s4711-kK. Submit only when SCRATCH is below 85% (plan: verification).
set -u
LABEL=$1; KS=$2; shift 2
declare -A RUN=([baseline]=$1 [schema1]=$2 [schema2]=$3); DRY=${4:-}
S=/orcd/scratch/orcd/006/weibingw/matsim-work
Q=$(awk -F'|' '/SCRATCH/{gsub(/ /,"",$4); print $4}' ~/orcd/.quota)
awk -v q="$Q" 'BEGIN{exit !(q<85)}' || { echo "SCRATCH ${Q}% >= 85%: not submitting"; exit 1; }
source ~/matsim-work/java-maven-env.sh
cd ~/matsim-work/matsim-nyc-modernized
test -z "$(git status --porcelain --untracked-files=no)" || { echo "main checkout dirty"; exit 1; }
for K in $KS; do for SC in baseline schema1 schema2; do
  PL=${RUN[$SC]}/simulation/ITERS/it.$K/BUILT.$K.plans.xml.zst
  test -f "$PL" || { echo "missing $PL"; continue; }
  OUT=$S/rq3/probe-$LABEL-$SC-s4711-k$K
  if [ -e "$OUT" ]; then echo "exists $OUT"; continue; fi
  CMD=(sbatch -p mit_preemptable --time=02:30:00 --cpus-per-task=16 --mem=40G --job-name=probe-$LABEL-$SC-k$K --export=ALL experiments/reference/reference.sbatch)
  if [ "$DRY" = --dry-run ]; then echo "DRY: $SC k=$K plans=$PL out=$OUT"; continue; fi
  SEED=4711 ITERS=12 INNOVATION_UNTIL=0 EVENTS_INTERVAL=0 PLANS_EVERY=10 RESEARCH=1 HEAP=24g \
    RUN_ARGS="--scenario $SC --plans $PL" OUT=$OUT "${CMD[@]}"
done; done

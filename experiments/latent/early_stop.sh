#!/bin/bash
# Early-stop runs of docs/converged-plan-plan.md, 6e.2: seed 4712, 30 iterations (0-29), innovation until iteration 19,
# selection only in 20-29 (the original schedule scaled from 100 / 79). Toll = schema1 ($9.18), which has three
# 100-iteration seeds (policy/schema1-s47xx-100it). Five runs:
#   base-net    baseline from the network plan (net-1.xml.gz)
#   base-cold   baseline from the cold plans (control a)
#   toll-net    schema1 from the same network plan
#   toll-cold   schema1 from the cold plans (control a)
#   toll-warm   schema1 from the baseline seed-4712 100-iteration output plans (control b)
# Run on the login node: bash ~/matsim-work/latent/early_stop.sh
set -euo pipefail
L=/orcd/pool/007/weibingw/matsim-data/latent; W=/orcd/scratch/orcd/006/weibingw/matsim-work
STABLE=$W/rq1/baseline-s4712-100it-rq1/simulation/BUILT.output_plans.xml.zst
cd ~/matsim-work/mnm-rq3
submit() {
  sbatch --parsable -J es-$1 -p mit_normal,mit_preemptable --requeue --time=10:00:00 -o $L/logs/es-$1-%j.log \
    --export=ALL,JAVA_HOME=/home/weibingw/tools/jdk-25,SEED=4712,ITERS=30,RESEARCH=1,INNOVATION_UNTIL=19,HEAP=24g,OUT=$W/latent/seed-es-$1-s4712-30it,RUN_ARGS="$2" \
    ~/matsim-work/latent/seedrun.sbatch
}
submit base-net  "--scenario baseline --plans $L/seed/net-1.xml.gz"
submit base-cold "--scenario baseline"
submit toll-net  "--scenario schema1 --plans $L/seed/net-1.xml.gz"
submit toll-cold "--scenario schema1"
submit toll-warm "--scenario schema1 --plans $STABLE"

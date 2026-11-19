#!/bin/bash
# Backup for a mit_preemptable run: started only if PREV_JOB did not finish OK (afternotok).
# Keeps the partial output under a new name, then runs the same reference job here.
set -u
cd "$SLURM_SUBMIT_DIR"
if [ -e "$OUT" ]; then mv -n "$OUT" "$OUT-preempted-$PREV_JOB" && echo "renamed partial $OUT -> $OUT-preempted-$PREV_JOB"; fi
exec bash experiments/reference/reference.sbatch

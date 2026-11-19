#!/bin/bash
# Move simulation/$SUB (ITERS or research; first argument, default ITERS) of completed MATSim runs from SCRATCH to POOL and leave a symlink at the old path.
# Nothing is deleted except source files rsync has already copied (--remove-source-files). Skips failed/partial runs.
set -u
SUB=${1:-ITERS}
S=/orcd/scratch/orcd/006/weibingw/matsim-work
DST=/orcd/pool/007/weibingw/matsim-work-iters  # kept for both kinds so the ITERS links stay valid
mkdir -p "$DST"
for RUN in "$S"/policy/* "$S"/rq1/* "$S"/rq3/*; do
  case "$RUN" in *failed*) echo "skip failed $RUN"; continue;; esac
  SRC="$RUN/simulation/$SUB"
  [ -d "$SRC" ] || continue
  [ -L "$SRC" ] && { echo "already moved $SRC"; continue; }
  # completed only: run.json state=completed
  python3 -c "import json,sys; m=json.load(open('$RUN/run.json')); sys.exit(0 if m.get('state')=='completed' and m.get('exit_code')==0 else 1)" 2>/dev/null \
    || { echo "skip not completed $RUN"; continue; }
  REL=${RUN#$S/}; T="$DST/$REL/$SUB"
  # after move_partial_iters.sh some it.N are already links into POOL: drop those links (data is already there)
  find "$SRC" -maxdepth 1 -type l -lname "$DST/*" -delete
  mkdir -p "$T"
  n0=$(find "$SRC" -type f | wc -l); b0=$(du -sb --apparent-size "$SRC" | cut -f1)
  rsync -a --remove-source-files "$SRC"/ "$T"/ || { echo "RSYNC FAILED $SRC"; continue; }
  n1=$(find "$T" -type f | wc -l); b1=$(du -sb --apparent-size "$T" | cut -f1)
  left=$(find "$SRC" -type f | wc -l)
  if [ "$n1" -ge "$n0" ] && [ "$left" -eq 0 ]; then
    find "$SRC" -depth -type d -empty -delete
    if [ ! -e "$SRC" ]; then ln -s "$T" "$SRC"; echo "moved $REL files=$n0/$n1 bytes=$b0/$b1"
    else echo "SOURCE NOT EMPTY $SRC"; fi
  else
    echo "VERIFY FAILED $REL files=$n0/$n1 left=$left"
  fi
done
echo "== quota after"; cat ~/orcd/.quota
echo MOVE DONE

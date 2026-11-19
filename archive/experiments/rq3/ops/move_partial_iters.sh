#!/bin/bash
# While runs are still going: move their finished plan snapshots ITERS/it.N to POOL and leave a link per it.N.
# Only snapshots at least 2 iterations behind the run's current iteration are touched (MATSim no longer writes them).
#   move_partial_iters.sh RUN_DIR [RUN_DIR ...]
set -u
S=/orcd/scratch/orcd/006/weibingw/matsim-work
DST=/orcd/pool/007/weibingw/matsim-work-iters
for RUN in "$@"; do
  SIM="$RUN/simulation"; [ -d "$SIM/ITERS" ] && [ ! -L "$SIM/ITERS" ] || continue
  cur=$(ls "$SIM"/iteration-metrics-*.json 2>/dev/null | wc -l)
  REL=${RUN#$S/}
  for D in "$SIM"/ITERS/it.*; do
    [ -L "$D" ] && continue
    n=${D##*/it.}; [ "$n" -le $((cur - 2)) ] || continue
    T="$DST/$REL/ITERS/it.$n"; mkdir -p "$T"
    n0=$(find "$D" -type f | wc -l)
    rsync -a --remove-source-files "$D"/ "$T"/ || { echo "RSYNC FAILED $D"; continue; }
    n1=$(find "$T" -type f | wc -l); left=$(find "$D" -type f | wc -l)
    if [ "$n1" -ge "$n0" ] && [ "$left" -eq 0 ]; then
      find "$D" -depth -type d -empty -delete; [ ! -e "$D" ] && ln -s "$T" "$D" && echo "moved $REL it.$n files=$n0"
    else echo "VERIFY FAILED $REL it.$n files=$n0/$n1 left=$left"; fi
  done
done
echo "== quota after"; cat ~/orcd/.quota
echo PARTIAL MOVE DONE

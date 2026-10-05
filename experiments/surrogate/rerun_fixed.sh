#!/bin/sh
# Recompute every analysis that used link traversal times after the parked-duration fix (2026-10-05).
set -e
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
FB=outputs/performance-20261004-171012-redundancy/full-baseline/simulation
echo "== oracle (mean/geo, end link) + baseline states 10/11"; $PY experiments/surrogate/oracle.py
echo "== noise floor"; $PY experiments/surrogate/noise_floor.py
echo "== persistence it10->it11"; $PY - <<'PYEOF'
import pickle,sys;sys.path.insert(0,'experiments/surrogate');import metrics as M
y10,l10=pickle.load(open('outputs/surrogate-analysis/baseline-state-10.pkl','rb'));y11,l11=pickle.load(open('outputs/surrogate-analysis/baseline-state-11.pkl','rb'))
print('persistence link', M.fmt(M.link_errors(y11,{k:v[0] for k,v in y10.items()},M.mean_time(y10))), '| agent', M.fmt(M.agent_errors(l11,l10)))
PYEOF
echo "== oracle bin 900"; $PY experiments/surrogate/oracle_bins.py 900
echo "== agent surrogate seed-4712-r2"; mkdir -p outputs/surrogate-analysis/seed4712r2
$PY experiments/surrogate/agent_surrogate.py outputs/surrogate-data-20261005/seed-4712-r2/simulation outputs/surrogate-analysis/seed4712r2 --iterations 1 2 3 4 5 6 --test 6 --network $FB/BUILT.output_network.xml.zst
echo DONE

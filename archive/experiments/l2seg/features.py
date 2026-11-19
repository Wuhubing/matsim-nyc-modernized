"""Per-agent features at the end of iteration t (plan Section 6.2), from the replanning log and, when the run
recorded them, ResearchMetrics (OUTPUT/simulation/research/).

Available now: plans in memory, executed minus best stored score, age of the selected plan, plan switches and
innovations in the last 5 iterations, executed-score change from t-1, subpopulation; with ResearchMetrics also
charging cohort, completed travel time and its change from t-1, choice/plan fingerprint changed.
Not yet available (need more logging): spread of stored scores, home and work zone, cordon crossing of any
stored plan, congestion on the selected plan's links, crowding on its transit runs."""
import csv, gzip
from pathlib import Path
import numpy as np

WINDOW = 5


def research_persons(run_dir, it, person_ids):
    path = Path(run_dir)/'simulation'/'research'/f'persons-{it}.csv.gz'
    if not path.exists(): return None
    pos = {p: k for k, p in enumerate(person_ids)}
    n = len(person_ids); travel = np.full(n, np.nan); cohort = np.full(n, '', dtype=object); changed = np.zeros(n, bool)
    with gzip.open(path, 'rt') as f:
        for r in csv.DictReader(f):
            k = pos.get(r['person_id'])
            if k is None: continue
            travel[k] = float(r['completed_travel_seconds']); cohort[k] = r['charging_cohort']; changed[k] = r['choice_changed'] == 'True'
    return {'travel': travel, 'cohort': cohort, 'choice_changed': changed}


def features(log, d, its, t_i, run_dir=None):
    """Feature columns (dict of arrays aligned with persons.csv) at the end of iteration its[t_i]."""
    t = its[t_i]; lo = max(0, t_i - WINDOW + 1)
    plan = d['plan']
    switches = (plan[lo + 1:t_i + 1] != plan[lo:t_i]).sum(axis=0) if t_i > lo else np.zeros(plan.shape[1], int)
    f = {'plans': d['plans'][t_i] if 'plans' in d else None,
         'executed_minus_best': d['executed'][t_i] - d['best'][t_i],
         'age': t - d['created'][t_i],
         'switches_last5': switches,
         'innovations_last5': d['innovated'][lo:t_i + 1].sum(axis=0),
         'score_change': d['executed'][t_i] - d['executed'][t_i - 1] if t_i else np.full(plan.shape[1], np.nan),
         'subpopulation': log.subpopulation}
    if run_dir is not None:
        now = research_persons(run_dir, t, log.person_id)
        if now is not None:
            before = research_persons(run_dir, its[t_i - 1], log.person_id) if t_i else None
            f.update(cohort=now['cohort'], travel_seconds=now['travel'], choice_changed=now['choice_changed'],
                     travel_change=now['travel'] - before['travel'] if before is not None else np.full(len(now['travel']), np.nan))
    return {k: v for k, v in f.items() if v is not None}

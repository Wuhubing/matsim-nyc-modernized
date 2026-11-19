"""Load the W1 replanning log (OUTPUT/simulation/replanning-log/) into numpy arrays indexed by person row.

Agent files are read one iteration at a time; plan ids (MATSim plan inheritance, base 36) become int64."""
import csv, gzip
from pathlib import Path
import numpy as np


class ReplanningLog:
    def __init__(self, run_dir):
        self.dir = Path(run_dir)/'simulation'/'replanning-log'
        with gzip.open(self.dir/'persons.csv.gz', 'rt') as f:
            rows = list(csv.DictReader(f))
        self.index = np.array([int(r['person']) for r in rows])          # MATSim person index
        self.person_id = [r['person_id'] for r in rows]
        self.subpopulation = np.array([r['subpopulation'] for r in rows])
        self.row = {int(r['person']): k for k, r in enumerate(rows)}
        with open(self.dir/'strategies.csv', newline='') as f:
            self.innovative_codes = {int(r['strategy']) for r in csv.DictReader(f) if r['innovative'] == '1'}
        self.iterations = sorted(int(p.name.split('-')[1].split('.')[0]) for p in self.dir.glob('agents-*.csv.gz'))

    def agents(self, it):
        """Arrays for iteration it, aligned with persons.csv: strategy, plan, created, parent, executed, best, plans."""
        n = len(self.index)
        out = {'strategy': np.full(n, -1, np.int16), 'plan': np.full(n, -1, np.int64), 'created': np.full(n, -1, np.int32),
               'parent': np.full(n, -1, np.int64), 'executed': np.full(n, np.nan), 'best': np.full(n, np.nan), 'plans': np.zeros(n, np.int16)}
        with gzip.open(self.dir/f'agents-{it}.csv.gz', 'rt') as f:
            for r in csv.DictReader(f):
                k = self.row[int(r['person'])]
                out['strategy'][k] = int(r['strategy']); out['plan'][k] = int(r['plan_id'], 36) if r['plan_id'] not in ('', 'null') else -1
                out['created'][k] = int(r['plan_created']); out['parent'][k] = int(r['parent_plan_id'], 36) if r['parent_plan_id'] else -1
                out['executed'][k] = float(r['executed_score']) if r['executed_score'] else np.nan
                out['best'][k] = float(r['best_score']) if r['best_score'] else np.nan
                out['plans'][k] = int(r['plans'])
        out['innovated'] = np.isin(out['strategy'], list(self.innovative_codes))
        return out

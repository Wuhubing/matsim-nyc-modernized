#!/usr/bin/env python3
"""Magnitude of iteration-to-iteration change from iteration_redundancy.py state pickles."""
import json, pickle, sys
from pathlib import Path

def load(d, i):
    with open(d / f'state-{i}.pkl', 'rb') as f:
        return pickle.load(f)

def main():
    d = Path(sys.argv[1]); n = len(list(d.glob('state-*.pkl'))); rows = []; prev = load(d, 0)
    for i in range(1, n):
        cur = load(d, i); pp, cp = prev['persons'], cur['persons']
        same = [abs(cp[p][2] - pp[p][2]) for p in pp.keys() & cp.keys() if pp[p][0] == cp[p][0]]
        changed = [abs(cp[p][2] - pp[p][2]) for p in pp.keys() & cp.keys() if pp[p][0] != cp[p][0]]
        q = lambda xs, t: sum(x <= t for x in xs) / len(xs)
        pl, cl = prev['links'], cur['links']; tot = 0; w = {0.02: 0, 0.05: 0, 0.10: 0}
        for k, b in cl.items():
            a = pl.get(k, (0, 0.0)); tot += b[0]
            dv = abs(b[0] - a[0]) / max(a[0], 1)
            dt = abs(b[1] / b[0] - (a[1] / a[0] if a[0] else 0)) / max(a[1] / a[0] if a[0] else 1, 1)
            for t in w:
                if dv <= t and dt <= t: w[t] += b[0]
        rows.append({'iteration': i, 'same_choice_persons': len(same),
                     'same_choice_travel_delta_le': {s: q(same, s) for s in (0, 60, 300, 900)},
                     'changed_choice_travel_delta_le': {s: q(changed, s) for s in (0, 60, 300, 900)},
                     'link_entries_on_link_hours_within': {str(t): v / tot for t, v in w.items()}})
        r = rows[-1]; print(i, 'same-choice |dT|<=0/60/300/900s:', ' '.join(f'{v:.3f}' for v in r['same_choice_travel_delta_le'].values()),
                            '| entries on link-hours within 2/5/10%:', ' '.join(f'{v:.3f}' for v in r['link_entries_on_link_hours_within'].values()), flush=True)
        prev = cur
    (d / 'magnitude.json').write_text(json.dumps(rows, indent=2) + '\n')

if __name__ == '__main__':
    main()

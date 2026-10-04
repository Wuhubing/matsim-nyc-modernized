#!/usr/bin/env python3
"""Share of choice changes that re-select a choice already simulated in an earlier iteration."""
import collections, json, pickle, sys
from pathlib import Path

def main():
    d = Path(sys.argv[1]); n = len(list(d.glob('state-*.pkl'))); seen = collections.defaultdict(set); last = {}; rows = []
    for i in range(n):
        with open(d / f'state-{i}.pkl', 'rb') as f:
            persons = pickle.load(f)['persons']
        changed = revisit = 0
        for p, v in persons.items():
            c = v[0]
            if i and p in last and last[p] != c:
                changed += 1; revisit += c in seen[p]
            seen[p].add(c); last[p] = c
        if i:
            rows.append({'iteration': i, 'choice_changed': changed, 'revisit_share': revisit / changed if changed else None})
            print(i, changed, f'{rows[-1]["revisit_share"]:.3f}', flush=True)
    (d / 'revisits.json').write_text(json.dumps(rows, indent=2) + '\n')

if __name__ == '__main__':
    main()

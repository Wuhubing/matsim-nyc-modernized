#!/usr/bin/env python3
"""M3 offline: priority files for the targeted chooser (W3) that give the innovation budget to groups that have not
settled yet (docs/aggregate-regularity-plan.md Sections 3 and 3.1).

  m3_priorities.py A3.json --snaps SNAPDIR --run RUN --out DIR
                   [--grouping od] [--key mode_tau0.05] [--reference s4712,s4713] [--agg median]
                   [--mode binary|remaining] [--placebo SEED] [--last 79]

A3.json: output of group_stability.py. Settling time per group T_g = --agg (median or max) over the reference runs
(substrings of A3's run paths). Use runs other than the seed of the test run, so that the run being steered never
sees its own future. Persons are assigned to groups exactly as in A3 (same parameters, persons.npz from --snaps,
cohorts from --run).
Priority of a person at iteration t (W3 ranks descending; ties are broken at random, NaN ranks last):
- binary: 1 while t < T_g, else 0;
- remaining: max(T_g - t, 0), so groups far from settling come first.
Persons outside the A3 subpopulations get no row (their budget is 0 anyway).
--placebo SEED: permute T_g among the groups (control: same amount of concentration, wrong targets).
Writes DIR/priority-t.csv.gz (header person_id,priority) for t = 0..--last (W3 needs a file for every iteration that
innovates) and DIR/summary.json with, per iteration and subpopulation, the share of persons with priority > 0. W3
gives round((1 - eps) B) budget places to the highest priorities, B = 30% of the subpopulation here; once fewer than
that are unsettled, the rest of the budget goes to settled persons at random, i.e. the concentration fades.

Run with: --targeted-priority DIR --targeted-epsilon 0.1 (run_reference.py)."""
import argparse, csv, gzip, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from group_stability import groupings, SUBPOPS


def settle_times(a3, grouping, key, reference, agg):
    runs = a3['runs']; cols = [i for i, r in enumerate(runs) if any(s in r for s in reference)]
    if not cols: raise SystemExit(f'no A3 run matches {reference}: {runs}')
    f = np.nanmedian if agg == 'median' else np.nanmax
    return {row['group']: float(f([row[key][i] for i in cols])) for row in a3['groupings'][grouping]['table']}, [runs[i] for i in cols]


def priorities(T, t, mode):
    return (T > t).astype(float) if mode == 'binary' else np.maximum(T - t, 0.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('a3'); ap.add_argument('--snaps', required=True); ap.add_argument('--run', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--grouping', default='od')
    ap.add_argument('--key', default='mode_tau0.05'); ap.add_argument('--reference', default='s4712,s4713')
    ap.add_argument('--agg', choices=('median', 'max'), default='median')
    ap.add_argument('--mode', choices=('binary', 'remaining'), default='binary')
    ap.add_argument('--placebo', type=int); ap.add_argument('--last', type=int, default=79)
    a = ap.parse_args()
    a3 = json.loads(Path(a.a3).read_text()); p = a3['params']
    Tg, used = settle_times(a3, a.grouping, a.key, a.reference.split(','), a.agg)
    if a.placebo is not None:
        keys = sorted(Tg); vals = np.random.default_rng(a.placebo).permutation([Tg[k] for k in keys]); Tg = dict(zip(keys, vals))

    persons = dict(np.load(Path(a.snaps)/'persons.npz'))
    keep = np.isin(persons['subpopulation'], SUBPOPS); persons = {k: v[keep] for k, v in persons.items()}
    with gzip.open(Path(a.run)/'simulation'/'research'/'cohorts.csv.gz', 'rt') as f:
        coh = {r['person_id']: r['charging_cohort'] for r in csv.DictReader(f)}
    cohort = np.array([coh.get(x, 'unknown') for x in persons['id']], dtype=object)
    keys = groupings(persons, cohort, p['cell_ft'], p['od_cell_ft'], p['min_size'])[a.grouping]
    missing = set(keys) - set(Tg)
    if missing: raise SystemExit(f'{len(missing)} groups not in A3 (different parameters or population?), e.g. {sorted(missing)[:3]}')
    T = np.array([Tg[k] for k in keys]); T[~np.isfinite(T)] = 0.0       # never changed -> settled from the start
    sub = persons['subpopulation']; ids = persons['id']

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); share = {}
    for t in range(a.last + 1):
        pr = priorities(T, t, a.mode)
        with gzip.open(out/f'priority-{t}.csv.gz', 'wt') as f:
            f.write('person_id,priority\n'); f.writelines(f'{i},{v:g}\n' for i, v in zip(ids, pr))
        share[t] = {s: float((pr[sub == s] > 0).mean()) for s in SUBPOPS}
    summary = {'a3': a.a3, 'grouping': a.grouping, 'key': a.key, 'reference_runs': used, 'agg': a.agg, 'mode': a.mode,
               'placebo': a.placebo, 'groups': len(set(keys)), 'persons': int(len(ids)), 'share_with_priority': share}
    (out/'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    print(f"{len(set(keys))} groups, {len(ids)} persons; reference {used}; share with priority > 0 (budget is 0.30):")
    for t in (1, 10, 20, 30, 40, 50, 60, 70, 79):
        if t <= a.last: print(f'  t={t:2d} ' + ' '.join(f'{s} {v:.2f}' for s, v in share[t].items()))


if __name__ == '__main__':
    main()

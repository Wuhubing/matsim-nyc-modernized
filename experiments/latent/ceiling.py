#!/usr/bin/env python3
"""How predictable is a person's stable-state plan at all (docs/converged-plan-plan.md, step 1).

  ceiling.py --final DIR --cohorts COHORTS.csv.gz --city city.npz --out FILE.json

DIR holds extract_plans.py pickles s{seed}-it80 / -it90 / -out for seeds 4711-4713 (baseline, innovation off
after iteration 79) and cold.pkl (the initial plans). Same sampled agents (crc32 % 1000 < 128). The label of a
person in a run is the selected plan of the output plans (iteration 100); per trip: main mode, departure hour.
Trips are matched by position (the activity chain is fixed, so a person has the same trips in every run; persons
whose trip count differs are counted and left out).

- within a run: agreement of the output with iterations 80 and 90 (selection only, so this is how much a person
  still switches between stored plans);
- across seeds: agreement of the output plans of two seeds; this is what a perfect copy of another run achieves
  (the 'copy the previous run' reference of the audit's rule 7);
- when the two other seeds agree on a trip's mode: how often, and how often the third seed matches (the trips
  whose stable mode does not depend on the run's randomness);
- simple references, fitted on seed 4711 and scored on seed 4712: the initial plan's mode; the most common
  stable mode by subpopulation and trip purpose; the same by straight-line distance band as well;
- aggregate: main-mode shares of trips (all, related cohort) per seed and their spread across seeds;
- the primary metric of the plan: per origin cell (city.npz grid, cells with >= 50 trips) the car and the pt share
  of trips; root mean square difference between two seeds (the yardstick U), and of each reference against seed
  4712, for all persons and the related cohort.
Departure: median |difference| in hours between runs for trips with the same mode in both."""
import argparse, csv, gzip, itertools, json, math, pickle
from collections import Counter, defaultdict
import numpy as np

SEEDS = [4711, 4712, 4713]
MODES = ['car', 'taxi', 'FHV', 'pt', 'ride', 'bike', 'cb', 'walk']


def trips(ag):
    sel = next((p for p in ag['plans'] if p['selected']), ag['plans'][0])
    return [(t[0], t[1] / 3600 if not math.isnan(t[1]) else math.nan, t[2], t[3], t[4], t[5], t[7]) for t in sel['trips']]


def load(d, name):
    with open(f'{d}/{name}.pkl', 'rb') as f: return {p: trips(a) for p, a in pickle.load(f).items()}


def agree(A, B):
    """Per-trip mode agreement, car-user agreement and departure differences between two label sets."""
    same = tot = 0; car_same = car_tot = 0; dep = []; skipped = 0
    for p in A.keys() & B.keys():
        a, b = A[p], B[p]
        if len(a) != len(b): skipped += 1; continue
        for x, y in zip(a, b):
            tot += 1; same += x[0] == y[0]
            if x[0] == y[0] and not (math.isnan(x[1]) or math.isnan(y[1])): dep.append(abs(x[1] - y[1]))
        car_tot += 1; car_same += any(t[0] == 'car' for t in a) == any(t[0] == 'car' for t in b)
    dep = np.array(dep)
    return {'trip_mode': same / tot, 'car_user': car_same / car_tot, 'dep_median_h': float(np.median(dep)),
            'dep_within_15min': float((dep <= 0.25).mean()), 'trips': tot, 'persons_skipped': skipped}


def shares(L, keep=None):
    c = Counter(t[0] for p, ts in L.items() if keep is None or keep(p) for t in ts); n = sum(c.values())
    return {m: c[m] / n for m in MODES}


def cell_shares(L, cell, keep=None, min_trips=50):
    n = defaultdict(float); car = defaultdict(float); pt = defaultdict(float)
    for p, ts in L.items():
        if keep is not None and not keep(p): continue
        for t in ts:
            c = cell(t[2], t[3]); n[c] += 1; car[c] += t[0] == 'car'; pt[c] += t[0] == 'pt'
    return {c: (car[c] / n[c], pt[c] / n[c]) for c in n if n[c] >= min_trips}


def rmse(A, B):
    cs = A.keys() & B.keys()
    return {'car': float(np.sqrt(np.mean([(A[c][0] - B[c][0]) ** 2 for c in cs]))),
            'pt': float(np.sqrt(np.mean([(A[c][1] - B[c][1]) ** 2 for c in cs]))), 'cells': len(cs)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--final', required=True); ap.add_argument('--cohorts', required=True)
    ap.add_argument('--city', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    with gzip.open(a.cohorts, 'rt') as f:
        related = {r['person_id']: r['charging_cohort'] == 'related' for r in csv.DictReader(f)}
    with open(f'{a.final}/cold.pkl', 'rb') as f: raw = pickle.load(f)
    cold = {p: trips(ag) for p, ag in raw.items()}; subpop = {p: ag['subpop'] for p, ag in raw.items()}
    out = {s: load(a.final, f's{s}-out') for s in SEEDS}
    res = {'persons': len(out[4711]), 'within_run': {}, 'across_seeds': {}}
    for s in SEEDS:
        for it in ('it80', 'it90'):
            res['within_run'][f'{s} {it} vs output'] = agree(load(a.final, f's{s}-{it}'), out[s])
    for s1, s2 in itertools.combinations(SEEDS, 2):
        res['across_seeds'][f'{s1} vs {s2}'] = agree(out[s1], out[s2])
    # trips on which the two other seeds agree: share, and how often the third matches
    two = {}
    for s in SEEDS:
        o1, o2 = [out[x] for x in SEEDS if x != s]; n = both = hit = 0
        for p in out[s]:
            if p in o1 and p in o2 and len(o1[p]) == len(o2[p]) == len(out[s][p]):
                for x, y, z in zip(o1[p], o2[p], out[s][p]):
                    n += 1
                    if x[0] == y[0]: both += 1; hit += z[0] == x[0]
        two[s] = {'other_two_agree_share': both / n, 'third_matches_when_they_agree': hit / both}
    res['two_seeds_agree'] = two
    # simple references fitted on 4711, scored on 4712
    res['initial_plan_mode'] = agree(cold, out[4712])

    def dist_band(t):
        d = math.hypot(t[4] - t[2], t[5] - t[3]) * 0.3048 / 1000
        return min(int(math.log2(max(d, 0.25) / 0.25)), 8)

    for name, key in (('purpose', lambda p, t: (subpop.get(p), t[6])),
                      ('purpose and distance', lambda p, t: (subpop.get(p), t[6], dist_band(t)))):
        table = defaultdict(Counter)
        for p, ts in out[4711].items():
            for t in ts: table[key(p, t)][t[0]] += 1
        pred = {p: [(table[key(p, t)].most_common(1)[0][0] if table[key(p, t)] else 'walk',) + t[1:] for t in ts]
                for p, ts in cold.items()}
        res[f'most_common_by_{name.replace(" ", "_")}'] = agree(pred, out[4712])
    city = np.load(a.city); x0, y0, size, nx, ny = city['grid']; ny = int(ny)
    cell = lambda x, y: int((x - x0) // size) * ny + int((y - y0) // size)
    refs = {'initial_plan_mode': cold}
    for name in ('purpose', 'purpose and distance'):
        key = (lambda p, t: (subpop.get(p), t[6])) if name == 'purpose' else (lambda p, t: (subpop.get(p), t[6], dist_band(t)))
        table = defaultdict(Counter)
        for p, ts in out[4711].items():
            for t in ts: table[key(p, t)][t[0]] += 1
        # expected shares, not the arg max: a lookup predicts probabilities
        refs[name] = (table, key)
    res['cell_rmse'] = {}
    for g, keep in (('all', None), ('related', lambda p: related.get(p, False))):
        r = {}
        for s1, s2 in itertools.combinations(SEEDS, 2):
            r[f'seeds {s1} vs {s2}'] = rmse(cell_shares(out[s1], cell, keep), cell_shares(out[s2], cell, keep))
        target = cell_shares(out[4712], cell, keep)
        r['initial plan mode vs 4712'] = rmse(cell_shares(cold, cell, keep), target)
        for name in ('purpose', 'purpose and distance'):
            table, key = refs[name]
            n = defaultdict(float); car = defaultdict(float); pt = defaultdict(float)
            for p, ts in cold.items():
                if keep is not None and not keep(p): continue
                for t in ts:
                    c = cell(t[2], t[3]); cnt = table[key(p, t)]; tot = sum(cnt.values()) or 1
                    n[c] += 1; car[c] += cnt['car'] / tot; pt[c] += cnt['pt'] / tot
            r[f'{name} lookup vs 4712'] = rmse({c: (car[c] / n[c], pt[c] / n[c]) for c in n if n[c] >= 50}, target)
        res['cell_rmse'][g] = r
    res['shares'] = {s: {'all': shares(out[s]), 'related': shares(out[s], lambda p: related.get(p, False))} for s in SEEDS}
    for g in ('all', 'related'):
        res[f'share_spread_{g}'] = {m: float(np.std([res['shares'][s][g][m] for s in SEEDS])) for m in MODES}
    with open(a.out, 'w') as f: json.dump(res, f, indent=1, default=str)
    print(json.dumps({k: v for k, v in res.items() if k != 'shares'}, indent=1, default=str))


if __name__ == '__main__':
    main()

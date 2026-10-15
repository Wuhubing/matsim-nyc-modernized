#!/usr/bin/env python3
"""Lever 2 (directed proposals, L2Seg's 'spend the search where it pays'): would mode proposals taken from the
agent's group be useful far more often than MATSim's random ones? Offline check on the plan snapshots.

  directed_proposals.py --runs RUN [RUN ...] --snaps SNAPDIR [SNAPDIR ...] --out FILE.json [--ks 20,30,40,50,60]

Persons of man and nonman with trips. Dominant mode of a plan = the main mode with most trips (plan_snapshots.py
MODES order breaks ties). Final mode = dominant mode of the selected plan in the final state ('output').
At snapshot k, the person's current mode = dominant mode of the best stored plan; 'changers' still have to find their
final mode (current != final). One proposal per person, always a mode other than the current one:
- random: uniform over the other modes (hit rate 1 / (number of modes - 1));
- global_trend: the mode whose population share (best plans, trip-weighted) rose most from k-10 to k;
- group_trend: the same within the person's group (A3 groupings: cohort, home, od);
- group_top: the most used other mode in the person's group at k;
- oracle_group_final: the most used other mode in the group's final state (not available in practice; upper bound).
Reported per grouping and k, mean over runs: changer share; per proposal rule the hit rate among changers (proposed
mode = final mode) and the useful-proposal rate over all persons (= changer share x hit rate) relative to random."""
import argparse, csv, gzip, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_snapshots import MODES
from group_stability import groupings, SUBPOPS, gshares

M = len(MODES)


def dom(counts):
    return np.where(counts.sum(axis=1) > 0, np.argmax(counts, axis=1), -1)


def best_other(scores, own):
    """Per row: argmax over modes of scores, excluding the row's own mode."""
    s = scores.astype(float).copy(); idx = np.flatnonzero(own >= 0); s[idx, own[idx]] = -np.inf
    return np.argmax(s, axis=1)


def load(d, k):
    z = np.load(Path(d)/f'snap-{k}.npz'); return {n: z[n] for n in z.files}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--runs', nargs='+', required=True); ap.add_argument('--snaps', nargs='+', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--ks', default='20,30,40,50,60')
    ap.add_argument('--cell-ft', type=float, default=10000); ap.add_argument('--od-cell-ft', type=float, default=20000)
    ap.add_argument('--min-size', type=int, default=300)
    a = ap.parse_args(); ks = [int(k) for k in a.ks.split(',')]
    res = {}
    for run, sd in zip(a.runs, a.snaps):
        persons = dict(np.load(Path(sd)/'persons.npz')); ids = persons['id']
        keep = np.isin(persons['subpopulation'], SUBPOPS)
        with gzip.open(Path(run)/'simulation'/'research'/'cohorts.csv.gz', 'rt') as f:
            coh = {r['person_id']: r['charging_cohort'] for r in csv.DictReader(f)}
        sub = {k: v[keep] for k, v in persons.items()}
        G = groupings(sub, np.array([coh.get(p, 'unknown') for p in sub['id']], dtype=object), a.cell_ft, a.od_cell_ft, a.min_size)
        def take(k):
            s = load(sd, k); order = {p: i for i, p in enumerate(s['id'])}
            return {n: v[[order[p] for p in sub['id']]] for n, v in s.items() if n != 'id'}
        fin = take('output'); fd = dom(fin['sel'])
        snaps = {k: take(k) for k in sorted(set(ks) | {k - 10 for k in ks})}
        for name, keys in G.items():
            u, g = np.unique(keys, return_inverse=True); ng = len(u)
            final_g = gshares(fin['sel'], g, ng)
            for k in ks:
                bk, bp = snaps[k]['best'], snaps[k - 10]['best']; cur = dom(bk)
                valid = (fd >= 0) & (cur >= 0); ch = valid & (cur != fd)
                sk, sp = gshares(bk, g, ng), gshares(bp, g, ng)
                tot = lambda c: c.sum(axis=0) / c.sum()
                glob = np.tile(tot(bk) - tot(bp), (len(cur), 1))
                rules = {'global_trend': best_other(glob, cur), 'group_trend': best_other((sk - sp)[g], cur),
                         'group_top': best_other(sk[g], cur), 'oracle_group_final': best_other(final_g[g], cur)}
                share = float(ch.sum() / valid.sum())
                row = {'changer_share': share, 'random': {'hit': 1 / (M - 1), 'useful_vs_random': 1.0},
                       'changer_final_modes': {MODES[m]: float(np.mean(fd[ch] == m)) for m in range(M)}}
                for r, pred in rules.items():
                    hit = float(np.mean(pred[ch] == fd[ch])) if ch.any() else float('nan')
                    row[r] = {'hit': hit, 'useful_vs_random': hit * (M - 1)}
                res.setdefault(name, {}).setdefault(k, []).append(row)
        print(f'done {run}', flush=True)
    def mean(rows):
        if isinstance(rows[0], dict): return {k: mean([r[k] for r in rows]) for k in rows[0]}
        return float(np.mean(rows))
    out = {'runs': a.runs, 'ks': ks, 'groupings': {n: {k: mean(v) for k, v in m.items()} for n, m in res.items()}}
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    rules = ['global_trend', 'group_trend', 'group_top', 'oracle_group_final']
    for name, m in out['groupings'].items():
        print(f'\n== {name}: changer share | hit rate among changers (random {1 / (M - 1):.3f}) for ' + ', '.join(rules))
        for k, r in m.items():
            fm = sorted(r['changer_final_modes'].items(), key=lambda x: -x[1])[:3]
            print(f"  k={k}: {r['changer_share']:.3f} | " + ' '.join(f"{r[x]['hit']:.3f}" for x in rules)
                  + '   changers end in ' + ', '.join(f'{a} {b:.2f}' for a, b in fm))


if __name__ == '__main__':
    main()

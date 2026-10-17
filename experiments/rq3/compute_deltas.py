#!/usr/bin/env python3
"""Policy differences for RQ2 acceptance: Delta = policy - baseline (same seed) and D = Delta(P1) - Delta(P2).

  compute_deltas.py --baseline S=DIR [S=DIR ...] --policy NAME:S=DIR [NAME:S=DIR ...] --out FILE.json
                    [--window 90-99] [--pair P1,P2]

Every DIR is a reference run directory (with simulation/research and simulation/iteration-metrics-*.json). All
indicators are means over the window of iterations (default 90-99). Indicators (sample units, not expanded):
- legs_<mode>_<group>: departing legs per mode for groups all / charging:related / charging:unrelated (group-modes)
- share_<mode>: departing legs of the mode / all departing legs (all persons)
- cordon_entries, revenue, unfinished, car_leg_seconds, wait_person_hours (iteration-metrics)
- usd_<group>: mean per-person executed score converted to dollars with the subpopulation's marginal utility of money
  (score is total plan utility, not the paper's travel-only consumer surplus)
- loser_share_<group> (Delta only): share of persons whose window-mean score is lower under the policy than under
  the baseline of the same seed (person-paired)
Output per indicator: values per seed; Delta per seed (paired); mean, sd, min, max of Delta; and the unpaired
variance Var(policy) + Var(baseline) next to the paired Var(Delta) (check B). D for --pair (default first two
policies) per seed and its summary. Sanity: a policy equal to the baseline gives Delta = 0 everywhere."""
import argparse, csv, gzip, json
from pathlib import Path
import numpy as np

MONEY = {'man': 0.062227, 'nonman': 0.0543894, 'outside': 0.062227}     # config-baseline.xml marginalUtilityOfMoney
GROUPS = ('all', 'charging:related', 'charging:unrelated')
MODES = ('car', 'pt', 'walk', 'taxi', 'FHV', 'ride', 'bike', 'cb')


def research(run):
    return Path(run)/'simulation'/'research'


def iteration_indicators(run, it):
    out = {}
    with gzip.open(research(run)/f'group-modes-{it}.csv.gz', 'rt') as f:
        for r in csv.DictReader(f):
            if r['group'] in GROUPS and r['leg_mode'] in MODES:
                out[f"legs_{r['leg_mode']}_{r['group']}"] = float(r['departures'])
    total = sum(out.get(f'legs_{m}_all', 0.0) for m in MODES)
    for m in MODES:
        out[f'share_{m}'] = out.get(f'legs_{m}_all', 0.0) / total if total else float('nan')
    m = json.loads((Path(run)/'simulation'/f'iteration-metrics-{it}.json').read_text())
    out['cordon_entries'] = float(m['private_car_entry_crossings'])
    out['revenue'] = float(m['net_congestion_revenue'])
    out['unfinished'] = float(m['unfinished_all'])
    out['car_leg_seconds'] = float(m['mean_completed_car_leg_seconds'])
    out['wait_person_hours'] = float(m['censored_wait_person_hours'])
    return out


def person_scores(run, it):
    """(person ids, subpopulation, cohort, score) for one iteration."""
    ids, sub, coh, sc = [], [], [], []
    with gzip.open(research(run)/f'persons-{it}.csv.gz', 'rt') as f:
        for r in csv.DictReader(f):
            ids.append(r['person_id']); sub.append(r['subpopulation']); coh.append(r['charging_cohort'])
            sc.append(float(r['score']) if r['score'] not in ('', 'NaN') else np.nan)
    return ids, np.array(sub), np.array(coh), np.array(sc)


def summarise_run(run, window):
    rows = [iteration_indicators(run, it) for it in window]
    ind = {k: float(np.mean([r[k] for r in rows if k in r])) for k in rows[0]}
    acc = None
    for it in window:
        ids, sub, coh, sc = person_scores(run, it)
        if acc is None:
            order = np.argsort(ids); base_ids = np.array(ids)[order]; acc = np.zeros(len(ids)); s0, c0 = sub[order], coh[order]
        else:
            order = np.argsort(ids)
            assert np.array_equal(np.array(ids)[order], base_ids), 'person set changed between iterations'
        acc += sc[order]
    score = acc / len(window)
    usd = score / np.array([MONEY.get(s, MONEY['man']) for s in s0])
    for g in GROUPS:
        m = np.ones(len(usd), bool) if g == 'all' else (c0 == g.split(':')[1])
        ind[f'usd_{g}'] = float(np.nanmean(usd[m]))
    return ind, {'ids': base_ids, 'usd': usd, 'cohort': c0}


def stats(x):
    x = np.array(x, float)
    return {'mean': float(x.mean()), 'sd': float(x.std(ddof=1)) if len(x) > 1 else None,
            'min': float(x.min()), 'max': float(x.max()), 'n': int(len(x))}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--baseline', nargs='+', required=True); ap.add_argument('--policy', nargs='+', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--window', default='90-99'); ap.add_argument('--pair')
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.window.split('-')); window = list(range(lo, hi + 1))
    base = dict(x.split('=', 1) for x in a.baseline)
    pol = {}
    for x in a.policy:
        name, rest = x.split(':', 1); s, d = rest.split('=', 1); pol.setdefault(name, {})[s] = d
    B = {s: summarise_run(d, window) for s, d in base.items()}
    P = {n: {s: summarise_run(d, window) for s, d in runs.items()} for n, runs in pol.items()}
    keys = list(next(iter(B.values()))[0].keys())
    out = {'window': [lo, hi], 'baseline': {s: B[s][0] for s in B}, 'policies': {}}
    deltas = {}
    for n, runs in P.items():
        seeds = [s for s in runs if s in B]
        res = {'seeds': seeds, 'indicators': {}}
        deltas[n] = {}
        for k in keys:
            yp = [runs[s][0][k] for s in seeds]; yb = [B[s][0][k] for s in seeds]
            d = [p - b for p, b in zip(yp, yb)]; deltas[n][k] = dict(zip(seeds, d))
            unpaired = (np.var(yp, ddof=1) + np.var(yb, ddof=1)) if len(seeds) > 1 else None
            res['indicators'][k] = {'policy': dict(zip(seeds, yp)), 'delta': dict(zip(seeds, d)), 'delta_stats': stats(d),
                                    'paired_var': float(np.var(d, ddof=1)) if len(seeds) > 1 else None, 'unpaired_var': unpaired}
        for g in GROUPS:          # person-paired loser shares and mean dollar change per cohort
            vals, means = {}, {}
            for s in seeds:
                pb, pp = B[s][1], runs[s][1]
                assert np.array_equal(pb['ids'], pp['ids']), 'different persons in policy and baseline'
                m = np.ones(len(pb['ids']), bool) if g == 'all' else (pb['cohort'] == g.split(':')[1])
                diff = pp['usd'][m] - pb['usd'][m]
                vals[s] = float(np.mean(diff < 0)); means[s] = float(np.nanmean(diff))
            res['indicators'][f'loser_share_{g}'] = {'delta': vals, 'delta_stats': stats(list(vals.values()))}
            deltas[n][f'loser_share_{g}'] = vals
        out['policies'][n] = res
    names = list(P)
    pair = a.pair.split(',') if a.pair else names[:2]
    if len(pair) == 2 and all(p in P for p in pair):
        d = {}
        for k in deltas[pair[0]]:
            seeds = [s for s in deltas[pair[0]][k] if s in deltas[pair[1]][k]]
            v = [deltas[pair[0]][k][s] - deltas[pair[1]][k][s] for s in seeds]
            d[k] = {'per_seed': dict(zip(seeds, v)), 'stats': stats(v)}
        out['D'] = {'pair': pair, 'indicators': d}
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    focus = ['legs_car_charging:related', 'share_car', 'share_pt', 'revenue', 'cordon_entries', 'usd_all',
             'usd_charging:related', 'usd_charging:unrelated', 'loser_share_charging:related', 'loser_share_charging:unrelated']
    for n, r in out['policies'].items():
        print(f'\n{n}: Delta mean (sd) [min, max] | paired var / unpaired var')
        for k in focus:
            if k in r['indicators']:
                s = r['indicators'][k]['delta_stats']; pv, uv = r['indicators'][k].get('paired_var'), r['indicators'][k].get('unpaired_var')
                ratio = f'{pv / uv:.3f}' if pv is not None and uv else '-'
                print(f"  {k:32} {s['mean']:+.5g} ({s['sd'] if s['sd'] is None else round(s['sd'], 6)}) [{s['min']:+.5g}, {s['max']:+.5g}] | {ratio}")
    if 'D' in out:
        print(f"\nD = {out['D']['pair'][0]} - {out['D']['pair'][1]}: mean (sd)")
        for k in focus:
            if k in out['D']['indicators']:
                s = out['D']['indicators'][k]['stats']
                print(f"  {k:32} {s['mean']:+.5g} ({s['sd'] if s['sd'] is None else round(s['sd'], 6)})")


if __name__ == '__main__':
    main()

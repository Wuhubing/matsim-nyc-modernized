#!/usr/bin/env python3
"""Evaluate L2 (PSim hybrids) and L3 (policy response surrogate) against the seed spread of all-QSim runs.

Indicators are taken from the final iteration (always QSim) of each 12-iteration run:
  score (avg executed), car and pt mode shares, unfinished persons, private-car cordon entries,
  mean completed car-leg seconds, censored waiting person-hours, persons not boarded at cutoff,
  net congestion revenue (sample USD).
Tolerance: the standard deviation across QSim seeds 4711/4712/4713 (same settings). |z| <= 1 is
'within seed noise'; the seed range is reported as well.
"""
import csv, json, math, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs'
SEEDS = {4711: OUT/'performance-20261004-171012-redundancy/full-candidate',
         4712: OUT/'surrogate-data-20261005/seed-4712-r2', 4713: OUT/'surrogate-data-20261005/seed-4713'}
INDICATORS = ['score', 'car_share', 'pt_share', 'unfinished', 'car_entries', 'car_leg_seconds', 'wait_person_hours', 'not_boarded', 'revenue']


def table(path):
    with open(path) as f:
        return list(csv.DictReader(f, delimiter=';'))


def indicators(run, iteration=11):
    sim = run/'simulation'
    m = json.loads((sim/f'iteration-metrics-{iteration}.json').read_text())
    score = next(r for r in table(sim/'BUILT.scorestats.csv') if int(r['iteration']) == iteration)
    modes = next(r for r in table(sim/'BUILT.modestats.csv') if int(r['iteration']) == iteration)
    return {'score': float(score['avg_executed']), 'car_share': float(modes['car']), 'pt_share': float(modes['pt']),
            'unfinished': m['unfinished_all'], 'car_entries': m['private_car_entry_crossings'],
            'car_leg_seconds': m['mean_completed_car_leg_seconds'], 'wait_person_hours': m['censored_wait_person_hours'],
            'not_boarded': m['waiting_at_cutoff'], 'revenue': m['net_congestion_revenue']}


def seed_spread():
    values = {s: indicators(p) for s, p in SEEDS.items()}
    spread = {k: {'mean': statistics.mean(v[k] for v in values.values()), 'sd': statistics.stdev(v[k] for v in values.values()),
                  'range': max(v[k] for v in values.values()) - min(v[k] for v in values.values())} for k in INDICATORS}
    return values, spread


def identical_metrics(a, b, iterations=12):
    return all(json.loads((a/f'simulation/iteration-metrics-{i}.json').read_text()) == json.loads((b/f'simulation/iteration-metrics-{i}.json').read_text())
               for i in range(iterations))


def manifest_times(campaign):
    m = json.loads((campaign/'manifest.json').read_text())
    return {a['name']: (a['status'], a.get('elapsed_seconds')) for a in m['attempts']}


def psim_log(run):
    f = run/'simulation/psim-log.csv'
    return list(csv.DictReader(open(f))) if f.exists() else []


def l2(campaigns, spread, reference):
    rows = {}
    for c in campaigns:
        for name, (status, seconds) in manifest_times(c).items():
            if status != 'complete':
                continue
            run = c/name; ind = indicators(run); log = psim_log(run)
            rows[name] = {'wall_seconds': seconds, 'qsim_iterations': sum(r['mobsim'] == 'qsim' for r in log) or 12,
                          'indicators': ind, 'z': {k: (ind[k] - reference[k]) / spread[k]['sd'] if spread[k]['sd'] else None for k in INDICATORS},
                          'relative': {k: (ind[k] - reference[k]) / abs(reference[k]) if reference[k] else None for k in INDICATORS}}
    return rows


def l3(policy, spread, scale1):
    points = {1.0: scale1}
    for name, (status, _) in manifest_times(policy).items():
        if status == 'complete':
            points[float(name.split('-')[1])] = indicators(policy/name)
    out = {}
    if not all(s in points for s in (0.0, 1.0, 2.0)):
        return {'available_scales': sorted(points)}
    for test in [s for s in points if s not in (0.0, 1.0, 2.0)]:
        out[test] = {}
        for k in INDICATORS:
            y0, y1, y2 = points[0.0][k], points[1.0][k], points[2.0][k]
            quad = y0 + (y1 - y0) * test + ((y2 - 2 * y1 + y0) / 2) * test * (test - 1)   # Newton form through 0,1,2
            lin = y0 + (y1 - y0) * test if test <= 1 else y1 + (y2 - y1) * (test - 1)
            truth = points[test][k]; sd = spread[k]['sd']
            out[test][k] = {'truth': truth, 'quadratic': quad, 'linear': lin,
                            'z_quadratic': (quad - truth) / sd if sd else None, 'z_linear': (lin - truth) / sd if sd else None}
    return {'available_scales': sorted(points), 'points': {str(s): v for s, v in points.items()}, 'holdout': {str(k): v for k, v in out.items()}}


def main():
    values, spread = seed_spread()
    result = {'seed_values': {str(k): v for k, v in values.items()}, 'seed_spread': spread}
    psim = [OUT/'surrogate-psim-20261005-f']   # clean batch; batch c only contributes the qsim-ref equality check
    ref_run = OUT/'surrogate-psim-20261005-c/qsim-ref'
    if (ref_run/'simulation/iteration-metrics-11.json').exists():
        result['qsim_ref_identical_to_full_candidate'] = identical_metrics(ref_run, SEEDS[4711])
    result['l2'] = l2(psim, spread, values[4711])
    policy = OUT/'surrogate-policy-20261005'
    if (policy/'manifest.json').exists():
        result['l3'] = l3(policy, spread, values[4711])
    (OUT/'surrogate-analysis/evaluation.json').write_text(json.dumps(result, indent=2, default=float) + '\n')
    print('seed sd:', {k: round(v['sd'], 4) for k, v in spread.items()})
    if 'qsim_ref_identical_to_full_candidate' in result:
        print('qsim-ref identical to full-candidate over 12 iterations:', result['qsim_ref_identical_to_full_candidate'])
    for name, r in result['l2'].items():
        zs = [abs(z) for z in r['z'].values() if z is not None]
        rel = [abs(v) for v in r['relative'].values() if v is not None]
        print(f"{name:14s} wall {r['wall_seconds']:7.0f}s qsim_its {r['qsim_iterations']:2d} max|z| {max(zs):6.2f} within-1sd {sum(z <= 1 for z in zs)}/{len(zs)}"
              f" max|rel| {100*max(rel):5.2f}% within-1% {sum(x <= .01 for x in rel)}/{len(rel)}")
        print('   rel%', ' '.join(f"{k}={100*v:+.2f}" for k, v in r['relative'].items()))
    if 'l3' in result and 'holdout' in result['l3']:
        for s, ks in result['l3']['holdout'].items():
            print('L3 scale', s, 'quadratic max|z|', round(max(abs(v['z_quadratic']) for v in ks.values()), 2),
                  'linear max|z|', round(max(abs(v['z_linear']) for v in ks.values()), 2))


if __name__ == '__main__':
    main()

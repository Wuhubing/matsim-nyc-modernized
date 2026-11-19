"""Per-iteration indicators of one run (plan Section 4), read from MATSim's stats and IterationMetrics.

  score              mean executed score (BUILT.scorestats.csv avg_executed)
  share_<mode>       mode share per mode (BUILT.modestats.csv)
  car_departures, car_completed, unfinished   (iteration-metrics-N.json)
  cordon_entries, net_revenue, wait_person_hours (censored, incl. waiting at the cut-off)
  counts_sim, counts_obs, counts_rel_error   daily totals over all bridge and tunnel count stations
                                              (ITERS/it.N/*.countscompare.txt, MATSim's scaled volumes)
"""
import csv, json
from pathlib import Path


def _table(path):
    with open(path, newline='') as f: return list(csv.DictReader(f, delimiter=';'))


def counts(path):
    """Daily simulated and observed totals over all stations of one countscompare.txt."""
    sim = obs = 0.0
    with open(path, newline='') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            sim += float(r['MATSIM volumes']); obs += float(r['Count volumes'])
    return sim, obs


def indicators(run_dir):
    """{iteration: {indicator: value}} for every iteration that has scores and IterationMetrics."""
    sim = Path(run_dir)/'simulation'
    scores = {int(r['iteration']): float(r['avg_executed']) for r in _table(sim/'BUILT.scorestats.csv')}
    modes = {int(r['iteration']): r for r in _table(sim/'BUILT.modestats.csv')}
    out = {}
    for it in sorted(scores):
        metrics_file = sim/f'iteration-metrics-{it}.json'
        if not metrics_file.exists() or it not in modes: continue
        m = json.loads(metrics_file.read_text())
        row = {'score': scores[it]}
        row.update({f'share_{k}': float(v) for k, v in modes[it].items() if k != 'iteration'})
        row.update(car_departures=m['departures'].get('car', 0), car_completed=m['completed'].get('car', 0),
                   unfinished=m['unfinished_all'], cordon_entries=m['private_car_entry_crossings'],
                   net_revenue=m['net_congestion_revenue'], wait_person_hours=m['censored_wait_person_hours'])
        cc = next((sim/f'ITERS/it.{it}').glob('*.countscompare.txt'), None)
        if cc is not None:
            s, o = counts(cc)
            row.update(counts_sim=s, counts_obs=o, counts_rel_error=s/o - 1 if o else float('nan'))
        out[it] = row
    return out

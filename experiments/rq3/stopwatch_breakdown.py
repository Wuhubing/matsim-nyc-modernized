#!/usr/bin/env python3
"""Where the time of a MATSim-NYC run goes, from MATSim's own BUILT.stopwatch.csv (no extra run needed).

  stopwatch_breakdown.py RUN_DIR [RUN_DIR ...] [--switch-off 80] [--out FILE.json]

Per run and in total: seconds per phase, split into innovation (< switch-off) and selection iterations, and into
plan-dump iterations (MATSim writes plans: 'dump all plans' > 0) and the others. Phases are MATSim's top-level
controller phases; scoring runs inside the mobsim (event handlers), so 'scoring' is ~0.
- 'dump all plans' is part of beforeMobsimListeners and is reported separately (before = beforeMobsim - dump).
- iterationEndsListeners holds MATSim's own analyses (scorestats, modestats, leg histograms, counts) and our research
  records; it is the upper bound of the analysis overhead we add.
Net time = iteration time - dump - iterationEnds: the time an unmodified MATSim run without our records and without
periodic plan dumps would need (an approximation: MATSim's own end-of-iteration analyses are subtracted too).
"""
import argparse, csv, json
from pathlib import Path

PHASES = ('iterationStartsListeners', 'replanning', 'dump all plans', 'beforeMobsimListeners', 'prepareForMobsim',
          'mobsim', 'afterMobsimListeners', 'scoring', 'iterationEndsListeners', 'iteration')


def secs(x):
    if not x:
        return 0.0
    h, m, s = (int(v) for v in x.split(':'))
    return h * 3600 + m * 60 + s


def read(run):
    f = Path(run)/'simulation'/'BUILT.stopwatch.csv'
    with open(f) as fh:
        rows = list(csv.reader(fh, delimiter=';'))
    head = rows[0]
    # duration columns come after the empty separator column
    sep = head.index('')
    dur = {name: sep + 1 + i for i, name in enumerate(head[sep + 1:]) if name}
    out = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        d = {p: secs(r[dur[p]]) if p in dur and dur[p] < len(r) else 0.0 for p in PHASES}
        d['beforeMobsim_excl_dump'] = d['beforeMobsimListeners'] - d['dump all plans']
        d['net'] = d['iteration'] - d['dump all plans'] - d['iterationEndsListeners']
        d['it'] = int(r[0]); out.append(d)
    return out


def summarise(rows, sel):
    rs = [r for r in rows if sel(r)]
    tot = sum(r['iteration'] for r in rs) or 1.0
    keys = ('replanning', 'beforeMobsim_excl_dump', 'dump all plans', 'prepareForMobsim', 'mobsim',
            'afterMobsimListeners', 'iterationEndsListeners', 'net', 'iteration')
    return {'n': len(rs), 'seconds': {k: sum(r[k] for r in rs) for k in keys},
            'share': {k: sum(r[k] for r in rs) / tot for k in keys},
            'mean_minutes_per_iteration': tot / max(len(rs), 1) / 60}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('runs', nargs='+'); ap.add_argument('--switch-off', type=int, default=80); ap.add_argument('--out')
    a = ap.parse_args()
    allrows, out = [], {}
    groups = {'all': lambda r: True, 'innovation': lambda r: r['it'] < a.switch_off,
              'selection': lambda r: r['it'] >= a.switch_off, 'dump': lambda r: r['dump all plans'] > 0,
              'no_dump': lambda r: r['dump all plans'] == 0}
    for run in a.runs:
        rows = read(run); allrows += rows
        out[str(run)] = {g: summarise(rows, f) for g, f in groups.items()}
    out['TOTAL'] = {g: summarise(allrows, f) for g, f in groups.items()}
    cols = ('replanning', 'beforeMobsim_excl_dump', 'dump all plans', 'prepareForMobsim', 'mobsim', 'iterationEndsListeners', 'net')
    print(f"{'runs: ' + str(len(a.runs)):22} {'n':>5} {'min/it':>7} " + ' '.join(f'{c[:12]:>12}' for c in cols))
    for g in groups:
        s = out['TOTAL'][g]
        print(f'{g:22} {s["n"]:5d} {s["mean_minutes_per_iteration"]:7.2f} ' + ' '.join(f'{s["share"][c]:12.1%}' for c in cols))
    print('\nper run, all iterations: total hours | net hours (without dumps and iterationEnds) | mobsim share')
    for run in a.runs:
        s = out[str(run)]['all']
        print(f'  {Path(run).name:28} {s["seconds"]["iteration"] / 3600:6.2f} {s["seconds"]["net"] / 3600:6.2f} {s["share"]["mobsim"]:7.1%}')
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1) + '\n')


if __name__ == '__main__':
    main()

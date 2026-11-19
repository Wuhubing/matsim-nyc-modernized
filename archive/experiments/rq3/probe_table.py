#!/usr/bin/env python3
"""Summarise selection probes: for each arm (label) and snapshot iteration k, the policy effects measured on probe
iterations 2-11 against the reference effects (iterations 90-99, same seed), in units of epsilon (04 section 6).

  probe_table.py --root .../matsim-work/rq3 --ref deltas-reference.json --out probes.json LABEL:K[,K...] ...
  e.g. probe_table.py ... warm:10,20,30,40 cold:30,50,70,80 e1:30,50,70

Probe directories: ROOT/probe-LABEL-{baseline,schema1,schema2}-s4711-kK. Cost of the policy pipeline to reach the
probe answer, in iterations: k innovation-phase iterations (the snapshot) + 12 probe iterations (reference: 100).
Passes = every stable indicator (car legs of the charging-related cohort, car share, pt share) within epsilon for
Schema 1, Schema 2 and D. Revenue and cordon entries are reported only.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compute_deltas as cd                                   # noqa: E402

SEED = '4711'
STABLE = ('legs_car_charging:related', 'share_car', 'share_pt')
REPORT = ('revenue', 'cordon_entries')
EPS = {'schema1': {'legs_car_charging:related': 712, 'share_car': 0.0005, 'share_pt': 0.0005, 'revenue': 4340, 'cordon_entries': 248},
       'schema2': {'legs_car_charging:related': 736, 'share_car': 0.0005, 'share_pt': 0.0005, 'revenue': 5252, 'cordon_entries': 286},
       'D': {'legs_car_charging:related': 526, 'share_car': 0.0005, 'share_pt': 0.0005, 'revenue': 3273, 'cordon_entries': 203}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', required=True); ap.add_argument('--ref', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('arms', nargs='+'); a = ap.parse_args()
    ref = json.loads(Path(a.ref).read_text()); root = Path(a.root)
    W = list(range(2, 12)); out = {}
    print(f"{'arm':6} {'k':>3} {'cost':>5} | " + ' | '.join(f'{p:^26}' for p in ('Schema 1', 'Schema 2', 'D'))
          + ' | pass | revenue/cordon (report) S1 S2 D')
    print(f"{'':6} {'':>3} {'':>5} | " + ' | '.join('  car-legs car-sh  pt-sh  ' for _ in range(3)))
    for arm in a.arms:
        label, ks = arm.split(':')
        for k in (int(x) for x in ks.split(',')):
            d = {sc: root/f'probe-{label}-{sc}-s{SEED}-k{k}' for sc in ('baseline', 'schema1', 'schema2')}
            missing = [str(p) for p in d.values() if len(list((p/'simulation').glob('iteration-metrics-*.json'))) < 12]
            if missing:
                print(f'{label:6} {k:3d}  incomplete: {", ".join(Path(m).name for m in missing)}'); continue
            B = cd.summarise_run(d['baseline'], W)[0]
            dl = {sc: {i: cd.summarise_run(d[sc], W)[0][i] - B[i] for i in STABLE + REPORT} for sc in ('schema1', 'schema2')}
            dl['D'] = {i: dl['schema1'][i] - dl['schema2'][i] for i in STABLE + REPORT}
            rr = {}
            for sc in ('schema1', 'schema2', 'D'):
                rv = (ref['D']['indicators'][i]['per_seed'][SEED] if sc == 'D' else ref['policies'][sc]['indicators'][i]['delta'][SEED]
                      for i in STABLE + REPORT)
                rr[sc] = {i: abs(dl[sc][i] - r) / EPS[sc][i] for i, r in zip(STABLE + REPORT, rv)}
            ok = all(rr[sc][i] <= 1 for sc in rr for i in STABLE)
            out[f'{label}-k{k}'] = {'delta': dl, 'ratio': rr, 'pass': ok, 'cost_iterations': k + 12}
            cells = ' | '.join(' '.join(f'{rr[sc][i]:6.2f}' for i in STABLE) + '   ' for sc in ('schema1', 'schema2', 'D'))
            rep = ' '.join(f"{rr[sc]['revenue']:.1f}/{rr[sc]['cordon_entries']:.1f}" for sc in ('schema1', 'schema2', 'D'))
            print(f'{label:6} {k:3d} {k + 12:5d} | {cells} | {"YES " if ok else "no  "} | {rep}')
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')


if __name__ == '__main__':
    main()

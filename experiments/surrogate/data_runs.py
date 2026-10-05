#!/usr/bin/env python3
"""Data-generating simulations for the surrogate study (sequential, own ledger; the user lifted the budget cap
on 2026-10-05, usage is still recorded).

  fixed-sNNNN : iteration 0 only, selected plans of full-baseline iteration 11, seed NNNN.
                Plans are identical across seeds, so differences are pure QSim stochasticity = noise floor.
  seed-NNNN   : 12-iteration 2025-policy run with seed NNNN, events AND pre-mobsim plans every iteration
                (training/validation data without information leakage) plus online metrics.
"""
import argparse, json, random, shutil, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'performance'))
import redundancy_campaign as R
B, D, ROOT = R.B, R.D, R.ROOT
CAMPAIGN = ROOT/'outputs/performance-20261004-171012-redundancy'
FIXED_PLANS = CAMPAIGN/'full-baseline/simulation/ITERS/it.11/BUILT.11.plans.xml.zst'
ONLINE = ['-Dnyc.onlineMetrics=true']


def register(m):
    for seed in m['fixed_seeds']:
        R.ARMS[f'fixed-s{seed}'] = ('candidate.jar', {('global', 'randomSeed'): str(seed), ('plans', 'inputPlansFile'): str(FIXED_PLANS)}, ONLINE)
    for seed in m['full_seeds']:
        for suffix in ('', '-r2'):
            R.ARMS[f'seed-{seed}{suffix}'] = ('candidate.jar', {('global', 'randomSeed'): str(seed), ('controller', 'writePlansInterval'): '1'}, ONLINE)


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(CAMPAIGN/'candidate.jar', out/'candidate.jar')
    code = out/'code'; code.mkdir()
    for p in [Path(__file__), Path(R.__file__), Path(B.__file__)]:
        shutil.copy2(p, code/p.name)
    D.save(out/'budget.json', {'limit_seconds': 10**7, 'used_seconds': 0.0, 'active': None, 'updated_utc': D.now(),
                               'note': 'User lifted the simulation budget cap on 2026-10-05; usage is recorded, not capped.'})
    (out/'executor.lock').touch()
    src = json.loads((CAMPAIGN/'manifest.json').read_text())
    inputs = [i for i in src['inputs'] if not i['path'].endswith(('.jar', '.py'))]
    inputs += [{'path': str(p), 'sha256': D.sha(p)} for p in [out/'candidate.jar', FIXED_PLANS]]
    m = {'created_utc': D.now(), 'source': src['source'], 'ledger': str(out/'budget.json'), 'lock': str(out/'executor.lock'),
         'java_home': src['java_home'], 'head_commit': D.command(['git', 'rev-parse', 'HEAD']).strip(), 'inputs': inputs,
         'fixed_seeds': [4711, 1001, 1002], 'full_seeds': [4712, 4713], 'attempts': [], 'status': 'prepared',
         'short_limit_seconds': 10**7, 'full_limit_seconds': 10**7}
    D.save(out/'manifest.json', m)
    print(out)


def run(out):
    m = json.loads((out/'manifest.json').read_text()); register(m)
    ledger = json.loads(Path(m['ledger']).read_text())
    if ledger['active'] or any(a['status'] != 'complete' and not a.get('reviewed_failure') for a in m['attempts']):
        raise RuntimeError('Inspect incomplete attempt first; no automatic retry')
    jobs = [(f'fixed-s{s}', 1, 'short') for s in m['fixed_seeds']] + [(f'seed-{s}', 12, 'full') for s in m['full_seeds']]
    for name, iterations, phase in jobs:
        # A manually reviewed failure is retried once under a new name; its partial outputs are kept.
        if any(a['name'] == name and a.get('reviewed_failure') for a in m['attempts']):
            name += '-r2'
        if not any(a['name'] == name for a in m['attempts']):
            R.execute(out, m, ledger, name, name, iterations, phase)
    m['status'] = 'complete'; D.save(out/'manifest.json', m)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('action', choices=['prepare', 'run']); ap.add_argument('--run-dir', type=Path, required=True)
    a = ap.parse_args()
    prepare(a.run_dir.resolve()) if a.action == 'prepare' else run(a.run_dir.resolve())

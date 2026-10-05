#!/usr/bin/env python3
"""L3 data: 12-iteration all-QSim runs (seed 4711, E1 online metrics, no event XML) at several congestion-charge
scales (-Dnyc.pricing.scale). Scale 1.0 is the existing full-candidate run with identical settings.
Starts after the PSim campaign has finished (one simulation at a time)."""
import argparse, json, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'performance'))
import redundancy_campaign as R
B, D, ROOT = R.B, R.D, R.ROOT
SCALES = ['0.0', '0.5', '1.5', '2.0']


def register():
    for s in SCALES:
        R.ARMS[f'scale-{s}'] = ('policy.jar', {('controller', 'writeEventsInterval'): '0'}, ['-Dnyc.onlineMetrics=true', f'-Dnyc.pricing.scale={s}'])


def prepare(out, after):
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(ROOT/'target/matsim-nyc-modernized-1.0.0.jar', out/'policy.jar')
    code = out/'code'; code.mkdir(); shutil.copy2(__file__, code/Path(__file__).name)
    D.save(out/'budget.json', {'limit_seconds': 10**7, 'used_seconds': 0.0, 'active': None, 'updated_utc': D.now(),
                               'note': 'Budget cap lifted by the user on 2026-10-05; usage recorded.'})
    (out/'executor.lock').touch()
    src = json.loads((after/'manifest.json').read_text())
    inputs = [i for i in src['inputs'] if not i['path'].endswith('.jar')] + [{'path': str(out/'policy.jar'), 'sha256': D.sha(out/'policy.jar')}]
    D.save(out/'manifest.json', {'created_utc': D.now(), 'source': src['source'], 'ledger': str(out/'budget.json'), 'lock': str(out/'executor.lock'),
            'java_home': src['java_home'], 'head_commit': D.command(['git', 'rev-parse', 'HEAD']).strip(), 'inputs': inputs,
            'order': [f'scale-{s}' for s in SCALES], 'after': str(after.resolve()), 'reference_scale_1': str(ROOT/'outputs/performance-20261004-171012-redundancy/full-candidate'),
            'attempts': [], 'status': 'prepared', 'short_limit_seconds': 10**7, 'full_limit_seconds': 10**7})
    print(out)


def wait_for(after):
    """Block until the named earlier campaign (one simulation at a time) has finished, successfully or not."""
    if not after:
        return
    after = Path(after)
    # The earlier runner appends 'exit N' when it stops (success or failure); its ledger must show no active run.
    while not (after/'executor.out').exists() or 'exit' not in (after/'executor.out').read_text() \
            or json.loads((after/'budget.json').read_text())['active']:
        time.sleep(30)


def run(out):
    wait_for(json.loads((out/'manifest.json').read_text()).get('after'))
    m = json.loads((out/'manifest.json').read_text()); register()
    ledger = json.loads(Path(m['ledger']).read_text())
    for name in m['order']:
        if not any(a['name'] == name for a in m['attempts']):
            R.execute(out, m, ledger, name, name, 12, 'full')
    m['status'] = 'complete'; D.save(out/'manifest.json', m)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('action', choices=['prepare', 'run']); ap.add_argument('--run-dir', type=Path, required=True)
    ap.add_argument('--after', type=Path)
    a = ap.parse_args(); prepare(a.run_dir.resolve(), a.after) if a.action == 'prepare' else run(a.run_dir.resolve())

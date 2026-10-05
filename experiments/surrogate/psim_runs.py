#!/usr/bin/env python3
"""L2 end-to-end test: NycPSim hybrid runs vs all-QSim, seed 4711, 12 iterations, online metrics, no event XML.

  qsim-ref   : -Dnyc.psim=cycle:1 (all QSim through the PSim gate) -> must equal full-candidate exactly
  psim3-mean : QSim on iterations 0,3,6,9,11; PSim elsewhere with mean link times (contrib behaviour)
  psim3-geo  : same schedule, geometric-mean link times
  psim6-geo  : QSim on 0,6,11 only
Starts only after the surrogate data executor has finished (memory: one 16 GiB simulation at a time).
"""
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'performance'))
import redundancy_campaign as R
B, D, ROOT = R.B, R.D, R.ROOT
DATA = ROOT/'outputs/surrogate-data-20261005'
BASE = {('controller', 'writeEventsInterval'): '0'}
ARMS = {'qsim-ref': ('cycle:1', 'mean'), 'psim3-mean': ('cycle:3', 'mean'), 'psim3-geo': ('cycle:3', 'geometric'), 'psim6-geo': ('cycle:6', 'geometric')}


def register():
    for name, (schedule, link) in ARMS.items():
        R.ARMS[name] = ('psim.jar', BASE, ['-Dnyc.onlineMetrics=true', f'-Dnyc.psim={schedule}', f'-Dnyc.psim.linkTime={link}'])


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(ROOT/'target/matsim-nyc-modernized-1.0.0.jar', out/'psim.jar')
    code = out/'code'; code.mkdir()
    for p in [Path(__file__), Path(R.__file__), ROOT/'src/main/java/org/c2smart/matsimnyc/NycPSim.java']:
        shutil.copy2(p, code/p.name)
    D.save(out/'budget.json', {'limit_seconds': 10**7, 'used_seconds': 0.0, 'active': None, 'updated_utc': D.now(),
                               'note': 'Budget cap lifted by the user on 2026-10-05; usage recorded.'})
    (out/'executor.lock').touch()
    src = json.loads((DATA/'manifest.json').read_text())
    inputs = [i for i in src['inputs'] if not i['path'].endswith(('.jar', '.py', '.zst'))] + [{'path': str(out/'psim.jar'), 'sha256': D.sha(out/'psim.jar')}]
    D.save(out/'manifest.json', {'created_utc': D.now(), 'source': src['source'], 'ledger': str(out/'budget.json'), 'lock': str(out/'executor.lock'),
            'java_home': src['java_home'], 'head_commit': D.command(['git', 'rev-parse', 'HEAD']).strip(), 'inputs': inputs,
            'order': list(ARMS), 'attempts': [], 'status': 'prepared', 'short_limit_seconds': 10**7, 'full_limit_seconds': 10**7})
    print(out)


def run(out):
    while json.loads((DATA/'manifest.json').read_text()).get('status') != 'complete' or json.loads((DATA/'budget.json').read_text())['active']:
        time.sleep(30)
    m = json.loads((out/'manifest.json').read_text()); register()
    ledger = json.loads(Path(m['ledger']).read_text())
    for name in m['order']:
        if not any(a['name'] == name for a in m['attempts']):
            R.execute(out, m, ledger, name, name, 12, 'full')
    m['status'] = 'complete'; D.save(out/'manifest.json', m)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('action', choices=['prepare', 'run']); ap.add_argument('--run-dir', type=Path, required=True)
    a = ap.parse_args(); prepare(a.run_dir.resolve()) if a.action == 'prepare' else run(a.run_dir.resolve())

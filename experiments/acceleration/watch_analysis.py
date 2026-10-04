#!/usr/bin/env python3
"""Analyze only after all simulations stop, avoiding CPU/I/O timing confounding."""
import json,subprocess,sys,time
from pathlib import Path
import pilot
out=Path(sys.argv[1]).resolve();seen=set()
while True:
    m=json.loads((out/'run_manifest.json').read_text())
    complete={a['stage'] for a in m['attempts'] if a['status']=='complete'}
    if m['status']=='simulations_complete' and complete-seen:
        subprocess.run([sys.executable,'-m','pip','install','-r',str(pilot.ROOT/'requirements.txt')],check=True)
        subprocess.run([sys.executable,str(Path(__file__).with_name('event_metrics.py')),str(out),'--tail','3'],check=True)
        subprocess.run([sys.executable,str(Path(__file__).with_name('check_transfer.py')),str(out)],check=True)
        subprocess.run([sys.executable,str(Path(__file__).with_name('validate.py')),str(out)],check=True)
        subprocess.run([sys.executable,str(Path(__file__).with_name('report.py')),str(out)],check=True)
        seen=complete
    if m['status']=='simulations_complete':
        break
    if any(a['status'] in ('failed','blocked') or (a['status']=='interrupted' and a.get('reason')) for a in m['attempts']):
        raise SystemExit('Simulation stopped; completed results retained')
    time.sleep(15)

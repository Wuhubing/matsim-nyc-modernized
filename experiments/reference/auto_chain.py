#!/usr/bin/env python3
"""Submit validation -> quality gate -> 3 x 100 iterations, with durable receipts and dependency gates."""
import argparse,fcntl,hashlib,json,os,re,subprocess
from pathlib import Path

def save(path,state):
    temp=path.with_suffix('.tmp')
    with temp.open('w') as f:
        json.dump(state,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    temp.replace(path)

def queue(snapshot):
    snapshot=Path(snapshot).resolve()
    manifest=snapshot/'snapshot.json'
    if not manifest.is_file():raise ValueError('A prepared snapshot is required')
    output=Path((snapshot/'output-root.txt').read_text().strip())
    fingerprint=hashlib.sha256(manifest.read_bytes()).hexdigest()
    statefile=snapshot/'auto-chain.json'
    with (snapshot/'auto-chain.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=json.loads(statefile.read_text()) if statefile.exists() else {'snapshot_sha256':fingerprint,'jobs':{}}
        if state['snapshot_sha256']!=fingerprint:raise ValueError('Snapshot changed since this chain was created')
        if state.get('pending_submission'):
            raise ValueError('A previous submission outcome is uncertain; inspect squeue/sacct and auto-chain.json before retrying. No duplicate was submitted.')
        if (snapshot/'baseline-job-id.txt').exists() and 'baseline' not in state['jobs']:
            raise ValueError('A baseline job already exists outside this chain; inspect it before creating another')
        (output/'validation').mkdir(parents=True,exist_ok=True)
        (output/'baseline').mkdir(parents=True,exist_ok=True)
        env=os.environ.copy();env['OUTPUT_ROOT']=str(output)
        for key in ['SEED','PLANS','ITERS','SCENARIO','INNOVATION_UNTIL','SLURM_EXPORT_ENV']:
            env.pop(key,None)
        def submit(role,script,dependency=None):
            if role in state['jobs']:return state['jobs'][role]
            argv=['sbatch','--parsable','-p','mit_normal','--export=ALL',f'--comment=matsim-{snapshot.name}-{role}']
            if dependency:argv += [f'--dependency=afterok:{dependency}','--kill-on-invalid-dep=yes']
            if role=='baseline':argv += ['--array=0-2']
            argv.append(script)
            state['pending_submission']={'role':role,'command':argv}
            save(statefile,state)
            jobenv=env.copy()
            if role=='validation':jobenv['OUTPUT_ROOT']=str(output/'validation')
            result=subprocess.run(argv,cwd=snapshot,env=jobenv,capture_output=True,text=True)
            if result.returncode:
                raise RuntimeError(f'sbatch failed for {role}: {result.stderr.strip()}. Submission intent retained for manual review.')
            job=result.stdout.strip().split(';')[0]
            if not re.fullmatch(r'[0-9]+',job):raise ValueError('Unexpected sbatch reply; check scheduler before retrying')
            state['jobs'][role]=job;state.pop('pending_submission');save(statefile,state)
            if role in ['validation','baseline']:(snapshot/f'{role}-job-id.txt').write_text(job+'\n')
            print(f'{role}: {job}',flush=True)
            return job
        if 'validation' not in state['jobs'] and (snapshot/'validation-job-id.txt').exists():
            job=(snapshot/'validation-job-id.txt').read_text().strip().split(';')[0]
            if not re.fullmatch(r'[0-9]+',job):raise ValueError('Invalid existing validation receipt')
            state['jobs']['validation']=job;save(statefile,state)
        validation=submit('validation','experiments/reference/validation.sbatch')
        gate=submit('gate','experiments/reference/validation_gate.sbatch',validation)
        baseline=submit('baseline','experiments/reference/baseline_after_validation.sbatch',gate)
        print(f'Queued: validation {validation} -> gate {gate} -> baseline array {baseline}.',flush=True)
        print('Baseline: seeds 4711/4712/4713, 100 iterations, 16 CPUs / 32 GiB / 8 hours per task.')
        return state

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('snapshot',type=Path);a=p.parse_args();queue(a.snapshot)

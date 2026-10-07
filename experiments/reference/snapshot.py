#!/usr/bin/env python3
"""Freeze source, inputs, runner and built JAR for queue-safe Slurm submissions."""
import datetime,hashlib,json,os,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def snapshot():
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+f'-{os.getpid()}'
    dest=Path.home()/'matsim-work/snapshots'/stamp;dest.mkdir(parents=True,exist_ok=False)
    for name in ['experiments','scripts','src','scenarios','assumptions','docs']:
        shutil.copytree(ROOT/name,dest/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ['pom.xml','requirements.txt','PROVENANCE.md','README.md','inputs-sha256.json']:shutil.copy2(ROOT/name,dest/name)
    (dest/'target').mkdir();shutil.copy2(ROOT/'target-research/matsim-nyc-modernized-1.0.0.jar',dest/'target/matsim-nyc-modernized-1.0.0.jar')
    shutil.copytree(ROOT/'outputs/reference-inputs',dest/'outputs/reference-inputs')
    (dest/'.venv').symlink_to(ROOT/'.venv',target_is_directory=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    (dest/'changes.patch').write_text(subprocess.check_output(['git','diff','HEAD','--'],cwd=ROOT,text=True))
    (dest/'python-packages.txt').write_text(subprocess.check_output([str(ROOT/'.venv/bin/python'),'-m','pip','freeze'],text=True))
    hashes={str(p.relative_to(dest)):digest(p) for p in dest.rglob('*') if p.is_file() and '.venv' not in p.parts}
    (dest/'snapshot.json').write_text(json.dumps({'commit':commit,'created':stamp,'files_sha256':hashes,'python':str((ROOT/'.venv/bin/python').resolve())},indent=2)+'\n')
    # Unique output root per snapshot; leave all previous experiments in place.
    output=Path.home()/'orcd/scratch/matsim-work'/stamp
    # The sandbox can read scratch but may not write it; create it in the SSH submission step.
    (dest/'output-root.txt').write_text(str(output.resolve())+'\n')
    print(dest)
    return dest
if __name__=='__main__':snapshot()

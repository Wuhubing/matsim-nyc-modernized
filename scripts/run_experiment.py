"""Portable, sequential three-arm runner. Generated outputs are never committed."""
import argparse,datetime,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--iterations',type=int,default=1)
choice=parser.add_mutually_exclusive_group(required=True)
choice.add_argument('--exploratory',action='store_true',help='Explicitly use the paper-derived capacity assumptions')
choice.add_argument('--capacity-factors',type=Path,help='Verified external archive capacity vector, in six-row CSV format')
parser.add_argument('--prepare-only',action='store_true')
parser.add_argument('--heap',default='16g')
args=parser.parse_args()
if args.iterations<1:parser.error('--iterations must be positive')
for rel,expected in json.loads((ROOT/'inputs-sha256.json').read_text()).items():
    with (ROOT/rel).open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=expected:raise SystemExit('Input checksum mismatch: '+rel)
factors=ROOT/'assumptions/paper-capacity-factors.csv' if args.exploratory else args.capacity_factors.resolve()
if not factors.is_file():raise SystemExit('Capacity factor file missing: '+str(factors))
jar=ROOT/'target/matsim-nyc-modernized-1.0.0.jar'
java=Path(os.environ['JAVA_HOME'])/'bin'/('java.exe' if os.name=='nt' else 'java') if os.environ.get('JAVA_HOME') else shutil.which('java')
if not args.prepare_only and (not jar.is_file() or not java):raise SystemExit('Build with Maven and install Java 25 first.')
out=ROOT/'outputs'/('experiment-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
out.mkdir(parents=True)
shutil.copy2(factors,out/'capacity-factors.csv')
manifest={'iterations':args.iterations,'exploratory':args.exploratory,'capacity_sha256':hashlib.sha256(factors.read_bytes()).hexdigest(),'arms':['baseline','schema1','actual2025']}
(out/'experiment.json').write_text(json.dumps(manifest,indent=2))
if not args.prepare_only:shutil.copy2(jar,out/'runner.jar')
source=ROOT/'scenarios/nyc-zip-aligned'
for arm in manifest['arms']:
    root=ET.parse(source/f'config-{arm}.xml').getroot()
    for m in root:
        for p in m.findall('param'):
            k,v=p.get('name'),p.get('value')
            if k in ['inputCountsFile','inputNetworkFile','inputPlansFile','transitScheduleFile','vehiclesFile','tollLinksFile'] and v!='null':p.set('value',(source/v).resolve().as_posix())
            if k=='pricing2025Links':p.set('value',(ROOT/'scenarios/nyc-2025/links.csv').as_posix())
            if k=='archiveCapacityFactors':p.set('value',(out/'capacity-factors.csv').as_posix())
            if k=='outputDirectory':p.set('value',(out/arm).as_posix())
            if k=='firstIteration':p.set('value','0')
            if k=='lastIteration':p.set('value',str(args.iterations-1))
    ET.indent(root)
    config=out/f'config-{arm}.xml'
    config.write_text('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE config SYSTEM "http://www.matsim.org/files/dtd/config_v2.dtd">\n'+ET.tostring(root,encoding='unicode'),encoding='utf-8')
print(out,flush=True)
if args.prepare_only:sys.exit(0)
for arm in manifest['arms']:
    status={'arm':arm,'status':'running','started':datetime.datetime.now().isoformat()}
    statusfile=out/f'status-{arm}.json'
    statusfile.write_text(json.dumps(status,indent=2))
    print('Running '+arm,flush=True)
    with (out/f'{arm}.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([str(java),'-Duser.language=en','-Xmx'+args.heap,'-jar',str(out/'runner.jar'),str(out/f'config-{arm}.xml')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    contents=(out/f'{arm}.log').read_text(encoding='utf-8',errors='replace')
    success=result.returncode==0 and f'ITERATION {args.iterations-1} ENDS' in contents and 'shutdown completed' in contents
    status.update(status='complete' if success else 'failed',exit_code=result.returncode,ended=datetime.datetime.now().isoformat())
    statusfile.write_text(json.dumps(status,indent=2))
    if not success:raise SystemExit('Run failed; inspect '+str(out/f'{arm}.log'))
print('All scenarios completed: '+str(out))

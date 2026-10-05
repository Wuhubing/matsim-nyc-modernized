"""Compile and execute the synthetic regression checks after mvn package."""
from pathlib import Path
import os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
def executable(name):
    return str(Path(os.environ['JAVA_HOME'])/'bin'/(name+'.exe' if os.name=='nt' else name)) if os.environ.get('JAVA_HOME') else name
jar=ROOT/'target/matsim-nyc-modernized-1.0.0.jar'
classes=ROOT/'target/regression-classes';classes.mkdir(parents=True,exist_ok=True)
tests=['VerifyZipAlignment','VerifyRestoration','Verify2025','VerifyBaselineDiagnostics','VerifyFixedPlanGuard','VerifyPSim']
subprocess.run([executable('javac'),'-cp',str(jar),'-d',str(classes)]+[str(ROOT/'scripts'/(t+'.java')) for t in tests],check=True)
for test in tests:subprocess.run([executable('java'),'-Duser.language=en','-cp',os.pathsep.join([str(jar),str(classes)]),'org.c2smart.matsimnyc.'+test],check=True)

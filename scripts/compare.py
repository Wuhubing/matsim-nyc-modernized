"""Plot comparable iteration-zero outputs; event summaries are measured separately."""
import csv,json,sys,subprocess
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter

ROOT=Path(__file__).resolve().parents[1]
if len(sys.argv)!=2:raise SystemExit('usage: python scripts/compare.py OUTPUT_DIRECTORY')
OUT=Path(sys.argv[1]).resolve()
for arm in ['baseline','schema1','actual2025']:
    subprocess.run([sys.executable,str(ROOT/'scripts/measure_pricing_traffic.py'),str(OUT/arm/'ITERS/it.0/BUILT.0.events.xml.zst'),str(ROOT/'scenarios/nyc-2025/cordon-links.csv'),str(OUT/f'{arm}-traffic.json')],check=True,stdout=subprocess.DEVNULL)
ARMS=['baseline','schema1','actual2025']
LABELS=['Baseline','Schema 1','2025 policy']
COLORS=['#64748b','#2563eb','#d97706']
def row(path,delimiter):
    with path.open(encoding='utf-8-sig',newline='') as f:
        return next(r for r in csv.DictReader(f,delimiter=delimiter) if int(r['iteration'])==0)
data={}
for arm in ARMS:
    folder=OUT/arm
    status=json.loads((OUT/f'status-{arm}.json').read_text(encoding='utf-8-sig'))
    assert status['status']=='complete' and status.get('exit_code',status.get('exitCode'))==0
    traffic=json.loads((OUT/f'{arm}-traffic.json').read_text())
    toll=row(folder/'pricing-audit.csv',',')
    modes=row(folder/'BUILT.modestats.csv',';')
    with (folder/'ITERS/it.0/BUILT.0.legHistogram.txt').open() as f:
        hist=list(csv.DictReader(f,delimiter='\t'))
    stuck=sum(int(r['stuck_all']) for r in hist)
    revenue=float(toll['sample_revenue_usd'])
    assert abs(sum(traffic['toll_revenue_by_reference'].values())-revenue)<.05
    data[arm]={'entries':traffic['cordon_car_link_entries'].get('entry',0),
        'minutes':traffic['mean_completed_car_leg_minutes'],'revenue':revenue,
        'stuck':stuck,'car_share':100*float(modes['car']),
        'completed_car_legs':traffic['completed_car_legs']}
assert data['baseline']['revenue']==0
metrics=[('entries','Car entries into the common cordon','Sample crossings',',.0f'),
         ('minutes','Mean completed car-leg time','Minutes',',.1f'),
         ('revenue','Net congestion-charge revenue','Sample USD',',.0f'),
         ('stuck','Stuck departures, all modes','Sample count',',.0f')]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,2,figsize=(12,8))
fig.patch.set_facecolor('#f8fafc')
for ax,(key,title,unit,fmt) in zip(axes.flat,metrics):
    values=[data[a][key] for a in ARMS]
    bars=ax.bar(LABELS,values,color=COLORS,width=.57)
    ax.set_title(title,loc='left',fontweight='bold',pad=18)
    ax.set_ylabel(unit);ax.set_ylim(0,max(values)*1.25 if max(values) else 1)
    ax.yaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
    ax.set_axisbelow(True);ax.grid(axis='y',alpha=.17)
    ax.bar_label(bars,labels=[format(v,fmt) for v in values],padding=5,fontweight='bold')
fig.suptitle('NYC congestion pricing: three-scenario comparison',x=.065,ha='left',fontsize=19,fontweight='bold',y=.985)
fig.text(.065,.935,'Iteration 0 only | Restored ZIP settings + assumed paper-derived capacity factors',color='#475569')
fig.text(.065,.055,'Exploratory, not converged. Same reporting cordon for all scenarios; revenues are not population-expanded.\nTravel times exclude unfinished car legs. Baseline retains existing facility tolls and fixed costs.',fontsize=10,color='#475569')
fig.tight_layout(rect=(.025,.11,1,.91),h_pad=3,w_pad=3)
fig.savefig(OUT/'comparison.png',dpi=180,facecolor=fig.get_facecolor())
fig.savefig(OUT/'comparison.pdf',facecolor=fig.get_facecolor())
(OUT/'comparison.json').write_text(json.dumps({'iteration':0,'metrics':data},indent=2))
lines=['# Exploratory comparison — iteration 0','','![Comparison chart](comparison.png)','',
'All three scenarios completed using the same executable, input population, random seed and non-policy settings. Capacity factors are assumed from the paper, not recovered from the ZIP. Taxi/FHV now use road simulation.',
'','| Metric | Baseline | Schema 1 | 2025 policy |','|---|---:|---:|---:|']
for key,title,unit,fmt in metrics:
    lines.append('| '+title+' ('+unit+') | '+' | '.join(format(data[a][key],fmt) for a in ARMS)+' |')
lines+=['| Car trip share (%) | '+' | '.join(f"{data[a]['car_share']:.3f}" for a in ARMS)+' |','']
for a,label in zip(ARMS[1:],LABELS[1:]):
    lines.append(f"{label}: common-cordon car entries differ by {100*(data[a]['entries']/data['baseline']['entries']-1):+.1f}% from baseline.")
lines+=['','These are first-iteration outcomes, not converged policy effects or observed 2025 outcomes. Initial route preparation can respond to tolls; one iteration does not establish an adapted mode-choice equilibrium. Mean car-leg durations cover completed trips and may be affected by which trips finish. Stuck counts are unfinished departures from leg histograms, not necessarily unique people. Historical facility tolls and fixed costs remain in the baseline; plotted revenue includes added congestion charges only.',
'','Car entries use entered-link events on the same 2025 reporting cordon for every scenario, rather than each policy’s different billing boundary. Event-derived congestion revenue reconciles with the pricing audit for each run. Values are simulated sample totals; no population expansion is applied.','',
'[Run manifest](experiment.json) | [Download PDF](comparison.pdf) | [Metrics](comparison.json)']
(OUT/'comparison.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps(data,indent=2))

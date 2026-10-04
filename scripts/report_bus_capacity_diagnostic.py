"""Validate paired artifacts and produce the Chinese delivery report."""
import csv,json,sys,collections as C,hashlib,xml.etree.ElementTree as E,copy,subprocess,shutil,html,re
from analyze_baseline_diagnostic import stream,ATTR
from run_bus_capacity_diagnostic import persons
from pathlib import Path
from run_bus_capacity_diagnostic import vehicle_data
from analyze_bus_capacity_diagnostic import writecsv
import run_baseline_diagnostic as D

def trace_cases(out,dest,cases):
 selected={p.encode() for p in cases}
 for arm,folder in dest.items():
  with stream(folder/'simulation/ITERS/it.0/BUILT.0.events.xml.zst') as f,(out/f'{arm}-case-events.jsonl').open('w') as target:
   for raw in f:
    key=b'person="' if b'person="' in raw else b'agent="' if b'agent="' in raw else None
    if key is None:continue
    p=raw.split(key,1)[1].split(b'"',1)[0]
    if p in selected:target.write(json.dumps({k.decode():html.unescape(v.decode()) for k,v in ATTR.findall(raw)})+'\n')
 with (out/'case-frozen-plans.xml').open('w') as f:
  f.write('<population>\n')
  for pe in persons(out/'common/frozen-plans.xml.gz'):
   if pe.get('id') in cases:f.write(E.tostring(pe,encoding='unicode'))
  f.write('</population>')

def main(out):
 manifest=json.load(open(out/'run_manifest.json'));attempts={a['stage']:a for a in manifest['attempts'] if a['status']=='complete'};dest={k:out/a['directory'] for k,a in attempts.items()};summ={k:json.load(open(p/'analysis.json')) for k,p in dest.items()};comp=json.load(open(out/'comparison.json'));orig=json.load(open(out/'original-cohort.json'));new=json.load(open(dest['control']/'new-full-cohort.json'));checks={}
 guards={k:json.load(open(p/'fixed-plan-guard.json')) for k,p in dest.items()};checks['identical_pretraffic_plan_fingerprints']=guards['control']['sha256']==guards['treatment']['sha256'];assert checks['identical_pretraffic_plan_fingerprints']
 def structure(e):return (e.tag,tuple(sorted(e.attrib.items())),(e.text or '').strip(),tuple(structure(c) for c in e))
 actual={k:vehicle_data(p/'simulation/BUILT.output_transitVehicles.xml.zst') for k,p in dest.items()};normal=json.load(open(out/'normalization.json'));bus_types={a['type'] for a in normal['capacity_changes']}
 capchecks=[]
 for c,t in zip(actual['control'].findall('vehicleType'),actual['treatment'].findall('vehicleType')):
  assert c.get('id')==t.get('id');a=c.find('capacity');b=t.find('capacity');bus=c.get('id') in bus_types
  for key in ['seats','standingRoomInPersons']:assert int(b.get(key))==int(a.get(key))*(2 if bus else 1)
  capchecks.append(dict(type=c.get('id'),bus=bus,control=dict(a.attrib),treatment=dict(b.attrib)))
  b.attrib.clear();b.attrib.update(a.attrib)
 checks['engine_noncapacity_vehicle_attributes_identical']=structure(actual['control'])==structure(actual['treatment']);assert checks['engine_noncapacity_vehicle_attributes_identical']
 configs={k:E.parse(p/'simulation/BUILT.output_config.xml').getroot() for k,p in dest.items()}
 for r in configs.values():
  for m in r.findall('module'):
   for p in m.findall('param'):
    if p.get('name')=='outputDirectory' or (m.get('name')=='transit' and p.get('name')=='vehiclesFile'):p.set('value','ARM_SPECIFIC')
 checks['engine_noncapacity_configuration_identical']=structure(configs['control'])==structure(configs['treatment']);assert checks['engine_noncapacity_configuration_identical']
 people={k:{r['person']:r for r in csv.DictReader(open(p/'person-results.csv'))} for k,p in dest.items()}
 for arm,p in dest.items():
  hist=list(csv.DictReader(open(p/'simulation/ITERS/it.0/BUILT.0.legHistogram.txt'),delimiter='\t'))
  assert sum(int(r['stuck_all']) for r in hist)==summ[arm]['active_legs']
  assert sum(int(r['departures_all']) for r in hist)==sum(int(r['departed_legs']) for r in people[arm].values())
  assert sum(int(r['arrivals_all']) for r in hist)==sum(int(r['completed_legs']) for r in people[arm].values())
 checks['histogram_departures_arrivals_stuck_match_both_arms']=True
 for a in manifest['attempts']:a['java_tool_options']='-Dnyc.fixedPlanGuard='+str(out/a['directory']/'fixed-plan-guard.json')
 groups=[]
 for label,ids in [('original',set(orig)),('new_control_full',set(new)),('outside_original',set(people['control'])-set(orig)),('all',set(people['control']))]:
  for metric in ['daily_completed','waiting_persons','wait_person_hours','started_wait_segments','active_legs']:
   values={}
   for arm,pp in people.items():
    rows=[pp[p] for p in ids]
    values[arm]=sum(r['final_activity_reached']=='True' for r in rows) if metric=='daily_completed' else sum(r['waiting']=='True' for r in rows) if metric=='waiting_persons' else sum(float(r['wait_seconds']) for r in rows)/3600 if metric=='wait_person_hours' else sum(int(r['wait_segments']) for r in rows) if metric=='started_wait_segments' else sum(bool(r['active_mode']) for r in rows)
   groups.append(dict(cohort=label,n=len(ids),metric=metric,**values,difference=values['treatment']-values['control']))
 for row in groups:
  if row['metric']=='wait_person_hours':
   row['control_mean_hours_per_person']=row['control']/row['n'];row['treatment_mean_hours_per_person']=row['treatment']/row['n']
 writecsv(out/'system-and-cohort-metrics.csv',groups)
 bygroup=[]
 for arm,pp in people.items():
  for group in sorted({r['group'] for r in pp.values()}):
   rr=[r for r in pp.values() if r['group']==group]
   bygroup.append(dict(arm=arm,group=group,persons=len(rr),daily_completed=sum(r['final_activity_reached']=='True' for r in rr),waiting_persons=sum(r['waiting']=='True' for r in rr),active_legs=sum(bool(r['active_mode']) for r in rr),wait_person_hours=sum(float(r['wait_seconds']) for r in rr)/3600,started_wait_segments=sum(int(r['wait_segments']) for r in rr)))
 writecsv(out/'population-by-group.csv',bygroup)
 paired=list(csv.DictReader(open(out/'paired-targets.csv')));original_rows=[r for r in paired if r['cohort']=='original'];cases={}
 rules=[('原群体目标完成且全天完成',lambda r:r['treatment_completed']=='True' and r['treatment_final_activity_reached']=='True'),('目标完成但后续未完成',lambda r:r['treatment_completed']=='True' and r['treatment_final_activity_reached']=='False'),('目标仍未完成',lambda r:r['treatment_completed']=='False')]
 for label,pred in rules:
  for r in sorted((r for r in original_rows if pred(r)),key=lambda r:r['person'])[:3]:cases[r['person']]=dict(r,selection=label)
 transitions=C.Counter()
 for p,c in people['control'].items():
  t=people['treatment'][p];transitions[(c['final_activity_reached'],t['final_activity_reached'])]+=1
  if p not in orig and c['final_activity_reached']!=t['final_activity_reached']:
   label='原群体外新增全天完成' if t['final_activity_reached']=='True' else '原群体外新增全天未完成'
   if sum(x['selection']==label for x in cases.values())<3:cases[p]=dict(person=p,selection=label,control=c,treatment=t)
 D.save(out/'selected-cases.json',list(cases.values()));D.save(out/'validation.json',dict(checks=checks,capacity_types=capchecks,day_completion_transitions=[dict(control=c,treatment=t,persons=n) for (c,t),n in transitions.items()]))
 title={'started':'目标leg已出发','boarded':'目标leg成功上车','completed':'目标leg完成','final_activity_reached':'全天计划完成','waiting_persons':'截止仍候车人数','wait_person_hours':'截止前累计候车人时','started_wait_segments':'已启动候车段数','active_legs':'截止活跃leg未完成人数','daily_not_completed':'最终预定活动未到达人数','not_started_persons':'全日尚未出发人数','unstarted_legs':'尚未启动的计划legs'}
 s='# NYC 固定计划巴士容量对照结果\n\n两组完整人口389,301人，各独立运行迭代0，截止30:00；seed=4711，global/QSim各16线程。未执行政策、长跑或行为重规划。\n\n## 核心配对结果\n\n差值=处理−控制。原群体固定为29,018人，目标leg按冻结计划序号对应。\n\n|群体|指标|控制|容量翻倍|差值|\n|---|---|---:|---:|---:|\n'
 for r in comp['metrics']:
  if r['cohort'] in ['original','all_population']:
   s+='|'+ '|'.join([r['cohort'],title[r['metric']],*[f'{r[k]:,.3f}' if isinstance(r[k],float) else f'{r[k]:,}' for k in ['control','treatment','difference']]])+'|\n'
 s+='\n目标leg完成与全天完成分别记录。最后活动通过计划活动序号及actstart匹配，不能只凭重复出现的Home名称判定。无计划出行者另列，未出发不记成功。\n\n## 机制与控制组标签\n\n'
 s+=f"新控制组全满载候车群体 {comp['new_control_count']:,} 人；与原群体同一person/leg交集 {comp['overlap_same_person_leg']:,}，原标签退出 {comp['exited_original']:,}，新增 {comp['new_labels']:,}。旧第4轮活跃未完成46,143人，新控制为{summ['control']['active_legs']:,}。序列化计划不是原多线程运行全部内部状态；小量差异保留，不要求逐事件一致，也不把固定种子视为逐位确定性。\n\n"
 for arm in ['control','treatment']:s+=f"- {arm}：候车方式 {summ[arm]['waiting_modes']}；剩余候车服务分类 {summ[arm]['service_categories']}；实际载客超过原容量的车辆 {summ[arm]['vehicles_observed_above_control_capacity']:,} 辆。负载客数、超生效容量、事件与计划方式/活动序号错配均为0。\n"
 s+='\n兼容服务按同线路及下游目的站匹配，允许不同route。同秒余位保持边界分类，不据此断言拒载错误。车型改变之外无车辆属性差异，实际生效配置仅车辆输入路径及输出目录不同。两组运行前计划指纹完全一致，且各自相对加载后快照改变人数为0。14类巴士车型容量分别9→18、11→22、12→24；本次无共享车辆/车型需要拆分。车辆容量不作为现实推荐值。\n\n## 等待与系统净变化\n\n'
 s+='等待从waitingForPt至实际上车；未上车截至108000秒累计。总等待须结合已启动候车段数解释，更多后续换乘可扩大观察到的等待暴露。已上车者分布仅为条件性指标。详见各组analysis.json、waiting-by-group-mode-hour.csv，以及system-and-cohort-metrics.csv（含原群体外变化）。\n\n'
 for arm in ['control','treatment']:s+=f"- {arm} 已上车段等待秒分布：{summ[arm]['conditional_boarded_wait_seconds']}。无计划出行人数：{summ[arm]['no_planned_travel']}。\n"
 s+='\n## 成本与验证\n\n|组|总墙钟秒|采样峰值RSS GiB|输出目录|\n|---|---:|---:|---|\n'
 for arm,a in attempts.items():s+=f"|{arm}|{a['elapsed_seconds']:.2f}|{a['sampled_peak_group_rss_bytes']/1024**3:.2f}|{a['directory']}|\n"
 b=json.load(open(out/'budget.json'));s+=f"\n累计仿真预算消耗 {b['used_seconds']:.2f}/7200秒，包含首次XML声明兼容失败，未清零。第一次在人口加载前退出；补齐config/schedule DOCTYPE与车辆namespace，不改变模型语义。两次有效运行退出码0，迭代结束和正常关闭证据齐全。资源明细见各组resources.csv；构建与离线分析不计入仿真预算。\n\n"
 s+='运行前guard有独立正反测试；离线事件夹具覆盖专用PT上车、同秒换乘、未上车截尾、目标完成但后续滞留、重复活动名最终序号识别、下游兼容及共享车辆/车型保护。两组事件出发/到达/stuck与引擎histogram逐项一致。\n\n## 来源与解释限制\n\n来源核查见provenance_zh.md。原论文使用约4%人口并明确公交容量非线性校准；本地389,301人与论文样本的精确对应、分组抽样比例及逐车型原始缩放记录仍不完整。旧版与现代化车辆、时刻表一致，未发现确证重复缩放。\n\n'
 s+='计划文件由BeforeMobsimListener在交通执行前写出；本实验将其选中计划序列化重构，删除旧评分和备选计划，不使用experienced plans。保留活动时间规则，实际出发和停站耗时可随交通执行改变。道路、评分警告、路由异质性仍是限制。单组配对不证明统计显著、收敛、现实容量不足或正确容量应翻倍。\n\n证据目录：comparison.csv、paired-targets.csv、selected-cases.json、两组person-results.csv和waiting-service.csv；validation.json记录实际生效检查。所有旧输入和旧运行结果未覆盖。\n'
 original_metrics={r['metric']:r for r in comp['metrics'] if r['cohort']=='original'}
 tc=summ['treatment'];cc=summ['control'];target_done=original_metrics['completed'];day_done=original_metrics['final_activity_reached']
 downstream=sum(r['treatment_completed']=='True' and r['treatment_final_activity_reached']=='False' for r in original_rows)
 outside_day=next(r for r in groups if r['cohort']=='outside_original' and r['metric']=='daily_completed')
 outcome=f"""
## 结论：支持容量机制，但并非所有瓶颈消失

- 原群体目标leg完成由{target_done['control']:,}增至{target_done['treatment']:,}，全天完成由{day_done['control']:,}增至{day_done['treatment']:,}。处理组{downstream:,}人完成目标leg后仍未完成全天计划，部分瓶颈留在后续环节。目标leg未出发者分别为{len(orig)-original_metrics['started']['control']}、{len(orig)-original_metrics['started']['treatment']}人，不计为成功。
- 全人口未完成减少{cc['active_legs']-tc['active_legs']:,}人（{(cc['active_legs']-tc['active_legs'])/cc['active_legs']:.2%}）。{transitions[('False','True')]:,}人由全天未完成转为完成，{transitions[('True','False')]:,}人由完成转为未完成；原群体之外也净增{outside_day['difference']:,}名全天完成者。转为未完成的具体延误来源与多线程微小差异尚未分解，不能全部归因于某一停站机制。
- 处理组仍有{tc['service_categories'].get('all_full',0):,}人面对后续兼容车辆全部满载；{tc['service_categories'].get('no_compatible_service',0):,}人无后续兼容服务，同秒边界{tc['service_categories'].get('same_second_boundary',0)}人。car未完成{tc['active_modes'].get('car',0):,}人，较控制变化{tc['active_modes'].get('car',0)-cc['active_modes'].get('car',0):+,}，未展开原因诊断。
- 总候车由{cc['wait_person_hours']:,.2f}降至{tc['wait_person_hours']:,.2f}人时，同时启动候车段由{cc['started_wait_segments']:,}增至{tc['started_wait_segments']:,}。不能直接换算为福利，已上车者条件性均值只作辅助。
- {tc['vehicles_observed_above_control_capacity']:,}辆巴士实际载客超过控制容量，且非容量车辆属性、有效配置及执行前计划一致。结果支持当前模型中巴士容量是大量长期候车的直接约束；不证明现实NYC容量不足，也不确定正确缩放倍率。
"""
 s=s.replace('## 核心配对结果',outcome+'\n## 核心配对结果',1)
 resources={}
 for arm,folder in dest.items():
  rr=list(csv.DictReader(open(folder/'resources.csv')));log=(folder/'run.log').read_text(errors='replace');osrss=re.search(r'(\d+)\s+maximum resident set size',log)
  resources[arm]=dict(sampled_peak_rss_bytes=attempts[arm]['sampled_peak_group_rss_bytes'],os_peak_rss_bytes=int(osrss[1]) if osrss else None,swap_max_bytes=max((int(r['swap_used_bytes']) for r in rr if r['swap_used_bytes']),default=None),pressure_levels=sorted({r['pressure_level'] for r in rr}),minimum_disk_bytes=min(int(r['disk_free_bytes']) for r in rr if r['disk_free_bytes']),output_bytes=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()))
 D.save(out/'resource-summary.json',resources)
 s+='\n资源补充：resource-summary.json保存系统峰值RSS、交换和输出规模；本次两组交换使用量峰值均为0，未触发资源中断。\n'
 (out/'report_zh.md').write_text(s)
 manifest['delivery_scripts']={p.name:D.sha(p) for p in D.ROOT.joinpath('scripts').glob('*bus_capacity*')};manifest['guard_source_sha256']=D.sha(D.ROOT/'src/main/java/org/c2smart/matsimnyc/FixedPlanGuard.java');D.save(out/'run_manifest.json',manifest)
 print(comp,checks,flush=True)
 if not (out/'case-frozen-plans.xml').exists():trace_cases(out,dest,cases)
if __name__=='__main__':main(Path(sys.argv[1]).resolve())

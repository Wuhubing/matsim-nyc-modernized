#!/usr/bin/env python3
"""Generate a Chinese pilot report from recorded evidence, without rerunning MATSim."""
import csv,json,sys
from pathlib import Path
import pilot

def report(out):
    results=pilot.summarize(out);m=json.loads((out/'run_manifest.json').read_text())
    ledger=json.loads((out/'budget.json').read_text());api=json.loads((out/'api-budget.json').read_text())
    choice=json.loads((out/'llm-selection.json').read_text()) if (out/'llm-selection.json').exists() else None
    lines=['# MATSim NYC 初始化加速先导实验','',
      '**这是单一收费情景、单一种子的有限轮次试验；没有已验证收敛的参照，不报告已证明的加速倍率。**','',
      '源情景为无新增拥堵收费的五轮基准运行，目标为仓库中的2025收费规则。两者沿用历史纽约需求；这不是对真实2025年城市出行的校准或预测验证。','',
      '各组采用相同政策、输入人口、道路/公交容量、评分、随机种子、线程和轮数。不同的是初始选中计划。单次顺序运行没有随机化执行顺序或多种子重复，耗时差仅作描述性比较。旧分数和备选计划已移除；它不是完整仿真状态恢复。','',
      f"仿真预算已用 {ledger['used_seconds']/60:.2f} / {ledger['limit_seconds']/60:.0f} 分钟。准备耗时 {m['preparation_seconds']:.1f} 秒另计。API 用量估算 ${api['measured_usd']:.6f}，保守预留 ${api['reserved_usd']:.2f} / $20。",'',
      f"历史源运行成本约 {m['source_simulation_seconds']/60:.2f} 分钟；本次复用已有结果，但评估首次使用总成本时必须计入，跨多个目标复用时应摊销。",'']
    if all(a in results for a in ('cold','warm_early','warm_latest')):
        c,e,w=(results[a] for a in ('cold','warm_early','warm_latest'))
        lines += [f"**实际发现：**MATSim启动至首轮前耗时：冷启动 {c['pre_iteration_seconds']:.0f} 秒，早期/最新热启动 {e['pre_iteration_seconds']:.0f}/{w['pre_iteration_seconds']:.0f} 秒。该项不包含外部计划提取、历史源生成和LLM调用，不能直接当作端到端节省。",'']
        if not any(r['finite_cold_reference']['final_within_tolerances'] for r in (e,w)):
            lines += ['两种热启动末段均未同时落入冷启动四指标容差。启动阶段耗时减少，尚未证明达到同样结果质量的总成本降低。','']
        if all(r['first_stability_screen']==m['iterations']-1 for r in (c,e,w)):
            lines += ['原三组首次稳定筛查都在最后一轮，没有独立后续轮次验证早停。','']
    if 'guarded_warm_latest' in m['initialization']:
        g=m['initialization']['guarded_warm_latest']
        lines += [f"追加分支 guarded_warm_latest：保留 outside 组在目标情景冷启动、交通仿真开始前已准备的计划，仅迁移其他组。迁移准备另耗 {g['preparation_seconds']:.1f} 秒。它是发现固定组路线差异后的探索性跟进，不是原三组事前设定比较。这里复用了本次 cold 的首轮前路由准备产物；未来独立部署必须另外完成并计入该背景路由准备，不能当作免费初始化。",'']
    if choice:lines += [f"LLM 事前选择：**{choice['candidate']}**（{choice['model']}）。",'',choice['reason'],'',
      '该选择只引用对应初始化组的结果；不是额外独立重复，也不能凭这一个选择证明 LLM 优于固定规则。','', 'LLM 理由中的“方式比例持续改善”没有预先定义何为改善，car占比也并非单调变化；对最新计划偏差的担忧尚未被实验证实。保留原回答供审计，不将其叙述当作证据。','']
    enriched=out/'llm-selection-constraints.json'
    if enriched.exists():
        ec=json.loads(enriched.read_text())
        lines += [f"补充静态约束后的第二次 LLM 选择：**{ec['candidate']}**。这是执行中发现非创新组风险后追加的探索性 context 对照，不是第一版事前设定比较；请求未包含目标情景结果。",'']
    transfer=out/'transfer-diagnostic.json'
    if transfer.exists():
        tr=json.loads(transfer.read_text())
        lines += ['非创新 outside 组的道路路线检查：','', '| 初始化 | 相对冷启动初始car路线不同人数 | 本组运行中改变car路线人数 | 末轮相对冷启动car路线不同人数 | 全人口准备后属性不同人数 |','|---|---:|---:|---:|---:|']
        for arm,t in tr['arms'].items():lines.append(f"|{arm}|{t['initial_car_route_signatures_different_from_cold']}|{t['car_route_signatures_changed_during_target_run']}|{t['final_car_route_signatures_different_from_cold']}|{t['prepared_person_attribute_differences_from_cold']}|")
        lines += ['', '如果旧路线差异在不创新的人群中持续存在，不能把它解释为仅仅收敛速度不同。固定背景人群的追加组用于检查这一机制；它仍不能替代更长、多种子的共同参照。','']
        if 'guarded_warm_latest' in results:
            g=results['guarded_warm_latest'];t=tr['arms'].get('guarded_warm_latest',{})
            if t.get('final_car_route_signatures_different_from_cold')==0 and not g['finite_cold_reference']['final_within_tolerances']:
                lines += ['追加组已消除 outside 组相对冷启动的汽车路线差异，但末段仍未同时落入冷启动四指标容差。这说明固定背景路线并非本次终点差异的唯一解释；适应深度、路径依赖和有限轮次参照仍需检查，不能据此判定哪组更接近现实。','']
    lines+=['| 初始化 | 仿真耗时分钟 | 末三轮平均分 | car 比例 | PT 比例 | 未完成均值 | 末三轮通过简易稳定筛查 |','|---|---:|---:|---:|---:|---:|---|']
    for arm,r in results.items():
        t=r['final_three_mean'];lines.append(f"|{arm}|{r['elapsed_seconds']/60:.2f}|{t['score']:.3f}|{t['car_share']:.2%}|{t['pt_share']:.2%}|{t['unfinished']:.0f}|{'是' if r['tail_stable'] else '否'}|")
    lines += ['', '| 初始化 | 首轮前准备秒 | 平均每轮秒 | 峰值采样RSS GiB |','|---|---:|---:|---:|']
    for arm,r in results.items():lines.append(f"|{arm}|{r['pre_iteration_seconds']:.1f}|{r['mean_iteration_seconds']:.1f}|{r['peak_rss_gib']:.2f}|")
    lines+=['','稳定筛查只看最近三轮范围：score≤0.25、car/PT比例各≤0.5个百分点、未完成≤1,500人。这是事先给定的筛查阈值，不是收敛或现实误差保证。','',
      '| 初始化 | 首次通过筛查的轮次 | 末三轮对照（非独立时明确标记） |','|---|---:|---|']
    for arm,r in results.items():lines.append(f"|{arm}|{r['first_stability_screen'] if r['first_stability_screen'] is not None else '未通过'}|{r['screen_matches_tail'] if r['independent_future_tail_available'] else '无独立后续三轮可验证'}|")
    lines+=['','上述为离线回放，没有真正提前终止任何组。当前筛查不包含全部路段流量与群体服务约束，不能直接作为线上停止规则。末段也包含按0.8比例关闭创新的影响：停止尝试新计划后，平均分的跳升与曲线变平可能反映策略切换，不能据此断言找到均衡或最优解。','']
    lines += ['| 初始化 | 终点是否接近冷启动末三轮（四指标） | 首个且后续保持接近的窗口结束轮次 |','|---|---|---:|']
    for arm,r in results.items():
        cr=r.get('finite_cold_reference',{})
        lines.append(f"|{arm}|{'是' if cr.get('final_within_tolerances') else '否'}|{cr['sustained_matching_window_end'] if cr.get('sustained_matching_window_end') is not None else '未达到'}|")
    lines += ['', '此共同参照仅为冷启动有限轮次末段，不是独立收敛真值；这里的回看匹配也不能作为在线停止保证。且只覆盖四项筛查指标，完整政策评价还需下方事件指标。','']
    path=out/'event-metrics.json'
    if path.exists():
        records=json.loads(path.read_text());lines+=['| 初始化 | 末三轮收费区私家车进入次数均值 | 已完成car leg均时/分钟 | 含截尾候车/人时 | 未上车人数 | 新增净收费/美元 |','|---|---:|---:|---:|---:|---:|']
        for arm in results:
            rr=[r for r in records if r['arm']==arm]
            if not rr:continue
            mean=lambda k:sum(r[k] for r in rr)/len(rr)
            lines.append(f"|{arm}|{mean('private_car_entry_crossings'):.0f}|{mean('mean_completed_car_leg_seconds')/60:.2f}|{mean('censored_wait_person_hours'):.0f}|{mean('waiting_at_cutoff'):.0f}|{mean('net_congestion_revenue'):.2f}|")
        lines+=['','上述数值是样本人群模型输出，没有人口扩展；均值是逐轮指标的算术平均。已完成行程均时排除了未完成行程，不是固定人群拥堵指标。收费区采用2025情景的进入link集合，计穿越次数而非独立人数。','']
        if all(a in results for a in ('warm_latest','guarded_warm_latest')):
            plain=[r for r in records if r['arm']=='warm_latest'];guarded=[r for r in records if r['arm']=='guarded_warm_latest']
            close=all(abs(results['warm_latest']['final_three_mean'][k]-results['guarded_warm_latest']['final_three_mean'][k])<=tol for k,tol in pilot.TOLERANCES.items())
            if len(plain)==len(guarded)==3 and close:
                avg=lambda rr,k:sum(r[k] for r in rr)/len(rr)
                old=avg(plain,'private_car_entry_crossings');new=avg(guarded,'private_car_entry_crossings')
                revenue=avg(guarded,'net_congestion_revenue')-avg(plain,'net_congestion_revenue')
                lines += [f"**四项总体指标接近，政策指标仍可能不同：**普通最新热启动与限定迁移组的末三轮平均分、car/PT比例、未完成差值全部落入本次四项容差，但收费区汽车进入次数从 {old:.0f} 变为 {new:.0f}（{(new/old-1)*100:+.2f}%），净收费差 {revenue:+.2f} 美元。这里只报告单次观察差异，尚未给该政策指标建立合格阈值或统计显著性；它说明总体指标筛查不能替代政策相关检查。",'']
    lines+=['## 可得结论与下一步','',
      '本次可检验热启动是否改变初始状态、有限轮次终点是否一致、简单稳定筛查是否提前触发。若末段仍变化或不同初始化终点不同，就不能把少跑几轮解释为同样精度。','',
      '下一步应在多个政策和多个种子上建立更长且稳定性经过检查的参照，评估达到共同结果容差的时间，并加入源情景生成、计划迁移和控制器开销。LLM 与固定最新、随机选择及数值检索都应比较。','',
      '产物：run_manifest.json、budget.json、api-budget.json、llm-request.json、llm-selection.json、trajectory.csv、summary.json、event-metrics.json、各组配置/日志/资源记录。原始事件保留供复核。']
    verification=out/'validation.json'
    if verification.exists():
        v=json.loads(verification.read_text())
        if {a['arm'] for a in v['arms']}==set(results):
            lines += ['', f"核验：{len(v['arms'])} 组有效配置仅初始化路径和输出路径不同；输入哈希保持一致；每组末三轮事件计数与仿真行程直方图、净收费审计记录吻合。预算记录无活动仿真。核验详情见 validation.json。"]
    if results:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        rows=list(csv.DictReader((out/'trajectory.csv').open()))
        fig,axes=plt.subplots(2,2,figsize=(10,7))
        for ax,key,label in zip(axes.flat,['score','car_share','pt_share','unfinished'],['Executed score','Car share','Public transit share','Unfinished persons']):
            for arm in results:
                rr=[r for r in rows if r['arm']==arm];ax.plot([int(r['iteration']) for r in rr],[float(r[key]) for r in rr],marker='.',linestyle='--' if arm.startswith('guarded') else '-',label=arm)
            off=next(iter(results.values())).get('innovation_off_from')
            if off is not None:ax.axvline(off-.5,color='gray',linestyle='--',alpha=.7)
            ax.set(xlabel='Iteration (gray line: innovation disabled)',ylabel=label);ax.grid(alpha=.25)
        axes[0,0].legend();fig.suptitle('Initialization pilot — finite horizon, not a convergence benchmark');fig.tight_layout();fig.savefig(out/'trajectories.png',dpi=160);plt.close(fig)
        lines+=['','![初始化轨迹](trajectories.png)']
    (out/'report_zh.md').write_text('\n'.join(lines)+'\n')
    print(out/'report_zh.md')
if __name__=='__main__':report(Path(sys.argv[1]).resolve())

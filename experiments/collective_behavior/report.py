"""Reports preserve incomplete cells and use whole-run replication."""
import collections
import json
from pathlib import Path
import statistics as S
from budget import read, save
from metrics import interval, summarize
from environment import Config


def records(path):
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def report(out):
    manifest=read(out/'manifest.json')
    runs=read(out/'numerical-summary.json') if (out/'numerical-summary.json').exists() else []
    grouped=collections.defaultdict(list)
    for r in runs:
        key=(r['config']['scenario'],r['config']['strength'],r['information'],r['method'])
        grouped[key].append(r['metrics'])
    cells=[]
    for key,rows in grouped.items():
        cell=dict(zip(('scenario','strength','information','method'),key))
        for metric in ('post_mean_cost','post_p90_person_cost','excess_cost','switch_fraction','flow_volatility'):
            cell[metric]=interval([r[metric] for r in rows])
        cells.append(cell)
    replay=records(out/'replay.jsonl'); baseline=records(out/'replay-baselines.jsonl')
    rg=collections.defaultdict(list)
    for r in replay+baseline: rg[(r['method'],r['information'])].append(r)
    replay_cells=[]
    for (method,info),rows in sorted(rg.items()):
        # Repeated samples of the same frozen state are clustered, not independent observations.
        bystate=collections.defaultdict(list)
        for r in rows: bystate[r['state']].append(r['score']['counterfactual_regret'])
        valid=[r for r in rows if r['score']['valid']]
        identifiable=[r for r in valid if r['score']['contemporaneously_identifiable']]
        replay_cells.append({'method':method,'information':info,'calls':len(rows),'states':len(bystate),
            'invalid':len(rows)-len(valid),'conditional_regret':interval([S.mean(v) for v in bystate.values()]),
            'prediction_mae':S.mean(r['score']['prediction_mae'] for r in valid) if valid else None,
            'identifiable_n':len(identifiable),
            'identified_accuracy':S.mean(r['score']['cause_correct'] for r in identifiable) if identifiable else None,
            'abstention_rate':S.mean(r['score']['abstained'] for r in valid) if valid else None})
    worlds=collections.defaultdict(list)
    for r in records(out/'closed-steps.jsonl'): worlds[r['world']].append(r)
    closed=[]
    for world,steps in sorted(worlds.items()):
        cfg=Config(**steps[0]['config']); rows=[r['row'] for r in steps]
        closed.append({'world':world,'method':steps[0]['method'],'config':steps[0]['config'],
            'seed':steps[0]['seed'],'days':len(rows),
            'metrics':summarize(rows,cfg) if len(rows)==cfg.days else None})
    # A fair paired descriptive comparison only on intersecting completed sample IDs.
    idx={(r['state'],r['repeat'],r['information'],r['method']):r for r in replay}
    paired={}
    for info in ('time','flow'):
        state_diffs=collections.defaultdict(list)
        for (state,repeat,information,method),r in idx.items():
            other=idx.get((state,repeat,information,'diagnose'))
            if information==info and method=='direct' and other:
                state_diffs[state].append(other['score']['counterfactual_regret']-r['score']['counterfactual_regret'])
        if state_diffs: paired[info]=interval([S.mean(v) for v in state_diffs.values()])
    decision='证据不足'
    explanation='小环境可检验机制，但尚不足以证明 LLM 的独特价值或 NYC 政策意义。'
    if len(replay)==720:
        matching=[c for c in replay_cells if c['information']=='flow']
        best_simple=min((c['conditional_regret']['mean'] for c in matching if c['method'] in ('random','smooth','estimate')),default=float('inf'))
        best_llm=min((c['conditional_regret']['mean'] for c in matching if c['method'] in ('direct','diagnose')),default=float('inf'))
        if best_simple<=best_llm:
            decision='缩小或转向'
            explanation='固定历史中，至少一个简单基线的平均行动遗憾不高于 LLM；不支持直接扩大 LLM 系统。该比较是探索性、非显著性结论。'
    result={'manifest_status':manifest['status'],'numerical':cells,'replay':replay_cells,
            'paired_diagnose_minus_direct':paired,'closed':closed,'decision':decision,'explanation':explanation}
    save(out/'results.json',result)
    lines=['# 可控选路实验：第一轮筛选报告','',f'**判断：{decision}。** {explanation}','',
        f"执行状态：{manifest['status']}；运行 {manifest.get('elapsed_seconds',0):.1f} 秒。",
        f"数值实验 {len(runs)} / 1260 次；固定历史 LLM 比较 {len(replay)} / 720 次；闭环完整运行 {sum(c['days']==30 for c in closed)} / 18 次。",'',
        '## 设计与解释边界','',
        '24 人、30 天；第 11–20 天干预，第 21 天恢复。两条路线的旅行时间为 10 + 0.5×总流量/容量系数、16 + 0.25×总流量。只有第一条路线变化。低/高强度容量为 2/3、1/2，背景流量为 8、16；共同变化叠加两者。无变化只运行一个强度，避免重复伪样本。',
        '政策只收到自身最近五次行动和实际旅行时间；flow 条件另提供两路总流量。不给事件日程、容量或原因标签。数值估计使用已知成本函数；它不是隐藏状态 oracle。',
        '配对案例仅证明：在固定其他人下一步行动的干预下，原因差异可能改变较优路线。它不证明 agent 能预测其他人，也不证明该流量变化会自发发生。',
        '回放状态来自预先指定的平滑学习轨迹，四类场景各 15 个；回放遗憾固定其他人的下一步行动，不能直接当作闭环改善。',
        '诊断正确率仅在最近一次走 A 且有同期总流量的直接可识别子集上报告；其余子集不强迫正确原因标签。time 条件允许不确定，但不是所有历史都同样不可识别。','',
        '## 数值基线','', '|场景/强度|信息|方法|变化后人均累计分钟|超出系统下界|流量波动|', '|---|---|---|---:|---:|---:|']
    for c in cells:
        lines.append(f"|{c['scenario']}/{c['strength']}|{c['information']}|{c['method']}|{c['post_mean_cost']['mean']:.2f}|{c['excess_cost']['mean']:.2f}|{c['flow_volatility']['mean']:.3f}|")
    lines+=['','每格 30 个独立群体种子。完整区间及尾部成本见 results.json；区间为运行级均值的描述性正态近似，不是多重比较校正后的推断。系统下界允许中央控制分流，仅作参照。','',
        '## 固定历史比较','', '|方法|信息|完成调用|无效|条件行动遗憾（分钟）|可识别子集正确率|', '|---|---|---:|---:|---:|---:|']
    for c in replay_cells:
        acc='—' if c['identified_accuracy'] is None else f"{c['identified_accuracy']:.1%}"
        lines.append(f"|{c['method']}|{c['information']}|{c['calls']}|{c['invalid']}|{c['conditional_regret']['mean']:.3f}|{acc}|")
    lines+=['','同一状态的三次采样先取平均，不能当三个独立交通情景。比较不含提示调参；直接选择与先诊断的区别也包含输出字段顺序，不能直接归因于内部推理。',
            '无效输出保留在行动指标中，沿用上一行动（首次则随机），其预测与诊断不计为有效；没有自动重试。未发出的预算受限调用不做行为回填。','',
            '## 闭环与预算','']
    for c in closed: lines.append(f"- {c['world']}：{c['days']}/30 天；"+('完整' if c['metrics'] else '未完成，不参与完整回合排名'))
    api=manifest.get('api',{})
    lines += ['',f"API 估计费用 ${api.get('estimated_usd',0):.6f}；未知结果预留 ${api.get('unknown_reserved_usd',0):.6f}；请求数 {api.get('calls',0)}。",
        '预算按实际 token 的标准输入价格保守估计，不抵扣缓存折扣，非账户账单核对。共享额度采用预占；若别的执行器占锁，未退还部分继续保守计入。',
        '若闭环未完成，只报告实际覆盖，不能从回放结果声称群体优势。新增提示、模型和更多调用需要单独记录，不能覆盖本批次。','',
        '## 下一步','',
        explanation,
        '只有发现重复出现且简单基线不能处理的现象，才进一步检查其是否影响收费政策指标；此次没有 NYC 验证，也不将模拟日解释为 MATSim 迭代轮次。','',
        '## 复现','',
        '本目录 code/ 为执行代码快照，manifest.json 保存哈希，numerical.jsonl.gz 保存数值逐步日志，replay-states.json 保存配对回放输入，calls/ 保存实际请求、响应、使用量与失败状态。closed-steps.jsonl 保留已完成的联合行动。','',
        '官方调用与价格依据：[GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini)、[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)。']
    (out/'report_zh.md').write_text('\n'.join(lines)+'\n')
    if cells:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(1,2,figsize=(12,4.8))
        groups=sorted({(c['scenario'],c['strength']) for c in cells})
        for method in ('random','smooth','estimate'):
            values=[next(c['excess_cost']['mean'] for c in cells if (c['scenario'],c['strength'])==g and c['method']==method and c['information']=='flow') for g in groups]
            axes[0].plot(range(len(groups)),values,'o-',label=method)
        axes[0].set_xticks(range(len(groups)),[f'{a}\n{b}' for a,b in groups]); axes[0].set_ylabel('Post-event excess minutes / person'); axes[0].set_title('Numerical baselines (30 seeds)'); axes[0].legend()
        if replay_cells:
            labels=[c['method']+'\n'+c['information'] for c in replay_cells]
            axes[1].bar(range(len(labels)),[c['conditional_regret']['mean'] for c in replay_cells]); axes[1].set_xticks(range(len(labels)),labels,rotation=60,ha='right'); axes[1].set_ylabel('Conditional regret (minutes)')
        axes[1].set_title(f'Frozen-history replay ({len(replay)}/720 LLM calls)')
        fig.tight_layout(); fig.savefig(out/'comparison.png',dpi=160); plt.close(fig)

if __name__=='__main__':
    import sys
    report(Path(sys.argv[1]))

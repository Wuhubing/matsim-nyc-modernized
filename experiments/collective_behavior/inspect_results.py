"""Post-run descriptive diagnostics; never dispatches simulation or API calls."""
import collections
import gzip
import json
from pathlib import Path
import statistics as S
import sys


def inspect(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    worlds=collections.defaultdict(list)
    for line in (out/'closed-steps.jsonl').read_text().splitlines():
        step=json.loads(line); worlds[step['world']].append(step)
    conditions=sorted({(v[0]['config']['scenario'],v[0]['config']['strength']) for v in worlds.values()})
    fig,axes=plt.subplots(len(conditions),2,figsize=(12,3.5*len(conditions)),squeeze=False)
    colors={'direct':'#0072B2','diagnose':'#D55E00','random':'#777777','smooth':'#009E73','estimate':'#CC79A7'}
    summaries=[]
    for name,steps in sorted(worlds.items()):
        first=steps[0]; condition=(first['config']['scenario'],first['config']['strength'])
        j=conditions.index(condition); method=first['method']; rows=[s['row'] for s in steps]
        days=[r['day'] for r in rows]
        travel=[S.mean(r['costs'][a] for a in r['actions']) for r in rows]
        shares=[r['endogenous_flow'][0]/24 for r in rows]
        for ax,values in zip(axes[j],(travel,shares)):
            ax.plot(days,values,color=colors[method],alpha=.45,label=method if first['seed']==0 else None)
        post=[s for s in steps if s['row']['day']>=11]
        errors=[]; invalid=0
        for s in post:
            for choice in s['choices']:
                if choice.get('valid'):
                    errors.append(S.mean(abs(p-t) for p,t in zip(choice['predicted_costs'],s['row']['costs'])))
                else: invalid+=1
        # Per-world diagnostic summaries; agents are not statistical replicates.
        summaries.append({'world':name,'days_observed':len(rows),'post_days':len(post),
                          'complete':len(rows)==30,'invalid_post_decisions':invalid,
                          'observed_post_prediction_mae':S.mean(errors) if errors else None})
    baseline=collections.defaultdict(list)
    with gzip.open(out/'numerical.jsonl.gz','rt') as f:
        for line in f:
            run=json.loads(line); condition=(run['config']['scenario'],run['config']['strength'])
            if condition in conditions and run['information']=='flow':
                baseline[(condition,run['method'])].append(run['rows'])
    for (condition,method),runs in baseline.items():
        j=conditions.index(condition)
        mean_cost=[S.mean(S.mean(r[d]['costs'][a] for a in r[d]['actions']) for r in runs) for d in range(30)]
        mean_share=[S.mean(r[d]['endogenous_flow'][0]/24 for r in runs) for d in range(30)]
        for ax,values in zip(axes[j],(mean_cost,mean_share)):
            ax.plot(range(1,31),values,'--',color=colors[method],linewidth=1.4,label=method+' (30-run mean)')
    for j,condition in enumerate(conditions):
        for k,ax in enumerate(axes[j]):
            if condition[0]!='none': ax.axvspan(10.5,20.5,color='gray',alpha=.1)
            ax.set_xlim(1,30); ax.set_xlabel('Day'); ax.set_title(f'{condition[0]} / strength {condition[1]}')
            ax.set_ylabel('Mean travel minutes' if k==0 else 'Route A share')
            if k==1: ax.set_ylim(0,1)
        axes[j,0].legend(fontsize=7)
    fig.suptitle('Closed-loop observed trajectories: each solid line is one group run; gray = intervention')
    fig.tight_layout(); fig.savefig(out/'closed-trajectories.png',dpi=160); plt.close(fig)
    (out/'closed-diagnostics.json').write_text(json.dumps(summaries,indent=2)+'\n')
    if (out/'results.json').exists() and 'elapsed_seconds' in json.loads((out/'manifest.json').read_text()):
        result=json.loads((out/'results.json').read_text())
        notes=['## 补充筛选分析','',
               '固定历史的“行动遗憾”是固定其他 23 人行动后，所选路线相对较好路线多花的分钟数；它不是城市总收益。','']
        for info,cell in result['paired_diagnose_minus_direct'].items():
            notes.append(f"- {info} 信息：先诊断减去直接选择的平均遗憾差为 {cell['mean']:.3f} 分钟，描述性区间 [{cell['low']:.3f}, {cell['high']:.3f}]；正数表示先诊断较差。")
        notes+=['','本批次的比较不支持把“先解释原因”当成已验证的改进。不同方法还改变了输出字段顺序，因此不能将差异唯一归因于诊断过程。',
                '', '### 原因判断的描述性检查','',
                '以下计数仅限具有同期 A 路旅行时间和流量的可识别样本；同一状态重复调用不能视为独立场景。','']
        replay=[json.loads(l) for l in (out/'replay.jsonl').read_text().splitlines()]
        for method in ('direct','diagnose'):
            rows=[r for r in replay if r['method']==method and r['score']['valid'] and r['score']['contemporaneously_identifiable']]
            wrong=[r for r in rows if not r['score']['cause_correct'] and r['choice']['cause']!='insufficient']
            counts=collections.Counter(r['choice']['cause'] for r in rows)
            notes.append(f"- {method}：{len(rows)} 次可识别有效回答，原因输出计数 {dict(counts)}；错误且未回答信息不足的次数为 {len(wrong)}。")
        notes+=['','原因标签错误是可观察的，但生成标签不等于模型内部真正使用的机制。要研究“错误归因是否导致群体失败”，下一阶段需要固定观察、单独干预诊断内容，并与直接算式和随机分流对照；本批次没有完成这一因果验证。',
                '', '### 群体轨迹','',
                '![群体轨迹](closed-trajectories.png)', '',
                '实线每条为一次 LLM 群体运行，虚线为数值基线 30 次运行的均值。虚线隐藏了跨运行波动，不能仅凭线条平滑程度比较稳定性。未完整运行的轨迹只展示已观察天数。',
                '', '|情景/强度|方法|完整群体数|变化后人均累计分钟|人均累计成本 P90|换路比例|路线 A 份额标准差|',
                '|---|---|---:|---:|---:|---:|---:|']
        groups=collections.defaultdict(list)
        for row in result['closed']:
            if row['metrics'] is not None:
                groups[(row['config']['scenario'],row['config']['strength'],row['method'])].append(row['metrics'])
        for (scenario,strength,method),rows in sorted(groups.items()):
            means=[S.mean(r[k] for r in rows) for k in ('post_mean_cost','post_p90_person_cost','switch_fraction','flow_volatility')]
            notes.append(f"|{scenario}/{strength}|{method}|{len(rows)}|"+'|'.join(f'{v:.3f}' for v in means)+'|')
        if not groups:
            notes=notes[:-2]
            notes.append('没有完整 30 天的闭环运行，因此不生成完整回合成本、尾部或换路排名。已观察轨迹和逐群体预测误差仍保留。')
        manifest=json.loads((out/'manifest.json').read_text())
        if manifest['status']=='budget_or_transport_stop' and manifest['api']['errors']<3 and manifest['api']['estimated_usd']<manifest['limits']['usd']-1:
            notes+=['','本轮因时间保护停止：请求启动前预留 30 秒用于在途请求结束，未追加调用补齐天数。']
        notes+=['','统计单位为群体运行，不是把 24 个 agents 当作 24 个独立重复。预测误差的逐群体结果见 closed-diagnostics.json。',
                '', '目前不进入 MATSim 扩展：尚未证明这种现象超出简单方法的处理能力，也未验证它会改变拥堵收费的政策判断。可以保留“共同信息下的同步反应”和“错误归因”的候选问题，先做更窄的机制对照。']
        path=out/'report_zh.md'; original=path.read_text().split('\n## 补充筛选分析')[0]
        path.write_text(original.rstrip()+'\n\n'+'\n'.join(notes)+'\n')
    return summaries


if __name__=='__main__':
    result=inspect(Path(sys.argv[1])); print(json.dumps(result,indent=2))

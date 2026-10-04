# 仿真过程中的冗余：逐轮离线度量

分支 `perf/simulation-redundancy`。只读取已完成运行的逐轮事件，**不新增仿真、不占用仿真预算**。
数据：`outputs/acceleration-pilot-20261004-032117/cold-attempt-1`（2025 收费、全人口 389,301、种子 4711、12 轮，
第 0–8 轮有创新，之后只做计划选择）。结果：`outputs/redundancy-20261004/cold/`。

## 问题

MATSim 每轮都会把全部人口完整重跑一遍交通仿真。上一轮已经算过的内容，有多少在下一轮又被原样或近似地重算？
冗余属于哪几类？每一类适合什么加速方式？这一节把加速问题抽象成可度量的对象，作为后续方法研究的前提。

## 定义

对每一轮 i 和每个人，从事件流提取：

- **选择签名**：各 leg 的方式 + 实际道路路线（link 序列）。它由 replanning 决定。注意：只改出发时间（TimeAllocationMutator）的变化不算选择变化。
- **结果签名**：此人所有事件的时间戳（出发、到达、活动、上下车、驶入 link 等）。它由交通仿真里的交互决定。
- **路段-小时状态**：每个 (link, 小时) 的驶入车辆数与平均通行时间。

相邻两轮比较，把每个人分成三类：完全重放（选择与结果都相同）、选择相同但结果变化、选择变化。

## 结果（cold，相邻轮次）

| 轮 | 完全重放 | 选择同·结果变 | 选择变 | 选择变中“回到旧计划”占比 | 选择同者 \|ΔT\|≤60s | 选择同者 \|ΔT\|>15min | 驶入发生在变化≤5% 的路段-小时 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 13.0% | 75.1% | 11.9% | 0% | 52.8% | 23.5% | 34.1% |
| 4 | 10.7% | 69.9% | 19.4% | 44.2% | 54.3% | 16.9% | 33.9% |
| 8 | 9.0% | 65.5% | 25.5% | 59.4% | 53.1% | 16.4% | 31.4% |
| 9 | 10.8% | 72.0% | 17.2% | 98.0% | 53.0% | 17.3% | 30.0% |
| 11 | 12.9% | 77.0% | 10.0% | 98.8% | 57.3% | 9.2% | 44.8% |

ΔT 指个人当日已完成 leg 的总出行时间变化。每轮约 7,600 万到 9,600 万条事件。
完整逐轮数据见 `redundancy.json`、`magnitude.json` 和 `revisits.json`。

## 观察到的四类冗余

1. **完全重放（R1，约 9–13%）**：选择和结果都与上一轮逐事件相同，但仍被完整仿真。比例低，说明“只重算变化的人”这种精确增量不可行。
2. **近似重放（R2，约 40% 的人口，含 R1）**：选择相同，总出行时间变化不超过 1 分钟。适合近似复用，但必须给出误差界。
3. **重复评估旧计划（R3）**：选择发生变化的人里，回到本人此前已仿真过的计划的比例逐轮上升，到第 8 轮达到 59%；关闭创新后约 99%。这些计划已有历史得分，再仿真主要是为了更新得分，以反映其他人改变后的交通状况。
4. **每轮固定开销（R4）**：每轮都完整写出约 1.1 GB 的事件 XML；冷启动初始化需要 151 秒的路由准备。前者在第 2 期工程项目里处理（E1），后者已有热启动方案。

## 对方法论的含义

- **交互导致的变化是全局性的，不是局部的。** 即使关闭了创新（第 10–11 轮），选择相同的人里仍有约 9% 的出行时间变化超过 15 分钟。只有 45% 的驶入发生在变化不超过 5% 的路段-小时上。
  所以不能只仿真“改了计划的人”；学习或近似的对象应该是**路段-小时 / 班次层面的交通状态**，而不是单个人的轨迹。
- **轮间本身存在噪声底线。** 计划不变时，结果也会有明显波动（流量因子 0.15，系统对扰动敏感）。
  任何近似方法的误差都应该与这个**轮间固有波动**比较，而不是与零比较。这为“何时可以用近似、何时必须做完整仿真”提供了一个可以从数据中得到的容差。
- **R3 指向一个决策问题**：对已经评估过的计划，是否需要再做完整仿真，还是用代理模型估计其得分就够了？
  它可以表述为预算分配问题：决策是本轮做完整仿真还是代理估计；可用特征是路段负荷、饱和度和计划变化率；反馈要等若干轮之后才出现。
  这正好符合 yining 提出的“长期反馈、启发式规则难以处理”的决策问题特征。

## 局限

单一情景、单一种子、只覆盖 12 轮；选择签名不含出发时间与公交线路；ΔT 只统计已完成的 leg；
相邻轮次比较不等于收敛判断。在得出普遍结论之前，需要用 warm 组和其他政策重复这些度量。

## 复现

```sh
.venv/bin/python experiments/redundancy/iteration_redundancy.py RUN/simulation --out OUT --workers 4   # 每轮约 150–190 秒
.venv/bin/python experiments/redundancy/magnitude.py OUT      # 需 PYTHONHASHSEED=0（主脚本会自动设置）
.venv/bin/python experiments/redundancy/revisits.py OUT
```

## 同分支的工程项：已计时验证

campaign `outputs/performance-20261004-171012-redundancy`（独立账本，用了 6,124 / 14,400 秒；报告见其中的 `report_zh.md`）。

- **E1＋E2，12 轮配对：总耗时 2,139.9 → 1,574.0 秒（−26.4%），mobsim 1,611 → 1,063 秒（−34%），输出 15.1 → 2.9 GB。**
  12 轮的逐轮指标差异为 0 项：计数和美分精确相等，其他数值满足 rtol 1e-9。
- 收益几乎全部来自 **E1**：在线计算指标，不再每轮写出事件 XML。
  E2（收费查表）在全规模上逐位一致，但耗时变化在噪声范围内（短跑 −2.9%）。
- JFR：事件线程的执行采样中，XML 写出占 37–39%；分发、评分和旅行时间统计各占 14–21%；自定义收费处理器只占 3–4%。
- 这对应上文的 R4（每轮固定开销）。消除它之后，每轮 mobsim 仍有 74–108 秒，而且随轮次增长。
  剩下的部分主要来自 R1–R3（交互仿真本身），需要用近似或学习方法处理，不能再指望结果严格一致的工程手段。
- 单一情景、种子、单次配对。E1 默认不写任何事件文件；需要事件时，可设 `writeEventsInterval=lastIteration`。

复现：

```sh
.venv/bin/python experiments/performance/redundancy_campaign.py prepare --baseline-jar PRE_E2_JAR --limit-seconds 14400
.venv/bin/python experiments/performance/redundancy_campaign.py run --run-dir outputs/performance-TIMESTAMP-redundancy
.venv/bin/python experiments/performance/critical_path.py outputs/performance-TIMESTAMP-redundancy/short-profile JDK/bin/jfr
```

离线等价性检查（不需要仿真）：

```sh
java -cp target/matsim-nyc-modernized-1.0.0.jar:target/regression-classes org.c2smart.matsimnyc.VerifyPricingReplay CONFIG EVENTS
java -cp target/matsim-nyc-modernized-1.0.0.jar:target/regression-classes org.c2smart.matsimnyc.ReplayIterationMetrics CONFIG EVENTS ITERATION OUTDIR
```

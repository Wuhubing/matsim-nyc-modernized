# 研究文档目录

**一句话：** 在不改变政策结论的前提下，用更少的总核时跑完一整套 MATSim-NYC 收费政策分析。

## 当前状态（2026-10-19）

- **问题定义已定：** 保住九项政策效应（在事先定好的区间内、方向相同），每个场景不跑偏，停得住，在没参与调试的场景上也成立；按总核时计算加速比（[charter.md](charter.md) 第 1、3 节）。
- **已有方法的结果：**
  - 精英父代（E1）：结论通过，固定流程下约 1.3 倍；
  - 精英父代 + 改时间后找路（E3）：不通过；
  - 热启动（W0、W1）：结论通过，但固定流程下不省时间；
  - 缩短流程的探针：原版、精英父代、热启动都不通过。
- **最新分析：** 收费区相关人群占 33% 的人，贡献了 87–90% 的小汽车出行政策效应；起点就要交费的人也要约 80 轮才基本改完（[progress-log.md](progress-log.md) 最后几节）。
- **下一步：** 先整理，再定方法方向（见进展记录末尾的待定事项）。

## 文件地图

| 文件 | 内容 |
|---|---|
| [charter.md](charter.md) | 总纲：问题、已有事实、验收、候选方法、测试漏斗、论文结构、工作方式 |
| [matsim-explained.md](matsim-explained.md) | MATSim 是什么、每轮做什么、为什么慢（白话） |
| [matsim-source-reading.md](matsim-source-reading.md) | MATSim 2026.0 源码逐行核实（参考） |
| [rq1-answer.md](rq1-answer.md) | RQ1：其他领域怎么加速仿真；按领域的总表；全部文献附录 |
| [rq2-answer.md](rq2-answer.md) | RQ2：哪些结论必须不变 |
| [rq3-answer.md](rq3-answer.md) | RQ3：MATSim 的"收敛"指什么 |
| [acceptance-protocol.md](acceptance-protocol.md) | 验收标准的具体数值和推导 |
| [progress-log.md](progress-log.md) | 按时间的进展记录（实验、结果、决定） |
| [experiments.md](experiments.md) | 实验登记表：所有运行、提交号、数据位置、结论；代号对照表 |
| [literature/](literature/README.md) | 61 篇读书笔记（按领域索引） |
| [diagnostics/g-estimator.md](diagnostics/g-estimator.md) | G 估算器（均衡差距）设计；只作诊断 |
| [archive/](archive/README.md) | 已被取代的计划和记录 |

## 代码地图

模型和运行器来自 `main`；下面只列研究相关部分。

| 组件 | 位置 | 状态 |
|---|---|---|
| 运行器（参照流程、热启动 `--plans`、`--innovation-until`、退火、得分平均、精英父代等选项） | `experiments/reference/run_reference.py`、`reference.sbatch` | 在用 |
| 逐人、分组、路段的每轮记录 | `src/main/java/org/c2smart/matsimnyc/ResearchMetrics.java`、`IterationMetrics.java` | 在用 |
| 重新规划日志（每次试新方案的结果） | `ReplanningLog.java`、`RecordingStrategyChooser.java` | 在用 |
| 精英父代 | `EliteParent.java` | 在用 |
| 政策效应、验收、探针、换方案分析 | `experiments/rq3/`（`compute_deltas.py`、`analyze_e1_x1_w1.py`、`probe_table.py`、`plan_change.py`；运维脚本在 `ops/`） | 在用 |
| 共用的解析函数和早期分析 | `experiments/l2seg/`（`experiments/rq3` 从这里导入函数） | 只当函数库用，里面的分析属于已放弃的方向 |
| 按个人挑人的选择器、重复找路过滤 | `TargetedInnovationChooser.java`、`StableReRoute.java` | 闲置：只在设置对应系统属性时生效 |

## 数据在哪里

所有运行在 ORCD 的 `/orcd/scratch/orcd/006/weibingw/matsim-work/` 下，大文件移到了 `/orcd/pool/007/weibingw/matsim-work-iters/`，原位置留有链接。逐个运行的路径和提交号见 [experiments.md](experiments.md)。

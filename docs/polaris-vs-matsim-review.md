# 文献综述：POLARIS 为什么看起来比 MATSim 快，以及现有加速研究怎么做（2026-10-27）

**地位：** 阅读小组的综述草稿，汇总 [literature/](literature/README.md) 已有笔记、`~/Desktop/26f/readinggroup/ref/` 里的 16 篇 PDF 和一次网上检索。更完整的跨领域版本见 [rq1-answer.md](rq1-answer.md)，验收口径见 [rq2-answer.md](rq2-answer.md)。标【推断】的是我们自己的判断，不是原文结论。

## 一句话结论

- **没有任何论文在同一个场景上直接比较过 POLARIS 和 MATSim 的速度。** "POLARIS 更快"的印象来自它的**结构**，不是来自实测对比。
- POLARIS 省在**轮数**上，靠四个设计：用选择模型一次评估所有方式（不试错）、跨轮平均路况、按"实际时间 − 预计时间"挑人换路、从上一次结果热启动。它的**每轮**并不便宜（Austin 每轮 1.25 小时）。
- MATSim 这边，现有加速论文可以分成"轮数更少"和"每轮更便宜"两类，其中轮数更少的几种做法，**本质上都是在把 POLARIS 的某个设计搬进 MATSim**，但没有人系统地比较过哪个设计最有用。
- 几乎所有加速论文都只用一个种子、只比较绝对水平（平均得分、方式比例），**没有检查政策效应是否不变**。

## 1. "POLARIS 更好"具体指什么？拆成三件事看

### 1.1 每轮更便宜？——没有证据

| 模型 | 规模 | 每轮耗时 | 一次完整运行 | 出处 |
|---|---|---|---|---|
| POLARIS Austin（收费研究） | 全区 | **1.25 小时**（24 线程） | 跑到第 50 轮，约 62 小时 | Mori et al.（[OSTI 3794253](https://www.osti.gov/pages/servlets/purl/3794253)） |
| POLARIS Chicago | 25% 人口 | 约 157 分钟 | — | Gurumurthy et al. 2025（[MUM 2025](https://matsim.org/conferences/mum2025/abstracts/MUM25_paper_24.pdf)） |
| POLARIS 多年联合仿真 | — | — | 每个预测年 14 轮，约 43.5 小时（热启动） | Nair et al. 2026（[arXiv 2608.24817](https://arxiv.org/abs/2608.24817)） |
| MATSim-NYC（本仓库） | 4% 人口 | 170–300 秒（16 线程） | 100 轮，约 5–8 小时 | [archive/matsim-nyc-findings.md](archive/matsim-nyc-findings.md) |
| MATSim 瑞士 10%（QSim → Hermes） | 10% 人口 | 12 分钟 → 5 分钟 | 301 轮，83 → 47 小时 | Graur et al. 2021（[笔记 02](literature/02_Graur2021_Hermes.md)） |

- 场景、人口比例、硬件都不同，**这张表不能用来说谁快**。
- POLARIS 每轮要让**所有人**重新跑一遍全天的需求模型（活动生成、目的地、方式、日程），所以每轮并不轻。
- POLARIS 的工程优化（C++、自定义内存分配器、并行事件引擎）在综述中被提到（[Overview of Agent-based Traffic Simulators](https://arxiv.org/pdf/2102.07505)），但没有对比数字。
- 网上检索（2026-10-27）没有找到两者在同一场景上的运行时间对比。

### 1.2 轮数更少？——是，但没有"两轮"那么夸张

- **Auld, Verbas & Stinson 2019**：按 gap 换路 + 信息混合，**2 轮**达到与原来 7 轮相同的相对 gap（[笔记 51](literature/51_Verbas2024_POLARIS_gap_based.md)）。但这只是**路径选择**，在 Bloomington 这个中等网络上跑了**一次**，没有多种子，也没有检查收敛到的流量是否一样。
- **含方式、目的地的完整政策运行**仍要 **14–50 轮**：Mori 的收费研究跑 50 轮（收入约 30 轮稳定），Nair 热启动后 14 轮。
- MATSim 常见配置是 100–500 轮（MATSim-NYC 100 轮，Berlin、Munich 的收费研究 400–500 轮，见 [rq2-answer.md](rq2-answer.md) 第 1 节）。
- 【推断】轮数上 POLARIS 大约少几倍，不是数量级的差别。

### 1.3 结果更可靠？——一样薄弱

- POLARIS 的收费研究用**一次运行的某一轮**（如第 50 轮）报告结果，收敛靠看曲线（[笔记 61](literature/61_POLARIS_system_iteration_and_pricing.md)）。
- 大规模情景扫描（192 个情景 × 8、765 次运行）靠 HPC 堆出来，然后用回归总结，没有讨论单次运行的随机性。
- 这一点和 MATSim 的政策研究一样（[rq2-answer.md](rq2-answer.md) 第 2 节：7 篇里只有 1 篇用了多个种子）。

## 2. 结构上的差别：POLARIS 的四个设计

| | MATSim | POLARIS | POLARIS 的好处 |
|---|---|---|---|
| **每轮谁重新决策** | 约 10–30% 的人随机变异，其余在已有方案中按 logit 选 | **所有人**按选择模型重新决定全天 | — |
| **新方式怎么来** | 随机换一个，执行一次才知道好坏 | logit / nested logit 在路况矩阵（skims）上**一次评估所有方式** | **不浪费试错**（设计 1） |
| **跨轮记住什么** | 每人最多 5 个方案和它们的得分（单次执行，有噪声） | **平均后的路况矩阵** | 平滑掉噪声和集体换路的过冲（设计 2） |
| **谁换路** | 随机抽人 | 上一轮"实际经历时间 − 找路时预计时间"大的人更可能换 | **只在需要的地方搜索**（设计 3） |
| **从哪里开始** | 通常冷启动 | 从上一年的路况矩阵热启动 | 少跑轮数（设计 4） |
| **收敛的对象** | 方案集合的分布（没有公认的度量） | 路况矩阵的不动点；路线层用相对 gap 判断 | 有明确的停止标准 |

出处：Auld et al. 2016（[OSTI 1392074](https://www.osti.gov/pages/servlets/purl/1392074)）、Auld et al. 2019（[OSTI 1528926](https://www.osti.gov/servlets/purl/1528926)）、Verbas et al. 2024（[arXiv 2408.05176](https://arxiv.org/abs/2408.05176)）、POLARIS 文档 Convergence 页。

**代价（POLARIS 换来速度付出的东西）：**
- 选择模型的效用和仿真执行的结果可以对不上：方式是在**估计的**路况上选的，执行后才知道实际路况。
- 设计 3 只管路线，方式和目的地的变化靠路况矩阵在轮与轮之间传递。
- 结果依赖一个外部估计的选择模型；MATSim 只依赖打分函数，行为上更"自洽"。
- 源码不公开，想替换其中一个设计做对照实验很难。

## 3. 现有论文怎么加速 MATSim

按"省在哪里"分组。ref 列是 `readinggroup/ref/` 的文件编号；笔记列是 [literature/](literature/README.md) 的编号。

### 3.1 轮数更少：更好的提议（对应 POLARIS 设计 1）

| 论文 | 做法 | 结果 | 局限 | 出处 |
|---|---|---|---|---|
| Hörl et al. 2018/2019/2021 | Discrete Mode Choice：先估算每条可行方式链的效用，按 logit 提议；执行和打分仍由 MATSim 做 | 方式比例更快稳定 | 默认估算器看不到道路收费 | 笔记 62 |
| Rakow & Nagel 2023 | 按估算效用提议换方式，并逐步退火 | Kelheim 上**少 4–5 倍轮数**达到相近得分 | 只比较得分，单个场景 | 笔记 63 |
| Fourie et al. 2013（PSim） | 两次真实仿真之间，用固定路况的"伪仿真"快速试方案 | 真实仿真轮数 101 → 13–20 | 便宜模型参与打分，终点改变（汽车比例低 4.5 个百分点） | ref 01，笔记 46 |
| Flötteröd 2026（ATAP） | 先模拟执行方案、只执行可能提高得分的方案；逼近无噪声的均衡点 | — | 只在 ref 03 中被提及，原文未读 | ref 03 |
| MAPPO（MUM 2026） | 用强化学习训练一个共享策略网络，替换整套重规划策略 | 摘要，无数字 | 尚无验证 | ref 11 |
| Patwary et al.（MUM 2025） | 用大语言模型给电动车用户安排充电（单次重规划） | 摘要，无数字 | 只针对充电这一类决策 | ref 12 |

### 3.2 轮数更少：只在需要的地方搜索（对应 POLARIS 设计 3）

| 论文 | 做法 | 结果 | 局限 | 出处 |
|---|---|---|---|---|
| Tchervenkov et al. 2020 | 换路概率 P = 1 − exp(−Δt/β)，Δt 是预计能省的时间；还修正了空路段时间估计的偏差 | 提高重规划率时，路段流量不再大幅振荡 | 只在 3 条路、600 人的沙盒上测试 | ref 02 |
| Zhuge et al. 2021 | 先让每人攒 20 个方案，之后只让"当前方案比记忆中最好方案差"的人重规划；加变时间步 | 轮数 154 → 69；合并变步长后总时间约 1/3.9 | 4 万辆车的小场景；只看 12 个计数点 | 笔记 01 |
| Auld et al. 2019（POLARIS） | 按 gap 换路 + 信息混合 | 7 → 2 轮 | 只管路线，一次运行 | 笔记 51 |

### 3.3 轮数更少：控制搜索强度（对应 POLARIS 设计 2）

| 论文 | 做法 | 结果 | 局限 | 出处 |
|---|---|---|---|---|
| Flötteröd et al. 2026（简单重规划配方） | 每人只记 1 个方案；第一阶段 50% 创新、50% 重新执行；第二阶段创新率按 1/(k+1) 或 1/√(k+1) 衰减（Robbins–Monro 条件） | Berlin、Munich、Stockholm、Oslo 四个场景上得分都比默认配置高、稳定更快；**随机改出发时间是最慢的策略**，需要慢衰减 | 只看平均得分；作者说推导"偏直觉" | ref 03 |
| MATSim ReplanningAnnealer | 内置的创新率退火 | — | sigmoid 衰减尾巴太快，不满足 Robbins–Monro（据 ref 03） | ref 03 |

### 3.4 轮数更少：热启动（对应 POLARIS 设计 4）

| 论文 | 做法 | 结果 | 局限 | 出处 |
|---|---|---|---|---|
| Nicolai 2013（经 ref 06 转引） | 冷、温、热启动 | Zurich：100 / 60 / 30 轮 | 二手引用 | ref 06 |
| Zame et al. 2026 | 测量"改动场景后重新收敛要多少轮" | 重新收敛的轮数**取决于新方案好了多少，不取决于改动多大**：改动相同，轮数差 8 倍（26–208 轮）；越是改进，越要更久才找到 | 电动卡车充电站场景，不是收费 | ref 06 |
| 本仓库热启动（W0/W1） | 从基线终点出发跑政策 | 结论通过，但固定流程下不省时间 | — | [progress-log.md](progress-log.md) |

### 3.5 每轮更便宜：更快的交通仿真

| 论文 | 做法 | 结果 | 出处 |
|---|---|---|---|
| Graur et al. 2021（Hermes） | 事件驱动、单线程的新 mobsim | 单轮约 2.5×，总时间只减少 43%（重规划成为瓶颈） | 笔记 02 |
| Laudan 2025/2026（DSim） | 分布式 mobsim | — | ref 09，笔记 47 |
| Moukir et al. 2024（multiMATSim） | 多个实例并行、交换方案 | 达到同一平均得分的时间 6 → 1.5 小时；跑满 300 轮反而更慢 | ref 08，笔记 48 |
| Saprykin 2022（GEMSim） | GPU mobsim | mobsim 很快，整个循环受 Amdahl 定律限制 | ref 10，笔记 42 |
| Fourie 2013（PSim）、Ben-Dor 2021、Mersini 2026 | 抽样和伪仿真；抽样比例与容量缩放 | Ben-Dor：低于 20–25% 抽样不安全；Mersini：给出按抽样比例设置容量系数的建议 | ref 01、04a、04b |

### 3.6 运行次数更少：优化和代理模型

| 论文 | 做法 | 出处 |
|---|---|---|
| Flötteröd 2017（opdyts） | 在不完全收敛的仿真上做优化，把"噪声"和"离均衡多远"分开计入 | ref 14 |
| Chhatre 2022；Koutounidis 2025 | 贝叶斯优化，减少需要运行的方案数 | ref 15、07 |
| Natterer et al. 2025 | 用图神经网络代替整个 MATSim 运行；政策道路 R² 0.98，非政策道路 0.77 | ref 13，笔记 49 |

## 4. 这些论文的共同不足

1. **没有直接对比。** 没有人在同一个场景上比较 POLARIS 和 MATSim，也没有人在 MATSim 里把 POLARIS 的四个设计**逐个加上**，看哪一个贡献最大。现有论文各自只试一个设计，场景、指标都不同，数字不能放在一起比。
2. **验证薄弱。** 加速论文基本只用一个种子，比较平均得分或方式比例等绝对水平，而且常在"达到原版平均得分"的那一轮比较（PSim、multiMATSim），没有事先定好的通过标准。只有 Natterer 比较了政策效应（[rq2-answer.md](rq2-answer.md) 第 3 节）。
3. **收费场景没人做。** 3.1 节的方式提议方法，默认估算器看不到道路收费；Zame 测的是充电站；Flötteröd 配方只看平均得分。**"在收费政策下，哪种加速方法能保住政策效应"没有现成答案。**
4. **出发时间是盲区。** Flötteröd 2026 指出随机改出发时间是最慢的策略；POLARIS 用日程模型安排时间。【推断】我们没有找到在 MATSim 里"按估算效用提议出发时间"的工作；而收费恰恰会改变出发时间（高峰 / 非高峰价格不同）。

## 5. 可以做的研究问题（候选，未筛选）

结合本仓库已有的事实（[charter.md](charter.md) 第 2 节）：

| 候选问题 | 为什么值得做 | 本仓库已有的基础 |
|---|---|---|
| **A. POLARIS 的哪个设计对 MATSim 最有用？** 在 MATSim-NYC 上逐个加入"按效用提议方式""路况平滑""按时间差挑人换路""热启动"，用九项政策效应验收，比较各自省下的总核时 | 填补第 4 节第 1 条；结果对所有 MATSim 用户都有参考价值 | 参照运行、验收标准、热启动和精英父代的结果都已有 |
| **B. 看得到收费的方式提议。** 在 Discrete Mode Choice / informed mode choice 的估算器里加入道路收费，测在收费政策下的加速比 | NYC 的剩余改进空间主要在方式选择（方式 gap 0.16 对路线 0.03）；随机换方式 71% 明显更差 | 方案日志、方式提议预测器（AUC 0.86）的分析 |
| **C. 按效用提议出发时间。** 用估算的效用代替随机改出发时间 | Flötteröd 2026：随机改时间最慢；收费有高峰差价 | 需要新写 |
| **D. 政策场景的重新收敛代价。** 测量从基线热启动后，不同收费水平要多少轮才稳定 | Zame 2026 只做了充电站；本仓库发现"起点就要交费的人到第 79 轮也只改了 82%" | 热启动 W0/W1 的运行 |

【推断】A 最能直接回答"为什么 POLARIS 更好"，B 和 C 是 A 里最可能有效的两个设计的深入版本。可以先做 A 的小规模版本（12 轮以内的检查），看哪个设计值得展开。

## 6. 待读

- **Gurumurthy et al. 2020**：POLARIS 的 nested logit 方式选择（变量、结构）。
- **Verbas et al. 2018**：POLARIS 路由和 DTA 收敛判据（原文未找到，2026-10-27 检索仍无结果）。
- **Flötteröd 2026（ATAP contrib）**：ref 03 提到的"只执行可能提高得分的方案"。
- **Hörl 2022**：抽样比例作为保真度旋钮（经 ref 06 转引）。
- **Nicolai 2013**：MATSim 热启动的原始数字。
- **Verbas, Mahmassani & Hyland 2016**（TR Part B 93）：gap-based 公交分配，摘要称收敛速度和结果质量都优于 MSA（[IDEAS](https://ideas.repec.org/a/eee/transb/v93y2016ipap1-16.html)）。

## 检索记录

2026-10-27 检索了"POLARIS 与 MATSim 的计算性能对比""Verbas/Auld 2018 DTA 收敛""MATSim 2024–2025 收敛加速"。没有找到直接对比；新增参考：
- [An Overview of Agent-based Traffic Simulators](https://arxiv.org/pdf/2102.07505)（提到 POLARIS 的内存分配器和并行事件引擎）
- [Verbas, Mahmassani & Hyland 2016](https://ideas.repec.org/a/eee/transb/v93y2016ipap1-16.html)
- [Tchervenkov et al. 2020，ETH Research Collection](https://research-collection.ethz.ch/handle/20.500.11850/452865)（即 ref 02）
- [MATSim ReplanningAnnealer 源码](https://matsim.org/doxygen/_replanning_annealer_config_group_8java_source.html)

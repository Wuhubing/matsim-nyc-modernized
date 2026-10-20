# [61] POLARIS：系统结构、迭代方式与收费研究（Auld et al. 2016；Mori et al.；Fakhrmoosavi et al. 2023）

- **领域**: 1 / 2 与 MATSim 同类的 agent 模拟器（补充 [51](51_Verbas2024_POLARIS_gap_based.md)）
- **依据**（2026-10-19 读原文）：
  - **Auld, Hope, Ley, Sokolov, Xu & Zhang 2016**，POLARIS: Agent-based modeling framework development and implementation for integrated travel demand and network and operations simulations，*Transportation Research Part C* 64:101–116，DOI [10.1016/j.trc.2015.07.017](https://doi.org/10.1016/j.trc.2015.07.017)。读的是 OSTI 公开的作者稿 [OSTI 1392074](https://www.osti.gov/pages/servlets/purl/1392074)（2014-05 投稿版，23 页）：§4.1 需求模型、§4.2 网络模型全读，其余略读。
  - **Mori, de Souza, Gurumurthy, Auld & Kockelman**，Comparing delay-, distance-, and cordon-based congestion pricing strategies via large-scale simulation，作者稿 [OSTI 3794253](https://www.osti.gov/pages/servlets/purl/3794253)（37 页；刊物未写明）：方法节、结果开头、附录 A 已读。
  - **Fakhrmoosavi, Gurumurthy, Kockelman, Hunter & Dean 2023**，On- and off-street parking strategies and outcomes for SAV fleet operations，作者稿 [OSTI 2482535](https://www.osti.gov/pages/servlets/purl/2482535)：只读了 POLARIS 方法描述一段。
  - POLARIS 官方文档 [polaris-studio](https://polaris.taps.anl.gov/polaris-studio/)：Anatomy、Run、Convergence 三页。
  - **未读到原文**：Auld & Mohammadian 2012（ADAPTS，TR Part A，付费）；Gurumurthy et al. 2020（方式选择模型）；Verbas et al. 2018（路由和 DTA 收敛）；de Souza et al. 2024（交通流模型）。

> 一句话：POLARIS 每一轮（一个"24 小时日"）**让所有人重新做一遍全天决策**：生成活动、选目的地、选方式（logit / nested logit，输入是路况矩阵 skims 或路由时间）、排日程、找路、交通仿真。跨轮学习的不是每个人的方案记忆，而是**路况矩阵**：多轮出行时间取平均，得到"稳定的 skim"。所以 POLARIS 的迭代是一个**在路况上找不动点**的过程，方式和目的地靠选择模型一次性评估所有选项，不需要逐个试。

## 1. 每一轮做什么（原文）

| 步骤 | 做法 | 出处 |
|---|---|---|
| 活动生成 | 按人群类型的 hazard-duration 模型生成活动 | 2016 §4.1.1 |
| 规划顺序 | 有序 probit 决定各属性（地点、方式、时间）何时规划、多灵活 | 2016 §4.1.2；Auld & Mohammadian 2012 |
| 目的地选择 | 从约束后的候选集中抽样，MNL（竞争目的地形式） | 2016 §4.1.2；Mori 方法节 |
| **方式选择** | 2016 版："a simple logit model"；"If the location of the activity is known, the skimmed or routed travel times by mode are used in the choice utility"，否则用加权可达性。后来的版本是 nested logit，变量包括各方式估计的出行时间、费用、接驳时间和按收入、出行目的算的时间价值；收费会进入 skim | 2016 §4.1.2；Mori 方法节；Fakhrmoosavi 引 Gurumurthy et al. 2020（"three nested logit models"） |
| 排日程 | 启发式规则 + 冲突处理模型 | 2016 §4.1.3 |
| 找路 | 每个 agent 自己的 time-dependent A*，可用历史、当前、经历、预测四种路况；按个人时间价值算广义成本 | 2016 §4.2.2；Mori 引 Verbas 2018、Auld 2019 |
| 交通仿真 | 中观，Newell 简化运动波 | 2016 §4.2.3 |

## 2. 跨轮怎么衔接（原文）

- **路况矩阵取平均：** "Across multiple 24-hour-day iterations of POLARIS, travel times are averaged to obtain a stable skim that is a function of demand"（Mori）。收费会大幅改变前几轮的 skim，所以"several iterations of POLARIS are simulated before results are reported"。
- **路线层收敛判据：** "the convergence is based on the closeness of the experienced versus routed travel times for all travelers"（Fakhrmoosavi 引 Verbas 2018）。也就是 [51](51_Verbas2024_POLARIS_gap_based.md) 里"测得的时间差"。
- **固定需求：** 可以从上一次运行读出需求（"fixed demand"），只重跑路线和交通仿真，"to avoid randomness in the simulation"（Fakhrmoosavi）。
- **文档里的收敛标准：** VMT/VHT 相邻轮变化 < 1–2%；> 95% 的车辆在一天内走完；每 3–5 轮检查一次；需求超过容量时"traditional convergence may not be achievable"。
- **轮数和成本（Mori，Austin 2035）：** 收费方案跑到第 50 轮，取第 50 轮结果；每轮 1.25 小时（24 线程）。收入约第 30 轮稳定，总延误约 10 轮接近终值但逐轮波动。

## 3. 和 MATSim 的结构对照

| | MATSim（我们的定义） | POLARIS |
|---|---|---|
| 每轮谁重新决策 | 约 30% 的人做随机变异，其余在已有方案中选 | **所有人**按选择模型重新决定全天 |
| 新方式怎么来 | 均匀随机换一个，执行一次才知道好坏 | logit 在 skim 上一次评估所有方式 |
| 跨轮记住什么 | 每人最多 5 个方案和它们的得分 | 平均后的路况矩阵（以及路线层的历史路况） |
| 收敛的是什么 | 方案集和选择分布（依分布） | 路况矩阵的不动点 |
| 慢在哪 | 发现好方案（尤其方式） | 路况稳定下来（收费下约 30–50 轮） |
| 结果怎么报告 | 我们：最后 10 轮均值，3 个种子 | 一次运行的某一轮（如第 50 轮），没有多种子 |

## 4. 对我们意味着什么【推断】

1. **设计 1（按效用选方式）的先例更清楚了：** POLARIS 根本不"试"方式，而是用选择模型在路况矩阵上一次性评估。搬到 MATSim 时：
   - 用 MATSim 自己的打分公式在上一轮（或平滑后）的路况上估算各方式的效用，按 logit 提议；这比另建一个独立的效用模型更不容易和执行结果分离（Planomat 的教训）。
   - 执行和打分仍由 MATSim 做，最后评估段只做选择，不受影响。
   - POLARIS 让所有人每轮都重新选；我们只改"提议"，不改谁去试。
2. **设计 2（路况混合）在 POLARIS 里有两层：** 路线层的信息混合（Auld 2019），以及需求层的 skim 跨轮平均。我们找路用的路况、按效用选方式用的路况，都可以用平均后的版本。
3. **"固定需求"对应我们的"快照 + 只做选择"探针：** 都是固定上一层的决策、只重跑下一层，用来去掉随机性或缩短流程。可以作为方法上的类比引用。
4. **POLARIS 的收费研究也没有处理随机性：** 一次运行、取第 50 轮，收敛靠看曲线。这和 RQ2 里 MATSim 政策研究的情况一样，也是我们验收设计（多种子、事先定好的区间）的切入点。
5. **引用时要注意：** 方式选择模型的出处是 Gurumurthy et al. 2020（nested logit），不是 Auld & Mohammadian 2012。后者讲的是规划顺序和规划时限模型。

## 5. 待补读

- Gurumurthy et al. 2020：nested logit 方式选择的具体变量和结构。
- Verbas et al. 2018：路由、DTA 和"经历时间 vs 路由时间"收敛判据。
- POLARIS 热启动（"从上一年的 skim 出发，2–11 轮"）目前只有二手描述（arXiv 2608.24817 的联合仿真论文），原始出处未找到。

## 6. 近几年使用 POLARIS 的论文（2023–2026，10-19 检索并读了相关段落）

| 论文 | 研究什么 | 迭代、运行次数、成本 | 和我们相关的点 |
|---|---|---|---|
| Fakhrmoosavi et al. 2023（[OSTI 2482535](https://www.osti.gov/pages/servlets/purl/2482535)），Austin | 共享自动驾驶车队的停车策略 | 部分结果用"固定需求"（读上一次运行的需求）"to avoid randomness" | 去随机性的做法：固定上层决策只重跑下层 |
| Auld et al. 2024（[arXiv 2403.14669](https://arxiv.org/abs/2403.14669)），Chicago | 192 个技术和政策组合（含拥堵收费、公交扩张） | "192 different scenarios that were run over 8 times each at converged settings"，共 1,600 多组结果，用回归总结（"8 times"指 8 次重复还是 8 轮，原文不清楚） | 大规模情景扫描；结论用回归和显著性表述，政策效应口径 |
| Verbas et al. 2024（[arXiv 2408.05176](https://arxiv.org/abs/2408.05176)），Chicago | 公交路由、分配与仿真 | 765 次运行做回归；见 [51](51_Verbas2024_POLARIS_gap_based.md) | 同上 |
| de Souza et al. 2024（Procedia CS，POLARIS-LC） | 拉格朗日坐标的多类交通流模型 | — | 只改每轮成本，与我们无关 |
| Gurumurthy et al. 2025（[MATSim User Meeting 2025](https://matsim.org/conferences/mum2025/abstracts/MUM25_paper_24.pdf)） | 建模与标定流程 | 25% 芝加哥模型，一个 24 小时日约 157 分钟；"convergence run"：每轮一个 24 小时日，"network states feeding into the next iteration to update demand outcomes"；标定要分层，工作地变化后要留足轮数让路网适应 | 作者自己在 MATSim 会议上把 POLARIS 和 MATSim 并列；说明"迭代求稳定"在 POLARIS 中同样昂贵 |
| Mori et al.（[OSTI 3794253](https://www.osti.gov/pages/servlets/purl/3794253)），Austin | 拥堵、距离、警戒线收费比较 | 跑到第 50 轮，每轮 1.25 小时；一次运行 | **和我们同一种政策（警戒线收费）**；收敛靠看收入、延误曲线 |
| Nair et al. 2026（[arXiv 2608.24817](https://arxiv.org/abs/2608.24817)） | 土地利用 + 交通 + 建筑能耗联合仿真 | 每个预测年 POLARIS 跑 14 轮，约 43.5 小时；"The prior year's skims warm-start the iterations, so fewer are needed" | 热启动的直接表述（但没有给出不热启动时要几轮） |
| Alam, Verbas et al. 2026（[arXiv 2609.00327](https://arxiv.org/abs/2609.00327)），Chicago 2050 | 9 个出行与能源政策情景 | 迭代运行；"If a trip takes significantly longer than expected, agents may revise their routing or mode choices in subsequent iterations" | 重新决策由"实际比预期慢很多"触发，即测得的时间差 |

**整体观察【推断】：**
- POLARIS 团队同样面临"每个情景要迭代十几到几十轮、每轮 1–2.5 小时"，所以大规模情景扫描（192 × 8、765 次）依赖 HPC，而不是更少的迭代。没有找到专门研究"减少 POLARIS 迭代数"的论文，只有 Auld 2019 的信息混合和热启动。
- 应用论文普遍用一次运行的某一轮或几次运行的回归报告结论，没有像我们这样事先定好政策效应的区间。
- 三个可借鉴的设计在近年论文中都有体现：按选择模型选方式（不试错）、跨轮平均路况、从上一个收敛状态热启动；"测得的时间差"既是 DTA 收敛判据，也是触发重新决策的条件。

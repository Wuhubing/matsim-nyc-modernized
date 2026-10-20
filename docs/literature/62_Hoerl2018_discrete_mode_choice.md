# [62] Hörl, Balac & Axhausen 2018、2019；Hörl 2021 — MATSim 的离散方式选择扩展（Discrete Mode Choice）

- **论文：**
  - Hörl, Balac & Axhausen 2018, *A first look at bridging discrete choice modeling and agent-based microsimulation in MATSim*, Procedia Computer Science 130:900–907, DOI [10.1016/j.procs.2018.04.087](https://doi.org/10.1016/j.procs.2018.04.087)（全文：[ETH Research Collection](https://doi.org/10.3929/ethz-b-000261733)）
  - Hörl, Balac & Axhausen 2019, *Pairing discrete mode choice models and agent-based transport simulation with MATSim*, 98th TRB Annual Meeting（全文：[ETH Research Collection](https://doi.org/10.3929/ethz-b-000303667)）
  - Hörl 2021, *Integrating discrete choice models with MATSim scoring*, Procedia Computer Science 184:704–711, DOI [10.1016/j.procs.2021.03.088](https://doi.org/10.1016/j.procs.2021.03.088)（[HAL hal-03099994](https://hal.science/hal-03099994v1)）
- **代码：** matsim-libs 的 [`contribs/discrete_mode_choice`](https://github.com/matsim-org/matsim-libs/tree/main/contribs/discrete_mode_choice)（README、`docs/GettingStarted.md`、`DiscreteModeChoiceConfigurator.java`、`MATSimDayScoringEstimator.java`、`MATSimTripScoringEstimator.java`）
- **领域：** 1 MATSim 与智能体交通仿真
- **依据（2026-10-20）：**
  - 2018、2019 两篇全文已读；
  - **2021 只读到摘要**：ScienceDirect 拒绝访问，HAL 的预印本只能作为文件下载，需要用户自己下载；
  - 代码读了 README、入门文档、配置帮助类和两个效用估算器，没有读全部源码。

> 一句话：MATSim 默认的换方式是随机的（随机挑一个计划，再给一段出行链随机换方式），会产生很多明显不合理的方案。这个扩展先为每个人算出所有可行的方式组合，用估算的效用（时间、费用等）给每种组合打分，再按 logit 概率或取最好的来选。

## 1. 它怎么替换随机换方式

每次给一个人换方式，分七步（入门文档）：

1. **找出选择单位：** 按出行（trip）或按出行链（tour，例如两次在家之间的一串出行）。2019 年的结论是按出行链更好，做出的决定更一致。
2. **这个人能用哪些方式：** 例如没有驾照就不能开车。
3. **列出所有方式组合：** 例如三段出行的 [步行, 公交, 公交]、[开车, 开车, 开车]……
4. **先按结构约束过滤：** 车只能在它停着的地方用，最后要开回家。
5. **估算每种组合的效用：** 对每种组合的每段出行都要找路（有缓存），再按效用函数算分。
6. **用找路结果再过滤一次：** 例如那个时段没有公交服务。
7. **选一个：** 随机、按 logit 概率，或取效用最高的。

**三种用法：**

| 用法 | 配置（`DiscreteModeChoiceConfigurator`） | 怎么运作 |
|---|---|---|
| 替换 SubtourModeChoice | 估算器 `Uniform`，选择器 `Random` | 所有组合效用都是 0、随机选，和原来的随机换方式几乎一样，只是约束更好配置 |
| **重要性采样器** | 估算器 `MATSimDayScoring`，选择器 `MultinomialLogit` | 仍然是 MATSim 的一个"试新方案"策略，只是**提议**换成按估算效用的 logit 概率；新方案照常执行、打分，照常在计划之间选择 |
| 方式选择放进循环 | 每人只留 1 个计划；保留上一个计划（`KeepLastSelected`）；永远不关试新方案 | MATSim 只当交通分配用，不再按得分在计划之间选择，方式完全由选择模型决定 |

**重要性采样器的估算器包含什么（代码）：** `MATSimTripScoringEstimator` 按 MATSim 配置里的参数，算方式常数、出行时间、距离，以及按距离计的费用（公交还加上等车时间）；`MATSimDayScoringEstimator` 再加上每天的固定费用。代码注释写明**不给活动打分**。**也没有道路收费**：在我们的收费场景里，直接用它，提议换方式时看不到拥堵费。

## 2. 会不会改变最后评估

| 用法 | 最后评估（原模型执行、打分，关掉试新方案后在已有计划里选） | 能不能用在我们的问题上 |
|---|---|---|
| 替换 SubtourModeChoice | 不变 | 能，但没有加速意义 |
| **重要性采样器** | **不变**：只改变提议哪种方式，执行、打分、选择都还是 MATSim 做；关掉试新方案后的阶段完全一样 | **能**。和总纲的规则一致：便宜的模型只提议，不打分 |
| 方式选择放进循环 | **改变**：没有按得分的选择，方式由选择模型直接决定 | 不能（违反"最后评估固定"） |

**要注意：** 即使最后评估不变，提议方式改了，最终留在每个人记忆里的计划也会不同，终点可能不同（总纲第 2 节事实四）。所以仍然要用九项政策效应检验。2018 年的论文自己也指出，换了提议方式后，各种方法的方式比例"没有直接对应"。

**2021 年（只读到摘要）：** 直接把离散选择模型的参数放进 MATSim 打分，在技术上不成立；可以用基于哈希函数生成的确定性伪误差（"冻结的随机性"）做到一致。这关系到估算的效用和 MATSim 实际打分不一致时怎么处理，需要读全文。

## 3. 报告了多少加速

**没有给出可以直接引用的加速倍数。**

- **2018（苏黎世 1% 样本，所有出行一开始都设成步行，跑 1,000 轮）：**
  - 比较三种按选择模型选方式的做法和两种按得分选择的做法（原来的随机换方式；按出行链随机抽、再按得分选择）。
  - 只用遥传（不模拟拥堵）和用队列仿真两种设置下，按选择模型的做法都"比按得分的做法快得多地达到稳定"，但**只有图，没有数字**。
  - 按选择模型选方式需要给每种选择找路，但找路能按人并行，所以**每轮时间和原来差不多**。
  - **它们比较的按选择模型的做法，不用得分做选择，相当于第三种用法**，不是重要性采样器。
- **2019（苏黎世，约 20 万人，每轮约 2.2 万人换方式，2011 年的 80 核机器）：**
  - 只测了"方式选择放进循环"的设置：每人一个计划，没有按得分的选择，也没有其他试新方案的策略。
  - 文中说"收敛应该快得多"，但没有和原版 MATSim 比较收敛速度。
  - 给出的是：按出行链的模型和调查的方式比例吻合得好；选择模型每轮的运行时间（图 6）；预测出行时间的误差中位数约 0%、均值 −2.5%（略低估）。
- **重要性采样器：** 入门文档只说它"有可能加快收敛"，没有找到发表的数字。

## 4. 对我们意味着什么【推断】

- **"按效用提议换方式"在 MATSim 里已经有现成的实现**，而且重要性采样器这种用法符合我们"最后评估固定、便宜的模型只提议"的规则（[../ideas.md](../ideas.md) 想法 1 的第 2 步）。
- **前人没有量化它在重要性采样器用法下能省多少轮。** 如果我们来测（用九项政策效应和总核时），本身就是新的结果。
- **用在 NYC 收费场景之前要补的：**
  1. **估算器要加上道路收费**（NYC 的收费在 `Pricing2025.java`、`CarOnlyRoadPricing.java`），否则提议换方式时看不到政策；
  2. 检查估算器和 NYC 自己的打分（`NycScoring.java`）是否一致，包括公交拥挤；
  3. 成本：每个换方式的人要给所有方式组合找路。2018 年说靠并行，每轮时间差不多；我们的重新规划约占试新方案期每轮的 12%，需要实测；
  4. 依赖：项目现在没有引入这个扩展，需要在 `pom.xml` 加 `org.matsim.contrib:discrete_mode_choice`（MATSim 2026.0）。
- **相关、还没读的：** matsim-libs 的 [`contribs/informed-mode-choice`](https://github.com/matsim-org/matsim-libs/tree/main/contribs/informed-mode-choice)（Rakow & Nagel 2023，*An annealing based approach to informed mode choice in agent-based transport simulations*，Procedia Computer Science 220:667–673，DOI [10.1016/j.procs.2023.03.086](https://doi.org/10.1016/j.procs.2023.03.086)）：同样是按估算效用提议方式，另外加了退火和剪掉没有希望的选项。全文还没拿到。

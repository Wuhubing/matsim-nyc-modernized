# [03] Horni, Nagel, Axhausen (eds.) 2016 — The Multi-Agent Transport Simulation MATSim

- **Venue**: Ubiquity Press，开放获取（CC BY 4.0），DOI 10.5334/baw，620 页
- **Domain / Tier / Priority**: MATSim & agent-based traffic sim / 1 / High
- **Link**: https://ubiquitypress.com/site/books/10.5334/baw（表中链接只是书目页面）
- **依据**: ✅ 已读原文。全书 PDF 取自 OAPEN / Open Research Library 镜像，97 章约 600 页。**与 RQ1 相关的章节逐章读完全文**（2026-10-19 补读）：
  - Ch.1 Introducing MATSim；Ch.3 Scoring（含 §3.3.3 得分平滑、§3.3.4 MSA）；Ch.4 配置（全章，含 §4.2.3 并行、§4.2.4 随机种子、§4.3 mobsim、§4.5 replanning）；
  - Ch.11 QSim；Ch.32 Cadyts；Ch.39 PSim；Ch.40 性能经验；Ch.43 已停用模块（DEQSim、Planomat）；Ch.46 历史（性能相关部分）；
  - Ch.47 agent-based 交通分配；Ch.48 Monte-Carlo 引擎；Ch.49 选择模型（全章含附录）；Ch.97 研究方向（§97.1–97.3）。
  - **未读**：Ch.5–31、33–38、41–42、44–45 的扩展模块说明（停车、电动车、公交、可视化等），Ch.50–51，Ch.52–96 的场景介绍。这些与加速或收敛无直接关系。
- 标【推断】的是我们的映射/建议，不是书中原话。

> 一句话：MATSim 官方手册。对 RQ1 有三处直接相关：(1) innovation/selection 的配置与"关掉创新"的理论理由（§4.5、§47.3.2）；(2) **PSim**：用上一轮出行时间做 surrogate，在两次 QSim 之间插多轮便宜的伪仿真（Ch.39）；(3) MATSim 是 Markov 链：**有创新时不可约性不成立，关掉创新后才"可能"存在唯一平稳分布**（Ch.48）。

## 1. 瓶颈（书中原话）
- Ch.39："MATSim's major current performance limitation is the network loading simulation, i.e., the mobsim"。
- Ch.40：行为模块（route、destination innovation）多线程化很直接，"the main challenge is the mobsim"。QSim 用 1 s 步长，若 24 h 在 120 s 内算完，就是每秒 720 轮线程间交互。
- Ch.39 §39.4.1：带公交的大场景中，"the time spent replanning can be up to twice that of the queue simulation"。
- Ch.48 §48.3：即使创新能做到不可约，"the resulting process dynamics would be slow due to the state space size"，即慢在探索。

## 2. 手段
| 手段 | 书中描述 | 出处 |
|---|---|---|
| 策略权重 | 每个 strategy 有权重，例如 ChangeLegMode 0.1、TimeAllocationMutator 0.2、SelectExpBeta 0.7；权重会归一化；可按 subpopulation 设置 | §4.5 |
| TimeAllocationMutator | 在可配置范围内**随机**平移活动结束时间 | §4.5.1.1 |
| 方案记忆 | `maxAgentPlanMemorySize` 例 5；默认删除得分最低的；书中说"This option is not yet well investigated" | §4.5.1.4 |
| 选择器 | SelectExpBeta（MNL）、ChangeExpBeta（按 e^{β(Sj−Si)/2} 切换，满足细致平衡，收敛到 MNL）；BestScore 容易卡在次优 | §4.5.2，§47.3.2.1 |
| 关掉创新 | `fractionOfIterationsToDisableInnovation`，出于理论原因建议最终关掉，并配合 MSA 得分平均 | §4.5.3，§49.1.1 |
| **PSim** | 周期性地用 meta-model 替代 QSim，"running approximately one hundred times faster"；用上一轮 QSim 的 TravelTime、站间时间、候车时间估计方案表现，在 QSim 之间做多轮"变异 + 评估" | Ch.39 |
| 多线程 QSim | Dobler 报告大场景接近线性加速，小场景几乎没有收益 | Ch.40 |
| within-day 重路由 | Märki et al. 2014、Dobler 2013 指出可减少达到均衡所需的迭代数 | Ch.40 |

## 3. 省在哪一项
- PSim：**每步计算**（便宜地评估创新），效果上是在相同 QSim 轮数内**探索更多变异**，所以也省 **QSim 迭代次数**。
- 多线程 QSim：每步计算。

## 4. 快了多少，代价是什么（原文数据）
- PSim（苏黎世 10% car，跑到"标准方法 100 轮的得分"为止，Fig. 39.2）：
  - 配置 1：每轮 QSim 配 9 轮 PSim，replanning rate 0.3；
  - 配置 2：每轮 QSim 配 24 轮 PSim，replanning rate 0.1。
  - 书中只说"dramatic decrease in computation times"、所需 QSim 轮数减少、时间随核数线性改善，**没有给具体倍数**。原文数字见 [46 Fourie et al. 2013](46_Fourie2013_PSim.md)：QSim 轮数 101 → 13–20；16 核墙钟时间减半以上；但 mode share 和 link 流量有偏移。
  - 代价：replanning 时间变多（但可完全并行）；PSim 是近似评估。
  - 书中观察："the distribution of mutation operation numbers can be dramatically spread out with the PSim approach"，并且这种做法对**随机变异型**策略更有利。
- 多线程 QSim（Table 40.1，Gauteng 52.3 万条 link）：1% 人口在 2014 年笔记本上 1 线程 110 s，6 线程 57 s，8 线程 55 s，**约 2 倍后就饱和**。这与我们只用 3.8/16 核的现象一致。

- **补读发现（与 RQ1 直接相关）**：
  - **§4.2.3 并行建议**："fewer threads are almost always better in terms of throughput"。在集群上做标定或情景探索时，"run a large number of simulations simultaneously with a low number of threads" 比少量多线程运行更有效率。【推断】这直接支持我们"16 核只用 3.8 核"的诊断：与其加线程，不如同时跑多个种子，这正好也满足多种子验证的需要。
  - **§4.2.4 随机种子**：不显式设置时，MATSim 总是从固定的内部种子开始，同一配置跑两次结果完全一样。【推断】做多种子实验时必须显式改 seed。
  - **§4.3.1 stuck time**：默认 10 s 不动就强行把车推过路口（解决 gridlock）。未发表的系统性研究发现，调大这个值后与计数的吻合反而变差。
  - **Ch.43 Planomat（被放弃的 surrogate 最优回应模块）**：它用遗传算法在一轮内评估多个时间/方式方案，用的是**自己重写的简化 mobsim**。三个问题导致它被放弃：(1) 简化 mobsim 跟不上核心 mobsim 的改动（收费、开放时间等），"Planomat's idea of a good plan often diverged from MATSim's"；(2) 总是返回同一个解，缺乏多样性，一旦与核心评估不一致就"insists on returning only suboptimal plans"；(3) 维护成本高。书中总结："best reply modules somehow need to follow core system development"，PSim（复用 mobsim 输出）是替代方案。
  - **§49.2.2 无偏选择集生成**：在 MATSim 迭代里插入 **Metropolis–Hastings 接受步**，使平稳选择分布等于对全集 U_n 的 MNL。用最优回应生成新方案时，接受规则在 μ_inno→∞ 下变成"新方案得分 ≤ 被替换方案得分才接受"。两者的得分要在**随机抽取的另一轮平稳迭代**的路网条件下计算，因为最优回应方案在最近一轮必然最好。这种"反直觉"的修正是为了抵消最优回应的选择偏差。
  - **§49.1.2 得分平滑**：指数平滑的得分无偏，方差为 α/(2−α) 倍原始方差。
  - **§97.3.1**：方案在选择集中的稳态概率 q_i = p_create/p_remove。默认"删最差方案"加上近似最优回应的生成，使 MATSim **严重高估高分方案**：p_i ∼ exp((β_choice+β_create+β_remove)S_i)。
  - **§97.2 明确把我们的问题列为开放问题**：用快速近似（如 within-day 重路由）加速均衡搜索，需要研究 "a) if the approach is indeed faster and b) if the resulting set of plans is unbiased by the fast initialization"。
  - **§97.3.5**：迭代过程究竟是行为学习还是纯数值方法，解释不明确。

## 5. 怎么证明结果没变
- PSim：以"达到同一目标得分"为终点比较时间，**没有比较均衡分布**。
- Ch.48 §48.4 给出正式框架：用 R 个不同随机种子，取最后一轮输出 y_r，用 (1/R)Σm(y_r) 估计平稳分布 Π(Y) 下的期望、方差、超阈值概率。只有在输入无不确定性**且方案集固定**时，才"could be feasible"用单次运行内多轮平均代替多次复制。

## 6. 假设（书中明确的）
- Ch.48：MATSim = Markov 链，状态是 Z（plans 及其 scores）。
  - 非周期性"likely"成立。
  - **开着创新时"irreducibility cannot be postulated"**：加入或删除方案后，部分状态空间就不可达。
  - 关掉创新后，标准配置"likely"不可约，理由是引用 Cascetta 1989 对 route choice 的类似结果。
  - 结论：只有方案集固定时，长期分布"likely to exist and be unique"。
- §47.3.2 脚注：没有创新、得分用 MSA 时，ChangeExpBeta 定义一个遍历 Markov 过程，收敛到唯一的 MNL 稳态概率。
- §47.3.2.2：系统"well-behaved"（稳定不动点）时得分会收敛；否则 MSA 可以强制收敛，"but the meaning is less clear"。

## 7. 能否用于 MATSim？怎么用
**✅ 就是 MATSim。对 RQ1 的结论：**
1. **PSim 必须作为对比基线**。它已经做到"用 surrogate 便宜地评估创新、在 QSim 之间多做探索"，而且书里点明它对随机变异更有利。【推断】我们的方法如果是"先筛掉无效创新"，与 PSim 的区别必须讲清楚：PSim 是**全员**交替使用伪仿真，没有决定**哪些** agent 或**哪类**创新值得评估，也没有检验均衡分布是否改变。
2. **均衡定义**：Ch.48 明确了"唯一平稳分布"只在**关掉创新后**才（可能）成立。【推断】所以加速方法只要最后仍关掉创新、在固定方案集上选择，均衡定义就不变；不同方法之间的差别体现在**最终方案集**上。RQ2 应比较的是"最终方案集 + 固定方案集上的平稳分布"。
3. **RQ2 验证**：直接引用 §48.4 的多种子估计框架。
4. 【推断】**two-stage 筛选必须吸取 Planomat 的教训**：低保真评估器要么直接复用核心 mobsim 的输出（像 PSim 那样），要么把筛选结果用核心 mobsim 抽检，否则低保真和高保真的"好方案"会逐渐分离。§49.2.2 的 MH 修正提供了理论工具：筛选本身会改变平稳分布，需要接受概率修正，或者至少用多种子 + pooled R̂ 检验分布没有移动。
5. 【推断】§97.2 的原话可以直接作为 RQ1/RQ2 的动机引文："research … is needed to see: a) if the approach is indeed faster and b) if the resulting set of plans is unbiased by the fast initialization"。
6. 书中承认方案删除规则"not yet well investigated"（§4.5.1.4），而 Ch.49 讨论了选择集演化问题。【推断】这两处是我们方法可以切入的"已知空白"。

## 延伸阅读（书中引用）
- Fourie, Illenberger, Nagel 2013, TRR 2343, DOI 10.3141/2343-09（PSim 原文，有具体加速数字）
- Märki et al. 2014；Dobler 2013（within-day 重路由减少迭代数）

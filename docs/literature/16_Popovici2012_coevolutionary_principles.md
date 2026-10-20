# [16] Popovici, Bucci, Wiegand, de Jong 2012 — Coevolutionary principles

- **Venue**: Handbook of Natural Computing（Springer），pp. 987–1033，DOI 10.1007/978-3-540-92910-9_31
- **Domain / Tier / Priority**: Evolutionary algorithms / 1 / Medium
- **Link**: https://doi.org/10.1007/978-3-540-92910-9_31（SpringerLink）。用户通过图书馆下载了整本手册（2105 页），本章位于 PDF 第 1040–1086 页；整本 PDF 太大，没有复制到 pdf/ 文件夹。
- **依据**: ✅ 已读全章（pp. 987–1028 正文：§1 引言与三个应用、§2 问题与解（solution concept）、§3 算法设计（表示与评价）、§4 分析（进步/单调性/性能比较、偏差分析综述）、§5 展望、§6 结语；pp. 1028–1033 参考文献只核对了范围）。标【推断】的是我们的映射。
  - 旧版笔记只核对了摘要，并把一些病理（cycling、disengagement 等）列为"待核实的背景知识"。读全文后：本章**没有**以列表形式讨论这些病理名称，而是从"解的概念"和"进步无法度量"的角度讨论；动态病理只在 §4.2.1 提到（稳定周期、混沌轨道、被差的局部最优吸引）。

> 一句话：共同演化算法（CoEA）用于没有现成评价函数的问题，个体的好坏只能通过与其他演化个体的**交互结果**来判断（"subjective fitness"），所以两个个体的优劣排序会随种群变化而翻转。本章主张先明确**解的概念（solution concept）**——到底要找什么——再设计算法；并指出这类问题的核心困难是：**算法看到的只是不完整的交互信息，无法直接知道自己是否在进步**。

## 1. 瓶颈（原文 §1、§4.1）
- 不是计算量，而是"How could one possibly build an effective algorithm when any time one believes A is better than B it is possible that later one will believe B is better than A?"
- 普通优化中"迄今最好"的质量随时间单调不减；在大多数共同优化问题中这一点**不成立**：判断一个候选解的真实质量需要与（通常无法穷举的）所有测试交互，算法只能基于不完整的信息比较候选解。
- 原文强调，这些困难来自问题本身，不是"演化"的问题，任何算法解这类问题都会遇到。

## 2. 手段（原文 §2–4）
- **概念框架（§2）**：交互域（interactive domain，一个或多个"度量"把交互映射到结果）→ 在其上定义 co-search / co-optimization 问题 = 哪些角色构成解（组件 vs 测试）+ 潜在解的形式（单个实体、集合、混合分布、组合）+ **解的概念**。
  - 两类问题：**组合式（compositional）**——所有角色都是组件，解是一个"团队"（例如每个变量一个种群）；**测试式（test-based）**——一个角色是组件，其他角色用来测试它。
  - 解的概念举例：理想团队（ideal team）、最坏情况最好（maximin）、同时最大化所有结果、期望效用最大（MEU）、**Nash 均衡**、Pareto 最优集及其最小等价集。原文说"details of the problem definition and algorithm design have much more impact on the overall behavior of a CoEA than details of the interactive domain"。
- **算法设计（§3）**：个体、种群、**档案（archive，跨代的记忆，可以存解或用于评价，例如 hall-of-fame）**；评价时要选择**与谁交互**（全混合太贵；个体中心 vs 种群中心；best-of-generation 等）和**如何聚合**多次交互的结果（取最好/最差/平均各有不同的、强烈的偏差；或保留为向量用多目标方法）；多种群之间的通信（同步/异步、顺序/并行、频率）。
- **单调性（§4.1.1）**：Ficici (2004) 发现某些解的概念允许设计"全局单调"的算法（输出的解的真实质量不降）：Nash 均衡、Pareto 最小等价集、同时最大化、理想团队是；**MEU 和 maximin 不是**。但所有已知的全局单调算法都需要**无限内存**，而且单调性不说明进步的**速度**。
- **替代的进步度量（§4.1.2）**：CIAO 图（当代最好个体与各代祖先对手交互的矩阵）、master tournament、dominance tournament、population-differential、relative strength。原文明说它们"cannot tell how the algorithm is doing with respect to the goal"，只能显示是否有某种"局部"进步；取平均可能掩盖循环。
- **测试平台（§4.1.3）**：在能算出真实质量的人工问题（如 number games）上比较算法，希望结论能迁移。
- **性能比较与免费午餐（§4.1.4）**：Wolpert & Macready (2005) 把共同优化算法分成"搜索启发式"和"输出选择函数"两部分，证明某些解的概念下**存在免费午餐**；单调性与性能之间可能有取舍（Popovici & De Jong 2009）。
- **偏差分析（§4.2）**：演化博弈论模型表明，常见的选择方法可能导致**稳定周期甚至混沌轨道**；组合式 CoEA 中任何纯 Nash 均衡都是吸引不动点，种群会被**全局很差的局部最优**吸引（"relative generalization"）；完全混合的交互方式隐含了"按平均表现定义最优"的解的概念。

## 3. 省在哪一项
本章是方法论综述，不涉及计算节省；只在 §3.2.1 提到交互次数是主要成本，所以要选择只评估部分交互，以及交互样本数可以动态或自适应调整。

## 4. 快了多少，代价是什么
- 不给加速数字。引言中的应用例子：Hillis 的排序网络共同演化得到 61 个比较器的 16 输入网络（当时已知最小为 60），非共同演化的方法最好只到 63。
- 代价：解的概念选错或交互/聚合方式与解的概念不匹配，会得到"confusing and unsatisfactory results"。

## 5. 怎么证明结果没变
- 核心观点：没有外部标尺时，"判断是否在进步"本身就很难；只有在能算出真实质量的测试问题上才能可靠评估。
- 替代度量只反映局部进步，不反映离目标多远。
- 原文结论："canonical coevolutionary algorithms may be useful in co-optimization, yet they are not intrinsically co-optimizers"。

## 6. 假设
- 个体的评价依赖于与其他演化个体的交互；问题可以在静态意义上形式化（把动态的适应度地形看成结构更复杂的静态问题）。
- 单调性和免费午餐的理论结果大多针对有限交互空间、并假设内存不受限。

## 7. 能否用于 MATSim？怎么用
**🟡 概念框架，对 RQ3（怎么判断收敛）有用：**
- MATSim 书 Ch.47 和 Nagel & Flötteröd 2009 明确把 MATSim 描述为"co-evolutionary, population-based search"（[03](03_Horni2016_MATSim_book.md)、[04](04_Nagel2009_agent_based_traffic_assignment.md)），所以本章的问题设定适用。
- 【推断】用本章的语言：MATSim 是一个**组合式**问题——每个 agent 的方案是一个组件，所有 agent 的方案一起构成"解"，单个 agent 的得分取决于所有其他人的选择（subjective fitness）。目标解的概念是**（随机）用户均衡 = 一种 Nash 均衡**，而不是"理想团队"（系统最优）。本章说 Nash 均衡是"全局单调"的解的概念，但需要无限内存；MATSim 每人只存约 5 个方案，没有这种保证。
- 【推断】§4.2.1 的结论直接支持我们关注的风险：选择机制本身可能导致周期或混沌，组合式问题中种群会被差的 Nash 均衡吸引。所以加速方法改变了选择/创新机制后，可能落到不同的均衡（与 [52 Li 2024](52_Li2024_day_to_day_MEUE.md)、[10 Cascetta](10_Cascetta1989_stochastic_process_dynamics.md) 的多重均衡讨论一致）。
- 【推断】§4.1.2 的教训：MATSim 的平均得分曲线类似 CoEA 中的"主观适应度"，变平只说明某种局部稳定，不说明接近均衡。应补充与方法无关的外部指标：基于最优回应的 gap（[09](09_Lu2009_gap_function_DUE.md)）——它正是检验 Nash 条件的直接方法（固定其他人，看单个 agent 能否改进），以及多种子 R̂（[25](25_Vehtari2021_improved_Rhat.md)）。
- 【推断】§3.1.3 的 archive 概念对应 MATSim 的方案记忆；§3.2.2"聚合方式（取最好/平均/最差）有强烈偏差"对应 MATSim 的得分平滑（learningRate、BrainExpBeta）：用什么方式聚合历次得分，会影响最终落到哪个点。
- 【推断】"搜索启发式 vs 输出选择函数"的划分对应我们的方法设计：加速方法可以只改"搜索"（创新怎么生成、给谁），而保持"输出"（关掉创新后的选择阶段）与原版一致——这正是我们论证"均衡定义不变"的思路。

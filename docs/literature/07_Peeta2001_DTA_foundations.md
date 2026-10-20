# [07] Peeta & Ziliaskopoulos 2001 — Foundations of dynamic traffic assignment: The past, the present and the future

- **Venue**: Networks and Spatial Economics 1(3):233–265，DOI 10.1023/A:1012827724856
- **Domain / Tier / Priority**: DTA & traffic equilibrium / 1 / Medium（综述）
- **Link**: 表中 TRID 链接只有书目，**没有全文**。全文取自作者在 Purdue 的公开稿：engineering.purdue.edu/~peeta/data/disseminate/Disseminated-2001_NSE_DTARev.pdf
- **依据**: ✅ 已读全文（作者公开稿：§1–4 全部、表 1、参考文献；第二轮从头到尾重读）。标【推断】的是我们的映射。

> 一句话：DTA 综述，作为期刊专刊的开篇。把方法分成数学规划、变分不等式、最优控制和**仿真类**。核心观点：DTA 天生"ill-behaved"；要保证解的存在性、唯一性、稳定性，就必须牺牲交通真实性。所以仿真类方法放弃了唯一性和全局最优，转而追求可部署的启发式解。

## 1. 瓶颈（原文）
- 仿真类 DTA 在求解中以"predictive iterative mode"使用仿真器：每轮迭代都用仿真器预测交通状态，作为找方向的一部分，"the substantial computational burden associated with the use of a simulator"（§2.4）。
- 部署场景中，"the computational burden ... can be operationally restrictive"，所以很多框架"trade-off solution accuracy with computational efficiency"。

## 2. 手段（综述归纳）
- 解析类：Merchant–Nemhauser 数学规划、VI（Friesz 等）、最优控制。
- 仿真类：DYNASMART（Mahmassani、Peeta 等）、DynaMIT（Ben-Akiva 等）。仿真器负责流量传播，外层迭代求 UE/SO。
- 稳定性：Smith 的 Lyapunov 分析、Horowitz、Friesz 的 tatonnement、Cantarella & Cascetta 1995（随机均衡的平稳分布存在且唯一的条件）、Watling 1999。
- §3.3.4 有限理性的换路规则（Mahmassani & Jayakrishnan 1991）：只有当前路径比最优路径慢出 max(η·当前时间, τ) 以上才换路；η 是相对无差异阈值，τ 是绝对最小改进量。
- §3.3.1：唯一的行为实验证据是 Chang & Mahmassani 1988（100 名出行者、24 天）。
- §3.3.5：现有可运行模型中"path processing seems to be a key computational bottleneck"。
- §3.3.3：处理需求不确定性的一种做法是用大量随机需求样本反复跑确定性模型（Peeta & Zhou 1999），缺点是单次 DTA 的计算量乘以大量情景。

## 3. 省在哪一项
综述，没有提出新的加速方法；指出的权衡是"精度 vs 计算效率"（问题规模、仿真粒度）。

## 4. 快了多少，代价是什么
没有数字。

## 5. 怎么证明结果没变
综述指出：仿真类方法的"equilibrium conditions are only heuristically approximated"。原文还说，由于问题 ill-behaved，"notions of convergence and uniqueness of the associated solution may not be particularly meaningful from a practical standpoint"。

## 6. 假设
- 解析类为了可分析，需要 FIFO、可微、简化的 link 性能函数等限制性假设。
- 仿真类没有数学性质保证，原文明确说这是"the key limitation"。
- 均衡本身是否存在："the notion of equilibrium highly questionable"，因为供给、需求一直在变，所有参数都是随机的。

## 7. 能否用于 MATSim？怎么用
**🟡 用于背景和定位，不提供具体方法。**
- 【推断】MATSim 属于"仿真类 + 行为 agent"一支。本综述可以用来支持两个论点：
  1. 仿真类分配的唯一性和收敛性在理论上不可保证，所以我们的验证只能是**经验性、统计性**的（多种子、分布比较），而不是证明。
  2. 计算负担主要来自"每轮迭代都要跑一次仿真"，这正是 RQ1 主问题"减少迭代次数"的出发点。
- 【推断】§3.3.4 的阈值换路规则可以直接作为 approach 3（gap 定向 replan）的行为依据：agent 只在"当前计划得分与最佳响应之差超过阈值"时才创新，阈值同时有相对项和绝对项。
- 文中引用的 Cantarella & Cascetta 1995（随机均衡平稳分布存在且唯一的条件）可作为 [10 Cascetta 1989](10_Cascetta1989_stochastic_process_dynamics.md) 的延伸阅读。

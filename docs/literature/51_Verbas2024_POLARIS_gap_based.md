# [51] Verbas, Cokyasar, de Camargo, Gurumurthy, Zuniga-Garcia & Auld 2024 — Modeling Transit in a Fully Integrated Agent-Based Framework: Methodology and Large-Scale Application

- **Venue**: arXiv [2408.05176](https://arxiv.org/abs/2408.05176)（Argonne National Laboratory）
- **领域**: 2 DTA / 与 MATSim 同类的 agent 模拟器 POLARIS（近期）
- **依据**: ✅ 已读全文（arXiv v1，29 页：§1–5、表 1–3、图 1–12、参考文献）。✅ 2026-10-19 补读了被引的 **Auld, Verbas & Stinson 2019** 全文（Procedia CS 151:864–869，开放获取，[OSTI 1528926](https://www.osti.gov/servlets/purl/1528926)，6 页），见下方"补充"一节。

> 一句话：介绍 POLARIS（activity-based、多模式、高性能的 agent 模拟平台）中的公交路由、分配与仿真。**POLARIS 的动态交通分配建立在 gap-based 方法之上**，并有自己的个性化扩展。

## 1. 瓶颈（原文）
仿真类交通模型没有闭式解，必须在"找最短路 → 分配 → 仿真 → 重算最短路"之间迭代，需要决定"谁留在原路径、谁换到新路径"。

## 2. 手段（原文 §3.3）
- 不再像 MSA 那样随机挑人，而是 gap-based：**上一轮"路由时间与经历时间之差"越大的出行者，越可能被换到新的最短路径**（引 Sbayti 2007、Lu 2009）。
- POLARIS 的两点扩展（Auld et al. 2019）：
  1. 换路决策基于路由时间与经历时间的 gap；
  2. 把历史和当前的时变路况平均成每个 agent 的期望值，**权重按该 agent 上一轮的相对 gap 和迭代次数个性化**（修正的双参数 Weibull 生存函数）。

## 3. 省在哪一项
**迭代次数**。

## 4. 快了多少，代价是什么
本文没有报告 gap-based 相对 MSA 的加速数字（引用的是先前研究的结论："proven to be very effective"）。

## 5. 怎么证明结果没变
本文重点是公交建模与政策分析，不是验证分配算法：
- 全文没有收敛曲线、迭代次数或相对 gap 的数字。
- §4 的数值实验：芝加哥 2040 年，6 个政策杠杆组合，N = 765 次运行，用回归估计各杠杆对公交登车量的影响（全区 Adj. R² 0.959，城区 0.896）。
- 公交服务改善：公交方式份额 +8.86%，登车量 +9.33%；FMLM 补贴：+3.58% / +3.13%；电商增长：总出行 −7.62%，登车量 −6.14%；拥堵收费：份额 +0.75%，登车量 +1.16%。
- 这些结论都是**政策带来的变化**（与我们 RQ2 的口径一致），但单次运行的随机性和收敛程度没有讨论。

## 6. 假设
有一个"路由时间"作为参照，所以每个出行者的 gap 可以计算。

## 7. 对我们意味着什么
- 【推断】**与 MATSim 同类的 activity-based agent 模拟器（POLARIS）已经在用个体 gap 决定谁重新选路**，而且学习权重也按个体 gap 调整。我们的 approach 3（gap 定向 replan）必须引用它，新意要放在：(a) 把 gap 定义到 MATSim 的**全日计划得分**上（不只是路径时间）；(b) 与创新过滤、自适应控制结合；(c) 用多种子检验均衡不变。
- gap 机制的效果数字在 Auld et al. 2019，已读，见下节。
- 765 次运行做回归，说明 POLARIS 每次运行足够便宜，可以大规模扫情景；MATSim-NYC 做不到，这正是加速的动机。

## 补充：Auld, Verbas & Stinson 2019 — Agent-Based Dynamic Traffic Assignment with Information Mixing（全文已读）
- **问题**：仿真类 DTA 的收敛。作者原话："the computational time of a single iteration can be high for large-scale networks"，所以要减少迭代数。
- **目标函数**：总 gap 最小化 min G = Σ_q (C_q − Γ_q)，其中 C_q 是经历时间，Γ_q 是路由时间。相对 gap g'_q = (C_q − Γ_q)/Γ_q。
- **两个机制**：
  1. **换路**：上一轮 gap 小的 agent 可以留在原路径，gap 大的才重新路由（概率式，沿用 Sbayti 2007、Lu 2009 的思路）。
  2. **信息混合**：路由用的 link 成本 = w·当前路况 + (1−w)·历史路况。权重 w = exp(−(Δt/(β g''_q))^γ) 是修正的 Weibull 生存函数，Δt 是距离进入该 link 的时间。factored gap g''_q = (1 − g'_q)Ω + g'_q。gap 越小，越信任历史（上一轮结果）；gap 越大，越信任当前路况。
- **实验**：Bloomington, IL，2,540 节点、7,023 link，约 43.9 万次小汽车出行。参数 β=900，γ=2.5。四种方案：
  - S1 静态（按当前密度路由）：相对 gap 一直约 15%，小波动来自多线程的随机性；
  - S2 只用 gap-based 换路：第 7 轮后收敛到约 2.5%，之前**明显振荡**；
  - S3 gap-based 换路 + 信息混合（Ω=1，不按个体 gap 调权重）：第 7 轮后收敛到同一水平，振荡明显减少；
  - S4 gap-based 信息混合，Ω 取迭代次数的倒数（类 MSA）：**2 轮后就收敛**。
- **局限（作者承认或我们发现的）**：
  - 只有一个中等规模网络、一次运行，没有多种子，也没有误差带；
  - 只看相对 gap，**没有检验收敛到的流量分布是否与 S2 相同**；
  - 参数敏感性分析留作未来工作（计划在 Chicago 上做）；
  - 只做路径选择，不含方式、时间等维度。
- 【推断】对我们：
  - (a) 这是 approach 3（gap 定向 replan）最直接的先例，而且给了数字：同一 gap 水平，迭代数从 7 降到 2。
  - (b) Ω=1/n 的设计就是我们 approach 2 的"1/t 式衰减"，把它和个体 gap 结合，是 approach 2 和 3 的组合。
  - (c) 他们没检验均衡分布是否改变，这正是我们 RQ2 的切入点。

## 可借鉴的设计（2026-10-19，用户确认，已写进总纲 v2.2 第 4 节）

按"最后评估之前的搜索可以自由设计、最后评估固定"判断，四个设计都只改搜索期，不碰最后评估段（只做选择）。

| 设计 | POLARIS 怎么做 | 搬到 MATSim | 对应事实 | 风险 / 预期 |
|---|---|---|---|---|
| 1. 按效用选方式 | logit / nested logit 在路况矩阵（skims）或路由时间上给各方式算效用再选（已读原文，见 [61](61_POLARIS_system_iteration_and_pricing.md)；模型出处是 Gurumurthy et al. 2020，不是 Auld & Mohammadian 2012） | 换方式时按估算效用或 H1 预测器提议，保留一部分均匀随机提议；执行和打分仍由 MATSim 做 | 一（方式是主要缺口）、二（随机换方式 71% 明显更差） | 估算和执行可能分离（Planomat）；潜力最大 |
| 2. 路况混合 | 找路成本 = w·当前 + (1−w)·历史（Auld 2019 S3） | 只改找路用的 TravelTime，最近几轮加权平均，权重可按 1/n 衰减 | 三（集体换路过冲） | 不依赖 gap 的 S3 只减少振荡，轮数没少；平滑过头对新收费反应慢 |
| 3. 热启动 | 从上一年路况矩阵出发，迭代数 2–11（二手来源，待核实） | 已在做（W0/W1） | 五 | 多重均衡下要用同样热启动的基线配对 |
| 4. 按测得的时间差挑人 | 上一轮"经历时间 − 路由时间"大的人更可能换路（Auld 2019 S2/S4，7 → 2 轮） | 从事件或重新规划日志算每次出行的时间差，按它决定重新找路的概率 | 三 | 只覆盖路线层；Auld 只有一次运行、没检验终点 |

**"不用 G"的边界（用户确认）：** 设计 4 用的是仿真中直接测得的时间差，不是 G 估算器，允许进入方法。

**补读结果（10-19）：** POLARIS 2016 系统论文和两篇用 POLARIS 的应用论文已读，见 [61](61_POLARIS_system_iteration_and_pricing.md)。仍待读：Gurumurthy et al. 2020（方式选择）、Verbas et al. 2018（DTA 收敛）。

# [19] Mertikopoulos, Papadimitriou, Piliouras 2018 — Cycles in adversarial regularized learning

- **Venue**: SODA 2018（arXiv 1709.02738v1）
- **Domain / Tier / Priority**: Learning in games / 1 / Medium（学习动态为什么会循环）
- **Link**: https://arxiv.org/abs/1709.02738
- **依据**: ✅ 已读全文（arXiv v1，22 页：§1–5、附录 A–D 全部证明、参考文献；第二轮从头到尾重读）。标【推断】的是我们的映射。

> 一句话（摘要）：把正则化学习（FoReL，包括 hedge、乘法权重、梯度下降等）放到**零和博弈**中相互对抗。连续时间的 FoReL 动态是 **Poincaré 回归**的：几乎每条轨迹都会无限次回到初始点任意小的邻域。这种循环对各玩家选用的正则项（可以各不相同）、效用的正仿射变换都稳健，在网络化竞争（零和 polymatrix 博弈）中依然存在。

## 1. 瓶颈
理论问题："Does the system converge to a Nash equilibrium? Does it even stabilize?" 基于遗憾（regret）的分析只能保证**时间平均**收敛到粗相关均衡（CCE），分辨不出系统是收敛、循环还是混沌。

## 2. 手段 / 分析
- 研究连续时间的 FoReL：后悔率 O(1/t)，并把 replicator dynamics 和 projection dynamics 作为特例（原文说这些是"transportation science"中研究最多的博弈动态之一）。
- 换到"累计收益差"的对偶空间：动态是**体积守恒**（不可压缩）的。
- 有内部 Nash 均衡时，存在**守恒量** G(y) = Σ[h*_i(y_i) − ⟨y_i, x*_i⟩]。
- 体积守恒 + 有界 → Poincaré 回归定理 → 回归。
- 没有内部均衡时（定理 4.3），G 随时间减小，轨迹收敛到最大支撑 Nash 均衡所张成的那个面，然后在该面内继续游荡；只有博弈有唯一的纯策略均衡时才真正收敛。
- 定理 3.1：连续时间 FoReL 的遗憾界是 O(1/t)，而离散时间最坏情况是 Θ(t^{−1/2})。

## 3. 省在哪一项
不适用（负面结果）。

## 4. 快了多少，代价是什么
负面结论（原文）："Does fast regret minimization necessarily imply (fast) equilibration in this case? … We settle these questions with a resounding 'no'"。时间平均收敛不代表实际轨迹收敛。

## 5. 怎么证明结果没变
数学证明，并在 3 人零和 polymatrix 博弈上给出数值轨迹图（Fig. 1）。

## 6. 假设
- **零和**（或常和、严格竞争）博弈；有内部 Nash 均衡（回归结论需要）。
- 连续时间、全信息的 FoReL。

## 7. 能否用于 MATSim？怎么用
**❌ 结论不能直接搬到 MATSim，但有两点启示：**
- 【推断】交通是拥堵博弈，Hofbauer & Sandholm 2002 将其列为势博弈（[18](18_Hofbauer2002_stochastic_fictitious_play.md)），而不是零和博弈。所以本文的"必然循环"不适用于 MATSim 的主体结构。
- 【推断】两点启示：
  1. "**遗憾小 / 时间平均收敛 ≠ 实际轨迹收敛**"。在 MATSim 中，"平均得分曲线平了"可能只说明某种平均意义下的稳定，个体选择仍可能在振荡（如出发时间来回摆动）。RQ3 应同时看末轮状态和时间平均。
  2. 本文参考文献 [26]（Palaiopanos, Panageas & Piliouras 2017）题为 *Multiplicative Weights Update with Constant Step-Size in Congestion Games: Convergence, Limit Cycles and Chaos*：说明即使在拥堵博弈中，**固定且较大的步长**也可能出现极限环和混沌。这与 [53](53_Anagnostides2022_last_iterate.md) 的"学习率太大会混沌"一致，可作为"激进加速有风险"的直接依据（该文本身未读）。
  3. 回应 Yining 的 GAN 类比：GAN 是两人零和，正是本文所说的循环场景；MATSim 的结构是多人拥堵博弈，更"友好"。所以 GAN 的循环病理**不是** MATSim 慢的主要原因（见 [20](20_Daskalakis2018_optimistic_GAN.md)）。

# [04] Nagel & Flötteröd 2009 — Agent-based traffic assignment: going from trips to behavioral travelers

- **Venue**: IATBR 2009 resource paper（PDF 日期 2009-11-09）；后改写为 MATSim 书 Ch.47
- **Domain / Tier / Priority**: MATSim & agent-based traffic sim / 1 / High
- **Link**: https://infoscience.epfl.ch/record/152368/files/NagFlo09.pdf
- **依据**: ✅ 已读全文（表中链接可下载）。标【推断】的是我们的映射。

> 一句话：从静态 trip-based 分配出发，逐步推广到"个体 agent + 完整日计划 + 随机网络加载"，定义了 **agent-based UE** 和 **agent-based SUE**，并把 MATSim 的求解过程解释为"共同演化、基于种群的搜索"。文中明确提出：**切换概率应与预期改进幅度成正比**；**还没有适用于全日计划的可操作 gap 函数**。

## 1. 瓶颈
- 迭代求解：为了稳定，每轮只能让一部分人切换（"inert shift"），所以要很多轮。
- 选择集是组合爆炸的：全日计划的最优回应很难算（Recker 2001），所以要转向 SUE 和多方案的做法。
- 网络加载要模拟上百万 agent（§3.3）。

## 2. 手段 / 机制（文中给出的）
- **Agent-based UE（§3.1）**：每个 agent 生成"上一轮的最优回应"，然后以一定概率切换过去。建议
  P(old→new) ∝ max[0, e^{β(S_new−S_old)} − 1] ≈ β(S_new − S_old)，
  即**切换概率与改进幅度成正比**。β 越小越稳定，但越慢。
- 也可以用 MSA。文中指出 MSA 的缺点是"the switching rate does not depend on the magnitude of the expected improvement, which possibly means slow(er) convergence"。
- 也可以用 gap 函数（引用 Lu et al. 2009）。原文："we are not aware of any operational gap function that applies to all-day plans"。
- **Agent-based SUE（§3.2）**：每个人维护一个方案"种群"（= 选择集），按 logit 选择；建议使用收敛到 logit 的切换过程 T(i→j) = γe^{β(Sj−Si)/2}（满足细致平衡），也就是 ChangeExpBeta。
- 得分平滑：MSA 或学习率 α，S_new = (1−α)S_old + αS̃（§3.2.2）。
- 创新（§3.2.3）：随机扰动成本后做最优回应，或每轮重新做最优回应，或用变异、交叉、构造式算法。

## 3. 省在哪一项
理论文章，没有给出加速实验。它指出可以省的环节是**迭代次数**（切换规则）。

## 4. 快了多少，代价是什么
没有加速数字。理论上的权衡（§3.1）："making β smaller makes the fixed point more stable, but slows down convergence"。§3.3 提到：不并行时，全瑞士（800 万人）一天约 1.5 h（Waraich et al. 2009）。

## 5. 怎么证明结果没变
文中给出的是定义层面的判据：
- UE：不动点处没有人切换（最优回应的得分等于现有方案的得分）。
- SUE：agent 从平稳的选择分布中抽样，由此产生的交通状态分布又重新生成该选择分布。

## 6. 假设
- particle UE 是组合问题："even a problem that had a unique solution in its continuous version may have a large number of solutions in its discrete version"。
- 物理排队（spillback）"has been shown to be an apparently inevitable source of multiple Nash equilibria"（引 Daganzo 1998）。→ **MATSim 很可能有多重均衡**。
- 脚注 1：关掉创新、MSA 平滑得分之后，切换逻辑定义了一个遍历的 Markov 过程，收敛到唯一的 logit 稳态。
- 随机网络加载与确定性网络加载在概念上差别不大，因为选择本身已经是随机的（§2.4）。

## 7. 能否用于 MATSim？怎么用
**✅ 是 MATSim 的理论基础，对 novelty 判断很关键：**
1. **"按改进幅度决定切换"不是新想法**：本文 2009 年就提出了 P ∝ β(S_new − S_old)（针对"已经生成的新方案是否被采用"）。而 Zhuge 2021 是按"当前方案与记忆中最好方案的差"决定谁去创新。【推断】我们必须说清楚自己作用在哪个环节：是谁去创新、生成什么样的创新，还是采不采用。
2. **gap 函数的空白**：作者 2009 年明确说没有适用于全日计划的可操作 gap 函数。【推断】若我们能定义一个可算的全日计划 gap（例如"用 router/PSim 在上一轮出行时间下得到的最优回应得分 − 当前得分"），并用它做收敛判据或选择性创新的依据，这是一个有文献支撑的贡献点。后续文献是否已有人做，需要再检索。
3. **多重均衡**：引用本文和 Daganzo 1998 作为"MATSim 可能有多个均衡，所以加速后必须检查是否落在同一个均衡"的依据。
4. **均衡定义（RQ2）**：使用 agent-based SUE 的定义，即平稳选择分布的自洽。

# [22] Roberts, Gelman, Gilks 1997 — Weak convergence and optimal scaling of random walk Metropolis algorithms

- **Venue**: Annals of Applied Probability 7(1):110–120，DOI 10.1214/aoap/1034625254
- **Domain / Tier / Priority**: MCMC & sampling / 2 / Medium（最优接受率 0.234）
- **Link**: 表中 Project Euclid 链接用 curl 访问返回 403；全文取自北京大学课程页公开的出版社 PDF：math.pku.edu.cn/teachers/xirb/Courses/QR2013/ReadingForFinal/MCMC/euclid.aoap.1034625254.pdf
- **依据**: ✅ 已读全文（11 页：§1 结果、§2 证明 Lemma 2.1–2.6、§3 三个推广方向、参考文献）。标【推断】的是我们的映射。

> 一句话（摘要）：研究多维随机游走 Metropolis 的提议分布如何缩放才能最有效。当维数 n → ∞ 且提议方差按 1/n 缩放时，链的第一个分量弱收敛到 Langevin 扩散。最大化扩散速度得到渐近最优策略，它与接受率有关：**渐近最优接受率为 0.234**。主结果只对对称乘积形式的目标密度给出证明。

## 1. 瓶颈（原文 §1）
"If the variance of the proposal is too small, the Markov chain will converge slowly since all its increments will be small. Conversely, if the variance is too large, the Metropolis algorithm will reject too high a proportion of its proposed moves"。在此之前只有经验法则，没有理论依据。

## 2. 手段
- 目标为 n 维乘积密度 π_n(x) = Πf(x_i)，高斯提议，方差 σ_n² = l²/n。
- Theorem 1.1：时间加速 n 倍后，第一个分量弱收敛到 Langevin 扩散，速度为 h(l)。
- **Corollary 1.2**：h(l) 在 l̂ = 2.38/√I 处最大（I 是与 f 有关的信息量，f 为高斯时 I = 1/方差），此时平均接受率 a(l̂) = 0.23，扩散速度 h(l̂) = 1.3/I。
- 时间要加速 n 倍才得到极限，所以算法复杂度为 O(n)（作者称连续状态空间此前没有这类复杂度结果）。
- 实用法则（原文）："**Tune the proposal variance so that the average acceptance rate is roughly 1/4**"。

## 3. 省在哪一项
**迭代次数**（混合更快）。

## 4. 快了多少，代价是什么
- 原文没有给"比坏步长快多少倍"的数字，只给出最优点。
- 代价：结论是**高维渐近**结果，严格证明只针对乘积形式的目标。

## 5. 怎么证明结果没变
MCMC 由细致平衡保证目标分布正确，步长只影响效率不影响目标（这是 MCMC 的一般性质，本文不另作验证）。

## 6. 假设
- 目标是 iid 乘积密度（§3 讨论推广：分量不同但满足大数律条件时，最优接受率**仍为 0.234**，作者称这种稳健性是"the most useful practical implication of this paper"；推广的关键条件是尾 σ-代数平凡，作者指出它在热力学意义上相当于"没有相变"）。
- 高维极限；高斯提议；**目标分布固定**。
- **Theorem 1.1 要求链从平稳分布出发**（X_0 的分量都服从 f）。也就是说 0.234 描述的是"已经到达平稳后"的混合效率，不是从远处出发的 burn-in（瞬态）阶段。
- §3 另两个推广（只给思路，没有证明）：Markov 链形式的目标可以推广，但极限变成无穷维扩散；可交换（exchangeable）形式的目标会出现"渐近可约"，算法不再是 O(n)。

## 7. 能否用于 MATSim？怎么用
**🟡 作为启发，不是可以直接用的算法：**
- 【推断】类比：MATSim 的创新 ≈ 提议；创新被保留或采用 ≈ 接受。我们观察到约 15% 的创新有效，相当于接受率约 0.15。
- 【推断】启示 1：**无效创新不全是浪费**。最优效率时，约 77% 的提议也被拒绝。目标不应是"把无效率降到 0"，而是找到使探索速度最大的提议大小。论文中应讲清楚这一点，以免被审稿人质疑"为什么要消灭所有无效创新"。
- 【推断】启示 2：可以用接受率作为反馈信号来调节创新幅度（如时间变异范围），即自适应 MCMC（[23](23_Andrieu2008_adaptive_MCMC.md)），与 1/5 规则（[14](14_Eiben1999_parameter_control.md)）是同一思路。
- 不能照搬：MATSim 的"目标"随其他 agent 的方案变化（非平稳）；创新维度混合离散和连续；本文 §3 也说明，存在"相变"类结构时结论可能不成立，而多重均衡正是类似的结构。所以 0.234 这个数字对 MATSim 没有直接意义。
- 【推断】还有一点：本文结论针对平稳阶段，而我们要缩短的约 80 轮探索属于瞬态阶段（离均衡还远），两者不是同一个问题。

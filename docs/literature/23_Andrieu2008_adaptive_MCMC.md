# [23] Andrieu & Thoms 2008 — A tutorial on adaptive MCMC

- **Venue**: Statistics and Computing 18:343–373，DOI 10.1007/s11222-008-9110-y
- **Domain / Tier / Priority**: MCMC & sampling / 2 / Medium
- **Link**: https://people.eecs.berkeley.edu/~jordan/sail/readings/andrieu-thoms.pdf
- **依据**: ✅ 已读全文（31 页：§1–4 理论与准则，§5 新算法，§6 三个实验，参考文献）。标【推断】的是我们的映射。

> 一句话（摘要）：综述自适应 MCMC，即在运行中优化 MCMC 的参数。用简单的 toy 例子说明其理论基础，特别是**为什么自适应 MCMC 在某些基本性质不满足时会失败**，并由此给出设计正确算法的准则。再介绍**随机逼近**框架，用它系统地优化常用准则并分析算法性质；最后提出一系列在实践中稳健的新算法，用于人工的高维场景和 mine disaster 数据。

## 1. 瓶颈（原文 §1）
"the choice of the proposal distribution is crucial: the statistical properties of the Markov chain heavily depend upon this choice"。

## 2. 手段
- **Controlled MCMC**：参数 θ_i 随链的历史更新。
- **风险（§1–2）**："this type of adaptation can easily perturb the ergodicity properties … will in most cases lead to the loss of π as an invariant distribution"，可能产生非常返过程或不一致的估计量。
- **Vanishing (diminishing) adaptation（§3）**：让 θ_i 对最近访问状态的依赖越来越小。主要条件是"expected ergodicity and continuity of the transition probabilities"；但作者也指出，可验证的充分条件很难给出，因为必须证明算法不会"unlucky enough to tune θ to poor values"。§3 还举例说明 vanishing adaptation 本身也有缺陷。
- **准则与随机逼近（§4）**：θ_{i+1} = θ_i + γ_{i+1}·H(θ_i, X_{i+1})。例如"coerced acceptance probability"：H = min(1, 接受比) − α*，目标 α* = 0.234（RWM）、0.574（Langevin MH）、单维约 0.44。还有 moment matching，以 (2.38²/n_x)·Σ_π 作为提议协方差（Gelman et al. 1995）。
- **另一种做法（§1）**：先自适应，"stop adaptation once we have enough evidence"，然后用固定的好参数 θ̃ 跑标准 MCMC。作者讨论了停止规则（监控 Robbins–Monro 更新场的平均值）。

- **§5 新算法（作者原创部分）**：
  - **复合准则（compound criterion，§5.1）**：初值很差时，接受率会极低或极高，链几乎不动，于是"学不到目标分布"，自适应也学不起来（鸡生蛋问题）。解决办法：**在初始阶段**用 Robbins–Monro 把接受率强制拉到 0.234（log λ ← log λ + γ(α − 0.234)），同时学协方差。作者明说这种调节"likely not to be useful in the long-run"，但在早期很有用。
  - **"胆小"与"大胆"的移动（timid vs bold，§5.1.3）**：逐分量的小步更新（目标接受率约 0.44）先收集信息，再交给依赖协方差估计的全局大步更新。
  - §5.2 用在线 EM 拟合混合分布做局部化的随机游走；§5.3 在线 PCA 沿主方向更新；§5.4 离散变量用 Gaussian copula 嵌入连续空间。
  - §5.2 Example 1：独立提议（IMH）在高维时权重方差 exp(ε²n) − 1，会卡住，属于"very bold"更新，不适合作为自适应的基础。

## 3. 省在哪一项
**迭代次数**（更好的提议 → 更快混合）。

## 4. 快了多少，代价是什么
- 综述没有统一的加速倍数：
  - §6.1（50 维 erratic normal）：只用图比较，作者说按目标密度评估次数算"gains are clear"，没有给数字。
  - §6.2 banana（Table 1，100 次运行）：和标准 AM **结果相当**，例如 8 维 B0.1 上一阶矩范数 4.99±3.99 vs 4.85±4.20；只在难的 B0.1 上方差更小（4 维 5.20±5.69 vs 5.13±12.85）。
  - §6.3 mine disaster：初值很差（前 10,000 步拒绝率很高），算法能"rapidly recover"；不是所有调节参数都收敛，但后验直方图与 Hastie (2005) 一致。
- 代价：适应不当会破坏遍历性（链收敛到错误的分布）；需要选择适应步长序列 γ_i。

## 5. 怎么证明结果没变
- 理论：vanishing adaptation 加上连续性条件 → 遍历性。
- 实验：在已知目标（如 banana 形分布）上，比较 25 次运行（长 80,000，burn-in 60,000）的经验分位数与真值。

- §6.3 作者总结三点：(1) vanishing adaptation 不需要参数收敛也能保证遍历平均正确；(2) 参数序列的收敛性仍要研究；(3) 可以把自适应运行只当作"预调参"，之后用固定参数跑标准 MCMC，这样就没有遍历性问题。
- Table 4 的 harmonic mean 归一化常数估计在 banana 目标上方差很大，作者自己说不可靠。

## 6. 假设
- **目标分布 π 固定**，且对每个固定的 θ，P_θ 都以 π 为不变分布。
- 转移核关于 θ 足够光滑。

## 7. 能否用于 MATSim？怎么用
**🟡 需要改造，但给出了"自适应创新"的理论框架和风险清单，很值得借鉴：**
- 【推断】MATSim 中可以自适应的参数：各创新策略的权重、时间变异范围、按 subpopulation 的创新率。
- 【推断】更新规则用 Robbins–Monro：参数 ← 参数 + γ_t·(观测成功率 − 目标成功率)。
- 【推断】**MATSim 现有做法正对应本文 §1 的"先适应、再停止、再用固定参数"**：在 `fractionOfIterationsToDisableInnovation` 之后关掉创新，只在固定方案集上做选择（[03](03_Horni2016_MATSim_book.md)）。所以自适应只影响"生成了哪些方案"，**不改变最终选择阶段的定义**。这是我们方法"不改变均衡定义"的论证依据之一。
- 关键区别：本文要求"对每个固定 θ，不变分布都是同一个 π"。在 MATSim 中，**不同的创新参数会生成不同的方案集，从而得到不同的最终平稳分布**（[18](18_Hofbauer2002_stochastic_fictitious_play.md) 的多重静止点）。所以本文的遍历性保证**不能直接搬过来**，"均衡没变"必须用多种子实验验证（RQ2）。
- 本文 §2 的失败例子提醒我们：自适应规则可能把参数调到"坏值"，例如把某类创新的权重压到接近 0，从而永远不探索某些方案。设计时应设置下限（类似"containment"的思想）。
- 【推断】§5.1 的复合准则和我们的情况很像：MATSim 初期方案很差，大部分创新无效，这时候用"目标有效率"去调创新幅度最有用；后期作者也认为这种调节作用不大。这支持"自适应只在前期起作用，后期按 MATSim 原规则关掉创新"的设计。
- 【推断】timid/bold 对应：先做小幅度的时间变异（胆小），积累"哪些 agent 有改进空间"的信息后，再对这些 agent 做重路由或换模式（大胆）。

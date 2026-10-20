# [14] Eiben, Hinterding, Michalewicz 1999 — Parameter control in evolutionary algorithms

- **Venue**: IEEE Transactions on Evolutionary Computation 3(2):124–141
- **Domain / Tier / Priority**: Evolutionary algorithms / 1 / High（对应 MATSim 固定的创新比例）
- **Link**: https://cs.adelaide.edu.au/~zbyszek/Papers/self9.pdf
- **依据**: ✅ 已读全文（§I–VII 全部、图 1–2；第二轮从头到尾重读，参考文献列表核对了范围）。标【推断】的是我们的映射。

> 一句话：区分 **parameter tuning**（运行前定好、运行中不变）和 **parameter control**（运行中改变）。按"怎么改"分为 deterministic（按时间表）、adaptive（按搜索反馈，如 Rechenberg 的 **1/5 成功规则**）、self-adaptive（参数编码进个体，随进化一起优化）；另外三个分类维度是改什么、作用范围（种群、个体、基因）、依据什么证据。核心论点：EA 运行本身是动态过程，**任何静态参数都"seems to be inappropriate"**。

## 1. 瓶颈（原文 §II）
- 手工调参耗时，参数之间相互影响，组合无法穷举，调出来的值也未必最优。
- 更根本的是，不同阶段需要不同参数："large mutation steps can be good in the early generations … small mutation steps might be needed in the late generations"。所以静态参数本身就会导致性能变差。

## 2. 手段
| 类型 | 机制（原文） |
|---|---|
| Deterministic | p 换成 p(t)，按代数 t 的预设规则变化，"without taking any notion of the actual progress" |
| Adaptive | 用搜索反馈改变参数，如种群多样性、相对改进、解的绝对质量 |
| Self-adaptive | 参数编码进染色体，由自然选择驱动变化 |

- **1/5 成功规则**（§III-A）：每 n 代检查成功变异比例 p_s。p_s > 1/5 时步长 σ ← σ/c（放大）；p_s < 1/5 时 σ ← σ·c（缩小）；文中给出 0.817 ≤ c ≤ 1。
- §V 中与我们最接近的几种 adaptive 机制：
  - **Davis 的 adaptive operator fitness**：奖励产生更好子代的算子，提高其概率，并把奖励按递减方式回传给前几代"铺路"的算子；
  - Julstrom：按近期贡献调节交叉与变异的比例；
  - **Lis & Lis**：多个并行种群各用不同的 p_m、p_c、种群规模，定期比较后把参数向最成功的种群移动一级；
  - **竞争子种群**（Schlierkamp-Voosen & Mühlenbein；Eiben et al. 1998）：每个子种群用一种交叉，进展快的子种群变大，并有机制**防止任何子种群灭绝**。
- 重要警告（§III）：自适应**变异步长**不影响评估，eval(⟨x, σ⟩) = f(x)；但如果自适应的是**评估函数里的权重**（如约束惩罚权重），eval(⟨x, W⟩) = f_W(x)，进化就可能"cheat"，通过改权重而不是改解来"改进"。

## 3. 省在哪一项
**迭代次数 / 评估次数**（每个阶段用更合适的探索强度）。

## 4. 快了多少，代价是什么
- 综述没有统一数字。原文提到，很多研究即使只用简单的 deterministic 规则也改进了结果，因为"suboptimal choice of p(t) often leads to better results than a suboptimal choice of p"。
- §VI 警告"transitory behavior"：若某算子一时表现差，其子种群缩小，之后即使它变得有用也很难"恢复"。
- 代价（§VII）：参数之间的 epistasis（相互作用）使在线调参复杂；adaptive/self-adaptive 有学习成本，需要收集统计量或增加额外操作。有研究认为收益不足以抵消成本。"how much parameter control is worthwhile"仍是开放问题。作者指出公平比较应把**事先调参的时间**也算进去，但当时没有这样的比较。

## 5. 怎么证明结果没变
综述没有给统一的验证范式。所引研究一般在测试函数上比较解的质量和速度。

## 6. 假设
- 有可观测的"成功"信号（如子代优于父代）。
- 主要针对静态适应度的优化问题。

## 7. 能否用于 MATSim？怎么用
**✅ 思路几乎可以直接用，是最值得试的手段之一：**
- 【推断】按本文分类，MATSim 现在是 **deterministic control**：创新策略权重固定，到 `fractionOfIterationsToDisableInnovation`（如 0.8）后一刀切为 0。
- 【推断】改成 **adaptive control**：
  - 我们能观测创新是否有效，**有效率约 15%，低于 1/5**。按 1/5 规则，应缩小变异幅度（如 TimeAllocationMutator 的 mutation range）。注意：1/5 规则调的是**步长**，不是创新比例。调创新比例需要另外的规则，比如按策略统计成功率、动态分配权重。
  - 按策略类型（ReRoute、时间、mode）分别统计成功率，动态调整权重。
  - 按 agent 或 subpopulation 调整（MATSim 已支持按 subpopulation 设置策略权重，[03](03_Horni2016_MATSim_book.md) §4.5）。
- 【推断】Davis 的"按贡献奖励算子"可以直接对应 MATSim 策略：某策略生成的创新被保留并提高得分，就给该策略加权；§VI 的"无法恢复"问题说明权重必须有**下限**（我们 approach 2 中的 floor），否则早期表现差的策略（如 mode 创新）可能永远被压住。
- 【推断】Lis & Lis 的并行种群做法与 [48 multiMATSim](48_Moukir2024_multiMATSim.md) 很像（不同权重的并行实例、定期向最好者靠拢），可以作为 multiMATSim 的先例引用。
- **本文 §III 的"cheat"警告对我们很重要**：【推断】自适应只能作用在**生成创新**的参数上（步长、策略权重），不能改得分函数，否则就像自适应评估权重一样，会改变"均衡"本身。
- 收敛的理论保证：本文没有讨论。需要结合 [23 Andrieu & Thoms](23_Andrieu2008_adaptive_MCMC.md) 的"递减适应"条件，以及 MATSim 最终关掉创新的做法。

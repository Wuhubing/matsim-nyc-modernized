# [34] Peherstorfer, Willcox, Gunzburger 2018 — Survey of multifidelity methods in uncertainty propagation, inference, and optimization

- **Venue**: SIAM Review 60(3):550–591（已读 arXiv 1806.10761v1）
- **Domain / Tier / Priority**: Surrogates & multi-fidelity / 3 / Medium（综述）
- **Link**: https://arxiv.org/pdf/1806.10761
- **依据**: ✅ 已读全文正文（arXiv v1 pp. 1–32：§1–6；约 220 条参考文献未读）。标【推断】的是我们的映射。

> 一句话（摘要）：同一系统往往有多个评估成本和保真度不同的模型。优化、推断、不确定性量化等"外循环"应用需要在大量输入上评估模型，只用高保真（HF）模型往往算不起。多保真度方法把 HF 和低保真（LF）模型结合起来，前提是："**low-fidelity models are leveraged for speedup while the high-fidelity model is kept in the loop to establish accuracy and/or convergence guarantees**"。模型管理策略分为三类：**adaptation、fusion、filtering**。

## 1. 瓶颈
外循环应用要多次评估模型，只用 HF 模型时计算需求超出可用资源（摘要）。

## 2. 手段（原文 §1.3、§2）
- **LF 模型的类型**：简化模型（简化物理、粗网格、放宽收敛容差）、投影降阶模型（POD 等）、数据拟合模型（可由黑箱 HF 的输入输出直接得到）。
- **Adaptation（§2.1）**：在计算过程中用 HF 信息增强 LF。例如 EGO 每轮更新 kriging；用 HF 与 LF 的差（加性）或比（乘性）来修正 LF 输出。
- **Fusion（§2.2）**：同时评估 LF 和 HF，再融合输出。例如控制变量法：少量 HF 评估保证**无偏**，大量 LF 评估降低方差；co-kriging。
- **Filtering（§2.3）**：先用 LF 做过滤，只在满足条件时才调用 HF。例如**两阶段（delayed acceptance）MCMC**：候选样本先要被 LF 似然接受，才交给 HF 评估。
- **§4.2 两阶段 MCMC 的效率来源**（原文）："no high-fidelity model evaluation is necessary in the second stage if the candidate sample z_lo was rejected at the first stage. Since the rejection rate of MCMC is typically high, many high-fidelity model evaluations are saved"。

- **§3.2 多保真度 Monte Carlo（MFMC，控制变量 = fusion）**：估计量 s̄_MF = s̄_hi + Σα_i(s̄_lo,mi − s̄_lo,mi−1)，**无偏**；最优 α_i = ρ_i·σ_hi/σ_i，各模型评估次数按成本和相关系数解析给出。**比只用 HF 更省的条件**：√(c_lo/c_hi) + √(1 − ρ²) < 1（单个 LF 时）。即 LF 既要便宜，又要与 HF 高度相关；一个 LF 的贡献要结合所有模型才能判断。多层 Monte Carlo 是它的特例（粗网格层级）。
- **§3.3 多保真度重要性采样（filtering）**：用 LF 大量评估来构造偏置分布，用 HF 计算最终估计，所以**仍无偏**；如果直接用 LF 的指示函数估计，就是有偏的。
- **§3.4 阈值过滤 [128]**：先算 LF；|f_lo(z)| > γ 时直接用 LF 判断，**只有在边界附近（|f_lo| ≤ γ）才调用 HF**。γ 依 LF 误差选择，可使误差小于任意 ε；误差未知时有迭代的启发式。
- **§4.2 两阶段 MCMC 的细节**：第二阶段的接受率要用 LF 第一阶段诱导的提议 Q 来修正，才保持目标分布正确；§4.3 [54] 再用 HF 结果在线改进 LF（adaptation + filtering），可以证明 LF 后验与 HF 后验的 Hellinger 距离随迭代减小，估计量仍无偏。
- §4.4：把 LF 与 HF 的差当作额外的随机误差项（Bayesian approximate error model）。
- **§5 优化**：EGO 用期望改进平衡"利用/探索"，但**对初始点敏感**（先把 kriging 当真去选下一点）；多保真度信赖域法要求 LF 在中心点与 HF **值和梯度都一致**（一阶一致性），才能保证收敛到 HF 的最优；[151] 把**前几轮迭代的结果当作 LF 模型**。

## 3. 省在哪一项
**HF 模型评估次数**。

## 4. 快了多少，代价是什么
- 综述没有统一的加速倍数，取决于问题和 LF 与 HF 的相关性；MFMC 给出了"何时值得"的解析条件（见第 2 问）。
- 代价与局限（§6）：几乎所有方法都假设 HF 代表"真值"，忽略了 HF 本身也是近似；现有方法大多假设模型之间是线性的层级关系。

## 5. 怎么证明结果没变
把 HF 留在回路中，提供精度或收敛保证。例如控制变量估计量无偏；两阶段 MCMC 的第二阶段用 HF 似然做接受/拒绝，保证目标分布正确（细致平衡）。

## 6. 假设
LF 与 HF 估计同一输出量且相关；LF 便宜得多；外循环有明确的目标结果（§1.2 区分了 outer-loop 和 many-query）。

## 7. 能否用于 MATSim？怎么用
**🟡 框架非常适用，可以统一我们的几个候选手段：**
- 【推断】MATSim 现成的 LF 模型：
  - PSim（上一轮出行时间 + 不重跑仿真，[03](03_Horni2016_MATSim_book.md)），属于"简化模型"；
  - 降采样人口（[05](05_BenDor2021_population_downscaling.md)）、大时间步 mobsim（[01](01_Zhuge2021_MATSim_computing_time.md)），属于"简化模型/粗网格"；
  - 学到的创新有效性模型（[31](31_Lamperti2018_ABM_ML_surrogate.md)），属于"数据拟合模型"。
- 【推断】**最对口的是 filtering，具体就是两阶段 MCMC 的结构**：创新 = 候选样本；第一阶段用 LF（PSim 式评分）判断创新是否可能有效，被拒绝的不必进入 HF（QSim/Hermes 执行）；第二阶段由真实执行和得分决定是否保留。综述明确说两阶段 MCMC 的收益来自"拒绝率高"，而我们的创新无效率约 85%，正是这种情形。
- 【推断】adaptation 对应：每轮用 HF 结果修正 LF（PSim 的出行时间本来就每轮更新）。
- 原则："HF 留在回路中"对应最后阶段必须是完整 QSim + 关掉创新，这样均衡定义才不变。
- 建议把我们的方法定位为**"随机共同演化仿真中，基于多保真度过滤的创新筛选"**，并引用两阶段 delayed-acceptance MCMC（Christen & Fox 2005 等，即本综述引用的 [44]）作为理论原型。
- 与 PSim 的区别：PSim 更接近"用 LF 代替若干轮 HF"，没有逐个创新做 HF 确认式的过滤。
- 【推断】**§3.4 的阈值过滤是方法 1 最直接的设计模板**：LF 评分明显好 → 直接保留；明显差 → 直接丢弃；只有在"难判断"的区间才交给 QSim 执行。阈值 γ 应根据 LF（PSim 式评分）与 HF（实际执行得分）的误差来定，所以需要先测量两者的误差分布。
- 【推断】MFMC 的条件 √(c_lo/c_hi) + √(1 − ρ²) < 1 可以直接用来估算方法 1 是否划算：例如 LF 成本是 HF 的 1%（√ = 0.1），则需要 ρ > 0.995 才有收益——这个要求很高。不过这个条件是针对"估计均值"的控制变量法；我们的用途是过滤，收益来自拒绝率高，所以更合适的参照是两阶段 MCMC，而不是 MFMC 的公式。
- 【推断】[151]"用前几轮的结果当 LF"正是 MATSim 的情形：上一轮的出行时间就是现成的 LF。

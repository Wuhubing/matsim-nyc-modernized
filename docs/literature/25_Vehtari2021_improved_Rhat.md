# [25] Vehtari, Gelman, Simpson, Carpenter, Bürkner 2021 — Rank-normalization, folding, and localization: An improved R̂ for assessing convergence of MCMC

- **Venue**: Bayesian Analysis 16(2):667–718（arXiv 1903.08008v5）
- **Domain / Tier / Priority**: MCMC & sampling / 2 / High（RQ3 应采用这个版本）
- **Link**: https://arxiv.org/abs/1903.08008
- **依据**: ✅ 已读全文（arXiv v5：§1–5 及附录 A–D；在线附录未读）。标【推断】的是我们的映射。

> 一句话（摘要）：Gelman–Rubin 的 R̂"has serious flaws"：链有**重尾**或各链**方差不同**时，无法正确诊断出不收敛。本文提出基于秩的诊断来修正这些问题，引入基于分位数的局部效率指标和分位数的 Monte Carlo 误差估计，建议用多链的 **rank plot** 代替 trace plot，并给出实践建议。

## 1. 瓶颈
有限时间内 MCMC 的表现"can be almost arbitrarily bad"。Fig. 2 的模拟：4 条链各 1000 次迭代，故意让一条链方差偏小或整体平移，**传统 R̂ 都检测不出来**。

## 2. 手段
- **split-R̂**：每条链切成两半，检测链内趋势。
- **rank-normalization**：把所有样本换成秩，再做正态逆变换，对重尾和无限方差稳健。
- **folded R̂**：对 |x − median| 计算，检测各链尺度（方差）的差异。最终 R̂ 取 bulk 与 tail 两个版本的最大值。
- **bulk-ESS / tail-ESS**、局部（分位数）ESS，以及分位数的 MCSE。
- 可视化：多链 rank plot；分位数/小区间效率图；"ESS 随抽样数增长"图（ESS 不随 S 线性增长甚至下降，说明多跑也解决不了）。
- ESS 的细节（§3.2）：用 FFT 算自相关，Geyer 初始单调序列截断，多链合并时用链间方差，所以比单链估计更保守；软件中把 ESS 上限设为 S·log10(S)。
- 分位数 MCSE（§4.4）：用 Beta(S_eff·α+1, S_eff·(1−α)+1) 的分位数反推，不需要估计密度。

## 3. 省在哪一项
诊断工具，不加速。

## 4. 快了多少，代价是什么
不加速。代价：需要多条链；阈值更严，可能要求更长的链。

## 5. 怎么证明结果没变（§2 实践建议，原文）
- **R̂ < 1.01** 才使用样本（比 Gelman & Rubin 1992 的 1.1 严得多）。原因是链间方差可能先降后升，传统 R̂ "can dip below 1.1 well before convergence"。
- **默认至少 4 条链**：多链更可能揭示多峰和混合不良；"most computers are able to run chains in parallel, giving multiple chains with no increase in computation time"。
- **rank-normalized ESS > 400**（4 条链时，每条 split 链平均 ESS 至少 50）才信任 R̂ 和 MCSE。
- 对分位数和区间，要单独检查尾部的收敛（tail-ESS）。
- 原文强调这些数值"should be adapted as necessary for the given application"。
- 多峰且峰之间分离时，split-R̂ 调整后的 ESS 估计会接近**找到的不同峰的数目**；只用单链计算，ESS 可能被严重高估。

- **附录 A 的灵敏度数字**（4 条 iid 正态链 + 人为问题）：
  - 所有链同样的线性趋势：不分割的 R̂ 检测不到；split-R̂ 用 1.01 阈值能检测到占总方差 **2%** 以上的趋势，用 1.1 阈值只能检测到 30% 以上。
  - 一条链均值平移：1.01 阈值能检测到 **1/3 个标准差**的平移，1.1 阈值要 1 个标准差。例：每条链 250 次、平移 0.5 时 split-R̂ = 1.05，rank plot 一眼看出。
  - 一条链方差偏小：split-R̂ 检测不到；folded-split-R̂ 用 1.01 能检测到标准差 < 3/4 的链。
- §5 例子：50 维 Cauchy（名义参数化 R̂ > 1.01、tail-ESS 最低 34；换成正态/伽马混合参数化后全部通过）；eight schools（centered 参数化 τ 的 bulk-ESS 67、tail-ESS 82；non-centered 全部通过）。
- **附录 C 失败案例**：centered eight schools 跑 4×10⁵ 次、每 200 次取一个（thinning）后，split-R̂ 和 ESS **都没发现问题**，但后验均值偏离正确值 3 个标准差以上。原因是 4 条链以同样方式失败，"converge" 到同一个错误的分布。只有 rank plot 还能看出问题。
- 附录 D：JAGS（Gibbs）1000 次 split-R̂ = 1.08、bulk-ESS 59；10,000 次后 1.01、677，全部通过。

## 6. 假设
- 各链目标相同；样本是标量。
- 方法只依赖样本本身，所以对任何多次运行的随机迭代都可以计算。但阈值（1.01、400）来自 MCMC 实践和模拟。

## 7. 能否用于 MATSim？怎么用
**✅ 直接可用。建议 RQ3 采用这个版本，而不是 1992 年原版：**
- 【推断】实施：链 = 不同种子的 MATSim 运行；样本 = 关掉创新后各轮的标量指标（平均得分、mode share、VKT、关键路段流量、gap 等）。Python 可以用 `arviz.rhat(..., method="rank")`、`arviz.ess(..., method="bulk"/"tail")`。
- 【推断】三个直接好处：
  1. split-R̂ 能自动发现"还在漂移"的链，适合检验 MATSim 是否真的稳定；
  2. folded R̂ 能发现"均值相同但逐轮波动不同"，例如某种加速方法导致更大的逐轮振荡；
  3. 多峰时 ESS 约等于找到的峰数，可以用来检测多重均衡（[11](11_Watling2003_day_to_day_dynamics.md)）。
- 【推断】**"至少 4 条链、并行不增加时间"直接对应我们的硬件现状**：只用了约 3.8/16 核，空闲核正好用来并行跑 4 个以上的种子。
- 【推断】阈值要重新校准：MATSim 关掉创新后每条链只有几十轮，且轮间自相关强，ESS > 400 和 R̂ < 1.01 可能达不到。本文自己也说阈值要按应用调整。建议报告 R̂ 和 ESS 的数值本身，并以**原版 MATSim 多种子的 R̂ 作为参照基线**（"我们的方法的 R̂ 与原版相当"）。
- 【推断】附录 A 的数字可以直接用来说明检测能力：如果只有 4 个种子，1.01 阈值能发现约 1/3 标准差的均值差异；种子间差异比这小的话，R̂ 看不出来。
- 【推断】**附录 C 的警告对我们最重要**：所有种子都用同一种加速方法时，可能"一起收敛到同一个错误的点"，R̂ 仍接近 1。所以 R̂ 必须在"原版 + 新方法"合并的运行上计算，而不能只算新方法自己的种子；同时也不要对 MATSim 的逐轮输出做 thinning。

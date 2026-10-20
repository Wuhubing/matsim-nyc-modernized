# [24] Gelman & Rubin 1992 — Inference from iterative simulation using multiple sequences

- **Venue**: Statistical Science 7(4):457–472（含讨论共到 p. 511）
- **Domain / Tier / Priority**: MCMC & sampling / 2 / High（原始 R̂，RQ3）
- **Link**: 表中 Project Euclid 链接用 curl 访问返回 403；全文取自 Gelman 主页的扫描 PDF（stat.columbia.edu/~gelman/research/published/itsim.pdf），**用 OCR 转成文字**，个别公式符号可能识别有误，关键公式已按原意核对。
- **依据**: ✅ 已读正文全文（pp. 457–472：§1–4 全部，含 §3 推导和 §4 精神分裂症反应时间例子、Table 1–4）。pp. 473–511 是其他学者的讨论和作者答复，未读。标【推断】的是我们的映射。

> 一句话（摘要）：迭代模拟（Gibbs、Metropolis 等）"Used naively … can give misleading answers"。推荐用**多条独立序列**，起点从**过度分散**的分布中抽取。每一步对每个一维估计量，同时给出分布估计和"如果无限继续模拟，分布估计还能变尖多少"的估计。方法适用于任何迭代模拟的输出，甚至不要求是 Markov 过程。

## 1. 瓶颈（原文 §1.2）
"it is not generally possible to monitor convergence of an iterative simulation from a single sequence … the random walk can remain for many iterations in a region heavily influenced by the starting distribution"。类比迭代最大化："one cannot use a single run to find all maxima"。

## 2. 手段（§2 七步法）
1. 独立模拟 m ≥ 2 条序列，每条长 2n，起点过度分散；**丢弃前 n 次**，只用后 n 次。
2. 对每个标量：B/n = m 个序列均值之间的方差；W = m 个序列内方差的平均。
3. 均值估计 = 全部 mn 个值的样本均值。
4. 方差估计 σ̂² = ((n−1)/n)·W + (1/n)·B：起点过度分散时偏大，平稳时无偏；而有限 n 时 W 偏小。
5. 用 Student t 近似目标分布，尺度 V̂ = σ̂² + B/(mn)。
6. **潜在尺度缩减因子** √R̂ = √((V̂/W)·df/(df−2))，n → ∞ 时降到 1。
7. 所有关注的标量的 R̂ 都接近 1 后，用各序列后半段的模拟值来概括目标分布。

- **§2.1 起点分布的构造**：先用优化（EM 等）多次找所有众数 → 在每个众数处用二阶导数做正态混合近似 → 除以 χ² 变量变成 t 混合（自由度 4 通常就够分散）→ 用 SIR 重要性重采样（约 N=1,000 抽 m=10）去掉低密度点。
- §2.3 与以前方法的区别：Fosdick (1959) 只用 B 不比较 W；Gelfand & Smith (1990) 只做定性比较。本文是**完全定量**的，不靠看图。
- §1.4：多条序列"ideally suited to parallel computing"，并行跑多条序列的时间和跑一条差不多。

## 3. 省在哪一项
不是加速，而是**诊断**：判断何时可以停止，避免多跑或少跑。

## 4. 快了多少，代价是什么
不提速；代价是需要多条序列（多次独立运行）。

- **§4 例子**（17 名受试者 × 30 次反应时间，混合随机效应模型，Gibbs 采样，m=10 条序列各 200 轮）：
  - Table 1（参数 τ）：只用前 20 轮时估计的潜在缩减因子 1.7，实际（与 200 轮比）缩减 2.5；40 轮时估计 1.1、实际 1.0。**早期估计"reasonably accurate"**。
  - Table 2（101–200 轮）：24 个标量的 √R̂ 都在 1.00–1.03。
  - Table 3（只用 11–20 轮）：λ 的 √R̂ = 1.88，−2 log 密度 1.79，说明还没收敛。
  - **§4.8 慢收敛例子（Table 4）**：起点不经过找众数和重要性重采样，直接从粗糙分布抽。λ 的 √R̂ = 5.15、β = 2.43。原因是 10 条中有**一条序列一直停在一个次要众数附近**。把这条去掉后，剩下 9 条的结果和 Table 2 基本相同。

## 5. 怎么证明结果没变
本身就是"证明已收敛"的工具。解释（§3）：R̂ 大时，要么继续模拟会显著减小 σ̂，要么会显著增大 W（序列还没有"complete tour of the target distribution"）；R̂ 接近 1 时，各序列都接近目标分布。事后还应检查起点确实过度分散。

## 6. 假设
- 各序列目标相同；起点过度分散；标量在变换后近似正态（作者建议先取对数或 logit）。
- §3.2 的推导用了"强平稳"（起点分布 = 目标分布）这个不现实的理想假设，作者承认，但认为由此得到的方法在实际中好用。
- §2.4 局限：**多峰目标**下，若不同序列停在各自起点附近的峰，"the estimated potential scale reduction will not decline to 1"。方法能**揭示**这个问题，但不能解决它。

## 7. 能否用于 MATSim？怎么用
**✅ 直接可用（RQ2/RQ3 的核心工具）：**
- 【推断】做法：同一场景、同一方法，用 m 个种子或不同初始方案各跑一次；对每个标量（平均执行得分、mode share、总 VKT、若干关键路段流量、平均 gap）取关掉创新后的窗口，计算 R̂。
- 【推断】两种用法：
  1. **何时收敛**：R̂ 降到阈值以下所需的轮数，可以作为与方法无关的收敛判据，替代 Zhuge 2021 那种内生的判据（参见 [06 Sheffi](06_Sheffi1985_Urban_Transportation_Networks.md) 对"变化量判据"的警告）。
  2. **是否到达同一均衡**：把"我们的方法"和"原版"的运行合在一起计算 R̂。若合并后 R̂ ≈ 1，两者在统计上无法区分；若 R̂ 不下降，按 §2.4 的解释，就是不同运行落在不同的峰，正对应多重均衡（[05](05_BenDor2021_population_downscaling.md)、[11](11_Watling2003_day_to_day_dynamics.md)）。
- 改造：MATSim 探索阶段是非平稳的，只能在关掉创新之后计算；"过度分散的起点"可以用不同的初始方案或不同的种子近似。建议使用改进版 R̂（[25](25_Vehtari2021_improved_Rhat.md)）。
- 【推断】§4.8 的例子对我们很有用：10 次运行中只要有一次落到另一个均衡，R̂ 就会很大。这正是我们想检测的现象。论文的处理是"看图找出那一条，确认那个众数没有意义再丢掉"；在 MATSim 中不能随便丢，因为另一个均衡可能是真实存在的（多重均衡），需要报告它出现的比例。
- 【推断】R̂ 只告诉我们"不同运行是否一致"，不能单独说明一致的那个点是不是原版 MATSim 的点；所以必须把原版运行和新方法运行放在一起算。

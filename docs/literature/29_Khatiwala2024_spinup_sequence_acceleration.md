# [29] Khatiwala 2024 — Efficient spin-up of Earth System Models using sequence acceleration

- **Venue**: Science Advances 10(18):eadn2839（2024-05-01），DOI 10.1126/sciadv.adn2839，CC BY 4.0
- **Domain / Tier / Priority**: Climate model spin-up / 2 / **Read first**
- **Link**: 表中 Oxford Martin 链接只是介绍页；全文取自 PMC11062586（Europe PMC 全文 XML）
- **依据**: ✅ 已读全文：摘要、引言、Results 三部分、Discussion、Methods（AA 公式与参数）。标【推断】的是我们的映射。

> 一句话：spin-up 就是不动点迭代 x_{k+1} = g(x_k)（g = 跑一个强迫周期的模型）。在模型外面包一层 **Anderson acceleration（AA）**，完全黑箱：用最近 m 个迭代的线性组合使残差最小。两个主流海洋生物地球化学模型在季节性强迫下**快约 12 倍**；IPCC 协议下的**年际变化强迫**下快 **5 倍**；陆地模型 JULES 快约 7 倍。

## 1. 瓶颈（原文）
- spin-up 要"several thousand years of model integration"才能把漂移降到可接受，主要原因是深海调整缓慢；即使在最强的超算上，一次 spin-up 也要数月。**同类问题：慢在到达稳态。**
- 后果：只能做一次 spin-up，无法传播参数不确定性，也难以系统标定。

## 2. 手段（Methods）
- 不动点 x_{k+1} = g(x_k)；残差 f(x) = g(x) − x。
- AA：x_{k+1} = Σ_j α_j^{(k)}·g(x_{k−m_k+j})，α 通过最小化 ‖Σα_j f(x_{k−m_k+j})‖² 求得，约束 Σα_j = 1（可保持示踪物守恒）。
- 黑箱："to evaluate g, it only requires the facility to run the model with a given initial condition and return the result"；开销可以忽略，主要是存储迭代和解一个小最小二乘问题。
- 本文设置：无阻尼，m_max = 50。
- **针对困难情形的两个改造（对我们最有价值）**：
  1. **年际变化强迫（噪声大）**：直接用 AA"struggled to make much progress in the presence of the large variability"。改为先在"重复 1 年"的去噪版本上做 200 次 AA，再以此为初值切回常规时间积分（"AA(200) + DI"）。
  2. **陆地模型（刚性、强非线性）**：直接对全模型做 AA 会停滞。改为只对慢变量（生物地球化学变量）做 AA，并**与短段自由运行交替**（每 50 次 AA 迭代后自由运行 10 年），让快变量先调整好。
- Discussion 中提出的方向：把问题分成"慢"和"快"两部分，外推系数只用慢分量计算，但同时作用于快慢两部分；以及动态调整参数的非平稳 AA。

## 3. 省在哪一项
**迭代次数**（模拟年数）。

## 4. 快了多少，代价是什么（原文数字）
| 情形 | 直接积分（DI） | AA | 倍数 |
|---|---|---|---|
| BLING，季节性强迫，达到 OMIP 标准（净 CO₂ 通量 < 0.01 PgC/yr） | 3710 年 | 310 次迭代 | ~12× |
| PISCES，同上 | 3975 年 | 340 次迭代 | ~12× |
| BLING，年际强迫，通量达标 | ~4050 年 | 200 AA + ~420 年 DI | 6.5× |
| 同上，示踪物场基本平衡 | — | 200 AA + 600 年 DI | **5×** |
| JULES 陆地模型（氮储量） | 10,000 年 | ~1500 次迭代 | ~7× |

- 早期工作（Khatiwala 2023，简单地球化学模型）报告 10–25 倍。
- 代价：存储最多 m_max 个状态向量；对噪声和刚性问题需要上述改造。

## 5. 怎么证明结果没变（可借给 RQ2）
- 以 **5000 年直接积分**的解为参照（陆地模型为 10,000 年）。
- **逐网格点散点图**（AA 解 vs DI 参照，看是否落在 1:1 线上），并与 DI 在 1000/2000/3000 年时的中间解对比。BLING 320 次 AA 迭代后，除碱度外的示踪物都比 3000 年 DI 更接近参照；500 次迭代后与 5000 年 DI"more or less the same"。
- 用物理意义明确的平衡指标（OMIP 的净 CO₂ 通量标准），而不只看残差范数。原文说残差范数"difficult to assess … how close to equilibrium a model is"。
- 有噪声时用 **50 年滑动平均**（及其最大最小包络）判断是否平衡。

## 6. 假设
- 确定性不动点映射（一个周期的模型积分）；状态是连续向量，可以线性组合。
- 不需要梯度。
- 噪声：作者说 AA 已有用于带噪声问题的先例，但年际变化带来的波动"quite large, and even defining an equilibrium can be challenging"，此时直接用 AA 效果不好。

## 7. 能否用于 MATSim？怎么用
**🟡 部分可用，需要关键改造。本文的两个改造正好给出了方向：**
- **障碍 1：状态离散**。【推断】MATSim 的状态是每个 agent 的方案，不能线性组合。改造：只对**连续的中间量**做 AA，即时变的路段出行时间场（router 和得分用的输入）。agent 用外推的出行时间 T̂ 去 replan。这本质上是"外推交通状态"，与 [20 optimistic](20_Daskalakis2018_optimistic_GAN.md) 同一家族。
- **障碍 2：随机噪声**。本文已证明，噪声大时直接 AA 停滞。【推断】借鉴"AA(200) + DI"的思路：先在一个**去噪的近似问题**上做加速（例如用多种子平均或平滑后的出行时间、或者 PSim 式的确定性评估），得到一个好的"热启动"状态，再切回正常的 MATSim 迭代。
- **障碍 3：快慢变量**。【推断】借鉴"只对慢变量做 AA，与自由运行交替"：MATSim 中的慢变量（如 mode 和活动时间的分布）与快变量（路径）可以分开处理；"与短段自由运行交替"对应"AA 外推若干步后，插入若干轮正常 MATSim 迭代"。
- **障碍 4：多重均衡**。外推可能把系统推到另一个吸引子，必须用多种子比较最终分布（[11](11_Watling2003_day_to_day_dynamics.md)、[18](18_Hofbauer2002_stochastic_fictitious_play.md)）。
- **验证方式可以直接借**：原版 MATSim 跑足够长的多种子运行作参照；逐 link（或逐 OD）散点图对比；用有物理意义的平衡指标（如 gap），而不是"得分变化很小"。
- 评价：概念上和我们的问题最像（黑箱、到达稳态），"去噪热启动"和"快慢分离"是本文给出的、可迁移到随机系统的具体做法。值得做小规模实验。

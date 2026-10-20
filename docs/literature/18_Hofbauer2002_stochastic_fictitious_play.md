# [18] Hofbauer & Sandholm 2002 — On the global convergence of stochastic fictitious play

- **Venue**: Econometrica 70(6):2265–2294
- **Domain / Tier / Priority**: Learning in games / 1 / High（logit 选择的收敛，对应 SUE）
- **Link**: https://homepage.univie.ac.at/Josef.Hofbauer/sfp.htm → 作者提供的最终版预印本 sfp.pdf（2001-12-17）
- **依据**: ✅ 已读全文（作者终稿预印本：§1–6、附录全部证明、参考文献；第二轮从头到尾重读）。标【推断】的是我们的映射。
- ⚠️ **旧版笔记的错误**："若交通博弈近似势博弈，理论上收敛到**唯一**的 logit 均衡"是错的。原文结论是：势博弈中收敛到扰动最优回应动态的**静止点集合**；若静止点都是双曲的，则收敛到某一个**线性稳定**的静止点，即势函数的局部极大点。**静止点可能有多个**。

> 一句话（摘要）：对四类博弈（有内部 ESS 的博弈、零和、**势博弈**、超模博弈），证明了 stochastic fictitious play 的全局收敛性。方法是随机逼近：随机过程的极限行为由其期望运动定义的微分方程刻画。为此证明了一个离散选择定理：**任何加性随机效用模型的选择概率都可以由一个确定性的扰动模型导出**。

## 1. 瓶颈
理论问题：普通 fictitious play 的行为对信念非常敏感，无法收敛到混合均衡。stochastic FP（加入收益扰动）之前只在 2×2 博弈和部分 p 人二策略博弈中证明过收敛，"nothing is known about convergence in games with more than two strategies per player"。

## 2. 手段
- **Standard SFP（§3.2）**：p 人重复博弈，状态 Z_t 是各玩家过去行为的**时间平均**（Z_t = (1/t)Σζ_u，即步长 1/t）；每期在受随机冲击的收益下，对信念做最优回应（扰动最优回应 B̃）。
- 随机逼近：SFP 的极限点落在扰动最优回应动态（P）的 chain recurrent set 中。
- 离散选择定理 → 把随机扰动转写为确定性扰动 V → 构造 Lyapunov 函数。
- 其他结论：
  - Proposition 2.3：形如 w(π_i)/Σw(π_j) 的选择函数中，只有 **logit** 能由随机或确定性收益扰动导出；
  - Proposition 3.1：扰动趋于零时，扰动动态的静止点收敛到原博弈的 Nash 均衡；
  - §4 开头：把收益整体放大 κ 倍，等价于把扰动缩小为 1/κ，所以**真正起作用的是"噪声相对收益的尺度"**；这种变换会改变静止点。
- 势博弈（§4.2）：本文的定义是所有玩家收益相同；脚注 7 推广到 weighted potential games。原文说势博弈"include pure coordination games and congestion games"。Lyapunov 函数是 Π(x) = Σ_s u¹(s)Πx^α − Σ_α V^α(x^α)，即势函数减去扰动项。

## 3. 省在哪一项
理论文章，不涉及加速。

## 4. 快了多少，代价是什么
没有给收敛速度。原文明确说结果"should not be interpreted as suggesting that stochastic fictitious play converges in all games"，例如 Jordan 的三人 matching pennies 就不收敛；超模博弈中也存在收敛到周期轨道的例子（Example 5.6）。

## 5. 怎么证明结果没变
数学证明（Theorem 6.1）：
- (i) 有内部 ESS 的二人对称博弈、(ii) 二人零和：几乎必然收敛到**唯一**静止点。
- **(iii) p 人势博弈**：扰动分布足够光滑时，极限集几乎必然是静止点集合 RP(P) 的连通子集；若所有静止点都是双曲的，几乎必然收敛到某个**线性稳定**静止点（势函数的局部极大点）。
- (iv) 超模博弈：收敛到静止点或某个特定集合；静止点唯一时收敛到它。

## 6. 假设
- 有限个玩家、有限策略集，**策略集固定**。
- 信念 = 对手历史行为的时间平均（步长 1/t）。
- 收益扰动来自加性随机效用模型（如 logit），且分布足够光滑。
- 不需要梯度。

## 7. 能否用于 MATSim？怎么用
**🟡 用来支撑理论论证，不是加速手段：**
- 【推断】映射：MATSim 关掉创新后，每个 agent 在固定方案集上做 logit 选择（ChangeExpBeta），方案得分是历史收益的平滑（MSA 平滑时步长就是 1/t），结构上接近 SFP（MATSim 书 §47.3.2.2 也说得分平均"somewhat similar to fictitious play"）。
- 【推断】若把交通看作拥堵博弈，因而是势博弈（本文明确把 congestion games 列为势博弈；但 MATSim 有动态排队和溢出，严格来说不一定成立），Theorem 6.1(iii) 给出：
  1. **收敛有保证**：这解释了为什么关掉创新后几轮内就稳定；
  2. **但收敛到的是"某个"线性稳定点（势函数的局部极大），可能不唯一**。这与 [04](04_Nagel2009_agent_based_traffic_assignment.md)（物理排队导致多重均衡）、[05](05_BenDor2021_population_downscaling.md)（MATSim 中 3/100 次运行落在不同 UE）、[11](11_Watling2003_day_to_day_dynamics.md)（双峰平稳分布）一致。
- 【推断】对我们方法的含义：
  - 最终到哪个均衡，取决于**方案集**（探索阶段生成了什么）和**初始点落在哪个吸引域**。加速探索的方法既改变方案集，也改变轨迹，所以有可能落到另一个局部极大点。
  - 因此"更快"必须同时检查"不更差"：比较最终的平均得分（在势博弈中与势函数相关）和分布。
- 【推断】§4 的尺度不变性对 MATSim 有直接含义：ChangeExpBeta 的 β（brainExpBeta）与得分单位（如效用的 marginal utility 设置）共同决定"噪声相对收益"的大小。加速方法若改变得分的尺度或计算方式（例如用代理模型打分），就等于改变了 logit 的噪声水平，从而改变静止点。
- 注意与 MATSim 书 §47.3.2 的区别：MATSim 书说在**方案集固定、得分取期望值**时，选择过程有唯一的稳态概率。那是给定得分下的选择分布；一旦得分随他人选择变化，就是本文的博弈问题，可能有多个静止点。

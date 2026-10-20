# [20] Daskalakis, Ilyas, Syrgkanis, Zeng 2018 — Training GANs with optimism

- **Venue**: ICLR 2018（arXiv 1711.00141v2）
- **Domain / Tier / Priority**: Learning in games / 1 / Medium（回应 Yining 的 GAN 类比）
- **Link**: https://arxiv.org/abs/1711.00141
- **依据**: ✅ 已读全文（arXiv v2，30 页：§1–6、附录 A–H，含 Theorem 1/3 的完整证明和 DNA、CIFAR10 实验设置；第二轮从头到尾重读）。标【推断】的是我们的映射。

> 一句话（摘要）：GAN 训练会出现**极限环**。WGAN 训练本质上是用同时进行的无悔动态求解零和博弈。作者提出用 **Optimistic Mirror Descent（OMD）**训练，并证明在**双线性零和博弈**中 OMD 的**末轮迭代**收敛到均衡，而 GD"bound to cycle"。在 DNA 序列生成上，OMD 得到更小的 KL 散度；提出的 **Optimistic Adam** 在 CIFAR10 上的 inception score 高于 Adam。

## 1. 瓶颈（原文 §1）
- 零和博弈中，无悔动态"can very often lead to limit oscillatory behavior"；即使在凸凹零和博弈中，也只有**平均**权重是均衡，末轮迭代不是。
- 对神经网络做权重平均"is a prohibitive approach"（非凸凹）。所以需要让末轮迭代就接近均衡的算法。

## 2. 手段
- OMD：利用"the opponent … is also training via a similar algorithm"的可预测性，在更新中加入"预测"项（在 GD 情形下即用 2·本轮梯度 − 上一轮梯度）。
- Proposition 1：对 min_x max_y xᵀy，GD 从任意非零初值都**发散**。
- Theorem 1：在双线性博弈 xᵀAy 中，满足 ‖A‖ ≤ 1 且步长 η < 1/(3γ²) 时，OMD 的末轮迭代到均衡集合的距离为 O(√η·γ·√Δ₀)。
- Optimistic Adam：Adam 的乐观版本。

## 3. 省在哪一项
**迭代次数 / 稳定性**：消除振荡，使末轮迭代收敛。

## 4. 快了多少，代价是什么
- 实验设置：DNA 任务每种优化器、每个学习率独立训练 **50 个模型**，比较 KL 散度分布；CIFAR10 的最终比较用 35 次运行、30 个 epoch（附录 H）。
- OMD 的"预测"可以是上一轮梯度、过去梯度的平均或折扣平均（三种都试了）。
- **训练比例的发现**：判别器与生成器 1:1 交替训练时乐观方法效果最好，1:5（多训几次判别器）反而变差。作者解释：乐观依赖"对手下一步可预测"，对手一次走太多步就不可预测了。
- 附录 B：让判别器多训练（不对称训练）是缩小极限环最有效的 GD 改进，但只能缩小、不能消除循环。
- 定性结果：toy 例子中 GD（包括梯度惩罚、动量、自适应步长等变体）出现极限环，OMD 逐点收敛；DNA 任务 KL 更小；CIFAR10 inception score 高于 Adam（原文 Fig. 4，没有用一个"倍数"概括）。
- 代价：要存一步历史梯度；理论只覆盖双线性情形，且步长要足够小。

## 5. 怎么证明结果没变
理论（末轮收敛界）+ 实验（KL 散度、inception score、轨迹图）。

## 6. 假设
- **可微、要用梯度**；两人零和；理论结果限于双线性博弈。

## 7. 能否用于 MATSim？怎么用
**🟡 思路可借，机制要改造（MATSim 没有梯度）：**
- **对 GAN 类比的回答**：【推断】GAN 是两人零和博弈，梯度动态会循环（本文和 [19](19_Mertikopoulos2018_cycles_regularized_learning.md)）；MATSim 是大量 agent 的拥堵博弈，接近势博弈（[18](18_Hofbauer2002_stochastic_fictitious_play.md)），学习动态通常收敛（关掉创新后几轮就稳定也印证这一点）。所以 GAN 的循环病理**不是** MATSim 慢的主要原因。MATSim 慢在探索（生成好方案），不在振荡。
- **可借的思路——"乐观/外推"**：【推断】OMD 的本质是"预测对手下一步会怎样，并据此更新"。在 MATSim 中，agent 目前用上一轮的出行时间做 replan，可以改用外推的出行时间 T̂_{t+1} = 2T_t − T_{t−1}（或平滑版本）做路由和时间变异，让创新瞄准"下一轮"的交通状态，减少"刚改完就过时"的无效创新。这与 [29 Anderson acceleration](29_Khatiwala2024_spinup_sequence_acceleration.md) 同属"外推"家族。
- 【推断】§5 的"1:1 比例"发现给外推加了一个条件：只有当系统每轮变化小且平滑时，"预测下一轮"才有用。MATSim 若每轮 replan 比例大，出行时间跳动大，外推就会失效；这意味着外推类方法应与较小的创新比例配合使用。
- 风险：MATSim 的出行时间有噪声，外推会放大噪声；本文的理论只适用于双线性零和博弈，不能保证在 MATSim 中有效，需要实验验证。

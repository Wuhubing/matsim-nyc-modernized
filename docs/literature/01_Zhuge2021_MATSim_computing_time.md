# [01] Zhuge et al. 2021 — An improvement in MATSim computing time for large-scale travel behaviour microsimulation

- **Authors**: Zhuge, Bithell, Shao, Li, Gao
- **Venue**: Transportation 48:193–214 (online 2019), DOI 10.1007/s11116-019-10048-0, open access
- **Domain / Tier / Priority**: MATSim & agent-based traffic sim / 1 / **Read first**
- **Link**: https://www.repository.cam.ac.uk/handle/1810/317402 (full-text PDF: https://ira.lib.polyu.edu.hk/bitstream/10397/88272/3/s11116-019-10048-0.pdf)
- **依据**: ✅ 已读全文（2026-10-15）

> 一句话：先强制每个 agent 攒 20 个方案，然后只让"当前方案比记忆中最好方案差"的 agent 去 replan；再把 mobsim 时间步从 1 s 改成按时段 15/30 s。小场景（4 万 car agent）上迭代数 154→69、总时间约减半，MAPE 略变差。

## 1. 瓶颈（Bottleneck）
共同演化（co-evolutionary）循环要跑很多轮才收敛（作者原话：大部分时间花在优化日计划的迭代循环上）；另外每轮 mobsim（1 s 时间步）也慢。**两类瓶颈都有，"到达稳态的轮数"是主线，和我们的问题结构很像。**

## 2. 手段（Method）
1. **新框架 + 选择性 replanning**（Experiment-FR）：
   - Phase 1：每个 agent 先 replan N_Plans 次（本文 N_Plans=20），把记忆塞满候选方案，目的是减少后面陷入局部最优。
   - Phase 2：只有"不满意"的 agent replan。按当前执行方案得分与记忆中最好方案得分的差距分两级：差距 ≥ θ1（0.1%）只做 ReRoute；差距 ≥ θ2（10%）再加 TimeAllocationMutator（±30 min）。满意的 agent 不再 replan。
2. **变时间步 mobsim**（Experiment-E）：按各时段在路网上的 agent 数分配时间步，越拥挤步长越大（7–19 点 30 s，其余 15 s）。
3. 两者合并（Experiment-C）。

## 3. 省在哪一项（Saves on）
- 方法 1：**迭代次数**（154 → 69 轮）
- 方法 2：**每步计算**（7.71 s/iter → 2.83 s/iter）

## 4. 快了多少，代价是什么
| 实验 | 轮数 | 总时间 | 末轮 MAPE | 末轮 SD |
|---|---|---|---|---|
| O（原版，1 s 步长） | 154 | 1187 s | 42.13% | 29.16% |
| FR（选择性 replan） | 69 | 549 s | 42.45% | 31.33% |
| E（变步长） | 230 | 652 s | 30.49% | 20.48% |
| C（合并） | 99 | 305 s | 34.50% | 25.15% |

- 方法 1 约 **2.2×**（总时间减少约 54%），MAPE 基本不变（正文另一处说 39.7% vs 42.5%、164 轮、1263 s，与表格数字不一致，引用时以 Table 2 为准并注明）。
- 方法 2 约 1.8×；合并约 **3.9×**。
- **代价**：
  - 内存：每个 agent 存 20 个方案，作者自己承认大场景（北京、上海）可能吃不消。
  - 3 个新参数（N_Plans, θ1, θ2）是"试了几次"定的，没有敏感性分析。
  - Phase 1 的 20 轮全员 replan 本身就是一大笔探索开销，作者没有单独计时。
  - 作者承认 N_Plans 小时更容易陷入局部最优。

## 5. 怎么证明结果没变（How validated）
- 只用 **12 个计数点、早高峰 2 小时**的 MAPE 和 SD，和原版对比；两版都用 Cadyts 标定。
- **单次运行、单个随机种子**，没有多种子比较。
- 收敛判据是"已执行方案的平均得分相对变化 < 0.001 连续 4 轮"。**这个判据和方法本身有内生关系：replan 的人少了，平均得分自然变化小，看起来"收敛得更快"，不一定真的更接近均衡。**
- 没比较得分分布、出发时间分布、路段流量全分布或均衡 gap。

## 6. 对系统的假设（Assumptions）
- 隐含假设：已满意的 agent 不需要探索，即"得分接近记忆中最好方案 = 接近最优"。但记忆里的方案只是有限样本，不代表真正的最优回应。
- 默认 Phase 1 的 20 个方案足以覆盖好的选项（防止局部最优全靠这个）。
- 只有 car、只有 ReRoute + 时间变异，没有 mode choice，也没有 location choice。
- 没有讨论随机性或多重均衡；把单次运行的结果当成"那个"均衡。

## 7. 能否用于 MATSim？怎么用
**✅ 本来就是 MATSim，是最接近我们的 baseline，必须正面对比。**
- 可复现：用一个自定义 `PlanStrategy` / `StrategyChooser`，按"当前得分与最好得分的差"决定谁 replan。
- **我们和它的区别（novelty 的核心）**：
  1. **目标不同**：Zhuge 筛的是"谁去 replan"（按 agent 是否满意）；我们关心的是"试探方案中 85% 无效"，即**生成哪种创新、生成后怎么筛**（按创新的预期价值）。两者正交，可以叠加。
  2. **验证不同**：它是单种子 + 12 个计数点 MAPE + 内生的收敛判据；我们可以做多种子、比较均衡状态的分布（得分、mode share、流量），并用和方法无关的判据（如 R̂、gap）。这是我们稳赢的点。
  3. **规模**：4 万 agent、1650 条路段、只有 car；我们是多模式、更大场景。
  4. 它没有 Phase 1 的成本分析，也没有考察"停在更差均衡"的风险；我们可以直接对比均衡得分分布。
- 另一个必须一起讨论的前身：Sbayti et al. 2007（[08](08_Sbayti2007_efficient_MSA_SBDTA.md)）在 DTA 里已经按经历的出行时间排序选人做 swap。"只让差的人换"这个思路在 DTA 里 2007 年就有了，不能声称是我们首创。

## 读后备注
- 变时间步的结果是非单调的（Fig. 5c），说明轮数对 mobsim 的设置很敏感，本身就是个值得注意的现象：**改 mobsim 也会改收敛路径**。
- 原文结论里写的"selective methods for reducing the number of agents active during ... replanning"正好是我们要往前推进的方向。

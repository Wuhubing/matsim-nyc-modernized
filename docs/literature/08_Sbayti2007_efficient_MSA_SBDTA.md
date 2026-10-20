# [08] Sbayti, Lu, Mahmassani 2007 — Efficient implementation of method of successive averages in simulation-based DTA models for large-scale network applications

- **Venue**: Transportation Research Record 2029:22–30，DOI 10.3141/2029-03
- **Domain / Tier / Priority**: DTA & traffic equilibrium / 1 / High（最接近的 DTA 类比）
- **Link**: https://doi.org/10.3141/2029-03（SAGE，付费）。全文 PDF 由用户通过图书馆下载，存于 [pdf/08.pdf](pdf/08.pdf)。
- **依据**: ✅ 已读全文（9 页：引言、问题设定、MSA、统一求解框架、三种实现、Fort Worth 实验与 Table 1、Knoxville 实验、结论、参考文献）。标【推断】的是我们的映射。
  - **更正**：旧版笔记依据引用文献，把方法描述为"按 gap 挑选换路者"。原文的排序标准其实是**经历的出行时间**（trip time）；但排序是在同一个 (o, d, τ) 组内进行的，组内最短路时间相同，所以按出行时间排序**等价于**按 gap 排序。旧版笔记删掉的"gap 降到 5% 以下"，原文确实这样写（结论和 Fort Worth 结果），现已恢复并注明出处。

> 一句话：MSA 在仿真类 DTA 中最常用，但有两个随拥堵和网络规模恶化的缺点：(1) 纯路径式实现要显式存储路径集和路径分配，内存爆炸；(2) 每轮把**所有**劣路径上的车按同一比例 1/k 换到当前最短路，"slightly sub-optimal paths are penalized to the same extent as the most inferior path"。作者提出**基于车辆的实现**（从车辆轨迹中恢复路径集，不另存）和**车辆排序法**（每个 (o, d, τ) 组内按经历的出行时间排序，只让最差的 1/k 换路，总步长不变），在两个真实网络上把 UE 和 SO 的 gap 都降到 5% 以下。

## 1. 瓶颈（原文）
- MSA 在真实网络上的收敛性"inconclusive"：(a) 仿真模型数学上不良性，解的性质没有保证；(b) 预设步长不利用局部信息，表现迟缓。大多数文献只在小的假想网络上测试。
- 纯路径式 MSA 内存随网络规模和迭代次数快速增长。
- 1/k 的统一换路率不区分路径有多差；原文说这一点"most detrimental to efficient convergence at high congestion levels"。
- 路径交换类算法（route-swap）可以按差距成比例换路，但又要确定最优交换率，失去了 MSA"预设步长"的优点。

## 2. 手段（原文"Implementation Considerations"）
- 统一框架（沿用 Peeta & Mahmassani）：DYNASMART-P 中观仿真加载 → 时变最短路（SO 用边际成本）→ 全有全无分配 → MSA 更新 → 收敛检查。
- **收敛判据**：比较相邻两轮每个 (o, d, τ, p) 的分配量，差值 > ε（取 1 辆车）的情形记为一次违例；违例数 ≤ φ（取 50）就停。作者明确说这只表示"stable solution"，**不说明是否达到 UE/SO**；解的质量另用 Janson 的相对 duality gap 衡量。gap **不用作停止判据**，因为低需求时前几轮就能得到小 gap，算法会过早停止。
- 三种实现：
  1. **flow-based**：多维数组存路径和分配，每条路径上 1/k 的车换到辅助路径。理论上最正确，但内存随网络规模和迭代次数暴涨。
  2. **vehicle-based + 随机选择**：利用中观仿真逐车追踪的特点，从上一轮的车辆轨迹恢复路径集，内存基本不随迭代增长；每辆不在辅助路径上的车以概率 1/k 换路。
  3. **vehicle-based + 排序（criterion-based / sorting）**：每个 (o, d, τ) 组内按预定标准排序（本文用**经历的出行时间**；也可以用延误，疏散问题可以用离开时间），**最差的 1/k**（不在辅助路径上的）车换到辅助路径。总步长与 MSA 相同，只是不同劣路径的换出比例不再相同。作者把它与有界理性联系起来：只有节省足够大的人才换路。

## 3. 省在哪一项
- **内存**（vehicle-based：Fort Worth 70,000 辆的场景中 flow-based > 700 MB，vehicle-based < 400 MB，原文说"42% reduction"；Knoxville 中 flow-based 在 3 GB 内存下跑不动，vehicle-based 约 1.6 GB）。
- **解的质量**（同样停止判据下 gap 小得多）。
- **不省迭代次数**：排序法"appears to require the most iterations to attain a stable solution"，每轮时间与其他两种相当。

## 4. 快了多少，代价是什么（原文 Table 1，Fort Worth：191 节点、573 条边、13 个交通小区）

| 需求（辆） | 方法 | UE gap | UE 迭代 | SO 边际 gap | SO 迭代 |
|---|---|---|---|---|---|
| 23,000 | flow / random / sorting | 4.08% / 7.63% / **2.23%** | 15 / 11 / 17 | 4.12% / 4.34% / **1.40%** | 14 / 12 / 15 |
| 45,000 | flow / random / sorting | 9.76% / 11.88% / **2.77%** | 28 / 22 / 31 | 14.11% / 8.08% / **2.28%** | 31 / 26 / 24 |
| 70,000 | flow / random / sorting | 13.26% / 19.16% / **3.90%** | 50 / 30 / 51 | 24.06% / 19.68% / **4.44%** | 46 / 41 / 41 |

- 拥堵越严重，flow-based 和随机选择越差，排序法的优势越大；作者说这"raises some doubts over the applicability of the MSA for congested real-life networks"。
- 注意：正文说三个需求水平是 35,000 / 50,000 / 70,000 辆，Table 1 写的是 23,000 / 45,000 / 70,000，**原文前后不一致**。
- **Knoxville**（1,347 节点、3,004 条边、356 个小区，2 小时 200,000 辆车）：flow-based 跑不动；两种 vehicle-based 方法都用了**约 8 小时**收敛（约 32 轮）。SO 边际 gap：随机 4.78% vs 排序 **0.56%**；UE gap：随机 7.78% vs 排序 **1.72%**。
- 代价：每次停止时的迭代数略多；排序标准要选对。

## 5. 怎么证明结果没变
- 两个指标分开：违例数判断"稳定"，Janson duality gap 判断"离 UE/SO 多远"。作者明确区分"稳定"和"质量"：所有方法都"exhibited nice convergence properties"，但高拥堵时解的质量差别很大。
- 只用一个仿真器、每个场景跑一次，**没有多种子**。

## 6. 假设
- trip-based，时变 OD 已知；只有路径选择，出发后不改路；完全信息；SO 版本假设所有车都服从中央控制。
- 必须是逐车追踪的仿真器（中观或微观），才能从轨迹恢复路径集。
- 排序在 (o, d, τ) 组内进行，组内有共同的最短路时间作为参照。

## 7. 能否用于 MATSim？怎么用
**✅ 思路可直接用，而且是 novelty 判断的关键文献：**
- "按差距大小决定谁去换"在 DTA 中 2007 年就已提出（本文的排序法），后来发展为 Lu et al. 2009 的 gap 函数方法（[09](09_Lu2009_gap_function_DUE.md)），POLARIS 也建立在 gap-based 方法上（[51](51_Verbas2024_POLARIS_gap_based.md)）。【推断】所以"按差距选谁 replan"不能作为我们的核心新意，我们要说清楚与它们的区别。
- 【推断】区别在哪：本文在 (o, d, τ) 组内比较出行时间，因为组内有共同的参照（最短路时间）。MATSim 的 agent 是全天计划，**没有天然的"同组"**，不同人的得分不能直接比较。所以要先定义每个人自己的 gap（例如"本轮执行得分 vs 用本轮出行时间算出的最优回应得分"），Nagel & Flötteröd 2009（[04](04_Nagel2009_agent_based_traffic_assignment.md)）说过全日计划还没有可操作的 gap 函数，这里仍有空间。
- 【推断】本文的数字支持我们的动机：**随机挑人（MATSim 现在的做法）在拥堵时明显更差**（70,000 辆时 UE gap 19.16% vs 3.90%）。但也提醒：排序法**不减少迭代次数**，收益在解的质量上。如果我们的目标是"更少轮数到达同样质量"，要用"达到某个 gap 阈值所需轮数"来比较，而不是用本文这种稳定性停止判据。
- 【推断】本文"稳定 ≠ 达到均衡"的区分，正是我们在 RQ2 中要坚持的：MATSim 得分曲线变平只说明稳定，不说明 gap 小。
- 【推断】vehicle-based 从轨迹恢复路径集的想法与 MATSim 的方案记忆类似；MATSim 每人存最多 5 个方案，内存问题不大，这一点对我们不是瓶颈。

# [46] Fourie, Illenberger, Nagel 2013 — Increased convergence rates in multiagent transport simulations with pseudosimulation（PSim）

- **Venue**: Transportation Research Record 2343(1):68–76，DOI 10.3141/2343-09
- **Domain / Tier / Priority**: MATSim & agent-based traffic sim / 1 / **Read first**（表外新增；与我们的方法最接近）
- **Link**:
  - TRR 正式版（付费）：https://doi.org/10.3141/2343-09
  - 投稿版全文（VSP 工作论文，2012-11-15 提交，标题 "A multi-model approach to large-scale multiagent transport simulation"）：https://svn.vsp.tu-berlin.de/repos/public-svn/publications/vspwp/2012/12-12/2012-11-14_FourieIllenbergerNagel.pdf
  - 更早的草稿（2012-07-15，标题 "Using mental simulation to improve the agent learning rate…"）：同目录下的 2012-08-02-FourieIllenbergerNagel.pdf
- **依据**: ✅ 已读 2012-11 投稿版全文；✅ 核对了 TRR 正式版的官方摘要（OpenAlex），与投稿版一致。⚠️ 正文数字取自投稿版，正式版若有修改需要另行核对。标【推断】的是我们的映射。

> 一句话：在 MATSim 循环里加一个内循环，周期性地用**伪仿真 PSim** 代替 QSim。PSim 用上一轮 QSim 得到的**分时段 link 出行时间查找表**，为新方案生成"预期事件流"并打分，速度约快**两个数量级**，而且完全并行。苏黎世场景中，达到同一平均得分所需的 QSim 轮数从 **101 降到 13–20**，16 核墙钟时间减少**一半以上**。但**均衡状态有可见偏移**（mode share、link 流量），作者认为"utility on its own is not a complete indication"。

## 1. 瓶颈（原文）
- "greatest current performance limitation is the network loading simulation"（QSim）；QSim 线程间需要同步，多核收益递减，而 replanning 可以线性并行。
- **探索效率低**："the impact of random changes to day plans … rapidly diminishes with increasing iterations; therefore a lot of time gets spent on mobility simulation with diminishing returns"。随着选择维度增加，探索所需的迭代数会大幅增加。

## 2. 手段（原文 DESIGN）
- **外循环**：QSim → 打分 → 进入内循环；**内循环**：PSim 执行 → 打分 → replan，重复 p 次；然后再选方案跑一次 QSim。外循环重复 q 次，最后以一次 QSim 结束。
- **PSim**：从 QSim 事件流计算每条 link 在每个时段（如 15 分钟）的平均出行时间，存成查找表；新方案按查找表构造事件流，交给**同一个打分模块**，得到预期得分并存入 agent 记忆；记忆满了就删除最差方案。
- 只模拟**新生成、尚未打分**的方案（PSim 中 agent 之间没有交互），进一步减少计算。
- agent 之间没有交互 → 不需要线程同步，replanning、事件处理全部并行。
- 与"best-response 大模块"的对比：作者认为大模块难维护、难扩展；PSim 让**随机变异型**策略在便宜的环境中多试几次，更通用。

## 3. 省在哪一项
**QSim 迭代次数**（用便宜的伪迭代代替），并把计算转移到可以并行的部分（利用空闲核）。

## 4. 快了多少，代价是什么（投稿版原文数字）
**场景**：苏黎世 30 km 范围的 10% car 场景，**67,239 个 agent、60,518 条 link**，早高峰收费（容量 > 4000 veh/h 的 link）；四个 replanning 模块等权（时间调整、重路由、subtour mode choice、次要活动地点选择）；公交以 2 倍自由流时间"瞬移"，不做仿真。

**基线**：只用 QSim，101 轮，replanning rate 0.3，记忆 5 个方案，第 101 轮平均得分 175.4。所有运行比较的都是"首次达到 175.4"的那一轮。

| 运行 | 达到参照得分的 QSim 轮数 | 出发时间分布 RMSD | 日 link 流量 RMSD | 出行时间差 ≤ 5 min 的 agent | car 份额 |
|---|---|---|---|---|---|
| Reference（只用 QSim，换一个种子） | 101 | 32.56 | 5.67 | 77.1% | 80.7% |
| QSim:PSim = 1:9，rate 0.3 | 20 | 50.85 | 24.53 | 74.6% | 76.2% |
| QSim:PSim = 1:24，rate 0.1 | **13** | 56.42 | 30.00 | 76.1% | 79.99% |

- 墙钟时间：16 核时，最快的多模型配置比默认方法快**一倍以上**（"more than a factor of two"）；**单核时几乎没有收益**，"only effective as the number of cores committed to the simulation is increased"。
- 规律：在 replanning rate 固定时，达到某个得分所需的 QSim 轮数**约与总迭代数（QSim + PSim）成反比**。
- **意外发现**：**降低 replanning rate、增加 PSim 轮数更好**（0.1 + 1:24 优于 0.3 + 1:9），虽然每个 agent 每个外循环产生的新方案更少（2.5 vs 3）。作者解释为"the larger number of combinations of replanning modules that can act on any given plan in successive inner loop iterations"。
- **代价（均衡偏移）**：
  - **mode share 明显偏向公交**（76.2% vs 80.7%）。原因是早期拥堵时 PSim 让更多 agent 发现公交更优，而公交的最优出发时间与 car 不同。通过降低 replanning rate、把 mode choice 权重减半，car 份额基本恢复（79.99%）。
  - link 流量 RMSD 是两个种子之间差异的约 **4–5 倍**（24.53/30.00 vs 5.67）。作者说其最小值"approximately twice that of the reference case"，但"still relatively small in absolute value"。
  - 出发时间 RMSD 也更大；作者指出在参照得分那一轮，所有运行都**还没有稳定**（随机变异演化慢）。

## 5. 怎么证明结果没变
- 以 QSim-only 101 轮作基线；**另跑一次只换种子的 QSim-only 作为"种子噪声"参照**。
- 五个指标：平均执行得分（作为对齐点）、出发时间分布 RMSD（5 分钟间隔）、car mode share、日 link 流量 RMSD、agent 级总出行时间差（≤ 5 min、≤ 1 min 的比例）。
- 局限：多模型运行**都用同一个种子**，没有多种子分布；比较点取"得分达到 175.4 的那一轮"，而不是稳态。

## 6. 假设
- 一个 agent 的方案变化不会显著改变网络出行时间（PSim 中 agent 之间没有交互，用上一轮的出行时间）。
- 拥堵格局在相邻迭代之间变化不大（MATSim 书 Ch.40 的概括）。
- 公交不做仿真（瞬移）。

## 7. 能否用于 MATSim？怎么用
**✅ 就是 MATSim，而且是与我们方法最接近的已有工作，必须作为强 baseline 正面比较。**

【推断】对 novelty 的影响：
1. **"便宜地预评估创新"已经有人做了**，而且效果很大：QSim 轮数 101 → 13。我们的方法如果只是"用 surrogate 给创新打分"，就和 PSim 没有本质区别。
2. **PSim 的缺口正好是我们可以切入的地方**：
   - **PSim 让无效创新变便宜，但没有让它们变少**：所有变异仍是随机的，只是在伪仿真里多试几次。我们的出发点（85% 创新无效）是**生成什么、给谁生成**，与 PSim 正交，甚至可以叠加。
   - **PSim 改变了均衡**：mode share 和 link 流量都偏离了只换种子的差异范围。作者自己承认"utility on its own is not a complete indication"。这是"加速后停在不同状态"风险的**直接实证**，也说明 surrogate 偏差确实存在（对应 Jin 2005 的假最优，[12](12_Jin2005_fitness_approximation_survey.md)）。【推断】两阶段过滤（[34](34_Peherstorfer2018_multifidelity_survey.md)：LF 只用来过滤，是否保留由 HF 执行结果决定）理论上可以避免这种偏差，这是可以检验的区别点。
   - **PSim 的验证只有单种子 + 一个参照种子**，比较点不是稳态。我们用多种子 + R̂ + 分布比较，可以给出更强的结论。
3. **作者展望里的空白**：作者指出 agent 可能卡在局部最优（例如 car 方案附近，随机切换到公交得分更差，很快被删除），并提出"an agent could optimize a public transit plan over many PSim iterations and only then compare it"，且可以在 QSim 运行时用闲置的核并行做。【推断】这正是"有针对性的创新"，和我们的方向一致，需要查 2013 年以后 MATSim 社区是否已实现。
4. **对我们实验的直接启示**：
   - 必须报告 **mode share 和 link 流量的分布偏移**，而不只看得分；
   - "低 replanning rate + 更多廉价迭代"更好，与 [14 Eiben](14_Eiben1999_parameter_control.md) 的自适应思路相关；
   - PSim 只在多核时有效，而我们正好有约 12 个空闲核。

**待办**：查 PSim 在 MATSim 当前版本中的状态（文档入口 matsim.org/extensions → pseudosimulation），以及 2013 年后的后续工作（如带公交仿真的版本，原文引用 [43]）。

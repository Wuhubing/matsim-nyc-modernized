# [09] Lu, Mahmassani, Zhou 2009 — Equivalent gap function-based reformulation and solution algorithm for the dynamic user equilibrium problem

- **Venue**: Transportation Research Part B 43(3):345–364，DOI 10.1016/j.trb.2008.07.005
- **Domain / Tier / Priority**: DTA & traffic equilibrium / 1 / High（与 RQ3 相关）
- **Link**: https://ideas.repec.org/a/eee/transb/v43y2009i3p345-364.html（ScienceDirect，付费）。全文 PDF 由用户通过图书馆下载，存于 [pdf/09.pdf](pdf/09.pdf)。
- **依据**: ✅ 已读全文（20 页：§1–7，含 Proposition 1–2 证明、§6 两组实验、Table 1–9b、参考文献）。标【推断】的是我们的映射。

> 一句话：把仿真类 DUE 通过 **gap 函数** Gap(r, π) = Σ r_p·(c_p − π_od) 改写为非线性最小化问题（最优值为 0 当且仅当满足 DUE），用**列生成**求解：外循环加入新的时变最短路，内循环用**按相对成本差缩放的 path-swapping 下降方向法**把当前路径集"均衡"好。每条非最短路换出的流量 ∝ (c_p − c*)/c_p，不需要梯度，也不需要线搜索。在 4 个真实网络上比 MSA 得到的 gap 小得多。

## 1. 瓶颈（原文 §1）
- 时间维度使得梯度和线搜索在大规模 DTA 中计算量大或不可行；仿真得到的路径成本连解析导数都没有。
- 已有的 path-swapping 方法（Smith & Wisten 1995、Szeto & Lo 2005 等）按**绝对**成本差换流，交换率没有系统的确定方法，要用很小的交换率防振荡，结果要几百甚至几千轮才收敛。
- MSA 不保证每轮下降，而且用"across-the-board step size"，不考虑不同 OD、不同出发时段离均衡有多远，可能收敛慢甚至不收敛。

## 2. 手段（原文 §3–5）
- **gap 函数（式 7）**：Gap(r, π) = Σ_{o,d,τ,p} r^τ_odp·[c^τ_odp(r) − π^τ_od]。Proposition 1 证明它是 VI 问题的 gap 函数。仿真中路径成本取同一 (o, d, τ, p) 上各车经历成本的平均。
- **列生成框架（§4，Fig. 1）**：外循环 k：求时变最短路，加入新路径；内循环 l：在当前路径集上用下降方向法求解受限问题（RNMP），每步都要做一次仿真加载。受限问题**不必解到最优**。
- **下降方向（式 12–14）**：对每个 (o, d, τ)，非最短路 p 的流量更新为 r_p·[1 − ρ·(c_p − c*)/c_p]，换出的流量平均分给当前最短路。用 1/c_p 缩放，起到类似 Newton 法中 Hessian 逆的作用，所以不需要选步长。Proposition 2 证明这是下降方向（假设路径边际可加，作者承认在有信号和排队的网络中只近似成立）。
- 原文的直觉解释："travelers farther from the equilibrium and on paths with larger flow rates are more strongly inclined to change path"。Fig. 2 的例子：同样差 5 分钟，在 125 分钟的 OD 上和在 10 分钟的 OD 上意义完全不同，用绝对差会在长 OD 上换得太多。
- **混合步长（式 17）**：每个外循环刚加入新路径的第一个内循环用 ρ = 1/k（MSA 步长，防止大量流量一下子涌向新路径），之后用 ρ = 1。
- 采用基于车辆的实现（从车辆路径集记录分配，即 [08](08_Sbayti2007_efficient_MSA_SBDTA.md) 的思路）。

## 3. 省在哪一项
**达到同等 gap 的迭代次数**（以及总计算时间）。每轮比 MSA 稍贵（要计算方向），但轮数少。

## 4. 快了多少，代价是什么（原文 §6）
- **两节点网络**（6,100 辆车在观测期，只测下降方向，不加新路径）：10 轮后平均 gap 从 0.45 min 降到 DDM 0.01 min、MSA 0.03 min；目标值 DDM 61.0、MSA 190.5（初始 2762.1）；计算时间 10.6 s vs 9.5 s。DDM 的收敛曲线几乎单调，MSA 前几轮明显振荡。
- **九节点网络**（11,236 辆车）：两种方法都在约 15 轮后没有新路径；混合步长目标值 105.3，MSA 554.0；CGMSA 每轮 21.5 s，CGDDM 23.7 s，但总时间 301 s vs **213 s**。
- **内循环次数 L_max（Table 3）**：1 → 2 时多降 11.7% 的初始 gap，只多 17 s；5 → 10 只多降 3.5%，多 89 s。所以受限问题不必解到最优。
- **出发时段长度（Table 4）**：DDM 对时段长度不敏感（平均 gap 0.008–0.011 min）；MSA 时段越粗越差（0.019 → 0.091 min）。
- **4 个真实网络（Table 6–7b）**：Fort Worth（27,447 辆）、Irvine（35,304）、Knoxville（86,483）、B-W 走廊（91,389）；K_max = 50、L_max = 5。以链路成本 gap 计，混合步长 DDM 的 gap 下降 92.5%–99.9%，CGMSA 只有 74.1%–93.8%（B-W 走廊：DDM 98.4% vs MSA 74.1%）。所有方法都至少降了 70%。
- 以"平均 gap < 0.1 min（6 秒）"为够好：混合步长 DDM 在 Fort Worth 上只要 5–6 轮，B-W 走廊 4–5 轮。
- **L_max = 1 时（没有受限路径集均衡）DDM 和 MSA 表现差不多**（Table 8a/8b）；从 L_max = 2 起 DDM 才明显更好。即收益主要来自"内循环先把现有路径集均衡好"。
- 计算时间：Fort Worth 约 3–6 小时，Irvine 约 8–23 小时（Pentium IV 2.8 GHz，2 GB 内存）；同样 L_max 下 DDM 每次运行只比 MSA 慢几分钟。
- 代价：维护路径集和路径流；每个内循环都要一次仿真加载，总仿真次数 ≈ K × L。

## 5. 怎么证明结果没变
- 用 gap 函数及与问题规模无关的**平均 gap**（AGap，每辆车平均离最短路多少分钟）衡量离 DUE 有多远；两种算法都可以用"车辆经历成本"或"链路成本累加"两种 gap。
- Table 5 直接检查九节点网络的解：每个 5 分钟出发时段内，被使用路径的平均经历时间都非常接近，未使用路径的时间都不更短，所以基本满足 DUE 条件。
- 作者明确说："this solution may not be a unique global one"，并引用 Sheffi 关于路径流不唯一的讨论。
- 每个场景只跑一次，没有随机种子比较。

## 6. 假设
- 确定性 DUE：时变 OD 已知；只有路径选择，出发后不改路；完全信息；没有 SUE 式的随机选择。
- 仿真器要能逐车追踪（中观或微观）以计算经历成本；任何保 FIFO、能表现物理排队的模型都可以。
- 下降性的证明需要链路成本单调、路径边际可加（作者承认只近似成立）。
- 没有讨论解的存在性和唯一性。

## 7. 能否用于 MATSim？怎么用
**🟡 需要改造：**
- **作为指标（RQ3）**：【推断】AGap 的形式（"每人平均离最优回应差多少"）正是我们需要的、与 replan 人数无关的收敛指标。MATSim 中可定义 agent gap = 最优回应得分 − 当前执行得分（最优回应用 router 或 PSim 在本轮出行时间下近似），比"平均得分不再变化"更适合做收敛判据，可以修补 Zhuge 2021 判据的内生性问题（参见 Sheffi 对 MSA 判据的警告，[06](06_Sheffi1985_Urban_Transportation_Networks.md)）。本文"平均 gap < 6 秒算够好"的做法给了一个绝对阈值的范例。
- **作为机制（方法 3）**：【推断】换路比例 ∝ **相对**差距 (c_p − c*)/c_p，而不是绝对差距。迁移到 MATSim：replan 概率可以按"相对得分差"设定，避免长出行链的人因为绝对差距大而被过度选中。
- 【推断】Table 8 的结果很重要：**收益主要来自"内循环先均衡好现有方案"**，而不是方向本身。对应 MATSim：创新（加入新方案）之后，先只做选择、让现有方案集稳定几轮，再做下一轮创新，可能比每轮都创新更有效。MATSim 的"innovation 只在部分迭代开启"是这个思路的粗糙版本。
- 【推断】混合步长"新路径加入时用 1/k，之后用 1"对应：新方案进入方案记忆的那一轮要谨慎（防止大量 agent 同时涌向新方案导致振荡），之后可以放开。
- 不能照搬：MATSim 是 SUE（logit 选择），gap 只会降到噪声底，不会降到 0；agent 的全天计划没有共同的"同组参照"，不同人的得分不可比。Nagel & Flötteröd 2009 明确说当时没有适用于全日计划的可操作 gap 函数（[04](04_Nagel2009_agent_based_traffic_assignment.md)）。
- 与 [08 Sbayti](08_Sbayti2007_efficient_MSA_SBDTA.md) 一脉相承：08 是"总步长不变、按出行时间排序挑人"，09 是"每条路径按相对差距决定换出比例"。POLARIS 的 gap-based 方法建立在这一系列上（[51](51_Verbas2024_POLARIS_gap_based.md)）。

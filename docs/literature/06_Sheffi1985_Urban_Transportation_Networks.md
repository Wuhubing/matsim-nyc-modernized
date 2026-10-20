# [06] Sheffi 1985 — Urban Transportation Networks: Equilibrium Analysis with Mathematical Programming Methods

- **Venue**: Prentice-Hall（作者在 MIT 页面免费提供 PDF）
- **Domain / Tier / Priority**: DTA & traffic equilibrium / 1 / Medium
- **Link**: https://web.mit.edu/sheffi/www/urbanTransportation.html → PDF：web.mit.edu/sheffi/www/documents/sheffi_urban_trans_networks.pdf
- **依据**: ✅ 已读原书相关章节全文（2026-10-19 补读）：Ch.5 §5.1 启发式均衡法、§5.2 Frank–Wolfe（凸组合法）应用（pp. 111–122）；Ch.12 全章：§12.1 SUE 等价极小化（pp. 312–322）、§12.2 MSA（pp. 322–332）、§12.3 More about SUE（pp. 332–340）、§12.4 小结。**未读**：Ch.1–4（基础数学规划）、6–11、13，这些是 UE 扩展与输入数据，与加速无直接关系。标【推断】的是我们的映射。

> 一句话：SUE 的等价最小化问题只有唯一极小点，但标准的"下降方向 + 线搜索"在 SUE 上做不了：随机加载使方向带噪声，目标函数也算不出来。所以用 **MSA**：预设步长 α_n = 1/n，x_{n+1} = x_n + (1/n)(y_n − x_n)。Sheffi 特别提醒，MSA 的流量是被"强迫"收敛的，**以流量相对变化作停止判据可能误导**。

## 1. 瓶颈（原文）
SUE 求解有两个难点（§12.2）：
1. 下降方向需要随机网络加载（probit 只能 Monte Carlo），所以方向是随机变量，"may not point at a descent direction (even though on the average it is a descent vector)"。
2. 目标函数含期望感知 OD 时间，需要路径枚举或模拟，计算昂贵且是随机值，"making the line search very difficult and in many cases infeasible"。

## 2. 手段
**MSA**（pp. 324–327）：
- 步长序列预先确定，与当前解无关。
- 收敛条件：Σα_n = ∞（保证不会过早停在半路）且 Σα_n² < ∞（保证随机误差的方差趋于 0）；方向只需"平均意义上"是下降方向。
- α_n = 1/n ⇒ x_{n+1} 就是前 n 个辅助解 y 的平均，"the source of the algorithm's name"；var(X_n) ≤ σ²/n → 0。
- 算法：初始加载 → 更新 link 时间 → 按当前时间做随机加载，得辅助流 y → x ← x + (1/n)(y − x) → 判断收敛。
- MSA 对确定性 UE（y 用全有全无加载）同样收敛，但比 convex combinations（Frank–Wolfe）慢。

## 3. 省在哪一项
MSA 本身是"稳但慢"的基准，不省时间。它的意义在于**在随机加载下仍然收敛**。

## 4. 快了多少，代价是什么
- 书中没有给加速倍数。
- 代价：步长与问题无关；收敛**非单调**，因为随机方向可能指向目标函数上升的方向，固定步长也可能越过最优点。

- **补读发现（§5.1–5.2，§12.3）**：
  - **朴素迭代会振荡**（Table 5.1）：capacity restraint 每轮全量 all-or-nothing，流量在 link 1 和 2 之间"flip-flops"，永不收敛。FHWA 的修补办法是 0.75/0.25 平滑加上取最后 4 轮平均，但"there is no reason to expect this algorithm to converge"，结果也不是均衡（三条路径的时间分别是 13.7/27.3/26.8）。Frank–Wolfe 只是在同样的程序里加一个线搜索步，3 轮后三条路径的时间就是 26.1/26.3/25.3。【推断】这对应 MATSim 的 innovation 比例：全员换方案就会振荡，控制步长才能收敛。
  - **算法效率要按最短路计算次数比较**："traffic assignment algorithms should be compared in terms of efficiency for a given number of minimum-path computations"。【推断】我们应按 mobsim 次数或墙钟时间比较，不是按迭代数。
  - **前几轮最划算**：Frank–Wolfe 的前几轮"the most cost effective"；实际大城市路网 4–6 轮就够，因为输入数据的精度不值得算得更准。**拥堵越重，收敛所需迭代越多**（Fig. 5.2）。
  - **内外循环的权衡（§12.3，对 PSim 式内循环直接适用）**：probit SUE 的 MSA，每个外迭代配 20 次内迭代时，需要 80–100 次 all-or-nothing 才收敛；配 5 次要 40–60 次；**配 1 次最好，只要 20–40 次**。对角化算法的结论也一样："it is best to use the minimum amount of computational effort on the intermediate (or sub-) problems"。
  - SUE 需要的 all-or-nothing 次数约为 UE 的 2–3 倍（10–12 次对 4–5 次）。MSA 在低拥堵、感知方差大时收敛快；高拥堵时慢，此时可以用 UE 近似 SUE。
  - **SUE 解唯一**（§12.1）：等价程序的 Hessian 正定，所以只有一个极小点（前提是 link 之间无交互）。有非对称 link 交互时没有等价极小化形式，只有 Jacobian 正定才保证唯一。【推断】MATSim 的 link 交互（溢出、公交）不满足这个前提，所以多重均衡是可能的，这与 [05](05_BenDor2021_population_downscaling.md)、[11](11_Watling2003_day_to_day_dynamics.md) 一致。

## 5. 怎么证明结果没变 / 收敛判据（原文，与我们高度相关）
- "it can be argued that the sequence {x^n} is 'forced' to converge. Consequently, stopping criteria that are based on the relative change in link flow may be misleading"。
- 建议：
  - 固定迭代次数；或
  - 看目标函数的下降速率；或
  - 用最近 m 轮的流量平均 x̄（m = 3 即可）来构造判据，如 (1/A)Σ(x̄^{n+1} − x̄^n)/x̄^n ≤ κ，这种判据"generally monotonically decreasing"。

## 6. 假设
- 静态网络；link 成本只依赖本 link 流量（可分离）且递增 → SUE 程序"has only a single minimum"。
- MSA 收敛要求：目标函数二阶连续可微、梯度在可行域内只有一个零点、方向平均意义上是下降方向。
- **MATSim 不满足**：有动态排队和溢出，成本不可分离，没有可写出的目标函数，唯一性没有保证（见 [04](04_Nagel2009_agent_based_traffic_assignment.md)：物理排队导致多重均衡）。

## 7. 能否用于 MATSim？怎么用
- 【推断】§12.3 的"内循环越少越好"给 PSim 式或 two-stage 方案提了一个可检验的假设：每轮 QSim 配多少次廉价评估最优，可能比直觉的少。PSim 原文的配置是 9 或 24 轮 PSim 配 1 轮 QSim（见 [46](46_Fourie2013_PSim.md)），值得做一个"内循环次数"的敏感性实验。
**🟡 概念可直接映射，算法要改。**
- 【推断】MATSim 的创新比例或 replanning 比例 ≈ MSA 步长。Σα = ∞、Σα² < ∞ 给出"递减创新率"不破坏收敛的理论条件（在 MATSim 中只是启发，因为前提不满足）。
- **对 RQ3 和我们批评 Zhuge 2021 的直接支持**：Sheffi 1985 就已指出，在步长递减或更新量变小的算法里，以"变化量变小"作收敛判据会误导。【推断】Zhuge 用"平均得分相对变化 < 0.001"，而他们的方法本身减少了 replan 的人数，这是同一类问题。可以直接引用 Sheffi。
- Frank–Wolfe 线搜索 ❌：需要可计算的确定性目标函数。
- 可借的工程做法：判据基于最近几轮的移动平均（m = 3），而不是单轮。

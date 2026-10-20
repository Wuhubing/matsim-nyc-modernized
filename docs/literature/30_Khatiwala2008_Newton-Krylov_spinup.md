# [30] Khatiwala 2008 — Fast spin up of ocean biogeochemical models using matrix-free Newton–Krylov

- **Venue**: Ocean Modelling 23(3–4):121–129
- **Domain / Tier / Priority**: Climate model spin-up / 2 / Low
- **Link**: https://ora.ox.ac.uk/objects/uuid:0bfee829-bf1d-4d3e-a4ca-aa6cb882e62c
- **依据**: ⚠️ **只读到官方摘要**（ORA 页面），没有公开全文。另外参考了 Khatiwala 2024（[29](29_Khatiwala2024_spinup_sequence_acceleration.md)，已读全文）对 Newton–Krylov 的评价。 2026-10-19 重查 OpenAlex：仍为 closed access，没有开放版本，**需要你通过图书馆获取全文**。

> 一句话（摘要）：提出一种高效计算**季节性强迫**海洋生物地球化学模型平衡解的方法：把问题写成大型非线性代数方程组，用 **matrix-free Newton–Krylov（MFNK）**求解。Newton 法提供超线性收敛，Krylov 子空间法求解 Newton 修正方程，两者通过 Jacobian–向量积联系，而这个乘积可以近似"探测"出来，不需要形成和存储真实 Jacobian。为了使 O(10⁶) 自由度的全球模型可行，设计了**灵活的预条件策略**。结果是一个基本"黑箱"的方案。在两个真实的生物地球化学问题上，比传统直接时间积分**约高效两个数量级**。

## 1. 瓶颈
同 [29](29_Khatiwala2024_spinup_sequence_acceleration.md)：直接时间积分要很长时间才能达到周期稳态。

## 2. 手段（摘要）
- G(u) = Φ(u) − u = 0（Φ 为一个强迫周期的模型积分）。
- Newton 迭代 + Krylov（如 GMRES）求解修正方程；Jacobian–向量积通过近似探测得到（matrix-free）。
- 灵活的预条件策略，使 O(10⁶) 自由度可行。

## 3. 省在哪一项
**迭代次数**（模拟年数）。

## 4. 快了多少，代价是什么
- 摘要："roughly two orders of magnitude more efficient" than direct time integration。
- 代价：需要预条件子。Khatiwala 2024 回顾说，Newton–Krylov 迄今"have only been successfully applied to simple geochemical models"，"has proved difficult in practice to apply to anything but the simplest biogeochemical models"。这正是作者后来转向 AA 的原因。

## 5. 怎么证明结果没变
摘要没有说明；从同系列工作推断是与直接积分的平衡解比较（待核实）。

## 6. 假设
- 确定性、足够光滑的映射（Jacobian–向量积的近似探测需要）；连续状态；有可用的预条件子。

## 7. 能否用于 MATSim？怎么用
**❌ 不适用：**
- 【推断】MATSim 是随机的：通过有限差分近似 Jacobian–向量积 [Φ(u + εv) − Φ(u)]/ε 时，噪声项按 1/ε 放大，会淹没信号。
- 【推断】状态离散（方案），没有光滑的 Jacobian；也没有现成的预条件子。
- 作者本人在 2024 年的论文中已经说明这种方法在复杂模型上难以应用，并改用更稳健的 AA（[29](29_Khatiwala2024_spinup_sequence_acceleration.md)）。
- 列入对照表的"不适用"一栏，作为"确定性 + 光滑"假设把方法筛掉的典型例子。

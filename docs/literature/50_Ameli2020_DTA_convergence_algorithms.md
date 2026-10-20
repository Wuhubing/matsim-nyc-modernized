# [50] Ameli, Lebacque & Leclercq 2020 — Cross-comparison of convergence algorithms to solve trip-based dynamic traffic assignment problems

- **Venue**: *Computer-Aided Civil and Infrastructure Engineering* 35(3):219–240，DOI [10.1111/mice.12524](https://doi.org/10.1111/mice.12524)
- **全文来源**: [HAL hal-02380851v2](https://hal.science/hal-02380851v2)（作者稿，24 页）
- **领域**: 2 DTA 与交通均衡（近期）
- **依据**: ✅ 已读全文：摘要、§4 各 swapping 算法（含 Lu 2009 的 gap-based 公式）、§5 实验设置、§7 结论。

> 一句话：系统比较仿真类 DTA 内循环中各种"把出行者从一条路径换到另一条路径"的 swapping 算法（MSA、MSAR、gap-based、概率型等），提出 4 种新 swapping 算法和 2 种步长初始化方法，在小、中、大三种网络和三种饱和度下全面测试。

## 1. 瓶颈
DTA 是不动点问题，外循环找路径集，内循环分配路径流；每次评估都要跑一次微观仿真（Symuvia），大网络上很慢。

## 2. 手段（原文）
- 比较的算法：MSA、MSAR、**gap-based（GB，Lu et al. 2009）**、gap-based normalized（GBN）、按路径排序的 SSP、GBP、BGB、概率型（PI）、IMSA 等。
- **Lu 2009 的 gap-based 公式**（§4）：换出路径 p 的比例 = (C_p − C*_w)/C_p × MSA 步长，其中 C*_w 是该 OD 的最短路径成本。作者指出，gap 指标乘上 MSA 步长可能使步长过小；GBN 把 gap 在 OD 内归一化，换得更灵活。
- 新增：初始分配方式（"Keep solution"）、步长初始化（Reset、Smart）。

## 3. 省在哪一项
**迭代次数**。

## 4. 快了多少，代价是什么
- 网络：5×5 网格、Ring city、Lyon 6e + Villeurbanne（1,883 个节点、3,383 条 link，2.5 h 需求），各有欠饱和、饱和、过饱和三种需求。
- 结论（§7）：
  - 网络规模和饱和度影响算法表现；
  - **"概率型（不用步长）+ Keep solution 初始化"**在多数情况下最好；
  - 外循环开始时的初始分配和步长对最终解和收敛速度影响显著；
  - 大网络过饱和情景下，新的步长初始化"can save a minimum of one day of computation"。
- 大网络上单次求解仍需数万到数十万秒（Table 8）。

## 5. 怎么证明结果没变
用平均 gap（AGap，秒）和违反约束的程度 V(G) 衡量解的质量，同时比较计算时间。

## 6. 假设
trip-based，出发时间固定，只有路径选择；微观仿真器提供路径时间。

## 7. 对我们意味着什么
- 【推断】**"按 gap 决定换多少"在 DTA 里有成熟的公式和大规模比较**，我们 approach 3（gap 定向 replan）可以直接借用 GB/GBN 的形式，并引用本文说明"概率型、不用步长"的方式在大网络上更稳。
- 【推断】"初始分配和初始步长对收敛影响显著"与 Mahfuz 2025 的"好的初值省 50–95% 迭代"一致，对 MATSim 的启示是：探索期的起点和早期步长值得调整。
- 这篇文章也补全了 [09 Lu 2009](09_Lu2009_gap_function_DUE.md) 中我们只读过摘要的公式部分。

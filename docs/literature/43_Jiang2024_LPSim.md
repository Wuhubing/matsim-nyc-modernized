# [43] Jiang, Sengupta, Demmel, Williams 2024 — Large scale multi-GPU based parallel traffic simulation for accelerated traffic assignment and propagation (LPSim)

- **Venue**: arXiv 2406.08496v2（2024-10-23，作者标注"Preprint submitted to Elsevier"）；v1 标题为"LPSim: Large Scale Multi-GPU Parallel Computing based Regional Scale Traffic Simulation Framework"
- **Domain / Tier / Priority**: GPU & parallel simulation / 3 / Low
- **Link**: https://arxiv.org/abs/2406.08496v2
- **依据**: ✅ 已读全文（arXiv v2：§1–5；部分表格数值在文本提取中错位，只引用正文能确认的数字）。标【推断】的是我们的映射。

> 一句话（摘要）：UC Berkeley 与 LBNL 的多 GPU 区域交通仿真框架。用**图划分**平衡多 GPU 负载，同时仿真数千万辆车的个体动力学。单块 V100 用 **6.28 分钟**完成 282 万个出行；两块 V100 用 **21.16 分钟**完成 901 万个出行；双 A100 用 **0.0398 h**，比 Xeon Gold 6326 CPU（4.49 h）快约 **113 倍**。

## 1. 瓶颈
区域尺度微观仿真要持续更新海量车辆状态、处理大量时空数据，计算需求很高（§1）。传统微观仿真器只能覆盖有限的主干道路。

## 2. 手段
- 微观模型：**IDM 跟驰**（可替换为其他传播模型）。
- 单 GPU：向量化的数据存储与访问；多 GPU：基于图划分，保证 GPU 数变化时输出一致。
- 用 BSP 模型、Amdahl 定律、Roofline 模型做性能分析。
- **数据结构（§3.1）**：路网在 GPU 内存中存成一维 char 数组，**1 字节 = 1 米车道**，255 表示空，0–254 表示车速（m/s）；每辆车一个线程，只依赖上一步状态（SIMD 友好）；换路段用原子操作避免两车写同一位置；路口处下游满了就等待。**路径由输入需求给定**，仿真中不重新选路。
- **多 GPU（§3.3）**：节点按图划分到各 GPU，跨分区的边放入"ghost zone"在两侧复制；车辆进入 ghost zone 时复制、离开时删除，用 Thrust device_vector 动态管理，用 cudaMemcpyPeer 直接在 GPU 间传。划分有两种：**均衡划分**（多层图划分，适合计算受限时）和**非均衡划分**（Leiden 社区检测 + 按地理位置 k-means 聚合，适合计算充裕、要减少通信时）。图的权重来自车辆路径的访问次数。

## 3. 省在哪一项
**每步计算**（交通传播的仿真时间）。

## 4. 快了多少，代价是什么（原文）
- 湾区路网 224,223 个节点、549,008 条边，SFCTA 一天（0–12 点）的 9,008,766 个出行：CPU 4.49 h，双 A100 0.0398 h，约 **113 倍**。
- 2 → 4 块 GPU（均衡划分）：约 **1.68 倍**加速。**多 GPU 之间的通信时间会抵消一部分并行收益**（贡献 3）。
- **4 → 8 块 GPU 时运行时间反而增加**：均衡划分是通信成为瓶颈，非均衡划分是各 GPU 计算量差异过大。随机划分在 80% 时就中止（Table 4）。
- 不同需求规模（3M–24M 出行，AWS V100）：所有规模从 1 到 2 块 GPU 都有收益；12M、20M 一直到 4 块都有收益；**24M 必须用 4 块以上**（单卡内存不够）。
- P2P 通信时间约为本地读写的 3 倍；经过图划分，通信只占总计算量约 **1‰**。
- **Roofline 分析**：线程分支（predication）导致约 **10 倍**性能损失；把 OD 按出发时间排序后降到约 **2 倍**（同一 warp 内的线程更可能走相同分支），但内存访问模式反而变差。程序是**内存受限**的。
- 把车辆存储从数组改成 device_vector 后快很多（数组版本需要大量主机–GPU 传输）。
- 与 Yedavalli et al. 2021（单 GPU，3.2M 出行）相比，LPSim 在相同规模下最快，并能扩展到 2400 万个 OD 出行。
- 代价：专用硬件；作者明确说贡献在"computational aspects, rather than theoretical transportation models"；尚未测试多模式（未来工作）。

## 5. 怎么证明结果没变
结论称"validated against real-world data"（引用 Jiang et al. 2024），本文主要验证速度和扩展性；未来计划用 Uber Movement 数据做标定和验证。

## 6. 假设
- trip-based 的 OD 需求（SFCTA 的 SF-CHAMP 模型给出 2350 万个出行，只取其中 1780 万个小汽车出行，即 75.7%），路径由外部给定；本文不涉及行为均衡的学习循环（相关工作中把 MATSim 和 BEAM 作为 agent-based 的对比背景）。
- 仿真规则很简化：不模拟碰撞，位置精度 1 米，路口规则简单。

## 7. 能否用于 MATSim？怎么用
**❌ 不能直接用（不是 MATSim，没有活动链和共同演化的 replanning）：**
- 【推断】作为"每步计算的硬件上限"参考：GPU 可以给交通传播带来约两个数量级的加速。但要注意比较对象是"路径已知、只做传播"的仿真，不包括 replanning 和打分。
- 【推断】"按出发时间排序减少分支"是一个简单可借的工程技巧：MATSim 的 agent 处理顺序如果按相似性分组，可能提高缓存/向量化效率。
- 【推断】"多 GPU 通信抵消收益"与我们观察到的"16 核只用约 3.8 核"属于同一类问题（同步/通信开销）。LPSim 的经验是：GPU 数超过问题规模所需时，再加只会变慢；而且负载不均衡（非均衡划分 8 块 GPU）同样会拖慢。MATSim QSim 的多线程也有同样的两种瓶颈。见 [45 Fujimoto](45_Fujimoto2000_PDES.md)；[05 Ben-Dor](05_BenDor2021_population_downscaling.md) 也报告 MATSim 并行 QSim 在约 11 核以上不再加速。

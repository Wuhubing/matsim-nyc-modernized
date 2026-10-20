# [47] Laudan, Heinrich & Nagel 2025 — High-Performance Mobility Simulation: Implementation of a Parallel Distributed Message-Passing Algorithm for MATSim

- **Venue**: *Information* 16(2):116（MDPI，开放获取），DOI [10.3390/info16020116](https://doi.org/10.3390/info16020116)
- **全文来源**: TU Berlin 机构库 [depositonce](https://depositonce.tu-berlin.de/items/d9fb992d-7229-49a4-a910-501e0bdcb982/full)（26 页 PDF）。前一版是 ISPDC 2024 会议论文（[VSP 工作论文](https://svn.vsp.tu-berlin.de/repos/public-svn/publications/vspwp/2024/24-10/LaudanEtAl2024DistributeQSim_accepted.pdf)，报告"最多快 100 倍"）。
- **领域**: 1 MATSim（表外新增，近期）
- **依据**: ✅ 已读全文（2025 期刊版，26 页：§1–5、表 1、图 1–9、参考文献；第二轮从头到尾重读）。标【推断】的是我们的映射。

> 一句话：用 Rust 重写 QSim，并改成按路网分区、用 MPI 消息传递的分布式算法。在 Metropole Ruhr 10% 场景上，1024 个进程时比现有 QSim **快 119 倍**，一天交通约 3.5–3.6 s 跑完（摘要写 3.5 s，结论写 3.6 s）。仍是原型，只加速 mobsim。

## 1. 瓶颈（原文）
- MATSim 三个阶段中，打分和 replanning 是"embarrassingly parallel"的，mobsim 最难分布，因为 agent 之间有交互。
- **现有 QSim 的扩展性很差**：单进程 real-time ratio（RTR）82，最高 202（24 个进程），但**超过 6 个进程后基本停在 191，只比单进程快 2.5 倍**。

## 2. 手段
- 用 METIS 把路网分成若干分区，每个进程负责一块；只和相邻分区交换消息（MPI）。
- 保持与 MATSim 输入输出格式兼容，产生与现有 mobsim **相同格式**的事件日志，便于用现有工具核查。
- 用 Rust 实现：单进程就比 QSim 快 7 倍（RTR 560 vs 82），作者归因于更紧凑的内存布局。
- 与 QSim 的交通流实现**并不完全相同**（§2.1）：没有 queue/buffer 两段结构，流量容量在交叉口更新时执行；存储容量用记账方式延迟释放来模仿 QSim；车辆进出路网的处理方式不同。
- 每个时间步都要与所有相邻分区同步一次。

## 3. 省在哪一项
**每步计算**（mobsim）。

## 4. 快了多少，代价是什么
- 场景：Metropole Ruhr，10% 样本，491,175 人，547,011 个节点、1,193,056 条 link；仿真 36 h；**去掉了公交**（原型不支持）。
- 10% 场景：1024 个进程（43 个节点）RTR 24,284，比单进程快 43.4 倍，比 QSim 快 **119 倍**。小样本收益小：1% 场景最多快 6.9 倍。
- 单台机器 16 个进程：比单核快 7.3 倍（QSim 同样条件只有 2.5 倍）。
- 进程多了以后，时间主要花在进程间通信，计算时间可以忽略；通信时间由**邻居最多的那个分区**决定（最多约 21–22 个邻居，平均约 6 个），网络延迟决定上限；作者的性能模型按每个邻居约 2 µs 拟合。
- 文中对比：Strippgen（GPU 版 QSim）比 Java 版快至多 70 倍，但要大改 MATSim 数据模型；Wan et al. 2023 的分布式 MATSim（PATRIC）最快只在 4 个进程时快 2 倍；Mobiliti 扩展性好但没有存储容量约束（无回溢）。
- 代价：原型；没有公交；只覆盖 mobsim，打分和 replanning 尚未整合；需要 HPC 集群和低延迟网络。

## 5. 怎么证明结果没变
产生与现有 mobsim 相同格式的事件日志，"allowing the simulation results … to be easily verified"。但全文**没有给出与 QSim 逐项比较流量、行程时间或均衡结果的数字**，而 §2.1 列出的实现差异意味着结果不会逐位相同。

## 6. 假设
交通流模型与 QSim 相同（排队模型）；单次 mobsim 内的计算加速，不涉及迭代与均衡。

## 7. 对我们意味着什么
- 【推断】**直接解释了我们"16 核只用到约 3.8 核"的现象**：现有 QSim 在 6 个进程后就不再加速。
- 【推断】每步计算的上限很高，但这个原型需要集群、不含公交，短期内用不上 MATSim-NYC。而且只要 replanning 仍是串行环节，整轮收益就会像 GEMSim 那样缩水（[42](42_Saprykin2019_GEMSim.md)）。
- 定位：RQ1 次问题的上限证据，与我们减少迭代次数的方向正交。

# [42] Saprykin, Chokani, Abhari 2019 — GEMSim: A GPU-accelerated multi-modal mobility simulator for large-scale scenarios

- **Venue**: Simulation Modelling Practice and Theory 94:199–214，DOI 10.1016/j.simpat.2019.03.002
- **Domain / Tier / Priority**: GPU & parallel simulation / 3 / Medium（架构最接近 MATSim）
- **Link**: 表中链接是作者 2022 年 ETH 博士论文《Application of Heterogeneous CPU-GPU Hardware for Large-Scale Agent-Based Mobility Simulations》（research-collection.ethz.ch/handle/20.500.11850/601899，开放获取，316 页）
- **依据**:
  - ✅ **博士论文全文已读**（2026-10-16 下载，2026-10-19 读完）：第 1–8 章、附录 A 的表 A.1–A.7 都读了，参考文献只浏览。读过的内容包括：ch.1–2 文献综述，ch.2 模型、收敛、Table 2.2、规模扩展、gridlock、异构硬件和能耗，ch.3 公交和车队，ch.4 需求管线，ch.5 慕尼黑 MaaS，ch.6 降采样，ch.7 Quartz，ch.8 结论和展望。论文第 2 章注明"based on contributions from"本期刊论文；Table 2.2 明确说是对该论文（论文参考文献 [178]）早先基准测试的**更新版本**。
  - ✅ 期刊论文：核对了**官方摘要**（Elsevier 摘要）；期刊正文付费，未读。
  - 标【推断】的是我们的映射。

> 一句话：GPU 上实现的中观、多模式、排队型 mobsim，外面套着与 MATSim 相同结构的共同演化学习循环。期刊版（2019）摘要：全瑞士最多 520 万 agent，mobsim 比 MATSim **快 68 倍**，内存为 1/5，一天仿真不到 5 分钟。博士论文（2022）用更新的硬件重做基准：**mobsim 快 100 倍，但整个循环只快 22.7 倍**，因为数据准备和 replanning 变成了新瓶颈。

## 1. 瓶颈
大规模 agent-based 出行仿真运行时间长（博士论文摘要："make the existing agent-based modelling tools impractical and lead to long runtimes"）。MATSim 的事件处理开销会随着交通流趋于均衡而**增大**：随着 agent 学会更好地出行，产生的事件更多，所以后期迭代反而更慢（§2.4.3）。

## 2. 手段
- GPU 上的中观排队模型（与 QSim 同一类交通流抽象），多模式（含公交）；**不是事件驱动的**，所以每轮时间稳定在约 90 s。
- 与 MATSim 相同结构的学习循环（plan → mobsim → score → replan）；re-routing 用 20 个线程，实现比 MATSim 更高效。
- 博士论文后续：同一套数据结构移植到众核 CPU（CPU 后端），扩展到需求响应车队、MaaS。

- **路由留在 CPU**（Table 2.1）：文献里的 GPU 最短路实现没有优势，San Francisco 网络上 GPU 反而**慢 8 倍**。所以 replanning 仍然在 CPU 上多线程跑。
- **Gridlock 处理**（§2.5）：GPU 不能动态分配内存，所以重新设计了三种策略：push-through、re-inject、squeeze（虚拟容量 64）。
  - 约 25 轮后三种策略收敛到相近状态。push-through **几轮内就给出不错的近似**，适合标定。
  - 作者建议混合使用：前期用 push-through，后期换 squeeze。
  - gridlock 处理最多占运行时间的 25%。
- 结果不完全确定：GPU 原子操作加上随机节点顺序，每次运行的输出都略有不同（§2.4）。

## 3. 省在哪一项
**每步计算**（mobsim），附带 replanning 的工程优化。

## 4. 快了多少，代价是什么（原文数字）

**博士论文 Table 2.2**（§2.4.3）。设置：300 万个只开车的 agent；2× AMD EPYC 7742 + 1 TB RAM + A100 40 GB；MATSim 用多线程 QSim（7 个线程跑排队模型，14 个线程处理事件）；两边都对 10% agent 做 re-routing（20 个线程）；每人保留 3 个方案；先跑 10 轮预热再测量。

| 环节 | GEMSim (s) | MATSim (s) | GEMSim 加速 |
|---|---|---|---|
| 数据准备 | 100 | 21 | **0.21×（更慢）** |
| Mobility simulation | 90 | 9058 | **100.64×** |
| Scoring | 1 | 4 | 4.00× |
| GPU 输出数据 | 47 | – | – |
| Learning（replanning） | 213 | 1149 | 5.39× |
| **合计** | **451** | **10232** | **22.69×** |

- 原文："GEMSim's mobility simulation runs 100 times faster than MATSim's QSim model … in total the whole simulation loop of GEMSim is more than 22 times faster"。
- **加速后的瓶颈**：GEMSim 每轮 451 s 中，learning 占 213 s（**约 47%**），数据准备占 100 s（约 22%），mobsim 只占 90 s（约 20%）。原文："the implementation of a GPU-accelerated traffic propagation model itself does not necessarily mean an overall speeding-up of the same level"；还提到 MATSim 开发者早期的 GPU 尝试，收益被 GPU 与其余代码之间的数据传输吃掉了。
- **与期刊版 68 倍的关系**：期刊摘要的 68 倍是更早的基准（硬件较低端，每人 2 个方案，预热 5 轮）。博士论文解释，新基准中 MATSim 更慢，是因为更多迭代后交通更顺、事件更多。所以 **68×（期刊）和 100×（论文）都是 mobsim 对比，只是测试条件不同**。
- **规模扩展**（§2.4.4，Fig. 2.19）：大样本时 mobsim 加速在 **80–100 倍**之间，约 200 万 agent 后趋于饱和；主机内存约为 MATSim 的 **1/5**。单块 GPU 可以跑 4000–4500 万个 agent。
- **另一组对比**（§2.8，众核 CPU 与 GPU 后端，与 MATSim 同一硬件）：MATSim 每轮 99.2 min（交通 87.5 + 学习 11.7）；GEMSim CPU 后端交通快 11.64 倍、整轮快 7.62 倍；GPU 后端（V100/A100）交通快 45.26 倍、**整轮快 15.84 倍**。
- **能耗**：100 轮的耗电，MATSim 约 140 kWh，GEMSim GPU 约 7.5 kWh。结论章还给出两个数字：GPU 后端比 CPU 后端省电约 2.76 倍；但云上 GPU 实例贵 6 倍以上，而 CPU 后端只慢约 4 倍，所以 CPU 后端在云上可能更划算。
- **多模式**（ch.3）：
  - 加入公交后，加速是 **27–31 倍**，约 100 万 agent 后饱和。
  - 10 万辆出租车的车队：整轮比 MATSim 快最多 **9 倍**（<30 min 对 3.5 h），交通部分最多快 50 倍。MATSim 带出租车时 QSim 只能单线程跑。
  - 车队调度放在 CPU 上，GPU 与 CPU 之间周期性同步。
- **结论章（ch.8）对瓶颈的总结**："the learning part becomes the largest runtime performance bottleneck contributing about 40% of iteration runtime at a large scale"。数据传输是第三个瓶颈：10% 样本时传输占 8%、交通 61%；全样本时传输 17%、交通 43%。
- **文献里的同类结果**（ch.1–2）：
  - Strippgen & Nagel 2009 的 CUDA mobsim 快 5.5–67 倍，但**接入 MATSim 后收益没有保住**。
  - Wang & Shen 整个循环快约 105 倍，但只在小网络上。
  - MANTA 比 JDEQSim 快 43%。
- 代价：需要重写仿真器，GPU 显存限制规模；与 MATSim 生态（扩展、配置）不兼容；数据准备比 MATSim 慢。

## 5. 怎么证明结果没变
- 博士论文用瑞士交通计数验证（137 个计数点，§2.3；后续场景 291 个）。
- 收敛：比较早晚高峰在相邻迭代之间的 link 流量差（§2.4.2，Fig. 2.16），以及平均得分。
- 降采样研究（ch.6）中，标定一套 k_l/k_f 系数要跑 1,221 组 × 5 = 6,105 次仿真。作者提出了基于卡方检验的新相似度指标 Sα，并批评 GEH：GEH 在 5% 样本时就能通过，Sα 要早高峰 ≥30%、午间 60%、晚高峰 40% 的样本才显著一致。
- 慕尼黑场景（ch.5）跑 400 轮：10% re-routing 加 10% 换方式，第 350 轮停止创新。期间得分会下跌，原因是非最优的方式选择。
- 期刊与博士论文都没有在同一场景上做 GEMSim 与 MATSim 的**均衡结果逐项对比**（至少博士论文第 2 章没有），对比的只是运行时间。【推断】所以"换成 GEMSim 后均衡是否一样"没有直接证据，这与 Hermes 承认结果"comparable, but not similar"的情况相似。

## 6. 假设
排队型交通流模型（与 QSim 同类）；加速只针对单次运行内的计算，不涉及均衡算法本身。

## 7. 能否用于 MATSim？怎么用
**🟡 作为"每步计算上限"的参考，不能直接插入 MATSim：**
- 【推断】对 RQ1 次问题的回答，有了 MATSim 的直接对比数字：**mobsim 快 68–100 倍，但整个循环只快约 16–23 倍**；加速之后，replanning 和数据准备占了每轮约 70% 的时间。这是"mobsim 加速后瓶颈转向 replanning"最有力的定量证据（Hermes 是第二条证据，[02](02_Graur2021_Hermes.md)），直接支持我们把主攻方向放在"减少无效创新和迭代数"上，两者正交、可以叠加。
- 【推断】有意思的旁证（§2.4.2，Fig. 2.16）：GEMSim 的瑞士场景也是**在第 80 轮停止创新**，之后相邻迭代 link 流量差的标准差下降为约 1/4。这与我们观察到的"关掉创新后几轮内就稳定"一致。
- 【推断】**Fig. 6.1 直接相关**：样本越大，收敛需要的迭代越多。<10% 样本几轮就收敛，20 轮后改善很小，所以降采样实验统一用 20+5 轮。这说明"迭代数"本身依赖规模；我们在小样本上测的收敛轮数，不能直接外推到全样本。
- 【推断】**降采样会改变均衡**（ch.6）：k_f* 约等于样本比例，k_l* 不稳定。对车队场景，作者发现全样本的均衡"relatively fragile"，全样本的最长等待时间比各降采样场景晚约 3 小时，而只降到 90% 样本，等待高峰就会提前到降采样场景的时间；换 3 组不同的样本重复，结果一样。这是"加速手段（降采样）会移动均衡"的又一实证，支持我们用多种子 + pooled R̂ 检验新方法是否落在同一均衡。
- 【推断】gridlock 的"前期粗、后期细"混合策略与我们的 two-stage / multi-fidelity 思路同构：早期迭代用便宜但近似的处理，接近收敛时换成精细处理。
- 降采样对聚合指标影响小：5–10% 样本的 VKT/VHT 误差在 2–6%；但 VHT 在小样本时误差可达 7–30%，VKT 一直不超过 6%。
- 博士论文摘要另一个发现，可以借给 [05](05_BenDor2021_population_downscaling.md) 的讨论：含 car 与公交的场景**至少需要 30% 样本**才能准确复现分解层面的输出；有需求响应车队时需要 100%。

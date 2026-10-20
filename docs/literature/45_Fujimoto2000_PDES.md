# [45] Fujimoto 2000 — Parallel and Distributed Simulation Systems

- **Venue**: Wiley（专著，ISBN 0-471-18383-0）
- **Domain / Tier / Priority**: GPU & parallel simulation / 3 / Low（参考书）
- **Link**: https://catalogimages.wiley.com/images/db/pdf/0471183830.pdf
- **依据**: ⚠️ **只读到书的前置部分**：表中链接是 Wiley 提供的样章 PDF（10 页），内容是版权页、**完整目录**和**序言**，**没有正文**。下文只引用目录和序言里能核实的内容。旧版笔记中关于各算法细节的表述属于领域常识，**没有用本书正文核对**，已标出。

> 一句话（序言）：系统论述离散事件仿真在多处理器平台上的执行。第二部分讲并行/分布式执行，目的是"use multiple processors to speed up the execution"，核心是保证并行执行"yields the same results as a sequential execution"的**同步算法**：**保守同步**（第 3 章）和**乐观同步**（第 4–5 章，Time Warp），以及只适用于特定问题、但"can yield dramatic performance improvements"的**时间并行仿真**（第 6 章）。第三部分讲分布式虚拟环境（DIS、HLA）。

## 目录中与我们相关的部分（已核实）
- §2.3 时间推进机制：**time-stepped execution**（§2.3.1）vs **event-driven execution**（§2.3.2）。
- 第 3 章 保守同步：null message 避免死锁（§3.2）、**lookahead 与仿真模型**（§3.3）、同步执行与 barrier（§3.5）、bounded lag（§3.6）、**可重复性与同时事件**（§3.9）、保守机制的性能与评述（§3.10–3.11）。
- 第 4–5 章 Time Warp：回滚、GVT、状态保存、内存管理、乐观与保守的比较（§5.6）。
- 第 6 章 时间并行仿真。
- §1.4.7 应用：Transportation。

## 1–6. 七问
专著，没有单一的实验，第 1–5 问不适用。从序言能确认的假设是：并行化的目标是**与顺序执行结果相同**（可重复性），而不是近似。

## 7. 能否用于 MATSim？怎么用
**🟡 用于理解 RQ1 次问题（为什么 16 核只用了约 3.8 核），不是主攻方向：**
- 【推断】MATSim 的 QSim 是 **time-stepped**（1 s 步长）+ 空间分区的多线程（MATSim 书 Ch.40：24 h 若 120 s 算完，即每秒 720 次线程间交互，[03](03_Horni2016_MATSim_book.md)），对应本书 §2.3.1 和 §3.5 的同步执行/barrier 范式；Hermes 则是 **event-driven**（§2.3.2，见 [02](02_Graur2021_Hermes.md)）。
- 【推断】低利用率的可能原因（待用 profiling 验证）：每个时间步工作量小、barrier 开销占主导；高峰时少数区域拥堵造成负载不均；事件处理（EventsManager）是串行瓶颈（Hermes 论文指出事件分发占大部分时间）。外部证据：MATSim 书 Table 40.1 显示 6–8 线程后饱和；Ben-Dor 2021 发现 2–11 核表现相近，12 核反而变慢（[05](05_BenDor2021_population_downscaling.md)）。
- 【推断】交通天然的 lookahead 是 link 的最短通过时间，可以支持保守 PDES（§3.3）。这属于领域常识，未用本书正文核实。
- 定位：并行能改善每步计算，但受同步开销和 Amdahl 定律限制。空闲核更直接的用法是**并行跑多个种子或副本**，服务于验证（[25](25_Vehtari2021_improved_Rhat.md)）或探索（[26](26_Earl2005_parallel_tempering.md)）。
- **待办**：若要在论文中讨论并行同步，需要借阅本书第 2–3 章。

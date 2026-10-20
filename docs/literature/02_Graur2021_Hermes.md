# [02] Graur, Bruno, Bischoff et al. 2021 — Hermes: Enabling efficient large-scale simulation in MATSim

- **Venue**: Procedia Computer Science 184 (ABMTRANS 2021)
- **Domain / Tier / Priority**: MATSim & agent-based traffic sim / 1 / **Read first**
- **Link**: https://www.dpss.inesc-id.pt/~rbruno/papers/dgraur-abmtrans21.pdf
- **依据**: ✅ 已读全文（2026-10-15）

> 一句话：用事件驱动、单线程、数据结构高度精简的新 mobsim 替代 QSim。每轮 mobsim 快 2.5–3 倍，之后 replanning 成为新的瓶颈。

## 1. 瓶颈
**每轮 mobsim 的计算（QSim）**。QSim 每个时间步都处理所有有车的 link，不管车是否准备好移动。Fig. 1：10% 瑞士场景，**线程数超过 8 后每轮时间不再下降**（和我们"16 核只用 3.8 个"的现象一致）。SBB 估计 100% 人口要跑几周。

## 2. 手段
- 事件驱动：只在 agent 真正需要动作时处理。
- 加载方案时预先计算事件结构，用更紧凑的数组和数据布局，内存占用更小。
- 单线程：作者判断瓶颈是内存而不是 CPU，多线程收益有限。
- 只保留核心功能，不支持 within-day replanning、信号灯、动态车辆调度等扩展。

## 3. 省在哪一项
**每步计算**（只加速 mobsim，不改迭代数）。

## 4. 快了多少，代价是什么
- SBB 10% 瑞士（AWS r5.8xlarge，32 vCPU）：单轮 **12:09 → 4:52 min（约 2.5×）**；301 轮 **83 h → 47 h（总时间减少约 43%）**。总时间只减 43%，是因为 replanning 等其他环节没变（Amdahl 定律）。
- Open Berlin 1%，10 轮：仿真时间减少 **70%**。Hermes 核心本身只占一小部分，剩下主要是 MATSim 的事件分发（EventsManager）。
- **代价**：
  - 结果"comparable, but not similar"：QSim 的 car 份额略高，大城市周边高速公路流量也有差异。作者认为原因是两者对 10% 降采样的 flow/storage capacity 处理不同。**需要小幅重新标定**。
  - 扩展功能缺失。
  - 作者结论：用 Hermes 后 **replanning 主导运行时间**。

## 5. 怎么证明结果没变
- 比较 mode share 表（如 car 44.69% vs 45.15%）。
- 比较高速公路日流量差异图。
- agent 级别出行时间偏差（"travel time skew"）：大部分在 10% 以内。
- 没有多种子、没有统计检验，只说"非常相似"。

## 6. 假设
- 与均衡理论无关，是纯工程替换。假设 mobsim 的细节差异（排队、PT 站停靠处理）对研究问题影响不大。
- 前提是不需要那些未实现的扩展。

## 7. 能否用于 MATSim？怎么用
**✅ 直接可用**（MATSim 主干已集成，`controller.mobsim = hermes`）。
- 作为 **RQ1 次问题的"每步计算上限"baseline**：我们 mobsim 占约 78%。如果 Hermes 把这部分降到约 35–40%，单轮时间约变为 0.22 + 0.78×0.4 ≈ 0.53，**单轮约快 1.9 倍**。然后瓶颈转到 replanning 和事件处理，这**正好说明减少无效创新（减少 replanning 和路由开销）更重要**，可以作为我们研究动机的论据。
- 注意：换 mobsim 会改变均衡（需重新标定）。所以和我们的方法比较时，**两边必须用同一个 mobsim**，否则混淆。
- 它的验证方式（mode share + 路段流量差 + agent 级出行时间差）可以直接借给 RQ2 当最低标准，但我们应补上多种子。

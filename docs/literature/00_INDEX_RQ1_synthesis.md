# RQ1 读书笔记总览与综合结论（按原文重新核对版，2026-10-16）

> RQ1：其他领域遇到"仿真太贵"时用过哪些加速手段？哪些能搬到 MATSim 这类随机、agent-based 的均衡仿真上？
>
> 我们的背景数据：关掉创新后几轮内就稳定 → 时间主要花在前 80 轮探索，其中约 85% 的试探方案无效；每轮约 78% 的时间在 mobsim，只用了约 3.8/16 核。

## 核对状态

每篇笔记开头的"依据"一行写明了实际读过的原文、使用的链接；表中链接失效或付费时，写明了替代来源。正文中标【推断】的是我们自己的映射或建议，不是原文结论。

| 状态 | 篇目 |
|---|---|
| ✅ 全文已读（正文全部；只跳过参考文献或讨论稿） | 01, 02, 04, 05, 07, 11, 12, 14, 15, 18–23, 25–27, 29, 31–33, 35, 36, 38–41, 43, 44, **42 GEMSim（博士论文 ch.1–8 + 附录全读；期刊版付费）**, **46 PSim（投稿版全文 + TRR 正式摘要）**, 47–60 |
| ✅ 正文全读，但长篇的参考文献 / 附录 / 讨论没读 | 24（讨论 pp. 473–511 未读）, 28（pp. 1–44 正文全读）, 34（pp. 1–32）, 37（pp. 483–521） |
| ✅ 书：与 RQ1 相关的章节逐章读完 | 03 MATSim 书（Ch.1、3、4、11、32、39、40、43、46–49、97）, 06 Sheffi（Ch.5.1–5.2、Ch.12 全章） |
| ✅ 全文已读（用户通过图书馆下载，2026-10-19；PDF 存于 [pdf/](pdf/)） | **08 Sbayti 2007**, **09 Lu 2009**, **10 Cascetta 1989**, **16 Popovici 2012**（整本手册中的第 31 章） |
| ⚠️ 只核对了官方摘要（付费，用户决定不再找） | 13 Jin 2011, 30 Khatiwala 2008 |
| ⚠️ 只有目录和序言（专著，用户决定不再找） | 17 Fudenberg & Levine（作者网站目录）, 45 Fujimoto（Wiley 样章） |

**表中链接的问题**：
- 12 Jin 2005 的链接已失效（404），改用 Internet Archive 快照；
- 15 CMA-ES 的 Harvard 链接返回 HTML，改用作者主页版本；
- 22、24 的 Project Euclid 返回 403，改用公开副本（24 是扫描件，经 OCR）；
- 37、38 的 MIT DSpace 返回空页，改用 UT Austin 副本；
- 03、06、07 的表中链接只是书目页，全文另找；
- 42 GEMSim 的表中链接是博士论文页面；PDF 曾被限流，2026-10-16 重试后下载成功并已读。

## 第三轮全文补读的新发现（2026-10-19）

- **MATSim 书 §97.2 把我们的问题列为开放问题**：用快速近似加速均衡搜索，要研究 "a) if the approach is indeed faster and b) if the resulting set of plans is unbiased by the fast initialization"。可直接作为动机引文（[03](03_Horni2016_MATSim_book.md)）。
- **Planomat 的失败（书 Ch.43）**：基于自建简化 mobsim 的最优回应模块，因为与核心 mobsim 的评估逐渐分离而被放弃。这是 two-stage / 低保真筛选必须正面回应的反例（[03](03_Horni2016_MATSim_book.md)）。
- **§49.2.2 的 MH 修正**：只接受被筛选过的创新会改变平稳分布，书中给出了 Metropolis–Hastings 接受概率作修正（[03](03_Horni2016_MATSim_book.md)）。
- **书 §4.2.3**："fewer threads are almost always better in terms of throughput"；建议同时跑多次低线程仿真。这支持"用空闲核跑多种子"的做法；§4.2.4 说明默认种子是固定的，必须显式修改。
- **Sheffi §12.3**：MSA 外迭代配 1 次内迭代最好（20–40 次 all-or-nothing），配 20 次反而要 80–100 次。PSim 式内循环的次数值得做敏感性实验（[06](06_Sheffi1985_Urban_Transportation_Networks.md)）。
- **GEMSim 博士论文 ch.6**：大样本需要更多迭代；全样本车队场景的均衡 "relatively fragile"，降到 90% 样本就让晚高峰移动。还提出了 push-through 加 squeeze 的"前粗后细"gridlock 策略（[42](42_Saprykin2019_GEMSim.md)）。
- **Auld 2019（POLARIS）**：个体 gap 换路 + 1/n 式信息混合，迭代数 7 → 2，但没检验均衡分布（[51](51_Verbas2024_POLARIS_gap_based.md)）。

## 重新核对后的重要更正（相对第一版笔记）

1. **[42] GEMSim**（已读博士论文全文）：期刊版（2019）摘要说 mobsim 比 MATSim **快 68 倍**；博士论文 Table 2.2 用新硬件重测：mobsim **100.6×**，但**整个循环只快 22.7×**（451 s vs 10232 s）。加速后 replanning 占 GEMSim 每轮时间的约 47%。
2. **[05] Ben-Dor**：案例是 **Sioux Falls**，不是 Tel Aviv；文中直接观察到 MATSim **"从一个 UE 转到另一个 UE"**，以及 **3/100 次运行收敛到不同的 UE**。
3. **[18] Hofbauer & Sandholm**：势博弈中 SFP 收敛到**某个**线性稳定的静止点（势函数局部极大），**不保证唯一**。第一版写"唯一"是错的。
4. **[39] GNS**：原文附录显示推理时间与原仿真器**相当**（51%–345%），作者说加速不是本文目标。第一版暗示可以提速，有误导。
5. **[12] Jin 2005**：综述**没有**给"节省 50–90%"这类数字，第一版编造了这个数，已删除。
6. **[08] Sbayti 2007**（已读全文）：排序标准是**同一 (o, d, τ) 组内经历的出行时间**，组内等价于按 gap 排序；"gap 降到 5% 以下"原文确有（Fort Worth 和 Knoxville），已恢复。排序法**不减少迭代次数**，收益在解的质量（70,000 辆时 UE gap 3.90% vs 随机选择 19.16%）。正文与 Table 1 的需求水平不一致（35k/50k vs 23k/45k）。
7. **[41] Kochkov**：arXiv 版与 PNAS 版**摘要**的加速数字相同（40–80 倍）。
8. **[09] Lu 2009**（已读全文）：换出量 ∝ **相对**成本差 (c−c*)/c；L_max = 1 时与 MSA 表现相近，收益主要来自"先在现有路径集内均衡好再加新路径"。
9. **[10] Cascetta 1989**（已读全文）：唯一平稳分布的充分条件之一是**所有可行方案的选择概率严格为正**；多重均衡时长期平均落在均衡之间（两路例子：SUE 3.60 / 9.50，STODYN 平均 8.81）。

---

## 文件列表

| # | 文件 | 省在哪 | 能否用于 MATSim | 核对 |
|---|---|---|---|---|
| 01 | [Zhuge 2021 选择性 replan + 变步长](01_Zhuge2021_MATSim_computing_time.md) | 迭代次数 + 每步计算 | ✅ 必须对比的 baseline | 全文 |
| 02 | [Hermes 2021](02_Graur2021_Hermes.md) | 每步计算 | ✅ 上限参考 | 全文 |
| 03 | [MATSim 书（PSim、Monte-Carlo 引擎）](03_Horni2016_MATSim_book.md) | 每步计算 / 迭代次数 | ✅ PSim 必须对比 | 相关章节全读（13 章） |
| 04 | [Nagel & Flötteröd 2009](04_Nagel2009_agent_based_traffic_assignment.md) | 理论 | ✅ 均衡定义 + novelty | 全文 |
| 05 | [Ben-Dor 2021 降采样](05_BenDor2021_population_downscaling.md) | 问题规模 | ✅ 验证模板 | 全文 |
| 06 | [Sheffi 1985 MSA](06_Sheffi1985_Urban_Transportation_Networks.md) | 迭代次数 | 🟡 步长 + 收敛判据警告 | 相关章节全读（Ch.5.1–5.2、12） |
| 07 | [Peeta 2001 DTA 综述](07_Peeta2001_DTA_foundations.md) | 综述 | 🟡 定位 | 全文 |
| 08 | [Sbayti 2007 按出行时间排序选人](08_Sbayti2007_efficient_MSA_SBDTA.md) | 解的质量（不省迭代） | ✅ novelty 威胁 | ✅ 全文 |
| 09 | [Lu 2009 gap 函数](09_Lu2009_gap_function_DUE.md) | 迭代次数 | 🟡 gap 指标 | ✅ 全文 |
| 10 | [Cascetta 1989](10_Cascetta1989_stochastic_process_dynamics.md) | 理论 | ✅ 平稳分布框架 | ✅ 全文 |
| 11 | [Watling & Hazelton 2003](11_Watling2003_day_to_day_dynamics.md) | 理论 | ✅ 多重均衡警示 | 全文 |
| 12 | [Jin 2005 适应度近似](12_Jin2005_fitness_approximation_survey.md) | 评估次数 | 🟡 **重点** | 全文 |
| 13 | [Jin 2011](13_Jin2011_surrogate_assisted_EC.md) | 评估次数 | 🟡 | ⚠️ 摘要 |
| 14 | [Eiben 1999 参数控制](14_Eiben1999_parameter_control.md) | 迭代次数 | ✅ **重点** | 全文 |
| 15 | [CMA-ES 2001](15_Hansen2001_CMA-ES.md) | 评估次数 | 🟡 样本不够 | 关键章节 |
| 16 | [共同演化原理](16_Popovici2012_coevolutionary_principles.md) | 诊断 | 🟡 | ✅ 全文 |
| 17 | [Fudenberg & Levine](17_Fudenberg1998_learning_in_games.md) | 理论 | 🟡 | ⚠️ 目录 |
| 18 | [Hofbauer & Sandholm 2002](18_Hofbauer2002_stochastic_fictitious_play.md) | 理论 | 🟡 收敛但不唯一 | 全文 |
| 19 | [Mertikopoulos 2018](19_Mertikopoulos2018_cycles_regularized_learning.md) | 理论 | ❌（警示） | 全文 |
| 20 | [Optimistic GAN](20_Daskalakis2018_optimistic_GAN.md) | 迭代次数 | 🟡 外推出行时间 | 全文 |
| 21 | [Syrgkanis 2015](21_Syrgkanis2015_fast_convergence_regularized_learning.md) | 迭代次数 | 🟡 低优先级 | 全文 |
| 22 | [Roberts 1997 0.234](22_Roberts1997_optimal_scaling_RWM.md) | 迭代次数 | 🟡 启发 | 全文 |
| 23 | [自适应 MCMC](23_Andrieu2008_adaptive_MCMC.md) | 迭代次数 | 🟡 **自适应的框架和风险** | 全文 |
| 24 | [Gelman & Rubin R̂](24_Gelman1992_Rhat.md) | 诊断 | ✅ RQ2/3 | 全文（OCR） |
| 25 | [改进 R̂](25_Vehtari2021_improved_Rhat.md) | 诊断 | ✅ RQ3 用这个 | 关键章节 |
| 26 | [Parallel tempering](26_Earl2005_parallel_tempering.md) | 迭代次数 | 🟡 利用空闲核 | 关键章节 |
| 27 | [Metadynamics](27_Laio2002_metadynamics.md) | 迭代次数 | 🟡 禁忌/去重 | 全文 |
| 28 | [增强采样综述](28_Henin2022_enhanced_sampling_survey.md) | 综述 | 🟡 验证范式 | 正文全读 |
| 29 | [Khatiwala 2024 AA](29_Khatiwala2024_spinup_sequence_acceleration.md) | 迭代次数 | 🟡 **去噪热启动 + 快慢分离** | 全文 |
| 30 | [Khatiwala 2008 NK](30_Khatiwala2008_Newton-Krylov_spinup.md) | 迭代次数 | ❌ | ⚠️ 摘要 |
| 31 | [Lamperti ML surrogate](31_Lamperti2018_ABM_ML_surrogate.md) | 运行次数 | 🟡 创新分类器 | 全文（WP） |
| 32 | [Grazzini 贝叶斯 ABM](32_Grazzini2017_Bayesian_ABM_estimation.md) | 运行次数 | 🟡 平稳/遍历检验 | 关键章节 |
| 33 | [Platt 标定比较](33_Platt2020_ABM_calibration_comparison.md) | 运行次数 | ❌ | 关键章节 |
| 34 | [多保真度综述](34_Peherstorfer2018_multifidelity_survey.md) | HF 评估次数 | 🟡 **统一框架（两阶段 MCMC）** | 正文全读 |
| 35 | [Kennedy & O'Hagan](35_Kennedy2001_Bayesian_calibration.md) | 运行次数 | ❌ | 关键章节（OCR） |
| 36 | [Giles MLMC](36_Giles2008_MLMC.md) | 运行次数 × 每步 | ❌ | 关键章节 |
| 37 | [投影降阶综述](37_Benner2015_projection_MOR_survey.md) | 每步计算 | ❌ | 正文全读 |
| 38 | [Operator inference](38_Peherstorfer2016_operator_inference.md) | 每步计算 | 🟡 推测性 | 关键章节 |
| 39 | [GNS](39_SanchezGonzalez2020_GNS.md) | （不是加速） | 🟡 远期 | 全文 |
| 40 | [FNO](40_Li2021_Fourier_neural_operator.md) | 每步计算 | ❌ | 关键章节 |
| 41 | [ML-CFD](41_Kochkov2021_ML_accelerated_CFD.md) | 每步计算 | ❌（思路可借） | arXiv + PNAS 全文 |
| 42 | [GEMSim](42_Saprykin2019_GEMSim.md) | 每步计算 | 🟡 上限参考 | 博士论文全文（ch.1–8） |
| 43 | [LPSim](43_Jiang2024_LPSim.md) | 每步计算 | ❌（上限参考） | 关键章节 |
| 44 | [MOSS GPU 模拟器](44_Zhang2024_GPU_simulator_benchmark.md) | 每步计算 | 🟡 轻量平台 | v1 + v2 全文 |
| 45 | [Fujimoto PDES](45_Fujimoto2000_PDES.md) | 每步计算 | 🟡 解释核利用率 | ⚠️ 目录 |
| **46** | [**PSim（Fourie et al. 2013）**](46_Fourie2013_PSim.md) | QSim 迭代次数 | ✅ **最接近的强 baseline** | 全文（投稿版） |

---

## 产出 1：加速手段地图（省在哪 × 代价），数字均出自原文

| 省在哪 | 手段家族 | 代表与原文数字 | 主要代价 |
|---|---|---|---|
| **迭代次数（主问题）** | 只让"差"的人动 | Zhuge 2021：154 → 69 轮，1187 s → 549 s；Sbayti 2007（同组内按出行时间排序、最差的 1/k 换路；拥堵时 gap 远小于随机选人，但不减少迭代次数；POLARIS 采用其后续 gap-based 方法）；Nagel & Flötteröd 2009：切换概率 ∝ 改进幅度 | 可能停在更差的均衡；Zhuge 的收敛判据有内生性 |
| | 自适应探索强度 | Eiben 1999（1/5 规则）；Andrieu & Thoms 2008（Robbins–Monro，vanishing adaptation）；CMA-ES（病态问题上快几个数量级，但要 10n–100n² 次评估才能适应） | 自身超参数；可能调到"坏值"；每个 agent 样本太少 |
| | Surrogate / 多保真度过滤 | **PSim：达到同一得分所需 QSim 轮数 101 → 13–20，16 核墙钟时间减半以上，但 mode share 与 link 流量偏移**；两阶段 delayed-acceptance MCMC（拒绝率越高，省得越多）；Lamperti（surrogate 预测快 500–3750 倍）；Jin 2005（警告：假最优） | surrogate 偏差；需要 evolution control |
| | 序列外推 | Khatiwala 2024 AA：季节性强迫约 12 倍，年际（有噪声）强迫 5 倍；Newton–Krylov 约 100 倍，但只适用于简单模型 | **噪声大时 AA 停滞**，需要去噪热启动或快慢分离 |
| | 增强探索 | Parallel tempering（> 1/M 倍效率）；metadynamics（效率随维数指数下降） | 并行资源；需要能量函数或集体变量 |
| | 学习规则改进 | Optimistic Hedge（遗憾 O(T^{−3/4})，但福利没有显著改进）；OMD（双线性零和博弈中末轮收敛） | 需要全信息反馈或梯度 |
| **每步计算（次问题）** | 更快的 CPU mobsim | Hermes：单轮 12:09 → 4:52 min；301 轮总时间 −43% | 结果"comparable, but not similar"，需要小幅重新标定 |
| | GPU | GEMSim：mobsim 比 MATSim **快 68×（期刊）/ 100.6×（博士论文）**，整个循环只快 **22.7×**，加速后 replanning 占每轮约 47%；LPSim：113 倍；MOSS：比 CityFlow 快 89 倍 | 重写，生态不兼容；循环加速远小于 mobsim 加速 |
| | 粗化 | Zhuge 变步长：每轮 7.71 s → 2.83 s；Kochkov：40–80 倍 | 精度变化；Kochkov 需要可微求解器 |
| | 学到的模拟器 / 降阶 | FNO：0.005 s vs 2.2 s（另需 12 h 训练）；投影降阶 28–30,000 倍；GNS：**不比原仿真器快** | 训练数据；需要规则网格或控制方程 |
| | 并行同步 | MATSim 书：6–8 线程后饱和；Ben-Dor：约 11 核以上无收益 | 同步/通信开销 |
| **问题规模** | 降采样 | Ben-Dor：k ≥ 25% 才安全，每轮时间 k=1 只是 k=0.1 的约 3 倍；GEMSim 博士论文：car + PT 需 ≥ 30% | 小 k 偏差大，多次重复反而更费时 |
| **运行次数** | 标定 surrogate | Lamperti、Kennedy–O'Hagan、MLMC（O(ε⁻³) → O(ε⁻²(log ε)²)） | 与单次运行加速无关 |
| **诊断** | R̂ / ESS / gap / 平稳性检验 | Vehtari：R̂ < 1.01、ESS > 400、≥ 4 条链；Grazzini：Runs test 定 burn-in；Sheffi：变化量判据会误导 | 需要多种子 |

**观察**：
- 对"慢在到达稳态"的问题，有效手段集中在三类：(1) 减少无效的提议或评估（surrogate、两阶段过滤、自适应提议）；(2) 外推（AA、乐观）；(3) 只更新离均衡远的部分（gap 选人）。
- 每步计算的加速有硬件上限，而且两篇独立文献（Hermes、GEMSim）都发现加速后**瓶颈转移到 replanning**。

---

## 产出 2：能否用于 MATSim（按假设筛选）

关键筛选条件：**MATSim 是随机的、方案离散、没有梯度、有多重均衡的直接证据（Ben-Dor 2021），适应度非平稳（取决于其他 agent）。**

| 判定 | 手段 | 被筛掉或需要改造的原因 |
|---|---|---|
| ✅ 直接可用 | Hermes；gap 选人（Sbayti/Zhuge）；自适应创新率（Eiben 1/5、按策略统计成功率）；R̂/ESS；PSim；Ben-Dor 式的验证框架 | 不依赖确定性或梯度 |
| 🟡 需要改造 | surrogate / 两阶段过滤（要做模型管理，模型要在线更新）；AA（只能作用在连续的出行时间场上，并且要**去噪热启动**）；乐观外推；CMA（样本不够，只能池化）；禁忌（偏置只能用在生成环节）；并行副本；Optimistic Hedge | 随机、离散、非平稳 |
| ❌ 不适用 | Newton–Krylov；投影降阶；FNO；MLMC；Kochkov 端到端训练；Kennedy–O'Hagan（对单次运行） | 需要确定性、光滑/梯度、控制方程、规则网格或层间耦合 |

---

## 产出 3：一页结论

### Q1. 其他领域有没有人解决过"随机系统、慢在探索、多重均衡"这类问题？

有，但没有一个领域同时具备这三个特征：
- **随机 + 慢在探索**：MCMC 和分子动力学。手段是自适应提议（Andrieu & Thoms：必须"递减适应"，否则会丢失目标分布）、副本交换、历史偏置。共同原则是**偏置只用于探索或提议，最终统计不偏**（Hénin 2022 只收录能恢复平衡统计的方法）。
- **慢在探索 + 评估贵**：进化计算与多保真度。手段是 surrogate 预筛选 + 模型管理（Jin 2005），以及两阶段 delayed-acceptance（Peherstorfer 2018）：**拒绝率越高，省得越多**，而我们的创新无效率约 85%。
- **慢在到达稳态**：气候 spin-up，用 AA（Khatiwala 2024）。**在噪声大时，作者自己改用"先在去噪问题上做 AA 热启动，再常规积分"，仍有 5 倍加速**。这是目前唯一一个在随机条件下仍然有效的外推证据。
- **多重均衡**：交通理论（Watling & Hazelton 2003：长记忆时单次模拟可能永远停在初值附近的峰；Hofbauer & Sandholm 2002：势博弈中收敛但不唯一）和 MATSim 实证（Ben-Dor 2021：3/100 次运行落在不同 UE）。这些文献只给出了**定义和警示**，没有给出加速方法。
- **空白**：没有人在"随机 + 共同演化 + 策略集在探索中扩展"的系统上，系统地减少无效创新，**同时**用多种子分布检验没有落到更差的均衡。

### Q2. Zhuge 2021 已经做了"只让低分 agent 去 replan"，我们的区别在哪？

1. **"按差距决定谁动"有更早的先例**：
   - Nagel & Flötteröd 2009 提出切换概率 ∝ 改进幅度；
   - Sbayti 2007 在 DTA 中按 gap 选人换路，后来被 POLARIS 采用；
   - PSim（[46](46_Fourie2013_PSim.md)，Fourie et al. 2013）已经在用 surrogate 评估创新。
   
   所以"选谁 replan"不能作为核心新意。

   **PSim 是最强的对手**（已读原文）：苏黎世 6.7 万 agent 场景，达到同一平均得分所需的 QSim 轮数从 101 降到 13–20，16 核墙钟时间减少一半以上。但它有三个缺口，正是我们可以切入的地方：
   - **让无效创新变便宜，而不是变少**：PSim 中的变异仍是随机的，只是在伪仿真里多试几次；我们针对的是"生成什么、给谁生成"，两者正交。
   - **均衡有可见偏移**：car 份额从 80.7% 降到 76.2%；日 link 流量 RMSD 是"只换种子"差异的 4–5 倍（24.5–30.0 vs 5.7）。作者自己说"utility on its own is not a complete indication"。【推断】两阶段过滤（LF 只做过滤，保留与否由 HF 执行结果决定）理论上可以避免这种 surrogate 偏差，这是可以实验检验的区别。
   - **验证弱**：多模型运行只用一个种子，加一个换种子的参照；比较点是"得分达到 175.4 的那一轮"，不是稳态。
2. **Zhuge 筛的是"人"，我们筛的是"创新"**：被选中的人仍然随机生成创新，85% 的无效率问题依旧存在。我们针对的是"生成什么创新、哪些值得执行"，两者正交、可以叠加。
3. **Zhuge 的验证有硬伤**：
   - 单种子；只用 12 个计数点、早高峰 2 小时的 MAPE；
   - 收敛判据（平均得分变化 < 0.001）与方法**内生相关**。Sheffi 1985 早就警告，步长或更新量递减的算法中，这类"变化量"判据会误导；
   - 没有检验是否停在更差的均衡。

   我们用多种子 + R̂/ESS（Vehtari 2021）+ 与方法无关的 gap + Ben-Dor 式的偏差与离群检测，可以直接回答"均衡有没有变"。
4. **可以补上的空白**：Nagel & Flötteröd 2009 写道，作者"not aware of any operational gap function that applies to all-day plans"。一个可计算的全日计划 gap（用 router 或 PSim 在本轮出行时间下估计最优回应），既能做收敛判据，又能指导创新，是有文献支撑的贡献点（需要再检索 2009 年之后是否已有人做）。

### Q3. 哪个手段最可能大幅缩短 80 轮的探索，同时不停在更差的均衡？

**最值得试的三个（按推荐顺序）：**

1. **两阶段（多保真度）创新过滤**（[34](34_Peherstorfer2018_multifidelity_survey.md) + [12](12_Jin2005_fitness_approximation_survey.md) + PSim [03](03_Horni2016_MATSim_book.md) + [31](31_Lamperti2018_ABM_ML_surrogate.md)）。每个创新先用便宜的评估（本轮出行时间下的得分，或学到的保留概率）过滤，只执行有希望的创新；保留一定比例的随机创新作为 evolution control（防止假最优）。理论原型是 delayed-acceptance MCMC；最终阶段仍是 QSim + 关掉创新，所以均衡定义不变。**与 PSim 的区别必须讲清楚**：PSim 整代交替使用伪仿真，新方案按伪仿真得分进入记忆，所以 surrogate 的偏差会直接进入选择，导致 mode share 偏移（[46](46_Fourie2013_PSim.md)）；我们按个体、按创新决定是否调用高保真，是否保留由高保真的执行结果决定。**实验中必须把 PSim 作为 baseline**，并比较 mode share 和 link 流量的偏移，而不只比较得分。PSim 原文还发现"低 replanning rate + 更多廉价迭代"更好，可以作为自适应控制的参照。
2. **自适应创新控制**（[14](14_Eiben1999_parameter_control.md) + [23](23_Andrieu2008_adaptive_MCMC.md)）。按策略类型或 subpopulation 统计成功率，用 Robbins–Monro 在线调整策略权重和变异幅度，并设下限防止调到坏值。只改创新的生成，不改得分（Eiben 的"cheat"警告）。实现成本最低。
3. **按全日计划 gap 定向 replan**，作为 Zhuge 的改进版强 baseline（[04](04_Nagel2009_agent_based_traffic_assignment.md) + [08](08_Sbayti2007_efficient_MSA_SBDTA.md) + [09](09_Lu2009_gap_function_DUE.md)），同时作为 RQ3 的收敛指标。

**备选**：对出行时间场做 AA 或乐观外推（[29](29_Khatiwala2024_spinup_sequence_acceleration.md)、[20](20_Daskalakis2018_optimistic_GAN.md)）。必须照搬 Khatiwala 的"去噪热启动"和"快慢分离"改造，并用多种子检查是否换了吸引子。

**每步计算上限（次问题）**：
- Hermes 单轮约快 2.5 倍（按我们 78% 的 mobsim 占比估算，整轮约快 1.9 倍）；
- GPU mobsim 比 MATSim 快 68–100 倍，但整个循环只快约 22.7 倍；GEMSim 每轮 451 s 中 replanning 占 213 s（博士论文 Table 2.2）。

两条证据都说明，**mobsim 加速后瓶颈转向 replanning，这反而放大了减少无效创新的价值**。空闲的约 12 个核最好用来**并行跑 ≥ 4 个种子**（Vehtari：并行多链不增加墙钟时间），服务于验证。

### 给 RQ2/RQ3 的验证清单（全部来自已读原文）

- **参照**：原版 MATSim 多种子长运行（Khatiwala：长时间直接积分作参照；Ben-Dor：10 次全规模运行的均值和 CV）。
- **指标**：聚合 + 分解（Ben-Dor 的相对偏差 b，容差 CV/√k 的思想）；逐 link 散点图对 1:1 线（Khatiwala）；有物理意义的平衡指标，而不是残差或"得分变化很小"（Khatiwala、Sheffi）。
- **收敛**：rank-normalized split-R̂ + bulk/tail ESS，至少 4 条链（Vehtari）；burn-in 用平稳性检验确定（Grazzini 的 Runs test）；有自相关时，标准误不能按 σ/√N 算（Watling & Hazelton）。
- **均衡等价**：两种方法的链合并后计算 R̂；用 Tukey fence 检测落在不同 UE 的离群运行（Ben-Dor）；分布是否多峰（Watling & Hazelton）；比较时间平均而不只看末轮（Mertikopoulos）。
- **遍历性决定种子数**：非遍历意味着多重均衡，必须多种子（Grazzini 脚注 10）。

### 待办（核对过程中发现的缺口）

1. ~~通过图书馆获取全文~~：08、09、10、16 ✅ 已读全文（2026-10-19）；13 Jin 2011、17 Fudenberg & Levine、30 Khatiwala 2008、45 Fujimoto 用户决定不再找，保持只读摘要/目录。
2. ~~PSim 原文~~ ✅ 已读（[46](46_Fourie2013_PSim.md)）。PSim 的后续：2013 年后带公交仿真的版本、作者展望中"让 agent 在 PSim 中单独优化公交方案"是否已有人实现、当前 MATSim 版本里 pseudosimulation 模块的状态。
3. ~~POLARIS 中 gap-based 分配的实现文献~~ ✅ Auld et al. 2019 已读全文（见 [51](51_Verbas2024_POLARIS_gap_based.md)：同一 gap 水平，迭代数 7 → 2）；2009 年之后关于"全日计划 gap 函数"的文献。
4. ~~GEMSim 博士论文~~ ✅ 已读。

## 近期论文（2020–2026，第二轮补充）

每篇都已按原始链接读过，"核对"一列写明读到的程度；没读到正文的不放进来。

| # | 文件 | 领域 | 链接 | 核对 |
|---|---|---|---|---|
| 47 | [Laudan et al. 2025 分布式 QSim](47_Laudan2025_distributed_QSim.md) | 1 MATSim | [DOI](https://doi.org/10.3390/info16020116) | 全文（期刊版） |
| 48 | [Moukir et al. 2024 multiMATSim](48_Moukir2024_multiMATSim.md) | 1 MATSim | [PDF](https://www.scitepress.org/Papers/2024/124526/124526.pdf) | 全文 |
| 49 | [Natterer et al. 2025 GNN 代理](49_Natterer2025_GNN_surrogate_MATSim.md) | 1 MATSim / 11 | [DOI](https://doi.org/10.1016/j.trc.2025.105360) · [HAL](https://hal.science/hal-04999526v1) · [arXiv](https://arxiv.org/abs/2501.11057) | ✅ 期刊全文 + arXiv 全文 |
| 50 | [Ameli et al. 2020 DTA 收敛算法比较](50_Ameli2020_DTA_convergence_algorithms.md) | 2 DTA | [DOI](https://doi.org/10.1111/mice.12524) · [HAL](https://hal.science/hal-02380851v2) | 全文 |
| 51 | [Verbas et al. 2024 POLARIS](51_Verbas2024_POLARIS_gap_based.md) | 2 DTA | [arXiv](https://arxiv.org/abs/2408.05176) | 全文 + Auld 2019 全文 |
| 52 | [Li et al. 2024 逐日动态与 MEUE](52_Li2024_day_to_day_MEUE.md) | 2 / 4 | [arXiv](https://arxiv.org/abs/2401.08013) | 全文 |
| 53 | [Anagnostides et al. 2022 末轮收敛](53_Anagnostides2022_last_iterate.md) | 4 博弈学习 | [arXiv](https://arxiv.org/abs/2203.12056) | 全文 |
| 54 | [Zhu et al. 2025 ML 增强采样综述](54_Zhu2025_ML_enhanced_sampling_review.md) | 6 分子动力学 | [DOI](https://doi.org/10.1021/acs.chemrev.5c00700) | 正文全文（§1–7） |
| 55 | [Mahfuz & Slawig 2025 学习稳态作初值](55_Mahfuz2025_ML_steady_state_spinup.md) | 7 spin-up | [arXiv](https://arxiv.org/abs/2506.10475) | 全文 |
| 56 | [Li, Chen & Jin 2026 DiLLSUE](56_Li2026_DiLLSUE_Anderson_SUE.md) | 7 / 2 / 12 | [arXiv](https://arxiv.org/abs/2607.17344) | 全文 |
| 57 | [Platt 2022 神经网络贝叶斯估计](57_Platt2022_NN_Bayesian_ABM.md) | 8 经济 ABM | [DOI](https://doi.org/10.1007/s10614-021-10095-9) · [arXiv](https://arxiv.org/abs/1906.04522) | 全文（arXiv v1） |
| 58 | [Chhatre et al. 2022 BEAM 并行贝叶斯优化](58_Chhatre2022_parallel_BO_BEAM.md) | 9 代理模型 | [arXiv](https://arxiv.org/abs/2207.05041) | 全文 |
| 59 | [Liu & Meidani 2023 异构 GNN 交通分配](59_Liu2023_HetGNN_traffic_assignment.md) | 11 学习型模拟器 | [arXiv](https://arxiv.org/abs/2310.13193) | 全文（arXiv v3） |
| 60 | [Yedavalli et al. 2020 MANTA](60_Yedavalli2020_MANTA.md) | 12 GPU | [arXiv](https://arxiv.org/abs/2007.03614) | 全文（arXiv v2） |
| 61 | [POLARIS 系统、迭代方式与收费研究](61_POLARIS_system_iteration_and_pricing.md) | 1 / 2 | [OSTI 1392074](https://www.osti.gov/pages/servlets/purl/1392074) · [OSTI 3794253](https://www.osti.gov/pages/servlets/purl/3794253) | ✅ 系统论文 §4 + 收费论文方法与附录 |

原清单中同样属于近期的：[42 GEMSim 博士论文 2022](42_Saprykin2019_GEMSim.md)、[43 LPSim 2024](43_Jiang2024_LPSim.md)、[44 MOSS 2024](44_Zhang2024_GPU_simulator_benchmark.md)、[25 Vehtari 2021](25_Vehtari2021_improved_Rhat.md)、[29 Khatiwala 2024](29_Khatiwala2024_spinup_sequence_acceleration.md)；表外的 [46 PSim](46_Fourie2013_PSim.md)。

**检索到但没读到正文、因此未收录**：He et al. 2023（ESWA，代理模型辅助进化算法综述，摘要无法获取）；Ameli et al. 2020b（CACAIE，并行元启发式 DTA，只读到摘要）。

**第二轮补充对结论的影响**：
- multiMATSim（48）已做"并行实例 + 交换方案"，但只用平均得分判断收敛，可作 baseline 和反例；
- POLARIS（51 + Auld 2019）已在 activity-based 模拟器中用个体 gap 决定谁换路，并用 gap 加 1/n 权重混合历史与当前路况，2 轮收敛（只看相对 gap，没检验均衡分布）；approach 3 必须引用，新意放在"全日计划 gap + 与创新过滤结合 + 多种子检验"；
- Laudan 2025（47）显示现有 QSim 超过 6 个进程就不再加速，解释了我们只用到约 3.8/16 核；
- DiLLSUE（56）首次把 Anderson 用于交通分配，明显快于 MSA，但它的加载是确定性的；
- Mahfuz 2025（55）和 Ameli 2020（50）都显示初值对收敛影响很大，新增"用历史运行学习初始方案"的备选思路。

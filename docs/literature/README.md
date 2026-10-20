# 读书笔记（RQ1）

63 篇文献的读书笔记，按领域排列，编号和 [../rq1-answer.md](../rq1-answer.md) 附录一致。每篇笔记开头写明读了原文的哪些部分；标【推断】的是我们自己的映射，不是原文结论。PDF 不在仓库里。

[00_INDEX_RQ1_synthesis.md](00_INDEX_RQ1_synthesis.md) 是 10-19 之前的综合笔记，基于旧框架（按 gap 挑人、PSim 作基线），当前结论以 [../rq1-answer.md](../rq1-answer.md) 为准。

L2Seg（Ouyang et al. 2025）没有单独笔记，见 [../rq1-answer.md](../rq1-answer.md)。

## MATSim 与智能体交通仿真

- [03](03_Horni2016_MATSim_book.md) Horni, Nagel, Axhausen (eds.) 2016 — The Multi-Agent Transport Simulation MATSim
- [04](04_Nagel2009_agent_based_traffic_assignment.md) Nagel & Flötteröd 2009 — Agent-based traffic assignment: going from trips to behavioral travelers
- [05](05_BenDor2021_population_downscaling.md) Ben-Dor, Ben-Elia, Benenson 2021 — Population downscaling in multi-agent transportation simulations: A review and case study
- [01](01_Zhuge2021_MATSim_computing_time.md) Zhuge et al. 2021 — An improvement in MATSim computing time for large-scale travel behaviour microsimulation
- [46](46_Fourie2013_PSim.md) Fourie, Illenberger, Nagel 2013 — Increased convergence rates in multiagent transport simulations with pseudosimulation（PSim）
- [48](48_Moukir2024_multiMATSim.md) Moukir, Tsuji, Emad, Sato & Baudelocq 2024 — Advancements in Traffic Simulations with multiMATSim's Distributed Framework
- [62](62_Hoerl2018_discrete_mode_choice.md) Hörl, Balac & Axhausen 2018、2019；Hörl 2021 — MATSim 的离散方式选择扩展（Discrete Mode Choice）
- [63](63_Rakow2023_informed_mode_choice.md) Rakow & Nagel 2023 — 按估算效用提议换方式并退火（informed mode choice；论文全文待读）
- [58](58_Chhatre2022_parallel_BO_BEAM.md) Chhatre, Feygin, Sheppard & Waraich 2022 — Parallel Bayesian Optimization of Agent-based Transportation Simulation

## 交通分配与逐日动态

- [06](06_Sheffi1985_Urban_Transportation_Networks.md) Sheffi 1985 — Urban Transportation Networks: Equilibrium Analysis with Mathematical Programming Methods
- [07](07_Peeta2001_DTA_foundations.md) Peeta & Ziliaskopoulos 2001 — Foundations of dynamic traffic assignment: The past, the present and the future
- [08](08_Sbayti2007_efficient_MSA_SBDTA.md) Sbayti, Lu, Mahmassani 2007 — Efficient implementation of method of successive averages in simulation-based DTA models for large-scale network applications
- [09](09_Lu2009_gap_function_DUE.md) Lu, Mahmassani, Zhou 2009 — Equivalent gap function-based reformulation and solution algorithm for the dynamic user equilibrium problem
- [10](10_Cascetta1989_stochastic_process_dynamics.md) Cascetta 1989 — A stochastic process approach to the analysis of temporal dynamics in transportation networks
- [11](11_Watling2003_day_to_day_dynamics.md) Watling & Hazelton 2003 — The dynamics and equilibria of day-to-day assignment models
- [50](50_Ameli2020_DTA_convergence_algorithms.md) Ameli, Lebacque & Leclercq 2020 — Cross-comparison of convergence algorithms to solve trip-based dynamic traffic assignment problems
- [52](52_Li2024_day_to_day_MEUE.md) Li, Wang, Feng, Xie & Nie 2024 — A Day-to-Day Dynamical Approach to the Most Likely User Equilibrium Problem
- [56](56_Li2026_DiLLSUE_Anderson_SUE.md) Li, Chen & Jin 2026 — DiLLSUE: a differentiable GPU solver for link-based logit stochastic user equilibrium

## 基于活动的智能体平台（POLARIS）

- [51](51_Verbas2024_POLARIS_gap_based.md) Verbas, Cokyasar, de Camargo, Gurumurthy, Zuniga-Garcia & Auld 2024 — Modeling Transit in a Fully Integrated Agent-Based Framework: Methodology and Large-Scale Application
- [61](61_POLARIS_system_iteration_and_pricing.md) POLARIS：系统结构、迭代方式与收费研究（Auld et al. 2016；Mori et al.；Fakhrmoosavi et al. 2023）

## 进化算法

- [12](12_Jin2005_fitness_approximation_survey.md) Jin 2005 — A comprehensive survey of fitness approximation in evolutionary computation
- [13](13_Jin2011_surrogate_assisted_EC.md) Jin 2011 — Surrogate-assisted evolutionary computation: Recent advances and future challenges
- [14](14_Eiben1999_parameter_control.md) Eiben, Hinterding, Michalewicz 1999 — Parameter control in evolutionary algorithms
- [15](15_Hansen2001_CMA-ES.md) Hansen & Ostermeier 2001 — Completely derandomized self-adaptation in evolution strategies (CMA-ES)
- [16](16_Popovici2012_coevolutionary_principles.md) Popovici, Bucci, Wiegand, de Jong 2012 — Coevolutionary principles

## 博弈学习

- [17](17_Fudenberg1998_learning_in_games.md) Fudenberg & Levine 1998 — The Theory of Learning in Games
- [18](18_Hofbauer2002_stochastic_fictitious_play.md) Hofbauer & Sandholm 2002 — On the global convergence of stochastic fictitious play
- [19](19_Mertikopoulos2018_cycles_regularized_learning.md) Mertikopoulos, Papadimitriou, Piliouras 2018 — Cycles in adversarial regularized learning
- [20](20_Daskalakis2018_optimistic_GAN.md) Daskalakis, Ilyas, Syrgkanis, Zeng 2018 — Training GANs with optimism
- [21](21_Syrgkanis2015_fast_convergence_regularized_learning.md) Syrgkanis, Agarwal, Luo, Schapire 2015 — Fast convergence of regularized learning in games
- [53](53_Anagnostides2022_last_iterate.md) Anagnostides, Panageas, Farina & Sandholm 2022 — On Last-Iterate Convergence Beyond Zero-Sum Games

## MCMC

- [22](22_Roberts1997_optimal_scaling_RWM.md) Roberts, Gelman, Gilks 1997 — Weak convergence and optimal scaling of random walk Metropolis algorithms
- [23](23_Andrieu2008_adaptive_MCMC.md) Andrieu & Thoms 2008 — A tutorial on adaptive MCMC
- [24](24_Gelman1992_Rhat.md) Gelman & Rubin 1992 — Inference from iterative simulation using multiple sequences
- [25](25_Vehtari2021_improved_Rhat.md) Vehtari, Gelman, Simpson, Carpenter, Bürkner 2021 — Rank-normalization, folding, and localization: An improved R̂ for assessing convergence of MCMC

## 分子动力学增强采样

- [26](26_Earl2005_parallel_tempering.md) Earl & Deem 2005 — Parallel tempering: Theory, applications, and new perspectives
- [27](27_Laio2002_metadynamics.md) Laio & Parrinello 2002 — Escaping free-energy minima (metadynamics)
- [28](28_Henin2022_enhanced_sampling_survey.md) Hénin, Lelièvre, Shirts, Valsson, Delemotte 2022 — Enhanced sampling methods for molecular dynamics simulations
- [54](54_Zhu2025_ML_enhanced_sampling_review.md) Zhu, Trizio, Zhang, Hu, Jiang, Hou et al. 2025 — Enhanced Sampling in the Age of Machine Learning: Algorithms and Applications

## 气候模型 spin-up

- [29](29_Khatiwala2024_spinup_sequence_acceleration.md) Khatiwala 2024 — Efficient spin-up of Earth System Models using sequence acceleration
- [30](30_Khatiwala2008_Newton-Krylov_spinup.md) Khatiwala 2008 — Fast spin up of ocean biogeochemical models using matrix-free Newton–Krylov
- [55](55_Mahfuz2025_ML_steady_state_spinup.md) Mahfuz & Slawig 2025 — Prediction of steady states in a marine ecosystem model by a machine learning technique

## 经济学智能体模型

- [31](31_Lamperti2018_ABM_ML_surrogate.md) Lamperti, Roventini, Sani 2018 — Agent-based model calibration using machine learning surrogates
- [32](32_Grazzini2017_Bayesian_ABM_estimation.md) Grazzini, Richiardi, Tsionas 2017 — Bayesian estimation of agent-based models
- [33](33_Platt2020_ABM_calibration_comparison.md) Platt 2020 — A comparison of economic agent-based model calibration methods
- [57](57_Platt2022_NN_Bayesian_ABM.md) Platt 2022 — Bayesian Estimation of Economic Simulation Models Using Neural Networks

## 多保真度与不确定性量化

- [34](34_Peherstorfer2018_multifidelity_survey.md) Peherstorfer, Willcox, Gunzburger 2018 — Survey of multifidelity methods in uncertainty propagation, inference, and optimization
- [35](35_Kennedy2001_Bayesian_calibration.md) Kennedy & O'Hagan 2001 — Bayesian calibration of computer models
- [36](36_Giles2008_MLMC.md) Giles 2008 — Multilevel Monte Carlo path simulation

## 降阶模型与学习型模拟器

- [37](37_Benner2015_projection_MOR_survey.md) Benner, Gugercin, Willcox 2015 — A survey of projection-based model reduction methods for parametric dynamical systems
- [38](38_Peherstorfer2016_operator_inference.md) Peherstorfer & Willcox 2016 — Data-driven operator inference for nonintrusive projection-based model reduction
- [39](39_SanchezGonzalez2020_GNS.md) Sanchez-Gonzalez et al. 2020 — Learning to simulate complex physics with graph networks
- [40](40_Li2021_Fourier_neural_operator.md) Li, Kovachki, Azizzadenesheli, Liu, Bhattacharya, Stuart, Anandkumar 2021 — Fourier neural operator for parametric partial differential equations
- [41](41_Kochkov2021_ML_accelerated_CFD.md) Kochkov, Smith, Alieva, Wang, Brenner, Hoyer 2021 — Machine learning-accelerated computational fluid dynamics
- [49](49_Natterer2025_GNN_surrogate_MATSim.md) Natterer, Rao, Tejada-Lapuerta, Engelhardt, Hörl & Bogenberger 2025 — Machine learning surrogates for agent-based models in transportation policy analysis
- [59](59_Liu2023_HetGNN_traffic_assignment.md) Liu & Meidani 2023 — End-to-End Heterogeneous Graph Neural Networks for Traffic Assignment

## 更快的仿真引擎与并行仿真

- [02](02_Graur2021_Hermes.md) Graur, Bruno, Bischoff et al. 2021 — Hermes: Enabling efficient large-scale simulation in MATSim
- [42](42_Saprykin2019_GEMSim.md) Saprykin, Chokani, Abhari 2019 — GEMSim: A GPU-accelerated multi-modal mobility simulator for large-scale scenarios
- [43](43_Jiang2024_LPSim.md) Jiang, Sengupta, Demmel, Williams 2024 — Large scale multi-GPU based parallel traffic simulation for accelerated traffic assignment and propagation (LPSim)
- [44](44_Zhang2024_GPU_simulator_benchmark.md) Zhang, Ao, Yan, Jin, Li 2024 — A GPU-accelerated large-scale simulator for transportation system optimization benchmarking
- [45](45_Fujimoto2000_PDES.md) Fujimoto 2000 — Parallel and Distributed Simulation Systems
- [47](47_Laudan2025_distributed_QSim.md) Laudan, Heinrich & Nagel 2025 — High-Performance Mobility Simulation: Implementation of a Parallel Distributed Message-Passing Algorithm for MATSim
- [60](60_Yedavalli2020_MANTA.md) Yedavalli, Kumar & Waddell 2020 — Microsimulation Analysis for Network Traffic Assignment (MANTA) at Metropolitan-Scale for Agile Transportation Planning

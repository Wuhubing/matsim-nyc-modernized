# 归档文档

这些文档记录了项目早期的方向和推导，已经被当前文档取代。只在需要查历史时读；**不要据此接着做**。其中仍然成立的数据和结论，都已经写进当前文档或实验登记表。

| 文件 | 日期 | 是什么 | 被什么取代 | 仍然有用的部分 |
|---|---|---|---|---|
| [research-charter.md](research-charter.md) | 10-15 | 总纲 v1：以 G（均衡差距）为主要度量的四个假设 | [../charter.md](../charter.md)（v2.2） | 问题背景、L2Seg 对应表 |
| [HANDOFF.md](HANDOFF.md) | 10-15 | 当时的交接说明和在跑的作业 | [../../CLAUDE.md](../../CLAUDE.md)、[../README.md](../README.md) | 集群和提交规则（已并入 CLAUDE.md） |
| [execution-plan.md](execution-plan.md) | 10-15 | 跨运行学习轨迹、`StableReRoute` 的执行计划 | 总纲 v2.2 | 无 |
| [aggregate-regularity-plan.md](aggregate-regularity-plan.md) | 10-15 | 利用总体层面规律的计划 | 总纲 v2.2 | 第 7 节的数据：个人层面规律弱、总体层面强 |
| [l2seg-replanning-plan.md](l2seg-replanning-plan.md) | 10-07 至 10-15 | 按个人预测谁需要重新规划（L2Seg 的直接类比）及全部推导 | 总纲 v2.2；[../rq1-answer.md](../rq1-answer.md) 的 L2Seg 部分 | 第 2 节每轮成本、第 3 节 L2Seg 对应、第 4 节早期基线、第 8.2 节试新方案的浪费分析 |
| [h0-equilibrium-gap.md](h0-equilibrium-gap.md) | 10-15 | 选择差距：慢在发现而不在选择 | 总纲第 2 节事实一 | 结论仍成立 |
| [h1-proposal-predictor.md](h1-proposal-predictor.md) | 10-15 | 离线预测器：试新方案的结果能否提前预测（换方式 AUC 0.86） | 总纲第 2 节事实二 | 结论仍成立，是"按效用提议换方式"的依据 |
| [matsim-nyc-findings.md](matsim-nyc-findings.md) | 10-04 至 10-15 | 运行发现汇总（工程优化、复现、模型偏差） | [../experiments.md](../experiments.md)、[../matsim-explained.md](../matsim-explained.md) | 第 3–5 节：可复现性、模型已知局限（屏幕线 +75% 等） |
| [project-log-detailed.md](project-log-detailed.md) | 10-04 至 10-15 | 每一步的详细记录（作业号、提交、失败原因） | [../progress-log.md](../progress-log.md) | 查早期作业细节 |
| [progress-2026-10-15.html](progress-2026-10-15.html) | 10-15 | 当时的进度页 | 无 | 无 |
| [matsim-as-algorithm.md](matsim-as-algorithm.md) | 10-17 | MATSim 的形式化、收敛定义、三个加速框架、离线检验 O1–O3 | [../matsim-explained.md](../matsim-explained.md)；框架部分被总纲第 4 节取代 | 第 1–4 节的形式化；第 9 节 O1–O3 的数据（总纲第 2 节引用） |

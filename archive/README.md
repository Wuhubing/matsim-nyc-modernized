# 归档：2026-11-18 之前的方法探索

2026-11-18 整理仓库时，把此前的方法探索从 `docs/` 和 `experiments/` 移到这里，保留原来的相对结构。仓库主目录只留问题定义、验收标准、参考资料、实验登记表、模型和运行器。

**地位：** 这里是历史记录，不是当前计划。以前试过并放下的方向可以重新做（用户 11-18），重新做之前先看这里当时的结论和理由。

## 内容

| 位置 | 内容 | 原位置 |
|---|---|---|
| [docs/progress-log.md](docs/progress-log.md) | 按时间的进展记录（到 10-20） | `docs/` |
| [docs/ideas.md](docs/ideas.md) | 发现与可能的方法（未经筛选） | `docs/` |
| [docs/converged-plan-plan.md](docs/converged-plan-plan.md) | 从人的一天加城市结构预测稳定状态（10-28 至 11-03，含提前结束检验） | `docs/` |
| [docs/latent-choice-plan.md](docs/latent-choice-plan.md)、[docs/latent-audit.md](docs/latent-audit.md) | 城市与个人隐变量网络的计划和审查 | `docs/` |
| [docs/policy-prediction-plan.md](docs/policy-prediction-plan.md) | 政策情景预测的计划 | `docs/` |
| [docs/diagnostics/](docs/diagnostics/g-estimator.md) | G 估算器（均衡差距）设计 | `docs/diagnostics/` |
| [docs/archive/](docs/archive/README.md) | 更早被取代的计划和记录（10-15 以前） | `docs/archive/` |
| `experiments/rq3/` | 政策效应、验收、探针、换方案等分析代码和输出 | `experiments/rq3/` |
| `experiments/l2seg/` | 共用解析函数和早期分析 | `experiments/l2seg/` |
| `experiments/latent/` | 学习型起点（隐变量网络、梯度提升树、种子起点）的代码和结果 | `experiments/latent/` |

三个代码目录之间的相对位置没有变，`rq3` 里按相对路径导入 `l2seg` 的脚本仍然可用。

## ORCD 上的运行

运行目录本身在 ORCD，不在仓库里。整理后的位置见 [../docs/experiments.md](../docs/experiments.md)。

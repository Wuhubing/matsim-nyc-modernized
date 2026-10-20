# 实验登记表

所有在 MIT ORCD 上跑过、有 `run.json` 的运行（生成于 2026-10-19，读取各运行目录的 `run.json`）。路径都在 `/orcd/scratch/orcd/006/weibingw/matsim-work/` 下；大文件（`simulation/ITERS`、`simulation/research`）已移到 `/orcd/pool/007/weibingw/matsim-work-iters/` 的同名路径，原位置留有链接，按原路径即可读。

**提交号**是跑这个运行时代码所在的提交，可以在旧分支上找到（`research/rq3-acceleration` 包含全部提交）。

## 代号对照表

进展记录和归档文档里还会出现这些代号：

| 代号 | 名称 |
|---|---|
| RQ0 | 早期原版基线（10-07，3 个种子，无重新规划日志） |
| RQ1 基线 | 原版基线（带重新规划日志） |
| E1（10-17 起） | 精英父代 |
| E3 | 精英父代 + 改时间后找路 |
| E1、E2（10-14 至 10-15） | 早期的得分平均、创新退火 |
| W0 | 热启动的基线 |
| W1 | 热启动的政策运行 |
| X1 | 只做选择的续跑 |
| Schema 1 / Schema 2 | $9.18 / $14 的收费方案 |
| k | 停止试新方案的轮次（探针） |
| B 阶段 | 漏斗的第二阶段：一个种子的短流程或探针 |

## 原版基线（带重新规划日志，RQ1 基线）

- **做什么：** 原流程不收费，100 轮，第 79 轮后只做选择；记录每次试新方案的结果
- **主要结果：** 政策效应参照的基线；试新方案约 85% 无效；最好计划得分到第 79 轮仍在升
- **在哪里分析：** progress-log.md；archive/l2seg-replanning-plan.md 第 8 节
- **现在是否相关：** 是：所有比较的基线

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `rq1/baseline-s4711-100it-rq1` | baseline | 4711 | 100 | cold.xml.gz | `e1581d1` | completed | 9.0 |
| `rq1/baseline-s4712-100it-rq1` | baseline | 4712 | 100 | cold.xml.gz | `e1581d1` | completed | 10.5 |
| `rq1/baseline-s4713-100it-rq1` | baseline | 4713 | 100 | cold.xml.gz | `e1581d1` | completed | 8.5 |

## 原版政策参照（Schema 1 $9.18 / Schema 2 $14）

- **做什么：** 原流程跑两个收费方案，各 3 个种子
- **主要结果：** 定出九项政策效应的区间
- **在哪里分析：** acceptance-protocol.md 第 6 节
- **现在是否相关：** 是：验收标准的来源

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `policy/schema1-s4711-100it` | schema1 | 4711 | 100 | cold.xml.gz | `6436c9f` | completed | 8.2 |
| `policy/schema1-s4712-100it` | schema1 | 4712 | 100 | cold.xml.gz | `6436c9f` | completed | 8.9 |
| `policy/schema1-s4713-100it` | schema1 | 4713 | 100 | cold.xml.gz | `6436c9f` | completed | 6.7 |
| `policy/schema2-s4711-100it` | schema2 | 4711 | 100 | cold.xml.gz | `91fe7b0` | completed | 7.1 |
| `policy/schema2-s4712-100it` | schema2 | 4712 | 100 | cold.xml.gz | `91fe7b0` | completed | 9.0 |
| `policy/schema2-s4713-100it` | schema2 | 4713 | 100 | cold.xml.gz | `91fe7b0` | completed | 8.9 |

## 精英父代（E1）

- **做什么：** 试新方案时从得分高的计划出发，其余同原流程
- **主要结果：** 九项政策效应全部通过；固定流程下约 1.3 倍（按创新期领先估计）
- **在哪里分析：** progress-log.md 10-18
- **现在是否相关：** 是

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `policy/elite-baseline-s4711-100it` | baseline | 4711 | 100 | cold.xml.gz | `143097d` | completed | 8.1 |
| `policy/elite-baseline-s4712-100it` | baseline | 4712 | 100 | cold.xml.gz | `8ced118` | completed | 7.3 |
| `policy/elite-baseline-s4713-100it` | baseline | 4713 | 100 | cold.xml.gz | `8ced118` | completed | 6.7 |
| `policy/elite-schema1-s4711-100it` | schema1 | 4711 | 100 | cold.xml.gz | `8ced118` | completed | 9.2 |
| `policy/elite-schema1-s4712-100it` | schema1 | 4712 | 100 | cold.xml.gz | `8ced118` | completed | 8.4 |
| `policy/elite-schema1-s4713-100it` | schema1 | 4713 | 100 | cold.xml.gz | `8ced118` | completed | 6.9 |
| `policy/elite-schema2-s4711-100it` | schema2 | 4711 | 100 | cold.xml.gz | `8ced118` | completed | 7.2 |
| `policy/elite-schema2-s4712-100it` | schema2 | 4712 | 100 | cold.xml.gz | `8ced118` | completed | 7.9 |
| `policy/elite-schema2-s4713-100it` | schema2 | 4713 | 100 | cold.xml.gz | `8ced118` | completed | 11.1 |

## 精英父代 + 改时间后找路（E3）

- **做什么：** 在精英父代上，改出发时间后重新找路
- **主要结果：** 收费区相关人群少开车次超出区间（1.15、1.51 倍容差）
- **在哪里分析：** progress-log.md 10-19 晚
- **现在是否相关：** 是（已否定）

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `policy/elite-tamrr-baseline-s4711-100it` | baseline | 4711 | 100 | cold.xml.gz | `8ced118` | completed | 8.3 |
| `policy/elite-tamrr-baseline-s4712-100it` | baseline | 4712 | 100 | cold.xml.gz | `8ced118` | completed | 7.5 |
| `policy/elite-tamrr-baseline-s4713-100it` | baseline | 4713 | 100 | cold.xml.gz | `8ced118` | completed | 7.5 |
| `policy/elite-tamrr-schema1-s4711-100it` | schema1 | 4711 | 100 | cold.xml.gz | `d5eafe6` | completed | 7.4 |
| `policy/elite-tamrr-schema1-s4712-100it` | schema1 | 4712 | 100 | cold.xml.gz | `d5eafe6` | completed | 9.2 |
| `policy/elite-tamrr-schema1-s4713-100it` | schema1 | 4713 | 100 | cold.xml.gz | `d5eafe6` | completed | 8.8 |
| `policy/elite-tamrr-schema2-s4711-100it` | schema2 | 4711 | 100 | cold.xml.gz | `8ced118` | completed | 11.4 |
| `policy/elite-tamrr-schema2-s4712-100it` | schema2 | 4712 | 100 | cold.xml.gz | `8ced118` | completed | 7.0 |
| `policy/elite-tamrr-schema2-s4713-100it` | schema2 | 4713 | 100 | cold.xml.gz | `a51f4cf` | completed | 9.9 |

## 热启动的基线（W0）

- **做什么：** 从原版基线第 99 轮的计划出发，再跑 100 轮不收费
- **主要结果：** 作为热启动政策运行的配对基线
- **在哪里分析：** progress-log.md 10-18 晚
- **现在是否相关：** 是

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `policy/warm-baseline-s4711-100it` | baseline | 4711 | 100 | BUILT.output_plans.xml.zst | `6436c9f` | completed | 8.4 |
| `policy/warm-baseline-s4712-100it` | baseline | 4712 | 100 | BUILT.output_plans.xml.zst | `6436c9f` | completed | 8.3 |
| `policy/warm-baseline-s4713-100it` | baseline | 4713 | 100 | BUILT.output_plans.xml.zst | `6436c9f` | completed | 8.5 |

## 热启动的政策运行（W1）

- **做什么：** 从原版基线第 99 轮的计划出发，跑收费方案 100 轮
- **主要结果：** 政策效应（减去热启动基线）全部通过；终点水平和冷启动差很多；固定流程下不省时间
- **在哪里分析：** progress-log.md 10-17、10-18 晚；plan-change 分析
- **现在是否相关：** 是

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `policy/warm-schema1-s4711-100it` | schema1 | 4711 | 100 | BUILT.output_plans.xml.zst | `6436c9f` | completed | 8.6 |
| `policy/warm-schema1-s4712-100it` | schema1 | 4712 | 100 | BUILT.output_plans.xml.zst | `6436c9f` | completed | 7.4 |
| `policy/warm-schema1-s4713-100it` | schema1 | 4713 | 100 | BUILT.output_plans.xml.zst | `6436c9f` | completed | 8.6 |
| `policy/warm-schema2-s4711-100it` | schema2 | 4711 | 100 | BUILT.output_plans.xml.zst | `91fe7b0` | completed | 7.8 |
| `policy/warm-schema2-s4712-100it` | schema2 | 4712 | 100 | BUILT.output_plans.xml.zst | `91fe7b0` | completed | 10.0 |
| `policy/warm-schema2-s4713-100it` | schema2 | 4713 | 100 | BUILT.output_plans.xml.zst | `91fe7b0` | completed | 7.7 |

## 只做选择的续跑（X1）

- **做什么：** 从原版基线第 99 轮出发，只做选择 50 轮
- **主要结果：** 关掉试新方案后的漂移很小；作为换方案比例的噪声底线
- **在哪里分析：** e3-acceptance 输出；plan-change 分析
- **现在是否相关：** 是

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `policy/x1-baseline-s4711-from99-50it` | baseline | 4711 | 50 | BUILT.output_plans.xml.zst | `6436c9f` | completed | 3.9 |
| `policy/x1-baseline-s4712-from99-50it` | baseline | 4712 | 50 | BUILT.output_plans.xml.zst | `6436c9f` | completed | 4.6 |
| `policy/x1-baseline-s4713-from99-50it` | baseline | 4713 | 50 | BUILT.output_plans.xml.zst | `6436c9f` | completed | 3.6 |

## 创新退火（早期代号 E2）

- **做什么：** 试新方案比例从 0.3 逐轮降到接近 0
- **主要结果：** 终点开车比例 0.376 对 0.426（另一种统计口径），提前停止发现
- **在哪里分析：** archive/l2seg-replanning-plan.md 8.2；archive/h0-equilibrium-gap.md
- **现在是否相关：** 部分：退火候选的旧证据

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `alg/e2-anneal-s4711-100it` | baseline | 4711 | 100 | cold.xml.gz | `91d17a0` | completed | 7.1 |

## 得分平均（早期代号 E1，与精英父代的 E1 无关）

- **做什么：** 计划得分取多次执行的平均
- **主要结果：** 两次都因内存不足失败，前 51 轮数据在目录里
- **在哪里分析：** archive/h0-equilibrium-gap.md
- **现在是否相关：** 否

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `alg/e1-scoremsa-s4711-100it` | baseline | 4711 | 100 | cold.xml.gz | `91d17a0` | failed | 7.5 |
| `alg/e1-scoremsa-s4711-100it-oom16g` | baseline | 4711 | 100 | cold.xml.gz | `d39bafc` | failed | 1.7 |

## 缩短流程探针：原版（B 阶段）

- **做什么：** 从原版第 k 轮的计划出发只做选择 12 轮
- **主要结果：** 只有 k = 80（即原流程）通过
- **在哪里分析：** progress-log.md 10-19 晚；out/probes-b1.json
- **现在是否相关：** 是

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `rq3/probe-cold-baseline-s4711-k30` | baseline | 4711 | 12 | BUILT.30.plans.xml.zst | `91fe7b0` | completed | 1.3 |
| `rq3/probe-cold-baseline-s4711-k50` | baseline | 4711 | 12 | BUILT.50.plans.xml.zst | `91fe7b0` | completed | 1.6 |
| `rq3/probe-cold-baseline-s4711-k70` | baseline | 4711 | 12 | BUILT.70.plans.xml.zst | `91fe7b0` | completed | 1.2 |
| `rq3/probe-cold-baseline-s4711-k80` | baseline | 4711 | 12 | BUILT.80.plans.xml.zst | `6436c9f` | completed | 1.4 |
| `rq3/probe-cold-schema1-s4711-k30` | schema1 | 4711 | 12 | BUILT.30.plans.xml.zst | `91fe7b0` | completed | 1.5 |
| `rq3/probe-cold-schema1-s4711-k50` | schema1 | 4711 | 12 | BUILT.50.plans.xml.zst | `91fe7b0` | completed | 1.1 |
| `rq3/probe-cold-schema1-s4711-k70` | schema1 | 4711 | 12 | BUILT.70.plans.xml.zst | `91fe7b0` | completed | 1.2 |
| `rq3/probe-cold-schema1-s4711-k80` | schema1 | 4711 | 12 | BUILT.80.plans.xml.zst | `6436c9f` | completed | 1.4 |
| `rq3/probe-cold-schema2-s4711-k30` | schema2 | 4711 | 12 | BUILT.30.plans.xml.zst | `91fe7b0` | completed | 0.9 |
| `rq3/probe-cold-schema2-s4711-k50` | schema2 | 4711 | 12 | BUILT.50.plans.xml.zst | `91fe7b0` | completed | 1.2 |
| `rq3/probe-cold-schema2-s4711-k70` | schema2 | 4711 | 12 | BUILT.70.plans.xml.zst | `91fe7b0` | completed | 1.2 |
| `rq3/probe-cold-schema2-s4711-k80` | schema2 | 4711 | 12 | BUILT.80.plans.xml.zst | `91fe7b0` | completed | 1.3 |

## 缩短流程探针：精英父代

- **做什么：** 从精英父代第 k 轮的计划出发只做选择 12 轮
- **主要结果：** k = 30/50/70 都不通过
- **在哪里分析：** 同上
- **现在是否相关：** 是

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `rq3/probe-e1-baseline-s4711-k30` | baseline | 4711 | 12 | BUILT.30.plans.xml.zst | `91fe7b0` | completed | 1.4 |
| `rq3/probe-e1-baseline-s4711-k50` | baseline | 4711 | 12 | BUILT.50.plans.xml.zst | `91fe7b0` | completed | 1.6 |
| `rq3/probe-e1-baseline-s4711-k70` | baseline | 4711 | 12 | BUILT.70.plans.xml.zst | `91fe7b0` | completed | 1.5 |
| `rq3/probe-e1-schema1-s4711-k30` | schema1 | 4711 | 12 | BUILT.30.plans.xml.zst | `91fe7b0` | completed | 0.9 |
| `rq3/probe-e1-schema1-s4711-k50` | schema1 | 4711 | 12 | BUILT.50.plans.xml.zst | `91fe7b0` | completed | 1.9 |
| `rq3/probe-e1-schema1-s4711-k70` | schema1 | 4711 | 12 | BUILT.70.plans.xml.zst | `91fe7b0` | completed | 1.6 |
| `rq3/probe-e1-schema2-s4711-k30` | schema2 | 4711 | 12 | BUILT.30.plans.xml.zst | `91fe7b0` | completed | 0.9 |
| `rq3/probe-e1-schema2-s4711-k50` | schema2 | 4711 | 12 | BUILT.50.plans.xml.zst | `91fe7b0` | completed | 1.5 |
| `rq3/probe-e1-schema2-s4711-k70` | schema2 | 4711 | 12 | BUILT.70.plans.xml.zst | `91fe7b0` | completed | 1.5 |

## 缩短流程探针：热启动

- **做什么：** 从热启动运行第 k 轮的计划出发只做选择 12 轮
- **主要结果：** k = 10–40 都不通过
- **在哪里分析：** 同上
- **现在是否相关：** 是

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `rq3/probe-warm-baseline-s4711-k10` | baseline | 4711 | 12 | BUILT.10.plans.xml.zst | `91fe7b0` | completed | 1.3 |
| `rq3/probe-warm-baseline-s4711-k20` | baseline | 4711 | 12 | BUILT.20.plans.xml.zst | `91fe7b0` | completed | 1.3 |
| `rq3/probe-warm-baseline-s4711-k30` | baseline | 4711 | 12 | BUILT.30.plans.xml.zst | `91fe7b0` | completed | 0.8 |
| `rq3/probe-warm-baseline-s4711-k40` | baseline | 4711 | 12 | BUILT.40.plans.xml.zst | `91fe7b0` | completed | 1.1 |
| `rq3/probe-warm-schema1-s4711-k10` | schema1 | 4711 | 12 | BUILT.10.plans.xml.zst | `91fe7b0` | completed | 1.3 |
| `rq3/probe-warm-schema1-s4711-k20` | schema1 | 4711 | 12 | BUILT.20.plans.xml.zst | `91fe7b0` | completed | 0.9 |
| `rq3/probe-warm-schema1-s4711-k30` | schema1 | 4711 | 12 | BUILT.30.plans.xml.zst | `91fe7b0` | completed | 1.6 |
| `rq3/probe-warm-schema1-s4711-k40` | schema1 | 4711 | 12 | BUILT.40.plans.xml.zst | `91fe7b0` | completed | 1.1 |
| `rq3/probe-warm-schema2-s4711-k10` | schema2 | 4711 | 12 | BUILT.10.plans.xml.zst | `91fe7b0` | completed | 1.0 |
| `rq3/probe-warm-schema2-s4711-k20` | schema2 | 4711 | 12 | BUILT.20.plans.xml.zst | `91fe7b0` | completed | 0.9 |
| `rq3/probe-warm-schema2-s4711-k30` | schema2 | 4711 | 12 | BUILT.30.plans.xml.zst | `91fe7b0` | completed | 1.1 |
| `rq3/probe-warm-schema2-s4711-k40` | schema2 | 4711 | 12 | BUILT.40.plans.xml.zst | `91fe7b0` | completed | 1.0 |

## 12 轮机制检查：精英父代 / + 改时间后找路

- **做什么：** 前 12 轮比较最好计划得分上升速度
- **主要结果：** 两者都比原版快；后者在 12 轮里最快
- **在哪里分析：** progress-log.md 10-17
- **现在是否相关：** 部分

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `rq3/elite-baseline-s4711-12it-v2` | baseline | 4711 | 12 | cold.xml.gz | `143097d` | completed | 1.2 |
| `rq3/elite-tamrr-baseline-s4711-12it-v2` | baseline | 4711 | 12 | cold.xml.gz | `143097d` | completed | 1.1 |

## 12 轮检查：重新找路的权重

- **做什么：** 改变重新找路策略的权重
- **主要结果：** 效果小，不单独做
- **在哪里分析：** progress-log.md 10-17
- **现在是否相关：** 否

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `rq3/reroute-w0.025-baseline-s4711-12it` | baseline | 4711 | 12 | cold.xml.gz | `143097d` | completed | 1.0 |
| `rq3/reroute-w0.05-baseline-s4711-12it` | baseline | 4711 | 12 | cold.xml.gz | `16f5f1c` | completed | 1.1 |
| `rq3/reroute-w0.1-baseline-s4711-12it` | baseline | 4711 | 12 | cold.xml.gz | `16f5f1c` | completed | 1.3 |

## 12 轮检查：2025 实际收费方案

- **做什么：** 确认关创新设置在 2025 方案上生效
- **主要结果：** 通过
- **在哪里分析：** progress-log.md
- **现在是否相关：** 否

| 运行目录 | 场景 | 种子 | 轮数 | 起点计划 | 提交 | 状态 | 墙钟时间（小时） |
|---|---|---|---|---|---|---|---|
| `rq3/check-off-actual2025-s4711-12it` | actual2025 | 4711 | 12 | cold.xml.gz | `0d89e03` | completed | 0.7 |

## 早期运行（没有 `run.json` 索引）

- **早期原版基线（RQ0）：** `20261007-083453-configfix/baseline/`，3 个种子 × 100 轮，用于最初的容差和稳定分析（archive/l2seg-replanning-plan.md 第 4 节）。
- **12 轮复现检查：** `20261007-003204-61/validation/`、`20261007-004927-68/validation/`。

## 失败或被抢占、已由正常运行替代的目录

`policy/elite-schema2-s4713-100it-failed-quota`, `policy/elite-tamrr-baseline-s4711-100it-failed-quota`, `policy/elite-tamrr-baseline-s4712-100it-failed-quota`, `policy/elite-tamrr-baseline-s4713-100it-failed-quota`, `policy/elite-tamrr-schema1-s4711-100it-failed-quota`, `policy/elite-tamrr-schema1-s4711-100it-preempted-26279181`, `policy/elite-tamrr-schema1-s4712-100it-failed-quota`, `policy/elite-tamrr-schema1-s4712-100it-preempted-26279182`, `policy/elite-tamrr-schema1-s4713-100it-preempted-26279183`, `policy/elite-tamrr-schema2-s4713-100it-preempted-26279186`, `alg/e1-scoremsa-s4711-100it`, `alg/e1-scoremsa-s4711-100it-oom16g`, `alg/e2-anneal-s4711-100it-oom16g`, `rq3/elite-baseline-s4711-12it`, `rq3/elite-tamrr-baseline-s4711-12it`, `rq3/probe-cold-baseline-s4711-k30-preempted-26391916-1`, `rq3/probe-cold-baseline-s4711-k50-preempted-26391923-1`, `rq3/probe-cold-schema1-s4711-k30-preempted-26391918-1`, `rq3/probe-cold-schema1-s4711-k30-preempted-26391918-2`, `rq3/probe-cold-schema2-s4711-k30-preempted-26391921-1`, `rq3/probe-cold-schema2-s4711-k80-preempted-26378825-0`

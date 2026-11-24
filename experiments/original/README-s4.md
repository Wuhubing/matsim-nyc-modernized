# 阶段 2–3 分析：抽取、对账、稳定窗口、政策差值（运行前登记，2026-11-24）

**本文件在抽取作业提交之前写下。** 之后只追加"结果"，不改前面的定义和阈值。分析草案新增的阈值（5%/10%/20%、95%/20%、翻转率比 2、净值 10% 等）都是**探索性筛选建议**，不是总纲或验收方案的正式标准；总纲九项 Δ 和容差（[charter.md](../../docs/charter.md) §3.1、[acceptance-protocol.md](../../docs/acceptance-protocol.md) §6）不改。

## 0. 版本与输入

- 分析版本：`s4-s6 v1 (2026-11-24)`；执行仓库 `research/cleanup`，HEAD `df776c3`，本目录新增文件未提交（只有他人的未跟踪 `docs/weekly/2026-10-20.md` 与本批新文件）。
- 脚本：`s4_common.py`、`s4_extract.py`、`s4_reconcile.py`、`s5_stability.py`、`s6_policy.py`、`s4_figures.py`、提交脚本 `s4.sbatch`（单个普通串行作业，`STAGE=` 选阶段）。各作业在 `run-manifest-<jobid>-<stage>.json` 里记下脚本 sha256、Python/numpy/pandas 版本、Slurm 资源、九个 run 的提交号。
- Python：ORCD 现有模块 `miniforge/25.11.0-0`（Python 3.12.12、numpy 2.3.5、pandas 2.3.3、matplotlib 3.10.8），**不安装任何软件**。（`~/matsim-work/venv-latent` 的解释器已丢失，s3 当时用的环境现在不能用。）
- 数据：九个原版运行 `/orcd/scratch/orcd/006/weibingw/matsim-work/{rq1/baseline-s47XX-100it-rq1, policy/schema1-s47XX-100it, policy/schema2-s47XX-100it}/simulation/research/`（`persons-N`、`groups-N`、`group-modes-N`、`cohorts.csv.gz`；基线另有 `replanning-log/`）。只读。
- 远端部署：`~/matsim-work/original-analysis/s4-20261124/code/`；结果 `~/matsim-work/original-analysis/out-s4-20261124/`（大矩阵留在这里）。已有 s3 的 `out-s3/*.json`、`*.npz`（只有每人汇总量）只用于对账；s2 的 `out-s2/aggregate.json`、时间结果直接复用，不重算。
- 资源上限（用户批准的上限）：同时 1 个作业，≤4 CPU，≤24 GiB，每作业 ≤2 小时，`mit_preemptable --requeue`，不用数组。按实测收紧。

## 1. 抽取（阶段 2 数据准备）

- 每个 run：`cohorts.csv.gz` 的顺序为共同顺序；每个 `persons-N` 按 `person_id` 对齐（**不按行号**），记录：行数、唯一 ID 数、重复行、不在 cohort 里的 ID、缺失 ID、行序是否与 cohort 相同、列头、数值解析错误、负数/非整数计数、`departures = completed + stuck`、`unfinished ∈ {0,1}`、gzip 尾部 CRC32 与大小、文件大小与 mtime。**缺行记 `present=False`，不补零；重复行保留第一行并记入问题。** 任何问题 → 该 run `complete=false`，依赖它的分析停止。
- 指纹：`choice_sha256`、`plan_sha256` 取前 128 位做碰撞检验（前 64 位相同而后 64 位不同的对数），只保存前 64 位。`realized_choice_hash64`、`outcome_hash64` 本来就是 64 位滚动哈希（可能碰撞）。并检查写入器的 `choice_changed`/`plan_changed` 与 64 位哈希比较结果是否逐项一致。
- 对账：逐组逐轮把 persons 之和与 `groups-N`、`group-modes-N` 比较（得分和、未完成、完成小汽车段、小汽车秒、收费、换方案数、进入数、全方式 departures/completed/stuck、人数）；`group-modes` 里逐行核对 `departures = completed + stuck`，以及 joint 组之和等于 all/charging/subpopulation 组。
- 基线日志：每个基线 run 读自己的 `strategies.csv` 和 `replanning-log/persons.csv.gz`（索引→`person_id`）；政策 run 没有日志，也不要求有。
- 缓存复用：只有 `check.json` 为 complete、源文件指纹（路径|大小|mtime|CRC）不变、NPZ 数组齐全才复用，否则重抽。

## 2. 指标定义（样本单位，不放大）

| 指标 | 定义 | 来源 |
|---|---|---|
| `legs_car_charging:related` | 收费区相关人群的小汽车**出发**段数 | `group-modes`，组 `charging:related`，方式 `car`，`departures` |
| `share_car`、`share_pt` | 该方式出发段数 ÷ 全部方式出发段数 | `group-modes`，组 `all` |
| Δ | 政策窗口均值 − 同 seed 基线窗口均值，窗口 = 第 90–99 轮 | |
| D | Δ(schema1) − Δ(schema2) | |
| 参照 | 3 个 seed 的 Δ 均值（Δ̄_ref）；容差 ε 用总纲表，不改 | charter §3.1 |
| 完成段数 | `completed`（s2 的 `legs_car` 是它），**单独保留** | |
| 组残差 | departures − completed（小汽车），先作精确残差，**对账完成后**才称 stuck | |

## 3. 对账与门槛（先于一切分解）

1. **总纲九项：** 重算 Δ̄_ref 与总纲表比较；通过标准是在总纲表的**舍入精度内**一致（整数项 ±0.5，五位小数项 ±0.000005，D 同）。sd 同时报告（样本标准差 ddof=1；若不吻合再报 ddof=0），不是门槛。
2. **s3：** 每个 run 重算 s3 的曲线（换方案、用车变化、用车比例、新方案、在最终备选里）与每人量的直方图，和 `out-s3/s3-*.json` 比较；浮点比例按 1e-9 比较，直方图按整数相等。
3. **s2：** `aggregate.json` 的完成小汽车段数与 share 曲线对比重算。
4. 任何一项不过：先查输入和口径；确有不可解差异则停止依赖它的分析并报告，**不改容差**。

## 4. 稳定性（阶段 2）

- 人群：会重新规划的人（`man`、`nonman`）为主；`outside`（计划不变）单列。固定主分组 = `subpopulation` × `charging_cohort`（多边形是探索性重建）。`plans_in_memory ≥ 2`（过去窗口最后一轮的值）只作稳定性辅助分层，注明受政策影响可能，**不用于政策贡献的主分组**。
- 窗口：主划分 P = 80–89，H = 90–99；滚动 t ∈ {84, 89, 94}，P = [t−9, t]，H = [t+1, t+5]（t=84 的 P 含创新期，单独标"含创新期"）；跨阶段 P = 70–79 → H = 80–89。
- 稳定定义（P 内 10 个状态全部满足）：`choice_sha256` 不变（计划指纹）；`plan_sha256` 不变（含时间）；`completed_car_legs>0` 不变（用车状态）；`completed_car_legs` 不变（用车次数）；`completed_travel_seconds`（与小汽车秒数 `completed_car_seconds`）相邻轮相对变化 ≤ τ，τ ∈ {5%, 10%, 20%}，另加绝对 ≤60 秒；`realized_choice_hash64` 不变（辅助）；`outcome_hash64` 不变（只作"轨迹不稳定"的证据，不作标签）。
- 相对变化：|x_t − x_{t−1}| / x_{t−1}；两轮都为 0 记"不变"；前一轮为 0 而本轮 >0 记"变化"（单独计数，不除零）。另报绝对差的分位数。
- H 失稳 = H 内任一状态与"P 最后一轮的状态"不同（相对"冻结在 P 末"的偏离）；同时报告 H 内相邻轮变化。两者都是回顾性检验，不是已部署的预测器。
- **翻转率比 = 未标签组 H 失稳率 ÷ 标签组 H 失稳率；标签组失稳为 0 时报告原始计数，不报无穷比。** 分层置换参照在 `subpopulation × cohort × P 窗口用车模式（始终开/从不开/混合）` 内解析计算：参照失稳率 = Σ_层 (标签人数_层 × 层内总体失稳率_层) / Σ 标签人数。
- 跨 seed：在 seed a 的 P 定义标签，在 seed b 的 H 检验同一批人；重叠 = |L_a ∩ L_b|，随机期望 = Σ_层 n_a,层 n_b,层 / N_层，报告比值与分层后的值。
- **新计划代理：** 先在三个基线 run 上核对日志阶段：用 `executed_score`（日志）与 `persons` 的 `score` 在不同滞后（−1、0、+1）上的一致率，以及 `plan_created==iteration` 与"含时间指纹此人以前未出现"在各滞后上的一致率，确认日志与 persons 同轮对齐；再报告混淆矩阵、precision、recall、各策略的 recall（用各 run 自己的策略编号）、创新开/关分开。**探索性门槛（不是正式标准）：总体一致率 ≥95% 且 recall（漏检 ≤20%）。** 不达标 → 政策 run 不做"试新方案 vs 选择"的拆分，也不把"新指纹"解释为真实创新。
- 更新机会：基线用日志的 `innovative`；政策 run 只给基线同配置的观测频率作期望，标注"期望，不是逐 ID 计数"。

## 5. 政策差值（阶段 3）

- Δ(t)：九项逐轮 Δ 和最近 10 轮均值（t ≥ 9），与 Δ̄_ref 比较，**持续进入容差**（此后到第 99 轮每轮都在 ε 内）与**首次穿过**分开；三种窗口：最近 10 轮、第 80 轮到 t 的累计、单轮；参照 = 3-seed 均值（主）和各 seed 自己的第 90–99 轮（敏感性）；跨过第 79/80 轮的窗口标注。每 seed 单独报，3/3 同号单独报。参照窗口自身：第 90–94 对 95–99 轮均值之差、第 80–89 对 90–99 轮均值之差。
- 固定共同输入 cohort（`cohorts.csv.gz`，九个 run 一致）。逐人量 y_i = `completed_car_legs`（第 90–99 轮均值），Δ_i = y_i^政策 − y_i^基线（同 seed、同 `person_id`）。**重构检查：Σ_{i∈G} Δ_i = groups 的 completed 组差值，否则停止。**出发段数的 Δ = Σ Δ_i + 组残差（departures−completed 的差），残差单列，与 ε 比较。逐人没有按方式的出发段数，只有全方式的 departures（可分解 ΔT_i）；**所以只分解 completed，不冒充完整总纲个体分解**。
- 正负：P = Σmax(Δ_i,0)，N = Σmin(Δ_i,0)，净 = P+N，总量 = P+|N|，抵消 = 1−|净|/总量。只有 |净| ≥ ε 时才报告占比（探索性规则）。集中度：|Δ_i| 与负部分的洛伦兹曲线/前 1%、5%、10%、20% 占比，不对净值画。
- 比例指标：`share = C/T`，S_P−S_B = (ΔC − S_B·ΔT)/T_P；分子项 ΔC/T_P 与分母项 −S_B·ΔT/T_P 分开；按 joint 分组（六个）加总。
- 噪声参照 = **分布**：基线 3 个 seed 对（4711–4712、4711–4713、4712–4713）算同样统计量；不逐人减去。同 seed 非共同随机数：报告配对方差/不配对方差、同 seed 政策 vs 基线与跨 seed 基线 vs 基线的第 99 轮计划指纹相同比例。
- 3 个 seed，迭代自相关：每 seed 一个窗口均值为一个单位；只描述，不给 p 值或置信区间。
- 稳定标签分层的贡献：标签 = 基线 run 在 P=80–89 的用车状态稳定/不稳定（也报政策 run 自己的标签，标注受政策影响）；逐轮报告各层对 Σ(y_P − y_B) 的贡献。

## 6. 结论的边界（运行前写下）

- 稳定、可省计算、政策结论保留是三件事，互相不能推出；哈希相同不是安全复用的证明，哈希不同不说明差异多大。
- 数据只支持跨迭代动态与稀疏轨迹；没有 events，不能宣称找到了"可安全省略的集合"。
- 个体差值是描述性分解，不是个体因果。

## 7. 结果（2026-11-24，运行之后追加；前面的定义和阈值未改）

结果摘要和作业记录在文献工作区：`/Users/ww/Desktop/matsim/work_plans/preflight/execution_results.md`、`execution_progress.md`；小结果在 `results/s4/`；大矩阵在 ORCD `~/matsim-work/original-analysis/out-s4-20261124/`。

**偏离登记的两点（都是看到结果之后的事后处理，已在摘要里标明）：**
1. 总纲九项里 $9.18 的收费区相关小汽车出发段数：重算 −8716.47，总纲表 −8717，差 0.53，超出本文 §3.1 登记的 ±0.5，**严格门槛按字面未通过**。原因是原脚本 `+.5g` 打印后再取整（−8716.5→−8717），脚本里复现了这个二次舍入作为次级检查；未改总纲容差；政策分解在这个解释之上继续。
2. 图：按基线 P 窗口用车结果分层的逐轮贡献是条件于基线结果的假象，不进主图（数据在 CSV 里保留并注明）。

其余按 §3 的门槛全部通过（900 份文件完整、s3/s2 逐项一致、`departures = completed + stuck` 在 72,900 行上精确成立）。

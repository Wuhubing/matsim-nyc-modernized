# MATSim NYC: modernized exploratory congestion-pricing scenarios

A Java 25 / MATSim 2026.0 modernization of C2SMART's released NYC model, with a baseline, reconstructed Schema 1 cordon, and a modeled launch-2025 congestion-pricing policy. This is an independent research workspace, not an official MTA model or a validated forecast of 2025 outcomes.

## 本 fork 的二次开发：仿真加速（分支 `perf/simulation-redundancy`）

本 fork 基于 [harrrisw/matsim-nyc-modernized](https://github.com/harrrisw/matsim-nyc-modernized) 做二次开发。
目标是在**结果严格不变**的前提下缩短多轮 MATSim 仿真的耗时，并把仿真过程中的冗余整理成可以度量的研究问题。

### 优化内容与效果

测试条件：2025 收费情景，全人口 389,301，种子 4711，16 线程，12 轮，单次配对。

| | 原版 | 本 fork | 变化 |
|---|---:|---:|---:|
| 12 轮总耗时 | 2,139.9 s | 1,574.0 s | **−26.4%** |
| 交通仿真（mobsim）合计 | 1,611 s | 1,063 s | **−34%** |
| 输出体积 | 15.1 GB | 2.9 GB | −81% |
| 逐轮指标差异 | — | **0 项** | 计数和美分精确相等，其余 rtol 1e-9 |

1. **在线指标替代逐轮事件写出（E1，带来几乎全部收益）。**
   原版每轮把约 8,000 万条事件写成约 1.1 GB 的 XML，只为在离线阶段从中统计指标。写出发生在单一事件线程上，会拖慢交通仿真。
   新增 `IterationMetrics`（`-Dnyc.onlineMetrics=true`），在仿真过程中直接计算同一组指标：收费区进入、car leg 时长、候车与未上车、收费收入、未完成出行等。
   每轮写出 `iteration-metrics-N.json`，并配合 `controller.writeEventsInterval=0` 使用。
2. **收费与历史成本查表（E2）。**
   `Pricing2025` 和 `LegacyCosts` 原来在路由和事件处理中，每次调用都要把 link ID 转成字符串再查集合；现在改为按 `Id.index()` 预先算好的标志数组查表。
   结果逐位一致，但耗时变化在噪声范围内（短跑 −2.9%）。
3. **仿真冗余度量（研究部分）。** 逐轮比较 12 轮的事件，发现：
   - 只有 9–13% 的人被原样重放；
   - 约 40% 的人方式和路线不变，出行时间变化不超过 1 分钟；
   - 换计划的人里，回到自己以前试过的计划的比例从第 8 轮的 59% 升到关闭创新后的约 99%；
   - 交通状态的变化是全局性的，不是局部的。
   这说明剩余的耗时来自交通交互本身，需要用近似或学习方法处理。

### 如何验证结果不变

- `scripts/VerifyPricingReplay.java`：把一整轮真实事件重放给新代码，569,387 条收费事件按顺序完全一致；路由收费在 1.1 亿个 link × 时间单元上逐位一致。
- `scripts/ReplayIterationMetrics.java`：在线指标与离线扫描事件文件的结果完全相同。
- `experiments/performance/redundancy_campaign.py`：在独立账本上跑配对计时，并比较 12 轮逐轮指标。
- `experiments/redundancy/`：冗余度量脚本与中文方法说明（`README.md`）。

### 注意

- 开启 E1 后默认不写任何事件文件。依赖事件的工具（如 `scripts/compare.py`）需要时，可设 `writeEventsInterval` 等于最后一轮的轮号，这样只写第 0 轮和最后一轮。
- 以上为单一情景、单一种子的结果。只证明已观测指标一致，不涉及事件顺序、个体轨迹、收敛性或现实效度。
- 上游的署名与 GPL-3.0 许可证保持不变。

## Included

- Java source, Maven build, and synthetic regression checks.
- Compressed network, migrated synthetic population (389,301 agents), transit schedule/vehicles, mode vehicle types, and traffic counts: approximately 45 MB total repository size.
- Common model settings and the three policy scenarios, cordon geometry/link lists, and explicit capacity assumptions.
- Portable experiment launcher and event-analysis utility.

Raw simulation outputs, JDK/Maven installations, dependency caches, and compiled jars are excluded. The separate 10.9 GB population CSV is not required for these supplied simulation inputs.

## Setup

Install **JDK 25**, **Maven 3.9+**, and **Python 3.11+**. Put `java`, `javac`, and `mvn` on PATH, or set JAVA_HOME for the scripts. Downloads: [Java](https://adoptium.net/), [Maven](https://maven.apache.org/download.cgi), [Python](https://www.python.org/downloads/).

From the repository root:

```sh
mvn -DskipTests package
python scripts/verify.py
```

Maven downloads the pinned dependencies from Maven Central and the MATSim repository. A normal build uses no machine-specific dependency cache. Python's standard library suffices for the launcher; optional analysis packages install with `python -m pip install -r requirements.txt`.

## Run all three scenarios

```sh
python scripts/run_experiment.py --exploratory --iterations 1
```

This runs baseline, Schema 1, then 2025 policy sequentially, each for **iteration 0 only**, using a 16 GB Java heap. Allow additional system memory. Use `--heap 24g` if appropriate for your machine. Results, logs and completion-status files go into a unique `outputs/experiment-*` directory. Existing outputs are never overwritten. `--prepare-only` verifies input hashes and generates configs without launching a simulation. Increase `--iterations` to allow behavioral adaptation; one iteration is not convergence.

The baseline removes only the new congestion charge: historical facility tolls, parking and other fixed costs remain. All arms share the same input population, seed, road modes, scoring and capacity assumptions.

After a completed exploratory run, create the iteration-zero comparison chart and report:

```sh
python -m pip install -r requirements.txt
python scripts/compare.py outputs/experiment-YOUR-TIMESTAMP
```

The comparison tool currently measures iteration 0, even for longer experiments. It streams the three event files and reports common-boundary private-car crossings, completed car-leg times, congestion revenue and unfinished departures. It is intended for the exploratory profile; its labels explicitly describe the assumed capacity factors.

## Calibration boundary

The released ZIP hard-codes speed multipliers but loads capacity multipliers from external `theta_up_down{k}.csv` files not included in the release. No verified final capacity vector is available here. The strict no-argument Java runner therefore requires a separately supplied `scenarios/nyc-zip-aligned/capacity-factors.csv`.

`--exploratory` explicitly uses `assumptions/paper-capacity-factors.csv`: published-table values previously reconstructed for this workspace. Applying those values at the archive's 00/07/10/13/16/19/22 network-change times is a hybrid assumption, **not exact reproduction of the ZIP's calibration**. Alternatively provide a verified vector with `--capacity-factors PATH`; CSV header is `period,expressway,arterial` followed by six positive finite factor rows indexed 0..5.

The modernized profile restores QSim road simulation for car, taxi and FHV, archived speed multipliers and scoring coefficients. It does not add the previously inferred extra PT fare. Modern transit-walk compatibility and safer driver attribution remain deliberate changes. Engine versions differ; exact old-engine equivalence is not claimed.

## Pricing scope and limits

Schema 1 charges private cars on reconstructed entry and exit links ($9.18 in 06–10/14–20 peaks, $3.06 otherwise). The 2025 implementation models weekday E-ZPass charges ($9 first daily entry in 05–21, $2.25 overnight), selected tunnel credits, and participating taxi/FHV per-trip charges ($0.75/$1.50). Historical demand and transit inputs are not updated to 2025.

No explicit empty taxi fleet circulation is modeled. Truck, motorcycle, mail-payment, weekend, low-income and special-exemption categories are not comprehensively represented. Route-search toll costs approximate daily caps/credits even though realized billing is stateful. Zone mapping on the historical network is approximate. See source and [provenance](PROVENANCE.md) before interpreting outcomes.

## Example, not validation

![Exploratory iteration-zero comparison](docs/iteration0-comparison.png)

The chart is from three completed September 26, 2026 exploratory runs. It is retained as a small illustrative artifact; raw outputs are excluded. [Underlying metrics](docs/iteration0-comparison.json). Differences in cordon traffic are initial model responses, not observed 2025 effects. Mode-share adaptation needs further iterations; unfinished trips and geographic aggregation limit interpretation.

## Attribution

Based on [C2SMART Center, Code for MATSim-NYC project (2022), DOI 10.5281/zenodo.7430184](https://doi.org/10.5281/zenodo.7430184) and [the MATSim-NYC paper](https://arxiv.org/abs/2008.04762). Preserve upstream attribution and the supplied [GPL-3.0 license](LICENSE). Source data and boundary provenance are described separately in [PROVENANCE.md](PROVENANCE.md).

## Baseline diagnostics (full population, old fixed-entry capacities)

For the local side-by-side checkout with `../C2SMART-Year3-Project`, the diagnostic
runner extracts the **active** `ExpressFactor` and `ArterialFactor` arrays from
`RunTimeDependentNetworkExample.java`. These are old fixed-entry parameters, not
verified final calibration results. The old repository is read-only.

Place the local toolchain
paths in `.tools/environment.json` (`java_home`, `maven`), then use `--build-only`. The executor checks
`.tools/build-status.json` and `.tools/verify-status.json` for `exit_code: 0` and
copies their logs. The current task's verified installations and build evidence
are retained there. Use the virtual environment containing `zstandard`:

```sh
.venv/bin/python scripts/run_baseline_diagnostic.py --build-only
.venv/bin/python scripts/test_baseline_diagnostic.py
.venv/bin/python scripts/run_baseline_diagnostic.py --prepare-only
.venv/bin/python scripts/run_baseline_diagnostic.py --run-dir outputs/baseline-diagnostic-TIMESTAMP
.venv/bin/python scripts/run_baseline_diagnostic.py --analyze-only --run-dir outputs/baseline-diagnostic-TIMESTAMP
```

Preparation prints the exact run directory. Execution runs **only baseline**:
first iteration 0, then an independent run of iterations 0–4. Both retain the
full 389,301-person input, seed 4711, 16 threads, original behavioral settings and
capacity scaling. Input hashes are cached against file metadata. Each output
attempt is new and cannot overwrite another. Scripts and a runnable JAR are
snapshotted alongside commands, input identifiers and effective MATSim configs.

All simulation attempts share one persisted **eight-hour budget**. A directory
lock prevents concurrent executors. A failed or uncleanly interrupted attempt
requires inspection before resuming, and the existing budget must not be reset.
The budget includes process startup, shutdown and retries; preparation, building
and offline analysis are timed separately. The initial Java heap limit is 16 GiB;
one 24 GiB retry is allowed only for a clear heap OOM without resource pressure.
Heap size is not total process memory. RSS sampling runs every ten seconds;
macOS memory pressure, swap and disk checks run every minute. The executor stops
on less than 30 GiB free disk, critical memory pressure lasting 60 seconds, swap
growth over 2 GiB within five minutes, or budget exhaustion.

The short run retains innovation fraction 0.8 and therefore is **not the prefix
of a 0–100 run**. Actual strategy evidence, logs, resource samples and metrics
are saved per attempt. Stopwatch operations include callbacks and potentially
I/O; missing measurements remain blank. Offline historical-charge checks inspect
`personScore` events separately from added congestion-charge `personMoney`
events. Negative utility changes are not fiscal revenue or dollar welfare.
Successful diagnostics do not establish convergence, old-engine equivalence,
or real-world predictive validity.

## Fixed-plan bus capacity diagnostic

`scripts/run_bus_capacity_diagnostic.py` prepares two independent baseline iteration-0
runs using the selected plans serialized before iteration 4 of the recorded baseline
campaign. It preserves all 389,301 persons, disables replanning, and changes only bus
seats and standing capacity by a factor of two. Shared transit vehicles/types, if any,
are normalized in both arms before treatment is applied. The opt-in
`nyc.fixedPlanGuard` rejects initialization changes before traffic execution.

Use the project JDK 25 and Maven to build, then:

```sh
.venv/bin/python scripts/run_bus_capacity_diagnostic.py --prepare-only
.venv/bin/python scripts/run_bus_capacity_diagnostic.py --run-dir outputs/bus-capacity-diagnostic-TIMESTAMP
.venv/bin/python scripts/run_bus_capacity_diagnostic.py --run-dir outputs/bus-capacity-diagnostic-TIMESTAMP --analyze-only
.venv/bin/python scripts/test_bus_capacity_diagnostic.py
```

The two arms and retries share a persistent two-hour simulation budget. Analysis
includes censored waiting, re-identifies the control's full-vehicle cohort, and
separates target-leg completion from reaching the final scheduled activity.
`comparison.csv` uses treatment minus control. These are mechanism diagnostics,
not population-expanded forecasts, welfare estimates, or calibrated capacity targets.

# 交接说明：新会话从这里接上（最后更新 2026-10-15）

新会话开始时，先读本文，再按需要读下面列出的文档。用户用中文交流。

## 1. 读什么

| 顺序 | 文件 | 内容 |
|---|---|---|
| 1 | `docs/HANDOFF.md`（本文） | 现在的状态、在跑的作业、规则 |
| 1.5 | `docs/execution-plan.md` | **落地方向的执行计划**（10-15）：主线 M7（跨运行学习轨迹，短跑加预测），副线 M8（`StableReRoute`） |
| 2 | `docs/aggregate-regularity-plan.md` | **当前的工作计划**：利用总体层面的规律减少冗余（阶段 A/B） |
| 3 | `docs/matsim-nyc-findings.md` 第 0 节 | 全过程概览和主要结论 |
| 4 | `docs/project-log-detailed.md` | 每一步的详细记录（作业、提交、失败原因） |
| 5 | `docs/l2seg-replanning-plan.md` | 原计划和全部推导，主要看第 0 节（范围决定）、4.2（RQ0）、8.1（RQ1）、8.2（浪费分析和 E1/E2） |

## 2. 现在的状态

- **仓库：** `~/matsim-work/matsim-nyc-modernized`，推到 fork `Wuhubing/matsim-nyc-modernized`。
- **分支（10-15 起）：**
  - 总体规律方向的新工作（A2–A5、M3/M8 等）在 `research/aggregate-regularity` 上做。它从 `research/l2seg-replanning` 的 `4d997d8` 拉出来。
  - E1/E2 和 A1 的结果仍写回 `research/l2seg-replanning`（`l2seg-replanning-plan.md` 第 8.2 节），之后再合并到新分支。
  - 推送脚本的副本要用新分支名生成（第 3 节）。
- **研究方向：** 个人层面挑人（L2Seg 的直接类比）预测能力弱，已经放下。现在转向总体层面的规律，见 `aggregate-regularity-plan.md`。
- **在跑或排队的作业：**

| 作业 | 内容 | 输出 | 完成后要做 |
|---|---|---|---|
| ~~25891637~~ | E1：score MSA，baseline，种子 4711，100 轮，heap 24g。**10-15 第 52 轮 Java 堆内存不足，挂起 3 小时后取消**；前 51 轮数据在输出目录。重跑需要更大的堆（得分平均额外占内存），要用户决定 | `/orcd/scratch/orcd/006/weibingw/matsim-work/alg/e1-scoremsa-s4711-100it` | 见下面 E1/E2 的说明 |
| 25891638（已完成） | E2：创新退火 0.3 → 0.0001（第 79 轮到底）；最终得分 4.53、开车占比 0.376，停在差的状态 | `.../alg/e2-anneal-s4711-100it` | 同上；开跑后确认 `run.json` 里是 `-Xmx24g` |
| ~~25894285~~ | A1：已取消，10-15 改在登录节点跑完（12 秒） | `outputs/trajectory/trajectory-rq1.json` | 已写进 `aggregate-regularity-plan.md` 第 7 节 |
| 25897058–60 | 快照解析（`plan_snapshots.py`），三个种子各一个，4 核 8G | `outputs/aggregate/snapshots-s47xx/` | A2、A3 的输入 |
| 25897061 | A2（`best_state.py`），等快照完成 | `outputs/aggregate/a2-best-state.json` | 结果写进 `aggregate-regularity-plan.md` 第 7 节，按第 5 节关卡决定是否申请 B1 |
| 25897062 | A3（`group_stability.py`），等快照完成 | `outputs/aggregate/a3-group-stability.json` | 同上，决定 M3 |
| 25897063 | A4（`link_stability.py`），种子 4711 | `outputs/aggregate/a4-link-stability-s4711.json` | 同上，决定 M8 |

| 25929332 | M8 改目标的分析（`reroute_duplicates.py`），种子 4711：按方案内容和来源看重复找路的比例 | `outputs/aggregate/m8-reroute-duplicates-s4711.json` | 结果写进 `aggregate-regularity-plan.md` 第 7 节的 A4 之后，决定 `StableReRoute` 怎么改 |

（A2–A4 已于 10-15 完成，结果见计划第 7 节。）
（以上分析作业都在 `mit_preemptable`，带 `--requeue`；日志在 `outputs/aggregate/slurm-*.out`。）

- **JAR 还没重新编译：** M8（`StableReRoute`，10-15）只用 `javac` 编译到 scratchpad 做了合成检查，`target/` 里的 JAR 还是旧的。原因是 E1/E2 开始时会从 `target/` 复制 JAR。等 E1/E2 开始跑以后，再执行 `mvn -o -q package -DskipTests`；新代码只在设置了 `nyc.stableReRoute.threshold` 时才生效，不影响其他运行。
- **E1/E2 完成后：**
  - 和 RQ1 种子 4711（`/orcd/scratch/orcd/006/weibingw/matsim-work/rq1/baseline-s4711-100it-rq1`）对比：10 轮均值何时进入 RQ0 容差（`outputs/rq0/tolerance-baseline.json`）；每轮换计划和回到旧计划的比例（W1 日志，`labels.py`）；L-U 命中率；最终状态（得分、方式构成、屏幕线）。
  - 写进 `l2seg-replanning-plan.md` 第 8.2 节。
  - E1/E2 本身不减少轮数，它们是验证浪费诊断的对照，也是新方法必须超过的基准。
- **等用户决定的事：**
  1. 判断标准：严格标准（2σ）还是政策效应标准（见 `aggregate-regularity-plan.md` 第 4 节）；
  2. 阶段 B 的每个运行；
  3. 是否做每轮成本的精确优化（按时段缓存路段容量，先跑 12 轮验证结果一致）。

## 3. 规则（必须遵守）

- **集群（/etc/claude-code/CLAUDE.md）：**
  - 共享的 HPC，尽量少用 CPU、内存和 I/O；
  - 绝不遍历 `/orcd/scratch` 或 `/orcd/pool`，只访问已知的具体路径；
  - 配额看 `~/orcd/.quota`，不用 du；
  - 不在登录节点跑大任务，登录节点上的分析也要先问用户；分析作业放 Slurm。
- **用户的约束：**
  - 100 轮运行和数组作业必须先经用户同意；12 轮以内的验证运行可以跑，但要先告诉用户；
  - 结果写回对应文档的小节，推翻旧结论要明确写出；
  - 小步提交，推到 fork。
- **作业设置：**
  - 100 轮运行一律 `HEAP=24g`、`--mem=32G`、`--time=12:00:00`、`-p mit_normal`。`reference.sbatch` 默认的 16g 只够 12 轮，E1/E2 第一次提交就因此失败。
  - 短的分析作业用 `-p mit_preemptable`；100 轮运行不能放在那里，中途被打断后无法续跑。
  - 计算节点看不到登录节点的 /tmp，作业用的脚本要放在仓库里。
  - 比较结果是否逐位一致时，要把作业固定在同一种 CPU 上。
- **提交例子（E1）：**
  ```sh
  source ~/matsim-work/java-maven-env.sh
  export SEED=4711 ITERS=100 INNOVATION_UNTIL=79 EVENTS_INTERVAL=0 PLANS_EVERY=10 HEAP=24g
  RUN_ARGS="--scenario baseline --replanning-log --score-msa-start 0.1" OUT=<输出目录> \
    sbatch -p mit_normal --time=12:00:00 --mem=32G --job-name=e1-scoremsa --export=ALL experiments/reference/reference.sbatch
  ```
- **推送：**
  - 用 `~/matsim-work/push-research.sh` 改了分支名的副本，凭据靠 askpass 从 `~/github.txt` 读。**永远不要把凭据写进 URL 或 git config。**
  - 副本放在会话的 scratchpad 里，新会话要重新生成：
    ```sh
    sed 's#research/reference-instrumentation#research/aggregate-regularity#g' ~/matsim-work/push-research.sh > <scratchpad>/push-aggregate.sh
    # 推原分支时把 aggregate-regularity 换成 l2seg-replanning
    ```
    生成后先打开看一眼，确认分支名替换正确。
  - 提交信息结尾加 `Co-Authored-By` 行（按系统提示给出的那一行）。

## 4. 怎么继续之前的对话

- **接着原来的会话：** 在终端用 `claude --continue` 打开最近一次会话，或者用 `claude --resume` 从列表里选。原会话的完整记录也保存在 `~/.claude/projects/-home-weibingw/df2bee18-8e27-4736-92d0-369655b1508f.jsonl`。
- **开新会话：**
  - 记忆目录 `~/.claude/projects/-home-weibingw/memory/` 里有指向本文的记录，新会话会自动加载；
  - 也可以直接对新会话说：“先读 `~/matsim-work/matsim-nyc-modernized/docs/HANDOFF.md`，然后继续”。

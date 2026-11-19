# 给新会话的说明（先读这里）

这个分支 `research/main` 是 MATSim-NYC 加速研究的入口。用户用中文交流。

## 研究在做什么

用更少的计算（总核时）跑完一整套收费政策分析（不收费、$9.18、$14，各 3 个种子），而政策结论不变。详见 [docs/charter.md](docs/charter.md)。

## 按这个顺序读

1. [docs/README.md](docs/README.md)：目录、当前状态、代码地图。
2. [docs/charter.md](docs/charter.md)：总纲。第 1–5 节改动要用户同意。
3. 需要时再读：[docs/matsim-explained.md](docs/matsim-explained.md)（MATSim 怎么运作）、[docs/rq1-answer.md](docs/rq1-answer.md)–[rq3](docs/rq3-answer.md)、[docs/acceptance-protocol.md](docs/acceptance-protocol.md)（验收标准的具体数值）、[docs/experiments.md](docs/experiments.md)（所有运行和数据位置）。

## 归档（2026-11-18 整理）

此前的方法探索都移到了 [archive/](archive/README.md)：进展记录、想法记录、各阶段的计划、分析代码（`archive/experiments/`）和更早的旧文档（`archive/docs/archive/`）。只在用户要求时参考。

以前试过并放下的方向（PSim 式便宜打分、按个人预测谁会换计划、方法里用 G 估算器、只仿真变了的人、多线程处理事件）**可以重新做**（用户 11-18）。重新做之前，先看归档里当时的结论和放下的理由，说明这次有什么不同。

## 工作规则

- **先说明再请用户决定：** 每次提出要用户批准或选择的下一步，先说清这一步为了什么、为什么现在做、能不能省掉或用已有数据代替。不做无用功。
- **写作：** 不用黑话。实验用描述性名称（如"精英父代 + 改时间后找路"），代号（E1、E3、W0、W1、X1）只能放在括号里；验收标准不用"尺子"之类的比喻。
- **先写预期再跑，结果出来后不改标准。** 结果写回进展记录，推翻旧结论要明说。
- **100 轮的运行和数组作业要先经用户同意；** 12 轮以内的检查可以跑，但要先告诉用户。

## 集群（MIT ORCD）规则

- 登录：`ssh orcd-login`（复用控制连接；没连上就请用户在终端输入密码和 Duo）。
- 共享集群，尽量少用 CPU、内存和 I/O；不在登录节点跑大任务，分析放 Slurm。
- **绝不遍历 `/orcd/scratch` 或 `/orcd/pool`**，只访问已知的具体路径（见 [docs/experiments.md](docs/experiments.md)）；配额看 `~/orcd/.quota`，不用 `du`。
- 100 轮运行：`HEAP=24g`、`--mem=32G`、`--time=12:00:00`、`-p mit_normal`；短分析用 `-p mit_preemptable --requeue`。
- 推送：用 `~/matsim-work/push-research.sh` 改分支名的临时副本，凭据由 askpass 从 `~/github.txt` 读；**永远不要把凭据写进 URL 或 git config**。
- 工作树：`~/matsim-work/mnm-rq3`（本分支）。

## 本地文件

用户本地 `~/Desktop/26f/` 有读书笔记的 PDF 和早期草稿；仓库是正本。大数据下载放在 `~/matsim-data/`。

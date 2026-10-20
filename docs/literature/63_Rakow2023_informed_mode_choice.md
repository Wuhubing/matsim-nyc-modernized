# [63] Rakow & Nagel 2023 — 按估算效用提议换方式，并对"选择的随机程度"退火（informed mode choice）

- **论文：** Rakow & Nagel 2023, *An annealing based approach to informed mode choice in agent-based transport simulations*, Procedia Computer Science 220:667–673, DOI [10.1016/j.procs.2023.03.086](https://doi.org/10.1016/j.procs.2023.03.086)
- **代码：** matsim-libs 的 [`contribs/informed-mode-choice`](https://github.com/matsim-org/matsim-libs/tree/main/contribs/informed-mode-choice)（README、`SelectSubtourModeStrategy.java`、`ModeChoiceWeightScheduler.java`、`InformedModeChoiceConfigGroup.java`、`estimators/DefaultLegScoreEstimator.java`）
- **领域：** 1 MATSim 与智能体交通仿真
- **依据（2026-10-20）：** **论文全文还没读到**（ScienceDirect 拒绝脚本访问，需要用户下载）。下面的内容来自代码和 README，结果数字待补。

> 一句话：和离散方式选择扩展（[62](62_Hoerl2018_discrete_mode_choice.md)）一样，用估算的效用来提议换方式；不同的是，选择时的"温度"随轮次退火：一开始接近随机，逐渐变成只挑估算最好的。另外可以剪掉明显没有希望的候选。

## 1. 它怎么替换随机换方式（代码）

主策略 `SelectSubtourModeStrategy` 是 MATSim 的一个"试新方案"策略，每次给一个人：

1. 以一定概率只改一段出行的方式；否则随机挑一段出行链（subtour）；
2. **生成候选：** 把这段出行链整体换成每一种方式，再加上估算最好的前 k 种组合（默认 k = 5）；
3. **估算效用：** 默认的估算器按 MATSim 打分配置算方式常数、距离、出行时间和按距离计的费用；公交另有估算器；可以加每天的固定费用。还有一个基于伪随机误差的估算器（`PseudoRandomTripScoreEstimator`），对应 Hörl 2021 的哈希误差；
4. **剪枝（可选）：** 去掉比最好候选差太多的候选，或者按距离规则剪掉；
5. **选择：** 按 logit 概率选，温度参数 1/β 默认无穷大（等于随机选）；
6. **退火（可选）：** `ModeChoiceWeightScheduler` 在试新方案的那些轮里，把 1/β 从初始值按线性、二次、三次、指数或余弦曲线降到 0。降到 0 时，就是每次都挑估算最好的那个。

## 2. 会不会改变最后评估

**不会。** 它仍然只是一个试新方案的策略：新方案照常执行、打分，照常在计划之间按得分选择；退火也只在试新方案的轮次里进行。关掉试新方案后，最后评估那一段完全不变。和离散方式选择扩展一样，提议方式变了，终点可能不同，仍然要用九项政策效应检验。

## 3. 报告了多少加速

**待读全文后补充。**

## 4. 对我们意味着什么【推断】

- 它把两个我们关心的想法放在了一起：**按效用提议**（[../ideas.md](../ideas.md) 想法 1 的第 2 步）和**探索强度逐渐降低**（总纲第 4.3 节记录的退火想法）。而且已经在 MATSim 2026 的代码里，可以直接配置。
- **和离散方式选择扩展同样的缺口：** 默认估算器不含道路收费，用在收费场景前要加上。
- **和我们之前试过的"创新退火"不同：** 之前那个是降低试新方案的人数比例（早期试验停止发现过早，终点明显偏离）；这里人数不变，降低的是"挑哪种方式"的随机程度。
- 两个扩展哪个更适合我们，要等读完这篇的结果再比较。

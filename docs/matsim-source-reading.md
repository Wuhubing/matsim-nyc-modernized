# MATSim 2026.0 源码阅读：replanning 循环的实际行为

- **开始**：2026-10-17
- **源码**：`matsim-org/matsim-libs` tag `2026.0`（提交 `c7a75eb`，2026-04-10），稀疏克隆在 `26f/src/matsim-libs-2026.0`（只取 `matsim/src/main/java` 和 `contribs/roadpricing`）
- **对应版本**：matsim-nyc-modernized 的 `pom.xml` 用 `matsim.version = 2026.0`
- **记法**：每条结论标出文件和行号；【推断】表示我们的解读，不是代码直接写明的

## 要核实的问题

1. 创新时复制哪个计划
2. 找路用的通行时间：时间分箱多大，是不是只用上一轮
3. 删计划的规则
4. 每类策略在各人群中的实际抽取方式

（以下各节边读边写）

## 1. 每一轮 replanning 的执行顺序（`GenericStrategyManagerImpl.run`）

文件：`matsim/src/main/java/org/matsim/core/replanning/GenericStrategyManagerImpl.java`

对每个人，按顺序（第 223–248 行）：

1. 如果这个人的计划数 **大于** `maxPlansPerAgent`，先删计划，直到等于上限（第 230–232 行，`removePlans`）。
2. 按这个人所在子人群的权重抽一个策略（第 239–240 行）。
3. 执行这个策略（第 247 行）。

所有人处理完之后，各策略的 `finish()` 才运行（第 251–253 行）。多模块策略的第二个及以后的模块，例如 SubtourModeChoice 之后的 ReRoute，是在 `finish()` 里对本轮所有新计划**批量**处理的（`GenericPlanStrategyImpl.finish`，第 121–133 行）。

**含义**
- 删计划发生在**本轮新计划生成之前**。所以本轮新建的计划一定会先被执行一次，下一轮才可能被删。
- 一个人在本轮创新后最多有 `maxPlansPerAgent + 1` 个计划（NYC 为 6 个）参与本轮仿真和打分，下一轮 replanning 开始时再删回 5 个。

## 2. 策略怎么抽（问题 4）

文件：`choosers/WeightedStrategyChooser.java`（第 15–26 行）

```java
double rnd = MatsimRandom.getRandom().nextDouble() * weights.getTotalWeights();
// 依次累加权重，第一个累计和 >= rnd 的策略被选中
```

- 每个人**独立**抽一次，概率 = 策略权重 / 本子人群权重总和。权重按子人群分别存放（`weightsPerSubpopulation`，第 79 行），不同子人群之间互不影响。
- 所以"30% 的人创新"是**期望值**：每人独立以 0.3 的概率抽到某个创新策略，实际人数每轮随机波动。不是精确挑出 30%。
- 权重在运行中可以改：`addChangeRequest` 登记"第几轮把某策略权重改成多少"，每轮开始时 `handleChangeRequests` 生效（第 284–298 行、325–340 行）。关闭创新（`disableAfterIteration`）就是通过这个机制把权重改成 0 实现的【待核实：在 `StrategyManager` 里】。

NYC 配置（`config-baseline.xml`）：`man` 和 `nonman` 都是 SelectExpBeta 0.7、TimeAllocationMutator 0.1、ReRoute 0.1、SubtourModeChoice 0.1；`outside` 只有 SelectExpBeta 1.0。

## 3. 每个策略实际做什么（问题 1）

文件：`GenericPlanStrategyImpl.run`（第 71–110 行）

**所有策略**（包括 SelectExpBeta）都先做同一件事：

```java
T plan = new RandomUnscoredPlanSelector<T, I>().selectPlan(person);  // 第 75 行
if (plan == null) plan = this.planSelector.selectPlan(person);       // 第 78–80 行
person.setSelectedPlan(plan);
```

- 只要这个人有**还没打过分**的计划（`score == null`），就随机挑一个未打分的计划执行，不管抽到的是什么策略。只有所有计划都有分时，才用策略自己的选择器。
- 对创新策略：接着把选中的计划**复制一份并设为选中**（`createCopyOfSelectedPlanAndMakeSelected`，第 94 行），记下创建轮次和来源（第 97–101 行），然后交给模块修改。

各策略的选择器（`strategies/*.java`）：

| 配置名 | 选择器（挑哪个计划来复制或执行） | 修改模块 |
|---|---|---|
| SelectExpBeta | `ExpBetaPlanSelector` | 无（只选择） |
| ReRoute | **`RandomPlanSelector`**（`ReRoute.java` 第 45 行） | ReRoute |
| TimeAllocationMutator | **`RandomPlanSelector`**（`TimeAllocationMutator.java` 第 40 行） | 只改时间，**不重新找路** |
| SubtourModeChoice | **`RandomPlanSelector`**（`SubtourModeChoice.java` 第 47 行） | SubtourModeChoice，然后 ReRoute（第 48–49 行） |
| TimeAllocationMutator_ReRoute | `RandomPlanSelector` | 改时间，然后 ReRoute |

`RandomPlanSelector`（`selectors/RandomPlanSelector.java`）：在这个人的所有计划里**均匀随机**挑一个，不看分数。

**结论（问题 1）**
- 三种创新都从记忆里**均匀随机**挑一个计划来改，最多 5 个里可能挑到最差的那个。这证实了仓库 H1 分析的判断："找路和改时间常从差的方案出发"。
- NYC 用的是 `TimeAllocationMutator`，不是 `TimeAllocationMutator_ReRoute`：改了出发时间以后**不重新找路**，路线沿用原计划（路线是按原来的出发时间算的）。【推断】改时间后的计划在新时段可能走的是不合适的路线，这会拉低改时间试探的成功率。
- `RandomUnscoredPlanSelector` 是强制机制：新计划在下一轮一定会被执行（如果它在本轮未被执行）。【推断】由于新计划在创建当轮就被设为选中并执行，正常情况下它在当轮就得到分数，这一机制主要处理初始未打分的计划和外部加入的计划。

**补充（复制计划时的得分）**：`PersonImpl.createCopyOfSelectedPlanAndMakeSelected`（第 79–89 行）调用 `PopulationUtils.copyFromTo(old, new, true)`，后者第 946 行 `out.setScore(in.getScore())`：**新计划继承父计划的得分**，在被执行之前不是"未打分"。所以对创新产生的计划，`RandomUnscoredPlanSelector` 不会起作用；它只对初始或外部加入的、确实没有分数的计划起作用。

## 4. 得分怎么更新

文件：`core/scoring/NewScoreAssignerImpl.java`（第 56–100 行）

每轮仿真后，只对每个人**被执行的那个计划**（`person.getSelectedPlan()`）更新得分：

| 情况 | 更新 |
|---|---|
| 旧得分为空 | S ← s̃（本轮仿真得分） |
| 未到 score MSA 起点 | S ← α·s̃ + (1−α)·S，α = `learningRate`（默认 1.0，`ScoringConfigGroup` 第 1672 行） |
| 到了 score MSA 起点之后 | 每个计划自己计数 n，α = 1/(n+1)，S ← α·s̃ + (1−α)·S |

- NYC 没有设 `learningRate`，所以是默认 1.0：**得分 = 最近一次执行的仿真得分**，不做任何平均。
- **没被执行的计划，得分不变**，停留在它上次被执行时的路况下的值。【推断】记忆里的 5 个计划，得分来自不同的轮次、不同的路况，选择时直接比较这些不同时点的得分。
- 新计划第一次执行时，旧得分是继承来的父计划得分。α = 1 时被完全覆盖，不受影响；α < 1 时，第一次评估会混入父计划的得分。
- score MSA 的起点 = (lastIteration − firstIteration) × fraction + firstIteration（第 47–50 行）。代码注释（第 104 行起）承认：这不是严格的 MSA，因为一个计划不是每轮都被评估。

## 5. 选择：ExpBeta

文件：`selectors/ExpBetaPlanSelector.java`

P(选中计划 j) = exp(β·(S_j − max S)) / Σ_k exp(β·(S_k − max S))，β = `brainExpBeta`（默认 1.0，`ScoringConfigGroup` 第 1673 行）。NYC 没有设，所以 β = 1。

- 这是在**当前存储的得分**上做 logit，每轮重新抽，和上一轮选了什么无关（SelectExpBeta；ChangeExpBeta 才是"从当前计划切换"的形式）。
- 【推断】β = 1 时，两个计划得分差 1 分，选中概率比约 2.7 倍；差 0.5 分约 1.6 倍。仓库测到的选择差距均值约 0.6 分，所以选择者经常不选最好的计划，这是"选择噪声"的来源。

## 6. 删计划（问题 3）

文件：`selectors/GenericWorstPlanForRemovalSelector.java`；默认 `planSelectorForRemoval = WorstPlanSelector`（`ReplanningConfigGroup` 第 425 行），NYC 没有改。

规则：
1. 统计每种计划类型（`plan.getType()`）的数量；
2. 在**数量 > 1 的类型**里删得分最低的（没有分数的优先删）；
3. 如果所有类型都只有一个，就在全部计划里删得分最低的。

- 【推断】NYC 的计划没有设类型，全部属于同一类，所以就是**删存储得分最低的那个**。这个得分可能是很多轮以前的（第 4 节）。
- MATSim 自己在配置说明里写道："WorstPlanSelector is not a good choice from a discrete choice theoretical perspective. Alternatives, however, have not been systematically tested."（`ReplanningConfigGroup` 第 285–288 行）

## 7. 关闭创新

文件：`core/replanning/StrategyManager.java`（第 77–100 行）

- 全局关闭轮 = (lastIteration − firstIteration) × `fractionOfIterationsToDisableInnovation` + firstIteration，取整。NYC：(99 − 0) × 0.8 = 79.2 → 79。
- 对每个不是"纯选择"的策略，登记一个修改请求：**第 80 轮起权重改成 0**（`addChangeRequest(maxIter + 1, …, 0.0)`）。如果策略自己设了更早的 `disableAfterIteration`，用更早的那个。
- 之后只剩 SelectExpBeta，每个人每轮只在已有计划里按 ExpBeta 选。仓库的 RQ0/RQ1 用 `disableAfterIteration = 79` 实现同样的效果。

## 8. 找路用的通行时间（问题 2）

文件：`core/trafficmonitoring/TravelTimeCalculator.java`；`config/groups/TravelTimeCalculatorConfigGroup.java`

- **时间分箱**：默认 900 秒（15 分钟，配置组第 56 行）；NYC 没有改。分箱内取平均（`travelTimeGetter = "average"`，第 55 行）。
- **只用上一轮**：`reset(iteration)`（第 414–430 行）在每轮开始时把所有路段的通行时间数据清空。所以第 k 轮 replanning 时，ReRoute 看到的是**第 k−1 轮仿真**测到的通行时间，没有跨轮平均。
- 没有车经过的时间箱，用自由流速度；并且做一致性修正：一个时间箱的通行时间不能比前一个箱减少超过箱长（`consolidateData`，第 451–478 行）。
- 返回值 = max(车辆最高速度对应的时间, 观测时间)（第 489–514 行）。
- NYC 设了 `separateModes = true`，`analyzedModes` 含 car、FHV、taxi 等：每种网络方式分别统计通行时间。

**结论（问题 2）**
- 找路是对**上一轮路况**的最优反应（15 分钟分箱）。【推断】这在交通分配里叫"朴素调整"：每次都对上一轮的状态求最优，没有平滑。如果很多人同时换到同一条路，下一轮这条路就堵，形成振荡。仓库在路段层面观察到"噪声加少数路段振荡"，和这个机制一致。

## 9. 换方式怎么提议

文件：`core/population/algorithms/ChooseRandomLegModeForSubtour.java`（第 219–238 行）；`SubtourModeChoiceConfigGroup`

- 构造所有可行的（子行程，方式）组合，然后**均匀随机**挑一个（第 238 行 `choiceSet.get(rng.nextInt(choiceSet.size()))`）。不看效用、不看路况。
- 默认 `chainBasedModes = car, bike`，`considerCarAvailability = false`，`probaForRandomSingleTripMode = 0`（第 44–50 行）。NYC 只设了 `modes`（8 种方式），其余用默认。
- 换方式之后接着做 ReRoute（`SubtourModeChoice.java` 第 48–49 行），也是用上一轮的通行时间。
- 【推断】这和仓库测到的结果一致：随机换方式第一次评估的中位数比之前最好的低 8–10 分，71% 明显更差。

## 小结：四个问题的答案

| 问题 | 答案 | 位置 |
|---|---|---|
| 1. 创新时复制哪个计划 | 在记忆里**均匀随机**挑一个（`RandomPlanSelector`），不看得分；复制品继承父计划得分 | `strategies/ReRoute.java:45`、`TimeAllocationMutator.java:40`、`SubtourModeChoice.java:47`；`PopulationUtils.java:946` |
| 2. 找路用的通行时间 | 只用**上一轮**仿真，每轮清空；15 分钟分箱，箱内平均 | `TravelTimeCalculator.java:414–430`；`TravelTimeCalculatorConfigGroup.java:55–56` |
| 3. 删计划 | 计划数超过 5 时，在下一轮 replanning 开头删**存储得分最低**的；得分可能过时 | `GenericStrategyManagerImpl.java:230, 266–278`；`GenericWorstPlanForRemovalSelector.java` |
| 4. 策略抽取 | 每人每轮按本子人群的权重**独立**抽一次；30% 是期望值；第 80 轮起创新权重置 0 | `WeightedStrategyChooser.java:15–26`；`StrategyManager.java:77–100` |

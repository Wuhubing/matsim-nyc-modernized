# [15] Hansen & Ostermeier 2001 — Completely derandomized self-adaptation in evolution strategies (CMA-ES)

- **Venue**: Evolutionary Computation 9(2):159–195
- **Domain / Tier / Priority**: Evolutionary algorithms / 1 / Medium
- **Link**: 表中 Harvard cse-lab 链接 ⚠️ **现在返回的是 HTML 页面，不是 PDF**。全文取自作者 Hansen 的公开版本 cmap.polytechnique.fr/~nikolaus.hansen/cmaartic.pdf（含勘误页）。
- **依据**: ✅ 已读全文（含勘误页、§1–8、附录 A MATLAB 代码）。pdftotext 把公式和部分数字转成乱码，**关键数字（图 11–13 图注、§7.4 正文、§8 结论）按 PDF 原图逐页核对**。标【推断】的是我们的映射。

> 一句话（摘要）：提出变异分布自适应的两个方法：**derandomization**（自适应信号直接来自被选中的变异步，而不是额外随机扰动参数）和 **cumulation**（用演化路径，而不是单步）。由此得到 **CMA**，可适应任意正态变异分布。在完全良好缩放的函数上，有无 CMA 性能相当；在**缩放很差且不可分的函数上，加速可达几个数量级**；在中度缩放失调的函数上，加速约 3–10 倍。

## 1. 瓶颈（原文 §1）
- 性能定义为"(expected) number of required objective function evaluations to reach a certain function value"。
- 只有很窄的一段策略参数取值能取得实质进展，而且好的取值因问题而异，并在搜索中变化"possibly by several orders of magnitude"。

## 2. 手段
- 变异分布逐级一般化：各向同性（1 个参数）→ 各轴独立方差（n 个）→ 任意方向的椭球（n(n+1)/2 个，即完整协方差）。
- mutative strategy parameter control 的原则缺陷 → derandomized：直接用被选中的步更新分布。
- cumulation：演化路径（累积多代的移动），用于协方差更新和步长控制。
- §2 的一般原则：参数的变化速率有上限，因为每代的选择信息有限，"Greater changes cannot rely on valid information and lead to stochastic behavior"；要适应的参数越多，单个参数的变化速率就必须越小。
- 三条设计原则：(1) 提高再次产生被选中步的概率；(2) 显式控制变化速率；(3) **随机选择下策略参数保持平稳**（没有选择信号时不应漂移）。
- 结论把它类比为从梯度法到 quasi-Newton：CMA 在迭代中近似逆 Hessian，不需要额外的搜索空间信息。

## 3. 省在哪一项
**目标函数评估次数**。

## 4. 快了多少，代价是什么（原文）
- 摘要：缩放很差、不可分函数上快几个数量级；中度失调时快 3–10 倍；完美缩放时没有优势。
- §7.4 全局搜索（n = 20，各 30 次运行，按原图核对）：
  - 标准 Rastrigin：CMA-ES 与 MUT-ES 表现相近（图 11）；
  - 轴比 1:10 的缩放 Rastrigin：MUT-ES 的函数值差 **20 倍**（图 12）；
  - 轴比 1:1000：差 **10,000 倍**，且 MUT-ES 要多约 10 倍评估（图 13）；CMA-ES 约 3·10⁴ 次评估。
  - 作者解释：适应分布形状后步长被调得更大，反而改善全局搜索。
- §7.3：CMA-ES 在除球函数外的所有测试函数上都明显快于只调全局步长的 PATH-ES，评估次数随维数在 n 到 n² 之间增长。
- **代价与限制（§8 原文）**：要可靠地适应变异分布形状的显著变化，"at least roughly 10n function evaluations"；实际问题中"unrealistic to expect the adaptation to improve strategy behavior before, say, 30n function evaluations"；完全适应可能要 100n² 次评估。所以建议计算资源能支持约 100 到 200(n+3)² 次评估。

## 5. 怎么证明结果没变
在测试函数上比较达到目标函数值所需的评估次数；强调**不变性**（对搜索空间的线性变换、目标函数值的单调变换不变），认为这是评价搜索算法的重要依据（§6）。

## 6. 假设
- 连续搜索空间，单目标，可以对候选解排序（选择只依赖排名，这是 ES 稳健性的主要来源）。
- 不需要导数。
- 主体实验在无噪声函数上。§5.1–5.2 提到：选择信息不足（噪声、与选择无关的参数）时策略参数会做随机游走；对"strongly disturbed problems"应选更小的协方差变化率 c_cov。

## 7. 能否用于 MATSim？怎么用
**🟡 需要大幅改造，只适用于连续部分：**
- 【推断】MATSim 的方案空间是混合的：路径和 mode 离散，活动结束时间连续。CMA 思路只能用于 **TimeAllocationMutator**（目前是"在可配置范围内随机平移"，[03](03_Horni2016_MATSim_book.md) §4.5.1.1），即学习"哪些活动时间该一起变、往哪个方向、变多大"。
- **§8 的评估次数下限是关键障碍**：【推断】一个 agent 有 n 个活动时间（例如 3–5 个），可靠适应就需要约 10n–30n 次评估，而每个 agent 每轮最多执行一个新方案，探索期只有约 80 轮，每轮创新概率约 10–30%。**单个 agent 的样本远远不够**，只能按人群类型池化，或者只做全局步长适应（1/5 规则或累积步长控制，见 [14](14_Eiben1999_parameter_control.md)）。
- 噪声和非平稳（其他 agent 在变）：原文没有专门处理，但 §2 和 §5.2 的原则可以直接借用：【推断】MATSim 的得分噪声大，每轮可用的"选择信息"少，所以 approach 2 中权重或变异幅度每轮的调整幅度必须很小；并且在没有有效信号时（创新得分与旧方案无显著差异）参数应保持不动，而不是随机漂移。
- Zhuge 2021 原文提到 MATSim 早期用过"covariance matrix adaptation evolution strategy"来加速（引用 Charypar 2006、Waraich 2015），需要查这条线具体做了什么，避免重复。

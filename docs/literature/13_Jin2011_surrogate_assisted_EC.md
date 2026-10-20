# [13] Jin 2011 — Surrogate-assisted evolutionary computation: Recent advances and future challenges

- **Venue**: Swarm and Evolutionary Computation 1(2):61–70，DOI 10.1016/j.swevo.2011.05.001
- **Domain / Tier / Priority**: Evolutionary algorithms / 1 / Medium
- **Link**: https://pub.uni-bielefeld.de/record/2978603 — Bielefeld 记录**没有上传文件**；该页面还有反爬验证。
- **依据**: ⚠️ **未读到全文，只核对了摘要**（Surrey 机构库页面）。Crossref 和 OpenAlex 均标为 closed access，ScienceDirect 返回 403。旧版笔记中写的具体内容（如 infill 准则、集成模型等章节）**无法从原文核实，已删除**。 2026-10-19 重查 OpenAlex：仍为 closed access，没有开放版本，**需要你通过图书馆获取全文**。

> 一句话（摘要）：surrogate（元模型）辅助的进化计算用计算便宜的模型近似适应度函数。该领域自约十年前起步，已用于计算昂贵的单目标和多目标优化，以及**动态**、约束、多峰优化。本文简要回顾历史与近期进展，并提出未来方向。

## 1. 瓶颈
同 [12 Jin 2005](12_Jin2005_fitness_approximation_survey.md)：真实适应度评估昂贵。

## 2. 手段
摘要只列出应用领域：单目标和多目标、**动态**、约束、多峰。具体方法需要读全文。

## 3. 省在哪一项
真实评估次数（与 2005 年综述同一框架）。

## 4. 快了多少，代价是什么
摘要未提及。

## 5. 怎么证明结果没变
摘要未提及。

## 6. 假设
未核实。从摘要看，覆盖了**动态优化**（适应度随时间变化），这与 MATSim 适应度的非平稳性相关。

## 7. 能否用于 MATSim？怎么用
**🟡 依赖全文，目前只能给方向：**
- 【推断】本文对我们的增量价值在"动态优化中的 surrogate"一节。MATSim 中一个方案的得分取决于其他 agent 的选择，适应度景观随迭代变化，属于动态问题。需要读全文确认作者对动态问题给出了哪些模型管理策略。
- 在拿到全文之前，RQ1 的论证以 [12 Jin 2005](12_Jin2005_fitness_approximation_survey.md)（已读全文）为主。
- **待办**：通过图书馆获取全文。

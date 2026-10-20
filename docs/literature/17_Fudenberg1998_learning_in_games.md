# [17] Fudenberg & Levine 1998 — The Theory of Learning in Games

- **Venue**: MIT Press（专著，276 页），ISBN 0262061945
- **Domain / Tier / Priority**: Learning in games / 1 / Medium（参考书）
- **Link**: https://jmvidal.cse.sc.edu/lib/fudenberg98a.html（书目和出版社简介）
- **依据**: ⚠️ **没有读到正文**：没有合法的免费 PDF。已核对的有：(1) 表中链接上的出版社简介；(2) 作者 Levine 网站上的完整目录（dklevine.com/papers/TOC.HTM，2000-08-01 更新）。旧版笔记中关于各章结论的具体表述（如"势博弈中 FP 收敛"）**不能以本书为出处引用**，对应结论改为引用已读全文的 [18 Hofbauer & Sandholm 2002](18_Hofbauer2002_stochastic_fictitious_play.md)。

> 一句话（出版社简介）：传统上，均衡被解释为共同知识下理性分析的结果，这在概念和实证上都有问题。本书提出另一种解释：**均衡是不完全理性的参与者随时间"摸索最优"的长期结果**。书中的模型为均衡理论提供基础，也为评估和修改传统均衡概念提供思路。

## 目录中与 RQ1 相关的章节（作者网站目录）
- Ch.2 Fictitious Play：§2.4 "The Interpretation of Cycles in Fictitious Play"，§2.8 FP 与 best response dynamic。
- Ch.3 Replicator dynamics：§3.9 "Set Valued Limit Points and Drift"。
- **Ch.4 Stochastic Fictitious Play and Mixed Strategy Equilibria**：§4.2 Notions of Convergence；§4.4 随机扰动收益与平滑最优回应；**§4.5 Smooth Fictitious Play and Stochastic Approximation**；§4.9 Learning About Strategy Spaces；附录：随机逼近理论。
- Ch.5 Adjustment Models with Persistent Randomness：Kandori–Mailath–Rob、吸引域的 radius/coradius、随机稳定性（附录：有限 Markov 链）。
- Ch.7 §7.3 Exogenous Experimentation；§7.4 博弈学习与 bandit 问题的比较。

## 1–6. 七问
本书是参考书，没有"仿真加速"实验，第 1–5 问不适用。第 6 问（假设）以 [18](18_Hofbauer2002_stochastic_fictitious_play.md) 为准。

## 7. 能否用于 MATSim？怎么用
**🟡 作为理论参考书，按需查阅具体章节：**
- 【推断】最相关的三处（按目录）：
  1. §4.4–4.5：**平滑 FP + 随机逼近**。MATSim 的 logit 选择（ChangeExpBeta）加上得分平滑在结构上接近这一框架（[03](03_Horni2016_MATSim_book.md) §47.3.2.2 也说得分平均"somewhat similar to fictitious play"）。
  2. §4.9 "Learning About Strategy Spaces"：与 MATSim 的**创新（策略集在扩展）**直接相关。博弈学习文献大多假设策略集固定，这一节可能是少数讨论策略集学习的地方，值得查阅。
  3. Ch.5 随机稳定性与吸引域：与"多重均衡、停在哪个均衡"相关（参见 [11](11_Watling2003_day_to_day_dynamics.md)）。
  4. §7.3–7.4 外生试验与 bandit 问题：与"探索 vs 利用"相关。
- **待办**：通过图书馆借阅，至少读 §4.5、§4.9、Ch.5。

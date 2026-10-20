# [11] Watling & Hazelton 2003 — The dynamics and equilibria of day-to-day assignment models

- **Venue**: Networks and Spatial Economics 3(3):349–370，DOI 10.1023/A:1025398302560
- **Domain / Tier / Priority**: DTA & traffic equilibrium / 1 / High（与 RQ3 相关）
- **Link**: https://eprints.whiterose.ac.uk/84674（作者接受稿 PDF）
- **依据**: ✅ 已读全文（作者接受稿）。标【推断】的是我们的映射。

> 一句话：把经济均衡（UE/SUE）、确定性动力系统和随机过程（Markov）三类 day-to-day 模型放进同一框架。结论：均衡可能不唯一，也可能不稳定；调整速度太快会导致振荡；随机过程模型的平稳分布可能是**双峰**的。**单次模拟可能长期停留在初值附近的那个峰，完全看不到另一个峰**；要得到精度可接受的平稳性质，往往需要非常长的模拟（"tens of thousands of days"）。

## 1. 瓶颈（原文）
- §4.4：用模拟估计平稳分布有两个难点：(1) 要丢弃 burn-in，"How long should this burn-in period be?"；(2) Markov 结构导致序列相关，真实标准误"considerable higher"于 σ/√N，所以需要的模拟天数比想象的多。
- 多重吸引子时："not only lack of precision is a problem, but also bias in equilibrium estimates may occur over long simulation runs"。

## 2. 手段 / 分析内容
- §2：扰动分析。即使是经典均衡模型也需要"稳定性"作为第三个合理性条件（存在、唯一之外），可以用来剔除不稳定的均衡。
- §3 确定性动力系统：例子中调整率 α 在 0 < α < 1/2 时均衡局部稳定，否则不稳定；可能存在 3 个 SUE（f₁ ≈ 3.60、8.40、9.95），两个稳定、一个不稳定，各有吸引域。
- §4 随机过程：
  - 平稳分布的形状随敏感度参数 θ 变化：θ 小时单峰；θ = 10 时呈双峰 (0.50, 0, 0.50)，模拟表现为在两个状态之间近乎周期地来回跳。
  - Example 8：**动态完全不同的两个过程可以有相同的平稳分布**；记忆长度 m > 1 时，差异还会影响均衡性质（逐日自相关在均衡中也持续存在）。
  - 多重吸引子：m = 1 时平稳分布双峰，模拟中偶尔在两个 SUE 之间转移；**m = 10 时，"simulations over many thousands of days are likely to see no transitions"**，单次模拟一直停在初值附近。

## 3. 省在哪一项
不适用（理论）。§4.4 和结论建议用**近似方法**（如 Davis & Nihan 的高斯自回归近似）代替模拟，从而免去长时间模拟。

## 4. 快了多少，代价是什么
不适用。核心权衡（§3）：调整越快越容易不稳定或振荡，越慢越稳定。

## 5. 怎么证明结果没变（原文建议）
- 跑**许多并行模拟**，用截面平均和 95% 预测区间（§4.4）。
- 丢弃 burn-in；考虑序列相关对标准误的影响（文中引用 MCMC 诊断文献）。
- 平稳分布不是全部：还要看动态和自相关（Example 8）。

## 6. 假设
- 小网络、只有路径选择、within-day 静态。
- 结论（§5）：在一定正则条件下，Markov 分配模型的均值平稳流量**随需求增大收敛到 SUE**；当 logit 离散参数 → ∞ 时，逐日演化趋近确定性动力模型。

## 7. 能否用于 MATSim？怎么用
**✅ 理论框架直接可用，对验证设计很关键：**
1. **"加速后停在不同均衡"的风险是实打实的**。【推断】MATSim 的方案记忆（默认 5 个方案）和得分平滑相当于"长记忆 m"。按本文 m = 10 的结论，单次运行可能永远停在初值附近的吸引子。所以 RQ2 必须用**多种子 × 两种方法**比较分布，并检查各运行落在哪个峰。[05 Ben-Dor](05_BenDor2021_population_downscaling.md) 在 MATSim 里已经观察到 3/100 次运行收敛到不同的 UE，与本文一致。
2. **"相同平稳分布 ≠ 相同动态"**（Example 8）。【推断】加速方法改变的是动态，只要平稳分布相同，就可以说"均衡没变"。这正好是我们需要的论证框架。
3. **burn-in 和序列相关**：【推断】给 RQ3 提供依据。要用 ESS 或考虑自相关的标准误（见 [25 Vehtari](25_Vehtari2021_improved_Rhat.md)），而不是把各轮当作独立样本。
4. 结论里"用近似方法代替模拟"的思路与 PSim、surrogate 的方向一致（[03](03_Horni2016_MATSim_book.md)、[34](34_Peherstorfer2018_multifidelity_survey.md)）。

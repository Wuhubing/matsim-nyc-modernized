# [31] Lamperti, Roventini, Sani 2018 — Agent-based model calibration using machine learning surrogates

- **Venue**: Journal of Economic Dynamics and Control 90:366–389（2018）；已读的是 LEM 工作论文版 2017/11（2017-10-03）
- **Domain / Tier / Priority**: Other ABMs / 2 / Medium
- **Link**: https://www.lem.sssup.it/WPLem/2017-11.html → PDF：lem.sssup.it/WPLem/files/2017-11.pdf（该站 SSL 证书有问题，用跳过证书校验的方式下载）
- **依据**: ✅ 已读工作论文全文（36 页：§1–6、附录 A 伪代码与 XGBoost 细节、附录 B 与 kriging 的比较）。⚠️ 期刊版的数字可能与工作论文版不同，引用前请对照期刊版。标【推断】的是我们的映射。

> 一句话（摘要）：把机器学习与**智能迭代采样**结合，用有限次 ABM 运行"学"出一个快速 surrogate 元模型，近似 ABM 输入（初始条件、参数）与输出之间的非线性关系。在 Brock–Hommes 资产定价模型和"Islands"内生增长模型上测试：surrogate 是真实模型相当准确的代理，并"dramatically reduce the computation time"。

## 1. 瓶颈（原文 §1）
- 参数越来越多（宏观 ABM 有几十个参数），直接估计和全局敏感性分析的计算量"computationally prohibitive"，存在维数灾难。
- 每组参数都要完整运行 ABM（还要多个种子）。

## 2. 手段（§3）
- surrogate = **XGBoost**（梯度提升树），不需要对响应面形状做假设。也可以选更快的线性 Logit。
- 两种标签：二值（参数是否满足标定标准，即"positive calibration"）或实值（标定距离）。
- 参数池用 Sobol 准随机序列抽样；初始训练集建议至少 100 个点，保证至少有一个正例；surrogate 的超参数用 Nelder–Mead 自动调。
- 迭代采样（主动学习）：用 surrogate 预测参数池，每轮从**预测为正**的点中随机抽 log(预算) 个去跑真实 ABM 并加入训练集；没有正预测时用**不确定性采样**（按标签熵，偏向 surrogate 难以判断的区域）。重复直到用完 ABM 运行预算。

## 3. 省在哪一项
**运行次数**（不是单次运行内的迭代数）。

## 4. 快了多少，代价是什么（原文数字）
- Brock–Hommes：在 10,000 个样本外点上，surrogate **预测快约 500 倍**；二值情形 F1 在预算 2500 时约 0.80，能找到约 75% 的正例；实值情形预算 500 时 TPR 约 70%，预算 2500 时接近 95%。
- Islands 模型：surrogate **快约 3750 倍**。
- 二值情形的 F1 在 Islands 模型上很快饱和在约 0.8；实值情形 TPR 在预算 2500 时达到 0.9，MSE < 0.08。
- §5.4 稳健性（Islands 的随机版本，每个参数点跑 100 个种子取平均，预算 500，参数池 100 万点）：Logit 精度 94.17%，XGBoost 94.72%，XGBoost 经 Platt 校准后 **99.35%**。所以简单的 Logit 也够用，校准概率很重要。
- 附录 B：在 Islands 模型上，预算 50 和 500 时 XGBoost surrogate 的样本外 MSE 都比 kriging 好；kriging 的计算量随点数按 O(n³) 增长。
- 预算的经验法则：画"性能 vs 运行次数"曲线，斜率开始下降就停止加点。
- 代价：surrogate 是近似，会漏掉部分正例（假阴性）；需要初始训练集和预算；作者指出模型越贵，节省越多。作者也说找到的参数区域"should be performed using the original ABM"做进一步检查。
- 注意：Brock–Hommes 部分正文一处写评估集为 100,000 点，图注和计时段落写 10,000 点，原文前后不一致。

## 5. 怎么证明结果没变
在大量**样本外**参数点上，用 F1、TPR、MSE 比较 surrogate 预测与真实 ABM 输出（每种设置训练 100 次）。

## 6. 假设
- 参数到输出（或到"是否满足标定"）的映射能被树模型学到。
- ABM 的随机性用固定种子处理（原文说 seed 固定）；只有 §5.4 的稳健性检验用了 100 个种子的平均。
- 作者说两个模型都可能有多重均衡；Remark 1–2 明确假设正例可能分散在多个不相连的区域，响应面可能是"knife-edge"的，所以不用平滑假设。
- 计算都在一台 16 GB 内存的笔记本上完成；大模型的应用"currently under development"，即没有在大规模 ABM 上验证。

## 7. 能否用于 MATSim？怎么用
**🟡 两种用法：**
1. **原本的用途（外循环）**：MATSim 行为参数的标定，或我们自己方法的超参数搜索（阈值、自适应速率），都可以用"分类器 + 主动学习"减少完整运行的次数。这属于 RQ1 中次要的"运行次数"一格。
2. **迁移到单次运行内部（更有意思）**：【推断】把分类器用在**创新层面**。输入 agent 特征、创新类型、时段、当前 gap 等，输出"这次创新会被保留"的概率，只执行高概率或高不确定度的创新。训练数据来自运行中的创新日志（在线积累），或同一场景的历史运行（离线训练）。本文"从预测为正的点里抽 + 不确定性采样"的机制，可以直接对应为"执行预测有效的创新 + 一部分高不确定度的创新"，防止 surrogate 的偏差锁死探索（与 [12](12_Jin2005_fitness_approximation_survey.md) 的 evolution control 思想一致）。
- 【推断】§5.4 的结果提示：创新层面的分类器不需要很复杂，Logit 加概率校准可能就够了，这样在线更新的成本很低。
- 区别要注意：本文的输入输出映射是静态的（固定种子、固定模型），而 MATSim 创新的有效性依赖于当前的交通状态，是非平稳的，模型需要在线更新。

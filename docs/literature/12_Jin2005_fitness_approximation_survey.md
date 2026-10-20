# [12] Jin 2005 — A comprehensive survey of fitness approximation in evolutionary computation

- **Venue**: Soft Computing 9(1):3–12，DOI 10.1007/s00500-003-0328-5
- **Domain / Tier / Priority**: Evolutionary algorithms / 1 / High
- **Link**: https://www.cs.le.ac.uk/people/sy11/ECiDUE/Jin-SC05.pdf — ⚠️ **该链接现已失效（404）**，全文取自 Internet Archive 2024-04-16 快照：web.archive.org/web/20240416102134/https://www.cs.le.ac.uk/people/sy11/ECiDUE/Jin-SC05.pdf（作者稿，页眉标注"Published in: Soft Computing, 9(1), pp. 3-12, 2005"）
- **依据**: ✅ 已读全文。标【推断】的是我们的映射。

> 一句话：EA 需要大量适应度评估，评估贵或没有显式函数时，就需要近似模型。综述三个层次的近似（问题近似、函数近似、进化近似）、近似模型嵌入 EA 的方式、**模型管理（evolution control）**和建模技术。核心警告：只用近似模型很可能收敛到**假最优（false optimum）**，必须和原始适应度函数配合使用。

## 1. 瓶颈（原文 §1–2）
- "a large number of fitness evaluations … are needed before a well acceptable solution can be found"。例如 3D CFD 一次计算在高性能计算机上要十几个小时。
- 其他动机：没有显式适应度模型（如人工评价）；**适应度有噪声**；多峰景观需要平滑。

## 2. 手段
- **近似层次（§3）**：
  - 问题近似：用简化物理替代，如 Euler 方程代替 N–S 方程；
  - 函数近似：元模型（多项式响应面、Kriging、NN、SVM）；
  - 进化近似：fitness inheritance（子代从父代估计）、fitness imitation（聚类后只评估代表个体）。
- **嵌入方式（§4.1）**：
  - 通过迁移（island model，不同子种群用不同精度的模型）；
  - 用于初始化、交叉、变异（"lower requirement on the model quality … can help so long as the prediction of the model is better than random guess"，但节省多少不清楚）；
  - **直接用于适应度评估**（最能减少评估次数，但风险最大）。
- **模型管理（§4.2）**：
  - 无控制：只用模型，有风险；
  - **individual-based**：每代部分个体用原函数评估，可以用"best strategy"（按模型排名的最好个体用原函数重评）或"random strategy"；
  - **generation-based**：每隔若干代整代用原函数评估；
  - **adaptive**：按模型精度调整控制频率（如信赖域框架）。原文指出固定频率可能"cause strong oscillation during optimization due to large model errors"。
- 一个有趣做法（引 [22]）：给适应度估计加置信区间，鼓励搜索未探索区域，在多峰问题上效果更好。

## 3. 省在哪一项
**原始适应度评估次数**。

## 4. 快了多少，代价是什么
- 综述**没有给统一的节省比例**。旧版笔记中"一般节省 50–90%"是我编的，**已删除**。
- 代价（原文）：假最优；高维、样本少时难以建立全局准确的模型；§7 指出"It is theoretically still unclear in which way the evolutionary algorithm can benefit from the approximate model"；近似模型"do not create new information"，只是防止历史信息丢失。

## 5. 怎么证明结果没变
综述没有统一的验证范式。原文强调两个要求：(1) EA 要收敛到**原始**适应度函数的全局最优或近似最优；(2) 计算成本尽量低。

## 6. 假设
- 主体讨论的是**静态**适应度函数（同一个解的适应度不随时间变化）。
- 噪声作为一种动机被讨论，处理方法是邻域平均或重复采样。
- 不需要梯度。

## 7. 能否用于 MATSim？怎么用
**🟡 需要改造，但思路最对口（直接针对"85% 创新无效"）：**
- 【推断】对应关系：个体 = agent 的一个候选方案；原始适应度 = 方案在 mobsim 中执行后的得分（要等一整轮仿真）；近似模型 = 用上一轮出行时间重算的得分（PSim 正是这样，[03](03_Horni2016_MATSim_book.md)），或学到的"保留概率"模型（[31](31_Lamperti2018_ABM_ML_surrogate.md)）。
- 【推断】三种嵌入方式在 MATSim 中的对应：
  1. 用于**生成创新**（引导变异方向）：对模型精度要求最低，最安全，但节省多少不确定；
  2. 用于**筛选创新**（只执行预测会改进的创新）：省得最多，风险是假最优；
  3. 必须有 **evolution control**：保留一部分不经筛选、直接执行的创新（random strategy），并持续用执行结果更新模型。
- 必须改的地方：MATSim 的适应度**非平稳**（取决于其他 agent），超出本综述"静态适应度"的主体假设，所以模型必须在线更新。
- 【推断】与 PSim 的区别：PSim 相当于"generation-based"（整代交替 PSim/QSim）；Jin 的框架提示可以做 individual-based 的选择性控制，这是更细的粒度。

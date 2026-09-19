# 第一轮离线评估解读（2026-09-19）

本轮使用已冻结的 21 个 scenarios 和同一个 500 首 candidate pool。
Baseline 共 668 次运行：Random 630 次、Basic CBF 17 次、Context+MMR 21 次。
四个单因素对照各运行 38 次（只运行 CBF 和 Context+MMR）。
完整歌单、每首歌的分数和分项证据在 `recommendation-runs.json`；
统计在 `summary.json` / `summary.csv`，对照差值在
`parameter-comparison.json` / `.csv`。相应 manifest 记录 checksum。

## 主要观察

- 转场类情境中，Context+MMR 的平均 mood match 为 0.925914，Basic CBF 为
  0.716463，Random 为 0.663768。CBF 不读取指定 mood，因此这个差异符合
  算法设计；它**不是**用户满意度或准确率。
- 同一类情境中，Context+MMR 的平均 history match 为 0.830368，Basic CBF 为
  0.861646。加入 mood 目标后，历史贴合度可能下降，属于需要权衡的现象。
- MMR 改为 relevance:diversity = 60:40 时，转场类 Context+MMR 的平均
  歌单内部多样性从 0.154974 升到 0.206826；history match 从 0.830368
  降到 0.811211。Basic CBF 不使用 MMR，因此其结果没有变化。
- history:mood 从 65:35 改到 50:50 时，转场类的 mood match 从 0.925914
  升到 0.940557，history match 从 0.830368 降到 0.818372。
- 将 relevance 的 weighted cosine 换成 weighted Euclidean 时，转场类的
  history match 从 0.830368 升到 0.877573，而 mood match 从 0.925914
  降到 0.866668。这是本数据与这组代理指标上的结果，不足以宣布哪一种距离最优。

## 必须保留的限制

- 这些是音频特征代理指标，没有人工相关性标注、歌词语义判断或 user testing。
  不能把高 mood match 解读为“听众真的觉得快乐/平静”。
- `transition_energetic_to_calm` 的 Context+MMR Top-1 是童谣
  *Itsy Bitsy Spider*；其输入历史也含 *The Wheels on the Bus*。
  数值上可以匹配 calm，实际歌单语义却可能不合适。这正是
  `scenario-approval.md` 所记录的已知风险的实际表现。
- Random 每个 seed 对同一个 pool 抽样，不读取 history/mood，所以同一 seed
  在不同情境得到相同歌单。30 个 seed 用来观察随机抽样的波动，不是 30 个
  独立用户或 30 组主观评价。
- distinct artist fraction 在多数分组接近 1，对目前 500 首 pool 的区分力弱。
  processing time 是本机运行时间，重跑会变化。

结论：目前已经能稳定生成可追溯的推荐歌单与参数对照，但还不能依据这一轮
代理指标单独确定“最佳”配置。现有 65:35 与 80:20 继续作为正式 baseline；
其他配置保留为对照，不自动改动生产算法。

# 2.2 Feature Weights 与 Similarity Metric：暂定结论

本研究只比较 Basic CBF，不运行 Random、mood fit 或 MMR。输入是已冻结的 17 个
history scenarios；每个配置在同一批 500 首候选歌曲上排序并取 Top-10。
原有 `current + weighted cosine` 的 17 张 Top-10 已与上一轮 baseline 逐一核对一致。
六个主配置构成 3 套权重 × 2 种相似度的完整矩阵；另外三组 current/cosine
移除 energy、valence 或两者，重新归一化剩余权重。正式默认值没有改变。

## 主要结果

下表以 `current + cosine` 为参照，Jaccard 是 17 个情境各自 Top-10 Jaccard 的
平均值；“第一名变化”是第一名不同的情境数。Jaccard 越低，只说明歌单变动越大，
**不说明哪一套更准确**。

| 配置 | 平均 Top-10 Jaccard | 第一名变化 | 全 500 首分数的平均 SD | 平均 Top-1/Top-10 分数差 |
| --- | ---: | ---: | ---: | ---: |
| current + cosine | 1.000 | 0/17 | 0.1043 | 0.0066 |
| equal + cosine | 0.636 | 10/17 | 0.1100 | 0.0085 |
| literature + cosine | 0.436 | 10/17 | 0.0971 | 0.0056 |
| current + Euclidean | 0.280 | 14/17 | 0.0962 | 0.0333 |
| equal + Euclidean | 0.269 | 13/17 | 0.0978 | 0.0338 |
| literature + Euclidean | 0.226 | 15/17 | 0.0863 | 0.0281 |

为了避免把两个变量混在一起，`factorial-summary.csv` 还保存配对比较：
固定 Euclidean 时，current→equal 的平均 Jaccard 为 0.585，current→literature
为 0.401；固定 equal 权重时，cosine→Euclidean 为 0.382；固定 literature
权重时，cosine→Euclidean 为 0.329。不同权重、不同 metric 均明显改变排序，
其变化幅度取决于另一项设置，不能只看与默认配置的一次比较。

Cosine 的 Top-10 分数在本数据上非常接近：current/cosine 的 17 张歌单平均
Top-1/Top-10 gap 只有 0.0066，170 首 Top-10 歌曲的平均分为 0.9915；
其中 45 个现有 explanation 把分数四舍五入写成 `1.00`。Current/Euclidean
的平均 gap 为 0.0333，Top-10 平均分为 0.9146。**但是**全 500 首候选歌曲的
平均分数 SD 是 cosine 0.1043、Euclidean 0.0962；因此不能笼统地说
“cosine 在所有候选歌曲上都更集中”。两种 metric 的刻度不同，gap 或均分
较大也不能直接解释成推荐质量较好。

## Energy 与 valence 的敏感性

在 current/cosine 基础上移除单项并重新归一化后：移除 energy 的平均
Top-10 Jaccard 为 0.431、第一名变化 7/17；移除 valence 为 0.289、第一名
变化 13/17；两项都移除为 0.169、第一名变化 16/17。这说明当前排序对两项
特征，尤其在这批情境中的 valence，十分敏感。但“直接移除”是强烈扰动，
不能据此断言目前的 0.25/0.25 权重不合理，更不能在没有主观 relevance
标注时选出最佳权重。

## Artist、genre 与处理时间

各配置的 artist HHI 大约为 0.10–0.11，接近 10 首歌曲均来自不同艺人的
最低值 0.10；genre HHI 也大约为 0.10–0.12。因此在这个固定 pool 和 Top-10
长度下，这两项集中度对选择配置的区分力有限。多标签 genre 按每首歌曲
贡献总量 1 的方式分配。处理时间只计已预热的 `rank_cbf`，不包括数据库、
向量建立或输出文件；它不是 REST API 的端到端 latency，也会随机器负载变化。

## Explanation 的人工抽查

以 `single_happy_anchor` 为例，current/cosine 的第一名是 *Romantic Sunday*
（score 约 0.9979），current/Euclidean 的第一名是 *House of Gold*
（score 约 0.9492）。两种配置的现有解释都说“Strong audio-feature match”，
并强调 energy/valence 相近；这没有清楚解释第一名为何改变。现有解释把
`feature_closeness × weight` 当作证据排序，且使用固定 0.90/0.75 文字门槛；
这不是 weighted cosine 的精确逐项贡献，也没有针对 Euclidean 的
`weight × squared_difference` 提供精确距离分解。上述说明属于**解释保真度
风险**，不是证明某条解释必定错误。生产解释代码此次保持不变。

就数学分解而言，Euclidean 的逐项平方距离较容易直接展示“哪些绝对差异
拉远了候选歌曲”；cosine 也可以分解加权点积，但还涉及两侧向量范数，
不能直接把普通绝对接近度当成贡献。若以后要对外提供精确的 feature-level
解释，应另开代码修改与测试，不应通过本离线实验悄悄改变 API 文案。

## 暂定判断与限制

本次证实权重和相似度都显著影响同一批歌曲的排序，并且 Euclidean 在
Top-10 内提供更大的数值分数间隔。它**没有**证明 Euclidean、equal 或
literature-informed 权重更符合用户喜好。文献权重原本来自不同预测任务，
只作为实验对照，不能称为 literature-proven optimum。Equal weights 也只
表示系数相同；特征分布不同，实际影响仍可能不同。

因此保留 `current + cosine` 为正式默认值，把其余配置视为候选与研究结果。
下一步若要选择新默认值，需要人工评价实际歌单与解释，最好再加入用户对
单首歌曲及整张歌单的反馈。当前 scenarios 仍是先前暂时接受、带备案的版本；
这些数值结果应按探索性研究解读。

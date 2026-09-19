# Scenario acceptance record

Date: 2026-09-19
Decision: accepted provisionally as written; no track substitutions.
Draft SHA-256: `544ec158523cce4968d797e1b5270f877b57a09e9ac5fa871f42c77efea5449b`
Frozen scenario count: 21

中文备案：项目负责人表示尚未完全理解各情境的具体差别，但暂时接受现有 21 个情境，
不替换歌曲，并要求保留记录。本次接受仅允许建立第一版离线实验基线，
不代表逐首人工核实，也不代表参数已经最优。

The project owner accepted the proposed 21 scenarios while noting that the
practical differences were not fully clear yet. This approval permits the
first offline baseline and comparisons; it is not a claim that the scenarios
or parameter values are optimal or that every title was manually validated.

Known caveats retained in this frozen version:

- `coherent_pop` is numerically/genre-coherent but mixes language and cultural
  contexts (Indian film/pop tracks and GAYLE). Interpret it as an audio-feature
  test, not proof of semantic playlist coherence.
- `transition_energetic_to_calm` contains *The Wheels on the Bus* as a recent
  calm track. Its feature profile fits the selection rule, but it is a
  children's song and can make a real listening playlist feel inappropriate.

If a later qualitative review changes these tracks, create a new protocol
version and keep this baseline intact for reproducibility.

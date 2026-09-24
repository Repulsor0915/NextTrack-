 # 1. Directory purpose

  先用一小段说明 domain 的职责：

  # Recommendation Domain

  This directory contains the core ranking logic used by NextTrack.

  The modules receive prepared candidate tracks and normalized audio-feature
  vectors, calculate recommendation scores, rerank the candidates, and produce
  evidence for recommendation explanations.

  可以补充边界：

  Database queries, API request handling, authentication, and response
  serialization are handled by the surrounding service and API layers.

  ———

  # 2. Supported recommendation modes

  保留现有表格：

   Mode           Required input         Main operation                   Output
  ━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   random         Candidate tracks       Random sampling                  Random baseline
  ─────────────  ─────────────────────  ───────────────────────────────  ─────────────────────────────
   cbf            Listening history      Audio-feature similarity         Similar tracks
  ─────────────  ─────────────────────  ───────────────────────────────  ─────────────────────────────
   context_mmr    History and/or mood    Context score followed by MMR    Relevant and diverse tracks

  然后解释：

  `auto` is a routing option used by the API. It selects one of the three
  recommendation modes according to the available request signals.

  ———

  # 3. Recommendation flow

  这一部分可以让读者快速理解文件之间的关系：

  flowchart LR
      A[Candidate tracks] --> B[Feature vectors]
      H[Listening history] --> C[Session profile]
      M[Requested mood] --> D[Mood score]

      B --> E[CBF or context ranking]
      C --> E
      D --> E

      E --> F[MMR reranking]
      F --> G[Explanation evidence]
      G --> I[Recommendation response]

  下面补充三条流程：

  - Random: candidates → random sampling
  - CBF: history profile → feature similarity → ranking
  - Context + MMR: history and/or mood → relevance score → diversity reranking

  ———

  # 4. Module responsibilities

  这是当前 draft 最值得补充的部分。

  ## Module responsibilities

   File                       Responsibility
  ━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   algorithm_config.py        Stores validated algorithm settings, feature weights, similarity metrics, and ranking ratios.
  ─────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   feature_vectors.py         Builds listening profiles and calculates feature-vector similarity.
  ─────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   cbf_ranker.py              Ranks candidates using similarity to the recent listening profile.
  ─────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   context_ranker.py          Combines history similarity and mood fit into contextual relevance.
  ─────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   mood_model.py              Defines mood profiles and calculates mood fit.
  ─────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   mmr.py                     Reranks relevant candidates to improve recommendation diversity.
  ─────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   random_ranker.py           Provides the random experimental baseline.
  ─────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   explanation_evidence.py    Collects numerical evidence used by explanations.
  ─────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   explanations.py            Converts recommendation evidence into user-facing text.
  ─────────────────────────  ───────────────────────────────────────────────────────────────────────────────────────────────
   model_versions.py          Stores public identifiers for the reviewed algorithm versions.

  ———

  # 5. Audio-feature assumptions

  列出算法使用的八项 feature：

  ## Audio features

  The ranking models use eight normalized audio features:

  - tempo
  - energy
  - valence
  - danceability
  - acousticness
  - instrumentalness
  - loudness
  - speechiness

  然后说明重要前提：

  The domain layer expects these values to have already been normalized into
  the range `[0, 1]`. Feature extraction and normalization are performed before
  the candidates enter the ranking functions.

  还可以说明：

  Every candidate vector and session profile must contain all eight feature
  names.

  ———

  # 6. Main formulas

  你现有 draft 的公式可以保留。

  ## CBF

  similarity = weighted_cosine(session_profile, candidate_vector)

  说明：

  - Session profile 怎么产生。
  - 默认最多使用五首历史歌曲。
  - Basic CBF 使用 equal average。
  - Context mode 使用 recency weighted average。

  ## Context relevance

  relevance = 0.65 × history_similarity + 0.35 × mood_fit

  需要说明：

  - 同时有 history 和 mood 才使用加权组合。
  - 只有 history 时，relevance 等于 history similarity。
  - 只有 mood 时，relevance 等于 mood fit。

  ## MMR

  mmr_score = (1 - diversity_strength) × relevance
            + diversity_strength × (1 - maximum_similarity)

  说明默认 diversity_strength = 0.20。

  ———

  # 7. Configuration

  保留当前 AlgorithmConfig 的介绍，但可以缩短：

  ## Configuration

  `algorithm_config.py` is the single source of truth for ranking parameters.

  The configuration controls:

  - audio-feature weights;
  - relevance similarity metric;
  - diversity similarity metric;
  - history window size;
  - history-profile strategy;
  - history and mood relevance weights;
  - mood-feature weights;
  - MMR diversity strength.

  然后说明配置是 frozen dataclass，以保证一次实验运行期间不会被修改。

  ———

  # 8. Input and output contracts

  这是 README 应该增加的重要内容。

  ## Input expectations

  Ranking functions receive candidate pairs in the following form:

  ```python
  (candidate, feature_vector)

  A feature vector is a dictionary containing the eight normalized features.

  {
      "tempo": 0.52,
      "energy": 0.71,
      "valence": 0.64,
      ...
  }


  输出说明：

  ```markdown
  Each ranker returns immutable ranking objects such as:

  - `CbfRanking`
  - `ContextRanking`
  - `MmrRanking`
  - `MoodScore`

  These objects retain both the final score and the evidence required by later
  stages.

  ———

  # 9. Determinism and tie breaking

  说明相同输入如何获得稳定结果：

  ## Determinism

  CBF and contextual ranking are deterministic for the same candidates,
  configuration, and user context.

  Equal scores are resolved using the candidate ID as a stable tie breaker.

  The random baseline accepts an injected seeded random source for repeatable
  tests and offline evaluation.

  ———

  # 10. Explanation design

  将现有 explanation 内容整理成：

  ## Recommendation explanations

  Explanation generation has two stages:

  1. `explanation_evidence.py` records the numerical values used during ranking.
  2. `explanations.py` converts selected evidence into user-facing text.

  Explanation functions describe completed ranking decisions. They do not
  modify candidate scores or final positions.

  还应说明 feature_closeness 是描述性指标，并非 cosine similarity 的独立 feature contribution。

  ———

  # 11. Model versioning

  保留现有内容并加入何时更新：

  ## Model versioning

  `model_versions.py` contains the public identifiers used in API metadata and
  offline evaluation results.

  A version should be updated when a change affects observable ranking behaviour,
  such as:

  - changing feature weights;
  - changing a scoring formula;
  - changing the history-profile method;
  - changing MMR behaviour;
  - changing the explanation contract.

  MOOD_MODEL_VERSION 目前放在 mood_model.py，README 中也可以说明。

  ———

  # 12. Limitations

  FYP README 应该主动说明限制：

  ## Current limitations

  - Mood targets are project-defined engineering values rather than learned user-specific targets.
  - Audio similarity cannot fully represent lyrics, language, culture, or personal meaning.
  - The model uses a limited recent-history window.
  - MMR diversity is calculated from the same eight audio features.
  - Feature weights may not generalize equally across every music catalogue or user group.

  ———

  # 13. Tests and evaluation

  说明在哪里验证：

  ## Testing and evaluation

  Unit tests cover:

  - session-profile construction;
  - cosine and Euclidean similarity;
  - CBF ranking;
  - context relevance;
  - mood fit;
  - MMR reranking;
  - random baseline reproducibility;
  - explanation evidence;
  - stable tie breaking.

  Offline evaluation is performed separately using fixed catalogue snapshots and
  experiment configurations.

  如果知道准确测试文件，再加入对应路径。

  ———

  # 14. References

  列出真正使用过的理论来源，例如：

  ## References

  - Content-based filtering and cosine similarity
  - Carbonell and Goldstein (1998), Maximal Marginal Relevance
  - Panda et al. (2021), audio-feature importance for music emotion recognition

  最终引用应包含作者、年份、标题、期刊或会议及 DOI/URL。

  ———

  ## 建议最终目录

  1. Directory purpose
  2. Recommendation modes
  3. Recommendation flow
  4. Module responsibilities
  5. Audio features
  6. Ranking formulas
  7. Algorithm configuration
  8. Input and output contracts
  9. Determinism
  10. Recommendation explanations
  11. Model versioning
  12. Limitations
  13. Testing and evaluation
  14. References

  你现有 draft 可以保留第 2、6、7、10、11 部分，主要需要补上 流程图、文件职责、输入输出要求、确定性、限制和测试说明。
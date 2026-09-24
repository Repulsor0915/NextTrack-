"""One validated configuration shared by every offline study."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


SCHEMA_VERSION = "nexttrack-offline-evaluation-v2"
STUDY_NAMES = ("catalogue", "configuration", "comparison", "performance")


@dataclass(frozen=True)
class EvaluationConfig:
    """Values that define one reproducible evaluation run."""

    seed: int = 221611
    candidate_count: int = 500
    top_n: int = 10
    random_repetitions: int = 30
    candidate_artist_policy: str = "allow_missing"
    history_windows: tuple[int, ...] = (1, 5)
    history_mood_ratios: tuple[tuple[float, float], ...] = (
        (1.0, 0.0),
        (0.65, 0.35),
        (0.5, 0.5),
        (0.0, 1.0),
    )
    mmr_strengths: tuple[float, ...] = (0.0, 0.2, 0.4)
    performance_fresh_repetitions: int = 5
    performance_warm_repetitions: int = 10

    def __post_init__(self) -> None:
        if self.candidate_count < self.top_n:
            raise ValueError("candidate_count must be at least top_n.")
        if self.top_n < 1:
            raise ValueError("top_n must be positive.")
        if self.random_repetitions < 1:
            raise ValueError("random_repetitions must be positive.")
        if self.candidate_artist_policy not in {"allow_missing", "require_known"}:
            raise ValueError(
                "candidate_artist_policy must be 'allow_missing' or 'require_known'."
            )
        if not self.history_windows or any(value < 1 for value in self.history_windows):
            raise ValueError("history_windows must contain positive integers.")
        if any(
            history < 0
            or mood < 0
            or abs((history + mood) - 1.0) > 1e-9
            for history, mood in self.history_mood_ratios
        ):
            raise ValueError("Every history/mood ratio must be non-negative and sum to 1.")
        if any(not 0.0 <= value <= 1.0 for value in self.mmr_strengths):
            raise ValueError("MMR strengths must be between 0 and 1.")
        if self.performance_fresh_repetitions < 1:
            raise ValueError("performance_fresh_repetitions must be positive.")
        if self.performance_warm_repetitions < 1:
            raise ValueError("performance_warm_repetitions must be positive.")

    def to_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, value: dict) -> "EvaluationConfig":
        supplied_version = value.get("schema_version", SCHEMA_VERSION)
        if supplied_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported evaluation schema: {supplied_version!r}.")
        fields = {
            key: item for key, item in value.items() if key != "schema_version"
        }
        for name in ("history_windows", "mmr_strengths"):
            if name in fields:
                fields[name] = tuple(fields[name])
        if "history_mood_ratios" in fields:
            fields["history_mood_ratios"] = tuple(
                tuple(pair) for pair in fields["history_mood_ratios"]
            )
        return cls(**fields)


def load_config(path: Path | None) -> EvaluationConfig:
    """Load a JSON config, or return the documented defaults."""

    if path is None:
        return EvaluationConfig()
    return EvaluationConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))

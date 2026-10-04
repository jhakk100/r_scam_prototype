import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .errors import ConfigurationError
from .validation import number, positive_integer


@dataclass(frozen=True)
class RagConfig:
    k_retrieve: int = 8
    k_max: int = 5
    tau: float = 0.60
    gap_threshold: float = 0.12
    gamma: float = 1.0
    kappa: float = 1.0

    def __post_init__(self):
        positive_integer(self.k_retrieve, "k_retrieve", ConfigurationError)
        positive_integer(self.k_max, "k_max", ConfigurationError)
        if self.k_retrieve < self.k_max:
            raise ConfigurationError("k_retrieve >= k_max가 필요합니다.")
        tau = number(self.tau, "tau", ConfigurationError, 0, 1)
        if tau == 1:
            raise ConfigurationError("tau는 1 미만이어야 합니다.")
        number(self.gap_threshold, "gap_threshold", ConfigurationError, 0)
        for key in ("gamma", "kappa"):
            if number(getattr(self, key), key, ConfigurationError) <= 0:
                raise ConfigurationError(f"{key}는 양수여야 합니다.")


@dataclass(frozen=True)
class FormulaConfig:
    alpha: float = 1.0
    beta: float = 1.0
    fusion_mode: str = "q"

    def __post_init__(self):
        if number(self.alpha, "alpha", ConfigurationError) <= 0:
            raise ConfigurationError("alpha는 양수여야 합니다.")
        number(self.beta, "beta", ConfigurationError, 0)
        if self.fusion_mode != "q":
            raise ConfigurationError("v1은 fusion_mode='q'만 지원합니다.")


@dataclass(frozen=True)
class DecisionConfig:
    low_threshold: float = 40.0
    high_threshold: float = 60.0

    def __post_init__(self):
        low = number(self.low_threshold, "low_threshold", ConfigurationError, 0, 100)
        high = number(self.high_threshold, "high_threshold", ConfigurationError, 0, 100)
        if low >= high:
            raise ConfigurationError("low_threshold < high_threshold가 필요합니다.")


@dataclass(frozen=True)
class PipelineConfig:
    rag: RagConfig = field(default_factory=RagConfig)
    formula: FormulaConfig = field(default_factory=FormulaConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) - {"rag", "formula", "decision"}:
            raise ConfigurationError("알 수 없는 pipeline 설정입니다.")
        try:
            return cls(RagConfig(**data.get("rag", {})),
                       FormulaConfig(**data.get("formula", {})),
                       DecisionConfig(**data.get("decision", {})))
        except TypeError as exc:
            raise ConfigurationError(f"pipeline 설정 형식 오류: {exc}") from exc


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"JSON 파일을 읽을 수 없습니다: {path}: {exc}") from exc

import math
from dataclasses import dataclass
from typing import Protocol

from ..errors import ModelError
from ..validation import number

CLASS_ORDER = ("SCAM", "NON_SCAM", "UNKNOWN")


@dataclass(frozen=True)
class ModelScores:
    p_S: float
    p_N: float
    p_U: float

    @property
    def margin(self):
        return self.p_S - self.p_N

    def to_dict(self):
        return {"p_S": self.p_S, "p_N": self.p_N, "p_U": self.p_U,
                "model_margin": self.margin}


class ModelScorer(Protocol):
    max_input_tokens: int
    reserved_tokens: int
    tokenizer_identity: str
    identity: str

    def count_tokens(self, conversation: str) -> int: ...
    def score(self, conversation: str) -> ModelScores: ...


def normalize_probabilities(values):
    try:
        values = tuple(values)
    except TypeError as exc:
        raise ModelError("SCAM/NON_SCAM/UNKNOWN 세 점수가 필요합니다.") from exc
    if len(values) != 3:
        raise ModelError("클래스 순서 SCAM/NON_SCAM/UNKNOWN의 세 점수가 필요합니다.")
    values = [number(v, label, ModelError, 0, 1) for v, label in zip(values, CLASS_ORDER)]
    total = math.fsum(values)
    if total == 0 or abs(total - 1) > 1e-6:
        raise ModelError("모델 점수 합이 1의 허용오차 1e-6을 벗어났습니다.")
    return ModelScores(*(v / total for v in values))


def scores_from_logits(values):
    try:
        values = tuple(values)
    except TypeError as exc:
        raise ModelError("세 클래스 logits가 필요합니다.") from exc
    if len(values) != 3:
        raise ModelError("세 클래스 전체의 logits/log-probability가 필요합니다.")
    values = [number(v, label, ModelError) for v, label in zip(values, CLASS_ORDER)]
    maximum = max(values)
    exps = [math.exp(v - maximum) for v in values]
    total = math.fsum(exps)
    return normalize_probabilities(v / total for v in exps)

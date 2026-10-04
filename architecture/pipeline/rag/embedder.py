import math
from dataclasses import asdict, dataclass
from typing import Protocol

from ..errors import ConfigurationError, RetrievalError
from ..validation import identifier, number, positive_integer


@dataclass(frozen=True)
class EmbeddingSpec:
    model_id: str
    revision: str
    dimension: int
    tokenizer: str
    max_input_tokens: int
    pooling: str = "mean"

    def __post_init__(self):
        for key in ("model_id", "revision", "tokenizer", "pooling"):
            identifier(getattr(self, key), key, ConfigurationError)
        positive_integer(self.dimension, "dimension", ConfigurationError)
        positive_integer(self.max_input_tokens, "max_input_tokens", ConfigurationError)

    def to_dict(self):
        return asdict(self)


class Embedder(Protocol):
    spec: EmbeddingSpec
    max_input_tokens: int
    reserved_tokens: int
    tokenizer_identity: str

    def count_tokens(self, conversation: str) -> int: ...
    def embed(self, conversation: str): ...


def normalize_vector(vector, dimension):
    try:
        vector = tuple(vector)
    except TypeError as exc:
        raise RetrievalError("embedding은 1차원 수치 배열이어야 합니다.") from exc
    if len(vector) != dimension:
        raise RetrievalError(f"embedding 차원 불일치: {len(vector)} != {dimension}")
    values = [number(v, "embedding component", RetrievalError) for v in vector]
    scale = max(abs(v) for v in values)
    if scale == 0:
        raise RetrievalError("영벡터 embedding은 허용하지 않습니다.")
    # 유한한 매우 큰/작은 벡터도 정규화 중 overflow/underflow하지 않는다.
    scaled = [v / scale for v in values]
    norm = math.sqrt(math.fsum(v * v for v in scaled))
    return tuple(v / norm for v in scaled)


def similarity_from_metric(value, metric="cosine_similarity"):
    value = number(value, "raw similarity metric", RetrievalError)
    if metric == "cosine_similarity":
        cosine = value
    elif metric == "cosine_distance":
        cosine = 1 - value  # 이 adapter의 distance 계약은 정확히 d=1-c이다.
    else:
        raise RetrievalError(f"v1에서 지원하지 않는 metric: {metric}")
    if cosine < -1 - 1e-6 or cosine > 1 + 1e-6:
        raise RetrievalError("cosine이 [-1,1]의 허용오차를 벗어났습니다.")
    cosine = min(1.0, max(-1.0, cosine))
    return max(0.0, cosine)

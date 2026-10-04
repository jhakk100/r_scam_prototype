import math
from dataclasses import dataclass

from ..config import RagConfig
from ..errors import DataError, RetrievalError
from ..validation import identifier, number

LABEL_VALUES = {"SCAM": 1, "NON_SCAM": -1}


@dataclass(frozen=True)
class RagEvidence:
    rag_score: float
    rag_quality: float
    rag_agreement: float
    rag_effective_quality: float
    k_effective: int
    total_weight: float
    used_cases: tuple

    def to_dict(self):
        return {"rag_score": self.rag_score, "rag_quality": self.rag_quality,
                "rag_agreement": self.rag_agreement,
                "rag_effective_quality": self.rag_effective_quality,
                "k_effective": self.k_effective, "total_weight": self.total_weight,
                "used_cases": list(self.used_cases)}


def rag_score(results, config=None):
    """RAG Formula v1 §21. Q_eff는 진단값으로만 계산한다."""
    config = config or RagConfig()
    eligible = []
    for hit in results:
        if not isinstance(hit, dict):
            raise DataError("검색 결과는 객체여야 합니다.")
        label = hit.get("label")
        if label not in ("SCAM", "NON_SCAM", "UNKNOWN"):
            raise DataError("미지원 검색 라벨입니다.")
        if type(hit.get("verified")) is not bool:
            raise DataError("verified는 boolean이어야 합니다.")
        similarity = number(hit.get("similarity"), "similarity", RetrievalError, 0, 1)
        identifier(hit.get("case_id"), "case_id", DataError)
        if hit["verified"] and label in LABEL_VALUES:
            eligible.append({**hit, "similarity": similarity})
    candidates = [hit for hit in sorted(eligible, key=lambda h: h["similarity"], reverse=True)
                  [:config.k_retrieve] if hit["similarity"] >= config.tau]
    selected = []
    for i, hit in enumerate(candidates):
        if len(selected) >= config.k_max:
            break
        selected.append(hit)
        if i + 1 < len(candidates):
            if hit["similarity"] - candidates[i + 1]["similarity"] > config.gap_threshold:
                break
    weights = [((h["similarity"] - config.tau) / (1 - config.tau)) ** config.gamma
               for h in selected]
    total = math.fsum(weights)
    used = tuple({**h, "weight": w} for h, w in zip(selected, weights))
    if total == 0:
        return RagEvidence(0.0, 0.0, 0.0, 0.0, len(selected), 0.0, used)
    evidence = math.fsum(w * LABEL_VALUES[h["label"]] for h, w in zip(selected, weights)) / total
    quality = -math.expm1(-total / config.kappa)
    agreement = abs(evidence)
    return RagEvidence(evidence, quality, agreement, quality * agreement,
                       len(selected), total, used)

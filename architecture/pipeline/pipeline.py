from dataclasses import dataclass

from .config import PipelineConfig
from .decision import classify_risk
from .errors import ModelError, PipelineError, RetrievalError
from .formula import fuse_evidence
from .input import INPUT_CONTRACT, check_input_budget, prepare_input
from .model.model_scorer import ModelScores, normalize_probabilities
from .output import build_response
from .rag import rag_score


@dataclass(frozen=True)
class PipelineResult:
    response: dict
    internal_log: dict


class RomanceScamPipeline:
    def __init__(self, model_scorer, embedder, vector_index, config=None):
        self.model = model_scorer
        self.embedder = embedder
        self.index = vector_index
        self.config = config or PipelineConfig()
        if self.embedder.spec != self.index.spec:
            raise RetrievalError("embedding과 index의 모델/버전 계약이 일치하지 않습니다.")

    def analyze(self, data, *, query_id=None, query_group=None):
        prepared = prepare_input(data)
        try:
            # 양쪽 전체 길이를 확인한 이후에만 실제 추론/embedding을 시작한다.
            model_budget = check_input_budget(prepared, self.model, "model")
            embedding_budget = check_input_budget(prepared, self.embedder, "embedding")
        except PipelineError:
            raise
        except Exception as exc:
            raise PipelineError(f"입력 길이 검사 backend 실패: {exc}") from exc
        try:
            scores = self.model.score(prepared.text)
            if not isinstance(scores, ModelScores):
                raise ModelError("scorer는 ModelScores를 반환해야 합니다.")
            scores = normalize_probabilities((scores.p_S, scores.p_N, scores.p_U))
        except PipelineError:
            raise
        except Exception as exc:
            raise ModelError(f"모델 추론 실패: {exc}") from exc
        try:
            vector = self.embedder.embed(prepared.text)
            hits = self.index.search(vector, self.embedder.spec, self.config.rag.k_retrieve,
                                     query_id=query_id, query_group=query_group)
            evidence = rag_score(hits, self.config.rag)
        except PipelineError:
            raise
        except Exception as exc:
            # 실제 장애는 정상적인 Q=0 상태와 구분한다. 장애 fallback은 v1 미확정.
            raise RetrievalError(f"검색 실패: {exc}") from exc
        fused = fuse_evidence(scores.margin, evidence.rag_score, evidence.rag_quality,
                              self.config.formula)
        level = classify_risk(fused.risk_score, self.config.decision)
        response = build_response(fused.risk_score, level)
        internal = {
            "input": {"contract": INPUT_CONTRACT, "sha256": prepared.sha256,
                      "message_count": prepared.message_count,
                      "observation_range": [0, prepared.message_count],
                      "model_budget": model_budget, "embedding_budget": embedding_budget},
            "model": {"identity": self.model.identity, **scores.to_dict()},
            "rag": {"embedding": self.embedder.spec.to_dict(),
                    "index_provenance": self.index.provenance, **evidence.to_dict()},
            "final": {"fusion_mode": "q", "evidence": fused.evidence,
                      "risk_score": fused.risk_score, "level": level},
            "settings": self.config.to_dict(),
        }
        return PipelineResult(response, internal)

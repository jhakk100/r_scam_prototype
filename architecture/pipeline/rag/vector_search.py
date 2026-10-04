import json
import math
import os
import tempfile
from pathlib import Path

from ..errors import DataError, LeakageError, RetrievalError
from ..input import INPUT_CONTRACT, check_input_budget, prepare_input
from ..validation import identifier, positive_integer
from .embedder import EmbeddingSpec, normalize_vector, similarity_from_metric

INDEX_VERSION = "cosine-index-v1"


class VectorIndex:
    """소규모 corpus용 exact cosine 검색. 별도 DB/ANN 의존성 없이 Top-K를 제공한다."""

    def __init__(self, spec, entries, provenance=None):
        self.spec = spec
        self.provenance = dict(provenance or {})
        self.entries = []
        seen = set()
        for row in entries:
            if not isinstance(row, dict):
                raise DataError("index entry는 객체여야 합니다.")
            key = identifier(row.get("case_id"), "case_id", DataError)
            group = identifier(row.get("case_group_id"), "case_group_id", DataError)
            label = row.get("label")
            if label not in ("SCAM", "NON_SCAM", "UNKNOWN"):
                raise DataError("index의 미지원 label입니다.")
            if type(row.get("verified")) is not bool:
                raise DataError("index의 verified는 boolean이어야 합니다.")
            if key in seen:
                raise DataError(f"index의 중복 ID: {key}")
            seen.add(key)
            if not row["verified"] or label == "UNKNOWN":
                raise DataError("index에는 검증된 SCAM/NON_SCAM 사례만 저장합니다.")
            vector = normalize_vector(row.get("vector"), spec.dimension)
            input_hash = identifier(row.get("input_sha256"), "input_sha256", DataError)
            self.entries.append({"case_id": key, "case_group_id": group, "label": label,
                                 "verified": True, "input_sha256": input_hash, "vector": vector})

    @classmethod
    def build(cls, cases, embedder, model_scorer=None, provenance=None):
        entries = []
        for case in cases:
            if not case.eligible:
                continue  # 자격 필터는 embedding/검색 이전에 적용한다.
            prepared = prepare_input(case.messages)
            if model_scorer is not None:
                check_input_budget(prepared, model_scorer, "model/corpus")
            check_input_budget(prepared, embedder, "embedding/corpus")
            try:
                vector = embedder.embed(prepared.text)
            except (DataError, RetrievalError):
                raise
            except Exception as exc:
                raise RetrievalError(f"corpus embedding 실패: {case.conversation_id}: {exc}") from exc
            entries.append({"case_id": case.conversation_id, "case_group_id": case.case_group_id,
                            "label": case.label, "verified": case.verified,
                            "input_sha256": prepared.sha256, "vector": vector})
        return cls(embedder.spec, entries, provenance)

    def search(self, query_vector, query_spec, k, query_id=None, query_group=None):
        positive_integer(k, "search k", RetrievalError)
        if self.spec != query_spec:
            raise RetrievalError("query/corpus의 embedding 모델·버전·차원·tokenizer·pooling 계약이 다릅니다.")
        if query_id is not None:
            identifier(query_id, "query_id", DataError)
        if query_group is not None:
            identifier(query_group, "query_group", DataError)
        # 평가 요청에서 자기 대화/사건이 corpus에 있으면 삭제 후 진행하지 않고 오류를 낸다.
        if any((query_id is not None and row["case_id"] == query_id) or
               (query_group is not None and row["case_group_id"] == query_group)
               for row in self.entries):
            raise LeakageError("평가 대상의 대화 또는 사건이 RAG corpus에 포함되어 있습니다.")
        query = normalize_vector(query_vector, self.spec.dimension)
        hits = []
        for row in self.entries:
            cosine = math.fsum(a * b for a, b in zip(query, row["vector"]))
            hits.append({key: value for key, value in row.items() if key != "vector"} |
                        {"similarity": similarity_from_metric(cosine), "cosine": cosine})
        # 실제 cosine으로 후보 검색한 뒤, 음수 cosine만 0으로 변환한다.
        # 반환 순서는 stable하며 동일 cosine에서는 corpus 순서를 유지한다.
        return sorted(hits, key=lambda row: row["cosine"], reverse=True)[:k]

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": INDEX_VERSION, "input_contract": INPUT_CONTRACT,
                "metric": "cosine_similarity", "embedding": self.spec.to_dict(),
                "provenance": self.provenance, "entries": self.entries}
        handle, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                stream.write("\n")
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    @classmethod
    def load(cls, path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if (data["version"] != INDEX_VERSION or data["input_contract"] != INPUT_CONTRACT or
                    data["metric"] != "cosine_similarity"):
                raise RetrievalError("index 버전·입력 계약·metric이 v1과 다릅니다.")
            return cls(EmbeddingSpec(**data["embedding"]), data["entries"], data["provenance"])
        except (OSError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, (RetrievalError, DataError)):
                raise
            raise RetrievalError(f"index를 읽을 수 없습니다: {path}: {exc}") from exc

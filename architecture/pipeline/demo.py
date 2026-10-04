"""고정 수치/벡터 fixture로 배선만 검증한다. 실제 AI 판별/성능 결과가 아니다."""

import math

from .config import PipelineConfig
from .data import CorpusCase
from .input import prepare_input
from .model import normalize_probabilities
from .pipeline import RomanceScamPipeline
from .rag.embedder import EmbeddingSpec
from .rag.vector_search import VectorIndex


class FixtureScorer:
    max_input_tokens = 100000
    reserved_tokens = 0
    tokenizer_identity = "fixture-character-counter-not-a-real-tokenizer"
    identity = "fixture-scores-not-a-trained-model"

    def count_tokens(self, text):
        return len(text)

    def score(self, text):
        return normalize_probabilities((0.72, 0.18, 0.10))


class FixtureEmbedder:
    max_input_tokens = 100000
    reserved_tokens = 0
    tokenizer_identity = "fixture-character-counter-not-a-real-tokenizer"
    spec = EmbeddingSpec("fixture-vectors-not-a-semantic-model", "v1", 2,
                         tokenizer_identity, max_input_tokens, "fixture")

    def __init__(self, vectors):
        self.vectors = vectors

    def count_tokens(self, text):
        return len(text)

    def embed(self, text):
        return self.vectors[text]


def run_demo():
    query = [{"speaker": "A", "text": "구조 연결 확인용 합성 입력"}]
    vectors = {prepare_input(query).text: (1.0, 0.0)}
    cases = []
    for i, (similarity, label) in enumerate(((0.90, "SCAM"), (0.86, "SCAM"),
                                           (0.82, "NON_SCAM"), (0.70, "SCAM"))):
        messages = [{"speaker": "A", "text": f"검색 벡터 fixture {i}"}]
        cases.append(CorpusCase(f"DEMO_{i}", f"DEMO_GROUP_{i}", label, True, messages))
        vectors[prepare_input(messages).text] = (similarity, math.sqrt(1 - similarity ** 2))
    scorer, embedder = FixtureScorer(), FixtureEmbedder(vectors)
    index = VectorIndex.build(cases, embedder, scorer, {"purpose": "architecture_fixture_only"})
    result = RomanceScamPipeline(scorer, embedder, index, PipelineConfig()).analyze(query)
    return {"mode": "architecture_demo", "notice": "고정 fixture의 기능 검증이며 실제 모델 판별 결과가 아닙니다.",
            "response": result.response, "internal_log": result.internal_log}

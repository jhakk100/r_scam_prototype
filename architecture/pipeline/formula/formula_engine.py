import math
from dataclasses import dataclass

from ..config import FormulaConfig
from ..validation import number


@dataclass(frozen=True)
class FusionResult:
    evidence: float
    risk_score: float


def fuse_evidence(model_margin, rag_score, rag_quality, config=None):
    config = config or FormulaConfig()
    margin = number(model_margin, "M", minimum=-1, maximum=1)
    rag = number(rag_score, "R", minimum=-1, maximum=1)
    quality = number(rag_quality, "Q", minimum=0, maximum=1)
    if quality == 0 or config.beta == 0:
        evidence = margin
    else:
        # 원래 (alpha*M+beta*Q*R)/(alpha+beta*Q)의 수치적으로 안정적인 계산.
        # 극단적인 유한 가중치의 곱 overflow/underflow를 피하며 수식은 변경하지 않는다.
        log_model = math.log(config.alpha)
        log_rag = math.log(config.beta) + math.log(quality)
        scale = max(log_model, log_rag)
        alpha = math.exp(log_model - scale)
        beta_q = math.exp(log_rag - scale)
        evidence = (alpha * margin + beta_q * rag) / (alpha + beta_q)
    number(evidence, "E", minimum=-1, maximum=1)
    score = 50 * (1 + evidence)
    number(score, "Risk Score", minimum=0, maximum=100)
    return FusionResult(evidence, score)

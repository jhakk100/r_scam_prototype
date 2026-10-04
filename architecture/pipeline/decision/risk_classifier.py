from ..config import DecisionConfig
from ..validation import number


def classify_risk(score, config=None):
    config = config or DecisionConfig()
    score = number(score, "Risk Score", minimum=0, maximum=100)
    if score < config.low_threshold:
        return "LOW"
    if score > config.high_threshold:
        return "HIGH"
    return "UNKNOWN"

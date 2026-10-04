from ..errors import PipelineError
from ..validation import number

MESSAGES = {
    "LOW": "현재 대화에서 로맨스 스캠과 관련된 위험 신호가 비교적 낮게 탐지되었습니다.",
    "UNKNOWN": "현재 정보만으로는 로맨스 스캠 여부를 명확하게 판단하기 어렵습니다.\n추가적인 대화 내용이나 정보가 필요할 수 있습니다.",
    "HIGH": "현재 대화에서 로맨스 스캠과 관련된 위험 신호가 높게 탐지되었습니다.\n상대방의 신원과 금전 요구 등을 추가로 확인하는 것을 권장합니다.",
}
DISCLAIMER = "LLM 기반 분석 결과는 오류가 있을 수 있으며, 본 결과만으로 실제 사기 여부를 확정할 수 없습니다."


def build_response(score, level):
    score = number(score, "Risk Score", minimum=0, maximum=100)
    if level not in MESSAGES:
        raise PipelineError("미지원 판정 수준입니다.")
    # 반올림된 값으로 재판정하지 않는다. 점수는 확률(%)이 아니다.
    return {"risk_score": score, "level": level, "message": MESSAGES[level],
            "disclaimer": DISCLAIMER}

# 로맨스 스캠 판별 시스템 파이프라인 구조 v0.2

## 1. 문서 목적

이 문서는 로맨스 스캠 판별 시스템의 전체 **추론 파이프라인 구조**와 각 영역의 역할을 정의한다.

현재 문서에서는 다음 내용을 다룬다.

- 입력 데이터 처리
- 특화 LLM의 역할
- RAG 검색 영역의 역할
- Model Margin 생성 위치
- RAG Score / Quality 생성 위치
- 수식 결합 영역
- 최종 Risk Score 생성
- LOW / UNKNOWN / HIGH 판정
- 사용자에게 보여주는 고정 출력
- 로그 및 디버깅용 내부 데이터

이 문서에서는 **수식 자체를 정의하지 않는다.**

Model Margin, RAG Score / Quality, 최종 Risk Score 계산에 필요한 구체적인 공식은 별도로 정리된 **수식 파일을 참고한다.**

---

# 2. 전체 구조

```text
대화 입력
   │
   ├──────────────────┐
   ▼                  ▼
특화 LLM            RAG 검색
   │                  │
   ▼                  ▼
Model Margin       RAG Score / Quality
   │                  │
   └─────────┬────────┘
             ▼
          수식 결합
             │
             ▼
         Risk Score
           0 ~ 100
             │
             ▼
         고정 구간 판정
             │
       ┌─────┼─────┐
       ▼     ▼     ▼
     LOW  UNKNOWN  HIGH
             │
             ▼
        고정 안내문 출력
```

핵심 원칙은 다음과 같다.

```text
LLM
→ 최종 판정을 직접 하지 않음

RAG
→ 최종 판정을 직접 하지 않음

수식 결합 모듈
→ 각 영역에서 생성된 수치를 조합

판정 모듈
→ Risk Score를 기준으로 고정 구간 판정

출력 모듈
→ 미리 정해진 안내문만 출력
```

---

# 3. 입력 영역

## 역할

사용자가 제공한 대화 내용을 시스템 내부 분석 형식으로 전달한다.

초기 버전은 **텍스트 대화만 처리**한다.

예시:

```text
A: 안녕하세요.
B: 안녕하세요.
A: 우리 여기 말고 다른 메신저에서 이야기할까요?
...
```

초기 범위:

```text
텍스트 대화
복사/붙여넣기 형태의 채팅 기록
구조화된 messages 데이터
```

초기 버전에서 제외:

```text
프로필 사진 판별
딥페이크 판별
이미지 기반 추론
멀티모달 기반 최종 판별
```

---

# 4. 특화 LLM 영역

## 역할

특화 LLM은 현재 대화의 문맥을 분석한다.

모델은 다음과 같은 요소를 학습하게 된다.

```text
친밀감 형성 방식
금전 요구
투자 요구
메신저 이동
감정적 압박
긴급 상황 제시
신원 불일치
언어적 불일치
반복적인 송금 요구
기타 로맨스 스캠 관련 특징
```

단순 특정 단어의 존재 여부가 아니라 대화 전체의 관계와 맥락을 분석하는 것을 목표로 한다.

## 출력 역할

LLM은 사용자에게 직접 최종 위험도나 최종 판정 문구를 생성하지 않는다.

대신 후속 계산에 사용할 **모델 측 수치값**을 제공한다.

이 값은 Model Margin 계산 영역으로 전달된다.

## Model Margin

Model Margin의 구체적인 정의와 계산 방식은:

> **별도 수식 파일 참고**

Model Margin 계산은 생성형 LLM 내부에서 하지 않고 일반 코드에서 처리하는 것을 기본으로 한다.

---

# 5. RAG 검색 영역

## 역할

현재 입력된 대화와 기존 데이터베이스에 저장된 사례를 비교하여 유사 사례를 검색한다.

```text
현재 대화
   │
   ▼
Embedding
   │
   ▼
Vector Search
   │
   ▼
Top-K 유사 사례
```

RAG 검색 결과에는 최소한 다음 정보가 포함되어야 한다.

```text
case_id
label
similarity
```

필요하면 다음 정보를 추가할 수 있다.

```text
risk_factors
scam_stage
reason_summary
```

---

# 6. Embedding 영역

## 역할

현재 대화와 기존 사례들을 벡터 형태로 변환한다.

Embedding 모델은 자연어 대화 간의 의미적 유사도를 계산하기 위해 사용한다.

```text
현재 입력 대화
→ Vector A

기존 사례 1
→ Vector B

기존 사례 2
→ Vector C
```

각 벡터 간 유사도를 기반으로 가장 가까운 사례를 검색한다.

---

# 7. Vector DB / 검색기

## 역할

Embedding 결과를 이용하여 기존 사례 중 가장 유사한 사례를 찾는다.

초기 구조에서는:

```text
Top-K 검색
```

방식을 사용한다.

Top-K 값은 실제 실험 결과에 따라 조정할 수 있도록 설정값으로 분리한다.

---

# 8. RAG Score

검색된 Top-K 결과를 이용하여 RAG 측 방향성을 나타내는 점수를 계산한다.

계산에는 일반적으로 다음 요소가 사용된다.

```text
검색 사례의 라벨
유사도
유효 검색 결과
```

구체적인 RAG Score 공식은:

> **별도 수식 파일 참고**

---

# 9. RAG Quality

RAG Quality는 현재 검색 결과를 얼마나 신뢰할 수 있는지 나타내는 값이다.

예를 들어 다음과 같은 요소가 Quality 계산에 사용될 수 있다.

```text
Top-K 결과들의 유사도 수준
유효한 검색 결과 개수
검색 결과의 분포
검색 사례 간 일관성
```

구체적인 Quality 계산 공식은:

> **별도 수식 파일 참고**

---

# 10. Similarity Threshold

검색 결과의 유사도가 너무 낮은 경우 해당 사례는 현재 입력과 관련성이 낮을 수 있다.

따라서 일정 기준 미만의 검색 결과는 RAG 계산에서 제외할 수 있다.

실제 threshold 값은 embedding 모델과 실제 데이터셋을 이용한 실험 후 확정한다.

---

# 11. 수식 결합 영역

이 영역은 다음 값을 입력받는다.

```text
Model Margin
RAG Score
RAG Quality
```

이 값들을 별도로 정의된 수식에 넣어 최종 Risk Score를 계산한다.

```text
Model Margin ───┐
                │
RAG Score ──────┼─→ 수식 계산 → Risk Score
                │
RAG Quality ────┘
```

구체적인 결합 공식은:

> **별도 수식 파일 참고**

이 영역은 LLM이 담당하지 않는다.

Python 등의 일반적인 수치 계산 코드로 구현한다.

---

# 12. Risk Score

수식 결합 결과는 최종적으로:

```text
0 ~ 100
```

범위의 Risk Score로 변환한다.

Risk Score 자체를 반드시 통계적 의미의 실제 범죄 발생 확률이라고 표현할 필요는 없다.

권장 표현:

```text
위험도
위험 점수
로맨스 스캠 위험 지수
```

---

# 13. 고정 구간 판정

Risk Score가 계산된 후 일반 코드에서 구간을 판정한다.

```text
낮은 점수
→ LOW

중간 점수
→ UNKNOWN

높은 점수
→ HIGH
```

구체적인 threshold 값은 모델 평가 결과를 바탕으로 추후 결정한다.

평가 시에는 다음 지표를 참고할 수 있다.

```text
Precision
Recall
F1
False Positive
False Negative
```

---

# 14. 고정 출력 영역

최종 출력 문구는 LLM이 생성하지 않는다.

코드에서 미리 정의한 문구를 사용한다.

예시:

## LOW

```text
현재 대화에서 로맨스 스캠과 관련된 위험 신호가 비교적 낮게 탐지되었습니다.
```

## UNKNOWN

```text
현재 정보만으로는 로맨스 스캠 여부를 명확하게 판단하기 어렵습니다.
추가적인 대화 내용이나 정보가 필요할 수 있습니다.
```

## HIGH

```text
현재 대화에서 로맨스 스캠과 관련된 위험 신호가 높게 탐지되었습니다.
상대방의 신원과 금전 요구 등을 추가로 확인하는 것을 권장합니다.
```

---

# 15. 사용자 출력

사용자에게 필요한 정보만 보여준다.

예:

```json
{
  "risk_score": 81.4,
  "level": "HIGH",
  "message": "현재 대화에서 로맨스 스캠과 관련된 위험 신호가 높게 탐지되었습니다.",
  "disclaimer": "LLM 기반 분석 결과는 오류가 있을 수 있으며, 본 결과만으로 실제 사기 여부를 확정할 수 없습니다."
}
```

---

# 16. 안내 문구

결과 화면 하단에는 다음과 같은 안내 문구를 표시한다.

> **LLM 기반 분석 결과는 오류가 있을 수 있으며, 본 결과만으로 실제 사기 여부를 확정할 수 없습니다.**

짧은 형태가 필요하면:

> **AI 기반 분석은 오류가 있을 수 있습니다.**

정도로 표시할 수 있다.

---

# 17. 내부 로그

연구 및 디버깅을 위해 사용자에게 보여주는 결과와 별도로 내부 계산값을 저장할 수 있다.

예:

```json
{
  "model": {
    "model_margin": 0.0
  },
  "rag": {
    "rag_score": 0.0,
    "rag_quality": 0.0,
    "used_cases": []
  },
  "final": {
    "risk_score": 0.0,
    "level": "UNKNOWN"
  }
}
```

위 값은 구조 설명용 placeholder이며 실제 계산값을 의미하지 않는다.

---

# 18. 권장 코드 구조

```text
pipeline/
│
├─ model/
│   └─ model_scorer.py
│
├─ rag/
│   ├─ embedder.py
│   ├─ vector_search.py
│   └─ rag_processor.py
│
├─ formula/
│   └─ formula_engine.py
│
├─ decision/
│   └─ risk_classifier.py
│
├─ output/
│   └─ response_builder.py
│
└─ pipeline.py
```

---

# 19. model_scorer.py

담당:

```text
특화 LLM 로드
대화 입력
모델 추론
모델 측 수치 출력
Model Margin 계산에 필요한 값 전달
```

Model Margin의 실제 계산 공식은:

> **별도 수식 파일 참고**

---

# 20. embedder.py

담당:

```text
현재 대화 embedding
기존 사례 embedding
벡터 변환
```

이 영역은 생성형 LLM이 아니라 embedding 모델을 사용하는 것을 기본으로 한다.

---

# 21. vector_search.py

담당:

```text
Vector DB 연결
Top-K 검색
Similarity 반환
사례 label 반환
```

예시 반환 형태:

```json
[
  {
    "case_id": "CASE_001",
    "label": "SCAM",
    "similarity": 0.91
  }
]
```

---

# 22. rag_processor.py

담당:

```text
Top-K 검색 결과 수신
유효 사례 필터링
RAG Score 계산
RAG Quality 계산
```

RAG Score 및 Quality 공식은:

> **별도 수식 파일 참고**

---

# 23. formula_engine.py

담당:

```text
Model Margin 입력
RAG Score 입력
RAG Quality 입력
최종 Risk Score 계산
```

수식 구현은 별도로 정리한 공식 파일을 기준으로 작성한다.

이 문서에서는 수식을 중복 정의하지 않는다.

---

# 24. risk_classifier.py

담당:

```text
Risk Score 입력
LOW / UNKNOWN / HIGH 구간 판정
```

Threshold는 설정 파일에서 변경할 수 있도록 설계한다.

예:

```yaml
decision:
  low_threshold: TBD
  high_threshold: TBD
```

---

# 25. response_builder.py

담당:

```text
Risk Score 표시
LOW / UNKNOWN / HIGH 표시
고정 안내문 선택
Disclaimer 추가
```

이 영역에서는 LLM을 호출하지 않는다.

---

# 26. pipeline.py

전체 모듈을 연결한다.

개념적 구조:

```python
conversation = input_data

model_values = model_scorer(conversation)

model_margin = model_margin_module(
    model_values
)

rag_hits = vector_search(
    conversation
)

rag_score, rag_quality = rag_processor(
    rag_hits
)

risk_score = formula_engine(
    model_margin,
    rag_score,
    rag_quality
)

level = risk_classifier(
    risk_score
)

response = response_builder(
    risk_score,
    level
)
```

위 코드는 구조 설명용 pseudo code이다.

Model Margin, RAG Score / Quality, Risk Score 계산 방식은:

> **별도 수식 파일 참고**

---

# 27. 설정 파일

조정 가능한 시스템 값은 설정 파일로 분리하는 것을 권장한다.

예:

```yaml
rag:
  top_k: 5
  similarity_threshold: TBD

decision:
  low_threshold: TBD
  high_threshold: TBD

model:
  path: models/romance_scam_model
```

실제 값은 실험을 통해 결정한다.

---

# 28. 오류 처리

각 영역에서 문제가 생겼을 때 잘못된 판정을 강제로 출력하지 않도록 한다.

예:

```text
LLM 추론 실패
→ ERROR

RAG 검색 실패
→ 설계에 따라 Model-only fallback 또는 UNKNOWN

수식 계산 오류
→ ERROR

Risk Score 범위 오류
→ ERROR

입력 대화 없음
→ 입력 오류
```

Fallback 정책은 실제 서비스 조건에 맞춰 추후 확정한다.

---

# 29. 평가 시 주의점

RAG 데이터베이스에는 평가 대상 데이터가 들어가면 안 된다.

특히 다음이 Train/RAG와 Test 양쪽에 동시에 포함되는 것을 방지해야 한다.

```text
동일 대화
동일 사건
동일 사건의 다른 대화
```

가능하면 `case_group_id` 단위로 분리한다.

---

# 30. 시스템 성격

이 시스템은 완전한 End-to-End LLM 판별기가 아니다.

구조적으로는 다음 요소가 결합된 하이브리드 시스템에 가깝다.

```text
특화 LLM
+
Embedding Search
+
Case-Based Retrieval
+
수식 기반 결합
+
Rule-based Decision
```

즉:

```text
LLM
→ 현재 사례 분석

RAG
→ 과거 유사 사례 검색

수식
→ 두 영역의 수치를 결합

Rule
→ 최종 판정
```

형태이다.

전통적인 전문가시스템의 일부 특징과 학습형 AI의 장점을 결합한 구조로 볼 수 있다.

---

# 31. 현재 개발 우선순위

```text
1. 특화 모델의 수치 출력 인터페이스 정의

2. Embedding + Top-K 검색 구현

3. RAG Score / Quality 계산 모듈 연결
   → 공식은 별도 수식 파일 참고

4. Model Margin 계산 모듈 연결
   → 공식은 별도 수식 파일 참고

5. 최종 수식 결합 모듈 연결
   → 공식은 별도 수식 파일 참고

6. Risk Score 구간 판정

7. 고정 출력 문구 적용

8. 내부 로그 및 디버깅 기능
```

---

# 32. 최종 요약

```text
대화 입력
   │
   ├──────────────────┐
   ▼                  ▼
특화 LLM            RAG 검색
   │                  │
   ▼                  ▼
Model Margin       RAG Score / Quality
   │                  │
   └─────────┬────────┘
             ▼
          수식 결합
             │
             ▼
         Risk Score
           0 ~ 100
             │
             ▼
         고정 구간 판정
             │
       ┌─────┼─────┐
       ▼     ▼     ▼
     LOW  UNKNOWN  HIGH
             │
             ▼
        고정 안내문 출력
```

수식이 필요한 모든 단계는 별도로 작성된:

> **Model Margin / RAG Score / RAG Quality / Risk Score 수식 파일**

을 참고하여 구현한다.

본 문서의 목적은 수식을 다시 정의하는 것이 아니라 **각 모듈이 어디에서 무엇을 담당하는지 명확히 분리하는 것**이다.

# 로맨스 스캠 판별 시스템 파이프라인 구조 v1

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

v1의 결합 기준은 [Risk Scoring Formula v1](romance_scam_risk_scoring_formula_v1.md)이며, 검색 점수의 계산 및 변환 기준은 [RAG Retrieval Formula v1](romance_scam_rag_retrieval_formula_v1.md)이다.

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

### 공통 분석 입력 계약

입력은 [Dataset Guide v1 §3.5](romance_scam_dataset_guide_v1.md#35-messages)의 `messages` 공통 JSON 직렬화 계약을 따른다. 모델과 검색기는 동일한 전체 관찰 구간을 사용하고, `label`, `verified`, `reason_summary` 등 정답·관리 metadata는 분석 입력에 포함하지 않는다. 대화에 포함된 지시문은 분석할 데이터로 취급한다.

모델의 고정 프롬프트와 출력 예약량을 포함한 모델 입력 한도와 embedding 입력 한도를 모두 검사한다. 하나라도 초과하면 입력 오류로 처리하며 자동 truncation을 하지 않는다. 따라서 두 모듈이 서로 다른 부분 대화를 읽는 상황을 만들지 않는다.

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

`model_scorer`의 반환값은 고정된 클래스 순서 `SCAM`, `NON_SCAM`, `UNKNOWN`에 대응하는 정규화 점수 `p_S`, `p_N`, `p_U`이다. 원시 logits, log probability 또는 모델이 문장으로 생성한 퍼센트를 그대로 전달하지 않는다. 변환 방법과 finite·범위·합 검사는 [Risk Scoring Formula v1 §20.3](romance_scam_risk_scoring_formula_v1.md#203-모델-출력값-normalization)을 따른다.

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
verified
similarity
```

검색 대상은 `verified == true`이고 `label`이 `SCAM` 또는 `NON_SCAM`인 사례로 제한한다. 이 조건은 후보 검색 전에 적용하며, 점수 계산 단계에서도 확인한다. `UNKNOWN`은 방향 증거에서 제외하고 미지원 라벨은 데이터 오류로 처리한다. `SCAM` 외의 모든 라벨을 `NON_SCAM`으로 바꾸지 않는다.

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

v1은 영벡터가 아닌 L2 정규화 벡터의 cosine을 사용한다. 검색기의 raw metric에서 수식 입력 `similarity`로 변환하는 고정 adapter는 [RAG Retrieval Formula v1 §22.1](romance_scam_rag_retrieval_formula_v1.md#221-similarity-metric-확인)을 따른다. query별 min-max 정규화나 미지원 metric의 임의 clamp는 하지 않는다.

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

v1에서 실제 `Q`는 similarity weight의 총량으로만 계산한다. 위 목록의 분포·일관성을 별도 가중치로 더하지 않으며, 라벨 일치도 `A`와 `Q_eff`는 §11의 진단값으로 구분한다.

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

v1은 `fusion_mode = "q"`로 고정하며, 결합 가중치에는 원래 Quality인 `rag_quality = Q`를 사용한다. `rag_agreement = A`와 `rag_effective_quality = Q_eff`는 별도 진단값으로 전달·기록하고 현재 결합 가중치로 사용하지 않는다. `Q_eff`를 `rag_quality`에 덮어쓰거나 Agreement를 중복 적용하지 않는다. 이 계약은 §23과 §26에도 동일하게 적용한다.

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

> 모델의 `UNKNOWN` argmax와 최종 `UNKNOWN`은 같은 판정 규칙이 아니다. 현재의 Model Margin은 방향성을 요약하며, 최종 보류 여부는 기존 Risk Score 구간으로 결정한다. `p_U`는 내부 로그에 보존하고 별도의 강제 보류 규칙은 추가하지 않는다.

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
    "p_S": 0.0,
    "p_N": 0.0,
    "p_U": 1.0,
    "model_margin": 0.0
  },
  "rag": {
    "rag_score": 0.0,
    "rag_quality": 0.0,
    "rag_agreement": 0.0,
    "rag_effective_quality": 0.0,
    "used_cases": []
  },
  "final": {
    "fusion_mode": "q",
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
정규화된 p_S, p_N, p_U 출력 및 수치 검증
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
    "verified": true,
    "similarity": 0.91
  }
]
```

반환된 `similarity`는 §6의 adapter를 통과한 값이다. `verified`와 `label`의 자격 조건은 §5를 따르며, metadata는 embedding 입력에 포함하지 않는다.

---

# 22. rag_processor.py

담당:

```text
Top-K 검색 결과 수신
유효 사례 필터링
RAG Score 계산
RAG Quality 계산
```

`rag_processor`는 RAG 수식 문서의 `rag_score(hits)`를 호출한 뒤 반환 키를 `R` → `rag_score`, `Q` → `rag_quality`, `A` → `rag_agreement`, `Q_eff` → `rag_effective_quality`로 매핑하여 이 네 필드를 반환한다. 마지막 두 값은 진단용이며, `rag_quality`는 항상 원래의 `Q`이다.

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

v1에서 이 모듈이 사용하는 RAG 가중치는 `rag_quality = Q`이다. 고정된 `fusion_mode = "q"`를 기록하며, `A` 또는 `Q_eff`를 결합식에 추가하지 않는다.

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
# Dataset Guide v1 §3.5: messages만 공통 직렬화하고 양쪽 길이 한도 검사
conversation = prepare_input(input_data)

model_values = model_scorer(conversation)

model_margin = model_margin_module(
    model_values
)

rag_hits = vector_search(
    conversation
)

rag_values = rag_processor(
    rag_hits
)

risk_score = formula_engine(
    model_margin,
    rag_values["rag_score"],       # R
    rag_values["rag_quality"]      # raw Q; v1 fusion_mode="q"
)

# rag_agreement와 rag_effective_quality는 내부 진단 로그에만 보존

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

formula:
  fusion_mode: q  # v1 고정 계약; 다른 모드로 변경하지 않음
```

고정된 `fusion_mode`를 제외한 실제 조정값은 실험을 통해 결정한다.

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

설정과 외부 수치는 Risk Scoring Formula v1 및 RAG Retrieval Formula v1의 정의역을 검사한다. NaN/Inf, 잘못된 확률합, 지원하지 않는 metric 등 유효하지 않은 입력은 위 오류 경로로 전달하며, 임의의 정상 점수로 바꾸지 않는다.

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

### Future Work / 평가 및 해석 주석

- 사건 누수는 아직 확인된 사실이 아니다. 향후 성능 평가에서는 Validation/Test의 사건 및 그 파생본을 모델 학습·해당 평가용 RAG corpus에서 격리하고, 분할 기록을 고정해야 한다. Train과 RAG의 상호 중복 자체는 평가 누수가 아니다. (critical review #2)
- 의미 유사도와 이웃 라벨 일치는 현재 대화의 정답을 보장하지 않으며, 분리된 모델·검색 모듈의 오류가 통계적으로 독립이라는 뜻도 아니다. 현재 구조의 실제 이득과 한계는 데이터 실험으로 확인한다. (critical review #10)
- 향후 지표 계산에서는 검증된 이진 정답의 2×3 판정표를 사용하고, SCAM→UNKNOWN을 전체 SCAM Recall의 분모에서 제외하지 않는다. 정답 UNKNOWN의 평가와 보류율·coverage·비용은 별도로 정의한다. (critical review #16)
- Validation 반복 선택에 따른 과적합 크기와 적정 파라미터는 실험 문제이다. 향후 평가에서는 탐색 범위·선택 횟수를 기록하고, Test 결과를 본 뒤 재조정한 설정을 같은 Test의 최종 성능으로 보고하지 않는다. (critical review #17)

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

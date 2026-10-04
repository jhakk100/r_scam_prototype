# 로맨스 스캠 학습용 데이터셋 작성 가이드 v0.1

## 1. 목적

이 문서는 로맨스 스캠 판별 모델 학습에 사용할 데이터셋을 일정한 형식으로 정리하기 위한 가이드입니다.

초기 목표는 다음 세 가지입니다.

1. 대화 내용을 모델이 학습할 수 있는 일정한 형식으로 정리
2. 정상 대화와 로맨스 스캠 대화를 구분
3. 가능하면 모델이 왜 그렇게 판단해야 하는지 근거까지 함께 기록

현재 단계에서는 **JSONL 형식**을 권장합니다.

- 대화 1건 = JSON 1개
- JSONL 파일에서는 JSON 1개를 한 줄에 기록
- 파일 확장자 예시: `romance_scam_dataset.jsonl`

---

# 2. 기본 데이터 구조

권장 형식은 아래와 같습니다.

```json
{
  "conversation_id": "CONV_000001",
  "case_group_id": "CASE_0001",
  "label": "SCAM",
  "verified": true,
  "scam_stage": "MONEY_REQUEST",
  "messages": [
    {
      "speaker": "A",
      "text": "안녕하세요."
    },
    {
      "speaker": "B",
      "text": "안녕하세요. 어디 사세요?"
    },
    {
      "speaker": "A",
      "text": "우리 여기 말고 카카오톡에서 이야기할까요?"
    }
  ],
  "risk_factors": [
    "PLATFORM_MIGRATION",
    "RAPID_INTIMACY"
  ],
  "evidence": [
    {
      "turn": 3,
      "risk_factor": "PLATFORM_MIGRATION",
      "text": "우리 여기 말고 카카오톡에서 이야기할까요?"
    }
  ],
  "reason_summary": "짧은 대화 이후 외부 메신저로 이동을 유도하는 행동이 나타남."
}
```

---

# 3. 반드시 필요한 항목

초기 데이터셋에서는 아래 5개 항목은 반드시 넣는 것을 권장합니다.

## 3.1 `conversation_id`

각 대화의 고유 번호입니다.

예시:

```text
CONV_000001
CONV_000002
CONV_000003
```

같은 번호가 중복되면 안 됩니다.

---

## 3.2 `case_group_id`

같은 사건, 같은 가해자, 또는 서로 강하게 연결된 동일 사건군을 하나의 그룹으로 묶기 위한 ID입니다.

예시:

```text
CASE_0001
CASE_0002
CASE_0003
```

예를 들어 동일 사건에서 대화 3개가 나온 경우:

```text
CONV_000001 -> CASE_0001
CONV_000002 -> CASE_0001
CONV_000003 -> CASE_0001
```

처럼 기록합니다.

### 중요한 이유

향후 모델을 학습할 때 같은 사건의 대화가 학습 데이터와 테스트 데이터에 동시에 들어가면 모델 성능이 실제보다 높게 측정될 수 있습니다.

따라서 `case_group_id`는 가능하면 반드시 작성합니다.

정상 대화 역시 그룹 구분이 가능하다면:

```text
NORMAL_0001
NORMAL_0002
```

처럼 작성할 수 있습니다.

---

## 3.3 `label`

대화의 최종 분류입니다.

허용 값은 아래 3개입니다.

```text
SCAM
NON_SCAM
UNKNOWN
```

의미:

### `SCAM`

로맨스 스캠으로 확인되었거나 학습용 정답으로 사용할 수 있을 정도로 명확한 경우

### `NON_SCAM`

정상적인 대화로 확인된 경우

### `UNKNOWN`

자료만으로는 로맨스 스캠인지 정상 대화인지 판단하기 어려운 경우

억지로 `SCAM` 또는 `NON_SCAM`으로 분류하지 말고 애매하면 `UNKNOWN`으로 기록하는 것이 좋습니다.

---

## 3.4 `verified`

해당 라벨이 검증된 정보인지 표시합니다.

예시:

```json
"verified": true
```

또는

```json
"verified": false
```

### 의미

```text
true
= 사람이 확인했거나 사건 자료 등으로 비교적 확실하게 확인된 데이터

false
= 아직 검증되지 않았거나 추정으로 작성된 데이터
```

초기 모델 학습에는 가능하면:

```text
verified = true
```

데이터를 우선 사용하는 것을 권장합니다.

---

## 3.5 `messages`

실제 대화 내용입니다.

형식:

```json
"messages": [
  {
    "speaker": "A",
    "text": "안녕하세요."
  },
  {
    "speaker": "B",
    "text": "안녕하세요."
  }
]
```

### 작성 규칙

- 대화 순서를 유지합니다.
- 대화 상대는 우선 `A`, `B` 형태로 통일합니다.
- 모델이 실제 서비스에서 누가 가해자인지 모르는 상황을 고려하여 메시지 자체에 `가해자`, `피해자`라고 직접 적지 않는 것을 권장합니다.
- 대화를 요약하지 말고 가능한 한 실제 문장을 유지합니다.

---

# 4. 가능하면 추가하면 좋은 항목

다음 항목은 필수는 아니지만 모델 성능과 향후 분석에 도움이 됩니다.

---

## 4.1 `scam_stage`

해당 대화가 로맨스 스캠의 어느 단계에 가까운지 기록합니다.

초기 권장 값:

```text
NONE
RAPPORT_BUILDING
TRUST_BUILDING
PLATFORM_MIGRATION
MONEY_REQUEST
REPEATED_PAYMENT
INVESTMENT_REQUEST
OTHER
```

### 예시

```json
"scam_stage": "MONEY_REQUEST"
```

정상 대화라면:

```json
"scam_stage": "NONE"
```

### 의미 예시

| 값 | 의미 |
|---|---|
| `NONE` | 스캠 단계 없음 |
| `RAPPORT_BUILDING` | 빠른 친밀감 형성 |
| `TRUST_BUILDING` | 신뢰 확보 단계 |
| `PLATFORM_MIGRATION` | 다른 메신저/플랫폼으로 이동 유도 |
| `MONEY_REQUEST` | 금전 요구 |
| `REPEATED_PAYMENT` | 반복 송금 요구 |
| `INVESTMENT_REQUEST` | 투자/수익 등을 명목으로 금전 요구 |
| `OTHER` | 위 분류에 없는 유형 |

정확히 하나로 분류하기 어렵다면 가장 핵심적인 단계 하나를 선택합니다.

---

## 4.2 `risk_factors`

대화에서 발견된 위험 신호입니다.

초기 권장 목록:

```text
RAPID_INTIMACY
PLATFORM_MIGRATION
MONEY_REQUEST
INVESTMENT_REQUEST
URGENT_REQUEST
IDENTITY_INCONSISTENCY
LANGUAGE_INCONSISTENCY
EMOTIONAL_PRESSURE
SECRECY_REQUEST
REPEATED_PAYMENT
FAKE_IDENTITY
OTHER
```

예시:

```json
"risk_factors": [
  "RAPID_INTIMACY",
  "PLATFORM_MIGRATION",
  "MONEY_REQUEST"
]
```

정상 대화라면:

```json
"risk_factors": []
```

로 작성할 수 있습니다.

---

## 4.3 `evidence`

판단 근거가 되는 실제 대화 문장을 기록합니다.

예시:

```json
"evidence": [
  {
    "turn": 12,
    "risk_factor": "MONEY_REQUEST",
    "text": "급하게 돈이 필요한데 조금만 보내줄 수 있어?"
  }
]
```

### 작성 규칙

- `turn`: 전체 대화에서 몇 번째 발화인지
- `risk_factor`: 해당 문장과 연결된 위험 요소
- `text`: 실제 근거 문장

판단 근거가 여러 개면 여러 항목을 넣습니다.

정상 대화이고 특별한 위험 신호가 없다면:

```json
"evidence": []
```

로 둘 수 있습니다.

---

## 4.4 `reason_summary`

왜 이런 라벨을 붙였는지 한두 문장으로 작성합니다.

예시:

```json
"reason_summary": "친밀감 형성 이후 외부 메신저 이동과 금전 요구가 연속적으로 나타남."
```

### 작성 규칙

- 길게 쓰지 않아도 됩니다.
- 가능한 한 사실 기반으로 작성합니다.
- 근거 없는 추측을 추가하지 않습니다.
- 1~2문장이면 충분합니다.

---

# 5. 정상 데이터 예시

```json
{
  "conversation_id": "CONV_100001",
  "case_group_id": "NORMAL_0001",
  "label": "NON_SCAM",
  "verified": true,
  "scam_stage": "NONE",
  "messages": [
    {
      "speaker": "A",
      "text": "오늘 밥 먹었어?"
    },
    {
      "speaker": "B",
      "text": "아직. 나중에 먹으려고."
    },
    {
      "speaker": "A",
      "text": "카카오톡으로 사진 보내줄게."
    }
  ],
  "risk_factors": [],
  "evidence": [],
  "reason_summary": "일반적인 친분 관계의 대화이며 금전 요구나 기만 정황이 확인되지 않음."
}
```

---

# 6. 로맨스 스캠 데이터 예시

```json
{
  "conversation_id": "CONV_200001",
  "case_group_id": "CASE_0042",
  "label": "SCAM",
  "verified": true,
  "scam_stage": "MONEY_REQUEST",
  "messages": [
    {
      "speaker": "A",
      "text": "당신을 알게 돼서 정말 행복해요."
    },
    {
      "speaker": "B",
      "text": "저도요."
    },
    {
      "speaker": "A",
      "text": "여기 말고 텔레그램으로 이야기해요."
    },
    {
      "speaker": "A",
      "text": "사실 지금 급한 일이 생겨서 돈이 조금 필요해요."
    }
  ],
  "risk_factors": [
    "RAPID_INTIMACY",
    "PLATFORM_MIGRATION",
    "MONEY_REQUEST"
  ],
  "evidence": [
    {
      "turn": 3,
      "risk_factor": "PLATFORM_MIGRATION",
      "text": "여기 말고 텔레그램으로 이야기해요."
    },
    {
      "turn": 4,
      "risk_factor": "MONEY_REQUEST",
      "text": "사실 지금 급한 일이 생겨서 돈이 조금 필요해요."
    }
  ],
  "reason_summary": "빠른 친밀감 형성 이후 외부 메신저 이동과 금전 요구가 연속적으로 나타남."
}
```

---

# 7. 정상 데이터도 여러 종류가 필요함

정상 데이터를 단순한 일상 대화만 넣으면 모델이 특정 단어만 보고 스캠으로 판단하는 문제가 생길 수 있습니다.

가능하면 다음과 같은 정상 대화도 포함하는 것을 권장합니다.

```text
정상 연애 대화
정상 금전 대화
정상 투자 대화
정상 메신저 이동 대화
정상적인 친밀감 표현
정상적인 송금/정산 대화
```

예를 들어:

```text
"카카오톡으로 이야기하자"
```

라는 문장이 있다고 해서 무조건 스캠은 아닙니다.

또한:

```text
"내가 돈 보내줄게"
```

같은 금전 관련 표현도 정상적인 상황에서 등장할 수 있습니다.

따라서 모델이 단순 키워드만 외우지 않도록 스캠과 비슷하게 보이는 정상 사례도 함께 넣는 것이 좋습니다.

---

# 8. 초기 데이터 비율

프로토타입 학습용 데이터는 우선:

```text
정상 대화 : 스캠 대화
5 : 5
```

정도로 구성하는 것을 권장합니다.

예:

```text
정상 500건
스캠 500건
```

다만 데이터의 수보다 **사건과 사람의 다양성**이 중요합니다.

예를 들어 스캠 대화 500건이 있어도 모두 같은 한 명의 가해자에게서 나온 데이터라면 학습 품질이 떨어질 수 있습니다.

가능하면 다양한 사건, 다양한 대화 스타일, 다양한 스캠 유형을 포함하는 것이 좋습니다.

---

# 9. 데이터 작성 시 피해야 할 것

## 9.1 모델이 추측해서 라벨을 확정하는 것

LLM이:

```text
SCAM 가능성이 높습니다.
```

라고 답했다고 해서 곧바로:

```json
"verified": true
```

로 기록하면 안 됩니다.

LLM을 이용해 정리하는 것은 가능하지만, 검증되지 않은 내용은:

```json
"verified": false
```

로 두는 것이 좋습니다.

---

## 9.2 SCAM과 NON_SCAM 중 하나를 억지로 선택하는 것

애매하면:

```text
UNKNOWN
```

을 사용합니다.

잘못된 라벨을 많이 넣는 것보다 UNKNOWN으로 남겨두는 편이 모델 학습에 더 안전합니다.

---

## 9.3 사건 ID 없이 무작위로 데이터를 섞는 것

같은 사건의 대화를 나중에 학습용과 평가용으로 나누면 실제보다 모델 성능이 높게 나올 수 있습니다.

따라서 가능한 한:

```text
case_group_id
```

를 작성합니다.

---

## 9.4 대화를 임의로 과도하게 요약하는 것

가능하면 원래 대화 흐름을 유지합니다.

잘못된 예:

```text
A가 B에게 친해진 후 돈을 요구함.
```

권장:

```json
"messages": [
  {
    "speaker": "A",
    "text": "당신을 알게 돼서 정말 행복해요."
  },
  {
    "speaker": "A",
    "text": "사실 지금 급하게 돈이 필요해요."
  }
]
```

---

# 10. 시간이 부족한 경우 최소 양식

모든 항목을 작성하기 어렵다면 아래 형식만이라도 맞추면 됩니다.

```json
{
  "conversation_id": "CONV_000001",
  "case_group_id": "CASE_0001",
  "label": "SCAM",
  "verified": true,
  "messages": [
    {
      "speaker": "A",
      "text": "..."
    },
    {
      "speaker": "B",
      "text": "..."
    }
  ]
}
```

최소 필수 항목:

```text
conversation_id
case_group_id
label
verified
messages
```

추가 항목은 이후에 보완할 수 있습니다.

---

# 11. LLM을 이용해서 데이터 정리할 때 사용할 프롬프트 예시

아래 프롬프트에 실제 대화를 붙여 넣어 사용할 수 있습니다.

```text
다음 대화 기록을 로맨스 스캠 학습용 데이터셋 형식으로 정리해줘.

반드시 아래 규칙을 지켜라.

1. 출력은 JSON 하나만 작성한다.
2. 대화 내용을 임의로 추가하거나 수정하지 않는다.
3. 판단할 수 없는 내용은 추측하지 않는다.
4. SCAM / NON_SCAM / UNKNOWN 중 하나로 분류한다.
5. 확실하게 검증된 자료가 아니라면 verified는 false로 둔다.
6. 위험 요소는 아래 목록에서 선택한다.

RAPID_INTIMACY
PLATFORM_MIGRATION
MONEY_REQUEST
INVESTMENT_REQUEST
URGENT_REQUEST
IDENTITY_INCONSISTENCY
LANGUAGE_INCONSISTENCY
EMOTIONAL_PRESSURE
SECRECY_REQUEST
REPEATED_PAYMENT
FAKE_IDENTITY
OTHER

7. 근거가 되는 문장이 있다면 evidence에 실제 문장을 그대로 기록한다.
8. reason_summary는 1~2문장으로 작성한다.
9. 대화에 없는 사실을 생성하지 않는다.

출력 형식:

{
  "conversation_id": "",
  "case_group_id": "",
  "label": "SCAM | NON_SCAM | UNKNOWN",
  "verified": false,
  "scam_stage": "",
  "messages": [],
  "risk_factors": [],
  "evidence": [],
  "reason_summary": ""
}

대화 기록:
[여기에 대화 기록 입력]
```

---

# 12. 최종 권장 형태

가능하면 최종적으로 각 대화 데이터가 다음 구조를 가지도록 합니다.

```text
conversation_id
case_group_id
label
verified
messages

+ 가능하면

scam_stage
risk_factors
evidence
reason_summary
```

가장 중요한 것은 **많은 데이터를 만드는 것보다 라벨과 대화 내용이 정확한 데이터를 만드는 것**입니다.

잘못된 데이터 1,000건보다 정확하게 정리된 데이터 300건이 초기 모델 제작에는 더 유용할 수 있습니다.

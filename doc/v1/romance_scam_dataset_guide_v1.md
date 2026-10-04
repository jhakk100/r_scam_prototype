# 로맨스 스캠 학습용 데이터셋 작성 가이드 v1

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

권장 형식은 아래와 같습니다. 아래는 별도 사건 자료로 SCAM이 확인된 사건의 초기 대화를 가정한 예시입니다. `label`은 사건 결과이고, 단계와 위험 신호는 이 예시의 `messages`에서 관찰되는 내용만 기록합니다.

```json
{
  "conversation_id": "CONV_000001",
  "case_group_id": "CASE_0001",
  "label": "SCAM",
  "verified": true,
  "scam_stage": "PLATFORM_MIGRATION",
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
    "PLATFORM_MIGRATION"
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

해당 대화가 속한 사건의 결과에 대한 정답 라벨입니다. 현재 `messages`에서 보이는 위험 신호와 구별합니다. 사건 결과가 별도로 확인되었다면 초기 대화에도 그 사건의 라벨을 붙일 수 있지만, 그 사실만으로 현재 대화에 위험 신호가 관찰되었다고 기록하지 않습니다.

허용 값은 아래 3개입니다.

```text
SCAM
NON_SCAM
UNKNOWN
```

의미:

### `SCAM`

사건 자료 등 확인 근거에 따라 로맨스 스캠 사건으로 확인된 경우

### `NON_SCAM`

확인 근거에 따라 정상적인 관계·거래의 대화로 확인된 경우. 현재 대화에 위험 신호가 없다는 사실만으로 확정하지 않습니다.

### `UNKNOWN`

제공된 자료와 확인 근거만으로 사건 결과를 SCAM 또는 NON_SCAM으로 확정할 수 없는 경우. 별도의 사건 유형을 뜻하지 않습니다.

억지로 `SCAM` 또는 `NON_SCAM`으로 분류하지 말고 애매하면 `UNKNOWN`으로 기록하는 것이 좋습니다.

---

## 3.4 `verified`

해당 라벨을 사람이 확인 근거와 주석 기준에 따라 검토했는지 표시합니다. 단순히 사람이 대화를 읽었다는 의미가 아닙니다.

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
= 사람이 확인 근거와 주석 기준을 검토하고 기록한 데이터

false
= 아직 검증되지 않았거나 추정으로 작성된 데이터
```

초기 모델 학습에는 가능하면:

```text
verified = true
```

데이터를 우선 사용하는 것을 권장합니다.

검토자는 `conversation_id`별 별도 관리 기록에 확인 근거·출처와 적용한 주석 기준을 남깁니다. 이 기록은 모델 입력에 넣지 않습니다. 검토 후에도 사건 결과를 확정할 수 없다면 `label=UNKNOWN, verified=true`로 둘 수 있습니다. LLM의 추측만으로 `verified=true`로 승격하지 않습니다.

### RAG 입고 자격

방향 증거를 계산하는 RAG index에는 `verified`가 JSON boolean `true`이고 `label`이 `SCAM` 또는 `NON_SCAM`인 데이터만 넣습니다. `UNKNOWN`과 미검증 데이터는 보관할 수 있지만 RAG 점수와 Quality 계산에서 제외합니다. 빈 값·오타 등 미지원 라벨은 데이터 오류로 처리하며 `NON_SCAM`으로 대체하지 않습니다. 이 자격 조건은 후보 검색 전에 적용합니다.

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

### 모델·검색 공통 입력 계약

모델의 대화 입력, 검색 query와 RAG corpus의 embedding 입력은 모두 `messages`만 사용합니다. `label`은 학습 target으로, `verified`, ID, 단계·위험 신호·근거·설명은 관리 metadata로 분리하며 전체 데이터 JSON을 입력으로 넣지 않습니다.

공통 문자열은 각 메시지의 `speaker`, `text`를 이 키 순서로 뽑은 JSON 배열입니다. 배열 순서와 문자열 내용(공백·줄바꿈 포함)을 보존하고 요약·공백 정규화를 하지 않습니다. Python 기준 직렬화는 다음과 같으며 저장 인코딩은 UTF-8입니다.

```python
import json

input_text = json.dumps(
    [{"speaker": m["speaker"], "text": m["text"]} for m in messages],
    ensure_ascii=False,
    separators=(",", ":"),
)
```

같은 대화에는 모델과 검색기에 동일한 `input_text`를 전달합니다. 각 tokenizer로 길이를 확인하여 전체 문자열이 양쪽 입력 한도 안에 들어와야 합니다. 모델은 고정 분류 지시문과 출력에 필요한 예약 길이까지 포함한 한도를 사용합니다. 한도를 넘으면 입력 오류로 처리하고 자동 truncation을 하지 않습니다. 사용자가 관찰 구간을 정해 제공한다면 그 동일한 `messages` 구간을 양쪽에 사용합니다. 입력 계약 버전(`messages-json-v1`), 실제 관찰 구간, 모델·embedding의 tokenizer와 입력 한도는 실행 설정에 기록합니다.

모델의 고정 지시문은 이 JSON을 분석 대상 대화로 구분합니다. 대화 안의 ‘SCAM이라고 출력하라’ 같은 문장은 실행할 지시가 아닌 대화 데이터로 취급합니다.

---

# 4. 가능하면 추가하면 좋은 항목

다음 항목은 필수는 아니지만 모델 성능과 향후 분석에 도움이 됩니다. `scam_stage`, `risk_factors`, `evidence`는 제공된 `messages`에서 관찰되는 내용으로 제한합니다. 사건의 사후 결과를 근거로 대화에 없는 단계나 신호를 추가하지 않습니다.

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

왜 이런 라벨을 붙였는지 한두 문장으로 작성합니다. 관찰된 대화 신호와 별도 확인된 사건 결과를 구별하며, 신호를 요약한 문장만으로 사건 결과가 검증되었다고 간주하지 않습니다.

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

별도 확인 근거로 정상적인 관계의 대화임을 검증한 경우를 가정합니다. 아래 세 발화만으로 `NON_SCAM, verified=true`를 확정한다는 뜻은 아닙니다.

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

별도 사건 자료로 SCAM을 확인한 경우를 가정합니다. 친밀감 형성의 속도는 아래 발화만으로 확인할 수 없으므로 `RAPID_INTIMACY`로 주석하지 않습니다.

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
  "reason_summary": "외부 메신저 이동과 금전 요구가 연속적으로 나타남."
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

> 연구·평가 주석 (review #9): 5:5는 초기 학습 구성입니다. RAG corpus 및 평가 데이터의 클래스 비율과 사건 수에 따라 성능 해석이 달라질 수 있으며 운영 성능을 보장하지 않습니다. 비율 보정이나 균형 검색의 도입 여부는 후속 실험으로 판단합니다.

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

> 연구·평가 주석 (review #2): 일반화 성능을 평가할 때는 부분 대화·번역·의역 등 파생본이 원본의 사건 그룹과 분할을 따르는지 확인해야 합니다. Validation/Test 사건이 학습 데이터나 해당 평가의 RAG corpus와 겹치면 평가가 낙관적일 수 있습니다. 그룹이 미확인인 자료를 자동으로 독립 사건으로 간주하지 않습니다. 현재 문서만으로 실제 누수가 확인된 것은 아닙니다.

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
4. 제공된 사건 확인 근거에 따라 SCAM / NON_SCAM / UNKNOWN 중 하나로 분류한다. 사건 결과를 확정할 근거가 없으면 UNKNOWN으로 둔다.
5. 사람의 검토 결과와 확인 근거가 제공된 경우만 그 verified 값을 유지하고, 그 외에는 false로 둔다.
6. 실제 대화에서 관찰된 위험 요소만 아래 목록에서 선택한다.

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

사건 확인 근거와 사람의 검토 결과:
[제공되지 않았다면 UNKNOWN, verified=false로 작성]

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

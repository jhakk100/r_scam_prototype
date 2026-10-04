# 데이터셋 폴더 사용 가이드

## 1. 어떤 파일을 사용하나

학습과 평가에는 다음 두 파일을 함께 사용한다.

| 파일 | 포함 내용 | 역할 |
|---|---|---|
| `study dataset/dataset.jsonl` | conversation_id, messages | 모델에 전달할 대화 |
| `answer dataset/answers.jsonl` | conversation_id, case_group_id, label, verified | 학습 정답, 평가 정답, 사건별 분할 정보 |

두 파일은 **동일한 372건의 대화에 대한 입력과 정답**이다. `study dataset`을 Train으로, `answer dataset`을 Test로 취급하면 안 된다. 정답 파일은 평가뿐 아니라 지도 학습에도 필요하다.

현재 라벨은 SCAM 180건, NON_SCAM 192건이다. UNKNOWN은 없다. 원본 라벨을 그대로 유지했으며, 논문 관계자가 검증한 자료라는 사용자 확인에 따라 정답 파일의 verified는 모두 true이다.

| 보관·관리 파일 | 용도 |
|---|---|
| `answer dataset/metadata/dataset.review.jsonl` | ID별 기존 출처·선택 주석 및 검토 기록 |
| `answer dataset/metadata/dataset.verification.json` | 사람 검증에 대한 사용자 확인 및 적용 대상 원본 해시 |
| `answer dataset/metadata/dataset.audit.json` | 데이터 점검 통계와 문제 항목 |
| `answer dataset/metadata/CLEANING_REPORT.md` | 문서 비교와 정제 결과 설명 |
| `answer dataset/archive/dataset.original.jsonl` | 제공받은 원본 그대로 보관 |
| `answer dataset/archive/dataset.combined.jsonl` | 폴더 분리 이전의 최소 스키마 정제본 보관 |
| `clean_dataset.py` | 보관 원본에서 활성 입력·정답 및 점검 기록을 재생성 |

metadata와 archive는 일반 분류 학습의 입력 데이터로 사용하지 않는다.

## 2. 입력과 정답을 어떻게 연결하나

JSONL은 한 줄이 JSON 객체 하나이며 UTF-8로 저장되어 있다. 두 파일은 줄 번호 대신 **conversation_id**로 연결한다. 파일의 정렬 순서가 바뀌어도 같은 ID끼리 연결해야 한다.

정답 파일의 실제 첫 레코드:

```json
{"conversation_id":"CONV_000001","case_group_id":"NORMAL_0001","label":"NON_SCAM","verified":true}
```

같은 ID의 대화를 입력 파일에서 찾으면 그 대화의 정답은 NON_SCAM이다.

| 필드 | 사용 방법 |
|---|---|
| messages | 발화 순서와 speaker/text를 유지해 모델 입력으로 구성 |
| label | 모델이 학습할 목표 또는 예측과 비교할 정답 |
| conversation_id | 입력·정답·예측을 연결하는 키; 모델 대화 입력에서는 제외 |
| case_group_id | 같은 사건·파생본이 여러 분할에 섞이지 않도록 관리; 모델 입력에서는 제외 |
| verified | 검증 상태와 RAG 입고 자격 관리; 모델 입력에서는 제외 |

모델에 전체 JSON을 입력하면 정답 또는 사후 정보가 노출될 수 있다. 특히 case_group_id에 NORMAL/SYNTH 같은 문자열이 들어 있어도 대화 입력에는 넣지 않는다. source_file, title, risk_factors, evidence, reason_summary 역시 입력에 넣지 않는다.

## 3. Python으로 읽고 연결하기

아래 예시는 dataset 폴더에 저장한 Python 스크립트에서 실행한다. 표준 라이브러리만 사용하며, 파일을 수정하거나 학습을 실행하지 않는다.

```python
import json
from pathlib import Path

root = Path(__file__).resolve().parent

def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

inputs = read_jsonl(root / "study dataset" / "dataset.jsonl")
answers = read_jsonl(root / "answer dataset" / "answers.jsonl")

input_by_id = {row["conversation_id"]: row for row in inputs}
answer_by_id = {row["conversation_id"]: row for row in answers}

assert len(input_by_id) == len(inputs), "대화 ID 중복"
assert len(answer_by_id) == len(answers), "정답 ID 중복"
assert input_by_id.keys() == answer_by_id.keys(), "입력·정답 ID 불일치"

examples = []
for row in inputs:
    answer = answer_by_id[row["conversation_id"]]
    input_text = json.dumps(
        [{"speaker": m["speaker"], "text": m["text"]} for m in row["messages"]],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    examples.append({
        "conversation_id": row["conversation_id"],
        "case_group_id": answer["case_group_id"],
        "input_text": input_text,
        "target_label": answer["label"],
    })

print(f"연결 완료: {len(examples)}건")
print(f"첫 대화: {examples[0]['conversation_id']}")
print(f"첫 정답: {examples[0]['target_label']}")
```

examples의 ID와 사건 그룹은 관리 정보다. 모델의 분석 대상 대화로 전달하는 값은 input_text이며, target_label은 별도의 학습 목표다. 전체 examples 객체를 프롬프트로 전달하지 않는다.

## 4. 학습·평가·RAG에서 사용하는 순서

### QLoRA 분류 학습

1. 위 방식으로 입력과 정답을 연결한다.
2. 사건·파생본 관계를 확인해 Train/Validation/Test에 사용할 ID를 정한다.
3. Train의 input_text를 분석 대상 대화로 제공하고 target_label을 학습 정답으로 사용한다.
4. 사용하는 모델과 학습 코드에 맞는 분류 헤드 또는 대화 템플릿으로 변환한다. 생성형 학습이라면 정답 라벨은 assistant의 목표 응답에 배치하고, 분석 대상 대화 본문에는 넣지 않는다.
5. Validation으로 설정·임계값을 선택하고, Test로 최종 평가한다.

QLoRA를 위해 기존 라벨을 UNKNOWN으로 변경하지 않는다. 현재 두 JSONL은 범용 입력·정답 자료이며 특정 학습 라이브러리에 바로 전달하는 템플릿까지 구성된 파일은 아니다.

### 평가

1. 평가에 배정한 ID의 대화만 모델에 전달한다.
2. 예측 결과를 conversation_id와 함께 저장한다.
3. 정답 파일에서 같은 ID의 label을 찾아 비교한다.
4. 검증된 정답은 SCAM/NON_SCAM이지만 모델의 최종 출력은 UNKNOWN일 수도 있다. SCAM을 UNKNOWN으로 판정한 사례를 전체 SCAM Recall의 분모에서 빼지 않는다.

정답은 모델 예측이 끝난 뒤 비교한다. 평가 프롬프트에는 label이나 정답 파일의 내용을 포함하지 않는다.

### RAG

1. verified=true이고 label이 SCAM 또는 NON_SCAM인 사례만 입고 대상으로 선택한다.
2. corpus embedding에는 대화 input_text만 사용한다. label은 검색 결과의 방향 증거 계산용 metadata로 분리한다.
3. 모델 입력, 검색 query, corpus embedding에 동일한 messages-json-v1 직렬화 기준을 사용한다.
4. 평가에서는 Validation/Test 사건과 파생본이 해당 평가의 RAG corpus에 포함되지 않도록 격리한다.

현재 372건은 라벨·검증 조건을 충족한다. 실제 평가용 corpus 구성은 사건 분할 후 결정한다.

### 현재 아직 정하지 않은 것

현재는 실제 Train/Validation/Test 분할, 모델별 학습 템플릿, 모델·embedding tokenizer 및 입력 한도를 확정하지 않았다. 사건 ID가 서로 다르다는 이유만으로 독립 사건이라고 가정하지 않는다. 두 입력 한도를 확인하고, 대화를 임의로 요약하거나 자동으로 서로 다른 구간을 잘라 사용하지 않는다.

## 5. 재생성과 데이터 추가

데이터셋 파일을 사용하는 것만으로는 재생성이 필요하지 않다.

재생성이 필요하면 dataset 폴더에서 Python 환경으로 다음을 실행한다.

```powershell
python .\clean_dataset.py
```

현재 Codex 작업 환경의 번들 Python으로 실행하려면 같은 폴더에서 다음 명령을 사용한다.

```powershell
& 'C:\Users\bjh38\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\clean_dataset.py
```

이 명령은 study dataset/dataset.jsonl, answer dataset/answers.jsonl, metadata의 review/audit 파일을 덮어써 재생성한다. archive의 원본과 분리 전 정제본, verification 기록은 변경하지 않는다.

새 대화를 추가하거나 기존 라벨을 수정할 때는 연결된 두 파일의 ID를 함께 관리하고 출처·사람 검증 기록도 갱신한다. 재생성은 보관 원본을 기준으로 하므로 활성 파일에만 직접 추가한 내용은 다음 재생성 때 사라진다. 입력 원본이 변경되면 기존 verification 해시·건수와 달라져 스크립트가 중단한다. 새 자료를 검증했다는 기록 없이 해시만 바꾸어 통과시키지 않는다.

# 데이터셋 사용 안내

파일별 역할, Python 연결 예시, QLoRA 학습·평가·RAG 사용 순서와 재생성 방법은 [상세 사용 가이드](USAGE_GUIDE.md)에 정리했다.

대화 입력과 정답·관리 정보를 두 폴더로 분리했다. **study/answer는 Train/Test 구분이 아니다.** 두 파일은 같은 372개 대화의 입력과 정답이며 conversation_id로 연결한다.

```text
dataset/
├── study dataset/
│   └── dataset.jsonl              # conversation_id, messages
├── answer dataset/
│   ├── answers.jsonl              # conversation_id, case_group_id, label, verified
│   ├── metadata/
│   │   ├── dataset.review.jsonl   # 출처·원래 선택 주석·검토 기록
│   │   ├── dataset.verification.json
│   │   ├── dataset.audit.json
│   │   └── CLEANING_REPORT.md
│   └── archive/
│       ├── dataset.original.jsonl # 제공받은 원본, 바이트 변경 없음
│       └── dataset.combined.jsonl # 분리 전 최소 스키마 정제본 보관
├── clean_dataset.py               # 원본에서 두 파일 재생성·검증
├── USAGE_GUIDE.md                 # 상세 사용 방법
└── README.md
```

## 학습과 평가

- 학습: 같은 conversation_id의 messages를 입력으로, label을 정답으로 사용한다. QLoRA 학습에도 정답 파일이 필요하다.
- 평가: 평가 대상으로 지정한 messages만 모델에 전달하고, 출력 결과를 정답 파일의 label과 비교한다.
- 모델 입력에는 messages만 포함한다. conversation_id는 연결용이고 case_group_id는 사건별 분할용이다. label과 verified를 대화 입력에 넣지 않는다.
- source_file, title, subtype, risk_factors, evidence, reason_summary는 학습용 입력 파일에 없다. 원래 정보는 metadata 및 archive에만 보존했다.
- 실제 Train/Validation/Test는 두 파일의 같은 ID를 같은 분할에 배정한다. 같은 사건·파생본이 여러 분할에 걸치지 않도록 case_group_id 및 원자료의 관계를 확인한다. 현재는 실제 분할을 만들지 않았다.

## ID로 연결하는 예시

```python
import json
from pathlib import Path

root = Path(__file__).resolve().parent  # 이 예시를 dataset 폴더의 스크립트에서 실행

def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

inputs = read_jsonl(root / "study dataset" / "dataset.jsonl")
answers = read_jsonl(root / "answer dataset" / "answers.jsonl")
by_id = {row["conversation_id"]: row for row in answers}

for row in inputs:
    answer = by_id[row["conversation_id"]]
    input_text = json.dumps(
        [{"speaker": m["speaker"], "text": m["text"]} for m in row["messages"]],
        ensure_ascii=False, separators=(",", ":"),
    )
    target_label = answer["label"]
    # input_text는 모델 입력, target_label은 별도의 학습 정답/평가 기준
```

라벨은 SCAM 180건, NON_SCAM 192건이다. 사용자 확인에 따른 사람 검증을 반영해 정답 파일의 verified는 모두 true이다. 재생성은 `python clean_dataset.py`로 실행한다. 원본 해시가 바뀌면 기존 검증 확인을 새 자료에 적용하지 않고 중단한다.

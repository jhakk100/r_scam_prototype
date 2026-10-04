# 데이터셋 점검·정제 결과

검토일: 2026-10-04 (Asia/Seoul)

수정 근거: 사용자가 원본은 논문 관계자가 작성해 제공한 검증된 자료라고 확인했다. 폴더에 별도의 검토 기록이 없다는 이유로 기존 라벨을 모두 UNKNOWN으로 바꾼 초기 판단을 철회했다. 현재 정제본은 원래 라벨을 보존하며, 사람 검증에 대한 사용자 확인을 별도 기록에 남긴다.

폴더 정리: 사용자의 요청에 따라 `study dataset/dataset.jsonl`에 대화 입력을, `answer dataset/answers.jsonl`에 라벨·검증 상태·사건 그룹을 분리했다. 현재 경로는 dataset 폴더 기준이다. 아래의 초기 정제본은 `answer dataset/archive/dataset.combined.jsonl`에 보관했고, 원본은 `answer dataset/archive/dataset.original.jsonl`에 이동했다. 두 폴더는 Train/Test 분할을 뜻하지 않는다.

## 문서 비교 결과

`doc/v1/romance_scam_dataset_guide_v1.md`와 `doc/paper/romance_scam_technical_draft_ko.docx`의 데이터 관련 요구사항은 일치한다. 논문 PDF의 해당 본문도 확인했다. 문서 전체가 같은 텍스트라는 뜻이 아니라, 데이터 정제 기준에서 충돌이 없다는 뜻이다.

| 비교 항목 | 가이드 위치 | 논문 위치 | 결과 |
|---|---|---|---|
| JSONL 및 5개 기본 필드 | §2–3, §10 | §4.1, 표 1 | 일치 |
| 라벨은 확인 근거가 있는 사건 결과이며 불명확하면 UNKNOWN | §3.3, §9.2, §11 | §4.1 | 일치 |
| verified는 사람이 확인 근거·기준을 검토하고 기록한 상태 | §3.4, §9.1 | §4.1 | 일치 |
| RAG는 verified=true인 SCAM/NON_SCAM만 검색 전 입고 | §3.4 | §3.4 | 일치 |
| messages만 동일한 JSON 배열로 모델·검색 입력에 사용 | §3.5 | §3.2, §4.2 | 일치 |
| 발화 원문·순서 보존, 선택 주석은 관찰된 내용만 기록 | §3.5, §4, §9.4 | §4.1–4.2 | 일치 |
| 사건·파생본 단위 분할, 미확인 그룹을 독립 사건으로 가정하지 않음 | §3.2, §9.3 | §4.3 | 일치 |
| 5:5는 초기 구성 권장값 | §8 | §4.2 | 일치; 비율을 맞추기 위한 삭제 없음 |

논문 §4.2는 정확·유사 중복과 최종 제외의 세부 절차를 미확정으로 남긴다. 따라서 유사도만으로 대화를 삭제하거나 사건 그룹을 합치지 않았다.

## 원본 점검

대상: `answer dataset/archive/dataset.original.jsonl`, 372건, 4,110발화.

- 원래 라벨: NON_SCAM 192건, SCAM 180건. 원본 파일의 verified 표기는 전부 false이지만, 사용자가 논문 관계자가 작성해 제공한 검증된 자료라고 확인했다. 정제본의 verified는 이 확인에 따라 true로 정정했다.
- JSON 파싱, 필수 필드, 고유 conversation_id, A/B 화자, 비어 있지 않은 발화, 근거 turn 범위와 원문 일치는 통과했다. 발화에 Unicode 대체 문자 U+FFFD는 없다.
- messages의 공통 직렬화 문자열이 완전히 같은 중복은 0건이다. 같은 `(source_file, source_conversation_id)` 조합의 중복도 0건이다.
- 문자 3-gram 집합 Jaccard ≥ 0.8의 유사 대화 후보는 0쌍이다. 이 수치는 의미적 중복·번역·의역·파생본이 없음을 보장하지 않는다.
- evidence.risk_factor가 해당 대화의 risk_factors에 없는 항목이 13개, 12개 대화에서 발견됐다. ID와 evidence 배열 인덱스는 `dataset.audit.json`에 기록했다.
- SCAM 180건 모두에 RAPID_INTIMACY, MONEY_REQUEST, URGENT_REQUEST, EMOTIONAL_PRESSURE, REPEATED_PAYMENT를 일괄 부여하고 scam_stage도 모두 REPEATED_PAYMENT로 기록했다. 14건은 evidence가 비어 있다. 근거 누락만으로 라벨 오류를 확정하지는 않지만, 주석의 타당성을 별도로 검토해야 한다.
- 예를 들어 CONV_000061은 친밀감 형성의 속도를 확인할 시간 정보가 없고, 공통 reason_summary에 등장하는 출금·정산 비용도 실제 발화에 없다. CONV_000214의 공연 정산 비용을 INVESTMENT_REQUEST로 기록한 항목도 위험 요소 목록과 불일치한다. CONV_000063의 “왜 또 비용이 나와?”처럼 요구를 질문하는 발화를 금전 요구 근거로 기록한 사례도 있다.
- source_file에 기록된 원자료 19개와 상세 검토 절차는 작업 폴더에 없지만, 이를 라벨 미검증의 증거로 취급하지 않는다. 원본 라벨은 사용자가 확인한 검증 결과를 유지한다. SYNTH 그룹 ID만으로 자료의 생성 방식이나 실제 사건 여부를 단정하지 않았다.
- case_group_id는 모두 서로 다르지만 실제 독립 사건 372개라고 확인된 것은 아니다.

## 적용한 정제

원본 내용은 수정하지 않고 `answer dataset/archive/dataset.original.jsonl`에 보관했다. 원본 SHA-256:

```text
3c0c485e11e2ce0e9e7fdec4df133d233ca197db713bce8ec7827f20193ef252
```

분리 전 정제본은 가이드 §10의 최소 5개 필드로 구성했으며 현재 `answer dataset/archive/dataset.combined.jsonl`에 보관한다. 활성 데이터는 대화 입력과 정답 파일로 나누었고, conversation_id로 연결하면 동일한 최소 스키마를 복원할 수 있다.

1. 372건을 모두 유지했다. 대화 원문, 발화 순서, 화자, conversation_id, case_group_id를 그대로 보존했다.
2. 원래 label을 그대로 보존했다. NON_SCAM 192건, SCAM 180건, UNKNOWN 0건이다. QLoRA를 위해 라벨을 UNKNOWN으로 변경할 이유는 없다.
3. 사용자 확인에 따라 verified=true를 기록했다. 근거는 논문 관계자의 사람 검증에 대한 사용자 진술이며 자동 정제나 LLM의 라벨 추측이 아니다. 정확한 사용자 진술, 적용한 원본 해시와 건수를 dataset.verification.json에 남겼다. 검증자 이름이나 상세 절차는 제공되지 않았으므로 임의로 기록하지 않았다.
4. scam_stage, risk_factors, evidence, reason_summary는 선택 필드이므로 최소 정제본에서 제외하고 원래 값 전체를 별도 검토 기록으로 옮겼다. 모든 주석이 틀렸다는 뜻이나 위험 신호가 없다는 뜻이 아니다. 일부만 임의로 재분류하는 대신 사람이 관찰 근거를 검토한 후 복원하도록 했다.
5. subtype, source_file, source_conversation_id, title과 기존 라벨을 포함한 **messages 외 원본 필드 전체**를 `dataset.review.jsonl`에 ID별로 보존했다. 이 기록과 정제본의 messages로 원본 JSON 객체를 복원할 수 있음을 검사했다.
6. 사건 그룹은 새로 추정하거나 합치지 않았다. 검토 기록에 case_group_status=UNCONFIRMED를 명시했고 Train/Validation/Test 분할은 만들지 않았다.

## 산출물과 확인

| 파일 | 용도 |
|---|---|
| study dataset/dataset.jsonl | conversation_id와 messages만 포함한 대화 입력, 372건 |
| answer dataset/answers.jsonl | conversation_id, case_group_id, label, verified 정답·분할 정보, 372건 |
| answer dataset/archive/dataset.original.jsonl | 변경하지 않은 원본 |
| answer dataset/archive/dataset.combined.jsonl | 분리 전 최소 스키마 정제본 보관 |
| answer dataset/metadata/dataset.review.jsonl | 원래 라벨·주석·출처 metadata, 검증 근거 연결 및 선택 주석 검토 기록, 372건 |
| answer dataset/metadata/dataset.verification.json | 원본 372건에 대한 사용자 확인과 사람 검증 출처 기록 |
| answer dataset/metadata/dataset.audit.json | 통계, 문제 항목, 중복 점검 및 미확정 사항 |
| clean_dataset.py | 확인된 원본 라벨을 유지하는 재현 가능한 정제·검증 코드 |

저장한 두 파일을 다시 읽어 각 372건, ID 중복 없음, ID 집합 일치, 입력 파일에 정답·관리 필드 없음, 모든 messages의 내용과 순서, messages-json-v1 직렬화 결과, 기존 라벨·사건 ID 보존, 원본 객체 복원 가능성을 검사했다. 보관한 원본 파일의 바이트가 변하지 않았음도 확인했다. 모두 통과했다.

실행 예시: `python clean_dataset.py`. 스크립트는 answer dataset/archive의 원본을 읽고 study/answer의 활성 파일과 metadata의 검토·점검 기록을 다시 생성한다. dataset.verification.json의 해시·건수가 입력과 일치하는지 먼저 검사한다. 원본 변경이나 데이터 추가 시 기존 사용자 확인을 새 자료에 자동 적용하지 않고 중단한다.

## 학습·RAG 사용 상태

정제본은 **기존 라벨을 정답으로 사용하는 분류 학습에 사용할 수 있다**. 입력은 messages만 사용하고, 정답은 label이다. 원본 전체 JSON이나 검토 metadata를 모델 입력에 섞지 않는다. 선택 주석을 학습하지 않는 분류 과제에는 해당 주석을 제외한 최소 스키마로 충분하다.

answer dataset은 평가에만 사용하는 파일이 아니다. 지도 학습에도 같은 ID의 정답이 필요하다. 평가할 때는 평가용 ID의 대화만 모델에 주고 출력과 정답을 비교한다. 현재 폴더 정리는 입력/정답 분리이며 실제 Train/Validation/Test 분할은 만들지 않았다.

372건 모두 SCAM/NON_SCAM 및 verified=true라는 RAG 라벨 자격을 충족한다. 이는 전부를 평가용 RAG corpus에 넣어도 된다는 뜻은 아니다. 평가에 사용할 사건·파생본은 해당 모델 학습과 RAG 자료에서 격리한다.

모델명·embedding 모델명, 각 tokenizer와 입력 한도가 정해지지 않아 실제 토큰 한도 검사는 수행하지 않았다. 자동 truncation은 하지 않았다. 이후 모델과 검색의 입력은 messages-json-v1만 사용하고 review metadata나 전체 JSON을 입력에 섞지 않는다.

기존 검증에 대한 사용자 확인은 각 conversation_id의 review 기록에서 dataset.verification.json으로 연결했다. 선택 주석을 설명·근거 학습에 활용한다면 발견된 불일치와 의미 적합성을 별도로 검토한다. 파생본과 사건 그룹은 검증된 라벨과 다른 문제이므로 학습·평가 분할 전에 확인한다.

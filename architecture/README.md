# 추론 아키텍처

로맨스 스캠 텍스트 대화를 분석하는 **v1 추론 아키텍처 프로토타입**이다.
이 폴더는 초기 아키텍처의 공통 입력 계약과 모델 백엔드를 제공한다. 최종 실행은 [V4](../V4/README.md), 최신 논문은 [최종 논문](../V4/paper/romance_scam_ko.docx)을 참고한다.
추론은 이 폴더에서, 모델 학습은 별도 `model_training/`에서 구현한다. 임계값 튜닝 및 실제 판별 성능 평가는 이후 실험 단계다.

## 현재 폴더 구성

```text
architecture/
├── pipeline/                 # 공통 입력·모델 연결·검색·수식·판정·출력
│   ├── model/
│   ├── rag/
│   ├── formula/
│   ├── decision/
│   ├── output/
│   ├── backends.py
│   ├── pipeline.py
│   └── __main__.py
├── configs/                  # 추론 설정
├── examples/                 # 입력 예시
├── tests/                    # 아키텍처·모델 연결 계약 테스트
├── docs/ARCHITECTURE_STATUS.md
├── requirements.txt          # 추론 의존성
└── README.md
```

데이터셋·v1 설계·논문 초안·환경 검사기는 프로젝트 루트에서 공동으로 관리한다.
모델 학습 파이프라인은 별도의 `model_training/` 폴더에 둔다.
아래 모든 실행 명령은 **프로젝트 루트 `r_scam_prototype/`** 기준이다.

## 다른 컴퓨터에서 가볍게 확인하기

프로젝트 루트에서 실행한다. 아래 명령은 Python 표준 라이브러리만 사용하며,
모델 다운로드·GPU·학습이 필요 없다. 환경 표준은 기존 검사기의 Python 3.11.6이다.

```powershell
python -m unittest discover -s architecture/tests -v
python -m architecture.pipeline audit-data
python -m architecture.pipeline demo
```

`audit-data`는 기존 대화/정답 파일을 읽어 연결과 스키마를 확인한다. 파일을 정제하거나 덮어쓰지 않는다.
`demo`는 고정된 합성 클래스 점수와 벡터로 모듈 연결을 검증한다.
출력에 `mode=architecture_demo`를 명시하며 **실제 AI 판별 또는 실험 성능으로 사용하지 않는다.**

## 실제 실행 환경 준비

`CHECK_ENV_and_AUTO_LIB_INSTALLER.py`에 있는 버전을 설치 명세에 반영했다.
실제 실행할 컴퓨터에서 가상환경을 만들고 GPU/CUDA 조건을 확인한다.
기존 검사기는 실행하면 누락된 패키지를 자동 설치하는 파일이다.
이 구현 작업에서는 해당 자동 설치나 모델 다운로드를 실행하지 않았다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install torch==2.7.0 --index-url https://download.pytorch.org/whl/cu126
python -m pip install -r architecture/requirements.txt
```

Python은 검사기와 같은 **3.11.6**을 사용한다. 위 PyTorch 명령은 기존 CUDA 12.6 표준이다.
CPU 실행 환경이면 실제 하드웨어에 맞는 PyTorch를 별도로 설치하고 `device_map=cpu`,
`dtype=float32`, `quantization=none`으로 설정한다. 기존 검사기는 GPU 학습환경을
검사하므로 CPU 추론 환경을 통과 판정하는 용도로 사용하지 않는다.

| 라이브러리 | 기존 검사기 버전 | 이번 아키텍처에서의 역할 |
|---|---:|---|
| torch | 2.7.0 | 실제 모델·encoder tensor 추론 |
| transformers | 5.14.1 | 모델/tokenizer 로드·분류 logits 또는 라벨 전체 채점·embedding |
| accelerate | 1.14.0 | device_map 모델 배치 |
| peft | 0.20.0 | 별도 학습 파이프라인 산출물인 LoRA adapter 연결 |
| bitsandbytes | 0.50.2 | 설정에서 nf4를 선택한 경우의 4-bit 모델 로드 |
| safetensors | 0.8.0 | 가중치 파일 로드 |
| trl | 1.9.2 | 기존 환경 명세에 보존; 현재 추론/학습 코드에서 사용하지 않음 |
| datasets | 5.0.1 | 기존 환경 명세에 보존; 현재 데이터 로더는 표준 JSONL 사용 |
| psutil | 버전 고정 없음 | 기존 환경 검사기용 |

작은 corpus의 벡터 검색은 L2 정규화 벡터의 exact cosine을 사용한다.
현재는 FAISS, Vector DB 서버, sentence-transformers, 웹 서버 라이브러리를 추가하지 않았다.
검색 알고리즘·수식·기능 범위는 v1을 따른다.

## 모델과 embedding 설정

`embedding.text_prefix`는 선택한 encoder가 요구하는 고정 접두사이며 생략 시 빈 문자열이다.
E5로 같은 형식의 대화 간 의미 유사도를 검색할 때는 `"query: "`를 query와 corpus 양쪽에 사용한다.
접두사를 포함한 실제 token 수를 검사하며, index의 embedding 계약에도 저장한다.
접두사를 바꾸면 index를 다시 생성해야 한다.

```powershell
Copy-Item architecture/configs/inference.example.json architecture/configs/inference.local.json
```

`inference.local.json`의 `REPLACE_*`를 실제 경로와 버전으로 교체한다.
로컬 상대 경로는 **설정 파일이 있는 폴더 기준**이다. `local_files_only=true`가 기본이며
모델이 없으면 명시적인 오류를 반환한다. `local_files_only=false`를 직접 선택하면
Hugging Face ID를 사용할 수 있으며 첫 실행에서 다운로드될 수 있다.

- `model`: 학습된 checkpoint 또는 기반 모델+학습된 adapter 경로를 지정한다.
  Gemma 4 E2B 환경에는 `backend=label_likelihood`, `family=gemma4` 연결 경로를 제공한다.
  라벨 전체 응답의 조건부 log-probability를 세 클래스 모두 계산해 정규화한다.
  자유 생성 문구/퍼센트를 읽어 점수로 사용하지 않는다.
- `sequence_classification`: 학습된 3클래스 분류 checkpoint를 연결하는 대안 어댑터다.
  checkpoint의 `id2label`에 SCAM/NON_SCAM/UNKNOWN 전체 매핑이 있어야 하고,
  가중치가 누락되어 분류 헤드가 임의 초기화되면 오류로 처리한다.
  PEFT 분류 헤드는 학습 단계에서 merged checkpoint로 내보낸 후 연결한다.
- `adapter_path`를 지정할 때는 `adapter_revision`도 지정한다. 기반 모델·tokenizer·adapter
  버전을 함께 관리한다. 학습 절차는 [별도 학습 안내](../model_training/README.md)를 따른다.
- `embedding`: mean pooling을 사용하는 문장 encoder를 지정하고 실제 차원·tokenizer 입력
  한도·고정 버전을 설정한다. 예시의 384차원/128토큰은 **배포 모델의 확정값이 아니다.**
  어떤 모델을 선택했는지에 따라 바꿔야 한다. 짧은 encoder 한도가 대화 길이에 충분한지도 확인한다.
- `model.max_input_tokens`와 `reserved_tokens`는 고정 프롬프트 및 라벨 응답을 포함하도록
  설정한다. 모델·embedding 중 한쪽이라도 한도를 넘으면 입력 오류다. 자동 truncation은 없다.
- 40/60과 검색 초기값은 v1의 임시 시작값이며 실제 성능으로 선정된 값이 아니다.

자세한 입력/학습 연결 계약은 [구현 상태 문서](docs/ARCHITECTURE_STATUS.md)를 참고한다.

## RAG index 생성

평가용 index는 사건 관계를 확인한 뒤 직접 만든 분할 파일을 사용한다.
분할 파일은 아래 구조로 **실제 데이터의 모든 ID를 정확히 한 번씩** 배정한다.
예시 ID는 구조 설명용이며 그대로 현재 데이터에 사용하지 않는다.

```json
{
  "train": ["실제 학습 ID들"],
  "validation": ["실제 검증 ID들"],
  "test": ["실제 평가 ID들"]
}
```

```powershell
python -m architecture.pipeline build-index --config architecture/configs/inference.local.json --split-file architecture/configs/split.local.json --output architecture/artifacts/rag_index.json
```

같은 ID·사건 그룹·동일 직렬화 대화가 여러 분할에 걸치면 중단한다.
train 중 verified=true인 SCAM/NON_SCAM만 embedding한다.
ID가 다르더라도 같은 사건의 파생본일 수 있으므로 그룹 관계는 사람의 확인이 필요하다.
자동으로 그룹 독립성을 확정하거나 유사 중복 제거 규칙을 추가하지 않는다.
분할 파일과 전체 데이터 fingerprint를 index에 기록한다. 모델 학습도 같은 train 분할을 사용한다.

실제 평가가 아닌 새 입력의 기능 확인용 전체 corpus를 만들 때는 의도를 명시한다.

```powershell
python -m architecture.pipeline build-index --config architecture/configs/inference.local.json --all-cases --output architecture/artifacts/prototype_index.json
```

이 index는 `prototype_all_cases_not_for_evaluation`으로 표시된다.
데이터셋 성능 평가용으로 사용하지 않는다. 현재 구현은 임의 분할 파일이나 실제 embedding index를 미리 생성하지 않았다.

## 실제 대화 추론

```powershell
python -m architecture.pipeline infer --config architecture/configs/inference.local.json --index architecture/artifacts/rag_index.json --input architecture/examples/conversation.json --log architecture/artifacts/internal_log.json
```

stdout에는 `risk_score`, `level`, 고정 `message`, `disclaimer`만 출력한다.
내부 수치·사용 사례·설정·입력 hash는 `--log` 파일에 별도로 기록한다.
`risk_score`는 확률이나 백분율이 아닌 0~100 위험 지수다.
예시 대화의 실제 예측값은 학습 모델을 연결한 뒤 확인한다.

데이터셋 평가 대상이라면 ID와 사건 그룹을 함께 지정하여 자기 사례/사건의 RAG 포함을 검사한다.
입력 JSON에는 해당 대화의 `messages`만 전달한다. 실제 ID·그룹은 정답 파일에서 연결한다.

```powershell
python -m architecture.pipeline infer --config architecture/configs/inference.local.json --index architecture/artifacts/rag_index.json --input architecture/artifacts/held_out_conversation.json --query-id 실제_ID --query-group 실제_사건그룹
```

오류는 stderr의 `status=ERROR`, `code`, `message`로 출력하고 exit code 1로 종료한다.
검색 성공 후 근거가 없는 경우에는 Q=0으로 모델 단독 수식이 계산되지만,
모델/검색 장애·잘못된 수치·잘못된 설정은 정상 판정으로 대체하지 않는다.

## 구현 검증과 남은 단계

- 핵심 수식, 문서 예시, 수치 정의역, 입력 공통성, threshold/gap 경계, Q fusion,
  index 저장/복원, 자격 필터, 사건/동일 대화 누수를 표준 라이브러리 테스트로 검사한다.
- 실제 학습 모델·embedding·Transformers API·CUDA 실행은 **실행할 다른 컴퓨터에서 검증할 항목**이다.
- `model_training/`에 QLoRA 라벨 학습 및 산출물 연결을 구현했다. 실제 실행은 다른 컴퓨터에서 진행한다.
  실제 분할·입력 한도·checkpoint 저장/로드 및 GPU 동작을 그 환경에서 확인한다.
  현재 데이터의 UNKNOWN 정답은 0건이며 데이터 라벨이나 verified를 임의로 변경하지 않았다.

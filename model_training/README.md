# v1 모델 학습 파이프라인

설계 기준은 `doc/v1/`이며 전체 기술 배경은 `doc/paper/`를 참고한다.
학습 소스·설정·테스트는 이 폴더에, 추론은 `architecture/`에 구분했다.
데이터는 `dataset/`, 실행 시 생성되는 어댑터는 `models/runs/`에서 공동 관리한다.
아래 명령은 **프로젝트 루트 `r_scam_prototype/`** 기준이며 실제 학습은 실행할 다른 컴퓨터에서 수행한다.

## 학습 방식

기존 `label_likelihood` 추론 어댑터에 연결하는 PEFT LoRA/QLoRA 라벨 학습이다.
기본 설정은 환경 검사기의 Gemma 4 E2B QLoRA 구성에 맞췄다. 모델 및 학습 설정은 실험 전 시작값이며 검증된 최적값이 아니다.

- 추론과 같은 `messages-json-v1` 직렬화와 고정 system 지시문을 사용한다. user에는 대화 JSON만,
  assistant에는 정확한 SCAM/NON_SCAM/UNKNOWN 라벨만 넣는다. ID·그룹·verified·사후 근거는 입력에서 제외한다.
- 학습·추론이 `architecture/pipeline/model/tokenization.py`를 공유한다. thinking은 비활성화한다.
  프롬프트와 padding은 labels=-100, 라벨 및 템플릿 종료 토큰 전체에만 표준 causal cross-entropy를 적용한다.
- 감독 토큰을 예측하는 위치만 `logits_to_keep`로 출력하고 gradient accumulation 전체의 감독 토큰 수로 loss를 정규화한다.
  전체 라벨 log-probability 합을 사용하는 기존 추론과 연결하며 새 점수 수식이나 길이 평균을 추가하지 않는다.
- NF4/double quantization 기반 QLoRA는 기반 모델을 고정하고 LoRA만 학습한다.
  Gemma4에서는 language_model 내부 linear 모듈만 대상으로 삼고 vision/audio tower와 lm_head는 제외한다.
- 모델 프롬프트+라벨 예약량과 embedding 전체 입력 길이를 모두 검사한다. 자동 절단·요약·vocabulary 확장은 하지 않는다.
- Validation loss로 epoch checkpoint를 선택한다. Test는 입력 적합성만 검사하며 학습/선택에 사용하지 않는다.
  최종 Test 성능 평가는 별도 단계이며 현재 결과는 `[실험 후 작성]`이다.

기존 M/R/Q fusion, Risk Score, LOW/UNKNOWN/HIGH 및 고정 안내문은 유지된다. Risk Score는 통계적 확률이 아니다.

## 1. 가벼운 확인

```powershell
python -m model_training audit-data
python -m model_training demo
python -m unittest discover -s model_training/tests -v
python -m unittest discover -s architecture/tests -v
```

데이터 검사와 demo는 ML 설치 없이 실행한다. demo는 합성 fixture 연결 확인이며 가중치/성능 결과를 만들지 않는다.
원본은 372건(SCAM 180, NON_SCAM 192, UNKNOWN 0), 모두 verified=true이다.
study/answer 파일은 입력/정답 쌍이며 train/test 분할이 아니다.
UNKNOWN 정답을 임의 생성하거나 재라벨링하지 않는다. 현재 데이터만 학습하면 UNKNOWN의 직접 감독 학습은 없으며,
세 후보 채점 인터페이스와 최종 Risk Score의 UNKNOWN 구간은 유지된다.

## 2. 사건 분할

같은 사건·부분 대화·번역·의역 파생본은 같은 case_group_id와 분할을 사용한다.
서로 다른 그룹 ID만으로 사건 독립성을 증명할 수 없다. 연구자가 확인한 분할 파일을 직접 지정할 수 있다.
모든 실제 ID를 정확히 한 번씩 배정하고 train/validation/test 모두 비어 있지 않아야 한다.

```json
{
  "train": ["실제 학습 ID"],
  "validation": ["실제 검증 ID"],
  "test": ["실제 최종 평가 ID"]
}
```

초안이 필요하면 실행 컴퓨터에서 다음 명령을 명시적으로 실행한다.

```powershell
python -m model_training propose-split --output artifacts/splits/split.proposal.json --seed 42 --validation-ratio 0.15 --test-ratio 0.15
```

동일 그룹 및 완전 동일 직렬화 대화의 연결 묶음을 통째로 배정한다. 라벨 균형화·유사 대화 제거는 하지 않는다.
비율은 요청값이며 묶음 크기에 따라 실제 비율이 달라진다. 동반 metadata에는 fingerprint·seed·통계와 초안 상태를 기록한다.
사건 독립성 및 번역/의역 관계는 연구자가 확인한다. 그룹을 수정했다면 다시 분할하고 최종본을
`artifacts/splits/split.json` 등으로 보관한다. 이번 구현에서는 실제 분할을 생성하거나 확정하지 않았다.

```powershell
python -m model_training audit-data --split-file artifacts/splits/split.json
```

누락/중복 ID, 교차 사건, 완전 동일 대화의 교차 분할은 오류다. 학습과 RAG index는 동일한 최종 분할을 사용한다.

## 3. 실행 컴퓨터 설치

기존 `CHECK_ENV_and_AUTO_LIB_INSTALLER.py`의 Python 3.11.6, torch 2.7.0/CUDA 12.6,
Transformers 5.14.1, Accelerate 1.14.0, PEFT 0.20.0, bitsandbytes 0.50.2, safetensors 0.8.0 명세를 반영했다.
검사기는 실행 시 누락 패키지를 자동 설치하므로 이번 작업에서는 실행하지 않았다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install torch==2.7.0 --index-url https://download.pytorch.org/whl/cu126
python -m pip install -r model_training/requirements.txt
```

3.11.6 인터프리터와 실제 GPU/driver 조합을 확인한다.
학습은 Transformers Trainer + PEFT를 사용한다. TRL/datasets/psutil은 기존 환경 명세에 보존했으며
현재 학습에서는 SFTTrainer나 datasets 전처리를 사용하지 않는다. 자동 템플릿 변환·절단 없이 기존 계약을 유지한다.

## 4. 설정 및 tokenizer 검사

```powershell
Copy-Item model_training/configs/train.example.json model_training/configs/train.local.json
```

설정을 실행 환경에 맞게 작성한다. 모든 로컬 상대 경로는 **설정 파일 위치 기준**이다.

| 항목 | 설정 내용 |
|---|---|
| data.inputs/answers/split | 기존 데이터와 최종 사건 분할 |
| data.expected_sha256 | 선택적으로 audit-data fingerprint 고정. 원문/정답/그룹 변경 시 중단 |
| data.verified_only | 기본 true. 미검증 train/validation 제외 건수 보고 |
| model.path/revision | 기반 모델 및 보존한 고정 버전. 어댑터를 기반 모델 경로로 지정하지 않음 |
| model.family | Gemma4는 gemma4, 지원되는 다른 causal LM은 causal_lm |
| model.instruction | 생략 시 기존 DEFAULT_INSTRUCTION. 내보낸 추론 설정에도 보존 |
| model.max_input_tokens/reserved_tokens | 실제 프롬프트 및 전체 라벨 종료 토큰을 포함할 한도 |
| embedding | 추론용 mean-pooling encoder의 고정 버전·실제 차원·입력 한도 |
| lora/training | 하드웨어와 Validation에 따라 결정할 실험 시작 설정 |
| training.output_dir | 비어 있는 새 실행 경로. 덮어쓰기/자동 resume 없음 |
| pipeline | 내보낼 기존 추론 설정. Test로 조정하지 않음 |

REPLACE_*를 실제 값으로 교체한다. local_files_only=true가 기본이다.
false를 직접 선택하면 원격 다운로드가 가능하며 main/latest 대신 고정 commit revision이 필요하다.
로컬 모델도 실제 revision과 보존한 파일 버전을 연구 기록에 남긴다.
예시의 384차원/128 embedding 토큰은 확정값이 아니다. 선택한 encoder에 맞춰 변경한다.
한도가 부족하면 실제 context 한도가 충분한 모델을 선택한다. tokenizer 한도만 임의로 올리지 않는다.

```powershell
python -m model_training prepare --config model_training/configs/train.local.json --report artifacts/preflight/run-001.json
```

가중치 없이 tokenizer/AutoConfig만 읽어 전체 분할의 길이·후보 라벨 prefix·정답 분포·누수 조건을 검사한다.
대화 원문/token 배열은 보고서에 저장하지 않는다. 실제 tokenizer의 chat template 호환성은 이 단계에서 확인한다.

환경 검사기의 시작 설정이며 실제 VRAM 사용량이나 실행 성공을 보장하는 값은 아니다.

| VRAM | 전체 token 한도 | batch | accumulation | LoRA r/alpha |
|---|---:|---:|---:|---:|
| 24 GB | 8192 | 1 | 8 | 32/64 |
| 16 GB | 4096 | 1 | 8 | 16/32 |
| 12 GB | 2048 | 1 | 16 | 16/32 |
| 8 GB | 1024 | 1 | 16 | 8/16 |

## 5. 학습

```powershell
$env:CUDA_VISIBLE_DEVICES = "0"
python -m model_training train --config model_training/configs/train.local.json
```

단일 프로세스/노출 GPU 한 개를 지원하며 학습에서 device_map=auto/offload를 사용하지 않는다.
기본 NF4, gradient checkpointing, paged AdamW 8-bit를 사용한다. bf16 미지원 GPU는 dtype=float16으로 설정한다.
작은 CPU 확인은 device=cpu, quantization=none, dtype=float32, optim=adamw_torch로 지정한다.
실제 Gemma/NF4/CUDA의 VRAM 및 API 호환성은 실행 컴퓨터에서 검증한다.

성공 후 생성되는 파일:

```text
models/runs/run-001/
├── checkpoints/             # Validation loss로 선택하는 epoch checkpoint
├── final_adapter/           # 선택된 PEFT 어댑터 + 동일 tokenizer
├── inference_config.json    # 기존 architecture 실행 설정
├── split.json               # 학습/RAG 공통 분할 복사본
├── resolved_config.json
├── preflight_report.json
├── lora_targets.json        # 정확한 대상 모듈·학습 파라미터 수
├── training_log.json
├── training_metrics.json    # 실제 train/validation 손실; test는 placeholder
└── run_manifest.json        # STARTED/FAILED/COMPLETED, 버전·fingerprint·adapter SHA256
```

실패 시 FAILED 기록과 생성된 checkpoint를 보존한다. 재실행은 새 output_dir를 사용한다.
COMPLETED 결과만 연결한다. 기반 모델·embedding을 외부/다른 drive에 두거나 원격 모델을 사용했다면
프로젝트 이동 후 내보낸 경로를 확인한다. 고정 버전, tokenizer, adapter와 split을 함께 보관한다.

## 6. 추론 연결

학습 때와 같은 dataset/정답을 사용한다. 변경됐다면 fingerprint와 사건 분할을 재검토한다.

```powershell
python -m architecture.pipeline build-index --config models/runs/run-001/inference_config.json --split-file models/runs/run-001/split.json --output artifacts/rag_index.json
python -m architecture.pipeline infer --config models/runs/run-001/inference_config.json --index artifacts/rag_index.json --input architecture/examples/conversation.json --log artifacts/inference_log.json
```

RAG에는 같은 train의 verified=true SCAM/NON_SCAM만 입고한다. --all-cases index를 연구 평가에 사용하지 않는다.
평가 대상은 --query-id/--query-group을 함께 지정한다. embedding 교체 시 index를 재생성한다.

## 7. 검증 범위

현재 작업 환경에는 torch/Transformers가 없어 실제 모델 다운로드·학습은 수행하지 않았다.
표준 라이브러리 기반 계약 테스트와 기존 아키텍처 회귀를 검증했다.
torch가 있으면 loss/gradient와 accumulation tensor 검증도 실행한다.
작은 합성 Llama/BERT의 CPU 학습→저장→아키텍처 재로드→추론 연결은 명시적으로 실행할 수 있다.
다운로드 없이 임시 폴더에 toy 가중치만 만들며 실제 데이터와 연구 결과는 변경하지 않는다.

```powershell
$env:R_SCAM_RUN_ML_TESTS = "1"
python -m unittest model_training.tests.test_ml_runtime -v
Remove-Item Env:\R_SCAM_RUN_ML_TESTS
```

toy 검증은 실제 Gemma4/NF4/CUDA 검증을 대신하지 않는다. 성능·임계값·calibration은 `[실험 후 작성]`이다.
설계 대응과 남은 확인은 [구현 상태](docs/TRAINING_STATUS.md)에 기록했다.

## API 확인 근거

공식 API 자료이며 기존 설계·논문에 새 이론/참고문헌을 추가한 것은 아니다.

- [Transformers Trainer](https://huggingface.co/docs/transformers/main_classes/trainer): 학습/검증 및 custom loss.
- [5.14.1 Trainer 소스](https://github.com/huggingface/transformers/blob/v5.14.1/src/transformers/trainer.py): causal shift 및 accumulation 토큰 수.
- [PEFT quantization](https://huggingface.co/docs/peft/developer_guides/quantization), [LoRA 설정](https://huggingface.co/docs/peft/package_reference/lora): k-bit 준비·대상 모듈·adapter.
- [Gemma4](https://huggingface.co/docs/transformers/model_doc/gemma4): 로드 클래스 및 logits_to_keep.

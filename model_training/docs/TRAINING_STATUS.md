# v1 모델 학습 구현 상태

작성일: 2026-10-04. 기준: doc/v1의 네 문서, doc/paper 기술 초안, 기존 아키텍처 학습 연결 계약 및 환경 검사기.
기존 설계·정답 데이터·논문 본문은 변경하지 않았다.

| 설계/구현 계약 | 코드 |
|---|---|
| 입력/정답 분리 및 messages 공통 직렬화 | architecture.pipeline.data/input 재사용, preparation.py |
| 명시적 사건 분할 | split.py + 기존 validate_split. 사건/정확 중복 검사; 파생본 관계는 연구자 확인 |
| verified=true 우선 학습 | data.verified_only 기본 true. 제외 건수 기록; 정답 변경 없음 |
| 세 클래스·고정 지시문·전체 라벨 응답 | 공유 LabelTokenContract. 모든 후보 prefix/예약 길이 검사 |
| 라벨 전용 supervised 학습 | encode_target/pad_features, LabelTrainer. prompt/pad -100, causal shift |
| 모델/query/corpus 입력 길이 계약 | 실제 model/embedding tokenizer + AutoConfig; 초과 시 중단 |
| 기반 모델 고정 및 QLoRA | NF4/double quantization, PEFT k-bit 준비, 언어 모델 linear LoRA만 학습 |
| held-out Test 보존 | train/validation만 Trainer 전달, Test 입력 적합성만 검사 |
| 산출물 연결 | final_adapter + 동일 tokenizer + 기존 inference_config + 동일 split |
| 재현 기록 | 데이터/분할/지시문/템플릿 hash, 설정, 버전, adapter hash, 실제 로그/손실 |

## 데이터 상태

원본 확인: 372건, SCAM 180, NON_SCAM 192, UNKNOWN 0, verified=true 372건.
실제 학습 분할은 이번 작업에서 생성하거나 확정하지 않았다. UNKNOWN을 임의 보충하지 않는다.
현재 데이터만 학습하면 UNKNOWN의 직접 감독 target이 없다는 사실을 기록한다.

## 실행 컴퓨터 확인

현재 환경에는 torch/transformers/peft가 없다. 모델을 다운로드하거나 학습하지 않았다.
표준 라이브러리 계약 및 아키텍처 회귀 테스트를 실행했다.
tensor 검증과 선택적 tiny CPU 통합 검증은 현재 환경에서 skip한다.

검증 결과: 학습 계약/CLI 테스트 22개와 기존 아키텍처 테스트 34개 통과(총 56개).
ML 검증 4개는 미실행으로 구분했다. audit/demo 및 Python 컴파일 검사도 통과했다.
검증 환경 Python은 3.12.14이며 목표 학습 환경 3.11.6에서 실제 ML 실행을 별도로 확인한다.

1. 사건 그룹/파생본 관계를 확인하고 최종 split 및 데이터 fingerprint를 고정한다.
2. 라이브러리/CUDA/driver와 고정 모델·encoder 파일을 확인한다.
3. prepare로 model/embedding 한도와 chat template prefix를 검사한다.
4. ML 테스트로 selective logits의 CE/gradient 동등성과 accumulation을 확인한다.
5. 실제 Gemma4/NF4 학습에서 언어 모델 LoRA 대상, VRAM, forward API, checkpoint 저장/로드를 확인한다.
6. 내보낸 설정과 같은 split으로 train-only RAG index 및 held-out 추론을 연결한다.
7. 성능 및 비교 실험을 별도로 수행한다. 현재 성능 결과: `[실험 후 작성]`.

## 범위

단일 프로세스/장치, 고정 텍스트 라벨 학습과 기존 아키텍처 연결까지 구현했다.
embedding 재학습, 새 기능/수식, 자동 증강/재라벨링, calibration, 별도 UNKNOWN 판정,
최종 Test 성능 보고, 분산 학습/자동 resume는 이번 구현 범위에 포함하지 않는다.
설치 명세와 실행 안내는 [README](../README.md)에 있다.

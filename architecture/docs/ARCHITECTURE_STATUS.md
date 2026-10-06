# v1 아키텍처 구현 상태

작성일: 2026-10-04. 초기 아키텍처의 구현 기록이며 최종 시스템은 `V4/README.md`를 참고한다. 과거 설계 문서는 Git 이력에 보존되어 있다.
아키텍처 소스·설정·예시·테스트·의존성·설명은 `architecture/`에서 관리한다. 모델 학습은 별도 `model_training/`에서 관리한다.
이 파일은 구현 상태를 기록하는 별도 문서이며 기존 v1 설계를 변경하지 않는다.

## 구현과 설계 대응

| 설계 | 구현 |
|---|---|
| Dataset Guide §3.5 공통 입력 | `architecture/pipeline/input.py`: messages만 speaker/text 키 순서로 직렬화, 원문·발화 순서 유지 |
| 입력 길이 계약 | 모델 프롬프트 포함 토큰 수+출력 예약량, embedding 토큰 수를 실제 추론 전에 각각 확인 |
| Risk Formula §3·20.3 | `model/model_scorer.py`: 세 클래스 finite/range/sum 검사, stable softmax, M=p_S-p_N |
| RAG Formula §2·22.1 | `rag/vector_search.py`, `embedder.py`: 자격 필터 선적용, 동일 모델·버전·차원·tokenizer·pooling 검사, L2 cosine |
| RAG Formula §3~14·21 | `rag_processor.py`: Top-8, threshold 0.6, 첫 gap>0.12, 최대 5, W/R/Q/A/Q_eff |
| Risk Formula §8·12 | `formula_engine.py`: 고정 Q fusion, S=50(1+E), 유효 근거 없음 상태는 E=M |
| Risk Formula §15 | `decision/risk_classifier.py`: S<T_L LOW, T_L<=S<=T_H UNKNOWN, S>T_H HIGH |
| Inference Pipeline §14~17 | 고정 문구, 네 필드 사용자 출력, 별도의 내부 로그 |
| 사건 단위 분할 | `data.py`: 입력/정답 ID 연결, 명시적 분할의 ID·그룹·정확 중복 교차 검사 |
| Inference Pipeline §28 오류 | 오류를 typed exception/CLI ERROR로 전달, 정상 Q=0 상태와 장애 구분 |

Q_eff는 진단값이다. Q fusion을 바꾸는 실행 모드, 강제 UNKNOWN override, 새 confidence 출력,
calibration, class-balanced retrieval, source diversity, 중복 가중치 보정 등 Future Work 기능은 구현하지 않았다.

## 모델 학습 단계에 전달할 계약

1. 모델·query·corpus의 분석 대상 문자열은 동일한 `messages-json-v1`이다.
   ID·사건 그룹·라벨·검증 여부·사후 설명을 user 대화 입력에 넣지 않는다.
2. 학습 모델 scorer는 SCAM/NON_SCAM/UNKNOWN 순서의 정규화 점수를 반환해야 한다.
   학습은 별도 model_training의 LoRA/QLoRA 라벨 학습으로 구현했다.
   기반 Gemma checkpoint 자체를 특화 학습 완료로 간주하지 않는다.
3. 생성형 학습 산출물을 연결하는 `label_likelihood` 어댑터는 고정 system 지시문,
   user의 공통 대화 JSON, assistant의 정확한 클래스 문자열을 사용하는 chat template를 따른다.
   `architecture/pipeline/backends.py`의 `DEFAULT_INSTRUCTION` 또는 실행 설정의 `instruction`을
   학습에서도 동일하게 사용하고, thinking은 비활성화한다.
   `model/tokenization.py`의 LabelTokenContract를 학습과 추론이 공유한다.
4. 채점은 세 개의 **전체 assistant 라벨 응답** 각각을 teacher forcing으로 계산한다.
   assistant 종료 토큰까지 포함한 모든 응답 token의 조건부 log-probability를 더한 뒤
   기존 v1 stable softmax를 적용한다. 길이 평균·첫 토큰만의 비교·생성된 퍼센트 파싱은 없다.
   토큰 수가 서로 다른 라벨도 전체 토큰을 계산한다. 이 선택 자체의 calibration을 주장하지 않는다.
5. 템플릿의 생성 prefix와 완성된 라벨 응답 prefix가 tokenizer에서 달라지면 오류다.
   해당 실제 tokenizer/chat template의 호환성은 실행 컴퓨터에서 확인한다.
   채점용 backend는 `logits_to_keep` 지원이 필요하다. 미지원 backend를 임의의 점수로 대체하지 않는다.
6. 분류 헤드 방식은 실제 학습된 3클래스 mapping과 가중치를 요구한다.
   두 방식은 같은 v1 scorer 출력 계약의 backend adapter이며 새로운 증거원이나 판정식을 추가하지 않는다.
7. 모델 학습과 RAG index는 같은 분할 계획을 사용한다. Validation/Test와 연결된 파생본은
   train/corpus에 넣지 않는다. 그룹 식별자의 단순 차이를 독립 사건의 증명으로 보지 않는다.
8. checkpoint·tokenizer·adapter의 버전, 프롬프트, 입력 한도와 라벨 순서를 보존한다.
   embedding 교체 시 index를 재생성하고 threshold/gap의 적정값은 이후 validation에서 확인한다.

## 실행 컴퓨터에서 확인할 내용

- 기존 환경 검사기의 Python 3.11.6, torch 2.7.0, CUDA 12.6 및 라이브러리 버전.
- 실제 Gemma 기반 모델/QLoRA adapter를 저장·로드하는 방식과 학습 출력 템플릿.
- 실제 encoder의 mean-pooling 정의, 차원·입력 한도·고정 revision.
- 전체 대화가 모델과 embedding 한도에 모두 들어오는지. 초과 입력을 자동 요약/절단하지 않는다.
- HF 어댑터의 실제 forward/tokenizer API, suffix logits, dtype, GPU VRAM 및 quantization 호환성.
- 실제 split 파일로 index를 만들고 held-out 입력을 실행하는 통합 확인.

현재 작업 환경에는 torch/transformers가 없으며 실제 모델을 다운로드하지 않았다.
따라서 표준 라이브러리 기반 구조·수식 검증과 실제 ML/GPU 검증을 구분한다.
학습·평가 성능, 실제 모델의 응답이나 embedding 품질을 생성하거나 주장하지 않는다.
학습 코드와 다른 컴퓨터 실행 절차는 [학습 구현 상태](../../model_training/docs/TRAINING_STATUS.md)를 참고한다.

## 라이브러리 연결 근거

아래 공식 자료는 실행 어댑터 API를 확인하기 위한 자료이며 논문에 새 참고문헌을 추가한 것은 아니다.

- [Hugging Face Gemma4](https://huggingface.co/docs/transformers/model_doc/gemma4): 모델 로드 클래스·forward logits.
- [Transformers 모델 로드](https://huggingface.co/docs/transformers/main_classes/model): revision/local_files_only/output_loading_info.
- [mean-pooling encoder 사용 예](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2): attention-mask 기반 pooling.
  이 예시 모델을 프로젝트의 확정 encoder로 선정한 것은 아니다.

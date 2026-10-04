# r_scam_prototype

로맨스 스캠 텍스트 대화 판별 프로토타입이다. 구현을 추론 아키텍처와 모델 학습 파이프라인으로 구분한다.
설계 기준은 `doc/v1/`이며 전체 기술 설명은 `doc/paper/`의 한국어 논문 초안을 참고한다.

## 폴더 구성

```text
r_scam_prototype/
├── architecture/                 # 추론 아키텍처 전체
│   ├── pipeline/                 # 모델 연결·RAG·수식·판정·출력
│   ├── configs/
│   ├── examples/
│   ├── tests/
│   ├── docs/
│   ├── requirements.txt
│   └── README.md
├── model_training/               # 별도 PEFT LoRA/QLoRA 학습 파이프라인
│   ├── configs/                  # 모델·데이터 분할·학습 설정
│   ├── tests/
│   ├── docs/
│   ├── requirements.txt
│   └── README.md
├── dataset/                      # 공통 대화 입력·정답·정제 기록
├── doc/
│   ├── v0.1/
│   ├── v1/
│   └── paper/
├── models/                       # 학습 시 산출물 및 embedding 공용 경로
├── CHECK_ENV_and_AUTO_LIB_INSTALLER.py
├── LICENSE
└── README.md
```

현재 구현된 아키텍처의 코드·설정·예시·테스트·의존성·설명을 `architecture/`에 모았다.
학습 코드는 `model_training/`에 구현했으며 기존 아키텍처와 입력·라벨 토큰 계약을 공유한다.
데이터셋, 설계 문서, 논문 초안과 환경 검사기는 두 영역이 함께 참조한다.

## 아키텍처 실행

프로젝트 루트에서 실행한다. 아래 명령은 모델 다운로드·GPU·학습 없이 구조를 확인한다.

```powershell
python -m unittest discover -s architecture/tests -v
python -m architecture.pipeline audit-data
python -m architecture.pipeline demo
```

`demo`는 고정 합성 수치와 벡터를 사용하는 연결 확인이며 실제 판별 결과가 아니다.
실제 모델·embedding 설치, index 생성과 추론 명령은 [아키텍처 실행 안내](architecture/README.md)에 있다.
구현 범위와 다음 단계 학습 연결 계약은 [아키텍처 구현 상태](architecture/docs/ARCHITECTURE_STATUS.md)를 참고한다.

## 모델 학습

[모델 학습 실행 안내](model_training/README.md)에 데이터 분할, 환경 설치, 설정, QLoRA 학습 및 추론 연결 명령이 있다.
입력/정답 연결, 사건 분할·입력 한도 검사, assistant 라벨 전용 학습, Validation checkpoint 선택,
PEFT adapter/tokenizer 저장과 추론 설정 내보내기를 구현했다. 실제 학습·GPU 실행은 다른 컴퓨터에서 진행한다.

```powershell
python -m model_training audit-data
python -m model_training demo
python -m unittest discover -s model_training/tests -v
```

위 audit/demo는 실제 모델 학습이나 판별 성능 실험이 아니다. 실제 데이터의 분할/학습 가중치는 아직 생성하지 않았다.
현재 데이터의 UNKNOWN 정답은 0건이며 임의 보충하지 않는다. 준비 및 검증 범위는
[학습 구현 상태](model_training/docs/TRAINING_STATUS.md)에 기록했다.

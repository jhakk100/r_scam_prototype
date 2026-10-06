# 최종 검색 결합 분류 시스템

스캠 판별에 특화한 E2B 모델과 동결된 TF-IDF/SVD 사례 검색을 사용한다. 학습된 어댑터와 검색 좌표, 모델 마진 유지 계수는 최종 실험과 동일하다.
저장소 안에서 실행하며 상위 V3·v2 폴더의 코드나 PC별 절대경로에 의존하지 않는다.

## 폴더 구성

- `pipeline.py`, `d03_retrieval.py`, `fusion.py`: 최종 추론, 검색과 결합식.
- `common.py`, `case_retrieval.py`, `topic_behavior.py`, `core.py`: 최종 학습·추론에 필요한 공통 코드.
- `runtime/`: 동결된 TF-IDF/SVD 변환, 검색 인덱스, 입력 특징 규칙과 실행 설정.
- `datasets/training/`: 최종 학습의 train/test, 분할 기록과 입력 특징 설정.
- `datasets/`: 검색 사례, 원본 평가 자료와 테스트 전용 변형. 변형을 학습·검색에 넣지 않는다.
- `experiments/d03-final-paired-20261006_205128/`: 실제 예측, 집계와 평가 당시 소스.
- `paper/`, `docs/`, `map/`: 논문, 기술 명세, 쉬운 안내서와 지도.
- `model/manifest.json`: 최종 어댑터와 토크나이저의 파일 해시. 실제 파일은 `model/final_adapter/`에 두며 Git에서 제외한다.

과거 설계 문서와 중복 자료는 저장소 밖에 보관했다. 평가 소스·프로토콜의 절대경로는 당시 환경의 기록이며 현행 실행에 사용하지 않는다.

## 가중치 없이 확인

Python 3.11을 사용한다.

```powershell
python -m pip install -r V4/requirements-test.txt
python V4/verify_release.py
python V4/serve_map.py
```

검사는 512개 저장 예측의 집계·검색 이웃·수식을 재계산하고 train/test 및 변형 부모의 격리를 확인한다. 모델을 새로 추론하는 ACC 실험은 아니다.
지도 서버가 출력한 localhost 주소로 접속한다. Z는 저장된 SCAM/NON_SCAM 라벨이며 검색 거리는 X·Y만 사용한다.

## 실제 모델 추론

다음 가중치가 별도로 필요하다. 대용량 모델과 토크나이저는 Git에 올리지 않는다.

```text
models_original/E2B/           원본 E2B 전체 모델 파일
V4/model/final_adapter/        선택한 run 20261006_131323의 어댑터와 토크나이저
```

최종 어댑터 fingerprint는 `4f896fca6d1e441937d052fb9002a62b793cb786df7e8c2dd59f121082c2a5ff`다.
원본 revision과 파일 해시는 `model/manifest.json`에 있다. 같은 최종 파일을 복사해야 한다. 기존 로컬 가중치는 보존했다.

CUDA PyTorch를 먼저 설치한 다음 아래를 실행한다. 측정 환경은 Python 3.11, torch 2.7.0+cu126이었다.

```powershell
python -m pip install -r V4/requirements.txt
python V4/pipeline.py --input V4/examples/dialogue.json
```

입력은 `{"messages":[{"speaker":"상대방","text":"대화 내용"},{"speaker":"나","text":"대화 내용"}]}` 형식이다. 정답이나 Z는 입력하지 않는다.
지시문 포함 2048 토큰과 출력 예약 32 토큰을 검사하며 자동으로 자르지 않는다. 최종 검색은 embedding 모델을 로드하지 않는다.

PowerShell에서도 실행할 수 있다. `-PythonPath` 또는 `RSCAM_PYTHON`으로 환경을 지정하며 생략하면 저장소의 `.venv/Scripts/python.exe`, 그다음 PATH의 Python을 사용한다.

```powershell
.\V4\run.ps1 -Mode test -PythonPath 'C:\path\to\python.exe'
.\V4\run.ps1 -Mode infer -InputPath .\V4\examples\dialogue.json
# GPU와 원본/특화 가중치가 모두 필요하며 두 모델을 새로 추론한다.
.\V4\run.ps1 -Mode evaluate
```

## 최종 연산

`M = p_SCAM - p_NON_SCAM`, `R = sum(s/(d+1e-6))/sum(1/(d+1e-6))`이며 SCAM의 s=+1, NON_SCAM의 s=-1이다.

`q = mean(max(0,1-d/(8c)))`, `w = min(0.7,q)`, `M_eff = M(1-0.35q)`, `E = (1-w)M_eff+wR`, `risk = 50(1+E)`.

65%는 q=1일 때 모델 마진 유지율이다. 0점·100점에서만 적용하는 보정이나 고정 65:35 결합이 아니다.
LOW는 40 미만, HIGH는 60 초과, 나머지는 UNKNOWN이다. 지수는 실제 사기 확률로 보정되지 않았다.
검색은 verified train 226건, SCAM/NON_SCAM=113:113이며 후보 8건에서 그룹 중복을 제거한 최대 5건을 참조한다.

자동 정보 부족 표시는 아직 구현되지 않았다. 독립 외부 검증, 계수의 최적성 및 데이터 증가에 따른 정확도의 지속 상승은 입증하지 않았다. 분석 결과를 완전히 신뢰하지 않는다.

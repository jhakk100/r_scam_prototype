# 마음체크 실행 묶음

이 폴더 전체를 그대로 사용합니다. `마음체크_시작.cmd`를 더블클릭하면 로컬 홈페이지가 열립니다. 처음에는 모델 준비에 시간이 걸립니다. 종료할 때는 `마음체크_종료.cmd`를 실행합니다.

Python 설치나 인터넷 연결 없이 이 폴더 안의 자원을 사용합니다. **Windows 64비트, NVIDIA GPU와 호환 NVIDIA 드라이버가 필요합니다.** 현재 검증 환경은 RTX 4070 Ti 12GB입니다. 다른 운영체제나 GPU 환경에서의 동작은 검증하지 않았습니다.

- `app/`, `maeum-check-source/`: 홈페이지 화면·이미지·한국어/영어 문장 인식 자산
- `engine/models_original/E2B/`: 판정에 필요한 원본 모델 가중치
- `engine/V4/model/final_adapter/`: 최종 학습 어댑터와 토크나이저
- `engine/V4/runtime/`: 검색 사례 226건, 고정 검색 좌표·규칙·결합 설정, 제외 대상의 해시와 ID
- `engine/architecture/`, `engine/V4/*.py`, `engine/model_training/artifacts.py`: 추론과 어댑터 무결성 확인에 필요한 코드
- `python/`, `packages/`: 독립 Python 실행 환경과 필요한 라이브러리
- `manifest.json`, `runtime-packages.json`: 포함 파일의 SHA-256과 라이브러리 버전
- `verify_standalone.py`, `verify_integration.py`: 독립 실행과 실제 분석 검증
- `runtime/`: 실행 중 만들어지는 주소와 로그

학습 데이터 전체, 실험 기록, 논문, 이전 모델, 임베딩 모델, 개발 도구는 포함하지 않았습니다. 모델 가중치가 대부분의 용량을 차지하므로 폴더 전체 용량은 작지 않습니다. 원본 모델과 어댑터를 바꾸거나 재학습하지 않았습니다.

대화는 이 컴퓨터에서 처리합니다. 이미지 원본이나 대화를 외부 서버로 보내지 않으며, 대화 원문을 자동으로 파일에 저장하지 않습니다. 결과 저장 버튼을 누른 경우에만 사용자가 텍스트 파일을 내려받습니다.

개발자 검증은 이 폴더에서 `python\python.exe verify_standalone.py`로 실행합니다. 서버를 먼저 연 뒤 `python\python.exe verify_integration.py`로 실제 GPU 추론을 확인할 수 있습니다.

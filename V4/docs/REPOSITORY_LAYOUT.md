# 저장소 폴더 이전 안내

최종 시스템을 `r_scam_prototype/V4/`로 묶었다. 논문의 쉬운 용어 수정본을 `paper/romance_scam_ko.docx`로 선택했다.
모델 가중치, 검색 좌표, 규칙, 결합 계수와 실제 실험 결과는 바꾸지 않았다.
기술 명세 DOCX와 쉬운 설명 PDF는 실험 당시 작성본을 보존했다. 실행 경로는 현재 README와 이 안내를 기준으로 한다.

| 이전 의존성 | 현재 위치 |
|---|---|
| V3의 공통 코드 | `V4/common.py`, `case_retrieval.py`, `topic_behavior.py`, `core.py` |
| V3의 최종 학습 자료 | `V4/datasets/training/` |
| V3의 최종 어댑터 | `V4/model/final_adapter/` (로컬 전용) |
| 원본 E2B 가중치 | `models_original/E2B/` (로컬 전용) |
| v2의 Python, V3의 semantic311 | 사용자가 설치한 Python 3.11 환경과 `V4/requirements*.txt` |
| 모델 백엔드 | `architecture/pipeline/backends.py` |
| 어댑터 무결성 검사 | `model_training/artifacts.py` |

실행 설정의 `@repo/` 경로는 저장소 루트를 기준으로 해석한다. 모델 설정의 상대경로는 설정 파일 위치가 기준이다.
과거 예측의 모델 identity, 소스 스냅샷 및 프로토콜에 기록된 절대경로는 당시 추론의 이력이다.
원본 모델과 최종 어댑터는 로컬에 보존하며 Git에서 제외했다. 다른 컴퓨터에서 실제 추론하려면 같은 파일을 별도로 배치해야 한다.
변형 80건과 정보 부족 10건은 테스트 전용이며 학습이나 검색 자료에 추가하지 않는다.

# CHANGELOG

| 수정 문서 | 기존 문제 | 최소 수정 내용 | 수정 근거가 된 critical review 항목 |
|---|---|---|---|
| 전체 4개 문서 | 원본과 최종본의 버전 구분 필요 | 원본을 `doc/v0.1/`에 그대로 보존하고 `doc/v1/` 수정본의 제목·버전 표기를 v1로 변경 | 해당 없음 — 사용자 버전 분리 요청 |
| [Dataset Guide](romance_scam_dataset_guide_v1.md) §3.4 | UNKNOWN·미검증 라벨의 RAG 사용 자격 미정 | 검증된 SCAM/NON_SCAM만 검색 전에 입고하고 UNKNOWN 제외·미지원 라벨 오류 명시 | [#1 CRITICAL](../critical_design_review_ko/critical_design_review_ko.md) |
| Dataset Guide §2·3.3~3.4·4~6·11 | 사건 결과·관찰 신호·verified 의미 혼재 및 관찰 근거 없는 예시 | 사건 결과 라벨과 검토 근거를 정의하고 관찰 가능한 주석만 유지; 예시 단계·위험 신호와 작성 프롬프트 최소 보정 | #4 HIGH |
| Dataset Guide §3.5 | 정답 metadata 혼입 및 모델·검색 관찰 범위 불일치 가능 | messages 전용 공통 JSON 직렬화·양쪽 길이 검사·초과 오류 명시; 자동 truncation 금지 | #15 HIGH |
| Dataset Guide §9.3 | 파생본·Validation 사건 누수의 평가 한계 | 원본 그룹·분할 계승과 평가 사건 격리를 연구·평가 주석으로만 추가 | #2 CRITICAL·조건부 |
| Dataset Guide §8 | 5:5 학습 비율의 운영 성능 일반화 한계 | 기존 비율을 유지하고 후속 분포 실험 주석만 추가 | #9 HIGH |
| [Inference Pipeline](romance_scam_inference_pipeline_v1.md) §1·9·11·17·22~23·26~27 | Q/Q_eff 결합 기준과 모듈 간 전달값 불일치 | Q fusion을 고정 기준으로 연결하고 raw Q·A·Q_eff 필드 및 RAG 반환 키 매핑·의사코드 일치 | #3 HIGH |
| Inference Pipeline §3·26 | 모델·검색 입력에 metadata나 다른 대화 구간이 사용될 수 있음 | Dataset §3.5 공통 입력 계약과 길이 초과 오류를 참조 | #15 HIGH |
| Inference Pipeline §4·19 | 모델 수치 출력 형식·변환 미정 | Risk §20.3의 정규화된 3클래스 점수 계약 참조 | #11 HIGH |
| Inference Pipeline §5·21 | UNKNOWN·미검증 검색 결과의 증거 유입 가능 | verified 필드와 검증된 이진 라벨 자격·명시적 매핑 계약 연결 | #1 CRITICAL |
| Inference Pipeline §6·21 | raw metric과 수식 similarity의 연결 미정 | RAG §22.1의 고정 cosine adapter 참조 | #14 HIGH |
| Inference Pipeline §13·17 | 모델 UNKNOWN과 최종 보류의 의미 혼동 | 기존 판정 유지 주석과 p_U 내부 기록 추가 | #12 HIGH |
| Inference Pipeline §28 | 잘못된 수치·설정의 처리 경로 불명확 | 수식 문서의 finite·정의역 검사 실패를 기존 오류 경로에 연결 | #13 HIGH |
| Inference Pipeline §29 | 사건 누수·공동 오류·보류 평가·반복 튜닝의 연구 한계 | 사건 분할, 독립성 해석, UNKNOWN 평가 분모, Test 재튜닝을 Future Work 주석으로만 추가 | #2 CRITICAL·조건부, #10·#16·#17 HIGH |
| [RAG Retrieval Formula](romance_scam_rag_retrieval_formula_v1.md) §2·7·21 | SCAM 이외 라벨을 NON_SCAM으로 변환 | 검색 전 검증된 이진 라벨 자격을 적용하고 의사코드에 명시 매핑·재검사·오류 처리 추가 | #1 CRITICAL |
| RAG Retrieval Formula §2 | corpus와 query의 입력 범위 미정 | Dataset §3.5의 messages 공통 입력 계약 참조 | #15 HIGH |
| RAG Retrieval Formula §0~1·14~15·21·24~25 | Risk의 Q fusion과 Q_eff fusion이 충돌 | 기존 Risk의 Q fusion으로 통일하고 A·Q_eff 계산은 진단값으로 보존 | #3 HIGH |
| RAG Retrieval Formula §6 | gap 경계·동률·0/1개 후보의 구현 규칙 불명확 | 기존 첫 gap 및 엄격한 초과 비교를 명시하고 동률 입력 순서·빈 집합 처리 확정 | #7 HIGH |
| RAG Retrieval Formula §9·21 | 잘못된 파라미터·NaN/Inf·작은 W에서 수치 오류 가능 | 양수 gamma 등 정의역과 finite 검사 추가; W=0 분기 유지 및 동일 수식의 expm1 계산 적용 | #13 HIGH |
| RAG Retrieval Formula §22.1 | similarity 정규화 척도가 미정 | cosine→max(0,c)와 cosine distance 변환 고정; 영벡터·미지원 metric·명백한 범위 오류 거부 | #14 HIGH |
| RAG Retrieval Formula §10·12~14 | R·Q·A를 정답 신뢰도나 독립 근거로 오해할 수 있음 | 가중 라벨·가중치 총량 해석과 중복·단일 이웃·Q_eff 비단조성 주석만 추가 | #5·#8·#10 HIGH |
| RAG Retrieval Formula §18·23 | gap 우월성·안정성 및 기타 설계 효과가 미검증 | gap 민감도, 결합·중복·분포·공동 오류·반복 선택 비교를 주석/Future Work로만 명시 | #5·#7~#10·#17 HIGH |
| [Risk Scoring Formula](romance_scam_risk_scoring_formula_v1.md) §4 | RAG 라벨 자격과 수식의 연결 누락 | 검증된 이진 라벨만 R·Q 계산에 포함하고 무효 라벨 오류 명시 | #1 CRITICAL |
| Risk Scoring Formula §8 | Q와 Q_eff 결합 기준 충돌 | fusion_mode=q 고정, raw Q만 결합하며 A·Q_eff는 진단값으로 보존 | #3 HIGH |
| Risk Scoring Formula §3.1·20.3 | logits·log-probability와 정규화 점수의 변환 계약 부족 | finite·범위·합 오차 검사 및 안정적 softmax adapter 명시 | #11·#13 HIGH |
| Risk Scoring Formula §6·20.4 | 일반 설정 정의역과 W=0 연산 순서 미명시 | 유한 수·파라미터 범위·W=0 선행 분기·expm1 구현 명시 | #13 HIGH |
| Risk Scoring Formula §20.2 | metric 변환 척도 모호 | RAG §22.1의 공통 adapter 참조 및 미지원 metric 오류 명시 | #14 HIGH |
| Risk Scoring Formula §3.2 | 모델 UNKNOWN과 최종 보류 혼동 | M은 방향 margin이며 UNKNOWN argmax를 보존하지 않는다는 의미 주석 추가 | #12 HIGH |
| Risk Scoring Formula §1·10·22 | 강충돌 UNKNOWN 보장·통계 독립성으로 읽힐 수 있음 | 상쇄 조건·threshold 판정·독립성 한계 주석만 추가 | #6·#10 HIGH |
| Risk Scoring Formula §7.2 | Q를 독립 사건의 정답 신뢰도로 해석할 수 있음 | 가중치 총량 지수와 중복·단일 이웃 한계 주석만 추가 | #8 HIGH |
| Risk Scoring Formula §16 | 기존 비용식을 정답 UNKNOWN까지 확장할 위험 | 검증된 이진 정답 적용 범위와 보류 포함 평가를 Future Work 주석으로 명시 | #16 HIGH |
| Risk Scoring Formula §19 | 반복 validation 선택 및 중복 가중치 탐색의 한계 | 탐색 기록·Test 분리·가중치 비율 해석을 Future Work 주석으로만 추가 | #17 HIGH |

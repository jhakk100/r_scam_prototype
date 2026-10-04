# Romance Scam Risk Scoring Formula v1

## 1. 문서 목적

이 문서는 로맨스 스캠 탐지 시스템에서 **LLM 기반 모델 판단과 RAG 검색 결과를 하나의 위험 점수로 결합하기 위한 수학적 판정식**을 정의한다.

이 시스템의 핵심 목표는 다음과 같다.

1. 모델과 RAG가 서로 다른 방향의 판단을 내릴 수 있음을 허용한다.
2. 한쪽의 근거가 약하면 다른 쪽의 강한 판단을 불필요하게 뒤집지 않도록 한다.
3. 모델과 RAG가 정면 충돌할 경우, 양쪽의 강한 증거가 서로 상쇄되어 `UNKNOWN`에 가까워지도록 한다.
4. 출력값을 통계적 확률처럼 오해하지 않도록 **확률(%)이 아닌 0~100 위험 점수**로 표현한다.
5. 데이터가 아직 적은 초기 프로토타입에서도 해석 가능하고 안정적으로 사용할 수 있도록 한다.

> 해석 주석: 3번은 설계 의도이며, 반대 방향 증거가 있다는 사실만으로 최종 `UNKNOWN`을 보장하지는 않는다. 실제 판정은 결합값과 §15의 threshold로 정한다(critical review #6).

---

# 2. 기본 아이디어: 모든 판단을 하나의 증거 축으로 변환

모델과 RAG의 결과를 바로 0~100 점수로 합치지 않는다.

먼저 모든 판단을 다음 범위의 **증거값(Evidence)** 으로 표현한다.

\[
-1 \le E \le 1
\]

의미는 다음과 같다.

| Evidence 값 | 의미 |
|---:|---|
| -1 | 매우 강한 NON_SCAM 근거 |
| -0.5 | 비교적 강한 NON_SCAM 근거 |
| 0 | 중립 / 판단 불가 / 근거 충돌 |
| +0.5 | 비교적 강한 SCAM 근거 |
| +1 | 매우 강한 SCAM 근거 |

즉, 전체 시스템을 다음과 같은 하나의 축으로 생각한다.

```text
NON_SCAM  <--------------------  UNKNOWN  -------------------->  SCAM
   -1                              0                              +1
```

최종 위험 점수는 모든 증거를 결합한 뒤 마지막 단계에서만 0~100으로 변환한다.

---

# 3. Model Evidence

## 3.1 모델 출력 정의

모델이 다음 세 클래스에 대한 정규화된 점수를 출력한다고 가정한다.

\[
p_S = P(SCAM)
\]

\[
p_N = P(NON\_SCAM)
\]

\[
p_U = P(UNKNOWN)
\]

그리고

\[
p_S+p_N+p_U=1
\]

이라고 한다.

> 주의: 여기서 `P` 표기는 계산 편의를 위한 모델 내부 점수 표현이다. 실제 통계적으로 calibration된 확률이라는 의미로 해석해서는 안 된다.

세 점수는 모두 유한한 \([0,1]\) 값이어야 하며, 합계 검증과 모델 출력 변환은 §20.3의 단일 계약을 따른다.

---

## 3.2 Model Evidence 공식

모델의 증거값을 다음과 같이 정의한다.

\[
\boxed{M=p_S-p_N}
\]

따라서

\[
-1 \le M \le 1
\]

이다.

### 예시 1: SCAM 우세

\[
p_S=0.80,\quad p_N=0.10,\quad p_U=0.10
\]

이면

\[
M=0.80-0.10=0.70
\]

즉, 강한 SCAM 방향의 증거이다.

### 예시 2: NON_SCAM 우세

\[
p_S=0.10,\quad p_N=0.80,\quad p_U=0.10
\]

이면

\[
M=0.10-0.80=-0.70
\]

즉, 강한 NON_SCAM 방향의 증거이다.

### 예시 3: UNKNOWN 우세

\[
p_S=0.10,\quad p_N=0.10,\quad p_U=0.80
\]

이면

\[
M=0
\]

즉, 모델 자체가 명확한 방향성을 갖지 않는 상태가 된다.

### 장점

이 구조에서는 UNKNOWN을 별도의 복잡한 예외 규칙으로 처리하지 않아도 된다.

SCAM과 NON_SCAM의 차이가 작아질수록 모델 증거는 자동으로 0에 가까워진다.

> 의미 주석: \(M\)은 3클래스 argmax가 아닌 방향 margin이다. \(|M|\le1-p_U\)이지만, UNKNOWN이 argmax여도 최종 UNKNOWN을 강제하지 않는다. 예를 들어 \((p_S,p_N,p_U)=(0.48,0.03,0.49)\)는 \(M=0.45\)이다. v1은 기존 변환을 유지하고 최종 보류는 §15에서 결정한다(critical review #12).

---

# 4. RAG Evidence

RAG는 현재 입력과 유사한 과거 사례를 Top-k 방식으로 검색한다.

각 검색 결과에 대해 다음 두 값을 사용한다.

- similarity: \(s_i\)
- label: \(y_i\)

라벨은 다음과 같이 수치화한다.

계산 대상은 `verified == true`이고 `label`이 `SCAM` 또는 `NON_SCAM`인 검색 사례로 한정한다. `UNKNOWN`과 미검증 사례는 방향 증거 및 Quality 계산에서 제외하며, 미지원 라벨은 데이터 오류로 처리한다. 자격 필터 및 검색 절차는 RAG Retrieval Formula v1을 따른다(critical review #1).

\[
y_i=
\begin{cases}
+1 & \text{SCAM}\\
-1 & \text{NON\_SCAM}
\end{cases}
\]

---

# 5. Similarity Weight

단순 cosine similarity 값을 그대로 가중치로 사용하는 대신, 일정 threshold 이하의 검색 결과는 제거한다.

threshold를

\[
\tau
\]

라고 정의한다.

초기 프로토타입의 권장 시작값은

\[
\tau=0.60
\]

이다.

검색 결과 \(i\)에 대한 가중치 \(w_i\)를 다음과 같이 정의한다.

\[
\boxed{
w_i=
\left(
\frac{s_i-\tau}{1-\tau}
\right)^\gamma
}
\]

단,

\[
s_i \ge \tau
\]

일 때만 사용한다.

그리고

\[
s_i < \tau
\]

이면

\[
w_i=0
\]

으로 처리한다.

---

## 5.1 \(\gamma\)의 의미

\(\gamma\)는 similarity가 높은 사례를 얼마나 강하게 우대할지 결정한다.

초기값으로는

\[
\gamma=1
\]

을 권장한다.

\(\tau=0.60\), \(\gamma=1\)인 경우:

| similarity \(s_i\) | weight \(w_i\) |
|---:|---:|
| 0.60 | 0.00 |
| 0.70 | 0.25 |
| 0.80 | 0.50 |
| 0.90 | 0.75 |
| 1.00 | 1.00 |

이 구조의 중요한 목적은 **threshold를 겨우 넘은 사례와 매우 유사한 사례를 동일한 수준의 근거로 취급하지 않는 것**이다.

---

# 6. RAG Evidence 공식

RAG가 제공하는 방향성 있는 증거를 다음과 같이 정의한다.

이 나눗셈은 \(W=\sum_iw_i>0\)일 때만 계산한다. 문서 내 모든 R 계산에서 \(W=0\)이면 먼저 §20.1의 \(R=Q=0\) 분기를 적용한다.

\[
\boxed{
R=
\frac{\sum_i w_i y_i}
{\sum_i w_i}
}
\]

따라서

\[
-1 \le R \le 1
\]

이다.

의미는 다음과 같다.

| R 값 | 의미 |
|---:|---|
| -1 | 검색 결과가 거의 모두 강한 NON_SCAM 사례 |
| 0 | 검색 결과가 서로 충돌하거나 유효한 방향성이 없음 |
| +1 | 검색 결과가 거의 모두 강한 SCAM 사례 |

---

## 6.1 계산 예시

Top-4 검색 결과가 다음과 같다고 하자.

| similarity | label |
|---:|---|
| 0.90 | SCAM |
| 0.86 | SCAM |
| 0.82 | NON_SCAM |
| 0.70 | SCAM |

\(\tau=0.60\), \(\gamma=1\)이면 대략적인 가중치는 다음과 같다.

\[
0.75,\quad0.65,\quad0.55,\quad0.25
\]

따라서

\[
R=
\frac{0.75+0.65-0.55+0.25}
{0.75+0.65+0.55+0.25}
\]

\[
R=\frac{1.10}{2.20}=0.50
\]

즉 RAG는 SCAM 방향으로 약 +0.5의 증거를 제공한다.

---

# 7. RAG Evidence Quality

RAG의 가장 중요한 문제 중 하나는 다음과 같다.

> Top-k 결과가 존재한다고 해서 그 검색 결과가 항상 믿을 만한 것은 아니다.

예를 들어 Top-3 결과가

```text
0.61
0.62
0.63
```

이라면 모두 threshold를 통과했더라도 실제로는 매우 약한 근거이다.

따라서 RAG에는 **방향성(R)** 과 별도로 **검색 근거의 질(Q)** 을 정의한다.

---

## 7.1 RAG Quality 공식

\[
\boxed{
Q=
1-\exp\left(
-\frac{\sum_i w_i}{\kappa}
\right)
}
\]

범위는

\[
0\le Q<1
\]

이다.

초기 프로토타입에서는

\[
\kappa=1
\]

을 시작값으로 사용할 수 있다.

---

## 7.2 Q의 의미

\[
\sum_iw_i \approx 0
\]

이면

\[
Q \approx 0
\]

이다.

즉, RAG 결과가 거의 신뢰할 수 없는 상태이다.

반대로 높은 similarity를 가진 사례가 여러 개 검색되면

\[
Q \rightarrow 1
\]

에 가까워진다.

따라서 R과 Q의 의미를 반드시 구분한다.

```text
R = RAG가 어느 방향을 주장하는가?
Q = 그 주장을 얼마나 신뢰할 수 있는가?
```

> 해석 주석: 여기서 Q는 검색 가중치 총량의 heuristic 지수이며, 정답 신뢰도나 독립 사건 수의 추정량이 아니다. 같은 사건의 중복도 Q를 높일 수 있고, R=±1도 가중치가 아주 작을 때 가능하다. 중복 통제 방식과 단일 이웃 허용 정도의 효과는 후속 실험에서 확인한다(critical review #8).

---

# 8. Model + RAG Evidence Fusion

모델과 RAG를 단순 50:50으로 평균하지 않는다.

**v1의 단일 결합 기준은 이 절의 Q fusion이다.** `fusion_mode="q"`를 고정 설정/로그값으로 사용하며, RAG의 `rag_quality`는 원래 \(Q\)를 뜻한다. \(A=|R|\)와 \(Q_{eff}=QA\)는 각각 `rag_agreement`, `rag_effective_quality` 진단값으로만 보존한다. 현재 결합식에 \(Q_{eff}\)를 대입하거나 Agreement를 추가로 곱하지 않는다. Q_eff fusion의 선택은 향후 비교 실험 대상이며 v1의 별도 실행 모드를 요구하지 않는다(critical review #3).

최종 통합 Evidence를 다음과 같이 정의한다.

\[
\boxed{
E=
\frac{
\alpha M+\beta QR
}{
\alpha+\beta Q
}
}
\]

여기서

- \(M\): Model Evidence
- \(R\): RAG Evidence
- \(Q\): RAG Evidence Quality
- \(\alpha\): Model 기본 가중치
- \(\beta\): RAG 기본 가중치

이다.

초기 프로토타입에서는

\[
\alpha=1,\quad\beta=1
\]

로 시작한다.

그러면 식은 다음처럼 단순화된다.

\[
\boxed{
E=
\frac{M+QR}{1+Q}
}
\]

---

# 9. 이 Fusion 식을 사용하는 이유

## 9.1 RAG 검색이 실패한 경우

RAG가 유효한 근거를 찾지 못했다면

\[
Q\approx0
\]

이다.

따라서

\[
E=
\frac{M+0R}{1}
=M
\]

즉,

\[
\boxed{E=M}
\]

이 된다.

RAG를 위한 별도의 복잡한 fallback 규칙 없이 모델 단독 판정으로 자연스럽게 전환된다.

---

## 9.2 RAG가 매우 강한 경우

\[
Q\approx1
\]

이면

\[
E\approx\frac{M+R}{2}
\]

이므로 모델과 RAG가 거의 동등한 수준으로 결합된다.

---

## 9.3 RAG가 약한 경우

예를 들어

\[
Q=0.2
\]

이면

\[
E=
\frac{M+0.2R}{1.2}
\]

이다.

즉 신뢰도가 낮은 RAG 결과가 강한 모델 판단을 쉽게 뒤집지 못한다.

---

# 10. 핵심 특징: 서로 반대되는 강한 증거의 상쇄

이 공식에서 가장 중요한 특성 중 하나이다.

모델이 강한 SCAM 판정을 내렸다고 하자.

\[
M=+0.8
\]

반대로 RAG가 강한 NON_SCAM 근거를 제시한다고 하자.

\[
R=-0.9
\]

그리고 RAG Quality도 매우 높다고 하자.

\[
Q=0.95
\]

그러면

\[
E=
\frac{0.8+0.95(-0.9)}{1+0.95}
\]

\[
E=
\frac{-0.055}{1.95}
\approx-0.028
\]

즉 최종 Evidence는 거의 0이 된다.

이는 시스템이 다음과 같이 해석해야 한다는 뜻이다.

> 모델과 RAG 모두 강한 근거를 가지고 있지만 서로 정반대의 결론을 제시하고 있다. 따라서 확정 판정을 내리지 말고 UNKNOWN에 가깝게 처리한다.

이 구조의 장점은 **한쪽의 오류가 다른 쪽의 독립적인 근거에 의해 견제될 수 있다는 것**이다.

> 해석 주석: 위 수치에서는 UNKNOWN 구간에 들어가지만 일반적인 충돌의 결과는 보장되지 않는다. 정확한 상쇄 조건은 \(\alpha M+\beta QR=0\)이며 UNKNOWN 여부는 §15의 threshold 조건을 별도로 만족해야 한다. 또한 두 모듈이 분리되어 있다는 사실이 오류의 통계적 독립성을 뜻하지는 않는다. 같은 단서에 대한 공동 오류는 향후 평가 대상이다. 별도 충돌 override나 새로운 결합 규칙은 추가하지 않는다(critical review #6, #10).

---

# 11. 반대 근거가 약한 경우

모델은 강한 SCAM 판정을 내렸다고 하자.

\[
M=0.8
\]

RAG는 반대 방향이다.

\[
R=-0.9
\]

그러나 RAG Quality가 낮다.

\[
Q=0.1
\]

그러면

\[
E=
\frac{0.8+0.1(-0.9)}{1.1}
\]

\[
E\approx0.645
\]

즉 낮은 신뢰도의 검색 결과 몇 개 때문에 강한 모델 판정이 뒤집히지 않는다.

---

# 12. Final Risk Score

통합 Evidence \(E\)를 마지막 단계에서 0~100 점수로 변환한다.

\[
\boxed{
S=50(1+E)
}
\]

따라서

\[
0\le S\le100
\]

이다.

| E | Risk Score |
|---:|---:|
| -1.0 | 0 |
| -0.5 | 25 |
| 0 | 50 |
| +0.5 | 75 |
| +1.0 | 100 |

---

# 13. 매우 중요한 해석 규칙

최종 점수는 **확률이 아니다.**

예를 들어

```text
Risk Score = 76
```

이라고 출력되었다고 해서

```text
로맨스 스캠일 확률 = 76%
```

라고 해석하면 안 된다.

올바른 표현은 다음과 같다.

```text
Romance Scam Risk Score: 76 / 100
```

또는

```text
Romance Scam Risk Index: 76
```

이다.

확률로 표현하려면 별도의 calibration 데이터와 검증 과정이 필요하다.

---

# 14. 최종 계산 예시

모델 출력이 다음과 같다고 하자.

\[
p_S=0.72
\]

\[
p_N=0.18
\]

\[
p_U=0.10
\]

Model Evidence는

\[
M=0.72-0.18=0.54
\]

이다.

RAG 계산 결과가

\[
R=0.50
\]

이고

\[
\sum_iw_i=2.20
\]

이라고 하자.

\(\kappa=1\)이면

\[
Q=1-e^{-2.20}
\]

\[
Q\approx0.889
\]

이다.

따라서 최종 Evidence는

\[
E=
\frac{0.54+(0.889)(0.50)}{1+0.889}
\]

\[
E\approx0.521
\]

이다.

최종 Risk Score는

\[
S=50(1+0.521)
\]

\[
\boxed{S\approx76.1}
\]

따라서 시스템 출력 예시는 다음과 같다.

```text
Romance Scam Risk Score: 76 / 100
```

---

# 15. Risk Score와 Class 판정을 분리

Risk Score와 최종 Class는 같은 개념으로 사용하지 않는 것을 권장한다.

Class 판정은 별도의 threshold를 사용한다.

\[
\boxed{
Class(S)=
\begin{cases}
NON\_SCAM & S<T_L\\
UNKNOWN & T_L\le S\le T_H\\
SCAM & S>T_H
\end{cases}
}
\]

초기 실험용 예시는 다음과 같다.

\[
T_L=40,\quad T_H=60
\]

그러면

```text
0  ~ 39  -> NON_SCAM
40 ~ 60  -> UNKNOWN
61 ~100  -> SCAM
```

으로 사용할 수 있다.

단, 40/60은 설명 및 초기 프로토타입용 예시일 뿐이다.

최종 threshold는 validation 데이터에서 결정해야 한다.

---

# 16. Threshold 최적화

향후 충분한 validation 데이터가 확보되면 오분류 비용을 정의할 수 있다.

\[
\boxed{
Loss=
C_{FN}FN+
C_{FP}FP+
C_UU
}
\]

여기서

- \(FN\): 실제 SCAM을 NON_SCAM으로 놓친 경우
- \(FP\): 실제 NON_SCAM을 SCAM으로 잘못 판단한 경우
- \(U\): UNKNOWN으로 보낸 경우
- \(C_{FN}\): False Negative 비용
- \(C_{FP}\): False Positive 비용
- \(C_U\): UNKNOWN 비용

이다.

로맨스 스캠 탐지에서는 실제 서비스 목적에 따라 False Negative와 False Positive의 비용이 동일하지 않을 수 있다.

따라서 향후 \(T_L\), \(T_H\)는 위 Loss를 최소화하도록 조정하는 것이 가능하다.

> Future Work — 평가 범위: 위 비용식은 검증된 SCAM/NON_SCAM 정답 집합에서 예측 UNKNOWN을 보류로 다루는 식이다. 정답 UNKNOWN의 비용은 정의되지 않았으므로 이 식에 섞지 않는다. 향후 성능 평가 시 전체 SCAM Recall의 분모에는 SCAM→UNKNOWN도 포함하고, 보류율·coverage와 확정 판정만의 오류를 구별한다. 비용과 필요한 최소 coverage는 최적화 전에 정해야 한다. 현재 프로토타입의 수식이나 판정 규칙은 변경하지 않는다(critical review #16).

---

# 17. Risk와 Confidence는 분리해야 한다

Risk Score가 50이라고 해서 항상 같은 상황은 아니다.

예를 들어 다음 두 상황을 비교한다.

## Case A: 정보 부족

\[
M\approx0
\]

\[
R\approx0
\]

모델과 RAG 모두 명확한 판단을 하지 못하는 경우이다.

## Case B: 강한 충돌

\[
M=+1
\]

\[
R=-1
\]

모델과 RAG 모두 매우 강한 판단을 내렸지만 서로 정반대 방향인 경우이다.

두 경우 모두 최종 Risk Score는 50 근처가 될 수 있다.

그러나 의미는 완전히 다르다.

따라서 장기적으로 다음과 같이 별도의 지표를 출력하는 것을 권장한다.

```text
Risk Score: 51 / 100
Evidence Confidence: LOW
Model-RAG Agreement: VERY LOW
```

즉 다음 세 개념을 구분해야 한다.

```text
Risk       = 어느 방향으로 위험한가?
Confidence = 현재 근거 자체가 얼마나 충분한가?
Agreement  = 모델과 RAG가 얼마나 같은 결론을 내리는가?
```

---

# 18. 전체 공식 요약

## Step 1. Model Evidence

\[
\boxed{M=p_S-p_N}
\]

---

## Step 2. RAG Similarity Weight

\[
\boxed{
w_i=
\left(
\frac{s_i-\tau}{1-\tau}
\right)^\gamma
}
\]

단,

\[
s_i<\tau \Rightarrow w_i=0
\]

---

## Step 3. RAG Evidence

\[
\boxed{
R=
\frac{\sum_iw_iy_i}
{\sum_iw_i}
}
\]

---

## Step 4. RAG Quality

\[
\boxed{
Q=
1-\exp\left(
-\frac{\sum_iw_i}{\kappa}
\right)
}
\]

---

## Step 5. Evidence Fusion

일반형:

\[
\boxed{
E=
\frac{
\alpha M+\beta QR
}{
\alpha+\beta Q
}
}
\]

초기 프로토타입:

\[
\alpha=\beta=1
\]

따라서

\[
\boxed{
E=
\frac{M+QR}{1+Q}
}
\]

---

## Step 6. Final Risk Score

\[
\boxed{
S=50(1+E)
}
\]

---

# 19. 초기 권장 하이퍼파라미터

현재 소규모 프로토타입을 기준으로 다음 값을 시작점으로 사용한다.

| Parameter | Initial Value | Meaning |
|---|---:|---|
| Top-k | 3~5 | 검색할 유사 사례 수 |
| \(\tau\) | 0.60 | 최소 similarity |
| \(\gamma\) | 1.0 | similarity 가중치 곡률 |
| \(\kappa\) | 1.0 | RAG Quality 증가 속도 |
| \(\alpha\) | 1.0 | Model 기본 가중치 |
| \(\beta\) | 1.0 | RAG 기본 가중치 |
| \(T_L\) | 40 (임시) | NON_SCAM / UNKNOWN 경계 |
| \(T_H\) | 60 (임시) | UNKNOWN / SCAM 경계 |

이 값들은 고정된 이론 상수가 아니다.

데이터가 증가하면 validation set을 통해 조정해야 한다.

> Future Work — 선택 과적합: 작은 validation에서 반복 튜닝한 최댓값이 새 사건에서도 유지된다고 보장할 수 없다. 후속 튜닝에서는 탐색 범위와 선택 횟수를 기록하고 Test를 재튜닝에 사용하지 않는다. 같은 양수 배율의 \(\alpha,\beta\)는 동일한 결합이므로 그 비율이 실질적인 조정 대상이다. v1의 초기값과 기능 범위는 유지한다(critical review #17).

---

# 20. 구현 시 반드시 처리해야 하는 예외

## 20.1 유효한 RAG 결과가 하나도 없는 경우

\[
\sum_iw_i=0
\]

이면 R 계산식의 분모가 0이 된다.

이 경우 다음처럼 정의한다.

\[
R=0
\]

\[
Q=0
\]

따라서

\[
E=M
\]

이 된다.

---

## 20.2 similarity 범위 확인

현재 공식은 similarity가 기본적으로

\[
0\le s_i\le1
\]

범위라고 가정한다.

사용하는 embedding / vector DB가 cosine similarity 대신 cosine distance 또는 다른 metric을 반환하는 경우 반드시 동일한 척도로 정규화해야 한다.

v1에서는 RAG Retrieval Formula v1 §22.1을 공통 adapter 기준으로 사용한다. 유한한 영벡터가 아닌 벡터를 L2 정규화하여 cosine \(c\in[-1,1]\)을 구한 뒤 \(s=\max(0,c)\)로 전달한다. 반환값이 실제로 \(d=1-c\)인 cosine distance이면 \(c=1-d\)로 변환한다. 그 외 metric은 이 버전에서 오류로 처리한다. 범위를 벗어난 명백한 값은 거부하며 부동소수점의 미세한 반올림 오차만 경계로 보정한다. query별 min-max 정규화와 \((c+1)/2\) 변환은 사용하지 않는다(critical review #14).

---

## 20.3 모델 출력값 normalization

모델이 직접 생성한 자연어 형태의

```text
87% scam
```

같은 값을 그대로 \(p_S\)로 사용하지 않는 것을 권장한다.

v1 scorer의 반환 형식은 고정 순서 `SCAM, NON_SCAM, UNKNOWN`의 세 정규화 점수 \((p_S,p_N,p_U)\)이다(critical review #11, #13).

1. 각 값이 finite이고 \(0\le p_j\le1\)인지 검사한다.
2. 총합 \(t=\sum_jp_j\)가 0이거나 \(|t-1|>10^{-6}\)이면 오류로 처리한다. 허용오차 이내인 경우만 \(p_j\leftarrow p_j/t\)로 보정한다. 잘못된 출력을 균등분포로 대체하지 않는다.
3. 모델이 logits \(z_j\)를 반환하면 adapter에서 다음 안정적 softmax를 적용한 뒤 같은 검증을 수행한다. raw logits나 음수 log-probability를 그대로 p에 대입하지 않는다.

\[
p_j=\frac{\exp(z_j-z_{max})}{\sum_k\exp(z_k-z_{max})},\qquad z_{max}=\max_k z_k
\]

logits도 모두 finite여야 한다. token log-probability 방식은 세 클래스 전체의 비교 가능한 점수가 명시된 adapter가 있는 경우에만 같은 안정적 정규화를 적용할 수 있다. 다중 token 라벨의 첫 token만 비교하거나 누락된 클래스 점수를 임의로 채우는 방식은 허용하지 않는다. 정의가 불명확한 backend 출력은 오류로 처리한다.

자연어로 생성된 숫자는 p로 사용하지 않는다. 정규화 자체는 calibration을 보장하지 않으며 별도 calibration 도입 여부는 향후 실험에서 판단한다.

---

## 20.4 수치와 설정의 정의역

계산 전에 모든 입력 수치와 설정이 finite인지 검사하고 다음 조건을 만족해야 한다(critical review #13).

\[
0\le\tau<1,\quad\gamma>0,\quad\kappa>0,\quad
\alpha>0,\quad\beta\ge0,\quad0\le T_L<T_H\le100
\]

범위 밖 설정과 NaN/Inf는 계산 오류로 처리하며 위험 점수를 생성하지 않는다. RAG 후보 수와 gap 설정은 RAG Retrieval Formula v1의 정의역을 따른다. \(W=0\) 분기는 나눗셈보다 먼저 수행하고, \(W>0\)에서 Quality의 구현은 작은 W의 정밀도를 보존하는 `Q = -expm1(-W / kappa)`를 사용한다. 이는 기존 Q 수식과 수학적으로 동일하다. 부동소수점 포화로 Q가 정확히 1이 되는 것은 허용된다.

---

# 21. 현재 구조의 한계

이 공식은 초기 프로토타입에 적합한 **해석 가능한 heuristic evidence fusion model**이다.

즉 완전히 데이터로부터 추정된 최적 통계모델은 아니다.

현재 단계에서는 데이터가 적기 때문에 오히려 이 특성이 장점이 될 수 있다.

하지만 데이터가 충분히 증가하면 다음 단계로 발전시킬 수 있다.

- Logistic Regression 기반 meta-classifier
- Log-odds evidence fusion
- Bayesian evidence model
- Platt Scaling
- Isotonic Regression
- Temperature Scaling
- Learned stacking model

이 경우 \(\alpha\), \(\beta\), \(\tau\), \(\gamma\), \(\kappa\)를 사람이 직접 지정하는 대신 실제 데이터에서 학습할 수 있다.

---

# 22. 설계 철학 요약

이 판정식의 핵심은 단순히 모델 점수와 RAG 점수를 평균내는 것이 아니다.

구조를 요약하면 다음과 같다.

```text
                +--------------------+
Input --------> |       Model        |
                +--------------------+
                          |
                          v
                   Model Evidence M
                          |
                          |
                          +------------------+
                                             |
                                             v
                                     Evidence Fusion
                                             |
                                             v
Input -> Embedding -> Vector DB -> Top-k -> RAG Evidence R
                              |              |
                              |              |
                              +-> Quality Q -+
                                             |
                                             v
                                  Unified Evidence E
                                             |
                                             v
                                   Risk Score 0~100
```

가장 중요한 개념은 다음 한 문장으로 정리할 수 있다.

> **모델과 RAG를 각각 독립적인 증거원으로 취급하고, RAG 근거의 신뢰도를 별도로 평가한 뒤, 서로 반대되는 강한 증거는 상쇄시키고 약한 증거는 강한 증거를 함부로 뒤집지 못하도록 한다.**

> 해석 주석: 위의 ‘독립적인’은 분리된 모듈을 뜻하며 통계적 독립성이나 정답 신뢰도를 보장하지 않는다. 충돌 상쇄와 UNKNOWN에 대한 정확한 조건은 §10의 주석을 따른다(critical review #6, #10).

---

# 23. 최종 공식 한 줄 버전

모든 정의를 전개하면 초기 프로토타입의 핵심 구조는 다음과 같다.

\[
M=p_S-p_N
\]

\[
w_i=
\left(
\frac{s_i-\tau}{1-\tau}
\right)^\gamma
\]

\[
R=
\frac{\sum_iw_iy_i}{\sum_iw_i}
\]

\[
Q=
1-e^{-\sum_iw_i/\kappa}
\]

\[
E=
\frac{M+QR}{1+Q}
\]

\[
\boxed{
S=50(1+E)
}
\]

이때 최종 \(S\)는 **확률이 아니라 Romance Scam Risk Score**이다.

---

## Version

- Document: Romance Scam Risk Scoring Formula
- Version: v1
- Status: Prototype specification with minimal implementation corrections
- Purpose: Model + RAG evidence fusion for romance scam detection

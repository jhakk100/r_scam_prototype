# Romance Scam RAG Retrieval Formula Specification v0.1

## 0. 목적

이 문서는 로맨스 스캠 판별 시스템에서 **RAG 검색 결과를 수학적으로 정제하고, 최종 판정식에 투입할 수 있는 단일 RAG Evidence 값으로 변환하는 과정**을 정의한다.

핵심 목표는 다음과 같다.

- 고정 Top-k가 아니라 검색 품질에 따라 실제 사용 개수를 조절한다.
- similarity가 낮은 결과의 영향력을 억제한다.
- 검색 결과끼리 충돌하면 RAG의 최종 영향력을 자동으로 낮춘다.
- 유효한 검색 결과가 없으면 자연스럽게 Model-only 판단으로 fallback한다.
- RAG의 출력은 확률이 아니라 **방향성을 가진 증거(evidence)** 로 해석한다.

---

# 1. 전체 RAG 처리 흐름

```text
Input Conversation
    ↓
Embedding
    ↓
Vector DB Search
    ↓
Top-K_retrieve 후보 검색
    ↓
Similarity Threshold Filter
    ↓
Similarity Gap Detection
    ↓
Adaptive Top-k Selection
    ↓
Similarity Weighting
    ↓
Signed RAG Evidence 계산
    ↓
RAG Quality 계산
    ↓
RAG Agreement 계산
    ↓
Effective RAG Reliability 계산
    ↓
최종 Model-RAG Fusion으로 전달
```

초기 권장값:

```text
K_retrieve = 8
K_max = 5
tau = 0.60
delta = 0.10 ~ 0.15
gamma = 1.0
kappa = 1.0
```

이 값들은 초기 프로토타입용 시작점이며, validation 데이터가 충분해지면 조정한다.

---

# 2. 1차 후보 검색

벡터 데이터베이스에서 similarity 기준 상위 후보를 먼저 넓게 가져온다.

\[
K_{\text{retrieve}} = 8
\]

검색 결과는

\[
s_1 \ge s_2 \ge \cdots \ge s_8
\]

순서라고 가정한다.

여기서 \(s_i\)는 i번째 검색 결과의 similarity다.

중요한 점은 **Top-8 전체를 판정에 사용하지 않는다는 것**이다. Top-8은 후보군 확보용이고, 실제 연산에는 이후 필터링을 통과한 일부만 사용한다.

---

# 3. Similarity Threshold Filter

최소 similarity 기준을

\[
\tau = 0.60
\]

으로 둔다.

검색 결과 \(i\)에 대해

\[
s_i < \tau
\]

이면 해당 결과를 제거한다.

즉:

\[
\boxed{
\mathcal{C}
=
\{i \mid s_i \ge \tau\}
}
\]

예:

```text
0.84
0.78
0.72
0.59
0.54
```

이면 threshold 0.60 기준으로 실제 후보는

```text
0.84
0.78
0.72
```

만 남는다.

이 단계는 **검색은 되었지만 실질적으로 유사하지 않은 사례가 판정에 개입하는 것을 막기 위한 것**이다.

---

# 4. Adaptive Top-k

최종 사용 가능한 최대 검색 수는

\[
K_{\max}=5
\]

로 둔다.

하지만 무조건 5개를 사용하는 것이 아니라, similarity 사이에 큰 단절이 있으면 그 지점에서 검색 결과를 자른다.

---

# 5. Similarity Gap

연속된 두 검색 결과의 similarity 차이를 다음과 같이 정의한다.

\[
\boxed{
\Delta_i=s_i-s_{i+1}
}
\]

gap threshold를 \(\delta\)라고 둔다.

초기 권장 범위:

\[
\delta = 0.10 \sim 0.15
\]

만약

\[
\Delta_i > \delta
\]

이면 \(i\)번째 결과와 \(i+1\)번째 결과 사이에 의미 있는 단절이 있다고 본다.

예:

\[
0.93,\ 0.91,\ 0.88,\ 0.70,\ 0.68
\]

여기서

\[
0.88-0.70=0.18
\]

이고

\[
0.18>0.10
\]

이라면 실제 사용 결과는

\[
0.93,\ 0.91,\ 0.88
\]

이며

\[
K_{\text{effective}}=3
\]

이 된다.

---

# 6. Effective Top-k

실제 연산에 사용되는 개수는 개념적으로

\[
\boxed{
K_{\text{effective}}
=
\min
\left(
K_{\text{threshold}},
K_{\text{gap}},
K_{\max}
\right)
}
\]

로 둘 수 있다.

- \(K_{\text{threshold}}\): threshold 통과 결과 수
- \(K_{\text{gap}}\): similarity gap 이전까지의 결과 수
- \(K_{\max}\): 최대 허용 검색 수

초기에는

\[
K_{\max}=5
\]

를 사용한다.

유효 결과가 하나도 없으면

\[
K_{\text{effective}}=0
\]

이다.

---

# 7. Label Encoding

각 검색 결과의 라벨을 다음과 같이 정의한다.

\[
\boxed{
y_i=
\begin{cases}
+1 & \text{SCAM}\\
-1 & \text{NON\_SCAM}
\end{cases}
}
\]

이렇게 하면 RAG의 방향성을 하나의 축에서 표현할 수 있다.

- +1 방향: 로맨스 스캠
- -1 방향: 정상
- 0 근처: 양쪽 증거가 서로 상쇄

---

# 8. Similarity Weight

threshold를 겨우 넘은 결과와 매우 유사한 결과를 동일하게 취급하지 않는다.

각 검색 결과의 weight를

\[
\boxed{
w_i=
\left(
\frac{s_i-\tau}{1-\tau}
\right)^\gamma
}
\qquad s_i\ge\tau
\]

로 정의한다.

그리고

\[
s_i<\tau
\]

이면

\[
\boxed{w_i=0}
\]

으로 처리한다.

여기서

- \(s_i\): similarity
- \(\tau\): minimum similarity threshold
- \(\gamma\): similarity 가중치 곡선 조정값

초기값:

\[
\gamma=1
\]

\(\tau=0.60\)일 때:

| Similarity | Weight |
|---:|---:|
| 0.60 | 0.00 |
| 0.70 | 0.25 |
| 0.80 | 0.50 |
| 0.90 | 0.75 |
| 1.00 | 1.00 |

즉 threshold를 겨우 넘은 결과는 매우 약한 증거로 취급한다.

---

# 9. Gamma의 의미

\(\gamma\) 값으로 높은 similarity 결과를 얼마나 강하게 우대할지 조절한다.

### \(\gamma=1\)

선형 증가. 초기 프로토타입 기본값으로 적합하다.

### \(\gamma>1\)

높은 similarity 결과를 더 강하게 우대한다.

예:

\[
\gamma=2
\]

이면 threshold 부근 결과의 영향력이 더 빠르게 줄어든다.

### \(\gamma<1\)

중간 similarity 결과에도 비교적 높은 weight를 준다.

초기 시스템에서는 우선 권장하지 않는다.

---

# 10. Signed RAG Evidence

최종 RAG 방향성을 다음과 같이 정의한다.

\[
\boxed{
R=
\frac{\sum_i w_i y_i}
{\sum_i w_i}
}
\]

단,

\[
\sum_i w_i>0
\]

인 경우에만 계산한다.

범위:

\[
-1\le R\le1
\]

해석:

- \(R\approx+1\): 강한 SCAM evidence
- \(R\approx-1\): 강한 NON_SCAM evidence
- \(R\approx0\): 검색 결과가 충돌하거나 방향성이 없음

---

# 11. RAG Evidence 예시

예를 들어:

| Similarity | Label |
|---:|---|
| 0.90 | SCAM |
| 0.86 | SCAM |
| 0.82 | NON_SCAM |
| 0.70 | SCAM |

\[
\tau=0.60,\quad \gamma=1
\]

이면 weight는 대략

\[
0.75,\ 0.65,\ 0.55,\ 0.25
\]

이다.

따라서:

\[
R=
\frac{
0.75+0.65-0.55+0.25
}{
0.75+0.65+0.55+0.25
}
\]

\[
R=\frac{1.10}{2.20}
\]

\[
\boxed{R=0.50}
\]

즉 RAG는 SCAM 방향으로 중간 정도의 evidence를 제공한다.

---

# 12. RAG Quality

RAG 결과의 방향성과 별도로, 검색 결과 자체의 질을 평가한다.

\[
\boxed{
Q=
1-
\exp
\left(
-\frac{\sum_iw_i}{\kappa}
\right)
}
\]

여기서

- \(Q\): RAG retrieval quality
- \(\kappa\): quality saturation 조절값

초기값:

\[
\kappa=1
\]

범위:

\[
0\le Q<1
\]

검색 결과가 거의 없거나 weight가 매우 작으면

\[
Q\approx0
\]

이고, 높은 similarity 결과가 충분히 존재하면

\[
Q\rightarrow1
\]

이다.

즉:

> \(R\)은 RAG가 어느 방향을 가리키는지 나타낸다.

> \(Q\)는 그 검색 결과 자체가 얼마나 강한지를 나타낸다.

---

# 13. RAG Agreement

검색 품질이 높아도 검색 결과들이 서로 반대 라벨일 수 있다.

예:

```text
SCAM
SCAM
NON_SCAM
NON_SCAM
```

이 경우 similarity가 높다면 \(Q\)는 높게 나올 수 있지만 방향성은 충돌한다.

이를 따로 표현하기 위해:

\[
\boxed{
A=|R|
}
\]

로 Agreement를 정의한다.

범위:

\[
0\le A\le1
\]

해석:

- \(A=1\): 검색 결과들이 사실상 같은 방향에 동의
- \(A=0\): SCAM / NON_SCAM evidence가 완전히 상쇄

---

# 14. Effective RAG Reliability

보수적인 시스템에서는 Quality와 Agreement를 함께 고려한다.

\[
\boxed{
Q_{\text{eff}}=Q\cdot A
}
\]

즉

\[
\boxed{
Q_{\text{eff}}=Q|R|
}
\]

이다.

이 값은 검색 결과가

1. 충분히 유사하고
2. 서로 같은 방향에 동의할 때

가장 커진다.

---

# 15. 최종 Fusion으로 전달되는 값

RAG 단계에서 최종적으로 다음 값을 전달한다.

```text
R      = RAG directional evidence
Q      = RAG retrieval quality
A      = RAG agreement
Q_eff  = effective RAG reliability
```

보수적 fusion에서는

\[
Q_{\text{eff}}=QA
\]

를 사용한다.

예를 들어 Model Evidence \(M\)과 결합하면:

\[
\boxed{
E=
\frac{
M+Q_{\text{eff}}R
}{
1+Q_{\text{eff}}
}
}
\]

즉:

\[
\boxed{
E=
\frac{
M+QAR
}{
1+QA
}
}
\]

이다.

---

# 16. Model-only Fallback

threshold를 통과하는 RAG 결과가 하나도 없으면

\[
K_{\text{effective}}=0
\]

이다.

이 경우:

\[
R=0,\quad Q=0,\quad A=0,\quad Q_{\text{eff}}=0
\]

으로 처리한다.

그러면:

\[
E=
\frac{M+0}{1+0}
\]

이므로

\[
\boxed{E=M}
\]

이 된다.

즉 RAG 검색 실패 시 자연스럽게 Model-only 판단으로 fallback한다.

---

# 17. Adaptive Top-k 예시

## 예시 A: 강한 5개 결과

\[
0.93,\ 0.91,\ 0.88,\ 0.84,\ 0.82,\ 0.79
\]

threshold 통과, 큰 gap 없음.

\[
K_{\text{effective}}=5
\]

---

## 예시 B: 3번째 이후 급격한 하락

\[
0.93,\ 0.91,\ 0.88,\ 0.70,\ 0.68
\]

\[
0.88-0.70=0.18
\]

\[
0.18>\delta
\]

라면

\[
K_{\text{effective}}=3
\]

---

## 예시 C: threshold에서 잘림

\[
0.76,\ 0.71,\ 0.64,\ 0.58,\ 0.55
\]

\[
\tau=0.60
\]

이므로

\[
K_{\text{effective}}=3
\]

---

## 예시 D: 유효 검색 없음

\[
0.58,\ 0.55,\ 0.52
\]

모든 값이 threshold 미만이므로

\[
K_{\text{effective}}=0
\]

이고

\[
Q=0
\]

이므로 Model-only fallback.

---

# 18. 왜 고정 Top-k보다 Adaptive Top-k가 나은가

고정 Top-k의 문제는 검색 품질과 무관하게 항상 같은 수의 사례를 사용한다는 점이다.

예:

```text
0.96
0.94
0.91
0.65
0.62
```

Top-5 고정이라면 마지막 두 결과까지 강제로 사용한다.

하지만 실제로는 첫 세 결과와 마지막 두 결과 사이에 질적 차이가 크다.

Adaptive Top-k는 이를 제거한다.

즉:

\[
\text{검색 개수}
\]

보다

\[
\text{검색 증거의 질}
\]

을 우선한다.

---

# 19. Bias-Variance 관점

Top-k가 너무 작으면 하나의 검색 오류가 전체 RAG 결과에 큰 영향을 줄 수 있다.

즉:

\[
Variance\uparrow
\]

반대로 Top-k가 너무 크면 관련성이 떨어지는 사례까지 포함된다.

즉:

\[
Bias\uparrow
\]

현재 소규모 RAG 데이터셋에서는

\[
K_{\max}=5
\]

정도가 합리적인 초기값이다.

따라서 초기 권장 구조는:

\[
\boxed{
Top\text{-}8\ Retrieve
\rightarrow
Threshold
\rightarrow
Gap\ Filter
\rightarrow
Adaptive\ Top\text{-}1\sim5
}
\]

이다.

---

# 20. 권장 초기 파라미터

| Parameter | Recommended Initial Value |
|---|---:|
| \(K_{\text{retrieve}}\) | 8 |
| \(K_{\max}\) | 5 |
| \(\tau\) | 0.60 |
| \(\delta\) | 0.10 ~ 0.15 |
| \(\gamma\) | 1.0 |
| \(\kappa\) | 1.0 |

이 값은 고정된 진리값이 아니라 초기 프로토타입용 시작점이다.

향후 validation dataset이 확보되면 조정한다.

---

# 21. 구현용 의사코드

```python
import math

def rag_score(
    results,
    tau=0.60,
    gap_threshold=0.12,
    k_max=5,
    gamma=1.0,
    kappa=1.0
):
    # results example:
    # [
    #   {"similarity": 0.91, "label": "SCAM"},
    #   {"similarity": 0.87, "label": "NON_SCAM"},
    # ]

    # 1. similarity descending
    results = sorted(
        results,
        key=lambda x: x["similarity"],
        reverse=True
    )

    # 2. threshold filter
    candidates = [
        r for r in results
        if r["similarity"] >= tau
    ]

    if len(candidates) == 0:
        return {
            "R": 0.0,
            "Q": 0.0,
            "A": 0.0,
            "Q_eff": 0.0,
            "k_effective": 0
        }

    # 3. adaptive top-k by similarity gap
    selected = []

    for i, r in enumerate(candidates):

        if len(selected) >= k_max:
            break

        selected.append(r)

        if i < len(candidates) - 1:
            gap = (
                candidates[i]["similarity"]
                - candidates[i + 1]["similarity"]
            )

            if gap > gap_threshold:
                break

    # 4. similarity weights
    weighted_sum = 0.0
    total_weight = 0.0

    for r in selected:

        s = r["similarity"]

        w = ((s - tau) / (1 - tau)) ** gamma

        y = +1 if r["label"] == "SCAM" else -1

        weighted_sum += w * y
        total_weight += w

    if total_weight == 0:
        return {
            "R": 0.0,
            "Q": 0.0,
            "A": 0.0,
            "Q_eff": 0.0,
            "k_effective": len(selected)
        }

    # 5. directional evidence
    R = weighted_sum / total_weight

    # 6. retrieval quality
    Q = 1 - math.exp(-total_weight / kappa)

    # 7. agreement
    A = abs(R)

    # 8. effective reliability
    Q_eff = Q * A

    return {
        "R": R,
        "Q": Q,
        "A": A,
        "Q_eff": Q_eff,
        "k_effective": len(selected)
    }
```

---

# 22. 구현 시 주의사항

## 22.1 Similarity metric 확인

사용하는 벡터 DB의 similarity 값이 반드시 0~1 범위라고 가정하면 안 된다.

cosine distance와 cosine similarity는 서로 다르므로, 필요하면 먼저

\[
s_i\in[0,1]
\]

범위로 정규화한 뒤 본 공식을 적용한다.

---

## 22.2 클래스 불균형

RAG DB의 라벨 비율이 심하게 불균형하면 nearest-neighbor 분포 자체가 한쪽으로 치우칠 수 있다.

예:

```text
SCAM 900
NON_SCAM 100
```

이 경우 장기적으로 class-balanced retrieval 또는 prior correction이 필요할 수 있다.

---

## 22.3 중복 사례 제거

동일하거나 거의 동일한 사례가 여러 개 저장되어 있으면 하나의 사건이 여러 표처럼 작동할 수 있다.

예:

```text
Case A
Case A copy
Case A paraphrase
Case A translated
```

따라서 retrieval 단계에서 duplicate 또는 near-duplicate 제거가 필요하다.

---

## 22.4 검색 결과 개수와 독립성

Top-5라고 해서 5개의 독립적인 증거가 있다는 뜻은 아니다.

서로 매우 유사한 데이터가 동일 사건에서 파생된 것이라면 실제 정보량은 하나일 수 있다.

향후에는 source diversity 또는 cluster diversity를 추가하는 것이 좋다.

---

# 23. 향후 확장

데이터가 충분히 증가하면 다음 요소를 고려할 수 있다.

### Learned Threshold

\[
\tau
\]

를 validation 데이터에서 최적화.

### Learned Gap Threshold

\[
\delta
\]

역시 validation 기반으로 추정.

### Class Prior Correction

SCAM / NON_SCAM 데이터 비율 차이를 보정.

### Diversity Penalty

거의 동일한 검색 결과가 반복되면 weight 감소.

### Source Reliability

사례 출처의 신뢰도에 따라 추가 가중치 적용.

### Temporal Decay

오래된 스캠 패턴의 영향력을 감소시키는 시간 가중치 적용.

---

# 24. 최종 요약

## Similarity filter

\[
s_i\ge\tau
\]

## Similarity gap

\[
\Delta_i=s_i-s_{i+1}
\]

\[
\Delta_i>\delta
\]

이면 이후 검색 결과를 버린다.

## Weight

\[
\boxed{
w_i=
\left(
\frac{s_i-\tau}{1-\tau}
\right)^\gamma
}
\]

## RAG Evidence

\[
\boxed{
R=
\frac{\sum_iw_iy_i}
{\sum_iw_i}
}
\]

## RAG Quality

\[
\boxed{
Q=
1-\exp
\left(
-\frac{\sum_iw_i}{\kappa}
\right)
}
\]

## RAG Agreement

\[
\boxed{
A=|R|
}
\]

## Effective Reliability

\[
\boxed{
Q_{\text{eff}}=QA
}
\]

## Model-RAG Fusion

\[
\boxed{
E=
\frac{
M+Q_{\text{eff}}R
}{
1+Q_{\text{eff}}
}
}
\]

---

# 25. 최종 권장 구조

```text
Top-8 Retrieve
      ↓
Similarity >= 0.60
      ↓
Gap threshold 0.10~0.15
      ↓
Adaptive Top-1~5
      ↓
Similarity Weight
      ↓
RAG Evidence R
      ↓
RAG Quality Q
      ↓
RAG Agreement A
      ↓
Q_eff = Q × A
      ↓
Model-RAG Fusion
```

이 구조의 핵심은 **검색 결과 개수보다 검색 증거의 질과 일관성을 우선한다는 것**이다.

"""Numerical checks of the supplied design documents, not application code.

Run: python design_review/review_checks.py
Only Python's standard library is used. No attached document is executed.
"""
import json
import math
from pathlib import Path


def rag(hits, tau=0.6, delta=0.12, gamma=1.0, kappa=1.0, k_max=5):
    """Transcribe the RAG specification, including its unsafe label mapping."""
    candidates = sorted((h for h in hits if h[0] >= tau), key=lambda h: h[0], reverse=True)
    selected = []
    for i, hit in enumerate(candidates):
        if len(selected) >= k_max:
            break
        selected.append(hit)
        if i + 1 < len(candidates) and hit[0] - candidates[i + 1][0] > delta:
            break
    weights = [((s - tau) / (1 - tau)) ** gamma for s, _ in selected]
    W = sum(weights)
    if W == 0:
        return dict(k=len(selected), W=0, R=0, Q=0, A=0, Q_eff=0)
    R = sum(w * (1 if label == "SCAM" else -1)
            for w, (_, label) in zip(weights, selected)) / W
    Q = -math.expm1(-W / kappa)
    return dict(k=len(selected), W=W, R=R, Q=Q, A=abs(R), Q_eff=Q * abs(R))


def scores(M, R, Q):
    eq = (M + Q * R) / (1 + Q)
    qe = Q * abs(R)
    ee = (M + qe * R) / (1 + qe)
    return dict(M=M, E_Q=eq, S_Q=50 * (1 + eq),
                E_Qeff=ee, S_Qeff=50 * (1 + ee))


def candidate_case(M, hits, **kwargs):
    state = rag(hits, **kwargs)
    return dict(hits=hits, **state, **scores(M, state["R"], state["Q"]))


q2 = -math.expm1(-2)
results = {
    "fusion_disagreement": scores(0.35, 0, q2),
    "unknown_is_non_scam_in_pseudocode": candidate_case(0, [(1, "UNKNOWN")]),
    "all_exact_threshold": candidate_case(0.8, [(0.6, "SCAM")]),
    "monotonicity_R_zero": scores(0.8, 0, q2),
    "monotonicity_R_point_one": scores(0.8, 0.1, q2),
    "strong_conflict": candidate_case(0.95, [(0.98, "NON_SCAM"),
        (0.88, "NON_SCAM"), (0.78, "NON_SCAM"), (0.70, "SCAM")]),
    "gap_before": candidate_case(-0.2, [(0.94, "SCAM")] + [(0.8199, "NON_SCAM")] * 4),
    "gap_after": candidate_case(-0.2, [(0.94, "SCAM")] + [(0.8201, "NON_SCAM")] * 4),
    "duplicate_one": candidate_case(-0.3, [(0.9, "SCAM")]),
    "duplicate_five": candidate_case(-0.3, [(0.9, "SCAM")] * 5),
    "one_perfect_neighbor_model_uncertain": candidate_case(0, [(1, "SCAM")]),
    "one_perfect_neighbor_full_conflict": candidate_case(1, [(1, "NON_SCAM")]),
    "unknown_argmax": dict(p_S=0.48, p_N=0.03, p_U=0.49, M=0.45, score=72.5),
    "general_weight_conflict_overshoot": {
        "M": 0.8, "R": -1, "Q": 0.9, "alpha": 1, "beta": 20,
        "E": (0.8 + 20*0.9*(-1))/(1+20*0.9),
        "S": 50*(1+(0.8 + 20*0.9*(-1))/(1+20*0.9)),
    },
    "same_accuracy_different_confidence": {
        "softmax_logits_2_0": 1/(1+math.exp(-2)),
        "softmax_logits_2_0_T10": 1/(1+math.exp(-0.2)),
    },
    "document_weight_example_gap_015": candidate_case(0.54,
        [(0.9, "SCAM"), (0.86, "SCAM"), (0.82, "NON_SCAM"), (0.70, "SCAM")], delta=0.15),
    "document_weight_example_gap_010": candidate_case(0.54,
        [(0.9, "SCAM"), (0.86, "SCAM"), (0.82, "NON_SCAM"), (0.70, "SCAM")], delta=0.10),
    "base_rate_precision": {
        "prevalence_50_percent": 0.9*0.5/(0.9*0.5+0.1*0.5),
        "prevalence_1_percent": 0.9*0.01/(0.9*0.01+0.1*0.99),
    },
    "tiny_weight_quality": {
        "naive": 1-math.exp(-1e-18),
        "expm1": -math.expm1(-1e-18),
    },
}

# Range verification over a finite grid complements the analytic proof.
checked = 0
for M in [-1, -0.8, -0.2, 0, 0.2, 0.8, 1]:
    for R in [-1, -0.9, -0.1, 0, 0.1, 0.9, 1]:
        for W in [0, 1e-12, 0.1, 1, 2, 5]:
            for kappa in [0.1, 1, 10]:
                Q = -math.expm1(-W/kappa)
                state = scores(M, R, Q)
                assert 0 <= Q <= 1  # Floating point may round a theoretical Q<1 to 1.
                assert -1-1e-14 <= state["E_Q"] <= 1+1e-14
                assert -1-1e-14 <= state["E_Qeff"] <= 1+1e-14
                assert 0-1e-12 <= state["S_Q"] <= 100+1e-12
                assert 0-1e-12 <= state["S_Qeff"] <= 100+1e-12
                checked += 1

assert results["unknown_is_non_scam_in_pseudocode"]["S_Qeff"] < 40
assert results["strong_conflict"]["S_Q"] <= 60 < results["strong_conflict"]["S_Qeff"]
assert results["gap_before"]["S_Qeff"] > 60
assert results["gap_after"]["S_Qeff"] < 40
assert results["monotonicity_R_zero"]["S_Qeff"] > results["monotonicity_R_point_one"]["S_Qeff"]
assert results["all_exact_threshold"]["S_Qeff"] == 90
results["range_grid_checks"] = checked

destination = Path(__file__).with_name("numerical_checks.json")
destination.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))

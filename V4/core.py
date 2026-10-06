"""Frozen neighbor voting and reference score arithmetic."""
import math

def rag_evidence(selected, distance_cutoff):
    if not math.isfinite(distance_cutoff) or distance_cutoff <= 0:
        raise ValueError("Distance cutoff must be finite and positive")
    if not selected:
        return {"R": 0.0, "V": 0.0, "distance_value": 0.0, "agreement": 0.0, "selected": []}
    weighted = []
    for hit in selected:
        d = hit["distance"]
        if not math.isfinite(d) or d < 0 or hit["label"] not in ("SCAM", "NON_SCAM"):
            raise ValueError("Invalid neighbor distance or label")
        weighted.append({**hit, "proximity": max(0.0, 1-d/distance_cutoff), "vote_weight": 1.0/(d+1e-6)})
    total = math.fsum(h["proximity"] for h in weighted)
    distance_value = total/len(weighted)
    vote_total = math.fsum(h["vote_weight"] for h in weighted)
    r = math.fsum(h["vote_weight"]*(1 if h["label"] == "SCAM" else -1) for h in weighted)/vote_total
    # Agreement is diagnostic only: the user requested similarity-only value gating.
    agreement = abs(r)
    return {"R": r, "distance_value": distance_value, "agreement": agreement,
            "V": distance_value, "selected": weighted}


def fuse(model_margin, rag_margin, value):
    for name, x, lo, hi in (("M", model_margin, -1, 1), ("R", rag_margin, -1, 1), ("V", value, 0, 1)):
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not lo-1e-12 <= x <= hi+1e-12:
            raise ValueError(f"Invalid {name}")
    m, r, v = float(model_margin), float(rag_margin), min(1.0, max(0.0, float(value)))
    evidence = (1-v)*m+v*r
    risk = min(100.0, max(0.0, 50*(1+evidence)))
    return {"evidence": evidence, "risk_score": risk, "level": classify(risk), "rag_share": v, "model_share": 1-v}


def classify(risk):
    if not math.isfinite(risk) or not 0 <= risk <= 100:
        raise ValueError("Invalid risk score")
    return "LOW" if risk < 40 else "HIGH" if risk > 60 else "UNKNOWN"

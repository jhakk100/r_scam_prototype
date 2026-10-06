"""Exploratory bounded fusion candidates; no candidate is a deployed default."""
import math


def classify(risk):
    if not math.isfinite(risk) or not 0 <= risk <= 100:
        raise ValueError("Invalid risk")
    return "LOW" if risk < 40 else "HIGH" if risk > 60 else "UNKNOWN"


def combine(model_margin, rag_margin, distances, cutoff, policy):
    if not -1 <= model_margin <= 1 or not -1 <= rag_margin <= 1:
        raise ValueError("Invalid margins")
    if cutoff <= 0 or not math.isfinite(cutoff):
        raise ValueError("Invalid distance cutoff")
    if any(d < 0 or not math.isfinite(d) for d in distances):
        raise ValueError("Invalid distances")
    multiplier = policy.get("distance_multiplier", 1.0)
    cap = policy.get("rag_cap", 1.0)
    gamma = policy.get("model_attenuation", 1.0)
    if not multiplier > 0 or not 0 <= cap <= 1 or not 0 <= gamma <= 1:
        raise ValueError("Invalid candidate parameters")
    q = sum(max(0.0, 1.0-d/(cutoff*multiplier)) for d in distances)/len(distances) if distances else 0.0
    if policy["type"] == "distance_gate":
        w = min(cap, q)
    elif policy["type"] == "fixed_weight_benchmark":
        w = cap if distances else 0.0
    else:
        raise ValueError("Unknown candidate")
    # Attenuation fades in with distance quality; at zero quality the model is unchanged.
    effective_margin = model_margin*(1-(1-gamma)*q)
    evidence = (1-w)*effective_margin+w*rag_margin
    risk = min(100.0, max(0.0, 50*(1+evidence)))
    return {"risk_score": risk, "level": classify(risk), "evidence": evidence,
            "rag_share": w, "distance_quality": q, "effective_model_margin": effective_margin}


def candidate_policies():
    policies = [{"id": "v3_reference", "type": "distance_gate", "rag_cap": 1.,
                 "model_attenuation": 1., "distance_multiplier": 1.}]
    for gamma in (1., .7, .5):
        for multiplier in (1., 2., 4., 8.):
            for cap in (.3, .5, .7):
                policies.append({"id": f"g{gamma:g}_c{multiplier:g}_r{cap:g}",
                    "type": "distance_gate", "rag_cap": cap,
                    "model_attenuation": gamma, "distance_multiplier": multiplier})
    # Control arms quantify the user's 70:30 proposal and higher unconditional RAG shares.
    for cap in (.3, .5, .7):
        policies.append({"id": f"fixed_r{cap:g}", "type": "fixed_weight_benchmark",
                         "rag_cap": cap, "model_attenuation": 1., "distance_multiplier": 1.})
    return policies

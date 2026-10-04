"""V1 minimum-schema cleanup preserving labels confirmed by the user.

Human-verification provenance is scoped to the exact original input hash.
Writes separate study inputs and answer records matched by conversation_id.
Never overwrites the archived original or creates train/test splits.
"""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STUDY = ROOT / "study dataset"
ANSWER = ROOT / "answer dataset"
METADATA = ANSWER / "metadata"
OPTIONAL = ("scam_stage", "risk_factors", "evidence", "reason_summary")
FACTORS = set("RAPID_INTIMACY PLATFORM_MIGRATION MONEY_REQUEST INVESTMENT_REQUEST "
              "URGENT_REQUEST IDENTITY_INCONSISTENCY LANGUAGE_INCONSISTENCY "
              "EMOTIONAL_PRESSURE SECRECY_REQUEST REPEATED_PAYMENT FAKE_IDENTITY OTHER".split())
STAGES = set("NONE RAPPORT_BUILDING TRUST_BUILDING PLATFORM_MIGRATION MONEY_REQUEST "
             "REPEATED_PAYMENT INVESTMENT_REQUEST OTHER".split())


def canonical(messages):
    return json.dumps([{ "speaker": m["speaker"], "text": m["text"] }
                       for m in messages], ensure_ascii=False, separators=(",", ":"))


def dump_lines(path, records):
    path.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n"
                            for r in records), encoding="utf-8")


def main():
    source = ANSWER / "archive" / "dataset.original.jsonl"
    before = source.read_bytes()
    source_hash = hashlib.sha256(before).hexdigest()
    verification = json.loads((METADATA / "dataset.verification.json").read_text(encoding="utf-8"))
    if verification.get("input_sha256") != source_hash or verification.get("verified") is not True:
        raise ValueError("Human-verification confirmation does not cover this input; update provenance first")
    rows = []
    for line, text in enumerate(before.decode("utf-8-sig").splitlines(), 1):
        if not text.strip():
            raise ValueError(f"Blank JSONL line: {line}")
        row = json.loads(text)
        for field in ("conversation_id", "case_group_id", "label", "verified", "messages"):
            if field not in row:
                raise ValueError(f"Missing {field} at line {line}")
        if type(row["verified"]) is not bool:
            raise ValueError(f"verified must be a JSON boolean at line {line}")
        if row["label"] not in {"SCAM", "NON_SCAM", "UNKNOWN"}:
            raise ValueError(f"Unsupported label at line {line}")
        if not all(isinstance(row[k], str) and row[k].strip()
                   for k in ("conversation_id", "case_group_id")):
            raise ValueError(f"Invalid identifier at line {line}")
        if not isinstance(row["messages"], list) or not row["messages"]:
            raise ValueError(f"Empty/invalid messages at line {line}")
        for msg in row["messages"]:
            if (msg.get("speaker") not in {"A", "B"}
                    or not isinstance(msg.get("text"), str) or not msg["text"].strip()
                    or "\ufffd" in msg["text"]):
                raise ValueError(f"Invalid speaker/text at line {line}")
        rows.append(row)
    if verification.get("record_count") != len(rows):
        raise ValueError("Human-verification confirmation record count does not match")
    if len({r["conversation_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate conversation IDs need manual resolution")

    cleaned, reviews, issues = [], [], []
    exact = defaultdict(list)
    source_ids = defaultdict(list)
    grams = []
    for line, row in enumerate(rows, 1):
        flags = ["CASE_GROUP_UNCONFIRMED",
                 "OPTIONAL_ANNOTATIONS_PENDING_HUMAN_REVIEW"]
        if row.get("scam_stage") not in STAGES:
            issues.append({"conversation_id": row["conversation_id"], "code": "INVALID_STAGE"})
        for factor in row.get("risk_factors", []):
            if factor not in FACTORS:
                issues.append({"conversation_id": row["conversation_id"], "code": "INVALID_FACTOR"})
        for index, evidence in enumerate(row.get("evidence", [])):
            code = None
            turn = evidence.get("turn")
            if type(turn) is not int or not 1 <= turn <= len(row["messages"]):
                code = "EVIDENCE_TURN_INVALID"
            elif evidence.get("text") != row["messages"][turn - 1]["text"]:
                code = "EVIDENCE_TEXT_MISMATCH"
            elif evidence.get("risk_factor") not in row.get("risk_factors", []):
                code = "EVIDENCE_FACTOR_NOT_IN_RISK_FACTORS"
            if code:
                flags.append(code)
                issues.append({"line": line, "conversation_id": row["conversation_id"],
                               "evidence_index": index, "code": code})
        # Use the guide's minimum schema. Optional annotations remain recoverable
        # in the review file; omission does not assert the absence of risk signals.
        cleaned.append({"conversation_id": row["conversation_id"],
                        "case_group_id": row["case_group_id"],
                        "label": row["label"], "verified": True,
                        "messages": row["messages"]})
        reviews.append({"conversation_id": row["conversation_id"], "source_line": line,
                        "case_group_status": "UNCONFIRMED",
                        "label_verification": {"verified": True,
                                               "provenance_file": "metadata/dataset.verification.json",
                                               "basis": "USER_CONFIRMED_PAPER_CONTRIBUTOR_VERIFICATION"},
                        "source_record_metadata": {k: v for k, v in row.items() if k != "messages"},
                        "review_reasons": list(dict.fromkeys(flags)),
                        "required_review": ["Confirm case/derivative grouping before splitting",
                                            "Review optional annotations against observed messages"],
                        "rag_eligible": row["label"] in {"SCAM", "NON_SCAM"}})
        exact[canonical(row["messages"])].append(row["conversation_id"])
        source_ids[(row.get("source_file"), row.get("source_conversation_id"))].append(row["conversation_id"])
        text = canonical(row["messages"])
        grams.append({text[i:i+3] for i in range(len(text)-2)})

    near = []
    for i, a in enumerate(grams):
        for j in range(i+1, len(grams)):
            b = grams[j]
            if min(len(a), len(b)) / max(len(a), len(b)) < .8:
                continue
            score = len(a & b) / len(a | b)
            if score >= .8:
                near.append({"conversation_ids": [rows[i]["conversation_id"], rows[j]["conversation_id"]],
                             "character_trigram_jaccard": round(score, 6),
                             "action": "REVIEW_ONLY_NO_AUTOMATIC_MERGE"})
    audit = {
        "input_file": source.relative_to(ROOT).as_posix(), "input_sha256": source_hash,
        "study_file": "study dataset/dataset.jsonl",
        "answer_file": "answer dataset/answers.jsonl",
        "join_key": "conversation_id",
        "train_validation_test_split_created": False,
        "document_comparison": "Dataset guide v1 and paper sections 3.2, 3.4, 4.1-4.3 agree",
        "input_count": len(rows), "output_count": len(cleaned), "removed_count": 0,
        "input_labels": dict(Counter(r["label"] for r in rows)),
        "output_labels": dict(Counter(r["label"] for r in cleaned)),
        "verified_true_count": len(cleaned),
        "rag_eligible_count": sum(r["verified"] is True and r["label"] in {"SCAM", "NON_SCAM"} for r in cleaned),
        "verification_provenance": verification,
        "messages_preserved": True, "case_groups_confirmed": False,
        "optional_annotations_omitted": list(OPTIONAL),
        "original_annotation_issues": issues,
        "exact_duplicate_groups": [v for v in exact.values() if len(v) > 1],
        "duplicate_source_keys": [v for v in source_ids.values() if len(v) > 1],
        "similarity_screen": {"metric": "character trigram set Jaccard on messages-json-v1",
                              "threshold": .8, "pairs": near,
                              "limitations": "Lexical screen only; does not rule out semantic duplicates, translations or derivatives"},
        "tokenizer_length_check": "NOT_RUN: model/embedding tokenizers and limits are unspecified",
        "training_readiness": "Original confirmed labels preserved for supervised learning; tokenizer checks and leakage-safe splitting remain training setup tasks",
    }
    study_rows = [{"conversation_id": r["conversation_id"], "messages": r["messages"]} for r in cleaned]
    answer_rows = [{k: r[k] for k in ("conversation_id", "case_group_id", "label", "verified")}
                   for r in cleaned]
    for folder in (STUDY, ANSWER, METADATA):
        folder.mkdir(parents=True, exist_ok=True)
    dump_lines(STUDY / "dataset.jsonl", study_rows)
    dump_lines(ANSWER / "answers.jsonl", answer_rows)
    dump_lines(METADATA / "dataset.review.jsonl", reviews)
    (METADATA / "dataset.audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Verify actual saved output and byte-for-byte preservation of the source.
    saved_study = [json.loads(s) for s in (STUDY / "dataset.jsonl").read_text(encoding="utf-8").splitlines()]
    saved_answers = [json.loads(s) for s in (ANSWER / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(saved_study) == len(saved_answers) == len(rows)
    study_by_id = {r["conversation_id"]: r for r in saved_study}
    answers_by_id = {r["conversation_id"]: r for r in saved_answers}
    assert len(study_by_id) == len(answers_by_id) == len(rows)
    assert study_by_id.keys() == answers_by_id.keys()
    assert all(set(r) == {"conversation_id", "messages"} for r in saved_study)
    assert all(set(r) == {"conversation_id", "case_group_id", "label", "verified"} for r in saved_answers)
    saved = [{**study_by_id[r["conversation_id"]], **answers_by_id[r["conversation_id"]]} for r in rows]
    saved_reviews = [json.loads(s) for s in (METADATA / "dataset.review.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(saved) == len(saved_reviews)
    for old, new, review in zip(rows, saved, saved_reviews):
        assert old["messages"] == new["messages"]
        assert canonical(old["messages"]) == canonical(new["messages"])
        assert old == {**review["source_record_metadata"], "messages": new["messages"]}
        assert new["verified"] is True and new["label"] == old["label"]
        assert old["case_group_id"] == new["case_group_id"]
    assert source.read_bytes() == before
    print(json.dumps({"rows": len(saved), "evidence_issues": len(issues),
                      "near_duplicate_candidates": len(near), "source_sha256": source_hash,
                      "verification": "PASSED"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

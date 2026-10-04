import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .errors import DataError, LeakageError
from .input import prepare_input
from .validation import identifier


@dataclass(frozen=True)
class CorpusCase:
    conversation_id: str
    case_group_id: str
    label: str
    verified: bool
    messages: list

    def __post_init__(self):
        identifier(self.conversation_id, "conversation_id", DataError)
        identifier(self.case_group_id, "case_group_id", DataError)
        if self.label not in ("SCAM", "NON_SCAM", "UNKNOWN"):
            raise DataError("CorpusCase의 미지원 label입니다.")
        if type(self.verified) is not bool:
            raise DataError("CorpusCase의 verified는 boolean이어야 합니다.")

    @property
    def eligible(self):
        return self.verified and self.label in ("SCAM", "NON_SCAM")


def read_jsonl(path):
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    raise DataError(f"{path}:{line_no}: 빈 JSONL 행입니다.")
                try:
                    record = json.loads(line)
                except ValueError as exc:
                    raise DataError(f"{path}:{line_no}: 잘못된 JSON입니다.") from exc
                if not isinstance(record, dict):
                    raise DataError(f"{path}:{line_no}: 객체가 필요합니다.")
                yield record
    except OSError as exc:
        raise DataError(f"데이터 파일을 읽을 수 없습니다: {path}: {exc}") from exc


def _by_id(records, name):
    output = {}
    for row in records:
        key = identifier(row.get("conversation_id"), "conversation_id", DataError)
        if key in output:
            raise DataError(f"{name}: 중복 conversation_id: {key}")
        output[key] = row
    return output


def load_dataset(inputs_path, answers_path):
    inputs = _by_id(read_jsonl(inputs_path), "입력")
    answers = _by_id(read_jsonl(answers_path), "정답")
    if inputs.keys() != answers.keys():
        raise DataError("대화 입력과 정답의 conversation_id 집합이 다릅니다.")
    if not inputs:
        raise DataError("데이터셋이 비어 있습니다.")
    cases = []
    for key, row in inputs.items():
        answer = answers[key]
        group = identifier(answer.get("case_group_id"), "case_group_id", DataError)
        label = answer.get("label")
        if label not in ("SCAM", "NON_SCAM", "UNKNOWN"):
            raise DataError(f"{key}: 미지원 label입니다.")
        if type(answer.get("verified")) is not bool:
            raise DataError(f"{key}: verified는 boolean이어야 합니다.")
        prepare_input(row)  # 검증만 수행하고 원문을 변경하지 않는다.
        cases.append(CorpusCase(key, group, label, answer["verified"], row["messages"]))
    return cases


def dataset_fingerprint(cases):
    """정답·그룹·검증 상태와 입력이 바뀌면 기존 분할을 재검토하게 한다."""
    rows = [{"conversation_id": c.conversation_id, "case_group_id": c.case_group_id,
             "label": c.label, "verified": c.verified,
             "input_sha256": prepare_input(c.messages).sha256}
            for c in sorted(cases, key=lambda c: c.conversation_id)]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_split(cases, plan):
    """실제 분할은 연구자가 지정한다. 자동 분할/독립 사건 추정은 하지 않는다."""
    if not isinstance(plan, dict) or set(plan) != {"train", "validation", "test"}:
        raise DataError("분할 파일은 train/validation/test ID 배열을 가져야 합니다.")
    by_id = {c.conversation_id: c for c in cases}
    assigned, groups, texts = {}, {}, {}
    for name, ids in plan.items():
        if not isinstance(ids, list):
            raise DataError(f"{name}: ID 배열이 필요합니다.")
        for key in ids:
            identifier(key, "split conversation_id", DataError)
            if key not in by_id:
                raise DataError(f"분할에 미등록 ID가 있습니다: {key}")
            if key in assigned:
                raise LeakageError(f"여러 번 배정된 ID: {key}")
            case = by_id[key]
            text_hash = prepare_input(case.messages).sha256
            for values, identity in ((groups, case.case_group_id), (texts, text_hash)):
                if identity in values and values[identity] != name:
                    raise LeakageError(f"동일 사건 또는 동일 대화가 분할을 넘습니다: {key}")
                values[identity] = name
            assigned[key] = name
    if assigned.keys() != by_id.keys():
        raise DataError("모든 대화를 정확히 한 분할에 배정해야 합니다.")
    if not plan["train"]:
        raise DataError("RAG corpus에 사용할 train 분할이 비어 있습니다.")
    return [by_id[key] for key in plan["train"]]


def audit_dataset(cases):
    counts = {label: sum(c.label == label for c in cases)
              for label in ("SCAM", "NON_SCAM", "UNKNOWN")}
    return {"count": len(cases), "labels": counts,
            "verified_count": sum(c.verified for c in cases),
            "rag_eligible_count": sum(c.eligible for c in cases),
            "case_group_count": len({c.case_group_id for c in cases}),
            "dataset_sha256": dataset_fingerprint(cases),
            "split_created": False}

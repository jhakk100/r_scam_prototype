"""자동 절단 없이 전 데이터 입력 한도를 검사하고 assistant 라벨만 감독한다."""

import hashlib
import json

from architecture.pipeline.backends import _source_settings, _token_limit
from architecture.pipeline.data import audit_dataset, dataset_fingerprint, load_dataset
from architecture.pipeline.config import read_json
from architecture.pipeline.errors import ConfigurationError, DataError, ModelError
from architecture.pipeline.input import INPUT_CONTRACT, check_input_budget, prepare_input
from architecture.pipeline.model.model_scorer import CLASS_ORDER
from architecture.pipeline.model.tokenization import LabelTokenContract
from .split import PARTITIONS, partitions


def sha256_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def load_partitions(settings):
    data = settings["data"]
    cases = load_dataset(data["inputs"], data["answers"])
    fingerprint = dataset_fingerprint(cases)
    if data.get("expected_sha256") and data["expected_sha256"] != fingerprint:
        raise DataError("데이터 fingerprint가 설정과 다릅니다. 정답·사건 그룹·분할을 재검토하십시오.")
    plan = read_json(data["split"])
    return cases, plan, partitions(cases, plan)


class TokenizerBudget:
    reserved_tokens = 0

    def __init__(self, tokenizer, settings, model_config):
        self.tokenizer = tokenizer
        self.max_input_tokens = _token_limit(tokenizer, model_config, settings["max_input_tokens"])
        self.tokenizer_identity = f"{settings.get('tokenizer_path', settings['path'])}@{settings['revision']}"

    def count_tokens(self, conversation):
        return len(self.tokenizer(conversation, truncation=False)["input_ids"])


def load_tokenizers(settings):
    try:
        from transformers import AutoConfig, AutoTokenizer
    except ImportError as exc:
        raise ConfigurationError("tokenizer 검사에는 transformers가 필요합니다. 학습 실행 컴퓨터에서 설치하십시오.") from exc
    result = {}
    try:
        for name in ("model", "embedding"):
            values = settings[name]
            path, _, source = _source_settings(values)
            tokenizer = AutoTokenizer.from_pretrained(values.get("tokenizer_path", path), **source)
            model_config = AutoConfig.from_pretrained(path, **source)
            result[name] = (tokenizer, model_config)
    except (ConfigurationError, ModelError):
        raise
    except Exception as exc:
        raise ModelError(f"tokenizer/config 로드 실패: {exc}") from exc
    return result


def encode_target(candidates, label):
    if label not in CLASS_ORDER:
        raise DataError("학습 target은 SCAM/NON_SCAM/UNKNOWN이어야 합니다.")
    ids, tail = candidates[CLASS_ORDER.index(label)]
    return {"input_ids": list(ids), "attention_mask": [1] * len(ids),
            "labels": [-100] * (len(ids) - tail) + list(ids[-tail:])}


def pad_features(features, pad_token_id):
    """오른쪽 padding. 패딩·프롬프트는 loss에서 제외한다. ML 없는 테스트에도 사용."""
    if not features or type(pad_token_id) is not int or pad_token_id < 0:
        raise DataError("비어 있지 않은 batch와 pad_token_id가 필요합니다.")
    if any(set(row) != {"input_ids", "attention_mask", "labels"} for row in features):
        raise DataError("batch에 ID/정답 metadata를 포함할 수 없습니다.")
    for row in features:
        if not row["input_ids"] or len(row["input_ids"]) != len(row["labels"]) or len(row["input_ids"]) != len(row["attention_mask"]):
            raise DataError("batch의 token/label/mask 길이가 다릅니다.")
    maximum = max(len(row["input_ids"]) for row in features)
    return {key: [row[key] + [padding] * (maximum - len(row[key])) for row in features]
            for key, padding in (("input_ids", pad_token_id), ("attention_mask", 0), ("labels", -100))}


def supervised_positions(labels):
    """출력 위치 i는 labels[i+1]을 예측한다. 전체 라벨 토큰의 위치 합집합."""
    if not labels or not labels[0] or any(len(row) != len(labels[0]) for row in labels):
        raise DataError("padding된 labels batch가 필요합니다.")
    positions = [i for i in range(len(labels[0]) - 1) if any(row[i + 1] != -100 for row in labels)]
    if not positions:
        raise DataError("감독할 assistant 라벨 토큰이 없습니다.")
    return positions


def prepare_datasets(settings, tokenizers=None):
    cases, plan, divided = load_partitions(settings)
    tokenizers = tokenizers or load_tokenizers(settings)
    tokenizer, model_config = tokenizers["model"]
    model = settings["model"]
    contract = LabelTokenContract(tokenizer, model["instruction"],
                                 _token_limit(tokenizer, model_config, model["max_input_tokens"]),
                                 model["reserved_tokens"])
    embedding_tokenizer, embedding_config = tokenizers["embedding"]
    embedding = TokenizerBudget(embedding_tokenizer, settings["embedding"], embedding_config)
    encoded = {name: [] for name in ("train", "validation")}
    report = {"dataset": audit_dataset(cases), "split_sha256": sha256_json(plan),
              "input_contract": INPUT_CONTRACT, "class_order": list(CLASS_ORDER),
              "instruction_sha256": hashlib.sha256(model["instruction"].encode("utf-8")).hexdigest(),
              "chat_template_sha256": sha256_json(tokenizer.chat_template),
              "verified_only": settings["data"]["verified_only"], "partitions": {},
              "test_used_for_training_or_selection": False,
              "notes": ["같은 case_group_id/완전 동일 대화의 교차 분할을 검사함. 번역·의역·부분 대화의 사건 그룹은 연구자가 확인해야 함.",
                        "입력 길이는 test에도 검사하지만 test target을 학습/검증 dataset에 넣지 않음."]}
    for name in PARTITIONS:
        rows = divided[name]
        selected = [case for case in rows if case.verified or not settings["data"]["verified_only"]]
        counts = {label: sum(case.label == label for case in selected) for label in CLASS_ORDER}
        lengths, embedding_lengths, targets = [], [], []
        for case in rows:
            prepared = prepare_input(case.messages)
            try:
                candidates = contract.candidates(prepared.text)
                budget = check_input_budget(prepared, embedding, "embedding")
            except Exception as exc:
                if isinstance(exc, (ConfigurationError, DataError)):
                    raise
                from architecture.pipeline.errors import PipelineError
                if isinstance(exc, PipelineError):
                    raise type(exc)(f"{name}/{case.conversation_id}: {exc}") from exc
                raise
            lengths.append(len(candidates[0][0]) - candidates[0][1])
            embedding_lengths.append(budget["input_tokens"])
            targets.extend(tail for _, tail in candidates)
            if name != "test" and (case.verified or not settings["data"]["verified_only"]):
                encoded[name].append(encode_target(candidates, case.label))
        report["partitions"][name] = {"count": len(rows), "selected_count": len(selected), "selected_labels": counts,
             "case_group_count": len({case.case_group_id for case in rows}),
             "unverified_count": sum(not case.verified for case in rows),
             "missing_supervised_classes": [label for label in CLASS_ORDER if not counts[label]],
             "max_prompt_tokens": max(lengths), "max_label_response_tokens": max(targets),
             "max_embedding_tokens": max(embedding_lengths)}
    if not encoded["train"] or not encoded["validation"]:
        raise DataError("verified 필터 후 train/validation 학습 대화가 비어 있습니다.")
    if "UNKNOWN" in report["partitions"]["train"]["missing_supervised_classes"]:
        report["notes"].append("train에 UNKNOWN 정답이 없어 UNKNOWN의 직접 감독 학습은 수행되지 않음. 정답 생성/재라벨링 없음.")
    report["model_token_limit"] = contract.max_input_tokens
    report["embedding_token_limit"] = embedding.max_input_tokens
    return encoded, report, plan, tokenizer

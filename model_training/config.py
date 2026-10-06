"""학습 설정 검증 및 설정 파일 기준 경로 해석."""

import copy
from pathlib import Path

from architecture.pipeline.backends import DEFAULT_INSTRUCTION
from architecture.pipeline.config import PipelineConfig, read_json
from architecture.pipeline.errors import ConfigurationError
from architecture.pipeline.validation import identifier, number, positive_integer


def _path(value, root, name):
    value = identifier(value, name, ConfigurationError)
    return str((root / value).resolve()) if not Path(value).is_absolute() else str(Path(value).resolve())


def validate_config(raw, root):
    settings = copy.deepcopy(raw)
    if not isinstance(settings, dict) or set(settings) != {"data", "model", "embedding", "lora", "training", "pipeline"}:
        raise ConfigurationError("data/model/embedding/lora/training/pipeline 설정이 필요합니다.")
    if any(not isinstance(value, dict) for value in settings.values()):
        raise ConfigurationError("설정 항목은 각각 객체여야 합니다.")
    root = Path(root).resolve()
    data = settings["data"]
    if set(data) - {"inputs", "answers", "split", "expected_sha256", "verified_only"}:
        raise ConfigurationError("알 수 없는 data 설정입니다.")
    for key in ("inputs", "answers", "split"):
        data[key] = _path(data.get(key), root, f"data.{key}")
    data.setdefault("verified_only", True)
    if type(data["verified_only"]) is not bool:
        raise ConfigurationError("data.verified_only는 boolean이어야 합니다.")
    expected = data.get("expected_sha256")
    if expected is not None and (not isinstance(expected, str) or len(expected) != 64
                                 or any(c not in "0123456789abcdef" for c in expected)):
        raise ConfigurationError("expected_sha256은 null 또는 SHA256 소문자 hex여야 합니다.")
    for name in ("model", "embedding"):
        values = settings[name]
        allowed = {"path", "revision", "local_files_only", "tokenizer_path", "max_input_tokens",
                   "dtype", "quantization", "device_map"}
        allowed |= {"backend", "family", "instruction", "reserved_tokens"} if name == "model" else {"dimension", "pooling", "text_prefix"}
        if set(values) - allowed:
            raise ConfigurationError(f"알 수 없는 {name} 설정입니다.")
        values.setdefault("local_files_only", True)
        if type(values["local_files_only"]) is not bool:
            raise ConfigurationError("local_files_only는 boolean이어야 합니다.")
        identifier(values.get("path"), f"{name}.path", ConfigurationError)
        revision = identifier(values.get("revision"), f"{name}.revision", ConfigurationError)
        if not values["local_files_only"] and revision.lower() in ("main", "master", "latest"):
            raise ConfigurationError("원격 모델은 이동하는 branch 대신 고정 commit revision을 지정하십시오.")
        if values["local_files_only"]:
            for key in ("path", "tokenizer_path"):
                if values.get(key):
                    values[key] = _path(values[key], root, f"{name}.{key}")
        values["max_input_tokens"] = positive_integer(values.get("max_input_tokens"),
                                                       f"{name}.max_input_tokens", ConfigurationError)
        if values.get("dtype", "float32") not in ("float32", "float16", "bfloat16"):
            raise ConfigurationError("dtype는 float32/float16/bfloat16이어야 합니다.")
        if values.get("quantization", "none") not in ("nf4", "none"):
            raise ConfigurationError("quantization은 nf4/none이어야 합니다.")
    model = settings["model"]
    if model.get("backend") != "label_likelihood" or model.get("family") not in ("gemma4", "causal_lm"):
        raise ConfigurationError("학습은 gemma4/causal_lm의 label_likelihood 계약을 지원합니다.")
    model["instruction"] = identifier(model.get("instruction", DEFAULT_INSTRUCTION),
                                       "model.instruction", ConfigurationError)
    model["reserved_tokens"] = positive_integer(model.get("reserved_tokens", 32),
                                                "model.reserved_tokens", ConfigurationError)
    if model["reserved_tokens"] >= model["max_input_tokens"]:
        raise ConfigurationError("라벨 예약 토큰은 모델 전체 한도보다 작아야 합니다.")
    embedding = settings["embedding"]
    if embedding.get("pooling") != "mean":
        raise ConfigurationError("기존 embedding 계약의 mean pooling을 사용하십시오.")
    if not isinstance(embedding.get("text_prefix", ""), str):
        raise ConfigurationError("embedding.text_prefix는 문자열이어야 합니다.")
    positive_integer(embedding.get("dimension"), "embedding.dimension", ConfigurationError)
    lora = settings["lora"]
    if set(lora) != {"r", "alpha", "dropout", "target_modules"} or lora["target_modules"] != "all-linear":
        raise ConfigurationError("lora에는 r/alpha/dropout/target_modules=all-linear가 필요합니다.")
    positive_integer(lora["r"], "lora.r", ConfigurationError)
    positive_integer(lora["alpha"], "lora.alpha", ConfigurationError)
    number(lora["dropout"], "lora.dropout", ConfigurationError, minimum=0, maximum=1)
    train = settings["training"]
    defaults = {"epochs": 3.0, "learning_rate": 0.0002, "batch_size": 1,
                "gradient_accumulation_steps": 16, "gradient_checkpointing": True,
                "warmup_ratio": 0.03, "weight_decay": 0.0, "max_grad_norm": 1.0,
                "seed": 42, "logging_steps": 10, "save_total_limit": 2,
                "optim": "paged_adamw_8bit", "device": "cuda:0"}
    if set(train) - (set(defaults) | {"output_dir"}):
        raise ConfigurationError("알 수 없는 training 설정입니다.")
    for key, value in defaults.items():
        train.setdefault(key, value)
    train["output_dir"] = _path(train.get("output_dir"), root, "training.output_dir")
    for key in ("batch_size", "gradient_accumulation_steps", "logging_steps", "save_total_limit"):
        positive_integer(train[key], f"training.{key}", ConfigurationError)
    positive_integer(train["seed"], "training.seed", ConfigurationError, True)
    for key in ("epochs", "learning_rate", "max_grad_norm"):
        if number(train[key], f"training.{key}", ConfigurationError, minimum=0) <= 0:
            raise ConfigurationError(f"training.{key}는 양수여야 합니다.")
    number(train["warmup_ratio"], "training.warmup_ratio", ConfigurationError, minimum=0, maximum=1)
    number(train["weight_decay"], "training.weight_decay", ConfigurationError, minimum=0)
    if type(train["gradient_checkpointing"]) is not bool:
        raise ConfigurationError("gradient_checkpointing은 boolean이어야 합니다.")
    if train["device"] not in ("cuda:0", "cpu"):
        raise ConfigurationError("단일 프로세스 cuda:0 또는 cpu 학습만 지원합니다.")
    if train["optim"] not in ("paged_adamw_8bit", "adamw_torch"):
        raise ConfigurationError("optim은 paged_adamw_8bit/adamw_torch여야 합니다.")
    if train["device"] == "cpu" and (model.get("quantization", "none") != "none"
            or model.get("dtype", "float32") != "float32" or train["optim"] != "adamw_torch"):
        raise ConfigurationError("CPU 확인은 quantization=none/dtype=float32/optim=adamw_torch를 사용하십시오.")
    PipelineConfig.from_dict(settings["pipeline"])
    return settings


def load_config(path):
    return validate_config(read_json(path), Path(path).resolve().parent)

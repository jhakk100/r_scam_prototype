"""단일 장치 PEFT (Q)LoRA supervised 학습. 모델 다운로드/학습은 train 호출 때만 수행."""

import inspect
import os
import platform
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from architecture.pipeline.backends import _check_loaded_weights, _model_kwargs, _source_settings
from architecture.pipeline.errors import ConfigurationError, ModelError
from .artifacts import adapter_fingerprint, export_inference_config, write_json
from .preparation import pad_features, prepare_datasets, sha256_json


def select_lora_targets(model, family, linear_types):
    """Gemma4의 vision/audio tower는 제외하고 언어 모델의 linear 층만 선택한다."""
    names = []
    for name, module in model.named_modules():
        if not name or not isinstance(module, linear_types):
            continue
        parts = name.split(".")
        if "lm_head" in parts or "output_layer" in parts:
            continue
        if family == "gemma4" and "language_model" not in parts:
            continue
        names.append(name)
    if not names:
        raise ModelError("지원하는 언어 모델 linear 층을 찾지 못했습니다. 모델 구조를 확인하십시오.")
    return sorted(names)


def _versions():
    result = {"python": platform.python_version()}
    for name in ("torch", "transformers", "accelerate", "peft", "bitsandbytes", "safetensors"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    return result


def _libraries():
    try:
        import torch
        import transformers
        import peft
        return torch, transformers, peft
    except ImportError as exc:
        raise ConfigurationError("실제 학습에는 torch/transformers/peft가 필요합니다. model_training/README.md를 확인하십시오.") from exc


def make_trainer_class(torch, base_class):
    class LabelTrainer(base_class):
        """전체 assistant 토큰의 causal CE; 선택한 출력 위치만 반환해 메모리를 절약한다."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Trainer가 gradient accumulation 전체의 감독 토큰 수를 전달하게 한다.
            self.model_accepts_loss_kwargs = True
            self._loss_shifts_labels = True

        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            labels = inputs["labels"]
            positions = (labels[:, 1:] != -100).any(dim=0).nonzero(as_tuple=False).flatten()
            if positions.numel() == 0:
                raise ModelError("감독할 assistant 라벨 토큰이 없습니다.")
            outputs = model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"],
                            use_cache=False, logits_to_keep=positions)
            targets = labels.index_select(1, positions + 1)
            logits = outputs.logits.float()
            if tuple(logits.shape[:2]) != tuple(targets.shape):
                raise ModelError("모델이 선택한 causal token 위치의 logits를 반환하지 않았습니다.")
            loss = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.shape[-1]),
                    targets.reshape(-1), ignore_index=-100, reduction="sum")
            denominator = num_items_in_batch if num_items_in_batch is not None else (targets != -100).sum()
            if torch.is_tensor(denominator):
                denominator = denominator.to(loss.device)
            if float(denominator) <= 0:
                raise ModelError("loss 분모의 감독 토큰 수는 양수여야 합니다.")
            loss = loss / denominator
            if not bool(torch.isfinite(loss)):
                raise ModelError("학습 loss가 NaN/Inf입니다.")
            return (loss, outputs) if return_outputs else loss

    return LabelTrainer


def train(settings):
    try:
        world_size = int(os.environ.get("WORLD_SIZE", "1"))
    except ValueError as exc:
        raise ConfigurationError("WORLD_SIZE 환경 변수는 정수여야 합니다.") from exc
    if world_size != 1:
        raise ConfigurationError("이 프로토타입 학습 구현은 단일 프로세스/단일 장치를 지원합니다.")
    output = Path(settings["training"]["output_dir"])
    if output.exists() and any(output.iterdir()):
        raise ConfigurationError("output_dir가 비어 있지 않습니다. 기존 결과를 보존하고 새 실행 경로를 사용하십시오.")
    encoded, report, plan, tokenizer = prepare_datasets(settings)
    torch, transformers, peft = _libraries()
    options = settings["training"]
    use_cuda = options["device"] == "cuda:0"
    if use_cuda and not torch.cuda.is_available():
        raise ConfigurationError("cuda:0 학습 설정이지만 CUDA를 사용할 수 없습니다.")
    if use_cuda and torch.cuda.device_count() != 1:
        raise ConfigurationError("CUDA_VISIBLE_DEVICES로 사용할 GPU 한 개만 노출하십시오.")
    dtype = settings["model"].get("dtype", "float32")
    if use_cuda and dtype == "bfloat16" and not torch.cuda.is_bf16_supported():
        raise ConfigurationError("GPU가 bfloat16을 지원하지 않습니다. dtype=float16으로 설정하십시오.")
    if tokenizer.pad_token_id is None:
        if tokenizer.eos_token_id is None:
            raise ModelError("padding에 사용할 기존 pad/eos token이 없습니다. vocabulary를 임의 확장하지 않습니다.")
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"status": "STARTED", "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "versions": _versions(), "config_sha256": sha256_json(settings),
                "dataset_sha256": report["dataset"]["dataset_sha256"],
                "split_sha256": report["split_sha256"], "test_evaluated": False}
    write_json(output / "run_manifest.json", manifest)
    write_json(output / "resolved_config.json", settings)
    write_json(output / "preflight_report.json", report)
    write_json(output / "split.json", plan)
    try:
        transformers.set_seed(options["seed"])
        values = settings["model"]
        path, _, source = _source_settings(values)
        loader = (transformers.AutoModelForImageTextToText if values["family"] == "gemma4"
                  else transformers.AutoModelForCausalLM)
        loading = dict(values, device_map={"": 0 if use_cuda else "cpu"})
        model, info = loader.from_pretrained(path, output_loading_info=True,
                                             **source, **_model_kwargs(loading, torch, transformers))
        _check_loaded_weights(info)
        if "logits_to_keep" not in inspect.signature(model.forward).parameters:
            raise ModelError("선택한 모델은 logits_to_keep를 지원하지 않습니다. 지원 모델을 지정하십시오.")
        model.config.use_cache = False
        linear_types = (torch.nn.Linear,)
        if values.get("quantization", "none") == "nf4":
            import bitsandbytes as bnb
            linear_types += (bnb.nn.Linear4bit,)
            model = peft.prepare_model_for_kbit_training(model,
                        use_gradient_checkpointing=options["gradient_checkpointing"],
                        gradient_checkpointing_kwargs={"use_reentrant": False})
        else:
            for parameter in model.parameters():
                parameter.requires_grad = False
        targets = select_lora_targets(model, values["family"], linear_types)
        lora = settings["lora"]
        model = peft.get_peft_model(model, peft.LoraConfig(r=lora["r"], lora_alpha=lora["alpha"],
                    lora_dropout=lora["dropout"], target_modules=targets, bias="none",
                    task_type=peft.TaskType.CAUSAL_LM))
        parameters = [(name, parameter) for name, parameter in model.named_parameters() if parameter.requires_grad]
        if not parameters or any("lora_" not in name for name, _ in parameters):
            raise ModelError("LoRA 이외의 학습 가중치가 발견되었거나 학습할 어댑터가 없습니다.")
        if values["family"] == "gemma4" and any("language_model" not in name.split(".") for name, _ in parameters):
            raise ModelError("Gemma4 언어 모델 이외의 tower는 학습하지 않습니다.")
        write_json(output / "lora_targets.json", {"modules": targets,
                   "trainable_parameters": sum(parameter.numel() for _, parameter in parameters)})

        class Collator:
            def __call__(self, features):
                padded = pad_features(features, tokenizer.pad_token_id)
                return {key: torch.tensor(value, dtype=torch.long) for key, value in padded.items()}

        arguments = transformers.TrainingArguments(output_dir=str(output / "checkpoints"),
            num_train_epochs=options["epochs"], learning_rate=options["learning_rate"],
            per_device_train_batch_size=options["batch_size"], per_device_eval_batch_size=options["batch_size"],
            gradient_accumulation_steps=options["gradient_accumulation_steps"],
            gradient_checkpointing=options["gradient_checkpointing"],
            gradient_checkpointing_kwargs={"use_reentrant": False}, optim=options["optim"],
            warmup_ratio=options["warmup_ratio"], weight_decay=options["weight_decay"],
            max_grad_norm=options["max_grad_norm"], bf16=use_cuda and dtype == "bfloat16",
            fp16=use_cuda and dtype == "float16", use_cpu=not use_cuda,
            eval_strategy="epoch", save_strategy="epoch", load_best_model_at_end=True,
            metric_for_best_model="eval_loss", greater_is_better=False,
            prediction_loss_only=True, remove_unused_columns=False, label_names=["labels"],
            logging_steps=options["logging_steps"], save_total_limit=options["save_total_limit"],
            dataloader_num_workers=0, report_to="none", push_to_hub=False,
            seed=options["seed"], data_seed=options["seed"])
        trainer = make_trainer_class(torch, transformers.Trainer)(model=model, args=arguments,
            train_dataset=encoded["train"], eval_dataset=encoded["validation"],
            processing_class=tokenizer, data_collator=Collator())
        result = trainer.train()
        validation_metrics = trainer.evaluate()
        final = output / "final_adapter"
        trainer.model.save_pretrained(final, safe_serialization=True)
        tokenizer.save_pretrained(final)
        adapter_sha = adapter_fingerprint(final)
        write_json(output / "training_metrics.json", {"train": result.metrics, "validation": validation_metrics,
                                                      "test": "[실험 후 작성]"})
        write_json(output / "training_log.json", trainer.state.log_history)
        write_json(output / "inference_config.json", export_inference_config(settings, output, adapter_sha))
        manifest.update({"status": "COMPLETED", "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                         "adapter_sha256": adapter_sha, "best_checkpoint": trainer.state.best_model_checkpoint,
                         "best_validation_loss": trainer.state.best_metric,
                         "inference_config": "inference_config.json"})
        write_json(output / "run_manifest.json", manifest)
        return manifest
    except Exception as exc:
        manifest.update({"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        write_json(output / "run_manifest.json", manifest)
        if isinstance(exc, (ConfigurationError, ModelError)):
            raise
        raise ModelError(f"학습 실패 (기록: {output / 'run_manifest.json'}): {exc}") from exc

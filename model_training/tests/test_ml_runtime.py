"""실행 컴퓨터용 ML 검증. 다운로드 없이 작은 합성 모델만 사용한다.

torch가 있으면 loss 검증을 실행한다. 전체 toy 학습/저장/추론 검증은
R_SCAM_RUN_ML_TESTS=1을 명시한 경우에만 실행한다. 실제 연구 성능 실험이 아니다.
"""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from architecture.pipeline.errors import ModelError
from model_training.artifacts import write_json
from model_training.config import validate_config
from model_training.trainer import make_trainer_class, train

HAS_TORCH = importlib.util.find_spec("torch") is not None
RUN_INTEGRATION = (os.environ.get("R_SCAM_RUN_ML_TESTS") == "1" and HAS_TORCH
                   and all(importlib.util.find_spec(name) is not None for name in ("transformers", "peft", "accelerate")))


@unittest.skipUnless(HAS_TORCH, "torch 없음: 실행 컴퓨터에서 loss tensor/gradient 검증")
class TensorLossTests(unittest.TestCase):
    def setUp(self):
        import torch
        self.torch = torch

        class BaseTrainer:
            def __init__(self):
                pass

        self.trainer = make_trainer_class(torch, BaseTrainer)()

    def test_selected_logits_same_loss_and_gradient_as_full_causal_ce(self):
        torch = self.torch
        logits = torch.randn(2, 5, 7, requires_grad=True)
        labels = torch.tensor([[-100, -100, 2, 3, 4], [-100, 1, 2, -100, -100]])
        inputs = {"input_ids": torch.ones_like(labels), "attention_mask": torch.ones_like(labels), "labels": labels}

        def model(**kwargs):
            return SimpleNamespace(logits=logits.index_select(1, kwargs["logits_to_keep"]))

        actual = self.trainer.compute_loss(model, inputs)
        expected = torch.nn.functional.cross_entropy(logits[:, :-1, :].reshape(-1, 7), labels[:, 1:].reshape(-1), ignore_index=-100)
        torch.testing.assert_close(actual, expected)
        actual_gradient = torch.autograd.grad(actual, logits, retain_graph=True)[0]
        expected_gradient = torch.autograd.grad(expected, logits)[0]
        torch.testing.assert_close(actual_gradient, expected_gradient)

    def test_accumulated_token_denominator_matches_combined_batch(self):
        torch = self.torch
        logits = torch.randn(2, 4, 5, requires_grad=True)
        labels = torch.tensor([[-100, 1, 2, 3], [-100, -100, -100, 4]])
        denominator = (labels[:, 1:] != -100).sum()
        losses = []
        for index in range(2):
            def model(index=index, **kwargs):
                return SimpleNamespace(logits=logits[index:index + 1].index_select(1, kwargs["logits_to_keep"]))
            inputs = {"input_ids": torch.ones_like(labels[index:index + 1]),
                      "attention_mask": torch.ones_like(labels[index:index + 1]), "labels": labels[index:index + 1]}
            losses.append(self.trainer.compute_loss(model, inputs, num_items_in_batch=denominator))
        expected = torch.nn.functional.cross_entropy(logits[:, :-1, :].reshape(-1, 5), labels[:, 1:].reshape(-1), ignore_index=-100)
        torch.testing.assert_close(sum(losses), expected)

    def test_no_supervised_tokens_fail(self):
        torch = self.torch
        labels = torch.full((1, 3), -100)
        with self.assertRaises(ModelError):
            self.trainer.compute_loss(None, {"input_ids": labels, "attention_mask": torch.ones_like(labels), "labels": labels})


@unittest.skipUnless(RUN_INTEGRATION, "전체 toy 학습 검증은 ML 환경에서 R_SCAM_RUN_ML_TESTS=1 지정")
class TinyOfflineIntegration(unittest.TestCase):
    def test_train_export_reload_inference(self):
        import torch
        from tokenizers import Tokenizer
        from tokenizers.models import WordLevel
        from tokenizers.pre_tokenizers import WhitespaceSplit
        from transformers import BertConfig, BertModel, LlamaConfig, LlamaForCausalLM, PreTrainedTokenizerFast
        from architecture.pipeline.__main__ import _settings
        from architecture.pipeline.backends import TransformersEmbedder, TransformersModelScorer
        from architecture.pipeline.config import PipelineConfig
        from architecture.pipeline.data import load_dataset, validate_split
        from architecture.pipeline.pipeline import RomanceScamPipeline
        from architecture.pipeline.rag.vector_search import VectorIndex

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            torch.manual_seed(42)
            words = ["[PAD]", "[UNK]", "[EOS]", "system", "user", "assistant", "SCAM", "NON_SCAM", "UNKNOWN", "end"]
            backend = Tokenizer(WordLevel({word: i for i, word in enumerate(words)}, unk_token="[UNK]"))
            backend.pre_tokenizer = WhitespaceSplit()
            tokenizer = PreTrainedTokenizerFast(tokenizer_object=backend, pad_token="[PAD]", eos_token="[EOS]", unk_token="[UNK]", model_max_length=256)
            tokenizer.chat_template = ("{% for m in messages %}{{ m['role'] + ' ' + m['content'] + ' end ' }}{% endfor %}"
                                       "{% if add_generation_prompt %}{{ 'assistant ' }}{% endif %}")
            for name in ("base", "encoder"):
                tokenizer.save_pretrained(root / name)
            LlamaForCausalLM(LlamaConfig(vocab_size=len(words), hidden_size=16, intermediate_size=32,
                num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2, max_position_embeddings=256,
                pad_token_id=0, eos_token_id=2, bos_token_id=2)).save_pretrained(root / "base")
            BertModel(BertConfig(vocab_size=len(words), hidden_size=16, intermediate_size=32,
                num_hidden_layers=1, num_attention_heads=2, max_position_embeddings=256)).save_pretrained(root / "encoder")
            inputs = [{"conversation_id": f"toy-{i}", "messages": [{"speaker": "A", "text": f"합성 {i}"}]} for i in range(9)]
            answers = [{"conversation_id": f"toy-{i}", "case_group_id": f"toy-group-{i}",
                        "label": ("SCAM", "NON_SCAM", "UNKNOWN")[i % 3], "verified": True} for i in range(9)]
            for name, rows in (("inputs.jsonl", inputs), ("answers.jsonl", answers)):
                (root / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            plan = {"train": [f"toy-{i}" for i in range(3)], "validation": [f"toy-{i}" for i in range(3, 6)],
                    "test": [f"toy-{i}" for i in range(6, 9)]}
            write_json(root / "split.json", plan)
            raw = {"data": {"inputs": "inputs.jsonl", "answers": "answers.jsonl", "split": "split.json"},
                   "model": {"path": "base", "revision": "toy-v1", "local_files_only": True, "family": "causal_lm",
                             "backend": "label_likelihood", "max_input_tokens": 256, "reserved_tokens": 16,
                             "dtype": "float32", "quantization": "none"},
                   "embedding": {"path": "encoder", "revision": "toy-v1", "local_files_only": True,
                                 "max_input_tokens": 256, "dimension": 16, "pooling": "mean", "device_map": "cpu",
                                 "dtype": "float32", "quantization": "none"},
                   "lora": {"r": 2, "alpha": 4, "dropout": 0.0, "target_modules": "all-linear"},
                   "training": {"output_dir": "run", "device": "cpu", "epochs": 1, "batch_size": 1,
                                "gradient_accumulation_steps": 2, "gradient_checkpointing": False,
                                "optim": "adamw_torch", "logging_steps": 1}, "pipeline": PipelineConfig().to_dict()}
            manifest = train(validate_config(raw, root))
            self.assertEqual(manifest["status"], "COMPLETED")
            self.assertFalse(manifest["test_evaluated"])
            settings, pipeline_config = _settings(root / "run/inference_config.json")
            settings["model"]["device_map"] = "cpu"
            scorer = TransformersModelScorer.load(settings["model"])
            embedder = TransformersEmbedder.load(settings["embedding"])
            cases = load_dataset(root / "inputs.jsonl", root / "answers.jsonl")
            index = VectorIndex.build(validate_split(cases, plan), embedder, scorer, {"purpose": "train_only", "split": plan})
            result = RomanceScamPipeline(scorer, embedder, index, pipeline_config).analyze(inputs[6], query_id="toy-6", query_group="toy-group-6")
            self.assertEqual(set(result.response), {"risk_score", "level", "message", "disclaimer"})
            self.assertTrue(0 <= result.response["risk_score"] <= 100)


if __name__ == "__main__":
    unittest.main()

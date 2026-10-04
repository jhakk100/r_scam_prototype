import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from architecture.pipeline.__main__ import _settings
from architecture.pipeline.backends import TransformersModelScorer
from architecture.pipeline.data import CorpusCase, dataset_fingerprint
from architecture.pipeline.errors import ConfigurationError, DataError, InputError, LeakageError, ModelError
from architecture.pipeline.input import prepare_input
from architecture.pipeline.model.tokenization import LabelTokenContract
from model_training.artifacts import adapter_fingerprint, export_inference_config, write_json
from model_training.__main__ import main
from model_training.config import load_config, validate_config
from model_training.demo import CharacterTokenizer, fixture_tokenizers, run_demo
from model_training.preparation import encode_target, pad_features, prepare_datasets, sha256_json, supervised_positions
from model_training.split import partitions, propose_split
from model_training.trainer import select_lora_targets, train

ROOT = Path(__file__).resolve().parents[1]


def fixture_cases(count=12):
    return [CorpusCase(f"case-{i}", f"group-{i}", ("SCAM", "NON_SCAM", "UNKNOWN")[i % 3], True,
                       [{"speaker": "A", "text": f"  원문 {i}\n"}, {"speaker": "B", "text": "확인"}]) for i in range(count)]


class TrainingContracts(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.raw = json.loads((ROOT / "configs/train.example.json").read_text(encoding="utf-8"))
        self.raw["data"].update({"inputs": "inputs.jsonl", "answers": "answers.jsonl", "split": "split.json"})
        for name in ("model", "embedding"):
            self.raw[name].update({"path": name, "revision": "fixture-v1", "max_input_tokens": 10000})
        self.raw["training"]["output_dir"] = "run"
        self.cases = fixture_cases()

    def settings(self):
        return validate_config(self.raw, self.root)

    def write_data(self, cases=None, plan=None):
        cases = self.cases if cases is None else cases
        inputs = [{"conversation_id": c.conversation_id, "messages": c.messages,
                   "secret_metadata": "사후 근거 - 입력 제외"} for c in cases]
        answers = [{"conversation_id": c.conversation_id, "case_group_id": c.case_group_id,
                    "label": c.label, "verified": c.verified} for c in cases]
        for name, rows in (("inputs.jsonl", inputs), ("answers.jsonl", answers)):
            (self.root / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        plan = plan or {"train": [c.conversation_id for c in cases[:6]],
                        "validation": [c.conversation_id for c in cases[6:9]],
                        "test": [c.conversation_id for c in cases[9:]]}
        write_json(self.root / "split.json", plan)
        return plan

    def test_config_relative_paths_and_defaults(self):
        write_json(self.root / "config.json", self.raw)
        settings = load_config(self.root / "config.json")
        self.assertEqual(settings["data"]["inputs"], str(self.root / "inputs.jsonl"))
        self.assertEqual(settings["training"]["output_dir"], str(self.root / "run"))
        self.assertTrue(settings["data"]["verified_only"])
        self.assertIn("SCAM", settings["model"]["instruction"])

    def test_bad_hyperparameters_rejected(self):
        for section, key, value in (("training", "epochs", float("nan")), ("training", "batch_size", True),
            ("training", "learning_rate", 0), ("training", "seed", -1), ("lora", "r", 0),
            ("lora", "dropout", 1.1), ("model", "reserved_tokens", 10000),
            ("model", "backend", "sequence_classification"), ("embedding", "pooling", "cls"),
            ("training", "gradient_checkpointing", "true"), ("data", "verified_only", 1)):
            with self.subTest(section=section, key=key):
                bad = copy.deepcopy(self.raw)
                bad[section][key] = value
                with self.assertRaises(ConfigurationError):
                    validate_config(bad, self.root)

    def test_cpu_requires_no_quantization(self):
        self.raw["training"]["device"] = "cpu"
        with self.assertRaises(ConfigurationError):
            self.settings()
        self.raw["model"].update({"dtype": "float32", "quantization": "none"})
        self.raw["training"]["optim"] = "adamw_torch"
        self.settings()

    def test_remote_requires_fixed_revision(self):
        self.raw["model"].update({"local_files_only": False, "path": "org/model", "revision": "main"})
        with self.assertRaises(ConfigurationError):
            self.settings()
        self.raw["model"]["revision"] = "fixture-fixed-commit"
        self.assertEqual(self.settings()["model"]["path"], "org/model")

    def test_split_reproducible_order_independent_complete(self):
        plan = propose_split(self.cases, seed=42)
        self.assertEqual(plan, propose_split(list(reversed(self.cases)), seed=42))
        divided = partitions(self.cases, plan)
        self.assertEqual(sum(len(rows) for rows in divided.values()), len(self.cases))
        self.assertTrue(all(divided.values()))

    def test_split_groups_and_duplicate_chains_stay_together(self):
        first = self.cases[0]
        duplicate = CorpusCase("extra", "group-1", "SCAM", True, first.messages)
        cases = self.cases + [duplicate]
        plan = propose_split(cases)
        location = {key: name for name, ids in plan.items() for key in ids}
        self.assertEqual(location["case-0"], location["extra"])
        self.assertEqual(location["case-1"], location["extra"])
        partitions(cases, plan)

    def test_split_rejects_cross_event_and_missing_id(self):
        plan = self.write_data()
        case = self.cases[6]
        changed = [*self.cases[:6], CorpusCase(case.conversation_id, "group-0", case.label, True, case.messages), *self.cases[7:]]
        with self.assertRaises(LeakageError):
            partitions(changed, plan)
        plan["test"].pop()
        with self.assertRaises(DataError):
            partitions(self.cases, plan)

    def test_split_rejects_unusable_ratios_or_small_group_count(self):
        for validation, test in ((0, 0.1), (0.5, 0.5), (float("inf"), 0.1)):
            with self.assertRaises(DataError):
                propose_split(self.cases, validation, test)
        with self.assertRaises(DataError):
            propose_split(self.cases[:2])

    def test_shared_tokens_match_inference_all_labels(self):
        settings = self.settings()["model"]
        tokenizer = CharacterTokenizer()
        contract = LabelTokenContract(tokenizer, settings["instruction"], 10000, 32)
        model = SimpleNamespace(config=SimpleNamespace(max_position_embeddings=100000), eval=lambda: None)
        scorer = TransformersModelScorer(model, tokenizer, settings, None)
        text = prepare_input(self.cases[0].messages).text
        self.assertEqual(contract.candidates(text), scorer.candidate_token_ids(text))
        for label in ("SCAM", "NON_SCAM", "UNKNOWN"):
            row = encode_target(contract.candidates(text), label)
            supervised = [token for token in row["labels"] if token != -100]
            self.assertEqual("".join(map(chr, supervised)), label + "</turn>")
            prefix = "".join(map(chr, row["input_ids"][:-len(supervised)]))
            self.assertIn(text, prefix)
            self.assertNotIn("case-0", prefix)
            self.assertNotIn("group-0", prefix)
            self.assertNotIn("verified", prefix)

    def test_padding_masks_prompt_and_pad_and_causal_shift(self):
        rows = [{"input_ids": [1, 2, 3, 4], "attention_mask": [1] * 4, "labels": [-100, -100, 3, 4]},
                {"input_ids": [1, 5, 6], "attention_mask": [1] * 3, "labels": [-100, 5, 6]}]
        padded = pad_features(rows, 0)
        self.assertEqual(padded["labels"][1], [-100, 5, 6, -100])
        self.assertEqual(padded["attention_mask"][1], [1, 1, 1, 0])
        self.assertEqual(supervised_positions(padded["labels"]), [0, 1, 2])
        with self.assertRaises(DataError):
            pad_features([{**rows[0], "conversation_id": "leak"}], 0)
        with self.assertRaises(DataError):
            supervised_positions([[-100, -100]])

    def test_prepare_test_not_in_encoded_and_no_metadata(self):
        self.write_data()
        encoded, report, plan, _ = prepare_datasets(self.settings(), fixture_tokenizers())
        self.assertEqual(set(encoded), {"train", "validation"})
        self.assertEqual(len(encoded["train"]), 6)
        self.assertEqual(report["dataset"]["count"], 12)
        self.assertFalse(report["test_used_for_training_or_selection"])
        self.assertEqual(report["split_sha256"], sha256_json(plan))
        for row in encoded["train"]:
            self.assertEqual(set(row), {"input_ids", "attention_mask", "labels"})
            self.assertNotIn("secret_metadata", "".join(map(chr, row["input_ids"])))

    def test_prepare_unknown_absence_reported_without_synthesis(self):
        cases = [CorpusCase(c.conversation_id, c.case_group_id, "SCAM" if i % 2 else "NON_SCAM", c.verified, c.messages)
                 for i, c in enumerate(self.cases)]
        self.write_data(cases)
        encoded, report, _, _ = prepare_datasets(self.settings(), fixture_tokenizers())
        self.assertEqual(report["partitions"]["train"]["missing_supervised_classes"], ["UNKNOWN"])
        self.assertEqual(len(encoded["train"]), 6)
        self.assertTrue(any("UNKNOWN 정답" in note for note in report["notes"]))

    def test_prepare_verified_filter_without_relabeling(self):
        cases = [CorpusCase(c.conversation_id, c.case_group_id, c.label, i != 0, c.messages) for i, c in enumerate(self.cases)]
        self.write_data(cases)
        encoded, report, _, _ = prepare_datasets(self.settings(), fixture_tokenizers())
        self.assertEqual(len(encoded["train"]), 5)
        self.assertEqual(report["partitions"]["train"]["unverified_count"], 1)
        self.raw["data"]["verified_only"] = False
        encoded, _, _, _ = prepare_datasets(self.settings(), fixture_tokenizers())
        self.assertEqual(len(encoded["train"]), 6)

    def test_prepare_rejects_model_embedding_or_label_overflow(self):
        self.write_data()
        for name, key, value in (("model", "max_input_tokens", 50), ("model", "reserved_tokens", 1),
                                 ("embedding", "max_input_tokens", 1)):
            with self.subTest(name=name, key=key):
                bad = copy.deepcopy(self.raw)
                bad[name][key] = value
                with self.assertRaises(InputError):
                    prepare_datasets(validate_config(bad, self.root), fixture_tokenizers())

    def test_prepare_rejects_changed_data_fingerprint(self):
        self.write_data()
        self.raw["data"]["expected_sha256"] = "0" * 64
        with self.assertRaises(DataError):
            prepare_datasets(self.settings(), fixture_tokenizers())
        self.raw["data"]["expected_sha256"] = dataset_fingerprint(self.cases)
        prepare_datasets(self.settings(), fixture_tokenizers())

    def test_gemma_targets_exclude_vision_audio_head(self):
        class Linear:
            pass
        model = SimpleNamespace(named_modules=lambda: iter([
            ("model.language_model.layers.0.q_proj", Linear()), ("model.vision_tower.linear", Linear()),
            ("model.audio_tower.linear", Linear()), ("lm_head", Linear()), ("model.language_model.norm", object())]))
        self.assertEqual(select_lora_targets(model, "gemma4", (Linear,)), ["model.language_model.layers.0.q_proj"])
        self.assertNotIn("lm_head", select_lora_targets(model, "causal_lm", (Linear,)))

    def test_training_preserves_nonempty_output_before_loading(self):
        directory = self.root / "run"
        directory.mkdir()
        (directory / "existing.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(ConfigurationError):
            train(self.settings())
        self.assertEqual((directory / "existing.txt").read_text(), "keep")

    def test_export_config_can_be_loaded_by_architecture(self):
        settings = self.settings()
        output = self.root / "run"
        config = export_inference_config(settings, output, "1" * 64)
        write_json(output / "inference_config.json", config)
        loaded, _ = _settings(output / "inference_config.json")
        self.assertEqual(loaded["model"]["path"], settings["model"]["path"])
        self.assertEqual(loaded["model"]["adapter_path"], str(output / "final_adapter"))
        self.assertEqual(loaded["model"]["instruction"], settings["model"]["instruction"])
        self.assertEqual(loaded["pipeline"], settings["pipeline"])
        self.assertEqual(set(loaded), {"pipeline", "model", "embedding"})

    def test_adapter_hash_changes_when_weights_change(self):
        final = self.root / "final"
        final.mkdir()
        with self.assertRaises(OSError):
            adapter_fingerprint(final)
        (final / "adapter_config.json").write_text("{}")
        weights = final / "adapter_model.safetensors"
        weights.write_bytes(b"synthetic-bytes-not-valid-weights")
        before = adapter_fingerprint(final)
        weights.write_bytes(b"different-synthetic-bytes")
        self.assertNotEqual(before, adapter_fingerprint(final))

    def test_remote_export_uses_exact_saved_local_tokenizer(self):
        self.raw["model"].update({"path": "org/model", "local_files_only": False})
        settings = self.settings()
        output = self.root / "run"
        config = export_inference_config(settings, output, "1" * 64)
        write_json(output / "inference_config.json", config)
        loaded, _ = _settings(output / "inference_config.json")
        self.assertEqual(loaded["model"]["path"], "org/model")
        self.assertEqual(loaded["model"]["tokenizer_path"], str(output / "final_adapter"))
        self.assertEqual(loaded["model"]["adapter_path"], str(output / "final_adapter"))

    def test_cli_split_proposal_is_architecture_compatible_and_preserves_existing(self):
        self.write_data()
        output = self.root / "proposal.json"
        args = ["propose-split", "--inputs", str(self.root / "inputs.jsonl"),
                "--answers", str(self.root / "answers.jsonl"), "--output", str(output)]
        with patch("model_training.__main__._emit") as emit:
            self.assertEqual(main(args), 0)
            self.assertIn("PROPOSAL", emit.call_args.args[0]["status"])
            before = output.read_bytes()
            partitions(self.cases, json.loads(before))
            metadata = json.loads(output.with_name("proposal.json.metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["dataset_sha256"], dataset_fingerprint(self.cases))
            self.assertEqual(main(args), 1)
            self.assertEqual(output.read_bytes(), before)

    def test_demo_is_explicitly_non_training(self):
        report = run_demo()
        self.assertFalse(report["weights_created"])
        self.assertTrue(report["prompt_masked"])
        self.assertIn("not_training", report["purpose"])


if __name__ == "__main__":
    unittest.main()

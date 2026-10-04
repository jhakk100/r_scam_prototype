"""합성 fixture만 사용한 학습 입력 연결 확인. 모델 학습·성능 검증이 아니다."""

from types import SimpleNamespace

from architecture.pipeline.backends import DEFAULT_INSTRUCTION
from architecture.pipeline.data import CorpusCase
from architecture.pipeline.input import prepare_input
from architecture.pipeline.model.tokenization import LabelTokenContract
from .preparation import encode_target, pad_features, supervised_positions
from .split import propose_split


class CharacterTokenizer:
    chat_template = "fixture-character-chat-template"
    model_max_length = 100000
    pad_token_id = 0

    def __call__(self, text, **kwargs):
        return {"input_ids": [ord(character) for character in text]}

    def apply_chat_template(self, messages, *, add_generation_prompt, **kwargs):
        text = "".join(f"<{message['role']}>" + message["content"] + "</turn>" for message in messages)
        return text + ("<assistant>" if add_generation_prompt else "")


def fixture_tokenizers():
    return {name: (CharacterTokenizer(), SimpleNamespace(max_position_embeddings=100000))
            for name in ("model", "embedding")}


def run_demo():
    tokenizer = CharacterTokenizer()
    contract = LabelTokenContract(tokenizer, DEFAULT_INSTRUCTION, 10000, 32)
    cases = [CorpusCase(f"fixture-{i}", f"fixture-group-{i}", label, True,
                       [{"speaker": "A", "text": f"합성 대화 {i}"}])
             for i, label in enumerate(("SCAM", "NON_SCAM", "UNKNOWN") * 3)]
    plan = propose_split(cases, seed=42)
    rows = [encode_target(contract.candidates(prepare_input(case.messages).text), case.label) for case in cases[:3]]
    padded = pad_features(rows, tokenizer.pad_token_id)
    return {"purpose": "synthetic_fixture_contract_check_not_training_or_performance",
            "split_counts": {name: len(ids) for name, ids in plan.items()},
            "class_order": ["SCAM", "NON_SCAM", "UNKNOWN"],
            "prompt_masked": all(all(value == -100 for value in row["labels"][:len(row["labels"]) -
                                           sum(value != -100 for value in row["labels"])]) for row in rows),
            "supervised_token_counts": [sum(value != -100 for value in row["labels"]) for row in rows],
            "causal_logit_positions": supervised_positions(padded["labels"]),
            "weights_created": False}

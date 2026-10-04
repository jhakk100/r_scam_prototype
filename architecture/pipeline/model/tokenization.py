"""학습과 추론이 공유하는 고정 대화·전체 라벨 토큰 계약."""

from ..errors import InputError, ModelError
from .model_scorer import CLASS_ORDER


class LabelTokenContract:
    def __init__(self, tokenizer, instruction, max_input_tokens, reserved_tokens):
        if not getattr(tokenizer, "chat_template", None):
            raise ModelError("label_likelihood에는 고정 chat_template가 필요합니다.")
        self.tokenizer = tokenizer
        self.instruction = instruction
        self.max_input_tokens = max_input_tokens
        self.reserved_tokens = reserved_tokens

    def messages(self, conversation):
        return [{"role": "system", "content": self.instruction},
                {"role": "user", "content": conversation}]

    def prefix(self, conversation):
        return self.tokenizer.apply_chat_template(self.messages(conversation), tokenize=False,
                                                  add_generation_prompt=True, enable_thinking=False)

    def ids(self, text):
        return self.tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"]

    def count_tokens(self, conversation):
        return len(self.ids(self.prefix(conversation)))

    def candidates(self, conversation):
        prefix = self.ids(self.prefix(conversation))
        if not prefix:
            raise ModelError("빈 모델 프롬프트입니다.")
        if len(prefix) + self.reserved_tokens > self.max_input_tokens:
            raise InputError("모델 전체 입력 한도 초과; truncation하지 않습니다.")
        candidates = []
        for label in CLASS_ORDER:
            text = self.tokenizer.apply_chat_template(
                self.messages(conversation) + [{"role": "assistant", "content": label}],
                tokenize=False, add_generation_prompt=False, enable_thinking=False)
            full = self.ids(text)
            if full[:len(prefix)] != prefix or len(full) <= len(prefix):
                raise ModelError("라벨 응답의 token prefix가 고정 프롬프트와 일치하지 않습니다.")
            tail = len(full) - len(prefix)
            if tail > self.reserved_tokens:
                raise InputError("전체 라벨 응답이 model.reserved_tokens를 초과합니다.")
            candidates.append((full, tail))
        return candidates

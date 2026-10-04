import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from .errors import InputError
from .validation import identifier, positive_integer

INPUT_CONTRACT = "messages-json-v1"


@dataclass(frozen=True)
class PreparedInput:
    text: str
    sha256: str
    message_count: int


def prepare_input(data):
    """관리 metadata를 제외하고 원문·공백·발화 순서를 그대로 직렬화한다."""
    if isinstance(data, Mapping):
        messages = data.get("messages")
    elif isinstance(data, str):
        # 붙여넣은 원문에서 화자/발화 경계를 추측하여 내용을 바꾸지 않는다.
        messages = [{"speaker": "TEXT", "text": data}]
    else:
        messages = data
    if not isinstance(messages, list) or not messages:
        raise InputError("messages는 비어 있지 않은 배열이어야 합니다.")
    output = []
    for i, message in enumerate(messages):
        if not isinstance(message, Mapping):
            raise InputError(f"messages[{i}]는 객체여야 합니다.")
        speaker = identifier(message.get("speaker"), f"messages[{i}].speaker", InputError)
        text = message.get("text")
        if not isinstance(text, str):
            raise InputError(f"messages[{i}].text는 문자열이어야 합니다.")
        output.append({"speaker": speaker, "text": text})
    if not any(m["text"].strip() for m in output):
        raise InputError("분석할 대화 내용이 없습니다.")
    text = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    return PreparedInput(text, hashlib.sha256(text.encode("utf-8")).hexdigest(), len(output))


def check_input_budget(prepared, backend, name):
    maximum = positive_integer(backend.max_input_tokens, f"{name}.max_input_tokens", InputError)
    reserved = positive_integer(backend.reserved_tokens, f"{name}.reserved_tokens", InputError, True)
    count = positive_integer(backend.count_tokens(prepared.text), f"{name}.token_count", InputError)
    if count + reserved > maximum:
        raise InputError(f"{name} 입력 한도 초과: {count}+{reserved}>{maximum}; 자동 truncation하지 않습니다.")
    return {"tokenizer": backend.tokenizer_identity, "input_tokens": count,
            "reserved_tokens": reserved, "max_input_tokens": maximum}

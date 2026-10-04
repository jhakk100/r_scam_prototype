"""학습 산출물 및 기존 아키텍처용 실행 설정. 학습 전 결과 수치를 만들지 않는다."""

import copy
import hashlib
import json
import os
from pathlib import Path


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def adapter_fingerprint(directory):
    directory = Path(directory)
    paths = sorted([directory / "adapter_config.json", *directory.glob("adapter_model*.safetensors")])
    if len(paths) < 2 or any(not path.is_file() for path in paths):
        raise OSError("최종 PEFT adapter_config/adapter_model safetensors가 없습니다.")
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8") + b"\0")
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def export_inference_config(settings, output_dir, adapter_sha256):
    output_dir = Path(output_dir).resolve()
    config = copy.deepcopy({key: settings[key] for key in ("pipeline", "model", "embedding")})
    for name in ("model", "embedding"):
        values = config[name]
        if values.get("local_files_only", True):
            for key in ("path", "tokenizer_path"):
                if values.get(key):
                    try:
                        values[key] = os.path.relpath(values[key], output_dir).replace("\\", "/")
                    except ValueError:  # 서로 다른 Windows drive의 경우 절대 경로를 유지한다.
                        values[key] = str(Path(values[key]).resolve())
    config["model"].update({"adapter_path": "final_adapter", "adapter_revision": adapter_sha256,
                            "tokenizer_path": "final_adapter", "device_map": "auto"})
    # architecture는 원격 source 설정의 상대 경로를 해석하지 않는다.
    # 로컬 산출물은 절대 경로로 지정해 저장한 정확한 tokenizer를 재사용한다.
    if not config["model"].get("local_files_only", True):
        config["model"]["tokenizer_path"] = str(output_dir / "final_adapter")
        config["model"]["adapter_path"] = str(output_dir / "final_adapter")
    return config

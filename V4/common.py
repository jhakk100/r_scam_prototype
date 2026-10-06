"""Repository-local paths and read-only artifact helpers."""
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
PATH_KEYS = {"experiment", "dataset", "model_run", "inference_config", "projection", "index",
             "retrieval_config", "fusion_config", "balanced_test", "xy_profile", "adapter_path",
             "comparison", "report", "paper", "technical_spec", "easy_guide", "verification",
             "active_runtime"}


def read(path):
    def resolve(value, key=None):
        if isinstance(value, dict):
            return {k: resolve(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v) for v in value]
        if key in PATH_KEYS and isinstance(value, str) and value.startswith("@repo/"):
            target = (ROOT / value[6:]).resolve()
            if not target.is_relative_to(ROOT):
                raise ValueError("Repository path escapes project root")
            return str(target)
        return value
    return resolve(json.loads(Path(path).read_text(encoding="utf-8-sig")))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

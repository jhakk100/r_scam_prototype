"""Exact model-input contract preserved from the measured training run."""
import json
from topic_behavior import Extractor
from architecture.pipeline.input import prepare_input

def model_input(messages, representation=None):
    """Exactly the same label-free format in training and inference."""
    rep = representation or Extractor().extract(messages)
    context = {"topic": rep["topic_descriptor"],
               "behavior_features": dict(zip(rep["feature_names"], rep["behavior_features"]))}
    return prepare_input(messages).text + "\nV3_CONTEXT\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":"))

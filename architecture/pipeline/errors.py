class PipelineError(ValueError):
    """정상 위험 점수로 대체하면 안 되는 파이프라인 오류."""

    code = "PIPELINE_ERROR"


class InputError(PipelineError):
    code = "INPUT_ERROR"


class ConfigurationError(PipelineError):
    code = "CONFIGURATION_ERROR"


class ModelError(PipelineError):
    code = "MODEL_ERROR"


class RetrievalError(PipelineError):
    code = "RETRIEVAL_ERROR"


class DataError(PipelineError):
    code = "DATA_ERROR"


class LeakageError(DataError):
    code = "LEAKAGE_ERROR"

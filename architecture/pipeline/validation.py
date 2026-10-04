import math
from numbers import Real

from .errors import PipelineError


def number(value, name, error=PipelineError, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise error(f"{name}: 유한한 수치가 필요합니다.")
    try:
        value = float(value)
    except (ValueError, OverflowError) as exc:
        raise error(f"{name}: 표현 가능한 유한한 수치가 필요합니다.") from exc
    if not math.isfinite(value):
        raise error(f"{name}: NaN/Inf는 허용하지 않습니다.")
    if minimum is not None and value < minimum:
        raise error(f"{name}: {minimum} 이상이어야 합니다.")
    if maximum is not None and value > maximum:
        raise error(f"{name}: {maximum} 이하여야 합니다.")
    return value


def positive_integer(value, name, error=PipelineError, allow_zero=False):
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise error(f"{name}: {'0 이상' if allow_zero else '양의'} 정수가 필요합니다.")
    return value


def identifier(value, name, error=PipelineError):
    if not isinstance(value, str) or not value.strip():
        raise error(f"{name}: 비어 있지 않은 문자열이 필요합니다.")
    return value

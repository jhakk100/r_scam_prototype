"""사건 그룹과 완전 동일 대화를 묶은 분할 제안. 사건 독립성의 자동 증명은 아니다."""

import random

from architecture.pipeline.data import validate_split
from architecture.pipeline.errors import DataError
from architecture.pipeline.input import prepare_input
from architecture.pipeline.validation import number, positive_integer

PARTITIONS = ("train", "validation", "test")


def partitions(cases, plan):
    validate_split(cases, plan)
    if any(not plan[name] for name in PARTITIONS):
        raise DataError("학습/검증/최종 평가용 train/validation/test 모두 비어 있지 않아야 합니다.")
    by_id = {case.conversation_id: case for case in cases}
    return {name: [by_id[key] for key in plan[name]] for name in PARTITIONS}


def propose_split(cases, validation_ratio=0.15, test_ratio=0.15, seed=42):
    """라벨 성능을 보고 분할을 고르지 않는 재현 가능한 그룹 단위 제안."""
    for value, name in ((validation_ratio, "validation_ratio"), (test_ratio, "test_ratio")):
        if not 0 < number(value, name, DataError, minimum=0, maximum=1) < 1:
            raise DataError("검증/평가 비율은 0과 1 사이여야 합니다.")
    if validation_ratio + test_ratio >= 1:
        raise DataError("검증/평가 비율 합은 1보다 작아야 합니다.")
    positive_integer(seed, "seed", DataError, True)
    by_id = {case.conversation_id: case for case in cases}
    if not cases or len(by_id) != len(cases):
        raise DataError("비어 있거나 ID가 중복된 데이터셋입니다.")
    parent = {key: key for key in by_id}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    seen = {}
    for case in sorted(cases, key=lambda c: c.conversation_id):
        for identity in (("group", case.case_group_id), ("text", prepare_input(case.messages).sha256)):
            if identity in seen:
                parent[find(case.conversation_id)] = find(seen[identity])
            else:
                seen[identity] = case.conversation_id
    components = {}
    for key in sorted(by_id):
        components.setdefault(find(key), []).append(key)
    clusters = list(components.values())
    if len(clusters) < 3:
        raise DataError("서로 분리 가능한 사건/동일 대화 묶음이 3개 미만입니다.")
    random.Random(seed).shuffle(clusters)
    targets = {"train": len(cases) * (1 - validation_ratio - test_ratio),
               "validation": len(cases) * validation_ratio, "test": len(cases) * test_ratio}
    plan = {name: [] for name in PARTITIONS}
    for index, cluster in enumerate(clusters):
        empty = [name for name in PARTITIONS if not plan[name]]
        if len(clusters) - index == len(empty):
            name = max(empty, key=lambda key: targets[key])
        else:
            name = max(PARTITIONS, key=lambda key: targets[key] - len(plan[key]))
        plan[name].extend(cluster)
    for ids in plan.values():
        ids.sort()
    partitions(cases, plan)
    return plan

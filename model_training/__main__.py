import argparse
import json
import sys
from pathlib import Path

from architecture.pipeline.config import read_json
from architecture.pipeline.data import audit_dataset, load_dataset
from architecture.pipeline.errors import ConfigurationError, PipelineError
from .artifacts import write_json
from .config import load_config
from .demo import run_demo
from .preparation import prepare_datasets, sha256_json
from .split import partitions, propose_split

ROOT = Path(__file__).resolve().parents[1]


def _data_arguments(parser):
    parser.add_argument("--inputs", type=Path, default=ROOT / "dataset/study dataset/dataset.jsonl")
    parser.add_argument("--answers", type=Path, default=ROOT / "dataset/answer dataset/answers.jsonl")


def _emit(value, stream=sys.stdout):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), file=stream)


def _new_file(path):
    if Path(path).exists():
        raise ConfigurationError(f"기존 파일을 덮어쓰지 않습니다. 새 경로를 지정하십시오: {path}")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="r_scam v1 모델 학습 (추론 아키텍처와 별도)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="ML 설치 없이 합성 fixture의 입력/마스킹/분할 확인")
    audit = commands.add_parser("audit-data", help="원본 수정 없이 데이터 및 선택적 분할 검사")
    _data_arguments(audit)
    audit.add_argument("--split-file", type=Path)
    split = commands.add_parser("propose-split", help="사건 그룹/동일 대화 묶음 단위 분할 초안 생성")
    _data_arguments(split)
    split.add_argument("--output", type=Path, required=True)
    split.add_argument("--validation-ratio", type=float, default=0.15)
    split.add_argument("--test-ratio", type=float, default=0.15)
    split.add_argument("--seed", type=int, default=42)
    prepare = commands.add_parser("prepare", help="모델 가중치 없이 실제 tokenizer로 전체 입력 길이 검사")
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--report", type=Path, help="선택적 검사 결과 저장 (대화 원문/학습 token은 저장하지 않음)")
    training = commands.add_parser("train", help="실제 PEFT (Q)LoRA 학습; 모델/GPU 환경 필요")
    training.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            _emit(run_demo())
        elif args.command in ("audit-data", "propose-split"):
            cases = load_dataset(args.inputs, args.answers)
            report = audit_dataset(cases)
            report["notes"] = ["study/answer 파일은 입력/정답 쌍이며 train/test 분할이 아님.",
                               "서로 다른 case_group_id만으로 사건 독립성을 보장하지 않음. 파생본의 그룹은 연구자가 확인해야 함."]
            if args.command == "audit-data":
                if args.split_file:
                    divided = partitions(cases, read_json(args.split_file))
                    report["partitions"] = {name: audit_dataset(rows) for name, rows in divided.items()}
                _emit(report)
            else:
                metadata_path = args.output.with_name(args.output.name + ".metadata.json")
                _new_file(args.output)
                _new_file(metadata_path)
                plan = propose_split(cases, args.validation_ratio, args.test_ratio, args.seed)
                report.update({"status": "PROPOSAL_REQUIRES_EVENT_GROUP_REVIEW", "seed": args.seed,
                    "requested_validation_ratio": args.validation_ratio, "requested_test_ratio": args.test_ratio,
                    "split_sha256": sha256_json(plan),
                    "partitions": {name: audit_dataset(rows) for name, rows in partitions(cases, plan).items()}})
                write_json(args.output, plan)
                write_json(metadata_path, report)
                _emit({"split_proposal": str(args.output.resolve()), "metadata": str(metadata_path.resolve()),
                       "status": report["status"]})
        elif args.command == "prepare":
            if args.report:
                _new_file(args.report)
            _, report, _, _ = prepare_datasets(load_config(args.config))
            if args.report:
                write_json(args.report, report)
            _emit(report)
        else:
            from .trainer import train
            _emit(train(load_config(args.config)))
    except PipelineError as exc:
        _emit({"status": "ERROR", "code": exc.code, "message": str(exc)}, sys.stderr)
        return 1
    except OSError as exc:
        _emit({"status": "ERROR", "code": "IO_ERROR", "message": str(exc)}, sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

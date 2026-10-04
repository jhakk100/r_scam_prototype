import argparse
import json
import sys
from pathlib import Path

from .config import PipelineConfig, read_json
from .data import audit_dataset, dataset_fingerprint, load_dataset, validate_split
from .demo import run_demo
from .errors import ConfigurationError, PipelineError
from .pipeline import RomanceScamPipeline
from .rag.vector_search import VectorIndex

ROOT = Path(__file__).resolve().parents[2]


def _data_arguments(parser):
    parser.add_argument("--inputs", type=Path, default=ROOT / "dataset/study dataset/dataset.jsonl")
    parser.add_argument("--answers", type=Path, default=ROOT / "dataset/answer dataset/answers.jsonl")


def _settings(path):
    settings = read_json(path)
    if not isinstance(settings, dict) or set(settings) != {"pipeline", "model", "embedding"}:
        raise ConfigurationError("실행 설정에는 pipeline/model/embedding 객체가 필요합니다.")
    config = PipelineConfig.from_dict(settings["pipeline"])
    # 실행 위치에 의존하지 않도록 로컬 모델 경로를 설정 파일 위치 기준으로 해석한다.
    for name in ("model", "embedding"):
        values = settings[name]
        if not isinstance(values, dict):
            raise ConfigurationError(f"{name} 설정은 객체여야 합니다.")
        if values.get("local_files_only", True):
            for key in ("path", "tokenizer_path", "adapter_path"):
                if values.get(key) and not Path(values[key]).is_absolute():
                    values[key] = str((Path(path).resolve().parent / values[key]).resolve())
    return settings, config


def _emit(value, stream=sys.stdout):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), file=stream)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="r_scam v1 추론 아키텍처 (모델 학습은 별도 단계)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="ML 라이브러리 없는 합성 fixture 기능 검증")
    audit = commands.add_parser("audit-data", help="입력/정답 연결·스키마 검사; 파일 수정 없음")
    _data_arguments(audit)
    build = commands.add_parser("build-index", help="실제 embedding으로 RAG index 생성")
    _data_arguments(build)
    build.add_argument("--config", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    corpus = build.add_mutually_exclusive_group(required=True)
    corpus.add_argument("--split-file", type=Path, help="train/validation/test ID 배열; train만 입고")
    corpus.add_argument("--all-cases", action="store_true", help="평가용이 아닌 전체 prototype corpus를 명시적으로 생성")
    infer = commands.add_parser("infer", help="실제 모델·embedding·index로 추론")
    infer.add_argument("--config", type=Path, required=True)
    infer.add_argument("--index", type=Path, required=True)
    infer.add_argument("--input", type=Path, required=True, help="messages를 가진 JSON 또는 JSON 메시지 배열")
    infer.add_argument("--log", type=Path, help="사용자 출력과 별도의 내부 JSON 로그")
    infer.add_argument("--query-id", help="데이터셋 평가 대상 ID (자기 대화 누수 검사)")
    infer.add_argument("--query-group", help="데이터셋 평가 대상 사건 (사건 누수 검사)")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            _emit(run_demo())
        elif args.command == "audit-data":
            _emit(audit_dataset(load_dataset(args.inputs, args.answers)))
        elif args.command == "build-index":
            settings, _ = _settings(args.config)
            cases = load_dataset(args.inputs, args.answers)
            provenance = {"dataset_sha256": dataset_fingerprint(cases)}
            if args.split_file:
                split = read_json(args.split_file)
                selected = validate_split(cases, split)
                provenance.update({"purpose": "train_only", "split": split})
            else:
                selected = cases
                provenance["purpose"] = "prototype_all_cases_not_for_evaluation"
            from .backends import TransformersEmbedder, TransformersModelScorer
            model = TransformersModelScorer.load(settings["model"])
            embedder = TransformersEmbedder.load(settings["embedding"])
            index = VectorIndex.build(selected, embedder, model, provenance)
            index.save(args.output)
            _emit({"index_path": str(args.output.resolve()), "case_count": len(index.entries),
                   "purpose": provenance["purpose"], "embedding": index.spec.to_dict()})
        else:
            if bool(args.query_id) != bool(args.query_group):
                raise ConfigurationError("데이터셋 평가 시 --query-id와 --query-group을 함께 지정하십시오.")
            settings, config = _settings(args.config)
            index = VectorIndex.load(args.index)
            if args.query_id and index.provenance.get("purpose") != "train_only":
                raise ConfigurationError("평가 대상 추론에는 train-only 분할로 생성한 index가 필요합니다.")
            from .backends import TransformersEmbedder, TransformersModelScorer
            model = TransformersModelScorer.load(settings["model"])
            embedder = TransformersEmbedder.load(settings["embedding"])
            pipeline = RomanceScamPipeline(model, embedder, index, config)
            result = pipeline.analyze(read_json(args.input), query_id=args.query_id, query_group=args.query_group)
            if args.log:
                args.log.parent.mkdir(parents=True, exist_ok=True)
                args.log.write_text(json.dumps(result.internal_log, ensure_ascii=False,
                                               allow_nan=False, indent=2) + "\n", encoding="utf-8")
            _emit(result.response)
    except PipelineError as exc:
        _emit({"status": "ERROR", "code": exc.code, "message": str(exc)}, sys.stderr)
        return 1
    except OSError as exc:
        _emit({"status": "ERROR", "code": "IO_ERROR", "message": str(exc)}, sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

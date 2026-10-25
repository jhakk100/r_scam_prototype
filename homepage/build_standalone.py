"""Build an offline Windows inference folder from the measured local environment.

Run using the repository's measured Python. Copies actual files, never symlinks,
and records content hashes. No training, model downloads, or pip installation.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path[:0] = [str(REPO / 'V4'), str(REPO)]
from architecture.pipeline.input import prepare_input
from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT_DISTRIBUTIONS = ['torch', 'transformers', 'peft', 'accelerate', 'bitsandbytes',
                      'scikit-learn', 'numpy', 'scipy', 'tzdata']
MODULES = ['pipeline.py', 'd03_retrieval.py', 'fusion.py', 'common.py', 'core.py',
           'case_retrieval.py', 'topic_behavior.py']


def json_value(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def distributions():
    environment = default_environment()
    environment['extra'] = ''
    queue = list(ROOT_DISTRIBUTIONS)
    found = {}
    while queue:
        name = queue.pop(0)
        key = name.lower().replace('_', '-')
        if key in found:
            continue
        dist = metadata.distribution(name)
        found[key] = dist
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is None or req.marker.evaluate(environment):
                queue.append(req.name)
    return list(found.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=HERE / '실행묶음')
    parser.add_argument('--resume', action='store_true', help='Resume an interrupted bundle after verifying existing copies')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and not args.resume:
        raise SystemExit('Output already exists; choose a new empty folder. Nothing overwritten.')
    if sys.version_info[:2] != (3, 11) or sys.platform != 'win32':
        raise SystemExit('Use the measured Windows Python 3.11 environment.')
    if args.resume and output.exists() and not (output / 'server.py').is_file():
        raise SystemExit('Resume target is not a previously created homepage bundle.')
    output.mkdir(parents=True, exist_ok=args.resume)
    records = {}

    def write_bytes(relative, data, category):
        dest = output / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        records[relative] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'category': category}

    def write_json(relative, value, category):
        write_bytes(relative, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'), category)

    def copy_file(source, relative, category):
        source = Path(source)
        dest = output / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if args.resume and dest.is_file() and dest.stat().st_size == source.stat().st_size:
            def fingerprint(path):
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                        digest.update(block)
                return digest.hexdigest()
            expected = fingerprint(source)
            if fingerprint(dest) == expected:
                records[relative] = {'bytes': dest.stat().st_size, 'sha256': expected, 'category': category}
                return
        digest = hashlib.sha256()
        size = 0
        with source.open('rb') as reader, dest.open('wb') as writer:
            for chunk in iter(lambda: reader.read(8 * 1024 * 1024), b''):
                writer.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        records[relative] = {'bytes': size, 'sha256': digest.hexdigest(), 'category': category}

    print('Copying homepage and frozen inference modules...', flush=True)
    for name in ['server.py', 'start.ps1', 'stop.ps1', '마음체크_시작.cmd', '마음체크_종료.cmd',
                 'examples.json', 'verify_integration.py', 'verify_standalone.py']:
        copy_file(HERE / name, name, 'application')
    for folder in ['app', 'maeum-check-source']:
        for path in (HERE / folder).rglob('*'):
            if path.is_file():
                copy_file(path, path.relative_to(HERE).as_posix(), 'web_assets')
    for name in MODULES:
        copy_file(REPO / 'V4' / name, 'engine/V4/' + name, 'inference_code')
    # These small modules form the existing import closure, not training tools.
    for path in (REPO / 'architecture').rglob('*.py'):
        if not any(part in ('tests', '__pycache__') for part in path.parts) and not path.name.startswith('test_'):
            copy_file(path, 'engine/' + path.relative_to(REPO).as_posix(), 'inference_code')
    for name in ['__init__.py', 'artifacts.py']:
        copy_file(REPO / 'model_training' / name, 'engine/model_training/' + name, 'adapter_integrity')

    active = json_value(REPO / 'V4/active_runtime.json')
    selected = json_value(REPO / 'V4/final-selection.json')
    selected = {'status': selected['status'], 'model': selected['model'], 'method': selected['method'],
                'independent_validation': selected['independent_validation']}
    active = {key: active[key] for key in ('inference_config', 'projection', 'index', 'retrieval_config',
              'fusion_config', 'xy_profile', 'model_variant', 'temporary', 'retrieval_method')}
    active['projection'] = '@repo/V4/runtime/feature-rules.json'
    write_json('engine/V4/active_runtime.json', active, 'frozen_configuration')
    write_json('engine/V4/final-selection.json', selected, 'frozen_configuration')
    cfg = json_value(REPO / 'V4/runtime/specialized-inference.json')
    cfg['embedding'] = {}  # D03 never loads an embedding model.
    write_json('engine/V4/runtime/specialized-inference.json', cfg, 'frozen_configuration')
    for relative in ['V4/fusion-config.json', 'V4/runtime/xy-profile.json',
                     'V4/runtime/rag_index.json', 'V4/runtime/retrieval-config.json']:
        copy_file(REPO / relative, 'engine/' + relative, 'frozen_configuration')
    rules = json_value(REPO / 'V4/datasets/training/projection.json')['rules']
    write_json('engine/V4/runtime/feature-rules.json', {'rules': rules}, 'feature_rules')
    entries = json_value(REPO / 'V4/runtime/rag_index.json')['entries']
    ids = {row['conversation_id'] for row in entries}
    points = json_value(REPO / 'V4/map/dataset-3d.json')['points']
    reference = [{'id': row['id'], 'messages': row['messages']} for row in points if row['id'] in ids]
    assert len(reference) == len(entries) == 226
    write_json('engine/V4/runtime/reference-cases.json', {'points': reference}, 'reference_dataset')
    # Hash/ID exclusions retain exact evaluation behavior without bundling test text.
    test_rows = json_value(REPO / 'V4/experiments/d03-final-paired-20261006_205128/test-inputs.json')
    exclusions = [{'input_sha256': prepare_input(row['messages']).sha256,
                   'conversation_id': row['conversation_id'], 'case_group_id': row['case_group_id']}
                  for row in test_rows]
    write_json('engine/V4/runtime/query-exclusions.json', exclusions, 'reference_exclusions')

    print('Copying selected base weights and final adapter (no hard links)...', flush=True)
    for name in ['config.json', 'generation_config.json', 'model.safetensors', 'README.md']:
        copy_file(REPO / 'models_original/E2B' / name, 'engine/models_original/E2B/' + name, 'base_model')
        print('Base model:', name, flush=True)
    for name in ['adapter_config.json', 'adapter_model.safetensors', 'tokenizer.json',
                 'tokenizer_config.json', 'chat_template.jinja', 'README.md']:
        copy_file(REPO / 'V4/model/final_adapter' / name, 'engine/V4/model/final_adapter/' + name, 'final_adapter')
    copy_file(REPO / 'LICENSE', 'engine/LICENSE', 'license')

    print('Copying isolated Python 3.11...', flush=True)
    native = Path(sys.executable).parent
    if not (native / 'python311.zip').is_file():
        raise SystemExit('The source Python must contain its embedded standard library.')
    for path in native.iterdir():
        if path.is_file() and path.suffix in ('.exe', '.dll', '.pyd', '.zip'):
            copy_file(path, 'python/' + path.name, 'python_runtime')
    write_bytes('python/python311._pth', b'python311.zip\n.\n..\n../packages\nimport site\n', 'python_runtime')
    python_license = REPO.parent / 'v2/runtime/python311/LICENSE.txt'
    if python_license.is_file():
        copy_file(python_license, 'python/LICENSE.txt', 'license')

    print('Resolving runtime-only wheel dependencies...', flush=True)
    copied = set()
    package_records = []
    tasks = []
    for dist in distributions():
        root = Path(dist.locate_file('')).resolve()
        package_records.append({'name': dist.metadata['Name'], 'version': dist.version})
        for item in dist.files or []:
            relative = Path(str(item))
            if relative.is_absolute() or '..' in relative.parts:
                continue  # Installed console entry points are not runtime imports.
            # NumPy imports this one compatibility helper during normal SciPy imports.
            runtime_helper = relative.as_posix() == 'numpy/_core/tests/_natype.py'
            if ((not runtime_helper and any(part in ('__pycache__', 'tests', 'test', 'docs', 'benchmarks') for part in relative.parts))
                    or relative.suffix == '.pyc' or relative.parts[:2] == ('torch', 'include')):
                continue
            source = (root / relative).resolve()
            if not source.is_relative_to(root) or not source.is_file():
                continue
            dest = 'packages/' + relative.as_posix()
            if dest in copied:
                continue
            copied.add(dest)
            tasks.append((source, dest, 'python_packages'))
    # Keep native dependencies/metadata; omit pip, training CLIs, caches and tests.
    total = len(tasks)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, _ in enumerate(pool.map(lambda task: copy_file(*task), tasks), 1):
            if index % 1000 == 0 or index == total:
                print(f'Runtime files: {index}/{total}', flush=True)
    write_json('runtime-packages.json', sorted(package_records, key=lambda row: row['name'].lower()), 'runtime_versions')
    write_bytes('읽어주세요.md', (HERE / 'standalone-guide.md').read_bytes(), 'documentation')
    manifest = {
        'format': 1, 'platform': 'Windows x64', 'python': '3.11',
        'requires': ['NVIDIA GPU', 'compatible NVIDIA driver'],
        'adapter_revision': selected['model']['adapter_revision'],
        'retrieval_method': active['retrieval_method'],
        'reference_case_count': len(reference), 'copied_external_links': False,
        'runtime_packages': package_records, 'files': records,
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    totals = Counter()
    for record in records.values():
        totals[record['category']] += record['bytes']
    summary = {'file_count': len(records), 'total_bytes': sum(totals.values()),
               'bytes_by_category': dict(totals), 'runtime_distributions': len(package_records),
               'reference_case_count': len(reference), 'adapter_revision': selected['model']['adapter_revision'],
               'retrieval_method': active['retrieval_method'], 'external_paths_in_python_pth': False,
               'training_code_included': False, 'experiments_included': False}
    (output / 'bundle-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    print('Bundle created:', output, flush=True)


if __name__ == '__main__':
    main()

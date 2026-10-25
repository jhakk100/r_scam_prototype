"""Verify the copied runtime cannot import project or ML files outside this folder."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hash-all', action='store_true')
    args = parser.parse_args()
    assert Path(sys.executable).resolve().is_relative_to(HERE)
    assert all(Path(path).resolve().is_relative_to(HERE) for path in sys.path)
    manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    checked = 0
    for relative, row in manifest['files'].items():
        path = (HERE / relative).resolve()
        assert path.is_relative_to(HERE) and path.is_file() and not path.is_symlink(), relative
        assert path.stat().st_size == row['bytes'], relative
        if args.hash_all or row['category'] in ('inference_code', 'final_adapter', 'frozen_configuration', 'reference_dataset'):
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                    digest.update(chunk)
            assert digest.hexdigest() == row['sha256'], relative
            checked += 1
    for name in ('torch', 'transformers', 'peft', 'accelerate', 'bitsandbytes', 'sklearn', 'numpy', 'scipy'):
        module = importlib.import_module(name)
        assert Path(module.__file__).resolve().is_relative_to(HERE), name
    import server
    assert server.REPO == HERE / 'engine'
    assert len(server.points) == 226
    assert server.runtime['retrieval_method'] == 'D03_plain_text_tfidf_svd_xy'
    from model_training.artifacts import adapter_fingerprint
    assert adapter_fingerprint(HERE / 'engine/V4/model/final_adapter') == manifest['adapter_revision']
    # All application, standard-library and package imports must come from this folder.
    # These Torch registries use synthetic filenames; their implementations are
    # the real torch._ops and torch._classes modules, checked along with all others.
    outside = {name: module.__file__ for name, module in sys.modules.items()
               if name not in ('torch.ops', 'torch.classes')
               and getattr(module, '__file__', None) and not str(module.__file__).startswith('<')
               and not Path(module.__file__).resolve().is_relative_to(HERE)}
    assert not outside, outside
    report = {'status': 'PASSED', 'all_imports_inside_bundle': True,
              'files_checked': len(manifest['files']), 'hashes_checked': checked,
              'all_file_hashes_checked': args.hash_all, 'reference_cases': len(server.points),
              'adapter_revision': manifest['adapter_revision'], 'cuda_available': sys.modules['torch'].cuda.is_available()}
    (HERE / 'runtime').mkdir(exist_ok=True)
    (HERE / 'runtime/standalone-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()

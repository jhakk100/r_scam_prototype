"""Restore public Tesseract v6 assets omitted from the received deployment export."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

HERE = Path(__file__).resolve().parent
DEST = HERE / 'maeum-check-source/ocr'
ASSETS = {
    **{name: 'https://cdn.jsdelivr.net/npm/tesseract.js-core@6.0.0/' + name for name in (
        'tesseract-core-lstm.wasm.js', 'tesseract-core-lstm.wasm',
        'tesseract-core-simd-lstm.wasm.js', 'tesseract-core-simd-lstm.wasm')},
    **{lang + '.traineddata.gz': f'https://cdn.jsdelivr.net/npm/@tesseract.js-data/{lang}/4.0.0_best_int/{lang}.traineddata.gz'
       for lang in ('kor', 'eng')},
    'LICENSE.tesseract-js-core.txt': 'https://cdn.jsdelivr.net/npm/tesseract.js-core@6.0.0/LICENSE',
    'LICENSE.tesseract-js.txt': 'https://cdn.jsdelivr.net/npm/tesseract.js@6.0.1/LICENSE.md',
}


def download(item):
    name, url = item
    request = urllib.request.Request(url, headers={'User-Agent': 'MaeumCheck-local-integration/1.0'})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    (DEST / name).write_bytes(data)
    print(name, len(data), flush=True)
    return {'file': name, 'url': url, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


if __name__ == '__main__':
    DEST.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(download, ASSETS.items()))
    (HERE / 'ocr-assets.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')

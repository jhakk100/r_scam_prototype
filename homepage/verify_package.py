"""Smoke-test the repository package without loading another GPU model."""
import ast
import json
from pathlib import Path
import sys
import threading
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import server


def main():
    assert server.REPO == HERE.parent
    assert server.V4 == HERE.parent / 'V4'
    for path in HERE.glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'))
    examples = json.loads((HERE / 'examples.json').read_text(encoding='utf-8'))
    assert len(examples) == 2
    for row in examples:
        server.validate_messages({'messages': row['messages']})
    http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for path in ('', 'app.js', 'input.js', 'style.css', 'favicon.svg',
                     'images/chat-companions.png', 'ocr/worker.min.js',
                     '_next/static/chunks/src-DXZWLGLI.js',
                     '_next/static/chunks/rolldown-runtime-C5USp2td.js',
                     'api/status', 'api/examples'):
            with client.open(f'http://127.0.0.1:{http.server_port}/{path}', timeout=5) as result:
                assert result.status == 200, path
                blob = result.read()
                if path == 'api/status':
                    assert json.loads(blob)['mode'] == 'final_v4'
                if path == 'api/examples':
                    assert len(json.loads(blob)) == 2
    finally:
        http.shutdown()
        http.server_close()
        worker.join(timeout=5)
    assert server.pipeline is None
    print('PASSED: repository paths, independent examples, UI assets and HTTP API; no GPU model loaded')


if __name__ == '__main__':
    main()

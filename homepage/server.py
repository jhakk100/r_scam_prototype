"""Serve the team's Maeum Check UI with the frozen, local final V4 pipeline."""
import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from urllib.parse import unquote, urlsplit
import uuid

HERE = Path(__file__).resolve().parent
REPO = HERE.parent if (HERE.parent / 'V4/active_runtime.json').is_file() else HERE.parent / 'r_scam_prototype'
V4 = REPO / 'V4'
STATIC = HERE / 'app'
ORIGINAL = HERE / 'maeum-check-source'
sys.path[:0] = [str(V4), str(REPO)]
from common import read
from architecture.pipeline.input import prepare_input
from pipeline import V4Pipeline

APP_ID = 'maeum-check-final-v4'
runtime = read(V4 / 'active_runtime.json')
selection = read(V4 / 'final-selection.json')
index_data = read(runtime['index'])
points = {p['id']: p for p in read(V4 / 'map/dataset-3d.json')['points']}
known = {prepare_input(r['messages']).sha256: r for r in
         read(V4 / 'experiments/d03-final-paired-20261006_205128/test-inputs.json')}
pipeline = None
model_lock = threading.Lock()
state_lock = threading.Lock()
slot = threading.BoundedSemaphore(1)
jobs = {}
state = {'state': 'idle', 'detail': '분석을 시작하면 최종 모델을 준비합니다.'}


def set_state(**values):
    with state_lock:
        state.update(values)


def load_model():
    global pipeline
    with model_lock:
        if pipeline is not None:
            return pipeline
        set_state(state='loading', detail='최종 특화 모델을 준비하고 있습니다. 첫 실행은 시간이 걸립니다.')
        try:
            pipeline = V4Pipeline.load(V4 / 'active_runtime.json')
            set_state(state='ready', detail='최종 특화 모델과 D03 유사 사례 검색이 준비되었습니다.')
            return pipeline
        except Exception:
            set_state(state='error', detail='모델 준비에 실패했습니다. runtime/server.stderr.log를 확인해 주세요.')
            traceback.print_exc()
            raise


def validate_messages(value):
    if not isinstance(value, dict):
        raise ValueError('JSON 객체를 보내 주세요.')
    messages = value.get('messages')
    if not isinstance(messages, list) or not 1 <= len(messages) <= 96:
        raise ValueError('발화는 1~96개까지 입력해 주세요.')
    for m in messages:
        if (not isinstance(m, dict) or set(m) != {'speaker', 'text'}
                or not isinstance(m['speaker'], str) or not m['speaker'].strip()
                or len(m['speaker']) > 40 or not isinstance(m['text'], str)
                or not m['text'].strip()):
            raise ValueError('각 발화의 화자와 대화 내용을 확인해 주세요.')
    if sum(len(m['text']) for m in messages) > 12000:
        raise ValueError('대화는 12,000자 이내로 입력해 주세요. 자동으로 자르지 않습니다.')
    prepare_input(messages)
    return messages


def present(result, elapsed):
    """Expose measured values; never manufacture eight category contributions."""
    neighbors = []
    for hit in result['rag']['selected']:
        neighbors.append({**hit, 'messages': points[hit['conversation_id']]['messages']})
    return {
        'mode': 'final_v4', 'model_variant': runtime['model_variant'],
        'retrieval_method': runtime['retrieval_method'],
        'adapter_revision': selection['model']['adapter_revision'],
        'input_sha256': result['input_sha256'],
        'model': result['model'], 'final': result['final'],
        'model_score': 50 * (1 + result['model']['model_margin']),
        'rag_score': 50 * (1 + result['rag']['R']),
        'coordinate': result['coordinate'],
        'retrieval': {k: v for k, v in result['retrieval'].items() if k != 'selected'},
        'neighbors': neighbors,
        'seconds': round(elapsed, 2),
        'is_probability': False,
    }


def run_job(ident, messages):
    started = time.monotonic()
    try:
        pipe = load_model()
        with state_lock:
            jobs[ident].update(state='running', detail='최종 모델과 유사 사례 검색으로 실제 분석 중입니다.')
        # Preserve the exclusion rules of the final evaluation for known inputs.
        match = known.get(prepare_input(messages).sha256)
        with model_lock:
            result = pipe.analyze(messages,
                query_id=match['conversation_id'] if match else None,
                query_group=match['case_group_id'] if match else None)
        data = present(result, time.monotonic() - started)
        with state_lock:
            jobs[ident].update(state='done', result=data)
    except Exception as exc:
        traceback.print_exc()
        from architecture.pipeline.errors import InputError
        detail = str(exc) if isinstance(exc, (InputError, ValueError)) else '분석에 실패했습니다. 서버 로그를 확인해 주세요.'
        with state_lock:
            jobs[ident].update(state='error', detail=detail)
    finally:
        slot.release()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        blob = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_blob(blob, 'application/json; charset=utf-8', status)

    def send_blob(self, blob, content_type, status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(blob)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        try:
            self.wfile.write(blob)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def valid_host(self):
        return self.headers.get('Host') in {
            f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.valid_host():
            return self.send_json({'error': '허용되지 않은 호스트입니다.'}, 403)
        path = unquote(urlsplit(self.path).path)
        if path in ('/api/status', '/api/config'):
            with state_lock:
                status = dict(state)
            return self.send_json({**status, 'app': APP_ID, 'mode': 'final_v4',
                'model_variant': runtime['model_variant'],
                'retrieval_method': runtime['retrieval_method'],
                'adapter_revision': selection['model']['adapter_revision'],
                'case_counts': dict(Counter(e['label'] for e in index_data['entries'])),
                'k_retrieve': 8, 'k_max': 5, 'stores_conversations': False,
                'ocr_available': all((ORIGINAL / 'ocr' / name).is_file() for name in
                    ('worker.min.js', 'tesseract-core-lstm.wasm.js', 'tesseract-core-lstm.wasm',
                     'kor.traineddata.gz', 'eng.traineddata.gz'))})
        if path.startswith('/api/jobs/'):
            with state_lock:
                data = jobs.get(path.rsplit('/', 1)[-1])
            return self.send_json(data or {'error': '분석 요청을 찾을 수 없습니다.'}, 200 if data else 404)
        if path == '/api/examples':
            examples = read(HERE / 'examples.json')
            return self.send_json([{'title': e['title'], 'messages': e['messages']} for e in examples[:2]])
        # Explicitly allow public UI assets only, excluding models and runtime files.
        if path in ('/', '/index.html', '/app.js', '/input.js', '/style.css'):
            target = STATIC / ('index.html' if path == '/' else path[1:])
        elif path.startswith(('/images/', '/ocr/', '/_next/static/')) or path == '/favicon.svg':
            target = (ORIGINAL / path[1:]).resolve()
            if not target.is_relative_to(ORIGINAL.resolve()):
                return self.send_json({'error': '찾을 수 없습니다.'}, 404)
        else:
            return self.send_json({'error': '찾을 수 없습니다.'}, 404)
        if not target.is_file():
            return self.send_json({'error': '파일을 찾을 수 없습니다.'}, 404)
        mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if target.suffix == '.js':
            mime = 'text/javascript; charset=utf-8'
        elif target.suffix in ('.html', '.css'):
            mime += '; charset=utf-8'
        elif target.suffix == '.wasm':
            mime = 'application/wasm'
        self.send_blob(target.read_bytes(), mime)

    def do_POST(self):
        if not self.valid_host():
            return self.send_json({'error': '허용되지 않은 호스트입니다.'}, 403)
        if self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host', '')):
            return self.send_json({'error': '이 홈페이지에서만 분석할 수 있습니다.'}, 403)
        if urlsplit(self.path).path != '/api/analyze':
            return self.send_json({'error': '찾을 수 없습니다.'}, 404)
        try:
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('JSON 형식으로 보내 주세요.')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 100000:
                raise ValueError('입력 크기를 확인해 주세요.')
            self.connection.settimeout(15)
            value = json.loads(self.rfile.read(length))
            messages = validate_messages(value)
        except (ValueError, TypeError, OSError) as exc:
            return self.send_json({'error': str(exc)}, 400)
        if not slot.acquire(blocking=False):
            return self.send_json({'error': '이전 분석이 끝난 뒤 다시 시도해 주세요.'}, 409)
        ident = uuid.uuid4().hex
        with state_lock:
            # Completed inputs/results live only in RAM, for at most 15 minutes.
            now = time.time()
            for key in list(jobs):
                if jobs[key]['created'] < now - 900 or len(jobs) >= 20:
                    del jobs[key]
            jobs[ident] = {'state': 'loading', 'detail': '최종 모델을 확인하고 있습니다.', 'created': now}
        threading.Thread(target=run_job, args=(ident, messages), daemon=True).start()
        return self.send_json({'job': ident}, 202)

    def log_message(self, *_args):
        pass  # Never log conversation bodies or returned results.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--preload', action='store_true')
    args = parser.parse_args()
    folder = HERE / 'runtime'
    folder.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    # Reap expired results even when no new analysis is submitted.
    def cleanup():
        while True:
            time.sleep(30)
            with state_lock:
                for key in list(jobs):
                    if jobs[key]['state'] in ('done', 'error') and jobs[key]['created'] < time.time() - 900:
                        del jobs[key]
    threading.Thread(target=cleanup, daemon=True).start()
    info = {'app': APP_ID, 'url': f'http://127.0.0.1:{server.server_port}/', 'pid': os.getpid()}
    (folder / 'server.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    print(info['url'], flush=True)
    if args.preload:
        def preload():
            try:
                load_model()
            except Exception:
                pass
        threading.Thread(target=preload, daemon=True).start()
    server.serve_forever()


if __name__ == '__main__':
    main()

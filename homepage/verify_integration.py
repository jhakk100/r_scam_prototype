"""Exercise the real local HTTP API and selected GPU model, without recording inputs."""
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
BASE = json.loads((HERE / 'runtime/server.json').read_text())['url']
client = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, value=None, headers=None):
    body = json.dumps(value, ensure_ascii=False).encode('utf-8') if value is not None else None
    req = urllib.request.Request(BASE + path, data=body,
        headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with client.open(req, timeout=15) as response:
            blob = response.read()
            return response.status, json.loads(blob) if path.startswith('api/') else blob, response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read()), exc.headers


def main():
    report = {'checks': [], 'inferences': []}
    code, status, _ = request('api/status')
    assert code == 200 and status['app'] == 'maeum-check-final-v4'
    assert status['retrieval_method'] == 'D03_plain_text_tfidf_svd_xy'
    assert status['case_counts'] == {'SCAM': 113, 'NON_SCAM': 113}
    assert status['ocr_available'] and status['stores_conversations'] is False
    report['checks'].append('final_model_and_d03_config')
    for path in ('', 'app.js', 'input.js', 'style.css', 'images/chat-companions.png',
                 'ocr/kor.traineddata.gz', 'ocr/eng.traineddata.gz',
                 'ocr/tesseract-core-lstm.wasm.js', 'ocr/tesseract-core-simd-lstm.wasm.js'):
        assert request(path)[0] == 200, path
    assert request('ocr/tesseract-core-lstm.wasm')[2]['Content-Type'] == 'application/wasm'
    report['checks'].append('ui_and_local_korean_ocr_assets')
    for path in ('server.py', 'runtime/server.json', '../server.py', '%2e%2e/server.py',
                 '_next/static/../../../server.py', 'api/jobs/unknown'):
        assert request(path)[0] == 404, path
    report['checks'].append('private_files_not_served')
    for value in ([], {}, {'messages': []}, {'messages': [{'speaker': '', 'text': 'test'}]},
                  {'messages': [{'speaker':'A', 'text': 3}]},
                  {'messages': [{'speaker':'A', 'text': 'x'*12001}]},
                  {'messages':[{'speaker':'A','text':'ok','label':'SCAM'}]}):
        assert request('api/analyze', value)[0] == 400, value
    assert request('api/analyze', {'messages':[{'speaker':'A','text':'hello'}]},
                   {'Origin':'https://unrelated.invalid'})[0] == 403
    report['checks'].append('input_limits_and_origin_validation')
    examples = json.loads((HERE / 'examples.json').read_text(encoding='utf-8'))
    # Two retained evaluation cases plus a freshly composed conversation.
    scenarios = [(e['id'], e['messages'], e) for e in examples[:2]]
    scenarios.append(('fresh_conversation', [
        {'speaker':'상대방', 'text':'오늘은 퇴근이 조금 늦었네요. 주말에 함께 산책할까요?'},
        {'speaker':'나', 'text':'좋아요. 토요일 오후에 만나요.'},
        {'speaker':'상대방', 'text':'역 앞 카페에서 만나서 천천히 걸어요. 비용은 각자 내면 되겠네요.'},
        {'speaker':'나', 'text':'네, 알겠어요. 편안한 저녁 보내세요.'}], None))
    for label, messages, expected in scenarios:
        code, result, _ = request('api/analyze', {'messages': messages})
        assert code == 202, result
        if not report['inferences']:
            assert request('api/analyze', {'messages': messages})[0] == 409
            report['checks'].append('concurrent_request_rejected')
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            code, job, _ = request('api/jobs/' + result['job'])
            assert code == 200
            if job['state'] in ('done', 'error'):
                break
            time.sleep(1)
        assert job['state'] == 'done', job
        data = job['result']
        normalized = json.dumps([{'speaker': m['speaker'], 'text': m['text']} for m in messages],
                                ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        assert data['input_sha256'] == hashlib.sha256(normalized).hexdigest()
        assert data['mode'] == 'final_v4' and data['is_probability'] is False
        assert 0 <= data['final']['risk_score'] <= 100
        assert len(data['neighbors']) <= 5 and len(data['retrieval']['candidates']) == 8
        assert len({hit['case_group_id'] for hit in data['neighbors']}) == len(data['neighbors'])
        assert all(hit['messages'] for hit in data['neighbors'])
        assert data['retrieval']['query_label_used'] is False
        assert data['retrieval']['query_z_used_for_search'] is False
        assert 'score_breakdown' not in data and 'analysis_confidence' not in data
        f = data['final']; m = data['model']['model_margin']; r = data['rag_score']/50-1
        risk = 50*(1+(1-f['rag_share'])*m*(1-.35*f['distance_quality'])+f['rag_share']*r)
        assert abs(risk-f['risk_score']) < 1e-9
        row = {'case':label, 'model_score':data['model_score'], 'rag_score':data['rag_score'],
               'final_score':f['risk_score'], 'level':f['level'], 'seconds':data['seconds'],
               'neighbors':len(data['neighbors']), 'input_sha256':data['input_sha256']}
        if expected:
            row['saved_reference_delta'] = abs(f['risk_score']-expected['final']['risk_score'])
            assert row['saved_reference_delta'] < 0.05, row
            assert [hit['conversation_id'] for hit in data['neighbors']] == [hit['id'] for hit in expected['neighbors']]
        report['inferences'].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    report['checks'].extend(['real_gpu_inference', 'known_case_parity', 'fresh_input_inference',
        'exact_input_hash', 'final_formula_parity', 'neighbor_text_and_group_deduplication'])
    report['status'] = 'PASSED'
    (HERE / 'runtime/integration-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASSED', flush=True)


if __name__ == '__main__':
    main()

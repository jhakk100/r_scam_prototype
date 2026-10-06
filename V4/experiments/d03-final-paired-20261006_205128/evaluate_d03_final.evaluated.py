"""Fresh paired E2B/V3 evaluation on the user-selected frozen D03 RAG."""
import sys, json, math, statistics, argparse, hashlib, shutil
from pathlib import Path
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pipeline import V4Pipeline
from common import read, sha
from d03_retrieval import D03Index
from core import rag_evidence
from fusion import classify, combine
from evaluate_intervention import save, transitions
from evaluate_final_challenge import measure
from architecture.pipeline.input import prepare_input
import numpy as np

LATEST = HERE / 'd03-final-latest.json'
MODES = ('model_only', 'combined', 'rag_only')


def prepare():
    old = read(HERE / 'active_runtime.json')
    source = Path(read(HERE / 'xy-latest.json')['experiment'])
    out = HERE / 'experiments' / ('d03-final-paired-' + datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True, exist_ok=False)
    root = out / 'runtime'; root.mkdir()
    profile = read(source / 'plain-text-axis-profiles.json')['D03']
    entries = read(source / 'D03-train-map.json')['entries']
    original = read(old['balanced_test'])
    variant = read(HERE / 'datasets/variant-test-20261006-closeout/binary-test.json')
    rows = [{**r, 'test_set': s} for s, rs in [('original', original), ('variant', variant)] for r in rs]
    train = [json.loads(s) for s in (Path(old['dataset']) / 'train_3d.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    train_by_id = {r['conversation_id']: r for r in train}
    assert Counter(e['label'] for e in entries) == {'SCAM': 113, 'NON_SCAM': 113}
    assert Counter(r['label'] for r in original) == {'SCAM': 88, 'NON_SCAM': 88}
    assert Counter(r['label'] for r in variant) == {'SCAM': 40, 'NON_SCAM': 40}
    assert len({r['conversation_id'] for r in rows}) == 256
    for e in entries:
        assert e['verified'] and e['split'] == 'train' and e['conversation_id'] in train_by_id
        assert e['input_sha256'] == prepare_input(train_by_id[e['conversation_id']]['messages']).sha256
    for key in ('conversation_id', 'case_group_id'):
        assert not {r[key] for r in rows} & {r[key] for r in train}
    parents = {i for r in variant for i in r['source_conversation_ids']}
    parent_groups = {i for r in variant for i in r['source_case_group_ids']}
    assert not parents & set(train_by_id)
    assert not parent_groups & {r['case_group_id'] for r in train}
    assert not {prepare_input(r['messages']).sha256 for r in rows} & {prepare_input(r['messages']).sha256 for r in train}
    # Freeze the selected fitted artifacts; no fitting or threshold selection on test.
    save(root / 'xy-profile.json', profile)
    compact = [{k: e[k] for k in ('conversation_id', 'case_group_id', 'input_sha256', 'label', 'xyz', 'verified', 'split')} for e in entries]
    save(root / 'rag_index.json', {'entries': compact, 'profile_sha256': sha(root / 'xy-profile.json'),
        'method': 'D03_plain_text_tfidf_svd_xy', 'fit_labels_used': False, 'query_z_used': False})
    config = {'k_retrieve': 8, 'k_max': 5, 'distance_cutoff': profile['cutoff'],
        'search_dimensions': 2, 'distance': 'euclidean_xy_div_sqrt2', 'topic_filter': False,
        'fit_count': 226, 'fit_labels_used': False, 'selection_basis': 'user-selected D03 after exploratory comparisons'}
    save(root / 'retrieval-config.json', config)
    save(root / 'fusion-config.json', read(old['fusion_config']))
    save(out / 'test-inputs.json', rows)
    for name, runtime in [('original', read(HERE / 'runtime/original-runtime.json')), ('specialized', old)]:
        runtime = {**runtime, 'experiment': str(out), 'index': str(root / 'rag_index.json'),
            'xy_profile': str(root / 'xy-profile.json'), 'retrieval_config': str(root / 'retrieval-config.json'),
            'fusion_config': str(root / 'fusion-config.json'), 'retrieval_method': 'D03_plain_text_tfidf_svd_xy',
            'rag_policy_status': 'USER_SELECTED_FINAL_EXPLORATORY', 'temporary': name == 'original',
            'selection_basis': 'User selected D03 RAG; preserved V3 model and provisional fusion coefficients'}
        save(root / (name + '-runtime.json'), runtime)
    index = D03Index(profile, compact, config)
    max_train_delta = max(float(np.max(np.abs(index.transform(train_by_id[e['conversation_id']]['messages']) - np.asarray(e['xyz'][:2])))) for e in entries)
    assert max_train_delta < 1e-10
    previous = {r['id']: r for r in read(source / 'D03-predictions.json')}
    max_query_delta = max_distance_delta = 0.
    rag_rows = []
    policy = read(root / 'fusion-config.json')
    for r in rows:
        ident = r['conversation_id']; prepared = prepare_input(r['messages'])
        xy, hits = index.search(r['messages'], ident, r['case_group_id'], prepared.sha256)
        ref = previous[ident]
        max_query_delta = max(max_query_delta, float(np.max(np.abs(np.asarray(xy) - ref['xy']))))
        assert [h['conversation_id'] for h in hits['selected']] == [h['conversation_id'] for h in ref['selected']]
        max_distance_delta = max(max_distance_delta, max(abs(h['distance'] - j['distance']) for h, j in zip(hits['selected'], ref['selected'])))
        evidence = rag_evidence(hits['selected'], config['distance_cutoff'])
        rr = 50 * (1 + evidence['R'])
        assert abs(rr - ref['variants']['rag_only']['risk_score']) < 1e-8
        rag_rows.append({'id': ident, 'label': r['label'], 'test_set': r['test_set'],
            'input_sha256': prepared.sha256, 'xy': xy, 'selected': hits['selected'], 'R': evidence['R'],
            'variants': {'rag_only': {'risk_score': rr, 'level': classify(rr)}}})
    assert max_query_delta < 1e-10 and max_distance_delta < 1e-10
    save(out / 'rag-predictions.json', rag_rows)
    protected_paths = [HERE / 'active_runtime.json', Path(old['index']), Path(old['retrieval_config']),
        Path(old['projection']), Path(old['inference_config']), HERE / 'fusion-config.json',
        HERE.parent / 'V3/doc/paper/romance_scam_technical_v3_ko.docx',
        HERE.parent / 'r_scam_prototype/doc/paper/romance_scam_technical_draft_ko.docx',
        Path(old['model_run']) / 'final_adapter/adapter_model.safetensors']
    protocol = {'status': 'PREPARED', 'selected_rag': 'D03', 'source': str(source), 'fusion': policy,
        'test_counts': {'original': 176, 'variant': 80}, 'rag_counts': {'SCAM': 113, 'NON_SCAM': 113},
        'fresh_inference_for_both_models': True, 'same_model_input_format': 'original dialogue plus fixed label-free V3_CONTEXT',
        'retrieved_text_supplied_to_llm': False, 'fit_train_only': True, 'fit_labels_used': False,
        'query_label_or_z_used': False, 'new_training': False, 'threshold_tuning': False,
        'test_used_in_previous_exploration': True, 'independent_validation': False,
        'variant_labels_provisional': True, 'variant_parent_correlated': True,
        'verification': {'max_train_xy_delta': max_train_delta, 'max_query_xy_delta': max_query_delta,
            'max_neighbor_distance_delta': max_distance_delta, 'all_256_previous_neighbors_matched': True,
            'all_training_and_rag_test_ID_group_hash_disjoint': True, 'variant_parent_groups_excluded': True},
        'protected_sha256': {str(p): sha(p) for p in protected_paths},
        'frozen_sha256': {str(p): sha(p) for p in root.glob('*.json')},
        'source_sha256': {str(p): sha(p) for p in (Path(__file__), HERE / 'pipeline.py', HERE / 'd03_retrieval.py', HERE / 'fusion.py')}}
    save(out / 'protocol.before-evaluation.json', protocol)
    for p in (Path(__file__), HERE / 'pipeline.py', HERE / 'd03_retrieval.py', HERE / 'fusion.py'):
        shutil.copyfile(p, out / (p.stem + '.evaluated.py'))
    save(LATEST, {'status': 'PREPARED', 'experiment': str(out)})
    print('PREPARED ' + str(out), flush=True)
    print(json.dumps(protocol['verification']), flush=True)


def score(name):
    out = Path(read(LATEST)['experiment'])
    protocol = read(out / 'protocol.before-evaluation.json')
    for p, h in protocol['frozen_sha256'].items():
        assert sha(p) == h
    save(LATEST, {'status': 'RUNNING_' + name.upper(), 'experiment': str(out)})
    pipeline = V4Pipeline.load(out / 'runtime' / (name + '-runtime.json'))
    has_adapter = hasattr(pipeline.base.model.model, 'peft_config')
    assert has_adapter == (name == 'specialized')
    reference = {r['id']: r for r in read(out / 'rag-predictions.json')}
    rows = read(out / 'test-inputs.json'); predictions = []
    for i, row in enumerate(rows, 1):
        result = pipeline.analyze(row['messages'], row['conversation_id'], row['case_group_id'])
        ref = reference[row['conversation_id']]
        assert result['input_sha256'] == ref['input_sha256']
        assert [h['conversation_id'] for h in result['retrieval']['selected']] == [h['conversation_id'] for h in ref['selected']]
        assert abs(result['rag']['R'] - ref['R']) < 1e-10
        assert len(result['retrieval']['selected']) <= 5
        assert not result['retrieval']['query_label_used'] and not result['retrieval']['query_z_used_for_search']
        assert not result['v4']['retrieved_text_supplied_to_llm']
        mr = 50 * (1 + result['model']['model_margin']); rr = 50 * (1 + result['rag']['R'])
        result.update(label=row['label'], test_set=row['test_set'], case_group_id=row['case_group_id'],
            label_verified=row.get('verified', False), challenge_type=row.get('challenge_type'),
            variants={'model_only': {'risk_score': mr, 'level': classify(mr)},
                'rag_only': {'risk_score': rr, 'level': classify(rr)}, 'combined': result['final']})
        predictions.append(result)
        if i % 10 == 0 or i == len(rows):
            save(out / (name + '-predictions.partial.json'), predictions)
            print(f'{name.upper()} {i}/{len(rows)}', flush=True)
    save(out / (name + '-predictions.json'), predictions)
    results = {s: {m: measure(rs, m) for m in MODES} for s, rs in
        [('original', predictions[:176]), ('variant', predictions[176:]), ('all', predictions)]}
    summary = {'status': 'COMPLETED', 'model_identity': pipeline.base.model.identity,
        'adapter_loaded': has_adapter, 'results': results,
        'transitions': {s: transitions(rs, 'model_only', 'combined') for s, rs in
            [('original', predictions[:176]), ('variant', predictions[176:]), ('all', predictions)]},
        'mean_rag_share': statistics.fmean(r['final']['rag_share'] for r in predictions),
        'mean_distance_quality': statistics.fmean(r['final']['distance_quality'] for r in predictions),
        'mean_rag_share_by_set': {s: statistics.fmean(r['final']['rag_share'] for r in predictions if r['test_set'] == s) for s in ('original', 'variant')},
        'model_extreme_count': sum(r['variants']['model_only']['risk_score'] <= 1 or r['variants']['model_only']['risk_score'] >= 99 for r in predictions),
        'fresh_inference': True, 'input_errors': 0}
    save(out / (name + '-summary.json'), summary)
    print(json.dumps({'model': name, 'results': results, 'transitions': summary['transitions']}, ensure_ascii=False), flush=True)


def finalize():
    out = Path(read(LATEST)['experiment']); protocol = read(out / 'protocol.before-evaluation.json')
    models = {s: read(out / (s + '-summary.json')) for s in ('original', 'specialized')}
    predictions = {s: read(out / (s + '-predictions.json')) for s in models}
    for p, h in {**protocol['protected_sha256'], **protocol['frozen_sha256']}.items():
        assert sha(p) == h
    max_delta = 0.
    for a, b in zip(predictions['original'], predictions['specialized']):
        assert a['id'] == b['id'] and a['model_input_sha256'] == b['model_input_sha256']
        assert a['retrieval'] == b['retrieval'] and a['rag'] == b['rag']
        for r in (a, b):
            ds = [h['distance'] for h in r['retrieval']['selected']]
            q = math.fsum(max(0., 1-d/(read(out / 'runtime/retrieval-config.json')['distance_cutoff']*8)) for d in ds)/len(ds)
            w = min(.7, q); effective = r['model']['model_margin'] * (1-.35*q)
            risk = 50*(1+(1-w)*effective+w*r['rag']['R'])
            max_delta = max(max_delta, abs(risk-r['final']['risk_score']))
    assert max_delta < 1e-10
    summary = {'status': 'COMPLETED_USER_SELECTED_D03', 'models': models, 'fusion': protocol['fusion'],
        'paired_inputs_and_search_identical': True, 'max_independent_formula_delta': max_delta,
        'test_counts': protocol['test_counts'], 'rag_counts': protocol['rag_counts'],
        'no_test_or_variant_parent_in_train_or_rag': True, 'query_label_used': False,
        'independent_validation': False, 'variant_labels_provisional': True, 'paper_changed': False}
    save(out / 'summary.json', summary)
    names = [('원본 E2B 단독', 'original', 'model_only'), ('원본 E2B + D03 RAG', 'original', 'combined'),
        ('V3 특화 LLM 단독', 'specialized', 'model_only'), ('V3 특화 LLM + D03 RAG', 'specialized', 'combined'),
        ('D03 RAG 단독', 'specialized', 'rag_only')]
    report = '# 최종 D03 RAG: 원본 E2B와 V3 특화 모델 비교\n\n'
    report += '두 모델 모두 256건을 입력부터 새로 추론했다. 같은 대화 원문과 라벨 없는 V3_CONTEXT를 사용했다. 검색 사례 텍스트를 LLM에 전달하지 않고, 별도 RAG 점수와 수식으로 결합했다. 재학습이나 임계값 탐색은 하지 않았다.\n\n'
    report += '| 구성 | 원본 테스트 176건 | 변형 테스트 80건 | 합산 256건 |\n|---|---:|---:|---:|\n'
    for title, model, mode in names:
        report += '| ' + title + ' | ' + ' | '.join(f"{models[model]['results'][s][mode]['accuracy']:.2%} ({models[model]['results'][s][mode]['correct']}/{models[model]['results'][s][mode]['count']})" for s in ('original', 'variant', 'all')) + ' |\n'
    report += '\nRAG는 verified train 226건(SCAM/NON-SCAM 113:113)이다. 원문 문자 2~4gram TF-IDF와 SVD 2축은 train에서만 적합된 D03 파일을 동결 사용했다. X·Y 거리로 전체 RAG에서 후보 8건을 찾고 그룹 중복을 제거해 최대 5건을 참조한다. 저장 라벨/Z는 이웃 투표에만 쓰며 새 입력의 정답은 검색에 사용하지 않는다.\n\n'
    report += '결합은 기존 임시 계수 유지: q=mean(max(0,1-d/(8c))), w=min(0.7,q), M_eff=M(1-0.35q), E=(1-w)M_eff+wR, risk=50(1+E). LOW<40, HIGH>60, 나머지는 UNKNOWN이다. 65%는 q=1일 때의 모델 마진 유지율이며 고정 65:35 비율이 아니다. UNKNOWN은 오답으로 집계했다.\n\n'
    report += '| 모델 | 원본 오류 교정 / 정답 손상 | 변형 오류 교정 / 정답 손상 | 평균 RAG 비중 |\n|---|---:|---:|---:|\n'
    for name, title in [('original', '원본 E2B'), ('specialized', 'V3 특화')]:
        v = models[name]; a, b = v['transitions']['original'], v['transitions']['variant']
        report += f"| {title} | {a['fixed_error']} / {a['correct_to_error']} | {b['fixed_error']} / {b['correct_to_error']} | {v['mean_rag_share']:.2%} |\n"
    report += '\n두 모델의 256건 입력 해시, 검색 이웃, 거리, RAG 값이 모두 같음을 확인했다. 과거 D03의 256건 검색 이웃/좌표와 배포 구현도 일치하며 결합식은 별도 계산으로 검증했다. 모델 가중치, 원본 데이터, V3 설정과 논문은 보존했다.\n\n'
    report += '이 테스트는 이미 D03 후보 선정에 사용한 데이터의 재평가이며 독립 검증이 아니다. 변형 80건은 생성자가 정한 미검증 라벨이고 같은 부모 사례에서 파생되어 상관된다. 원본 테스트 일부도 미검증 합성 라벨이다. 전체 ACC를 외부 실대화 일반화나 최적 수식의 증거로 확정하지 않는다.\n'
    (out / 'REPORT_KO.md').write_text(report, encoding='utf-8')
    # Activate only after both actual model evaluations and paired checks succeed.
    old = read(HERE / 'active_runtime.json')
    save(out / 'active-runtime.before-selection.json', old)
    active = read(out / 'runtime/specialized-runtime.json')
    active['final_rag_selection_date'] = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    save(HERE / 'active_runtime.json', active)
    save(HERE / 'rag-final-selection.json', {'status': 'FINAL_RAG_SELECTED_BY_USER', 'method': 'D03_plain_text_tfidf_svd_xy',
        'runtime': active, 'comparison': str(out), 'report': str(out / 'REPORT_KO.md'),
        'independent_validation': False, 'paper_changed': False})
    save(LATEST, {'status': 'COMPLETED_USER_SELECTED_D03', 'experiment': str(out),
        'report': str(out / 'REPORT_KO.md'), 'active_runtime': str(HERE / 'active_runtime.json')})
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--stage', choices=('prepare', 'original', 'specialized', 'finalize'), required=True)
    stage = parser.parse_args().stage
    if stage == 'prepare': prepare()
    elif stage == 'finalize': finalize()
    else: score(stage)

"""Verify retained data and score arithmetic without GPU inference."""
import sys,json,math,hashlib
from pathlib import Path
from collections import Counter
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from pipeline import V4Pipeline
from d03_retrieval import D03CasePipeline,D03Index
from common import read,sha
from evaluation_utils import measure,save
from architecture.pipeline.input import prepare_input

def main():
    selected=read(HERE/'final-selection.json');runtime=read(HERE/'active_runtime.json')
    assert runtime==selected['runtime']
    for key in ('inference_config','projection','index','retrieval_config','fusion_config','balanced_test','xy_profile'):
        assert Path(runtime[key]).is_file(),key
    assert Path(runtime['dataset']).is_dir()
    out=Path(selected['comparison']);summary=read(out/'summary.json');rows=read(out/'test-inputs.json')
    profile=read(runtime['xy_profile']);index=read(runtime['index']);config=read(runtime['retrieval_config'])
    assert index['profile_sha256']==sha(runtime['xy_profile'])
    assert Counter(e['label'] for e in index['entries'])=={'SCAM':113,'NON_SCAM':113}
    train=[json.loads(s) for s in (Path(runtime['dataset'])/'train_3d.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    for key in ('conversation_id','case_group_id'):
        assert not {r[key] for r in rows}&{r[key] for r in train}
    assert not {prepare_input(r['messages']).sha256 for r in rows}&{prepare_input(r['messages']).sha256 for r in train}
    parents={i for r in rows if r['test_set']=='variant' for i in r['source_conversation_ids']}
    groups={i for r in rows if r['test_set']=='variant' for i in r['source_case_group_ids']}
    assert not parents&{r['conversation_id'] for r in train}
    assert not groups&{r['case_group_id'] for r in train}
    replay_count=0;max_delta=0.
    for name in ('original','specialized'):
        preds=read(out/f'{name}-predictions.json')
        for subset,rs in [('original',preds[:176]),('variant',preds[176:]),('all',preds)]:
            for mode in ('model_only','rag_only','combined'):
                assert measure(rs,mode)==summary['models'][name]['results'][subset][mode]
        for row,ref in zip(rows,preds):
            xy,hits=D03Index(profile,index['entries'],config).search(row['messages'],row['conversation_id'],row['case_group_id'],prepare_input(row['messages']).sha256)
            assert [h['conversation_id'] for h in hits['selected']]==[h['conversation_id'] for h in ref['retrieval']['selected']]
            ds=[h['distance'] for h in hits['selected']]
            weights=[1/(d+1e-6) for d in ds]
            R=math.fsum(w*(1 if h['label']=='SCAM' else -1) for w,h in zip(weights,hits['selected']))/math.fsum(weights)
            policy=read(runtime['fusion_config']);q=math.fsum(max(0.,1-d/(config['distance_cutoff']*policy['distance_multiplier'])) for d in ds)/len(ds)
            w=min(policy['rag_cap'],q);M=ref['model']['model_margin']
            risk=50*(1+(1-w)*M*(1-(1-policy['model_attenuation'])*q)+w*R)
            max_delta=max(max_delta,abs(risk-ref['final']['risk_score']))
            assert abs(R-ref['rag']['R'])<1e-10 and abs(risk-ref['final']['risk_score'])<1e-10
            replay_count+=1
    # Check the public inference path using a measured score, without loading weights.
    ref=read(out/'specialized-predictions.json')[0];row=rows[0]
    class Scores:
        margin=ref['model']['model_margin']
        def to_dict(self):return {k:v for k,v in ref['model'].items() if k!='identity'}
    class Model:
        identity=ref['model']['identity']
        def score(self,text):
            assert hashlib.sha256(text.encode('utf-8')).hexdigest()==ref['model_input_sha256']
            return Scores()
    base=D03CasePipeline(Model(),profile,index['entries'],config,read(runtime['projection'])['rules'])
    live=V4Pipeline(base,read(runtime['fusion_config']),runtime).analyze_features(row['messages'],{'xyz':[99,-99,0]},[0]*384,row['conversation_id'],row['case_group_id'])
    assert abs(live['final']['risk_score']-ref['final']['risk_score'])<1e-10
    weights=Path(runtime['model_run'])/'final_adapter/adapter_model.safetensors'
    model_manifest=read(HERE/'model/manifest.json')
    actual_weight_hash=sha(weights) if weights.is_file() else None
    if actual_weight_hash:
        from model_training.artifacts import adapter_fingerprint
        assert actual_weight_hash==model_manifest['files_sha256']['adapter_model.safetensors']
        assert adapter_fingerprint(weights.parent)==selected['model']['adapter_revision']
    result={'status':'PASSED','retained_comparison_cases':replay_count,'max_formula_delta':max_delta,
        'reference_paths_exist':True,'train_test_and_variant_parent_exclusions':True,
        'rag_ratio':'113:113','final_k_max':5,'fresh_gpu_inference':False,
        'weights_present':weights.is_file(),'weights_sha256':actual_weight_hash,
        'expected_weights_sha256':model_manifest['files_sha256']['adapter_model.safetensors'],
        'sources_sha256':{p.name:sha(p) for p in HERE.glob('*.py')}}
    save(HERE/'runtime/release-verification.json',result);print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()

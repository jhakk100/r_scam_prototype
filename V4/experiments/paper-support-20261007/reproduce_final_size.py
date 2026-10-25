"""Frozen final retrieval size experiment; reuse measured LLM scores, never refit or train."""
import sys,json,random,statistics,math,hashlib
from pathlib import Path
from collections import Counter,defaultdict
HERE=Path(__file__).resolve().parent
V4=HERE.parents[1]
sys.path.insert(0,str(V4))
from common import read,sha
from d03_retrieval import D03Index
from core import rag_evidence
from fusion import combine,classify
from evaluation_utils import measure
from architecture.pipeline.input import prepare_input
SIZES=(22,56,114,170,226)
SEEDS=tuple(range(42,52))

def save(name,value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')

def order_topics(entries,seed):
    groups=defaultdict(list)
    for entry in entries:groups[entry['topic_id']].append(entry)
    rng=random.Random(seed)
    for topic in sorted(groups):
        groups[topic].sort(key=lambda e:e['conversation_id']);rng.shuffle(groups[topic])
    used=Counter();ordered=[]
    for step in range(1,len(entries)+1):
        available=[t for t in sorted(groups) if used[t]<len(groups[t])]
        topic=min(available,key=lambda t:(-(step*len(groups[t])/len(entries)-used[t]),t))
        ordered.append(groups[topic][used[topic]]);used[topic]+=1
    return ordered

def run():
    runtime=read(V4/'active_runtime.json');selection=read(V4/'final-selection.json')
    baseline=Path(selection['comparison'])
    profile=read(runtime['xy_profile']);config=read(runtime['retrieval_config']);policy=read(runtime['fusion_config'])
    original_entries=read(runtime['index'])['entries']
    training=[json.loads(s) for s in (Path(runtime['dataset'])/'train_3d.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    topics={r['conversation_id']:r['representation']['topic_id'] for r in training}
    entries=[{**e,'topic_id':topics[e['conversation_id']]} for e in original_entries]
    rows=read(baseline/'test-inputs.json')
    predictions={name:{r['id']:r for r in read(baseline/(name+'-predictions.json'))} for name in ('original','specialized')}
    assert Counter(e['label'] for e in entries)=={'SCAM':113,'NON_SCAM':113}
    assert all(e['split']=='train' and e['verified'] for e in entries)
    assert all(not {r[key] for r in rows}&{e[key] for e in entries} for key in ('conversation_id','case_group_id'))
    assert not {prepare_input(r['messages']).sha256 for r in rows}&{e['input_sha256'] for e in entries}
    assert config['k_retrieve']==8 and config['k_max']==5
    assert len(rows)==256 and Counter(r['label'] for r in rows[:176])=={'SCAM':88,'NON_SCAM':88}
    protected=[V4/'active_runtime.json',V4/'final-selection.json',Path(runtime['xy_profile']),Path(runtime['index']),Path(runtime['retrieval_config']),Path(runtime['fusion_config'])]
    before={str(p):sha(p) for p in protected}
    full_index=D03Index(profile,entries,config)
    coordinates={r['conversation_id']:full_index.transform(r['messages']) for r in rows}
    hashes={r['conversation_id']:prepare_input(r['messages']).sha256 for r in rows}
    runs=[]
    for seed in SEEDS:
        scam=order_topics([e for e in entries if e['label']=='SCAM'],seed)
        normal=order_topics([e for e in entries if e['label']=='NON_SCAM'],seed+100000)
        previous=set()
        for size in SIZES:
            subset=[entry for pair in zip(scam[:size//2],normal[:size//2]) for entry in pair]
            ids={e['conversation_id'] for e in subset}
            assert previous<=ids;previous=ids
            assert Counter(e['label'] for e in subset)=={'SCAM':size//2,'NON_SCAM':size//2}
            results=[]
            for row in rows:
                ident=row['conversation_id'];xy=coordinates[ident]
                candidates=[]
                for e in subset:
                    if e['conversation_id']==ident or e['case_group_id']==row['case_group_id'] or e['input_sha256']==hashes[ident]:continue
                    candidates.append({k:e[k] for k in ('conversation_id','case_group_id','label','xyz')})
                    candidates[-1]['distance']=math.dist(e['xyz'][:2],xy)/math.sqrt(2)
                candidates.sort(key=lambda h:(h['distance'],h['conversation_id']))
                selected=[];groups=set()
                for h in candidates[:8]:
                    if h['case_group_id'] in groups:continue
                    selected.append(h);groups.add(h['case_group_id'])
                    if len(selected)==5:break
                evidence=rag_evidence(selected,config['distance_cutoff'])
                distances=[h['distance'] for h in selected]
                variants={'rag_only':{'risk_score':50*(1+evidence['R']),'level':classify(50*(1+evidence['R']))}}
                for name in predictions:
                    variants[name+'_combined']=combine(predictions[name][ident]['model']['model_margin'],evidence['R'],distances,config['distance_cutoff'],policy)
                if size==226:
                    ref=predictions['specialized'][ident]
                    assert [h['conversation_id'] for h in selected]==[h['conversation_id'] for h in ref['retrieval']['selected']]
                    assert abs(variants['specialized_combined']['risk_score']-ref['final']['risk_score'])<1e-10
                results.append({'id':ident,'label':row['label'],'test_set':row['test_set'],'variants':variants})
            runs.append({'seed':seed,'rag_size':size,'class_counts':dict(Counter(e['label'] for e in subset)),
                'subset_ids':sorted(ids),'metrics':{s:{m:measure(rs,m) for m in ('rag_only','original_combined','specialized_combined')}
                for s,rs in [('original',results[:176]),('variant',results[176:]),('all',results)]}})
    curves=[]
    for size in SIZES:
        group=[r for r in runs if r['rag_size']==size]
        curves.append({'rag_size':size,'per_class':size//2,'metrics':{s:{m:{
            'mean':statistics.fmean(r['metrics'][s][m]['accuracy'] for r in group),
            'min':min(r['metrics'][s][m]['accuracy'] for r in group),
            'max':max(r['metrics'][s][m]['accuracy'] for r in group)}
            for m in ('rag_only','original_combined','specialized_combined')} for s in ('original','variant','all')}})
    trends={}
    for s in ('original','variant','all'):
        means=[c['metrics'][s]['rag_only']['mean'] for c in curves]
        individual=[]
        for seed in SEEDS:
            acc=[r['metrics'][s]['rag_only']['accuracy'] for r in runs if r['seed']==seed]
            individual.append(all(a<=b+1e-12 for a,b in zip(acc,acc[1:])))
        trends[s]={'mean_nondecreasing':all(a<=b+1e-12 for a,b in zip(means,means[1:])),
            'individual_nondecreasing_seeds':sum(individual),'seed_count':len(SEEDS)}
    assert all(sha(p)==h for p,h in before.items())
    protocol={'method':'D03_plain_text_tfidf_svd_xy','sizes':SIZES,'seeds':SEEDS,'class_ratio':'1:1',
        'sampling':'Nested separately by label; approximate topic proportions; same sampler as historical experiment',
        'fit_pool_count':226,'projection_frozen':True,'cutoff_frozen':True,'fusion_frozen':True,
        'test_counts':{'original':176,'variant':80},'model_scores_reused':True,'new_llm_inference':False,
        'new_training':False,'query_z_used':False,'independent_validation':False,
        'source_sha256':sha(Path(__file__)),'profile_sha256':sha(runtime['xy_profile']),
        'baseline_summary_sha256':sha(baseline/'summary.json'),
        'full_size_predictions_match_previous':True,'active_runtime_unchanged':True}
    save('final-size-runs.json',runs)
    save('final-size-summary.json',{'status':'COMPLETED_EXPLORATORY','protocol':protocol,'curve':curves,'trends':trends})
    print(json.dumps({'curve':curves,'trends':trends},ensure_ascii=False))

if __name__=='__main__':run()

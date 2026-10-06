"""V4 inference with the selected model, retrieval method and distance-based fusion."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from fusion import combine
from common import read
import argparse,json,math
from collections import Counter


def validate_policy(policy):
    if policy.get('type')!='distance_gate':
        raise ValueError('Active V4 requires distance-based value gating')
    for key,lo,hi in (('rag_cap',0,1),('model_attenuation',0,1),('distance_multiplier',0,None)):
        value=policy.get(key)
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
            raise ValueError('Finite numeric '+key+' required')
        if value<lo or (key=='distance_multiplier' and value==0) or (hi is not None and value>hi):
            raise ValueError('Invalid '+key)
    return policy


def validate_model_selection(runtime,cfg):
    variant=runtime.get('model_variant')
    model=cfg['model']
    if variant=='original_E2B_no_adapter':
        if model.get('adapter_path') or model.get('adapter_revision'):
            raise ValueError('Original E2B diagnostic cannot load an adapter')
    elif variant=='v3_finetuned_final':
        selected=read(HERE/'final-selection.json')['model']
        if (Path(model.get('adapter_path','')).resolve()!=Path(selected['adapter_path']).resolve()
                or model.get('adapter_revision')!=selected['adapter_revision']):
            raise ValueError('Only the selected V3 adapter may serve as the final model')
    else:
        raise ValueError('Unknown or retired model selection')
    return variant


class V4Pipeline:
    def __init__(self,base,policy,runtime):
        self.base,self.policy,self.runtime=base,validate_policy(dict(policy)),runtime

    @classmethod
    def load(cls,runtime_path=None,overrides=None):
        path=runtime_path or HERE/'active_runtime.json'
        runtime=read(path)
        from architecture.pipeline.__main__ import _settings
        cfg,_=_settings(runtime['inference_config'])
        variant=validate_model_selection(runtime,cfg)
        policy=read(runtime['fusion_config'])
        policy.update(overrides or {})
        validate_policy(policy)
        if runtime.get('retrieval_method')=='D03_plain_text_tfidf_svd_xy':
            from d03_retrieval import D03CasePipeline
            base=D03CasePipeline.load(path)
        else:
            raise ValueError('The packaged final release only supports the selected D03 retrieval')
        if variant=='original_E2B_no_adapter' and ('adapter:' in base.model.identity or hasattr(base.model.model,'peft_config')):
            raise ValueError('An adapter was unexpectedly loaded')
        if variant=='v3_finetuned_final' and 'adapter:' not in base.model.identity:
            raise ValueError('The final V3 adapter was not loaded')
        counts=Counter(e['label'] for e in base.index.entries)
        if not counts['SCAM'] or counts['SCAM']!=counts['NON_SCAM']:
            raise ValueError('Active V4 RAG must have exactly equal SCAM/NON_SCAM counts')
        if base.config['k_max']!=5:
            raise ValueError('Active V4 uses at most five final cases')
        base.config['region_candidates']=len(base.index.entries)
        base.index.config['region_candidates']=len(base.index.entries)
        return cls(base,policy,runtime)

    def adjust(self,result):
        reference=result['final']
        selected=result['retrieval']['selected']
        final=combine(result['model']['model_margin'],result['rag']['R'],
                      [h['distance'] for h in selected],self.base.config['distance_cutoff'],self.policy)
        q=final['distance_quality']
        result['v3_reference_final']=reference
        result['rag']['original_V']=result['rag']['V']
        result['rag']['V']=q
        result['rag']['distance_value']=q
        result['rag']['effective_rag_share']=final['rag_share']
        result['rag']['distance_cutoff_used']=self.base.config['distance_cutoff']*self.policy['distance_multiplier']
        for hit in result['rag']['selected']:
            hit['original_proximity']=hit['proximity']
            hit['proximity']=max(0.,1-hit['distance']/result['rag']['distance_cutoff_used'])
        result['final']={**final,'model_share':1-final['rag_share'],
                         'model_margin_scale':1-(1-self.policy['model_attenuation'])*q}
        result['v4']={'temporary':self.runtime.get('temporary',True),'model_variant':self.runtime['model_variant'],'policy':self.policy,
                      'final_reference_cases_max':5,'retrieved_text_supplied_to_llm':False}
        return result

    def analyze(self,messages,query_id=None,query_group=None):
        return self.adjust(self.base.analyze(messages,query_id,query_group))

    def analyze_features(self,messages,coord,embedding,query_id=None,query_group=None):
        if self.runtime.get('retrieval_method')=='D03_plain_text_tfidf_svd_xy':
            # Legacy coordinates/embeddings must not override the frozen D03 text map.
            return self.analyze(messages,query_id,query_group)
        return self.adjust(self.base.analyze_features(messages,coord,embedding,query_id,query_group))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--runtime')
    parser.add_argument('--rag-cap',type=float)
    parser.add_argument('--distance-multiplier',type=float)
    parser.add_argument('--model-attenuation',type=float)
    args=parser.parse_args()
    overrides={key:value for key,value in (('rag_cap',args.rag_cap),('distance_multiplier',args.distance_multiplier),('model_attenuation',args.model_attenuation)) if value is not None}
    value=read(args.input)
    result=V4Pipeline.load(args.runtime,overrides).analyze(value['messages'] if isinstance(value,dict) else value)
    print(json.dumps(result,ensure_ascii=False,indent=2))

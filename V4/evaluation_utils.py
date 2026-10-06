"""Final evaluation helpers, independent of retired exploratory scripts."""
import json
from pathlib import Path
from collections import Counter
HERE=Path(__file__).resolve().parent

def save(path,value):
    path=Path(path).resolve()
    if not path.is_relative_to(HERE):raise ValueError('V4 output required')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def transitions(rows,baseline,mode):
    fixed=harmed=changed=0
    for r in rows:
        truth={'SCAM':'HIGH','NON_SCAM':'LOW'}[r['label']]
        a,b=r['variants'][baseline]['level'],r['variants'][mode]['level']
        fixed+=a!=truth and b==truth;harmed+=a==truth and b!=truth;changed+=a!=b
    return {'fixed_error':fixed,'correct_to_error':harmed,'level_changes':changed}

def measure(rows,mode):
    confusion={label:{level:0 for level in ('LOW','UNKNOWN','HIGH','INPUT_ERROR')} for label in ('SCAM','NON_SCAM')}
    for r in rows:confusion[r['label']][r['variants'][mode]['level']]+=1
    tp=confusion['SCAM']['HIGH'];tn=confusion['NON_SCAM']['LOW'];fp=confusion['NON_SCAM']['HIGH']
    unknown=sum(c['UNKNOWN'] for c in confusion.values());errors=sum(c['INPUT_ERROR'] for c in confusion.values())
    scam_count=sum(confusion['SCAM'].values());count=len(rows)
    precision=tp/(tp+fp) if tp+fp else 0.;recall=tp/scam_count if scam_count else 0.
    return {'count':count,'correct':tp+tn,'accuracy':(tp+tn)/count if count else None,
        'opposite_label_errors':confusion['SCAM']['LOW']+fp,'unknown':unknown,
        'coverage':1-(unknown+errors)/count if count else None,'scam_precision':precision,
        'scam_recall':recall,'scam_f1':2*precision*recall/(precision+recall) if precision+recall else 0.,
        'confusion':confusion,'input_errors':errors}

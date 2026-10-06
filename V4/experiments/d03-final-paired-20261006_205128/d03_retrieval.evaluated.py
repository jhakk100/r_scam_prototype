"""Frozen D03: plain dialogue TF-IDF/SVD coordinates, label-free XY search."""
import sys, math, hashlib
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'V3'))
from common import read, sha
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from architecture.pipeline.input import prepare_input
from case_retrieval import model_input
from topic_behavior import Extractor
from core import rag_evidence, fuse


class D03Index:
    def __init__(self, profile, entries, config):
        self.profile, self.entries, self.config = profile, list(entries), config
        if len({e['conversation_id'] for e in entries}) != len(entries):
            raise ValueError('Unique RAG IDs required')
        if any(e['split'] != 'train' or not e['verified'] for e in entries):
            raise ValueError('Only verified training cases may enter D03')
        if any(e['label'] not in ('SCAM', 'NON_SCAM') or e['xyz'][2] != int(e['label'] == 'SCAM') for e in entries):
            raise ValueError('Stored labels/Z disagree')
        self.xy = np.asarray([e['xyz'][:2] for e in entries], dtype=float)
        self.vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 4),
            min_df=2, max_features=12000, sublinear_tf=True, vocabulary=profile['vocabulary'])
        self.vectorizer.idf_ = np.asarray(profile['idf'], dtype=float)
        self.components = np.asarray(profile['components'], dtype=float)

    def transform(self, messages):
        # No speaker names, JSON serialization, outcome labels, or query Z.
        text = '\n'.join(m['text'] for m in messages)
        raw = np.asarray(self.vectorizer.transform([text]) @ self.components.T)[0]
        norm = self.profile['normalization']
        return (raw - np.asarray(norm['center'])) / np.asarray(norm['scale'])

    def search(self, messages, query_id=None, query_group=None, query_hash=None):
        xy = self.transform(messages)
        distances = np.linalg.norm(self.xy - xy, axis=1) / math.sqrt(2)
        eligible = [i for i, e in enumerate(self.entries)
            if e['conversation_id'] != query_id and e['case_group_id'] != query_group
            and e['input_sha256'] != query_hash]
        ordered = sorted(eligible, key=lambda i: (float(distances[i]), self.entries[i]['conversation_id']))[:self.config['k_retrieve']]
        candidates = []
        for i in ordered:
            e = self.entries[i]
            candidates.append({k: e[k] for k in ('conversation_id', 'case_group_id', 'label', 'xyz')})
            candidates[-1]['distance'] = float(distances[i])
        selected, groups = [], set()
        for h in candidates:
            if h['case_group_id'] in groups:
                continue
            selected.append(h); groups.add(h['case_group_id'])
            if len(selected) == self.config['k_max']:
                break
        return xy.tolist(), {'selected': selected, 'candidates': candidates,
            'region_size': len(eligible), 'metric': 'plain_text_tfidf_svd_xy_euclidean_div_sqrt2',
            'query_label_used': False, 'query_z_used_for_search': False, 'topic_filter_used': False}


class D03CasePipeline:
    def __init__(self, model, profile, entries, config, rules):
        self.model, self.config = model, config
        self.index = D03Index(profile, entries, config)
        self.extractor = Extractor(rules)

    @classmethod
    def load(cls, runtime_path):
        from architecture.pipeline.backends import TransformersModelScorer
        from architecture.pipeline.__main__ import _settings
        from model_training.artifacts import adapter_fingerprint
        runtime = read(runtime_path)
        cfg, _ = _settings(runtime['inference_config'])
        if cfg['model'].get('adapter_path'):
            assert adapter_fingerprint(cfg['model']['adapter_path']) == cfg['model']['adapter_revision']
        index = read(runtime['index'])
        assert index['profile_sha256'] == sha(runtime['xy_profile'])
        return cls(TransformersModelScorer.load(cfg['model']), read(runtime['xy_profile']),
            index['entries'], read(runtime['retrieval_config']), read(runtime['projection'])['rules'])

    def analyze(self, messages, query_id=None, query_group=None):
        prepared = prepare_input(messages)
        xy, hits = self.index.search(messages, query_id, query_group, prepared.sha256)
        rag = rag_evidence(hits['selected'], self.config['distance_cutoff'])
        # Preserve the exact label-free model input used to train/evaluate V3.
        text = model_input(messages, self.extractor.extract(messages))
        scores = self.model.score(text)
        z = (1 + rag['R']) / 2 if hits['selected'] else None
        return {'id': query_id, 'input_sha256': prepared.sha256,
            'model_input_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'coordinate': {'xy': xy, 'estimated_z': z, 'xyz': [*xy, z],
                'z_source': 'retrieved_case_vote', 'query_label_used': False},
            'model': {'identity': self.model.identity, **scores.to_dict()},
            'retrieval': hits, 'rag': rag,
            'final': fuse(scores.margin, rag['R'], rag['V'])}

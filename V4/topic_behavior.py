"""Frozen label-free input features used by the final adapter."""
import re
from common import HERE, read
RULE_PATH=HERE/"runtime/topic_behavior_rules.json"

class Extractor:
    def __init__(self, rules=None):
        self.rules = read(RULE_PATH) if rules is None else rules
        self.context_ids = set(self.rules["contextual_behavior_ids"])
        self.nonassertive = re.compile(self.rules["nonassertive_context_pattern"])
        self.patterns = [[re.compile(s,re.I) for s in b["patterns"]] for b in self.rules["behaviors"]]

    def extract(self, messages):
        if not isinstance(messages,list) or not messages or any(not isinstance(m.get("text"),str) for m in messages):
            raise ValueError("Nonempty dialogue messages required")
        text = "\n".join(m["text"] for m in messages)
        scores = []
        for topic in self.rules["topics"]:
            score = sum(weight*min(3,len(re.findall(re.escape(term),text,re.I))) for term,weight in topic["terms"].items())
            scores.append((score,topic))
        scores.sort(key=lambda v:-v[0])
        score,primary = scores[0]
        if score == 0:
            primary = {"id":"unknown","name":"주제 불명","description":"주제를 확인할 수 없는 대화","objects":[]}
        secondary = [topic for value,topic in scores[1:] if topic["id"] != "daily" and value >= max(3,score*.6)][:1] if score else []
        objects = [word for word in primary["objects"] if re.search(re.escape(word),text,re.I)]
        descriptor = f"대화 주제: {primary['name']}. {primary['description']}. 중심 주제는 {primary['name']}."
        if objects:
            descriptor += " 대화 대상: "+", ".join(objects)+"."
        if secondary:
            descriptor += " 함께 이야기하는 상황: "+secondary[0]["name"]+"."
        evidence = []
        active = [set() for _ in self.patterns]
        mentioned = [set() for _ in self.patterns]
        for turn,m in enumerate(messages):
            for sentence in re.findall(r"[^.!?\n]+[.!?]?",m["text"]):
                nonassertive = bool(self.nonassertive.search(sentence)) or sentence.strip().endswith('?') or bool(re.search('[‘’“”\"\']',sentence))
                for i,(behavior,patterns) in enumerate(zip(self.rules["behaviors"],self.patterns)):
                    hit = next((p.search(sentence) for p in patterns if p.search(sentence)),None)
                    if hit is None:
                        continue
                    mode = "mentioned_or_nonassertive" if behavior["id"] in self.context_ids and nonassertive else "observed_cue"
                    target = mentioned if mode == "mentioned_or_nonassertive" else active
                    target[i].add(turn)
                    evidence.append({"turn":turn,"speaker":m.get("speaker",""),"behavior":behavior["id"],
                                     "name":behavior["name"],"mode":mode,"match":hit.group(0),"sentence":sentence.strip()})
        features = [min(3,len(s))/3 for s in active]+[min(3,len(s))/3 for s in mentioned]
        return {"topic_id":primary["id"],"topic_name":primary["name"],"topic_descriptor":descriptor,
                "topic_status":"MATCHED_BY_RULE" if score else "NO_TOPIC_CUE",
                "topic_terms":objects,"secondary_topics":[t["name"] for t in secondary],
                "behavior_features":features,"behavior_evidence":evidence,
                "feature_names":[b["id"]+suffix for suffix in ("_observed","_mentioned") for b in self.rules["behaviors"]],
                "extraction_method":"lexical_rules_v1_not_verified_annotations"}

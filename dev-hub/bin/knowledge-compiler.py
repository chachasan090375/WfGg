#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,collections,hashlib
from pathlib import Path

def load(p):
    x=json.loads(Path(p).read_text(encoding="utf-8"));return x

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--policy",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();data=load(a.input);policy=load(a.policy)
    groups=collections.defaultdict(list)
    for o in data.get("observations") or []:
        if o.get("rule_key"):groups[str(o["rule_key"])].append(o)
    min_ev=int((policy.get("compiler") or {}).get("minimum_distinct_evidence",2))
    rules=[]
    for key,obs in groups.items():
        sources={str(x.get("source")) for x in obs if x.get("source")}
        values=collections.Counter(json.dumps(x.get("value"),sort_keys=True) for x in obs)
        if len(sources)<min_ev:continue
        value_json,count=values.most_common(1)[0]
        confidence=round(count/len(obs),4)
        rules.append({"rule_id":"rule:"+hashlib.sha256(key.encode()).hexdigest()[:12],
                      "rule_key":key,"value":json.loads(value_json),"confidence":confidence,
                      "evidence_count":len(obs),"distinct_sources":len(sources),"state":"CONFIRMED" if confidence>=0.75 else "INFERRED"})
    result={"schema":"chacha.dev/knowledge-compiler-result/v1","rules":rules,"compiled_count":len(rules)}
    Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("CHACHA_KNOWLEDGE_COMPILER=PASS")
    print("COMPILED_RULES="+str(len(rules)))
if __name__=="__main__":main()
